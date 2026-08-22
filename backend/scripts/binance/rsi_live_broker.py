"""RSI 전략의 **실거래 체결 계층**. 페이퍼 시뮬레이터는 건드리지 않는다.

설계 원칙 — **거래소가 진실이다.**
    페이퍼는 봉을 보고 청산을 판정하지만, 실거래에서 익절은 **호가에 얹어 둔
    지정가가 채워지는 사건**이다. 우리가 봉으로 "닿았다"고 판정하는 것과
    실제 체결은 다르다. 그래서 익절 체결은 **거래소에 물어서** 안다.

왜 지정가 익절인가
    이 전략의 엣지가 거기 달려 있다. 백테스트는 익절가 정확 체결·메이커
    2bp·슬리피지 0 을 전제한다. 조건부 주문(트리거 후 시장가)으로 내보내면
    테이커에 슬리피지가 붙어 전제가 깨진다 — 실측 슬리피지 평균 104bp 는
    익절 5% 의 5분의 1 이다.

수명 주기
    진입   시장가 BUY → 체결가 확정 → **즉시** 익절 지정가(reduceOnly) 등록
    익절   거래소가 채운다. 매 사이클 대조해서 알아챈다
    시간만료 익절 지정가 **취소 먼저** → 시장가 청산
    재시작  거래소 포지션·주문을 읽어 상태를 맞춘다

⚠ `reduceOnly` 는 필수다. 없으면 포지션이 닫힌 뒤 남은 지정가가 **반대
   포지션을 새로 연다**. 2026-07-27 고아 포지션 사고와 같은 계열이다.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger("rsi_live")


_LOOP: Optional[asyncio.AbstractEventLoop] = None
_LOOP_LOCK = threading.Lock()


def _loop() -> asyncio.AbstractEventLoop:
    """브로커 수명 동안 **하나만** 쓰는 배경 루프.

    ⚠ 2026-08-22 실계좌에서 드러남 — 호출마다 루프를 만들고 닫으면
      `Event loop is closed` 로 전부 실패한다. 어댑터의 HTTP 클라이언트가
      **전역 공유**라 처음 만든 루프에 묶이는데, 그 루프를 닫으면 클라이언트가
      죽는다. 조회 3건이 조용히 빈 결과를 냈다 — 실거래에서 이러면 포지션이
      없다고 오판해 **중복 진입**한다.
    """
    global _LOOP
    with _LOOP_LOCK:
        if _LOOP is None or _LOOP.is_closed():
            _LOOP = asyncio.new_event_loop()
            threading.Thread(target=_LOOP.run_forever, daemon=True,
                             name="rsi-live-loop").start()
    return _LOOP


def _run(coro, timeout: float = 30.0):
    """동기 사이클에서 async 어댑터를 부른다. 배경 루프에 태운다."""
    return asyncio.run_coroutine_threadsafe(coro, _loop()).result(timeout)


@dataclass
class LiveOrder:
    """우리가 건 익절 지정가 하나."""
    symbol: str
    order_id: str
    price: float
    qty: float


@dataclass
class LiveBroker:
    """계좌 하나에 붙는 실거래 브로커.

    `account_id` 는 `exchange_accounts.id`. 키는 DB 에서 복호화해 읽는다
    (.env 에 두지 않는다 — 저장소 규약).
    """
    account_id: int
    notional_usd: float
    dry_run: bool = False               # True 면 주문 대신 로그만
    _adapter: Any = field(default=None, init=False, repr=False)
    tp_orders: dict = field(default_factory=dict)     # 종목 → LiveOrder

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
        log.info("실거래 브로커 연결 — 계좌 %s(%s) · 슬롯당 $%.0f%s",
                 self.account_id, r[3], self.notional_usd,
                 " · DRY-RUN" if self.dry_run else "")

    # ── 조회 ────────────────────────────────────────────────
    def positions(self) -> dict:
        """거래소의 열린 롱 포지션 {종목: 수량}. **진실의 원본.**"""
        from app.adapters.binance_futures import FAPI_V2
        try:
            rows = _run(self._adapter._signed_get(f"{FAPI_V2}/positionRisk", {}))
        except Exception as e:                        # noqa: BLE001
            log.error("포지션 조회 실패: %s", e)
            return {}
        out = {}
        for p in rows or []:
            q = float(p.get("positionAmt", 0) or 0)
            if q > 0:                                  # 이 전략은 롱만 쓴다
                out[p["symbol"]] = q
        return out

    def open_orders(self) -> dict:
        """미체결 주문 {종목: [LiveOrder]}."""
        try:
            rows = _run(self._adapter.get_outstanding_orders())
        except Exception as e:                        # noqa: BLE001
            log.error("주문 조회 실패: %s", e)
            return {}
        out: dict = {}
        for o in rows or []:
            out.setdefault(o["symbol"], []).append(LiveOrder(
                symbol=o["symbol"], order_id=str(o["order_id"]),
                price=float(o["price"]), qty=float(o["quantity"])))
        return out

    # ── 진입 ────────────────────────────────────────────────
    def open_long(self, symbol: str, ref_price: float) -> Optional[dict]:
        """시장가 진입. 체결가·수량을 **거래소 응답에서** 받는다."""
        if ref_price <= 0:
            return None
        qty = self.notional_usd / ref_price
        if self.dry_run:
            log.info("[DRY] %s 시장가 진입 %.6f (기준 %.8g)", symbol, qty, ref_price)
            return {"price": ref_price, "quantity": qty}
        try:
            r = _run(self._adapter.place_buy_order(symbol, 0.0, qty))
        except Exception as e:                        # noqa: BLE001
            log.error("%s 진입 실패: %s", symbol, e)
            return None
        if r.get("status") != "success":
            log.error("%s 진입 거절: %s", symbol, r.get("message") or r)
            return None
        px = float(r.get("price") or 0)
        q = float(r.get("quantity") or 0)
        if px <= 0 or q <= 0:
            # ⚠ 체결가 0 을 위로 올리면 상위가 이론가로 대체해 회계가 어긋난다.
            log.error("%s 진입은 됐는데 체결가/수량이 0 — px=%s qty=%s", symbol, px, q)
            return None
        log.info("%s 실거래 진입 — %.6f @ %.8g", symbol, q, px)
        return {"price": px, "quantity": q}

    def arm_take_profit(self, symbol: str, qty: float, tp_price: float) -> bool:
        """진입 **직후** 익절 지정가를 호가에 얹는다."""
        if self.dry_run:
            log.info("[DRY] %s 익절 지정가 %.8g × %.6f", symbol, tp_price, qty)
            return True
        try:
            r = _run(self._adapter.place_reduce_only_limit(
                symbol, "SELL", tp_price, qty))
        except Exception as e:                        # noqa: BLE001
            log.error("%s 익절 지정가 실패: %s", symbol, e)
            return False
        if r.get("status") != "success":
            log.error("%s 익절 지정가 거절: %s", symbol, r.get("message") or r)
            return False
        self.tp_orders[symbol] = LiveOrder(symbol, r["order_id"],
                                           float(r["price"]), float(r["quantity"]))
        return True

    # ── 청산 ────────────────────────────────────────────────
    def cancel_take_profit(self, symbol: str) -> None:
        """시간만료 청산 **전에** 반드시 부른다.

        `reduceOnly` 라 포지션이 닫히면 거래소가 자동 취소하지만, 청산이
        실패하면 주문만 남는다. 먼저 걷어내는 편이 안전하다.
        """
        o = self.tp_orders.pop(symbol, None)
        if o is None or self.dry_run:
            return
        try:
            r = _run(self._adapter.cancel_order(o.order_id, symbol))
            if r.get("status") != "success":
                log.warning("%s 익절 지정가 취소 실패: %s", symbol,
                            r.get("message") or r)
        except Exception as e:                        # noqa: BLE001
            log.warning("%s 익절 지정가 취소 예외: %s", symbol, e)

    def close_long(self, symbol: str) -> Optional[float]:
        """시장가 전량 청산. 체결가를 돌려준다."""
        self.cancel_take_profit(symbol)
        if self.dry_run:
            log.info("[DRY] %s 시장가 청산", symbol)
            return None
        try:
            r = _run(self._adapter.close_position(symbol))
        except Exception as e:                        # noqa: BLE001
            log.error("%s 청산 실패: %s", symbol, e)
            return None
        if r.get("status") != "success":
            log.error("%s 청산 거절: %s", symbol, r.get("message") or r)
            return None
        px = float(r.get("price") or 0)
        log.info("%s 실거래 청산 — @ %.8g", symbol, px)
        return px or None

    # ── 대조 ────────────────────────────────────────────────
    def detect_tp_fills(self, tracked: set) -> dict:
        """익절 지정가가 채워졌는가 — **거래소에 묻는다.**

        우리가 들고 있다고 아는 종목 중 거래소에 포지션이 없으면 채워진 것이다.
        체결가는 우리가 건 지정가 값을 쓴다(지정가는 그 값에만 채워진다).
        """
        pos = self.positions()
        filled = {}
        for sym in list(tracked):
            if sym in pos:
                continue
            o = self.tp_orders.pop(sym, None)
            if o is not None:
                filled[sym] = o.price
                log.info("%s 익절 체결 확인 — @ %.8g (거래소 대조)", sym, o.price)
            else:
                filled[sym] = 0.0        # 가격 미상 — 상위가 경고로 드러낸다
                log.warning("%s 포지션이 사라졌는데 우리 익절 주문이 없다 "
                            "— 수동 청산? 강제청산?", sym)
        return filled

    def reconcile(self) -> dict:
        """재시작 직후 거래소와 맞춘다. {종목: 수량} 을 돌려준다."""
        pos = self.positions()
        oo = self.open_orders()
        self.tp_orders = {s: v[0] for s, v in oo.items() if v}
        log.info("거래소 대조 — 포지션 %d종목 · 미체결 주문 %d종목",
                 len(pos), len(self.tp_orders))
        # 포지션 없는데 남은 주문은 고아다 — 걷어낸다
        for sym in list(self.tp_orders):
            if sym not in pos:
                log.warning("%s 고아 주문 발견 — 취소한다", sym)
                self.cancel_take_profit(sym)
        return pos
