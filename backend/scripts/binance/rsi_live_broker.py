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
import time
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
    # ⚠ 거래소 레버리지 (2026-08-23 대표님 지시로 명시 설정)
    #
    #   **노출 배수가 아니다.** 노출은 `notional_usd` 가 정한다 —
    #   수량 = 명목/가격 이라 레버리지와 무관하다. 백테스트의 자본 모형도
    #   "슬롯당 명목 = 자본/슬롯"(총명목 = 자본)이라 노출은 언제나 1배다.
    #
    #   이 값이 정하는 것은 **증거금 점유율**이다. 명목 $752 를
    #   1x 로 잡으면 마진 $752(지갑의 99.9%), 2x 면 $376 이다.
    #
    #   기본 1 인 이유 — 모르는 값으로 도는 것보다 **마진 벽에 부딪혀
    #   시끄럽게 실패**하는 편이 낫다. 신상저격수에서 RSI 로 1군을 바꿀 때
    #   레버리지를 재설정하지 않아 계좌에 남아 있던 2x 로 조용히 돌았다.
    leverage: int = 1
    # 주문마다 배수를 달리하는 전략을 위한 훅. callable(symbol) -> int.
    # None 이면 위 `leverage` 를 쓴다.
    leverage_fn: Any = None
    _adapter: Any = field(default=None, init=False, repr=False)
    _lev_done: dict = field(default_factory=dict)     # 종목 → 적용된 배수
    tp_orders: dict = field(default_factory=dict)     # 종목 → LiveOrder
    # ⚠ 손절은 **거래소 조건부 주문**이다(2026-08-24 30분봉 사양).
    #   우리 루프가 봉 마감에 판정하면 최대 30분 늦는다 — 그 사이 −0.5% 는
    #   훨씬 지나간다. 거래소가 밀리초에 트리거하게 맡긴다.
    sl_orders: dict = field(default_factory=dict)     # 종목 → LiveOrder
    entry_ms: dict = field(default_factory=dict)      # 종목 → 진입 시각(ms)

    # ── 레버리지 ────────────────────────────────────────────
    def want_leverage(self, symbol: str) -> int:
        """이 주문에 쓸 배수. 훅이 있으면 훅이 정한다."""
        if self.leverage_fn is not None:
            try:
                return max(1, int(self.leverage_fn(symbol)))
            except Exception as exc:                          # noqa: BLE001
                log.error("%s 동적 레버리지 실패 — 기본 %dx 사용: %s",
                          symbol, self.leverage, exc)
        return max(1, int(self.leverage))

    def ensure_leverage(self, symbol: str) -> Optional[int]:
        """주문 **전에** 배수를 맞춘다. 실패하면 None — 진입하지 않는다.

        ⚠ 실패했는데 그냥 진입하면 **모르는 배수로 실자금이 돈다.** 그게
          정확히 2026-08-23 에 드러난 문제다(계좌에 남아 있던 2x).
          한 종목에 한 번만 부른다 — 배수는 계좌·종목 속성이라 유지된다."""
        want = self.want_leverage(symbol)
        if self._lev_done.get(symbol) == want:
            return want
        if self.dry_run:
            self._lev_done[symbol] = want
            return want
        try:
            r = _run(self._adapter.set_leverage(symbol, want))
        except Exception as exc:                              # noqa: BLE001
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
        log.info("실거래 브로커 연결 — 계좌 %s(%s) · 슬롯당 $%.1f · 레버리지 %s%s",
                 self.account_id, r[3], self.notional_usd,
                 "동적(훅)" if self.leverage_fn else f"{self.leverage}x",
                 " · DRY-RUN" if self.dry_run else "")

    # ── 조회 ────────────────────────────────────────────────
    def wallet_balance(self) -> Optional[float]:
        """지갑 잔고(USDT, 실현 기준). 복리 사이징이 이 값을 쓴다.

        ⚠ **평가액이 아니라 지갑**이다. 미실현을 자본에 넣으면 아직 확정도
          안 된 이익 위에 다음 포지션을 키우게 된다 — 백테스트 자본곡선은
          청산된 거래만 쌓는다.

        ⚠ 실패하면 None. 호출부는 **설정값으로 후퇴**해야 한다."""
        from app.adapters.binance_futures import FAPI_V2
        try:
            d = _run(self._adapter._signed_get(f"{FAPI_V2}/account", {}))
            v = float((d or {}).get("totalWalletBalance") or 0.0)
            return v if v > 0 else None
        except Exception as e:                        # noqa: BLE001
            log.error("지갑 조회 실패: %s", e)
            return None

    def positions(self, strict: bool = False) -> dict | None:
        """거래소의 열린 롱 포지션 {종목: 수량}. **진실의 원본.**

        ⚠ `strict=True` 면 조회 실패에 **None** 을 돌려준다. 빈 딕셔너리와
          구분해야 한다 — 2026-08-27 03:33, 시각 동기가 어긋나 `-1021` 로
          조회가 실패했는데 호출부가 그걸 "포지션이 사라졌다"로 읽었다.
          장부를 닫고 보호 주문까지 걷었는데 거래소엔 포지션이 그대로 남아
          **다섯 시간 동안 익절도 손절도 없는 고아**가 됐다.
          모르는 것과 없는 것은 다르다.
        """
        from app.adapters.binance_futures import FAPI_V2
        try:
            rows = _run(self._adapter._signed_get(f"{FAPI_V2}/positionRisk", {}))
        except Exception as e:                        # noqa: BLE001
            # ⚠ 시각 동기는 30분에 한 번이라 그 사이 드리프트로 -1021
            #   (Timestamp outside recvWindow) 이 난다. 그게 2026-08-27 고아
            #   포지션의 첫 단추였다. **즉시 재동기하고 한 번만 다시 묻는다.**
            log.warning("포지션 조회 실패 — 시각 재동기 후 재시도: %s", e)
            try:
                _run(self._adapter.sync_server_time())
                rows = _run(self._adapter._signed_get(f"{FAPI_V2}/positionRisk", {}))
                log.info("포지션 조회 재시도 성공")
            except Exception as e2:                   # noqa: BLE001
                log.error("포지션 조회 실패(재시도까지): %s", e2)
                return None if strict else {}
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
        lev = self.ensure_leverage(symbol)
        if lev is None:
            # 배수를 못 맞췄다 — 모르는 마진으로 실자금을 넣지 않는다.
            log.error("%s 레버리지 미설정 — 진입하지 않는다", symbol)
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
        log.info("%s 실거래 진입 — %.6f @ %.8g (%dx)", symbol, q, px, lev)
        # 청산 체결을 되찾을 때 이 시각 이후만 본다 — 지난 거래가 섞이면 안 된다.
        self.entry_ms[symbol] = int(time.time() * 1000) - 5_000
        return {"price": px, "quantity": q, "leverage": lev}

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

    def arm_stop_loss(self, symbol: str, trigger: float,
                      limit_price: float = 0.0, qty: float = 0.0) -> bool:
        """진입 **직후** 손절 스톱리밋을 거래소에 건다.

        ⚠ `limit_price` 0 이면 STOP_MARKET 이다 — 체결은 보장되나 가격이
          보장되지 않는다. 30분봉 사양의 격자에서 시장가 손절은 연 **−100%**,
          지정가(간격 0)는 **+430%** 였다. 기본은 **발동가와 같은 지정가**다.

        ⚠ **지정가 손절에는 `closePosition` 을 쓸 수 없다.** 공식 문서가
          "Close-All, used with STOP_MARKET or TAKE_PROFIT_MARKET" 라고
          못박고 있고, `STOP` 에 얹으면 거래소가 **-4136 Target strategy
          invalid for orderType STOP, closePosition true** 로 막는다
          (2026-08-26 TRXUSDT 실거래에서 실제로 맞았다 — 진입했다가 손절을
          못 걸어 되돌렸다). 그래서 **체결 수량 + reduceOnly** 로 건다.
          `qty` 는 진입 응답의 체결 수량이어야 한다 — 익절과 같은 값이다.

        ⚠ `close_position=True`(스탑마켓 경로) 는 포지션이 있어야만 등록된다
          (GTE_GTC). 진입 직후에만 걸 수 있고 미리 걸어둘 수 없다.

        ⚠ `price_protect` 는 **끈다**. 켜면 표시가·계약가 괴리가 클 때 체결을
          막는데, 그 순간이 정확히 손절이 필요한 순간이다."""
        if trigger <= 0:
            return False
        lim = limit_price if limit_price > 0 else trigger
        if self.dry_run:
            log.info("[DRY] %s 손절 스톱리밋 발동 %.8g · 지정 %.8g",
                     symbol, trigger, lim)
            return True
        if limit_price > 0 and qty <= 0:
            # 수량 없이 지정가 손절을 걸 길이 없다. 조용히 시장가로 바꾸면
            # 규약이 달라진다(격자에서 시장가 손절은 연 -100%) — 소리내어 죽는다.
            log.error("%s 지정가 손절에 수량이 없다 — 진입을 되돌려야 한다", symbol)
            return False
        try:
            r = _run(self._adapter.place_algo_stop(
                symbol, side="SELL", trigger_price=trigger, limit_price=lim,
                take_profit=False,
                # 지정가(STOP) 는 closePosition 금지 → 수량+reduceOnly.
                # 시장가(STOP_MARKET) 만 closePosition 이 허용된다.
                close_position=(limit_price <= 0), quantity=qty,
                working_type="CONTRACT_PRICE", price_protect=False))
        except Exception as e:                        # noqa: BLE001
            log.error("%s 손절 등록 실패: %s", symbol, e)
            return False
        if r.get("status") != "success":
            log.error("%s 손절 거절: %s", symbol, r.get("message") or r)
            return False
        # ⚠ 어댑터는 조건부 주문 번호를 `algo_id` 로 돌려준다. `order_id` 를
        #   읽으면 **빈 문자열**이 저장되고, 그러면 `cancel_stop_loss` 가
        #   `not o.order_id` 에서 조용히 되돌아가 **손절이 영원히 안 걷힌다**
        #   (2026-08-26 실계좌 시험에서 발각 — 취소했는데 그대로 남아 있었다).
        algo_id = str(r.get("algo_id") or r.get("order_id") or "")
        if not algo_id:
            log.warning("%s 손절은 등록됐는데 주문번호를 못 받았다 — 취소는 "
                        "종목 전체 조건부 정리로 후퇴한다", symbol)
        self.sl_orders[symbol] = LiveOrder(symbol, algo_id, float(lim), 0.0)
        log.info("%s 손절 스톱리밋 — 발동 %.8g · 지정 %.8g (id %s)",
                 symbol, trigger, lim, algo_id or "?")
        return True

    def cancel_stop_loss(self, symbol: str) -> None:
        """손절 조건부 주문을 걷는다.

        ⚠ 청산할 때 **익절과 손절을 둘 다** 걷어야 한다. 하나만 걷으면
          남은 쪽이 다음 진입을 엉뚱하게 청산한다."""
        o = self.sl_orders.pop(symbol, None)
        if self.dry_run:
            return
        try:
            if o is not None and o.order_id:
                r = _run(self._adapter.cancel_algo_order(symbol, o.order_id))
            else:
                # 번호를 모른다(재기동으로 장부가 비었거나 등록 응답이
                # 번호를 안 줬다). 남겨두면 고아가 되므로 **종목 전체**
                # 조건부 주문을 걷는다. 이 세션은 종목당 손절 하나만 건다.
                r = _run(self._adapter.cancel_all_algo_orders(symbol))
            if (r or {}).get("status") != "success":
                log.warning("%s 손절 취소 실패: %s", symbol,
                            (r or {}).get("message") or r)
        except Exception as e:                        # noqa: BLE001
            log.warning("%s 손절 취소 예외: %s", symbol, e)

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
        self.cancel_stop_loss(symbol)          # 둘 다 걷는다 — 하나만 걷으면
                                               # 다음 진입이 엉뚱하게 잘린다
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
    def detect_exit_fills(self, tracked: set) -> dict:
        """거래소가 채운 청산을 알아낸다 — {종목: (사유, 체결가)}.

        우리가 들고 있다고 아는 종목 중 거래소에 포지션이 없으면 채워진 것이다.

        ⚠ 2026-08-24 30분봉 사양부터 **출구가 둘**이다 — 익절 지정가와 손절
          스톱리밋. 어느 쪽이 채워졌는지 반드시 가려야 한다. 뭉뚱그려 익절로
          세면 −0.5% 손절이 장부에 **+8% 이익**으로 들어간다. 그 한 줄이
          모든 판정을 뒤집는다.

          가리는 법 — 아직 **살아 있는** 주문이 있는 쪽이 안 채워진 쪽이다.
          포지션이 닫히면 반대쪽은 거래소가 자동 취소하거나 우리가 걷는다.
        """
        pos = self.positions(strict=True)
        if pos is None:
            # 거래소를 못 읽었다. 이 상태에서 "없으니 닫혔다" 로 가면
            # 살아 있는 포지션을 장부에서 지우고 보호 주문까지 걷는다.
            # **판정을 다음 사이클로 미룬다** — 늦는 것이 틀리는 것보다 낫다.
            log.error("포지션 조회 실패 — 이번 사이클 청산 판정을 건너뛴다 "
                      "(장부를 함부로 닫지 않는다)")
            return {}
        live_lim = self.open_orders()               # 남아 있는 지정가(익절)
        try:
            live_algo = self.open_algo_orders()     # 남아 있는 조건부(손절)
        except Exception as exc:                    # noqa: BLE001
            log.warning("조건부 주문 조회 실패 — 사유 판정이 흐려진다: %s", exc)
            live_algo = {}
        filled = {}
        for sym in list(tracked):
            if sym in pos:
                continue
            tp = self.tp_orders.pop(sym, None)
            sl = self.sl_orders.pop(sym, None)
            tp_alive, sl_alive = sym in live_lim, sym in live_algo
            if tp is not None and not tp_alive and sl_alive:
                filled[sym] = ("tp", tp.price)      # 익절만 사라졌다
            elif sl is not None and not sl_alive and tp_alive:
                filled[sym] = ("sl", sl.price)      # 손절만 사라졌다
            elif tp is not None and sl is None:
                filled[sym] = ("tp", tp.price)      # 손절을 안 건 세션
            elif sl is not None and tp is None:
                filled[sym] = ("sl", sl.price)
            elif tp_alive and sl_alive:
                # ⚠ 둘 다 **살아 있다** = 아무것도 안 채워졌다. 그런데 포지션이
                #   없다? 그건 청산이 아니라 **조회가 이상한 것**이다.
                #   2026-08-27 실측으로 이 조합이 정확히 그 상황이었다.
                #   장부를 되돌려 놓고 다음 사이클에 다시 본다.
                self.tp_orders[sym] = tp or self.tp_orders.get(sym)
                self.sl_orders[sym] = sl or self.sl_orders.get(sym)
                log.error("%s 포지션이 안 보이는데 익절·손절이 **둘 다 살아 "
                          "있다** — 채워진 것이 없다는 뜻이다. 청산으로 세지 "
                          "않고 장부를 유지한다", sym)
                continue
            else:
                # 둘 다 사라졌다 — 어느 주문인지는 못 가린다. 그래도
                # **체결가는 사실로 알 수 있다.** 거래소에 물어본다.
                px_x, qty_x = self.closing_fill(sym)
                filled[sym] = ("unknown", px_x)
                if px_x > 0:
                    log.warning("%s 포지션이 사라졌다 — 어느 주문인지는 못 "
                                "가리지만 체결가는 거래소에서 되찾았다: "
                                "%.8g × %.6g (익절잔존=%s 손절잔존=%s)",
                                sym, px_x, qty_x, tp_alive, sl_alive)
                else:
                    log.error("%s 포지션이 사라졌는데 체결 내역도 못 읽었다 "
                              "(익절잔존=%s 손절잔존=%s) — 손익이 추정치가 "
                              "된다", sym, tp_alive, sl_alive)
            if filled[sym][0] != "unknown":
                # 지정가는 보통 주문가 그대로 채워지지만, **확인 없이 믿지
                # 않는다.** 체결 내역이 읽히면 그쪽이 사실이다.
                px_x, _ = self.closing_fill(sym)
                if px_x > 0 and abs(px_x - filled[sym][1]) > 1e-12:
                    log.info("%s 체결가 정정 — 주문가 %.8g → 실체결 %.8g",
                             sym, filled[sym][1], px_x)
                    filled[sym] = (filled[sym][0], px_x)
                log.info("%s %s 체결 확인 — @ %.8g (거래소 대조)",
                         sym, filled[sym][0], filled[sym][1])
            # 반대쪽이 남아 있으면 걷는다 — 안 걷으면 다음 진입이 잘린다
            if tp_alive and filled[sym][0] != "tp":
                self.tp_orders[sym] = tp or self.tp_orders.get(sym)
                self.cancel_take_profit(sym)
            if sl_alive and filled[sym][0] != "sl":
                self.sl_orders[sym] = sl or self.sl_orders.get(sym)
                self.cancel_stop_loss(sym)
        return filled

    def closing_fill(self, symbol: str) -> tuple[float, float]:
        """이 종목의 **청산 체결가**를 거래소 체결 내역에서 되찾는다.

        반환 (가중평균 체결가, 수량). 못 찾으면 (0.0, 0.0).

        ⚠ 왜 필요한가 — 2026-08-29 MUSDT. 손절이 지정가 그대로(0.9970 ·
          0.9804) 채워졌는데, 익절·손절이 **둘 다 사라져** 어느 쪽인지 못
          가렸고 상위가 `fill_px=0` 을 받아 **30분 뒤 현재가**를 체결가로
          적었다. 손실이 -0.50% → -1.94% 로 3배 부풀었다.
          가릴 수 없으면 추측할 게 아니라 **거래소에 물어보면 된다.**
        """
        from app.adapters.binance_futures import FAPI
        since = int(self.entry_ms.get(symbol, 0))
        try:
            rows = _run(self._adapter._signed_get(
                f"{FAPI}/userTrades",
                {"symbol": symbol, "limit": 200,
                 **({"startTime": since} if since else {})}))
        except Exception as exc:                      # noqa: BLE001
            log.warning("%s 체결 내역 조회 실패 — 체결가를 못 되찾는다: %s",
                        symbol, exc)
            return 0.0, 0.0
        # 꼬리에서부터 **연속된 SELL** 만 모은다 = 이번 청산의 체결들.
        qty = notional = 0.0
        for t in reversed(rows or []):
            if str(t.get("side")) != "SELL":
                break
            q = float(t.get("qty", 0) or 0)
            qty += q
            notional += q * float(t.get("price", 0) or 0)
        if qty <= 0:
            return 0.0, 0.0
        return notional / qty, qty

    def open_algo_orders(self) -> dict:
        """살아 있는 조건부 주문 {종목: [algoId]}."""
        rows = _run(self._adapter.get_open_algo_orders())
        out: dict = {}
        for o in rows or []:
            out.setdefault(o.get("symbol"), []).append(str(o.get("algoId")))
        return out

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


# ══════════════════════════════════════════════════════════════════════
#  세션 등록 — 감시·비상정지 체계 안으로 들어간다
# ══════════════════════════════════════════════════════════════════════
@dataclass
class SessionRegistry:
    """실거래 세션을 `live_bot_sessions` 에 등록하고 매 사이클 갱신한다.

    ⚠ 왜 필요한가 (2026-08-22) — RSI 실거래는 독립 PM2 프로세스라 DB 조회로는
      "실거래 세션 0건" 으로 보였다. 대시보드·`ops-monitor`·**DB 비상정지**가
      전부 이 세션을 못 봤다. 실거래인데 감시 체계 밖에 있는 셈이다.

    비상정지 규약 — `orders_enabled=false` 또는 `status != 'RUNNING'`
        **신규 진입만 막는다. 청산은 계속한다.**
        진입만 막고 청산도 막으면 포지션이 갇힌다 — 그게 더 위험하다.
    """
    session_id: str
    account_id: int
    symbol_label: str
    strategy_name: str
    interval: str
    config: dict
    initial_capital: float

    def _engine(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from app.db.session import engine
        return engine

    def register(self) -> None:
        import json
        from sqlalchemy import text
        with self._engine().begin() as c:
            row = c.execute(text("select id from live_bot_sessions where id=:i"),
                            {"i": self.session_id}).fetchone()
            if row:
                c.execute(text("""update live_bot_sessions
                    set status='RUNNING', is_active=true, stopped_at=null,
                        is_paper=false, account_id=:a, strategy_config=:cfg,
                        initial_capital=:cap
                    where id=:i"""),
                          {"i": self.session_id, "a": self.account_id,
                           "cfg": json.dumps(self.config, ensure_ascii=False),
                           "cap": self.initial_capital})
                log.info("세션 등록 갱신 — %s", self.session_id)
                return
            c.execute(text("""insert into live_bot_sessions
                (id, symbol, strategy_name, strategy_config, interval, status,
                 started_at, initial_capital, current_capital, orders_enabled,
                 is_paper, is_active, account_id)
                values (:i, :sym, :nm, :cfg, :iv, 'RUNNING', now(), :cap, :cap,
                        true, false, true, :a)"""),
                      {"i": self.session_id, "sym": self.symbol_label,
                       "nm": self.strategy_name,
                       "cfg": json.dumps(self.config, ensure_ascii=False),
                       "iv": self.interval, "cap": self.initial_capital,
                       "a": self.account_id})
            log.info("세션 신규 등록 — %s (계좌 %s · 실거래)",
                     self.session_id, self.account_id)

    def entries_allowed(self) -> bool:
        """비상정지 확인. 조회 실패 시 **막는 쪽**으로 판단한다."""
        from sqlalchemy import text
        try:
            with self._engine().connect() as c:
                r = c.execute(text("select status, orders_enabled, is_active "
                                   "from live_bot_sessions where id=:i"),
                              {"i": self.session_id}).fetchone()
        except Exception as e:                        # noqa: BLE001
            log.error("비상정지 상태 조회 실패 — 진입을 막는다: %s", e)
            return False
        if not r:
            log.error("세션 %s 가 DB 에 없다 — 진입을 막는다", self.session_id)
            return False
        ok = (str(r[0]) == "RUNNING") and bool(r[1]) and bool(r[2])
        if not ok:
            log.warning("비상정지 — status=%s orders_enabled=%s is_active=%s "
                        "(청산은 계속한다)", r[0], r[1], r[2])
        return ok

    def heartbeat(self, capital: float, n_pos: int) -> None:
        from sqlalchemy import text
        try:
            with self._engine().begin() as c:
                c.execute(text("update live_bot_sessions set current_capital=:c "
                               "where id=:i"),
                          {"c": capital, "i": self.session_id})
        except Exception as e:                        # noqa: BLE001
            log.warning("세션 갱신 실패: %s", e)

    def mark_stopped(self) -> None:
        from sqlalchemy import text
        try:
            with self._engine().begin() as c:
                c.execute(text("update live_bot_sessions set status='STOPPED', "
                               "stopped_at=now() where id=:i"),
                          {"i": self.session_id})
            log.info("세션 종료 표시 — %s", self.session_id)
        except Exception as e:                        # noqa: BLE001
            log.warning("세션 종료 표시 실패: %s", e)
