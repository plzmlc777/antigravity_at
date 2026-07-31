"""
Kiwoom US Equity Adapter (REST) — 미국주식 시세/차트 전용.

키움 REST API의 미국주식 도메인(`/api/us/*`)을 감싼다. 국내주식 어댑터
(kiwoom_real.py, `/api/dostk/*`)와는 api-id 체계도 응답 스키마도 다르므로
별도 모듈로 분리한다. 토큰 발급/캐싱은 KiwoomBaseAdapter를 그대로 재사용
(국내/미국이 동일한 OAuth 엔드포인트를 쓴다).

지원 범위 (Phase 1 = 조회 전용):
    usa10098  거래소구분 조회   /api/us/stkinfo   ticker -> stex_tp(ND/NY/AM)
    usa20100  현재가 종목정보   /api/us/mrkcond
    usa06011  분 차트           /api/us/chart
    usa06012  일 차트           /api/us/chart

주문 API(ust20000 매수 / ust20001 매도 / ust21070 원장잔고)는 의도적으로
미구현. Paper 모드는 어댑터를 호출하지 않고 OrderExecutionService에서
체결을 시뮬레이션하므로 필요가 없고, 실주문은 해외증권 거래 가능 계좌가
별도로 필요하다(현 ISA 계좌는 508540 오류로 거부됨).

시간 규약 (실측 확인, 2026-07-31 — AAPL 1분봉 3000개 분석):
    - 분봉 cntr_tm 은 **ET(미국 동부시각)** 기준 `YYYYMMDDHHMMSS`. KST 아님.
      근거: 09:30~16:00 구간이 391봉이고 그 시가 333.13/저가 329.59 가
      일봉의 시가 333.10/저가 329.59 와 일치. 거래량도 16시대(=종가 동시호가)
      에 최대.
    - HH 는 24 이상으로 표기될 수 있다(예: 252600 = 다음날 01:26 ET).
      오버나이트 세션(ET 20:00~04:00)이 같은 영업일에 속하기 때문.
    - bus_dt 는 미국 현지 영업일. 세션 구성:
        pre  04:00~09:30 / regular 09:30~16:00 / after 16:00~18:00 /
        overnight 20:00~익일 04:00 (키움 Blue Ocean)
    - 일봉/분봉 모두 strt_dt 는 "조회 종료일"이며 그 이전으로 내림차순 100건씩
      반환된다. 연속조회(cont-yn/next-key)는 날짜 경계를 넘어 계속 과거로 간다.

일봉 주의 (중요):
    usa06012 일봉의 종가는 정규장 종가가 아니라 **연장/오버나이트 체결까지
    반영한 최신가**다. 영업일이 진행 중이면 값이 계속 바뀐다.
    (실측: 7/30 정규장 종가 334.16 vs 일봉 종가 312.35 — 오버나이트 급락 반영)
    정규장 기준 일봉이 필요하면 1분봉을 RTH 구간만 집계할 것.

가격 단위 주의:
    - 차트 API 의 exrt_appl_tp=1 은 일봉 가격을 KRW 로 환산해 내려준다
      (분봉은 무시됨). 본 어댑터는 항상 0(USD 원가격)으로 고정한다.
    - 현재가 API 의 pre_open_pric / pre_high_pric / pre_low_pric 는 "전일" OHLC 다.
      당일 OHLC 는 open_pric / high_pric / low_pric.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from ..core.exchange_interface import ExchangeInterface
from ..core.http_client import HttpClientManager, get_rate_limiter
from ..core.us_trading_hours import classify_session
from .kiwoom_base import KiwoomBaseAdapter

logger = logging.getLogger(__name__)

DEFAULT_US_API_URL = "https://api.kiwoom.com"
PAGE_SIZE_HINT = 100  # 키움이 페이지당 반환하는 행 수 (실측)

# 거래소구분 코드 (usa10098 응답 실측: AAPL->ND, SPY->NY)
STEX_NASDAQ = "ND"
STEX_NYSE = "NY"
STEX_AMEX = "AM"


class KiwoomUSError(Exception):
    """미국주식 API가 return_code != 0 을 반환한 경우."""

    def __init__(self, api_id: str, return_code: Any, message: str):
        self.api_id = api_id
        self.return_code = return_code
        super().__init__(f"[{api_id}] rc={return_code} {message}")


async def _post(url: str, max_retries: int = 3, retry_delay: float = 2.0, **kwargs) -> httpx.Response:
    """레이트리밋 + 5xx/네트워크 재시도 POST (kiwoom_real 과 동일 정책)."""
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            await get_rate_limiter().acquire()
            client = HttpClientManager.get_instance().get_client()
            resp = await client.post(url, **kwargs)
            if resp.status_code < 500:
                return resp
            last_error = httpx.HTTPStatusError(
                f"Server error '{resp.status_code}' for url '{url}'",
                request=resp.request, response=resp)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            last_error = e
        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay * (attempt + 1))
    raise last_error


def _f(value: Any) -> float:
    """키움 숫자 문자열 -> float. '+312.83' / '-25.36' / '' 모두 허용."""
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "").lstrip("+")
    if not text or text == "-":
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _abs_f(value: Any) -> float:
    """OHLC 용. 키움은 일부 필드에 방향 부호를 붙여 내려주므로 절대값을 쓴다."""
    return abs(_f(value))


def parse_et_timestamp(bus_dt: str, cntr_tm: str) -> Optional[datetime]:
    """분봉 시각 문자열 -> ET naive datetime.

    cntr_tm 의 시(HH)는 24 이상일 수 있다(오버나이트 세션이 ET 자정을 넘겨
    같은 영업일에 속함). 24 이상이면 날짜를 하루 넘기고 시를 24로 뺀다.
    """
    raw = (cntr_tm or "").strip()
    if len(raw) < 14:
        return None
    date_part, hh, mm, ss = raw[:8], int(raw[8:10]), int(raw[10:12]), int(raw[12:14])
    try:
        base = datetime.strptime(date_part, "%Y%m%d")
    except ValueError:
        return None
    day_offset, hour = divmod(hh, 24)
    return base + timedelta(days=day_offset, hours=hour, minutes=mm, seconds=ss)


class KiwoomUSAdapter(ExchangeInterface, KiwoomBaseAdapter):
    """미국주식 어댑터 — 시세는 실데이터, 주문은 Paper 전용.

    ExchangeInterface 를 구현하되 주문 계열 메서드는 실패 응답을 돌려준다.
    live_engine 은 Paper 세션에서도 시세 조회(get_current_price /
    get_minute_candles)에 어댑터를 쓰므로 인터페이스 구현이 필요하고,
    체결은 OrderExecutionService 의 is_paper 분기에서 시뮬레이션되므로
    주문 메서드는 호출되지 않는다.
    """

    def __init__(
        self,
        app_key: str = None,
        secret_key: str = None,
        account_no: str = None,
        account_name: str = "",
        api_url: str = None,
    ):
        super().__init__(app_key=app_key, secret_key=secret_key)
        # 모의투자 서버(mockapi)는 미국주식을 지원하지 않는다. 항상 실서버 조회.
        self.base_url = (api_url or DEFAULT_US_API_URL).rstrip("/")
        self.account_no = account_no
        self.account_name = account_name
        # 미국주식은 키움 모의투자 서버가 없다. LiveManager 가 참조하는 속성.
        self.is_virtual = False
        self._stex_cache: Dict[str, str] = {}

    # ── 저수준 호출 ────────────────────────────────────────────────

    async def _request(
        self,
        api_id: str,
        path: str,
        body: Dict[str, Any],
        cont_yn: str = "N",
        next_key: str = "",
    ) -> Dict[str, Any]:
        """단일 페이지 호출. 응답 본문 + 연속조회 헤더를 합쳐 돌려준다."""
        await self._ensure_token()
        if not self.access_token:
            raise KiwoomUSError(api_id, "no_token", "access token 발급 실패")

        headers = {
            **self._get_auth_headers(api_id),
            "cont-yn": cont_yn,
            "next-key": next_key,
        }
        resp = await _post(f"{self.base_url}{path}", json=body, headers=headers)
        data = resp.json()

        return_code = data.get("return_code")
        if return_code not in (0, None):
            message = str(data.get("return_msg", ""))
            # 토큰 만료(8005)면 1회 강제 갱신 후 재시도
            if "8005" in message or "인증" in message:
                await self._force_refresh_token()
                headers["Authorization"] = f"Bearer {self.access_token}"
                resp = await _post(f"{self.base_url}{path}", json=body, headers=headers)
                data = resp.json()
                return_code = data.get("return_code")
                if return_code not in (0, None):
                    raise KiwoomUSError(api_id, return_code, str(data.get("return_msg", "")))
            else:
                raise KiwoomUSError(api_id, return_code, message)

        data["_cont_yn"] = resp.headers.get("cont-yn", "N")
        data["_next_key"] = resp.headers.get("next-key", "")
        return data

    async def _request_paged(
        self,
        api_id: str,
        path: str,
        body: Dict[str, Any],
        list_key: str,
        max_pages: int = 1,
        page_delay: float = 0.2,
    ) -> List[Dict[str, Any]]:
        """cont-yn/next-key 연속조회로 여러 페이지를 이어붙인다."""
        rows: List[Dict[str, Any]] = []
        cont_yn, next_key = "N", ""

        for page in range(max_pages):
            data = await self._request(api_id, path, body, cont_yn=cont_yn, next_key=next_key)
            page_rows = data.get(list_key) or []
            rows.extend(page_rows)

            cont_yn, next_key = data.get("_cont_yn", "N"), data.get("_next_key", "")
            if cont_yn != "Y" or not page_rows:
                break
            if page + 1 < max_pages:
                await asyncio.sleep(page_delay)

        return rows

    # ── 종목/거래소 ────────────────────────────────────────────────

    async def resolve_exchange(self, symbol: str) -> Optional[str]:
        """티커 -> 거래소구분(stex_tp). 프로세스 수명 동안 캐시."""
        ticker = (symbol or "").strip().upper()
        if not ticker:
            return None
        if ticker in self._stex_cache:
            return self._stex_cache[ticker]

        data = await self._request("usa10098", "/api/us/stkinfo", {"stk_cd": ticker})
        items = data.get("list") or []
        if not items:
            logger.warning(f"[KiwoomUS] 거래소구분 조회 실패 — 미상장/미지원 티커: {ticker}")
            return None

        stex_tp = items[0].get("stex_tp")
        self._stex_cache[ticker] = stex_tp
        return stex_tp

    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """종목 메타(한글명/영문명/시장/ETF 여부)."""
        ticker = (symbol or "").strip().upper()
        data = await self._request("usa10098", "/api/us/stkinfo", {"stk_cd": ticker})
        items = data.get("list") or []
        if not items:
            return None
        item = items[0]
        self._stex_cache[ticker] = item.get("stex_tp")
        return {
            "symbol": item.get("stk_cd"),
            "name_kr": item.get("stk_nm"),
            "name_en": item.get("stk_enm"),
            "exchange": item.get("mkgb"),      # NASDAQ / NYSE / AMEX
            "stex_tp": item.get("stex_tp"),
            "sector": item.get("upgb"),
            "is_etf": item.get("isEtf") == "Y",
        }

    # ── 시세 ──────────────────────────────────────────────────────

    async def get_current_price(self, symbol: str) -> Dict[str, Any]:
        """현재가 + 52주 고저 + 당일 OHLC (usa20100).

        조회 실패 시 None 이 아니라 빈 dict 을 반환한다 — live_engine 이
        `tick_data.get('price', 0)` 로 바로 접근하기 때문.
        """
        ticker = (symbol or "").strip().upper()
        stex_tp = await self.resolve_exchange(ticker)
        if not stex_tp:
            return {}

        try:
            data = await self._request(
                "usa20100", "/api/us/mrkcond", {"stex_tp": stex_tp, "stk_cd": ticker}
            )
        except KiwoomUSError as e:
            logger.error(f"[KiwoomUS] 현재가 조회 실패 {ticker}: {e}")
            return {}
        # 주의: pre_* 접두 필드는 "전일" 값이다. 당일 OHLC 는 open_pric/high_pric/low_pric.
        return {
            "symbol": ticker,
            "name": data.get("stk_nm"),
            "stex_tp": stex_tp,
            "currency": data.get("curr_unit") or "USD",
            "price": _abs_f(data.get("cur_prc")),
            "change": _f(data.get("pred_pre")),
            "change_pct": _f(data.get("flu_rt")),
            "volume": _f(data.get("acc_trde_qty")),
            "open": _abs_f(data.get("open_pric")),
            "high": _abs_f(data.get("high_pric")),
            "low": _abs_f(data.get("low_pric")),
            "prev_close": _abs_f(data.get("base_close_pric")),
            "high_52w": _abs_f(data.get("52wk_hgst_pric")),
            "low_52w": _abs_f(data.get("52wk_lwst_pric")),
            "market_cap": _f(data.get("mac")),
            "shares_outstanding": _f(data.get("stk_cnt")),
            "fx_rate_krw": _f(data.get("base_exrt")),  # 기준환율 (참고용, 가격은 USD)
            "trade_suspended": (data.get("trd_susp_tp") or "0") != "0",
        }

    async def get_daily_candles(
        self,
        symbol: str,
        end_date: str = None,
        max_pages: int = 1,
        adjusted: bool = True,
    ) -> List[Dict[str, Any]]:
        """일봉 (usa06012). end_date(YYYYMMDD) 이전으로 내림차순 조회 후
        오름차순으로 정렬해 돌려준다."""
        ticker = (symbol or "").strip().upper()
        stex_tp = await self.resolve_exchange(ticker)
        if not stex_tp:
            return []

        body = {
            "stex_tp": stex_tp,
            "stk_cd": ticker,
            "strt_dt": end_date or datetime.now().strftime("%Y%m%d"),
            "upd_stkpc_tp": "1" if adjusted else "0",
            "exrt_appl_tp": "0",  # 0=USD 원가격, 1=KRW 환산 (일봉에만 적용됨 — 실측)
        }
        rows = await self._request_paged(
            "usa06012", "/api/us/chart", body, "result_list", max_pages=max_pages
        )

        candles = []
        for row in rows:
            dt_str = (row.get("dt") or "").strip()
            if len(dt_str) != 8:
                continue
            candles.append({
                "symbol": ticker,
                "timestamp": datetime.strptime(dt_str, "%Y%m%d"),
                "open": _abs_f(row.get("open_pric")),
                "high": _abs_f(row.get("high_pric")),
                "low": _abs_f(row.get("low_pric")),
                "close": _abs_f(row.get("cur_prc")),
                "volume": _f(row.get("acc_trde_qty")),
            })
        candles.sort(key=lambda c: c["timestamp"])
        return candles

    async def fetch_minute_candles(
        self,
        symbol: str,
        interval_min: int = 1,
        end_date: str = None,
        max_pages: int = 1,
        adjusted: bool = True,
    ) -> List[Dict[str, Any]]:
        """분봉 (usa06011). timestamp 는 ET naive datetime (자정 넘김 보정 포함).

        수집기/백필용 리치 버전. live_engine 이 쓰는 인터페이스 호환 버전은
        get_minute_candles() 를 볼 것.
        """
        ticker = (symbol or "").strip().upper()
        stex_tp = await self.resolve_exchange(ticker)
        if not stex_tp:
            return []

        body = {
            "stex_tp": stex_tp,
            "stk_cd": ticker,
            "strt_dt": end_date or datetime.now().strftime("%Y%m%d"),
            "tic_scope": str(interval_min),
            "upd_stkpc_tp": "1" if adjusted else "0",
            "exrt_appl_tp": "0",  # 0=USD 원가격, 1=KRW 환산 (일봉에만 적용됨 — 실측)
        }
        rows = await self._request_paged(
            "usa06011", "/api/us/chart", body, "result_list", max_pages=max_pages
        )

        candles = []
        for row in rows:
            ts = parse_et_timestamp(row.get("bus_dt"), row.get("cntr_tm"))
            if ts is None:
                continue
            candles.append({
                "symbol": ticker,
                "timestamp": ts,                                     # ET naive
                "business_date": (row.get("bus_dt") or "").strip(),  # 미국 현지 영업일
                "session": classify_session(ts),                     # pre/regular/after/overnight
                "open": _abs_f(row.get("open_pric")),
                "high": _abs_f(row.get("high_pric")),
                "low": _abs_f(row.get("low_pric")),
                "close": _abs_f(row.get("cur_prc")),
                "volume": _f(row.get("trde_qty")),
            })
        candles.sort(key=lambda c: c["timestamp"])
        return candles

    # ── ExchangeInterface 구현 ─────────────────────────────────────

    def get_name(self) -> str:
        return "KiwoomUS"

    def get_account_name(self) -> str:
        return self.account_name or "KiwoomUS"

    async def get_minute_candles(self, symbol: str, interval_minutes: int = 1) -> list:
        """live_engine 호환 분봉. timestamp 는 국내 어댑터와 동일하게
        'YYYYMMDDHHMMSS' 문자열이되 **ET 기준**(24시 롤오버 보정 완료)."""
        try:
            rich = await self.fetch_minute_candles(symbol, interval_min=interval_minutes)
        except KiwoomUSError as e:
            logger.error(f"[KiwoomUS] 분봉 조회 실패 {symbol}: {e}")
            return []

        return [
            {
                "timestamp": c["timestamp"].strftime("%Y%m%d%H%M%S"),
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c["volume"],
            }
            for c in rich
        ]

    async def get_balance(self) -> Dict[str, Any]:
        """조회 전용 어댑터 — 잔고 API(ust21070)는 해외증권 주문 가능 계좌가
        필요하다. 빈 dict 을 반환해 LiveContext.async_sync_balance 가 조용히
        건너뛰게 한다(Paper 잔고는 체결 기록으로 자체 관리)."""
        return {}

    def _order_unsupported(self, action: str, symbol: str) -> Dict[str, Any]:
        message = (
            f"KiwoomUS 어댑터는 실주문을 지원하지 않습니다 ({action} {symbol}). "
            "Paper 모드에서만 사용하십시오."
        )
        logger.error(f"[KiwoomUS] {message}")
        return {"status": "failed", "message": message, "order_id": None}

    async def place_buy_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        return self._order_unsupported("BUY", symbol)

    async def place_sell_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        return self._order_unsupported("SELL", symbol)

    async def cancel_order(self, order_id: str, symbol: str, quantity: int,
                           origin_order_id: str = "") -> Dict[str, Any]:
        return self._order_unsupported("CANCEL", symbol)

    async def get_outstanding_orders(self) -> list:
        return []

    async def get_order_executions(self, order_no: str = "", symbol: str = "") -> List[Dict[str, Any]]:
        return []
