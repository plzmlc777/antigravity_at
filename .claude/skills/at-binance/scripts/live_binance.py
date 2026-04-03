#!/usr/bin/env python3
"""
Binance Live Trading Manager - 기존 API를 통한 라이브 세션 관리.
API 엔진의 LiveManager를 활용하여 바이낸스 라이브 트레이딩을 제어.

Usage:
    # 세션 시작
    python live_binance.py start --symbol BTCUSDT --strategy dip_martingale \
        --interval 1h --leverage 5 --paper

    # 세션 상태 조회
    python live_binance.py status
    python live_binance.py status --session-id <id>

    # 세션 중지
    python live_binance.py stop --session-id <id>

    # 세션 일시정지/재개
    python live_binance.py pause --session-id <id>
    python live_binance.py resume --session-id <id>

    # 심볼 변경 (AI 추천 기반)
    python live_binance.py switch --session-id <id> --new-symbol ETHUSDT
"""

import argparse
import json
import subprocess
import sys
from typing import Dict, Any, Optional

API_BASE = "http://localhost:8001/api/v1"


def _api_call(method: str, endpoint: str, data: Dict = None, timeout: int = 30) -> Optional[Dict]:
    """API 호출 헬퍼."""
    url = f"{API_BASE}{endpoint}"
    cmd = ["curl", "-s", "-m", str(timeout), "-X", method, url]

    if data:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(data)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return None
        if not result.stdout.strip():
            return {}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        print(f"Timeout: {url}")
        return None
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        print(f"Response: {result.stdout[:500]}")
        return None


def cmd_start(args):
    """라이브 세션 시작."""
    config = {}
    if args.leverage > 1:
        config["leverage"] = args.leverage
    if args.config:
        config.update(json.loads(args.config))

    exchange = args.exchange or "BinanceFutures"

    payload = {
        "strategy_id": args.strategy,
        "symbol": args.symbol,
        "interval": args.interval,
        "is_paper": args.paper,
        "exchange_name": exchange,
        "config": config,
    }

    print(f"Starting live session:")
    print(f"  Strategy: {args.strategy}")
    print(f"  Symbol: {args.symbol}")
    print(f"  Interval: {args.interval}")
    print(f"  Exchange: {exchange}")
    print(f"  Leverage: {args.leverage}x")
    print(f"  Paper: {args.paper}")
    if config:
        print(f"  Config: {json.dumps(config)}")
    print()

    result = _api_call("POST", "/live/sessions", payload, timeout=60)
    if result:
        if "id" in result:
            print(f"Session started: ID={result['id']}")
            print(f"  Status: {result.get('status', 'unknown')}")
        elif "detail" in result:
            print(f"Error: {result['detail']}")
        else:
            print(json.dumps(result, indent=2))
    else:
        print("Failed to start session.")


def cmd_status(args):
    """세션 상태 조회."""
    if args.session_id:
        result = _api_call("GET", f"/live/sessions/{args.session_id}")
        if result:
            _print_session_detail(result)
    else:
        result = _api_call("GET", "/live/sessions")
        if result:
            sessions = result if isinstance(result, list) else result.get("sessions", [])
            # 바이낸스 세션만 필터
            binance_sessions = [
                s for s in sessions
                if "binance" in (s.get("exchange_name", "") or "").lower()
                or (s.get("symbol", "").endswith("USDT"))
            ]

            if not binance_sessions:
                print("No active Binance sessions.")
                return

            print(f"{'ID':>4s}  {'Symbol':>12s}  {'Strategy':>20s}  {'Status':>10s}  {'Paper':>6s}  {'PnL':>10s}")
            print(f"{'-'*72}")
            for s in binance_sessions:
                print(
                    f"{s.get('id', '?'):>4s}  {s.get('symbol', '?'):>12s}  "
                    f"{s.get('strategy_id', '?'):>20s}  {s.get('status', '?'):>10s}  "
                    f"{'Y' if s.get('is_paper') else 'N':>6s}  "
                    f"{s.get('unrealized_pnl', 0):>10.2f}"
                )


def _print_session_detail(session: Dict):
    """세션 상세 정보 출력."""
    print(f"Session ID: {session.get('id')}")
    print(f"  Symbol: {session.get('symbol')}")
    print(f"  Strategy: {session.get('strategy_id')}")
    print(f"  Status: {session.get('status')}")
    print(f"  Paper: {session.get('is_paper')}")
    print(f"  Exchange: {session.get('exchange_name')}")
    print(f"  Interval: {session.get('interval')}")

    state = session.get("state", {})
    if state:
        print(f"  Current Level: {state.get('current_level', 0)}")
        print(f"  Avg Price: {state.get('average_price', 0)}")
        print(f"  Total Qty: {state.get('total_quantity', 0)}")
        print(f"  Unrealized PnL: {state.get('unrealized_pnl', 0):.2f}")


def cmd_stop(args):
    """세션 중지."""
    result = _api_call("POST", f"/live/sessions/{args.session_id}/stop")
    if result:
        print(f"Session {args.session_id} stopped.")
        if "detail" in result:
            print(f"  Detail: {result['detail']}")
    else:
        print(f"Failed to stop session {args.session_id}")


def cmd_pause(args):
    """세션 일시정지."""
    result = _api_call("POST", f"/live/sessions/{args.session_id}/pause")
    if result:
        print(f"Session {args.session_id} paused.")
    else:
        print(f"Failed to pause session {args.session_id}")


def cmd_resume(args):
    """세션 재개."""
    result = _api_call("POST", f"/live/sessions/{args.session_id}/resume")
    if result:
        print(f"Session {args.session_id} resumed.")
    else:
        print(f"Failed to resume session {args.session_id}")


def cmd_switch(args):
    """심볼 변경."""
    payload = {"new_symbol": args.new_symbol}
    result = _api_call("POST", f"/live/sessions/{args.session_id}/switch-symbol", payload)
    if result:
        print(f"Session {args.session_id}: switching to {args.new_symbol}")
        if "detail" in result:
            print(f"  Detail: {result['detail']}")
    else:
        print(f"Failed to switch symbol for session {args.session_id}")


def main():
    parser = argparse.ArgumentParser(description="Binance Live Trading Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # start
    p_start = subparsers.add_parser("start", help="Start a live session")
    p_start.add_argument("--symbol", required=True, help="Symbol (e.g., BTCUSDT)")
    p_start.add_argument("--strategy", "-s", required=True, help="Strategy name")
    p_start.add_argument("--interval", "-i", default="1h", help="Interval (default: 1h)")
    p_start.add_argument("--leverage", type=int, default=1, help="Leverage (default: 1)")
    p_start.add_argument("--exchange", default=None, help="Exchange name")
    p_start.add_argument("--paper", action="store_true", default=True, help="Paper trading (default)")
    p_start.add_argument("--real", action="store_true", help="Real trading")
    p_start.add_argument("--config", help="Strategy config as JSON")
    p_start.set_defaults(func=cmd_start)

    # status
    p_status = subparsers.add_parser("status", help="Show session status")
    p_status.add_argument("--session-id", help="Specific session ID")
    p_status.set_defaults(func=cmd_status)

    # stop
    p_stop = subparsers.add_parser("stop", help="Stop a session")
    p_stop.add_argument("--session-id", required=True, help="Session ID")
    p_stop.set_defaults(func=cmd_stop)

    # pause
    p_pause = subparsers.add_parser("pause", help="Pause a session")
    p_pause.add_argument("--session-id", required=True, help="Session ID")
    p_pause.set_defaults(func=cmd_pause)

    # resume
    p_resume = subparsers.add_parser("resume", help="Resume a paused session")
    p_resume.add_argument("--session-id", required=True, help="Session ID")
    p_resume.set_defaults(func=cmd_resume)

    # switch
    p_switch = subparsers.add_parser("switch", help="Switch symbol")
    p_switch.add_argument("--session-id", required=True, help="Session ID")
    p_switch.add_argument("--new-symbol", required=True, help="New symbol")
    p_switch.set_defaults(func=cmd_switch)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "start" and args.real:
        args.paper = False

    args.func(args)


if __name__ == "__main__":
    main()
