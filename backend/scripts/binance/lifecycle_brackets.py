"""거래소 브래킷(손절·익절) 주문 — 실거래를 1h 모형에 맞춘다.

⚠ 왜 필요한가 (2026-08-15)
    정본은 **일봉**으로 평가한다(`eval_freq_minutes: 1440`). 그래서 한 봉 안에서
    손절과 익절이 **둘 다 닿으면 순서를 모른다.** 커널은 보수적으로 손절을
    먼저 잡는다:

        app/composer_framework/kernel.py::_forced_exit  (숏 분기)
            if sl_price > 0 and high >= sl_price:   ← 손절 먼저
            if tp_price > 0 and low  <= tp_price:

    1h 포트폴리오 격자가 SL50/TP50 을 1위($1,307)로 뽑은 이유가 바로 그 순서를
    **실제로 보기** 때문이다. 일봉 모형에서 같은 설정은 $411 로 하위권이다.
    즉 파라미터만 옮기고 집행을 그대로 두면 **1h 의 이점이 실현되지 않는다.**

    시간 단위 사이클을 만드는 대신, **거래소가 실시간으로 판정**하게 한다.
    진입 직후 STOP_MARKET / TAKE_PROFIT_MARKET 을 걸어두면 순서는 거래소가
    정한다 — 사이클 주기와 무관해진다.

    부수 효과: 사이클 사이(하루)의 급변에도 손절이 걸린다. 지금은 하루에
    한 번만 본다.

⚠ 설계 원칙
    · `closePosition=true` — 수량을 안 넘긴다. 부분체결·수량 어긋남이 없고,
      포지션이 닫히면 바이낸스가 **나머지 브래킷을 자동 취소**한다(OCO 동작).
    · `workingType=CONTRACT_PRICE` — 마지막 체결가 기준. 백테스트가 쓰는
      봉의 고가/저가와 같은 기준이다(MARK_PRICE 로 하면 백테스트와 어긋난다).
    · **멱등** — 이미 걸린 브래킷이 있으면 다시 걸지 않는다. 드라이버는 매일
      돌고 실패 시 재시도하므로 중복 주문이 쉽게 생긴다.
    · 실패해도 진입을 되돌리지 않는다. 브래킷이 없으면 **종전 동작(일봉 정본
      청산)으로 degrade** 될 뿐이고, 이미 열린 포지션을 강제로 닫는 쪽이 더
      위험하다. 대신 크게 로그를 남긴다.

⚠ 정본과의 관계
    브래킷이 체결되면 거래소는 flat 인데 정본은 아직 short 로 안다. 드라이버의
    기존 정합 로직이 다음 사이클에 이를 잡아 청산으로 기록한다
    (`_real_direct_close` 경로). 그 지연 동안 **재진입은 일어나지 않는다** —
    진입창이 상장 직후로 닫혀 있기 때문이다.
"""
from __future__ import annotations

import logging
from decimal import ROUND_DOWN, ROUND_UP, Decimal

log = logging.getLogger("lifecycle_brackets")

FAPI = "/fapi/v1"


def _round_to_tick(price: float, tick: str, *, up: bool) -> str:
    """틱사이즈에 맞춘다. 안 맞으면 -1111 로 거부된다.

    손절(위)은 **올림**, 익절(아래)은 **내림** — 어느 쪽이든 백테스트가 가정한
    체결가보다 불리한 쪽으로 맞춘다. 유리한 쪽으로 반올림하면 백테스트가
    낙관적이 된다.
    """
    t = Decimal(str(tick))
    if t <= 0:
        return f"{price:.8f}".rstrip("0").rstrip(".")
    q = (Decimal(str(price)) / t).quantize(Decimal("1"),
                                           rounding=ROUND_UP if up else ROUND_DOWN)
    return str((q * t).normalize())


def place_short_brackets(adapter, symbol: str, sl_price: float,
                         tp_price: float | None,
                         *, run_async, dry_run: bool = True) -> dict:
    """숏 포지션에 손절·익절 브래킷을 건다. 반환: {"sl":..., "tp":..., "skipped":...}

    ⚠ 가격은 **정본이 계산한 절대가**(`cycle["sl_price"]` / `["tp_price"]`)를
      그대로 받는다. 퍼센트로 다시 계산하면 정본 장부와 미세하게 어긋나
      "거래소는 청산됐는데 정본은 아직"이 생긴다. 0 이하는 '없음'으로 본다.

    `run_async` 는 드라이버의 `_run_async` (동기 컨텍스트에서 코루틴 실행).
    """
    out: dict = {"sl": None, "tp": None, "skipped": None}

    # ── 멱등 — 이미 걸려 있으면 건너뛴다 ──────────────────────────────
    try:
        existing = run_async(adapter._signed_get(f"{FAPI}/openOrders",
                                                 {"symbol": symbol})) or []
    except Exception as exc:
        log.error("%s 미체결 주문 조회 실패: %s — 브래킷 생략", symbol, exc)
        out["skipped"] = f"openOrders 조회 실패: {exc}"
        return out
    has_tp = tp_price is not None and tp_price > 0
    kinds = {o.get("type") for o in existing}
    if "STOP_MARKET" in kinds and ("TAKE_PROFIT_MARKET" in kinds or not has_tp):
        out["skipped"] = f"이미 존재 ({sorted(kinds)})"
        log.info("%s 브래킷 이미 존재 — 건너뜀 %s", symbol, sorted(kinds))
        return out

    tick = "0"
    try:
        if not getattr(adapter, "_symbol_filters", None):
            run_async(adapter.load_exchange_info())
        tick = (adapter._symbol_filters.get(symbol) or {}).get("tickSize", "0")
    except Exception as exc:
        log.warning("%s tickSize 조회 실패(%s) — 원가격으로 시도", symbol, exc)

    # 숏이므로 손절은 **위**, 익절은 **아래**. 청산 주문 방향은 BUY.
    if not (sl_price and sl_price > 0):
        out["skipped"] = "정본이 손절가를 안 냈다"
        log.warning("%s 손절가 없음 — 브래킷 생략", symbol)
        return out
    legs = [("STOP_MARKET", float(sl_price), True, "sl")]
    if has_tp:
        legs.append(("TAKE_PROFIT_MARKET", float(tp_price), False, "tp"))

    for otype, raw_px, up, key in legs:
        px = _round_to_tick(raw_px, tick, up=up)
        params = {"symbol": symbol, "side": "BUY", "type": otype,
                  "stopPrice": px, "closePosition": "true",
                  "workingType": "CONTRACT_PRICE"}
        if dry_run:
            log.info("[DRY] %s %s stopPrice=%s closePosition", symbol, otype, px)
            out[key] = {"dry_run": True, "stopPrice": px}
            continue
        try:
            res = run_async(adapter._signed_post(f"{FAPI}/order", params))
            out[key] = {"orderId": (res or {}).get("orderId"), "stopPrice": px}
            log.info("[SENT] %s %s stopPrice=%s orderId=%s", symbol, otype, px,
                     (res or {}).get("orderId"))
        except Exception as exc:
            # ⚠ 진입을 되돌리지 않는다 — 브래킷 없으면 종전(일봉 정본 청산)으로
            #   degrade 될 뿐이고, 열린 포지션을 강제로 닫는 쪽이 더 위험하다.
            log.error("[FAIL] %s %s 브래킷 실패: %s — 일봉 정본 청산으로 degrade",
                      symbol, otype, exc)
            out[key] = {"error": str(exc)}
    return out


def cancel_brackets(adapter, symbol: str, *, run_async,
                    dry_run: bool = True) -> int:
    """남은 브래킷을 취소한다. 정본이 먼저 청산한 경우에 쓴다.

    `closePosition` 주문은 포지션이 닫히면 자동 취소되지만, 취소 실패나 경합이
    있을 수 있으므로 명시적으로 한 번 더 지운다. 반환: 취소한 주문 수.
    """
    try:
        orders = run_async(adapter._signed_get(f"{FAPI}/openOrders",
                                               {"symbol": symbol})) or []
    except Exception as exc:
        log.error("%s 미체결 조회 실패: %s", symbol, exc)
        return 0
    n = 0
    for o in orders:
        if o.get("type") not in ("STOP_MARKET", "TAKE_PROFIT_MARKET"):
            continue
        if dry_run:
            log.info("[DRY] %s 취소 대상 orderId=%s %s", symbol,
                     o.get("orderId"), o.get("type"))
            n += 1
            continue
        try:
            run_async(adapter._signed_delete(f"{FAPI}/order",
                                             {"symbol": symbol,
                                              "orderId": o.get("orderId")}))
            n += 1
        except Exception as exc:
            log.warning("%s 주문 %s 취소 실패: %s", symbol, o.get("orderId"), exc)
    return n
