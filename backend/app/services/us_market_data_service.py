"""
US Equity Market Data Service (키움 미국주식 API 기반).

BinanceMarketDataService 와 동일한 계약(get_candles / fetch_history /
get_candles_by_date)을 구현해 get_market_data_service() 팩토리에 꽂힌다.

저장 규약 (다른 거래소와 다르므로 반드시 숙지):
    1) **타임스탬프는 ET naive** 다. (국내=KST, Binance=UTC)
       미국장 세션 경계(09:30/16:00)는 ET 로 고정이고 DST 로 KST 가 통째로
       1시간 움직이므로, ET 로 저장해야 세션 기준 지표가 일관된다.
    2) **정규장(RTH 09:30~16:00) 분봉만 저장**한다.
       키움 미국 분봉은 프리/애프터/오버나이트(Blue Ocean) 체결도 함께 주는데,
       OHLCV 테이블에 세션 구분 컬럼이 없어 섞어 담으면 이동평균·변동성 등이
       조용히 오염된다. 연장 세션이 필요하면 KiwoomUSAdapter 를 직접 쓸 것.
    3) 1d 는 API 일봉(usa06012)을 쓰지 않고 RTH 1분봉을 영업일로 묶어 만든다.
       API 일봉 종가는 오버나이트 체결까지 반영한 최신가라 정규장 종가와 다르다
       (실측: AAPL 7/30 정규장 334.16 vs API 일봉 312.35).

인증: 미국주식 API 도 국내와 동일한 앱키/시크릿을 쓴다(실측 확인). DB 의
KiwoomUS 계정을 우선 쓰고, 없으면 실서버 Kiwoom 계정의 키를 빌린다.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from ..core.us_trading_hours import (
    MarketPhase,
    classify_session,
    is_trading_day,
    last_completed_business_date,
    minutes_in_session,
)

logger = logging.getLogger(__name__)


class USMarketDataService:
    """키움 미국주식 시세 서비스 (DB-first, 1m 원본 + 런타임 집계)."""

    MAX_DAYS = 730
    DEFAULT_DAYS = 365
    FETCH_LIMIT = 200_000
    ROWS_PER_PAGE = 100          # 키움 응답 실측
    MIN_DB_CANDLES = 100         # 이 미만이면 API 재조회

    # 하루치 원본(프리+정규+애프터+오버나이트)은 약 1,400봉 ≈ 14페이지.
    # 정규장만 남기더라도 페이지는 전부 넘겨야 하므로 여유 계수를 둔다.
    PAGES_PER_DAY = 16

    def __init__(self):
        self._adapter = None

    # ── 어댑터/자격증명 ────────────────────────────────────────────

    def _get_adapter(self):
        """DB 자격증명으로 KiwoomUSAdapter 를 지연 생성."""
        if self._adapter is not None:
            return self._adapter

        from ..adapters.kiwoom_us import KiwoomUSAdapter
        from ..core import security
        from ..db.session import SessionLocal
        from ..models.account import ExchangeAccount

        db = SessionLocal()
        try:
            account = (
                db.query(ExchangeAccount)
                .filter(ExchangeAccount.exchange_name == "KiwoomUS")
                .first()
            )
            if account is None:
                # 미국주식 API 는 국내와 동일 앱키로 열린다 — 실계좌 키를 빌린다.
                account = (
                    db.query(ExchangeAccount)
                    .filter(
                        ExchangeAccount.exchange_name == "Kiwoom",
                        ExchangeAccount.environment == "real",
                    )
                    .first()
                )
            if account is None:
                raise RuntimeError("미국주식 시세 조회용 키움 자격증명을 찾을 수 없습니다")

            app_key = security.decrypt_key(account.encrypted_access_key or "")
            secret_key = security.decrypt_key(account.encrypted_secret_key or "")
        finally:
            db.close()

        self._adapter = KiwoomUSAdapter(app_key=app_key, secret_key=secret_key)
        return self._adapter

    # ── 조회 (팩토리 계약) ─────────────────────────────────────────

    async def get_candles(self, symbol: str, interval: str = "1m", days: int = 730,
                          limit: int = 100000, to_date: str = None) -> List[Dict]:
        """DB 우선, 부족하면 API 백필 후 재조회. 1m 외 인터벌은 런타임 집계."""
        days = min(days, self.MAX_DAYS)
        symbol = (symbol or "").strip().upper()

        aggregation_map = {
            "3m": 3, "5m": 5, "10m": 10, "15m": 15, "30m": 30,
            "60m": 60, "1h": 60, "4h": 240,
        }

        if interval == "1d":
            base = await self.get_candles(symbol, "1m", days, limit * 390, to_date=to_date)
            return self._aggregate_to_daily(base)

        if interval in aggregation_map:
            multiplier = aggregation_map[interval]
            base = await self.get_candles(symbol, "1m", days, limit * multiplier, to_date=to_date)
            aggregated = self._aggregate_candles(base, multiplier)
            logger.info(f"[USMarketData] {symbol} 집계 {len(base)} 1m -> {len(aggregated)} {interval}")
            return aggregated

        if interval != "1m":
            logger.warning(f"[USMarketData] 미지원 인터벌 {interval} — 1m 로 처리")

        end_ref, start_ref = self._resolve_range(days, to_date)
        rows = self._read_db(symbol, start_ref, end_ref)

        if len(rows) < self.MIN_DB_CANDLES:
            logger.info(
                f"[USMarketData] {symbol} DB 부족({len(rows)}) — API 백필 {days}일"
            )
            await self.fetch_history(symbol, "1m", days)
            rows = self._read_db(symbol, start_ref, end_ref)

        return rows[-limit:] if limit else rows

    async def get_candles_by_date(self, symbol: str, interval: str, date_str: str) -> List[Dict]:
        """특정 미국 영업일(YYYY-MM-DD) 하루치."""
        symbol = (symbol or "").strip().upper()
        try:
            target = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"[USMarketData] 잘못된 날짜: {date_str}")
            return []

        start_ref = datetime.combine(target, datetime.min.time())
        end_ref = start_ref + timedelta(days=1)

        rows = self._read_db(symbol, start_ref, end_ref)
        if not rows:
            await self.fetch_history(symbol, "1m", days=5, end_date=target)
            rows = self._read_db(symbol, start_ref, end_ref)

        if interval == "1d":
            return self._aggregate_to_daily(rows)
        multiplier = {"3m": 3, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "1h": 60}.get(interval)
        return self._aggregate_candles(rows, multiplier) if multiplier else rows

    # ── 수집 ──────────────────────────────────────────────────────

    async def fetch_history(self, symbol: str, interval: str = "1m", days: int = 730,
                            limit: int = None, backfill: bool = False,
                            end_date: date = None) -> int:
        """usa06011 연속조회로 과거 분봉을 긁어 OHLCV 에 upsert. 저장 건수 반환.

        연속조회는 날짜 경계를 넘어 계속 과거로 가므로, 목표 시작일에
        도달하거나 페이지 상한에 걸릴 때까지 한 루프로 처리한다.
        """
        symbol = (symbol or "").strip().upper()
        adapter = self._get_adapter()

        anchor = end_date or datetime.now().date()
        target_start = self._business_days_back(anchor, days)
        max_pages = min(days * self.PAGES_PER_DAY + 20, 4000)

        logger.info(
            f"[USMarketData] {symbol} 수집 시작 — {target_start} ~ {anchor} "
            f"(최대 {max_pages}페이지)"
        )

        body = {
            "stex_tp": await adapter.resolve_exchange(symbol),
            "stk_cd": symbol,
            "strt_dt": anchor.strftime("%Y%m%d"),
            "tic_scope": "1",
            "upd_stkpc_tp": "1",
            "exrt_appl_tp": "0",
        }
        if not body["stex_tp"]:
            logger.error(f"[USMarketData] {symbol} 거래소구분 해석 실패 — 수집 중단")
            return 0

        from ..adapters.kiwoom_us import parse_et_timestamp

        total_saved = 0
        cont_yn, next_key = "N", ""
        oldest_seen: Optional[datetime] = None

        for page in range(max_pages):
            try:
                data = await adapter._request(
                    "usa06011", "/api/us/chart", body, cont_yn=cont_yn, next_key=next_key
                )
            except Exception as e:
                logger.error(f"[USMarketData] {symbol} 페이지 {page} 조회 실패: {e}")
                break

            rows = data.get("result_list") or []
            if not rows:
                break

            batch = []
            for row in rows:
                ts = parse_et_timestamp(row.get("bus_dt"), row.get("cntr_tm"))
                if ts is None:
                    continue
                if oldest_seen is None or ts < oldest_seen:
                    oldest_seen = ts
                # 정규장만 저장 (모듈 docstring 규약 2)
                if classify_session(ts) != MarketPhase.REGULAR.value:
                    continue
                batch.append({
                    "symbol": symbol,
                    "timestamp": ts,
                    "time_frame": "1m",
                    "open": abs(float(row.get("open_pric") or 0)),
                    "high": abs(float(row.get("high_pric") or 0)),
                    "low": abs(float(row.get("low_pric") or 0)),
                    "close": abs(float(row.get("cur_prc") or 0)),
                    "volume": int(float(row.get("trde_qty") or 0)),
                })

            total_saved += self._upsert(batch)

            cont_yn, next_key = data.get("_cont_yn", "N"), data.get("_next_key", "")
            if cont_yn != "Y":
                logger.info(f"[USMarketData] {symbol} 연속조회 종료 (page={page})")
                break
            if oldest_seen and oldest_seen.date() <= target_start:
                logger.info(f"[USMarketData] {symbol} 목표 시작일 도달 ({oldest_seen})")
                break
            await asyncio.sleep(0.1)
        else:
            logger.warning(
                f"[USMarketData] {symbol} 페이지 상한({max_pages}) 도달 — "
                f"{oldest_seen} 이전 구간은 미수집"
            )

        logger.info(f"[USMarketData] {symbol} 수집 완료 — 정규장 {total_saved}봉 저장")
        return total_saved

    async def fetch_daily_history(self, symbol: str, years: float = 6.0,
                                  end_date: date = None,
                                  drop_incomplete: bool = True) -> int:
        """usa06012 연속조회로 일봉을 긁어 OHLCV(time_frame='1d')에 upsert.

        분봉은 약 7개월(2026-01-01 이후)까지만 제공되므로, 장기 백테스트용
        시계열은 일봉으로 확보한다. 실측 깊이: AAPL 2020-08-10까지 (1,500봉/15페이지).

        경고 — 이 일봉의 종가는 정규장 종가가 아니다:
            연장·오버나이트(Blue Ocean) 체결까지 반영한 그 영업일의 최종가다.
            정규장 종가와 수 % 벌어질 수 있다(AAPL 2026-07-30: 334.16 vs 312.35).
            분봉이 있는 구간은 RTH 집계 일봉(get_candles interval='1d')이 더 정확하고,
            그 이전 장기 구간은 이 일봉을 쓸 수밖에 없다. 백테스트 스펙에 어느 쪽을
            썼는지 반드시 명시할 것.

        drop_incomplete=True (기본):
            오버나이트 세션이 아직 끝나지 않은 영업일은 저장하지 않는다. 그 값은
            조회할 때마다 달라져 백테스트 재현성을 깨뜨린다.
            (실측 괴리: 진행 중인 날 SPY +0.54% / QQQ +1.32% / SOXX +3.77%,
             완결된 날 중앙 0.04~0.09%)
            시가는 정규장 시가와 사실상 일치한다(괴리 중앙 0.001~0.06%) — 종가보다
            시가 기준 전략이 substrate 신뢰도가 높다.
            거래량은 연장·오버나이트 포함이라 정규장 집계의 1.85~2.2배다.
        """
        symbol = (symbol or "").strip().upper()
        adapter = self._get_adapter()

        anchor = end_date or datetime.now().date()
        stex_tp = await adapter.resolve_exchange(symbol)
        if not stex_tp:
            logger.error(f"[USMarketData] {symbol} 거래소구분 해석 실패 — 일봉 수집 중단")
            return 0

        # 연 252 거래일, 페이지당 100봉 → 여유 2페이지
        max_pages = int(years * 252 / self.ROWS_PER_PAGE) + 2
        body = {
            "stex_tp": stex_tp,
            "stk_cd": symbol,
            "strt_dt": anchor.strftime("%Y%m%d"),
            "upd_stkpc_tp": "1",
            "exrt_appl_tp": "0",
        }

        rows = await adapter._request_paged(
            "usa06012", "/api/us/chart", body, "result_list", max_pages=max_pages
        )

        cutoff = last_completed_business_date() if drop_incomplete else None
        skipped = []

        batch = []
        for row in rows:
            dt_str = (row.get("dt") or "").strip()
            if len(dt_str) != 8:
                continue
            try:
                ts = datetime.strptime(dt_str, "%Y%m%d")
            except ValueError:
                continue
            if cutoff is not None and ts.date() > cutoff:
                skipped.append(ts.date())
                continue
            batch.append({
                "symbol": symbol,
                "timestamp": ts,
                "time_frame": "1d",
                "open": abs(float(row.get("open_pric") or 0)),
                "high": abs(float(row.get("high_pric") or 0)),
                "low": abs(float(row.get("low_pric") or 0)),
                "close": abs(float(row.get("cur_prc") or 0)),
                "volume": int(float(row.get("acc_trde_qty") or 0)),
            })

        saved = self._upsert(batch)
        if batch:
            note = f" (미완결 {len(skipped)}일 제외)" if skipped else ""
            logger.info(
                f"[USMarketData] {symbol} 일봉 {saved}봉 저장 "
                f"({batch[-1]['timestamp'].date()} ~ {batch[0]['timestamp'].date()}){note}"
            )
        else:
            logger.warning(f"[USMarketData] {symbol} 일봉 수집 결과 없음")
        return saved

    # ── 내부 유틸 ─────────────────────────────────────────────────

    @staticmethod
    def _business_days_back(anchor: date, days: int) -> date:
        """anchor 로부터 거래일 기준 days 일 전 (주말/휴장일 건너뜀)."""
        remaining, cursor = days, anchor
        while remaining > 0:
            cursor -= timedelta(days=1)
            if is_trading_day(cursor):
                remaining -= 1
        return cursor

    @staticmethod
    def _resolve_range(days: int, to_date: str = None) -> tuple:
        if to_date:
            try:
                end_ref = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
            except ValueError:
                end_ref = datetime.now()
        else:
            end_ref = datetime.now()
        return end_ref, end_ref - timedelta(days=days)

    @staticmethod
    def _read_db(symbol: str, start_ref: datetime, end_ref: datetime) -> List[Dict]:
        from ..db.session import SessionLocal
        from ..models.ohlcv import OHLCV

        db = SessionLocal()
        try:
            rows = (
                db.query(OHLCV)
                .filter(
                    OHLCV.symbol == symbol,
                    OHLCV.time_frame == "1m",
                    OHLCV.timestamp >= start_ref,
                    OHLCV.timestamp < end_ref,
                )
                .order_by(OHLCV.timestamp.asc())
                .all()
            )
            return [
                {
                    "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": r.open, "high": r.high, "low": r.low,
                    "close": r.close, "volume": r.volume,
                }
                for r in rows
            ]
        finally:
            db.close()

    @staticmethod
    def _upsert(batch: List[Dict]) -> int:
        if not batch:
            return 0
        from sqlalchemy.dialects.postgresql import insert

        from ..db.session import SessionLocal
        from ..models.ohlcv import OHLCV

        db = SessionLocal()
        try:
            stmt = insert(OHLCV).values(batch)
            stmt = stmt.on_conflict_do_update(
                constraint="uix_symbol_timestamp_tf",
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                },
            )
            db.execute(stmt)
            db.commit()
            return len(batch)
        except Exception as e:
            db.rollback()
            logger.error(f"[USMarketData] upsert 실패: {e}")
            return 0
        finally:
            db.close()

    @staticmethod
    def _parse_ts(value) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")

    def _aggregate_candles(self, base: List[Dict], multiplier: int) -> List[Dict]:
        """1m -> N분봉. 정규장 시작(09:30)을 기준으로 버킷을 자른다.

        자정 기준으로 나누면 09:30 시작인 미국장이 반 토막 버킷으로 시작하므로
        세션 시작 기준 경과분으로 버킷을 계산한다.
        """
        if not base or multiplier <= 1:
            return base

        buckets: Dict[datetime, Dict] = {}
        for row in base:
            ts = self._parse_ts(row["timestamp"])
            elapsed = (ts.hour * 60 + ts.minute) - (9 * 60 + 30)
            bucket_start = ts.replace(second=0, microsecond=0) - timedelta(
                minutes=elapsed % multiplier
            )
            slot = buckets.get(bucket_start)
            if slot is None:
                buckets[bucket_start] = {
                    "timestamp": bucket_start.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": row["open"], "high": row["high"],
                    "low": row["low"], "close": row["close"],
                    "volume": row["volume"],
                }
            else:
                slot["high"] = max(slot["high"], row["high"])
                slot["low"] = min(slot["low"], row["low"])
                slot["close"] = row["close"]
                slot["volume"] += row["volume"]

        return [buckets[k] for k in sorted(buckets)]

    def _aggregate_to_daily(self, base: List[Dict]) -> List[Dict]:
        """RTH 1분봉 -> 정규장 기준 일봉. ET 날짜로 묶는다."""
        if not base:
            return []

        buckets: Dict[date, Dict] = {}
        counts: Dict[date, int] = {}
        for row in base:
            ts = self._parse_ts(row["timestamp"])
            day = ts.date()
            slot = buckets.get(day)
            if slot is None:
                buckets[day] = {
                    "timestamp": day.strftime("%Y-%m-%d 00:00:00"),
                    "open": row["open"], "high": row["high"],
                    "low": row["low"], "close": row["close"],
                    "volume": row["volume"],
                }
                counts[day] = 1
            else:
                slot["high"] = max(slot["high"], row["high"])
                slot["low"] = min(slot["low"], row["low"])
                slot["close"] = row["close"]
                slot["volume"] += row["volume"]
                counts[day] += 1

        result = []
        for day in sorted(buckets):
            expected = minutes_in_session(day)
            # 결손이 심한 날은 일봉으로 쓰면 왜곡된다 — 50% 미만이면 제외
            if counts[day] < expected * 0.5:
                logger.warning(
                    f"[USMarketData] {day} 분봉 {counts[day]}/{expected} — 일봉 제외"
                )
                continue
            result.append(buckets[day])
        return result
