#!/usr/bin/env python3
#
# AI Autonomous Trading Pipeline - orchestrates all skills.
#
# Flow:
#   1. Health check (at-monitor) -> identify CRITICAL sessions
#   2. Parameter optimization (at-backtest/optimize) -> grid search
#   3. Apply best config to session
#
# Usage:
#   python pipeline.py run --session-id <ID> --api-url http://localhost:8001
#   python pipeline.py optimize --session-id <ID> --api-url http://localhost:8001
#   python pipeline.py auto --api-url http://localhost:8001
#

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SYMBOL_SELECT_DIR = SKILL_DIR.parent / "at-symbol-select" / "scripts"
BACKTEST_DIR = SKILL_DIR.parent / "at-backtest" / "scripts"
MONITOR_DIR = SKILL_DIR.parent / "at-monitor" / "scripts"


def run_cmd(cmd, timeout=600):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return {"error": result.stderr.strip()[-300:]}
        text = result.stdout.strip()
        # Try JSON parse
        for start_char in ["{", "["]:
            idx = text.find(start_char)
            if idx >= 0:
                try:
                    return json.loads(text[idx:])
                except json.JSONDecodeError:
                    pass
        return {"output": text}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}


def step_health_check(api_url, session_id=None):
    print("\n[Step 0] Health Check")
    cmd = [sys.executable, str(MONITOR_DIR / "health_check.py"),
           "--api-url", api_url, "--json"]
    if session_id:
        cmd.extend(["--session-id", session_id])
    return run_cmd(cmd, timeout=30)


def step_optimize(strategy, symbol, futures=True, days=14):
    print(f"\n[Step 2] Optimizing {strategy} / {symbol}...")
    cmd = [sys.executable, str(BACKTEST_DIR / "optimize.py"),
           "--strategy", strategy, "--symbol", symbol,
           "--auto-ranges", "--days", str(days),
           "--scoring", "weighted", "--top", "3", "--json"]
    if futures:
        cmd.extend(["--exchange", "BinanceFutures"])
    return run_cmd(cmd, timeout=600)


def step_apply(api_url, session_id, symbol, params, reason):
    print(f"\n[Step 3] Applying {symbol} to {session_id}...")
    cmd = [sys.executable, str(SYMBOL_SELECT_DIR / "run_pipeline.py"),
           "apply", "--session-id", session_id, "--symbol", symbol,
           "--params", json.dumps(params), "--reason", reason,
           "--api-url", api_url]
    return run_cmd(cmd, timeout=30)


def get_session_info(api_url, session_id):
    cmd = [sys.executable, str(SYMBOL_SELECT_DIR / "run_pipeline.py"),
           "session-info", "--session-id", session_id, "--api-url", api_url]
    return run_cmd(cmd, timeout=15)


def cmd_optimize(args):
    print(f"[Optimize] Session: {args.session_id}")
    info = get_session_info(args.api_url, args.session_id)
    if "error" in info:
        print(f"Error: {info['error']}")
        return

    symbol = info.get("symbol", "")
    strategy = info.get("strategy_name", "rsi_martingale")
    cfg = info.get("strategy_config", {})
    is_futures = "Futures" in cfg.get("exchange_name", "")

    print(f"Symbol: {symbol}, Strategy: {strategy}, Futures: {is_futures}")

    opt_result = step_optimize(strategy, symbol, futures=is_futures, days=args.days)
    if isinstance(opt_result, dict) and "error" in opt_result:
        print(f"Optimization error: {opt_result.get('error', '?')}")
        return

    top = opt_result if isinstance(opt_result, list) else opt_result.get("top_results", [])
    if not top:
        print("No results.")
        return

    best = top[0] if isinstance(top, list) else top
    print(f"\nBest: {best.get('config', {})}")
    print(f"Score: {best.get('weighted_score', best.get('score', 0))}")

    if not args.dry_run:
        params = best.get("config", {})
        reason = f"Optimized: score={best.get('weighted_score', 0)}"
        result = step_apply(args.api_url, args.session_id, symbol, params, reason)
        print(f"Applied: {json.dumps(result, indent=2)}")
    else:
        print("\n[Dry-run] Would apply above config.")


def cmd_auto(args):
    print("[Auto] Checking all sessions...")
    health = step_health_check(args.api_url)

    if isinstance(health, dict) and "error" in health:
        print(f"Error: {health}")
        return

    if not isinstance(health, list):
        print(str(health))
        return

    criticals = [h for h in health if h.get("grade") == "CRITICAL"]
    print(f"Found: {len(criticals)} CRITICAL out of {len(health)} total")

    if not criticals:
        print("No critical sessions.")
        return

    for h in criticals:
        sid = h.get("session_id", "")
        m = h.get("metrics", {})
        print(f"\nCRITICAL: {sid} ({m.get('symbol', '?')})")
        if not args.dry_run:
            args.session_id = sid
            cmd_optimize(args)
        else:
            print("[Dry-run] Would optimize.")


def cmd_run(args):
    print(f"[Pipeline] Session: {args.session_id}")

    # Health check
    health = step_health_check(args.api_url, args.session_id)
    if isinstance(health, list) and health:
        print(f"Grade: {health[0].get('grade', '?')}")

    # Get session info
    info = get_session_info(args.api_url, args.session_id)
    if "error" in info:
        print(f"Error: {info}")
        return

    symbol = info.get("symbol", "")
    strategy = info.get("strategy_name", "rsi_martingale")
    cfg = info.get("strategy_config", {})
    is_futures = "Futures" in cfg.get("exchange_name", "")
    print(f"Current: {symbol} / {strategy} / futures={is_futures}")

    # Optimize
    opt_result = step_optimize(strategy, symbol, futures=is_futures, days=args.days)
    if isinstance(opt_result, dict) and "error" not in opt_result:
        top = opt_result.get("top_results", [])
        if top:
            best = top[0]
            print(f"\nBest: {best.get('config', {})}")
            print(f"Score: {best.get('weighted_score', 0)}")

            if not args.dry_run:
                params = best.get("config", {})
                reason = "Pipeline optimized"
                step_apply(args.api_url, args.session_id, symbol, params, reason)
    else:
        print(f"Optimization failed: {opt_result}")

    print("\nPipeline complete.")


def main():
    parser = argparse.ArgumentParser(description="AI Trading Pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run")
    p_run.add_argument("--session-id", required=True)
    p_run.add_argument("--api-url", default="http://localhost:8001")
    p_run.add_argument("--days", type=int, default=14)
    p_run.add_argument("--dry-run", action="store_true")

    p_opt = sub.add_parser("optimize")
    p_opt.add_argument("--session-id", required=True)
    p_opt.add_argument("--api-url", default="http://localhost:8001")
    p_opt.add_argument("--days", type=int, default=14)
    p_opt.add_argument("--dry-run", action="store_true")

    p_auto = sub.add_parser("auto")
    p_auto.add_argument("--api-url", default="http://localhost:8001")
    p_auto.add_argument("--days", type=int, default=14)
    p_auto.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    {"run": cmd_run, "optimize": cmd_optimize, "auto": cmd_auto}[args.command](args)


if __name__ == "__main__":
    main()
