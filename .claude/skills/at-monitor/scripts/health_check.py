#!/usr/bin/env python3
"""
Session Health Check - live session status assessment.

Usage:
    python health_check.py --api-url http://localhost:8001
    python health_check.py --api-url http://localhost:8001 --json
    python health_check.py --api-url http://localhost:8001 --session-id <ID>
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone


def fetch_sessions(api_url):
    """GET /api/v1/live/monitor/sessions - no auth required."""
    url = f"{api_url}/api/v1/live/monitor/sessions"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def assess_health(session, stats=None):
    """Assess session health based on metrics.

    Args:
        session: Session data (from monitor/sessions API, stats are inline)
        stats: Unused (kept for backward compat)

    Returns:
        dict with grade, reasons, metrics
    """
    grade = "HEALTHY"
    reasons = []

    symbol = session.get("symbol", "?")
    status = session.get("status", "?")
    is_paper = session.get("is_paper", True)

    # Stats are inline in monitor API response
    total_return = session.get("total_return", 0) or 0
    win_rate = session.get("win_rate", 0) or 0
    max_drawdown = session.get("max_drawdown", 0) or 0
    total_cycles = session.get("total_cycles", 0) or 0
    sharpe = session.get("sharpe_ratio", 0) or 0
    profit_factor = session.get("profit_factor", 0) or 0
    avg_pnl = session.get("avg_pnl", 0) or 0

    metrics = {
        "symbol": symbol,
        "status": status,
        "is_paper": is_paper,
        "total_return": total_return,
        "win_rate": win_rate,
        "max_drawdown": max_drawdown,
        "total_cycles": total_cycles,
        "sharpe_ratio": sharpe,
        "profit_factor": profit_factor,
        "avg_pnl": avg_pnl,
    }

    if status != "RUNNING":
        return {"grade": "STOPPED", "reasons": [f"Status: {status}"], "metrics": metrics}

    # Not enough data
    if total_cycles < 3:
        return {"grade": "INSUFFICIENT", "reasons": [f"Only {total_cycles} cycles"], "metrics": metrics}

    # CRITICAL checks
    if max_drawdown < -20:
        grade = "CRITICAL"
        reasons.append(f"MDD {max_drawdown:.1f}% < -20%")

    if total_cycles >= 10 and win_rate < 40:
        grade = "CRITICAL"
        reasons.append(f"Win rate {win_rate:.1f}% < 40%")

    if total_return < -10:
        grade = "CRITICAL"
        reasons.append(f"Return {total_return:.2f}% < -10%")

    # WARNING checks (only if not already CRITICAL)
    if grade == "HEALTHY":
        if max_drawdown < -10:
            grade = "WARNING"
            reasons.append(f"MDD {max_drawdown:.1f}% approaching limit")

        if total_cycles >= 10 and win_rate < 50:
            grade = "WARNING"
            reasons.append(f"Win rate {win_rate:.1f}% below 50%")

        if total_return < 0:
            grade = "WARNING"
            reasons.append(f"Negative return {total_return:.2f}%")

        if sharpe < 0:
            grade = "WARNING"
            reasons.append(f"Negative Sharpe {sharpe:.2f}")

    if grade == "HEALTHY":
        reasons.append("All metrics within normal range")

    return {"grade": grade, "reasons": reasons, "metrics": metrics}


def main():
    parser = argparse.ArgumentParser(description="Session Health Check")
    parser.add_argument("--api-url", default="http://localhost:8001")
    parser.add_argument("--session-id", default=None, help="Check specific session")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    try:
        data = fetch_sessions(args.api_url)
    except Exception as e:
        print(f"Error fetching sessions: {e}", file=sys.stderr)
        sys.exit(1)

    sessions = data.get("sessions", [])

    if args.session_id:
        sessions = [s for s in sessions if s.get("session_id") == args.session_id]

    if not sessions:
        if args.json:
            print(json.dumps({"sessions": [], "summary": "No running sessions"}))
        else:
            print("No running sessions found.")
        return

    results = []
    for session in sessions:
        sid = session.get("session_id", "")
        health = assess_health(session)
        health["session_id"] = sid
        health["strategy"] = session.get("strategy_name", "?")
        results.append(health)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        grade_icons = {
            "HEALTHY": "[OK]",
            "WARNING": "[WARN]",
            "CRITICAL": "[CRIT]",
            "INSUFFICIENT": "[LOW]",
            "STOPPED": "[STOP]",
            "STALE": "[STALE]",
        }
        sep = "=" * 70
        print(f"\n{sep}")
        print(f"  Session Health Report - {len(results)} sessions")
        print(sep)

        for r in results:
            icon = grade_icons.get(r["grade"], "[?]")
            m = r["metrics"]
            print(f"\n  {icon} {r['session_id'][:20]:20s}  {m['symbol']:12s}  {r['strategy']:20s}")
            print(f"       Return={m['total_return']:+.2f}%  WR={m['win_rate']:.1f}%  MDD={m['max_drawdown']:.1f}%  Cycles={m['total_cycles']}  Sharpe={m['sharpe_ratio']:.2f}")
            for reason in r["reasons"]:
                print(f"       - {reason}")

        # Summary
        counts = {}
        for r in results:
            g = r["grade"]
            counts[g] = counts.get(g, 0) + 1

        print(f"\n{sep}")
        summary_parts = [f"{g}={c}" for g, c in sorted(counts.items())]
        print(f"  Summary: {', '.join(summary_parts)}")
        print(sep)

        criticals = [r for r in results if r["grade"] == "CRITICAL"]
        if criticals:
            print(f"\n  !! {len(criticals)} CRITICAL session(s) need attention !!")


if __name__ == "__main__":
    main()
