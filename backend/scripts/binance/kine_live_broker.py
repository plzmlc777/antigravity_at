"""속도저울(s2both) 의 **실거래 체결 계층**. 페이퍼 시뮬레이터는 건드리지 않는다.

왜 새 모듈인가 (2026-09-05)
    `rsi_live_broker.LiveBroker` 는 **롱 전용**이다. `positions()` 가
    `q > 0` 만 담고, 손절은 `side="SELL"` 하드코딩이며, 청산 체결 복원은
    "꼬리에서 연속된 SELL" 만 모은다. 속도저울은 숏이 다리의 절반이다.

    그 파일을 방향 파라미터화하는 편이 코드량은 적지만, **그것은 지금
    실자금을 굴리는 계좌 8 의 브로커다.** 회귀가 나면 두 트랙이 동시에
    무너진다. 그래서 어댑터를 직접 쓰는 새 계층을 만들고, RSI 브로커에서는
    **검증된 방어 장치만** 이식했다.

이식한 방어 장치 (전부 실계좌 사고에서 나왔다)
    · 조회 실패는 빈 결과가 아니라 `None` — 모르는 것과 없는 것은 다르다 (교훈#106)
    · 체결가 0 이면 추측하지 말고 체결 내역에 물어본다 (2026-08-31 NAORISUSDT)
    · 끝내 모르면 **즉시 되판다** — 보호 없는 고아를 남기느니 왕복 수수료가 싸다
    · 레버리지는 주문 **전에** 맞추고, 실패하면 진입하지 않는다 (교훈#102)
    · 배경 이벤트 루프는 **하나만** 쓴다 — 어댑터 HTTP 클라이언트가 전역이다

수명 주기
    진입   시장가(테이커) → 체결가·수량 확정 → **즉시** 손절 조건부 주문 등록
    손절   거래소가 트리거한다. 매 사이클 포지션 대조로 알아챈다
    만기   손절 주문 **취소 먼저** → 시장가 청산
    재시작 거래소 포지션을 읽어 상태를 맞춘다

⚠ 손절을 거래소에 거는 이유 — 격자가 5분이라 우리 루프가 판정하면 최대
   5분 늦는다. 그 사이 -5% 는 훨씬 지나간다. 거래소가 밀리초에 트리거하게
   맡긴다. 프로세스가 죽어도 손절은 살아 있다.

⚠ `close_position=True` 는 **포지션이 있어야만** 등록된다(-4509). 진입
   직후에만 걸 수 있고 미리 걸어둘 수 없다.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

# ⚠ 배경 루프·오류코드 파서는 **공유한다.** 루프를 새로 만들면 어댑터의
#   전역 HTTP 클라이언트가 처음 만든 루프에 묶인 채 두 루프가 생겨
#   `Event loop is closed` 로 조회가 조용히 실패한다(2026-08-22 실계좌).
#   RSI 브로커와는 별도 프로세스로 도므로 상태를 공유하지 않는다.
#
# ⚠ import 경로 — PM2 러너는 `PYTHONPATH=.` 만 주고 `-m scripts.binance.…`
#   로 띄운다. 그러면 이 파일이 있는 디렉터리는 sys.path 에 **없다**.
#   맨이름 import 는 예비비행(`PYTHONPATH=.:scripts/binance`)에서만 통하고
#   본실행에서 죽는다 — 두 경로가 다르면 예비비행이 검증이 아니다.
try:
    from scripts.binance.rsi_live_broker import _err_code, _run
except ImportError:                                   # 직접 실행·대화형용
    from rsi_live_broker import _err_code, _run

log = logging.getLogger("kine_live")

FAPI_PATH = "/fapi/v1"
FAPI_V2_PATH = "/fapi/v2"


@dataclass
class KineOrder:
    symbol: str
    order_id: str
    price: float
    qty: float


@dataclass
class KineLiveBroker:
    """계좌 하나를 잡고 롱·숏 양방향으로 체결한다.

    ⚠ 이 브로커는 계좌를 **독점한다고 가정한다.** `positions()` 가 계좌의
      모든 포지션을 자기 것으로 읽는다. 다른 전략과 계좌를 공유하면 남의
      포지션을 자기 것으로 착각한다 — 계좌 15 는 이 트랙 전용이다.
    """

    account_id: int
    # ⚠ 기본 1배. 문서 §4.2 — 배수를 올리면 -5% 손절이 자본의 -5% 가 아니게
    #   된다. 그리고 거래소 레버리지는 **옛 트랙 값이 남는다**(교훈#102).
    leverage: int = 1
    dry_run: bool = False

    _adapter: Any = field(default=None, init=False, repr=False)
    _lev_done: dict = field(default_factory=dict)
    sl_orders: dict = field(default_factory=dict)      # 종목 → KineOrder
    entry_ms: dict = field(default_factory=dict)       # 종목 → 진입 시각(ms)
    last_error: Any = None
    notify: Any = None                                 # callable(str)

    # ── 연결 ────────────────────────────────────────────────
    def connect(self) -> None:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from sqlalchemy import text

        from app.adapters.binance_futures import BinanceFuturesAdapter
        from app.core.security import decrypt_key
        from app.db.session import engine

        with engine.connect() as c:
            r = c.execute(text(
                "select encrypted_access_key, encrypted_secret_key, api_url, "
                "account_name, environment from exchange_accounts where id=:i"),
                {"i": self.account_id}).fetchone()
        if not r:
            raise SystemExit(f"계좌 {self.account_id} 없음")
        if str(r[4]).lower() != "real":
            log.warning("계좌 %s 는 environment=%s — 실거래가 아니다",
                        self.account_id, r[4])
        self._adapter = BinanceFuturesAdapter(
            decrypt_key(r[0]), decrypt_key(r[1]),
            r[2] or "https://fapi.binance.com")
        _run(self._adapter._ensure_exchange_info())
        log.info("속도저울 실거래 브로커 연결 — 계좌 %s(%s) · 레버리지 %dx%s",
                 self.account_id, r[3], self.leverage,
                 " · DRY-RUN" if self.dry_run else "")

    # ── 조회 ────────────────────────────────────────────────
    def wallet_balance(self) -> Optional[float]:
        """지갑 잔고(USDT, 실현 기준). 실패하면 None.

        ⚠ **평가액이 아니라 지갑**이다. 미실현을 자본에 넣으면 아직 확정도
          안 된 이익 위에 다음 포지션을 키운다."""
        try:
            d = _run(self._adapter._signed_get(f"{FAPI_V2_PATH}/account", {}))
            v = float((d or {}).get("totalWalletBalance") or 0.0)
            return v if v > 0 else None
        except Exception as e:                            # noqa: BLE001
            log.error("지갑 조회 실패: %s", e)
            return None

    def positions(self, strict: bool = False) -> dict | None:
        """열린 포지션 {종목: **부호 있는** 수량}. 롱 양수 · 숏 음수.

        ⚠ RSI 브로커와 다른 점이 바로 여기다. 저쪽은 `q > 0` 만 담아
          숏을 통째로 못 본다.

        ⚠ `strict=True` 면 조회 실패에 **None**. 빈 딕셔너리와 구분해야
          한다 — 실패를 "포지션이 없다"로 읽으면 보호 주문을 걷어내고
          거래소엔 포지션이 남는 고아가 된다(교훈#106)."""
        try:
            rows = _run(self._adapter._signed_get(
                f"{FAPI_V2_PATH}/positionRisk", {}))
        except Exception as e:                            # noqa: BLE001
            # ⚠ 시각 드리프트로 -1021 이 난다. 즉시 재동기하고 한 번만 더 묻는다.
            log.warning("포지션 조회 실패 — 시각 재동기 후 재시도: %s", e)
            try:
                _run(self._adapter.sync_server_time())
                rows = _run(self._adapter._signed_get(
                    f"{FAPI_V2_PATH}/positionRisk", {}))
                log.info("포지션 조회 재시도 성공")
            except Exception as e2:                       # noqa: BLE001
                log.error("포지션 조회 실패(재시도까지): %s", e2)
                return None if strict else {}
        out = {}
        for p in rows or []:
            q = float(p.get("positionAmt", 0) or 0)
            if q != 0:
                out[p["symbol"]] = q
        return out

    def open_algo_orders(self) -> dict:
        """미체결 조건부 주문 {종목: [algoId]}."""
        try:
            rows = _run(self._adapter.get_open_algo_orders())
        except Exception as e:                            # noqa: BLE001
            log.error("조건부 주문 조회 실패: %s", e)
            return {}
        out: dict = {}
        for o in rows or []:
            out.setdefault(o.get("symbol"), []).append(str(o.get("algoId")))
        return out

    # ── 레버리지 ────────────────────────────────────────────
    def ensure_leverage(self, symbol: str) -> Optional[int]:
        """주문 **전에** 배수를 맞춘다. 실패하면 None — 진입하지 않는다.

        ⚠ 실패했는데 진입하면 모르는 배수로 실자금이 돈다. 거래소 레버리지는
          계좌·종목 속성이라 **옛 트랙 값이 남아 있다**(교훈#102)."""
        want = max(1, int(self.leverage))
        if self._lev_done.get(symbol) == want:
            return want
        if self.dry_run:
            self._lev_done[symbol] = want
            return want
        try:
            r = _run(self._adapter.set_leverage(symbol, want))
        except Exception as exc:                          # noqa: BLE001
            log.error("%s 레버리지 %dx 설정 실패: %s", symbol, want, exc)
            return None
        if r.get("status") != "success":
            log.error("%s 레버리지 %dx 거절: %s", symbol, want,
                      r.get("message") or r)
            return None
        got = int(r.get("leverage") or want)
        self._lev_done[symbol] = got
        log.info("%s 레버리지 %dx 적용", symbol, got)
        return got

    # ── 수량 ────────────────────────────────────────────────
    def size(self, symbol: str, notional: float,
             ref_price: float) -> tuple[float, str]:
        """명목을 거래소 규칙에 맞춘 수량으로 바꾼다. (수량, 사유) 를 준다.

        수량 0 이면 진입하지 않는다 — 사유를 함께 돌려 로그에 남긴다.
        페이퍼는 521종목 전부를 보지만 실거래에는 **최소 명목**이 있다
        (문서 §4.4)."""
        if ref_price <= 0 or notional <= 0:
            return 0.0, "가격/명목 0"
        f = self._adapter.get_symbol_precision(symbol)
        try:
            min_notional = float(f.get("minNotional", "5") or 5)
        except (TypeError, ValueError):
            min_notional = 5.0
        if notional < min_notional:
            return 0.0, f"명목 ${notional:.2f} < 최소 ${min_notional:.2f}"
        qty = self._adapter.adjust_quantity(symbol, notional / ref_price,
                                            ref_price)
        if qty <= 0:
            return 0.0, "수량 반올림 결과 0(stepSize)"
        # ⚠ 반올림이 **내림**이라 최소 명목 아래로 떨어질 수 있다. 다시 잰다.
        if qty * ref_price < min_notional:
            return 0.0, (f"반올림 후 명목 ${qty * ref_price:.2f} "
                         f"< 최소 ${min_notional:.2f}")
        return float(qty), ""

    # ── 진입 ────────────────────────────────────────────────
    def open(self, symbol: str, short: bool, ref_price: float,
             notional: float) -> Optional[dict]:
        """시장가 진입. 체결가·수량을 **거래소 응답에서** 받는다.

        문서 §4.1 — 이 갈래는 진입 시각이 규칙의 일부다(5분 격자 · 신호
        즉시). 지정가로 걸어 미체결되면 규칙이 아니라 다른 전략이 된다.
        왕복 수수료 0.072% 도 이미 테이커 기준이다."""
        self.last_error = None
        qty, why = self.size(symbol, notional, ref_price)
        if qty <= 0:
            log.info("%s 진입 건너뜀 — %s", symbol, why)
            self.last_error = {"code": None, "msg": why}
            return None
        lev = self.ensure_leverage(symbol)
        if lev is None:
            log.error("%s 레버리지 미설정 — 진입하지 않는다", symbol)
            self.last_error = {"code": None, "msg": "레버리지 미설정"}
            return None
        side = "숏" if short else "롱"
        if self.dry_run:
            log.info("[DRY] %s %s 시장가 진입 %.8g (기준 %.8g · 명목 $%.2f)",
                     symbol, side, qty, ref_price, notional)
            return {"price": ref_price, "quantity": qty, "leverage": lev}
        # 체결 내역을 되찾을 때 이 시각 이후만 본다 — 지난 거래가 섞이면 안 된다.
        placed_ms = int(time.time() * 1000) - 5_000
        try:
            if short:
                r = _run(self._adapter.place_short_order(symbol, 0.0, qty))
            else:
                r = _run(self._adapter.place_buy_order(symbol, 0.0, qty))
        except Exception as e:                            # noqa: BLE001
            log.error("%s %s 진입 실패: %s", symbol, side, e)
            self.last_error = {"code": _err_code(e), "msg": str(e)}
            return None
        if r.get("status") != "success":
            m = r.get("message") or str(r)
            log.error("%s %s 진입 거절: %s", symbol, side, m)
            self.last_error = {"code": _err_code(m), "msg": str(m)}
            return None
        px = float(r.get("price") or 0)
        q = float(r.get("quantity") or 0)
        if px <= 0 or q <= 0:
            # ⚠ 체결가 0 을 위로 올리면 상위가 이론가로 대체해 회계가 어긋난다.
            #   **주문은 이미 나갔다** — 여기서 None 만 주면 포지션이 열린 채
            #   장부에서 사라진다. 추측하지 말고 체결 내역에 물어본다.
            log.error("%s 체결가/수량이 0 (px=%s qty=%s) — 체결 내역에서 되찾는다",
                      symbol, px, q)
            fpx, fq = self.entry_fill(symbol, placed_ms, short)
            if fpx > 0 and fq > 0:
                px, q = fpx, fq
                log.warning("%s 진입가 복구 — %.8g @ %.8g (체결 내역)",
                            symbol, q, px)
            else:
                held = float((self.positions() or {}).get(symbol, 0) or 0)
                if held != 0:
                    log.error("%s 체결가를 끝내 못 찾았는데 포지션 %.8g 이 "
                              "열려 있다 — 고아를 남기지 않고 즉시 청산한다",
                              symbol, held)
                    try:
                        _run(self._adapter.close_position(symbol))
                        self._tell_orphan(symbol, held)
                    except Exception as exc:              # noqa: BLE001
                        log.critical("%s 고아 청산 실패 — 수동 개입 필요: %s",
                                     symbol, exc)
                return None
        log.info("%s %s 실거래 진입 — %.8g @ %.8g (%dx · 명목 $%.2f)",
                 symbol, side, q, px, lev, q * px)
        self.entry_ms[symbol] = placed_ms
        return {"price": px, "quantity": q, "leverage": lev}

    # ── 손절 ────────────────────────────────────────────────
    def arm_stop(self, symbol: str, short: bool, entry_px: float,
                 stop_pct: float) -> bool:
        """진입 **직후** 손절 조건부 주문을 거래소에 건다.

        ⚠ `close_position=True` 는 포지션이 있어야만 등록된다(-4509).
          그래서 진입 직후에만 부를 수 있다.

        ⚠ 트리거 후 **시장가**다. 갭이 나면 손절가보다 나쁘게 체결된다 —
          페이퍼는 손절가 정확 체결을 가정하므로 그만큼 낙관 편향이다
          (문서 §6 ③). 실거래에서 그 차이를 재는 것이 목적 중 하나다."""
        if stop_pct <= 0:
            return True
        trig = entry_px * ((1 + stop_pct / 100.0) if short
                           else (1 - stop_pct / 100.0))
        trig = self._adapter.adjust_price(symbol, trig)
        # 롱을 닫으려면 SELL, 숏을 닫으려면 BUY
        side = "BUY" if short else "SELL"
        if self.dry_run:
            log.info("[DRY] %s 손절 %s 트리거 %.8g", symbol, side, trig)
            return True
        try:
            r = _run(self._adapter.place_algo_stop(
                symbol, side=side, trigger_price=trig,
                limit_price=0.0,          # STOP_MARKET — 체결 보장, 가격 미보장
                close_position=True))
        except Exception as e:                            # noqa: BLE001
            log.critical("%s 손절 등록 예외 — **보호 없는 포지션**: %s", symbol, e)
            self._tell_naked(symbol, str(e))
            return False
        if (r or {}).get("status") != "success":
            m = (r or {}).get("message") or str(r)
            log.critical("%s 손절 등록 거절 — **보호 없는 포지션**: %s", symbol, m)
            self._tell_naked(symbol, str(m))
            return False
        # ⚠ 어댑터가 돌려주는 키는 **`algo_id`** 다(`algoId` 아님).
        #   틀리면 번호가 빈 채로 저장돼 취소가 종목 전체 걷기로 후퇴한다 —
        #   조용히 동작해서 안 보인다(교훈#88).
        oid = str(r.get("algo_id") or "")
        self.sl_orders[symbol] = KineOrder(symbol=symbol, order_id=oid,
                                           price=trig, qty=0.0)
        log.info("%s 손절 등록 — %s 트리거 %.8g (id %s)", symbol, side, trig, oid)
        return True

    def cancel_stop(self, symbol: str) -> None:
        """만기 청산 **전에** 반드시 부른다.

        ⚠ 남겨두면 다음 진입을 엉뚱하게 청산한다. 번호를 모르면 종목 전체
          조건부 주문을 걷는다 — 이 세션은 종목당 손절 하나만 건다."""
        o = self.sl_orders.pop(symbol, None)
        if self.dry_run:
            return
        try:
            if o is not None and o.order_id:
                r = _run(self._adapter.cancel_algo_order(symbol, o.order_id))
            else:
                r = _run(self._adapter.cancel_all_algo_orders(symbol))
            if (r or {}).get("status") != "success":
                log.warning("%s 손절 취소 실패: %s", symbol,
                            (r or {}).get("message") or r)
        except Exception as e:                            # noqa: BLE001
            log.warning("%s 손절 취소 예외: %s", symbol, e)

    # ── 청산 ────────────────────────────────────────────────
    def close(self, symbol: str, short: bool) -> Optional[float]:
        """손절 주문을 걷고 시장가로 전량 청산한다. 체결가를 돌려준다."""
        self.cancel_stop(symbol)
        if self.dry_run:
            log.info("[DRY] %s 시장가 청산", symbol)
            return None
        try:
            r = _run(self._adapter.close_position(symbol))
        except Exception as e:                            # noqa: BLE001
            log.error("%s 청산 실패: %s", symbol, e)
            self.last_error = {"code": _err_code(e), "msg": str(e)}
            return None
        if (r or {}).get("status") != "success":
            m = (r or {}).get("message") or str(r)
            # 이미 닫혀 있으면(손절 체결) 성공으로 본다 — 체결가는 아래에서 찾는다
            log.warning("%s 청산 응답 비정상: %s", symbol, m)
        px = float((r or {}).get("price") or 0)
        if px > 0:
            log.info("%s 청산 체결 %.8g", symbol, px)
            return px
        # 응답이 가격을 안 줬다 — 체결 내역에 물어본다(추측하지 않는다)
        fpx, _ = self.closing_fill(symbol, short)
        if fpx > 0:
            log.info("%s 청산가 복구 %.8g (체결 내역)", symbol, fpx)
            return fpx
        log.error("%s 청산가를 못 찾았다 — 상위가 판단해야 한다", symbol)
        return None

    # ── 체결 내역 ───────────────────────────────────────────
    def _trades(self, symbol: str, since_ms: int = 0) -> list:
        params: dict = {"symbol": symbol, "limit": 100}
        if since_ms:
            params["startTime"] = int(since_ms)
        try:
            return _run(self._adapter._signed_get(
                f"{FAPI_PATH}/userTrades", params)) or []
        except Exception as e:                            # noqa: BLE001
            log.error("%s 체결 내역 조회 실패: %s", symbol, e)
            return []

    def entry_fill(self, symbol: str, since_ms: int,
                   short: bool) -> tuple[float, float]:
        """진입 체결의 (가중평균가, 총수량). 못 찾으면 (0, 0).

        진입 방향은 롱이면 BUY, 숏이면 SELL 이다."""
        want = "SELL" if short else "BUY"
        rows = [t for t in self._trades(symbol, since_ms)
                if str(t.get("side")) == want]
        return self._vwap(rows)

    def closing_fill(self, symbol: str, short: bool) -> tuple[float, float]:
        """청산 체결의 (가중평균가, 총수량). 진입 시각 이후만 본다.

        ⚠ 꼬리에서부터 **연속된 청산 방향**만 모은다 — 그 앞은 진입이다."""
        want = "BUY" if short else "SELL"
        rows = self._trades(symbol, self.entry_ms.get(symbol, 0))
        rows.sort(key=lambda t: int(t.get("time") or 0))
        tail = []
        for t in reversed(rows):
            if str(t.get("side")) != want:
                break
            tail.append(t)
        return self._vwap(tail)

    def roundtrip_fee_pct(self, symbol: str, notional: float,
                          short: bool | None = None) -> Optional[float]:
        """이 거래의 **실제** 왕복 수수료를 명목 대비 %로 돌려준다.

        ⚠ 상수를 쓰지 않는 이유 (2026-09-05 실측) — 명세는 편도 0.036% ·
          왕복 0.072% 를 가정하는데 실제는 **편도 0.0500% · 왕복 0.100%**
          였다(계좌 8·15 동일, VIP 0 테이커 표준). 그 0.028%p 차이가
          '상위 5% 제외 거래당' 을 +0.0156% 에서 -0.0124% 로 뒤집는다.
          가정을 원장에 쓰면 그 오차가 영구히 숨는다 — 거래소에 물어본다.

        진입 시각 이후의 모든 체결 수수료를 더한다(진입 + 청산 + 부분체결).
        못 재면 None — 호출부가 상수로 후퇴하고 **그 사실을 로그에 남긴다**.

        ⚠ **경합** (2026-09-05 실측) — 청산 직후에 물으면 그 체결이 아직
          `userTrades` 에 안 올라와 **편도(0.05%)만 합산**된다. 원장 5·6행이
          그렇게 기록됐고 1~4행은 우연히 반영이 빨라 통과했다. 매번 다르니
          "이번엔 맞았다"로 넘길 수 없다.
          그래서 **양쪽 방향이 다 잡혔는지 확인**하고, 한쪽뿐이면 잠깐 뒤
          한 번만 다시 묻는다. 그래도 없으면 **반쪽 값을 쓰지 않고** None 이다
          — 낙관적인 절반 값이 원장에 남는 것이 최악이다.

        `short` 를 주지 않으면 방향 검사를 못 하므로 예전처럼 단순 합산한다.
        """
        if self.dry_run or notional <= 0:
            return None
        entry_side = "SELL" if short else "BUY"
        exit_side = "BUY" if short else "SELL"

        def _sum(rows) -> tuple[float, set]:
            fee, sides = 0.0, set()
            for t in rows:
                try:
                    fee += float(t.get("commission") or 0.0)
                except (TypeError, ValueError):
                    continue
                sides.add(str(t.get("side")))
            return fee, sides

        since = self.entry_ms.get(symbol, 0)
        fee, sides = _sum(self._trades(symbol, since))
        if short is not None and not {entry_side, exit_side} <= sides:
            time.sleep(1.5)
            fee, sides = _sum(self._trades(symbol, since))
            missing = [lab for side, lab in ((entry_side, "진입"),
                                             (exit_side, "청산"))
                       if side not in sides]
            if missing:
                log.warning("%s 왕복 수수료를 못 잰다 — 체결 내역에 %s 체결이 "
                            "아직 없다(경합). 반쪽 값을 쓰지 않고 상수로 "
                            "후퇴한다", symbol, "·".join(missing))
                return None
        if fee <= 0:
            return None
        return 100.0 * fee / notional

    @staticmethod
    def _vwap(rows: list) -> tuple[float, float]:
        num = den = 0.0
        for t in rows:
            p = float(t.get("price") or 0)
            q = float(t.get("qty") or 0)
            if p > 0 and q > 0:
                num += p * q
                den += q
        return (num / den, den) if den > 0 else (0.0, 0.0)

    # ── 재시작 대조 ─────────────────────────────────────────
    def reconcile(self, own: set | None = None) -> dict | None:
        """거래소와 맞춘다. {종목: 부호수량} 을 돌려준다. **못 읽으면 None.**

        ⚠ 우리 장부에 없는 포지션은 **손대지 않는다** — 수동 개입일 수 있다.
          드러내기만 한다. 포지션 없는데 남은 조건부 주문은 고아라 걷는다.

        ⚠ **반드시 strict 로 읽는다** (2026-09-08 사고). 예전엔 non-strict 라
          조회 실패가 `{}` 로 돌아왔고, 그러면
            ① 호출부가 장부의 포지션을 전부 "거래소에 없다"고 지웠고
            ② 아래 고아 청소가 **살아 있는 포지션의 손절을 전부 취소**했다.
          바이낸스 `-1003` IP 차단 때 실제로 ①이 일어났다(②는 조건부 주문
          조회도 같이 실패해 우연히 면했다). 모르는 것과 없는 것은 다르다."""
        pos = self.positions(strict=True)
        if pos is None:
            log.critical("거래소 포지션을 못 읽었다 — **대조하지 않는다.** "
                         "장부를 지우지도, 조건부 주문을 걷지도 않는다")
            return None
        algo = self.open_algo_orders()
        log.info("거래소 대조 — 포지션 %d종목 · 조건부 주문 %d종목",
                 len(pos or {}), len(algo))
        for sym in list(algo):
            if sym not in (pos or {}):
                log.warning("%s 고아 조건부 주문 발견 — 취소한다", sym)
                self.cancel_stop(sym)
        if own is not None:
            for sym in (pos or {}):
                if sym not in own:
                    log.warning("거래소에 %s 포지션이 있는데 우리 장부엔 없다 "
                                "— 이 세션은 건드리지 않는다", sym)
        return pos or {}

    # ── 알림 ────────────────────────────────────────────────
    def _tell_orphan(self, symbol: str, qty: float) -> None:
        """고아를 되판 사실은 **반드시 크게 알린다** — 조용하면 못 본다."""
        if not callable(self.notify):
            log.critical("%s 고아 즉시청산 — 알림 경로가 없어 로그만 남긴다",
                         symbol)
            return
        try:
            self.notify(
                f"🚨 <b>고아 방지 즉시청산</b> — 속도저울 1군\n"
                f"{symbol} 수량 {qty:.8g}\n"
                f"체결가를 못 찾아 보호 없는 포지션을 남기지 않으려 되팔았습니다.")
        except Exception as exc:                          # noqa: BLE001
            log.error("고아 청산 알림 실패: %s", exc)

    def _tell_naked(self, symbol: str, why: str) -> None:
        """손절을 못 건 포지션은 **보호가 없다.** 조용하면 안 된다."""
        if not callable(self.notify):
            log.critical("%s 손절 미등록 — 알림 경로가 없어 로그만 남긴다",
                         symbol)
            return
        try:
            self.notify(
                f"🚨 <b>손절 미등록</b> — 속도저울 1군\n"
                f"{symbol}\n사유: {why}\n"
                f"이 포지션은 **보호 장치가 없습니다.** 확인이 필요합니다.")
        except Exception as exc:                          # noqa: BLE001
            log.error("손절 미등록 알림 실패: %s", exc)
