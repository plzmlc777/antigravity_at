"""Monthly REAL trading report → Telegram (month-over-month comparison).

Computes calendar-month realized-PnL stats for the REAL Binance Futures account
(acct8) from live_trade_executions (is_paper=false), compares the just-completed
month vs the prior month, appends current total equity, and sends a Telegram
report to the REAL alert chats (reuses lifecycle driver's _telegram_notify).

Deterministic worker — no LLM. Wire via PM2 sas-loop cron '0 9 1 * *' (1st of
month, 18:00 KST). Self-contained: derives all months from the executions table
each run, so there is no baseline file to drift.

A "closed trade" = an execution that booked a non-zero realized_pnl (opens book
0). Direction-agnostic (works for long or short).

Usage:
  python -m scripts.monthly_real_trading_report            # send for last month
  python -m scripts.monthly_real_trading_report --month 2026-06   # specific month
  python -m scripts.monthly_real_trading_report --dry     # compute + print, no send
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.db.session import engine  # noqa: E402

REAL_ACCOUNT_ID = 8


def _month_bounds(y: int, m: int) -> tuple[str, str]:
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start.isoformat(), end.isoformat()


def _prev_month(y: int, m: int) -> tuple[int, int]:
    return (y - 1, 12) if m == 1 else (y, m - 1)


def month_stats(y: int, m: int) -> dict:
    """Closed-trade realized-PnL stats for calendar month (y, m)."""
    start, end = _month_bounds(y, m)
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT realized_pnl, symbol
            FROM live_trade_executions
            WHERE is_paper = false AND status = 'FILLED'
              AND realized_pnl IS NOT NULL AND realized_pnl <> 0
              AND COALESCE(order_filled_at, signal_timestamp) >= :s
              AND COALESCE(order_filled_at, signal_timestamp) <  :e
            ORDER BY realized_pnl DESC
        """), {"s": start, "e": end}).fetchall()
    pnls = [float(r.realized_pnl) for r in rows]
    n = len(pnls)
    total = sum(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_wins = sum(wins)
    top2 = sum(sorted(wins, reverse=True)[:2])
    return {
        "month": f"{y}-{m:02d}",
        "n": n,
        "total": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / n * 100.0) if n else 0.0,
        "avg": (total / n) if n else 0.0,
        "max_win": max(pnls) if pnls else 0.0,
        "max_loss": min(pnls) if pnls else 0.0,
        # share of gross winnings from the top 2 wins (0-100%): high = fragile,
        # profit concentrated in a couple lucky trades.
        "top2_share": (top2 / gross_wins * 100.0) if gross_wins > 0 else 0.0,
        "symbols": sorted({r.symbol for r in rows}),
    }


def current_equity() -> dict | None:
    """acct8 total margin balance + unrealized (best-effort; None on failure)."""
    try:
        import asyncio

        from app.models.account import ExchangeAccount
        from app.models.user import User  # noqa: F401 — resolve mapper
        from scripts.account_keepalive import _build_adapter
        from app.adapters.binance_futures import FAPI_V2
        from app.db.session import SessionLocal

        async def _fetch():
            db = SessionLocal()
            try:
                acc = db.query(ExchangeAccount).filter(
                    ExchangeAccount.id == REAL_ACCOUNT_ID).first()
                adapter = _build_adapter(acc)
                await adapter._ensure_time_sync()
                data = await adapter._signed_get(f"{FAPI_V2}/account")
                return {
                    "wallet": float(data.get("totalWalletBalance", 0)),
                    "equity": float(data.get("totalMarginBalance", 0)),
                    "unrealized": float(data.get("totalUnrealizedProfit", 0)),
                    "open_positions": sum(
                        1 for p in data.get("positions", [])
                        if float(p.get("positionAmt", 0)) != 0),
                }
            finally:
                db.close()

        return asyncio.run(_fetch())
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] equity fetch failed: {exc}", file=sys.stderr)
        return None


def _delta(cur: float, prev: float) -> str:
    d = cur - prev
    sign = "▲" if d > 0 else ("▼" if d < 0 else "—")
    return f"{sign} {d:+,.2f}"


def build_message(this_m: dict, prev_m: dict, eq: dict | None) -> str:
    L = []
    L.append("📊 <b>바이낸스 실거래 월간 리포트</b>")
    L.append(f"<b>{this_m['month']}</b> (전월 {prev_m['month']} 대비)")
    L.append("")
    L.append("💰 <b>이번 달 실현손익</b>")
    L.append(f"  <b>{this_m['total']:+,.2f} USDT</b>  ({_delta(this_m['total'], prev_m['total'])} vs 전월)")
    L.append("")
    L.append("📈 <b>거래 통계</b>")
    L.append(f"  완결 거래: <b>{this_m['n']}</b>회  (전월 {prev_m['n']})")
    L.append(f"  승/패: {this_m['wins']}승 {this_m['losses']}패  (승률 {this_m['win_rate']:.0f}%)")
    L.append(f"  거래당 평균: <b>{this_m['avg']:+,.2f}</b>  (전월 {prev_m['avg']:+,.2f})")
    L.append(f"  최대 승/패: +{this_m['max_win']:,.2f} / {this_m['max_loss']:,.2f}")
    if this_m["wins"] >= 2 and this_m["top2_share"] >= 60:
        L.append(f"  ⚠️ 상위 2승이 전체 이익의 {this_m['top2_share']:.0f}% (집중·취약)")
    if eq:
        L.append("")
        L.append("🏦 <b>실계좌 현황</b>")
        L.append(f"  총자산: <b>${eq['equity']:,.2f}</b>  (미실현 {eq['unrealized']:+,.2f})")
        L.append(f"  오픈 포지션: {eq['open_positions']}개")
    if this_m["symbols"]:
        L.append("")
        L.append(f"  거래 종목: {', '.join(s[:-4] if s.endswith('USDT') else s for s in this_m['symbols'])}")
    L.append("")
    verdict = "🟢 전월 대비 개선" if this_m["total"] > prev_m["total"] else (
        "🔴 전월 대비 악화" if this_m["total"] < prev_m["total"] else "⚪ 전월과 동일")
    L.append(verdict)
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=None, help="YYYY-MM (default: last complete month)")
    ap.add_argument("--dry", action="store_true", help="compute + print, do not send Telegram")
    args = ap.parse_args()

    if args.month:
        y, m = map(int, args.month.split("-"))
    else:
        today = datetime.utcnow().date()
        y, m = _prev_month(today.year, today.month)

    this_m = month_stats(y, m)
    prev_m = month_stats(*_prev_month(y, m))
    eq = current_equity()
    msg = build_message(this_m, prev_m, eq)

    print(msg)
    print("\n---")
    if args.dry:
        print("[DRY] not sending Telegram")
        return 0

    if this_m["n"] == 0 and prev_m["n"] == 0:
        print("[SKIP] no real trades in either month — not sending")
        return 0

    try:
        from scripts.binance.lifecycle_live_signal_driver import _telegram_notify
        _telegram_notify(REAL_ACCOUNT_ID, msg)
        print("[SENT] telegram dispatched")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] telegram send: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
