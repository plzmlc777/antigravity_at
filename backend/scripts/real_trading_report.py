"""REAL trading report → Telegram (weekly or monthly, period-over-period).

Computes realized-PnL stats for the REAL Binance Futures account (acct8) from
live_trade_executions (is_paper=false) over a period (last complete calendar
month, or the last 7 days), compares to the immediately preceding period,
appends current total equity, and telegrams the REAL alert chats (reuses
lifecycle driver's _telegram_notify).

Deterministic worker — no LLM. Self-contained: derives all stats from the
executions table each run, so there is no baseline file to drift.

A "closed trade" = an execution that booked a non-zero realized_pnl (opens book
0). Direction-agnostic (works for long or short).

Wire via PM2 sas-loop crons:
  monthly:  '0 22 1 * *'  (1st 22:00 UTC = 2nd 07:00 KST)  --period month
  weekly:   '0 22 * * 0'  (Sun 22:00 UTC = Mon 07:00 KST)  --period week

Usage:
  python -m scripts.real_trading_report --period month     # last complete month
  python -m scripts.real_trading_report --period week      # last 7 days
  python -m scripts.real_trading_report --period week --dry # compute+print only
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.db.session import engine  # noqa: E402

REAL_ACCOUNT_ID = 8
# 실거래(신상저격수) 개시일 — 누적 손익 기준일.
BASELINE_DATE = date(2026, 6, 1)


def recent_windows() -> tuple[list[dict], list[dict], dict]:
    """최근 3주 / 최근 3개월 / BASELINE_DATE 이후 누적."""
    today = datetime.utcnow().date()
    # 최근 주는 오늘 체결분까지 포함(exclusive end = 내일). 창이 7일씩 슬라이드하며
    # 겹치지 않는다: 이번 [today-6, today+1) / 다음주 [today+1, today+8).
    end0 = today + timedelta(days=1)
    weeks = []
    for i in range(3):
        e = end0 - timedelta(days=7 * i)
        s = e - timedelta(days=7)
        le = e - timedelta(days=1)
        # 월 경계를 넘는 주는 끝 날짜에도 월을 표기해야 모호하지 않다(06/29~07/05).
        end_lbl = le.strftime("%d") if le.month == s.month else le.strftime("%m/%d")
        weeks.append(period_stats(s, e, f"{s.strftime('%m/%d')}~{end_lbl}"))
    months = []
    y, m = today.year, today.month
    for _ in range(3):
        ms, me = _month_bounds(y, m)
        months.append(period_stats(ms, me, f"{y}-{m:02d}"))
        y, m = _prev_month(y, m)
    # 누적은 오늘 체결분까지 포함해야 하므로 exclusive end를 내일로.
    cum = period_stats(BASELINE_DATE, today + timedelta(days=1), "누적")
    return weeks, months, cum


def _month_bounds(y: int, m: int) -> tuple[date, date]:
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start, end


def _prev_month(y: int, m: int) -> tuple[int, int]:
    return (y - 1, 12) if m == 1 else (y, m - 1)


def period_stats(start: date, end: date, label: str) -> dict:
    """Closed-trade realized-PnL stats for [start, end) (dates)."""
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT realized_pnl, symbol
            FROM live_trade_executions
            WHERE is_paper = false AND status = 'FILLED'
              AND realized_pnl IS NOT NULL AND realized_pnl <> 0
              AND COALESCE(order_filled_at, signal_timestamp) >= :s
              AND COALESCE(order_filled_at, signal_timestamp) <  :e
            ORDER BY realized_pnl DESC
        """), {"s": start.isoformat(), "e": end.isoformat()}).fetchall()
    pnls = [float(r.realized_pnl) for r in rows]
    n = len(pnls)
    total = sum(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_wins = sum(wins)
    top2 = sum(sorted(wins, reverse=True)[:2])
    return {
        "label": label,
        "n": n,
        "total": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / n * 100.0) if n else 0.0,
        "avg": (total / n) if n else 0.0,
        "max_win": max(pnls) if pnls else 0.0,
        "max_loss": min(pnls) if pnls else 0.0,
        # share of gross winnings from the top 2 wins (0-100%): high = fragile.
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


# ── 고정폭 표 (Telegram <pre>) ────────────────────────────────────────────
# 한글은 monospace에서도 2칸을 차지하므로 East-Asian width로 패딩해야 열이 맞는다.

def _dwidth(s: str) -> int:
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def _pad(s: str, width: int, right: bool = False) -> str:
    gap = max(0, width - _dwidth(s))
    return (" " * gap + s) if right else (s + " " * gap)


def build_table(weeks: list[dict], months: list[dict], cum: dict,
                unrealized: float | None = None) -> list[str]:
    """주간 3 / 월간 3 / 누적을 한 표로. 열 4개(모바일 폭 고려).

    진행 중인 구간(최근 주·이번 달·누적)은 `실현(미실현)`으로 표시한다 —
    미실현은 현재 오픈 포지션의 평가손익이라 종료된 과거 구간에는 없다.
    """
    cols = [("기간", 11, False), ("손익", 17, True), ("거래", 4, True), ("승률", 4, True)]

    def row(label: str, st: dict, live: bool = False) -> str:
        wr = f"{st['win_rate']:.0f}%" if st["n"] else "-"
        pnl = f"{st['total']:+,.2f}"
        if live and unrealized is not None:
            pnl += f"({unrealized:+,.2f})"
        cells = [label, pnl, str(st["n"]), wr]
        return " ".join(_pad(c, w, r) for c, (_, w, r) in zip(cells, cols))

    head = " ".join(_pad(n, w, r) for n, w, r in cols)
    sep = "─" * 39
    L = ["<pre>", head, sep]
    for i, st in enumerate(weeks):
        L.append(row(st["label"], st, live=(i == 0)))
    L.append(sep)
    for i, st in enumerate(months):
        L.append(row(st["label"], st, live=(i == 0)))
    L.append(sep)
    L.append(row("누적", cum, live=True))
    L.append("</pre>")
    if unrealized is not None:
        L.append("  <i>괄호 = 현재 오픈 포지션 미실현손익</i>")
    return L


def build_message(kind_ko: str, cmp_ko: str, this_p: dict, prev_p: dict,
                  eq: dict | None, table: list[str] | None = None) -> str:
    L = []
    L.append(f"📊 <b>바이낸스 실거래 {kind_ko} 리포트</b> — 신상저격수(신규상장 Day-1 숏) 1군")
    L.append(f"<b>{this_p['label']}</b> ({cmp_ko} {prev_p['label']} 대비)")
    L.append("")
    if table:
        L.append(f"🗂 <b>기간별 실현손익</b> (누적 기준일 {BASELINE_DATE.isoformat()})")
        L += table
        L.append("")
    L.append(f"💰 <b>이번 {kind_ko[0]} 실현손익</b>")
    L.append(f"  <b>{this_p['total']:+,.2f} USDT</b>  ({_delta(this_p['total'], prev_p['total'])} vs {cmp_ko})")
    L.append("")
    L.append("📈 <b>거래 통계</b>")
    L.append(f"  완결 거래: <b>{this_p['n']}</b>회  ({cmp_ko} {prev_p['n']})")
    L.append(f"  승/패: {this_p['wins']}승 {this_p['losses']}패  (승률 {this_p['win_rate']:.0f}%)")
    L.append(f"  거래당 평균: <b>{this_p['avg']:+,.2f}</b>  ({cmp_ko} {prev_p['avg']:+,.2f})")
    L.append(f"  최대 승/패: +{this_p['max_win']:,.2f} / {this_p['max_loss']:,.2f}")
    if this_p["wins"] >= 2 and this_p["top2_share"] >= 60:
        L.append(f"  ⚠️ 상위 2승이 전체 이익의 {this_p['top2_share']:.0f}% (집중·취약)")
    if eq:
        L.append("")
        L.append("🏦 <b>실계좌 현황</b>")
        L.append(f"  총자산: <b>${eq['equity']:,.2f}</b>  (미실현 {eq['unrealized']:+,.2f})")
        L.append(f"  오픈 포지션: {eq['open_positions']}개")
    if this_p["symbols"]:
        L.append("")
        L.append(f"  거래 종목: {', '.join(s[:-4] if s.endswith('USDT') else s for s in this_p['symbols'])}")
    L.append("")
    if this_p["total"] > prev_p["total"]:
        L.append(f"🟢 {cmp_ko} 대비 개선")
    elif this_p["total"] < prev_p["total"]:
        L.append(f"🔴 {cmp_ko} 대비 악화")
    else:
        L.append(f"⚪ {cmp_ko}과 동일")
    return "\n".join(L)


def _windows(period: str, month: str | None):
    """Return (kind_ko, cmp_ko, this_stats, prev_stats)."""
    if period == "month":
        if month:
            y, m = map(int, month.split("-"))
        else:
            today = datetime.utcnow().date()
            y, m = _prev_month(today.year, today.month)
        ts, te = _month_bounds(y, m)
        py, pm = _prev_month(y, m)
        ps, pe = _month_bounds(py, pm)
        this_p = period_stats(ts, te, f"{y}-{m:02d}")
        prev_p = period_stats(ps, pe, f"{py}-{pm:02d}")
        return "월간", "전월", this_p, prev_p
    # week: last 7 days ending at run date (exclusive), vs the 7 days before
    # 오늘 체결분까지 포함(exclusive end = 내일). 창이 7일씩 슬라이드하며 안 겹침.
    end = datetime.utcnow().date() + timedelta(days=1)
    this_s = end - timedelta(days=7)
    prev_s = end - timedelta(days=14)
    this_p = period_stats(this_s, end, f"{this_s.isoformat()}~{(end - timedelta(days=1)).isoformat()}")
    prev_p = period_stats(prev_s, this_s, f"{prev_s.isoformat()}~{(this_s - timedelta(days=1)).isoformat()}")
    return "주간", "전주", this_p, prev_p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", choices=["week", "month"], default="month")
    ap.add_argument("--month", default=None, help="YYYY-MM (month period only; default last complete)")
    ap.add_argument("--dry", action="store_true", help="compute + print, do not send Telegram")
    args = ap.parse_args()

    kind_ko, cmp_ko, this_p, prev_p = _windows(args.period, args.month)
    eq = current_equity()
    weeks, months, cum = recent_windows()
    msg = build_message(kind_ko, cmp_ko, this_p, prev_p, eq,
                        table=build_table(weeks, months, cum,
                                          unrealized=eq.get("unrealized") if eq else None))

    print(msg)
    print("\n---")
    if args.dry:
        print("[DRY] not sending Telegram")
        return 0

    # 발송 스킵은 "정말 아무것도 없을 때"만 — 누적 거래 0건 AND 오픈 포지션 0개.
    # (포지션을 Day-30까지 홀드하면 주간 완결거래가 0이어도 누적·미실현 표는 유효.)
    open_pos = eq.get("open_positions", 0) if eq else 0
    if cum["n"] == 0 and open_pos == 0:
        print("[SKIP] no cumulative trades and no open positions — not sending")
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
