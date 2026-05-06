#!/usr/bin/env python3
"""Day 7/14/30 milestone check for newly-seeded paper sessions.

Per `paper_pool_master.md §5-D` checklist. Computes age-since-creation per
session, applies the appropriate Day-7/14/30 checks, flags anomalies, and
prints a structured report.

Focus: 5 newly-seeded research_track sessions (3 funding_carry + 2
autocorr_regime, both seeded 2026-05-04). Other paper sessions are also
included for full pool visibility.

Usage:
  python -m scripts.milestone_check                    # all sessions
  python -m scripts.milestone_check --research-only    # only 5 newly seeded
  python -m scripts.milestone_check --since 2026-05-04 # sessions newer than this date
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.composer_framework.paper_session import SessionStore, PaperSession  # noqa: E402

DEFAULT_STORE_ROOT = ROOT / "runs" / "paper_sessions"

# Newly-seeded research_track paradigm sessions (focus targets)
RESEARCH_TRACK_SEEDS = {
    "funding_carry": [
        "472fafc0-65a",   # HBARUSDT
        "accc65a5-e27",   # AXSUSDT
        "f4c8ee87-a76",   # COMPUSDT
    ],
    "autocorr_regime": [
        "694e4f47-369",   # LINKUSDT
        "469a7a29-9be",   # UNIUSDT
    ],
    "funding_dispersion": [
        "d2640960-52b",   # ETCUSDT
    ],
    "cross_symbol_lead_lag": [
        "b5041367-5a6",   # DOGEUSDT
    ],
}

# Backtest baseline metrics (from R-3 robustness, embedded in spec.notes)
BASELINE_METRICS = {
    # funding_carry
    "472fafc0-65a": {"alpha": 107.68, "sharpe": 1.87, "pf": 3.06, "trades_1y": 19, "perm_p": 0.000},
    "accc65a5-e27": {"alpha": 148.62, "sharpe": 1.48, "pf": 2.53, "trades_1y": 38, "perm_p": 0.000},
    "f4c8ee87-a76": {"alpha": 118.43, "sharpe": 1.67, "pf": 2.75, "trades_1y": 28, "perm_p": 0.000},
    # autocorr_regime
    "694e4f47-369": {"alpha": 116.18, "sharpe": 1.25, "pf": 3.33, "trades_1y": 84, "perm_p": 0.000},
    "469a7a29-9be": {"alpha": 120.27, "sharpe": 1.10, "pf": 2.70, "trades_1y": 88, "perm_p": 0.000},
    # funding_dispersion
    "d2640960-52b": {"alpha": 138.00, "sharpe": 3.50, "pf": 3.72, "trades_1y": 37, "perm_p": 0.000},
    # cross_symbol_lead_lag (resurrected from 18th graveyard via BTC 1y backfill)
    "b5041367-5a6": {"alpha": 69.79, "sharpe": 1.83, "pf": 3.03, "trades_1y": 34, "perm_p": 0.005},
}


def parse_iso(ts: str) -> datetime:
    """Parse ISO datetime, assume UTC if no tz."""
    s = ts.replace("Z", "")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def days_since(created_at: str) -> float:
    if not created_at:
        return -1.0
    dt = parse_iso(created_at)
    now = datetime.now(timezone.utc)
    return (now - dt).total_seconds() / 86400.0


def expected_trades_at_day(trades_1y: float, day: float) -> float:
    """Linear extrapolation: trades_1y / 365 * day."""
    return trades_1y / 365.0 * day


def check_one(s: PaperSession) -> dict:
    age_d = days_since(s.created_at)
    base = BASELINE_METRICS.get(s.session_id, {})
    expected_trades_now = expected_trades_at_day(base.get("trades_1y", 0), age_d)
    actual_trades = s.n_trades
    progress_pct = (
        (actual_trades / expected_trades_now * 100.0)
        if expected_trades_now > 0 else float("nan")
    )

    alerts = []
    if age_d >= 7:
        # Day 7 checklist
        if base.get("trades_1y", 0) > 0:
            if progress_pct < 5:
                alerts.append(f"Day 7: trade progress {progress_pct:.1f}% < 5% (vs baseline {base['trades_1y']}/y)")
            elif progress_pct < 30:
                alerts.append(f"Day 7: low progress {progress_pct:.1f}% (expected ~{expected_trades_now:.1f})")
        # drawdown
        if s.total_return_pct < -0.15:
            alerts.append(f"Day 7: drawdown {s.total_return_pct*100:.1f}% < -15% threshold")

    if age_d >= 14:
        if s.total_return_pct < -0.25:
            alerts.append(f"Day 14: drawdown {s.total_return_pct*100:.1f}% < -25% threshold")
        # alpha sign check requires market context — skip for now (manual)

    if age_d >= 30:
        if base.get("alpha", 0) > 0:
            alpha_pct_30d = s.total_return_pct * 100 * (365 / 30)  # annualized
            ratio = alpha_pct_30d / base["alpha"] if base["alpha"] > 0 else 0
            if ratio < 0.8 or ratio > 1.2:
                alerts.append(f"Day 30: alpha {alpha_pct_30d:.1f}% vs baseline {base['alpha']:.1f}% (ratio {ratio:.2f})")

    return {
        "session_id": s.session_id,
        "name": s.name,
        "symbol": s.symbol,
        "status": s.status,
        "created_at": s.created_at,
        "age_days": round(age_d, 2),
        "n_cycles": s.n_cycles,
        "n_trades": s.n_trades,
        "total_return_pct": round(s.total_return_pct * 100, 3),
        "baseline_trades_1y": base.get("trades_1y", "—"),
        "baseline_alpha": base.get("alpha", "—"),
        "expected_trades_now": round(expected_trades_now, 2) if expected_trades_now > 0 else "—",
        "trades_progress_pct": round(progress_pct, 1) if expected_trades_now > 0 else "—",
        "alerts": alerts,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--research-only", action="store_true",
                   help="Show only the 5 newly-seeded research_track sessions")
    p.add_argument("--since", default=None, help="Filter sessions created on/after YYYY-MM-DD")
    p.add_argument("--store", default=str(DEFAULT_STORE_ROOT))
    args = p.parse_args()

    store = SessionStore(Path(args.store))
    sessions = store.list_all()

    research_ids = {sid for sids in RESEARCH_TRACK_SEEDS.values() for sid in sids}

    if args.research_only:
        sessions = [s for s in sessions if s.session_id in research_ids]
    if args.since:
        cutoff = parse_iso(args.since + "T00:00:00")
        sessions = [s for s in sessions if s.created_at and parse_iso(s.created_at) >= cutoff]

    if not sessions:
        print("No sessions match filter.")
        return 0

    rows = [check_one(s) for s in sessions]
    rows.sort(key=lambda r: (r["age_days"] if r["age_days"] >= 0 else 9999), reverse=True)

    # Render
    print(f"=== Milestone Check — {datetime.now(timezone.utc).isoformat(timespec='seconds')} UTC ===")
    print(f"Sessions: {len(rows)}")
    print()
    fmt = ("{age:>5s} {sid:>13s} {sym:>10s} {cyc:>5s}/{tr:>4s} "
           "ret {ret:>7s}% prog {prog:>6s}% base_α {ba:>6s} {alerts}")
    print(fmt.format(age="age", sid="session", sym="symbol", cyc="cyc",
                     tr="trd", ret="ret", prog="prog", ba="α_bl",
                     alerts="alerts"))
    print("-" * 110)
    n_alerts = 0
    for r in rows:
        is_research = r["session_id"] in research_ids
        marker = "⭐" if is_research else "  "
        alerts_str = ""
        if r["alerts"]:
            alerts_str = f" ⚠ {len(r['alerts'])}"
            n_alerts += len(r["alerts"])
        print(fmt.format(
            age=f"{r['age_days']:.1f}d",
            sid=marker + r["session_id"][:11],
            sym=r["symbol"][:10],
            cyc=str(r["n_cycles"]),
            tr=str(r["n_trades"]),
            ret=f"{r['total_return_pct']:+.2f}",
            prog=(f"{r['trades_progress_pct']}" if r["trades_progress_pct"] != "—" else "—"),
            ba=(f"{r['baseline_alpha']:.0f}" if isinstance(r["baseline_alpha"], (int, float)) else "—"),
            alerts=alerts_str,
        ))

    if n_alerts > 0:
        print()
        print(f"=== Alerts ({n_alerts}) ===")
        for r in rows:
            for alert in r["alerts"]:
                print(f"  {r['session_id'][:11]} {r['symbol']:>10s}  {alert}")

    print()
    print("Legend: cyc=cycles, trd=trades, ret=return%, prog=trade progress vs 1y baseline,")
    print("        α_bl=backtest alpha %. ⭐=newly-seeded research_track session.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
