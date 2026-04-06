#!/usr/bin/env python3
"""
Continuous Session Monitor - periodic health checks with auto-intervention.

Usage:
    # Monitor all sessions every 60s (log only)
    python monitor.py --api-url http://localhost:8001 --interval 60

    # Auto-pause CRITICAL sessions
    python monitor.py --api-url http://localhost:8001 --interval 300 --auto-action pause

    # Custom thresholds
    python monitor.py --api-url http://localhost:8001 --interval 60         --max-drawdown -15 --min-win-rate 45 --min-cycles 10

    # Single check (no loop)
    python monitor.py --api-url http://localhost:8001 --once
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# Import health_check module
sys.path.insert(0, str(Path(__file__).parent))
from health_check import fetch_sessions, assess_health


def pause_session(api_url, session_id):
    """POST /api/v1/live/{session_id}/pause."""
    url = f"{api_url}/api/v1/live/{session_id}/pause"
    try:
        req = urllib.request.Request(url, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def trigger_symbol_switch(api_url, session_id):
    """Trigger AI symbol selection for session."""
    # This would call the at-symbol-select skill pipeline
    # For now, log the recommendation
    return {"action": "symbol-switch-recommended", "session_id": session_id}


def run_check(api_url, thresholds, auto_action="log"):
    """Run a single health check cycle.

    Returns:
        list of health results with any actions taken
    """
    try:
        data = fetch_sessions(api_url)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {e}", file=sys.stderr)
        return []

    sessions = data.get("sessions", [])

    if not sessions:
        return []

    results = []
    for session in sessions:
        sid = session.get("session_id", "")
        health = assess_health(session)
        health["session_id"] = sid
        health["strategy"] = session.get("strategy_name", "?")
        health["action_taken"] = None

        # Apply custom thresholds (override default grades)
        m = health["metrics"]
        if m["total_cycles"] >= thresholds.get("min_cycles", 10):
            if m["max_drawdown"] < thresholds.get("max_drawdown", -20):
                health["grade"] = "CRITICAL"
                if f"MDD" not in str(health["reasons"]):
                    health["reasons"].append(f"MDD {m['max_drawdown']:.1f}% below threshold")
            if m["win_rate"] < thresholds.get("min_win_rate", 40):
                health["grade"] = "CRITICAL"
                if f"Win rate" not in str(health["reasons"]):
                    health["reasons"].append(f"Win rate {m['win_rate']:.1f}% below threshold")

        # Auto-action for CRITICAL
        if health["grade"] == "CRITICAL" and auto_action != "log":
            if auto_action == "pause":
                result = pause_session(api_url, sid)
                health["action_taken"] = {"type": "pause", "result": result}
                print(f"[{datetime.now().strftime('%H:%M:%S')}] PAUSED {sid} ({m['symbol']}): {health['reasons']}")
            elif auto_action == "symbol-switch":
                result = trigger_symbol_switch(api_url, sid)
                health["action_taken"] = {"type": "symbol-switch", "result": result}
                print(f"[{datetime.now().strftime('%H:%M:%S')}] SYMBOL-SWITCH triggered for {sid}")

        results.append(health)

    return results


def print_status(results, timestamp):
    """Print compact status line."""
    if not results:
        print(f"[{timestamp}] No running sessions")
        return

    grade_counts = {}
    for r in results:
        g = r["grade"]
        grade_counts[g] = grade_counts.get(g, 0) + 1

    parts = []
    for g in ["CRITICAL", "WARNING", "HEALTHY", "INSUFFICIENT", "STALE"]:
        if g in grade_counts:
            parts.append(f"{g}={grade_counts[g]}")

    # Show critical/warning details
    problems = [r for r in results if r["grade"] in ("CRITICAL", "WARNING")]
    details = ""
    if problems:
        detail_parts = []
        for p in problems:
            m = p["metrics"]
            detail_parts.append(
                f"{m['symbol']}({p['grade'][:4]}:ret={m['total_return']:+.1f}%,mdd={m['max_drawdown']:.0f}%)"
            )
        details = " | " + ", ".join(detail_parts)

    action_count = sum(1 for r in results if r.get("action_taken"))
    action_str = f" | Actions: {action_count}" if action_count else ""

    print(f"[{timestamp}] {len(results)} sessions: {' '.join(parts)}{details}{action_str}")


def main():
    parser = argparse.ArgumentParser(description="Continuous Session Monitor")
    parser.add_argument("--api-url", default="http://localhost:8001")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    parser.add_argument("--max-drawdown", type=float, default=-20, help="MDD threshold for CRITICAL")
    parser.add_argument("--min-win-rate", type=float, default=40, help="Min win rate for CRITICAL")
    parser.add_argument("--min-cycles", type=int, default=10, help="Min cycles before threshold checks")
    parser.add_argument("--auto-action", choices=["log", "pause", "symbol-switch"], default="log",
                        help="Action on CRITICAL sessions")
    parser.add_argument("--once", action="store_true", help="Single check, no loop")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    thresholds = {
        "max_drawdown": args.max_drawdown,
        "min_win_rate": args.min_win_rate,
        "min_cycles": args.min_cycles,
    }

    print(f"Monitor started: interval={args.interval}s, action={args.auto_action}")
    print(f"Thresholds: MDD>{args.max_drawdown}%, WR>{args.min_win_rate}%, min_cycles={args.min_cycles}")
    print()

    if args.once:
        results = run_check(args.api_url, thresholds, args.auto_action)
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            # Full report for single check
            from health_check import main as hc_main
            sys.argv = ["health_check.py", "--api-url", args.api_url]
            if args.json:
                sys.argv.append("--json")
            hc_main()
        return

    try:
        while True:
            ts = datetime.now().strftime("%H:%M:%S")
            results = run_check(args.api_url, thresholds, args.auto_action)
            print_status(results, ts)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nMonitor stopped.")


if __name__ == "__main__":
    main()
