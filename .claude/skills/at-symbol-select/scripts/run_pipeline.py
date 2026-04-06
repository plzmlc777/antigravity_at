#!/usr/bin/env python3
"""
AI 종목 선정 파이프라인 헬퍼.

Claude 에이전트가 단계별로 호출하는 CLI 도구.
에이전트 자체가 AI(FIND/SELECT) 역할을 하고,
이 스크립트는 데이터 수집/백테스트/점수/적용의 실행부만 담당.

Commands:
    python run_pipeline.py fetch-market [--futures]
    python run_pipeline.py backtest --symbol BTCUSDT --strategy rsi_martingale [--config '{}'] [--days 14] [--futures]
    python run_pipeline.py batch-backtest --candidates '["BTCUSDT","ETHUSDT"]' --strategy rsi_martingale [--config '{}'] [--futures]
    python run_pipeline.py score --results-file /tmp/results.json
    python run_pipeline.py apply --session-id <id> --symbol ETHUSDT [--params '{}'] [--api-url http://localhost:8001]
    python run_pipeline.py session-info --session-id <id> [--api-url http://localhost:8001]
"""

import argparse
import json
import sys
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Any

# Paths
SCRIPT_DIR = Path(__file__).parent
BACKTEST_DIR = SCRIPT_DIR.parent.parent / "at-backtest" / "scripts"


def _extract_json(text: str) -> Optional[Dict]:
    """stdout에서 JSON 객체를 추출. 여러 줄 pretty-printed JSON 지원."""
    # Try parsing from first '{' to last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    # Fallback: try each line
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def cmd_fetch_market(args):
    """시장 데이터 수집."""
    cmd = [sys.executable, str(SCRIPT_DIR / "fetch_market_data.py")]
    if args.futures:
        cmd.append("--futures")
    if args.min_volume:
        cmd.extend(["--min-volume", str(args.min_volume)])
    if args.summary:
        cmd.append("--summary")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(result.stdout, end="")


def cmd_backtest(args):
    """단일 종목 백테스트."""
    backtest_py = BACKTEST_DIR / "backtest.py"
    if not backtest_py.exists():
        print(f"Error: backtest.py not found at {backtest_py}", file=sys.stderr)
        sys.exit(1)

    cmd = [
        sys.executable, str(backtest_py),
        "--strategy", args.strategy,
        "--symbol", args.symbol,
        "--interval", args.interval,
        "--days", str(args.days),
        "--capital", str(args.capital),
        "--source", args.source,
        "--json",
    ]
    if args.futures:
        cmd.append("--futures")
    if args.config:
        cmd.extend(["--config", args.config])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(json.dumps({
            "symbol": args.symbol,
            "error": result.stderr.strip()[-500:] if result.stderr else "unknown error"
        }))
        return

    # Parse JSON output (may be multi-line pretty-printed)
    data = _extract_json(result.stdout)
    if data:
        data["symbol"] = args.symbol
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(json.dumps({"symbol": args.symbol, "error": "no JSON output from backtest"}))


def cmd_batch_backtest(args):
    """여러 종목 일괄 백테스트."""
    try:
        candidates = json.loads(args.candidates)
    except json.JSONDecodeError:
        print("Error: --candidates must be valid JSON array", file=sys.stderr)
        sys.exit(1)

    backtest_py = BACKTEST_DIR / "backtest.py"
    if not backtest_py.exists():
        print(f"Error: backtest.py not found at {backtest_py}", file=sys.stderr)
        sys.exit(1)

    results = []
    total = len(candidates)

    for i, candidate in enumerate(candidates):
        # candidate can be string or dict
        if isinstance(candidate, str):
            symbol = candidate
            config = json.loads(args.config) if args.config else {}
        else:
            symbol = candidate["code"]
            config = json.loads(args.config) if args.config else {}
            if "direction" in candidate:
                config["position_side"] = candidate["direction"]

        config_str = json.dumps(config)
        print(f"[{i+1}/{total}] Backtesting {symbol}...", file=sys.stderr)

        cmd = [
            sys.executable, str(backtest_py),
            "--strategy", args.strategy,
            "--symbol", symbol,
            "--interval", args.interval,
            "--days", str(args.days),
            "--capital", str(args.capital),
            "--source", args.source,
            "--config", config_str,
            "--json",
        ]
        if args.futures:
            cmd.append("--futures")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                results.append({"symbol": symbol, "error": result.stderr.strip()[-200:]})
                continue

            data = _extract_json(result.stdout)
            if data:
                data["symbol"] = symbol
                if isinstance(candidate, dict) and "direction" in candidate:
                    data["direction"] = candidate["direction"]
                results.append(data)
            else:
                results.append({"symbol": symbol, "error": "no JSON output"})

        except subprocess.TimeoutExpired:
            results.append({"symbol": symbol, "error": "timeout"})

    # Score results
    sys.path.insert(0, str(SCRIPT_DIR))
    from scoring import score_results
    scored = score_results(results)
    print(json.dumps(scored, indent=2, ensure_ascii=False))


def cmd_score(args):
    """결과 파일에 스코어 적용."""
    with open(args.results_file) as f:
        results = json.load(f)

    sys.path.insert(0, str(SCRIPT_DIR))
    from scoring import score_results
    scored = score_results(results)
    print(json.dumps(scored, indent=2, ensure_ascii=False))


def cmd_session_info(args):
    """백엔드 세션 정보 조회."""
    url = f"{args.api_url}/api/v1/live/{args.session_id}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_apply(args):
    """종목 선정 결과를 백엔드에 적용.

    POST /api/v1/live/session/{id}/skill-symbol-switch
    """
    url = f"{args.api_url}/api/v1/live/session/{args.session_id}/skill-symbol-switch"

    payload = {
        "new_symbol": args.symbol,
        "source": "skill:symbol-select",
    }
    if args.params:
        payload["optimized_params"] = json.loads(args.params)
    if args.reason:
        payload["reason"] = args.reason
    if args.backtest_results:
        payload["backtest_results"] = json.loads(args.backtest_results)

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="AI 종목 선정 파이프라인 헬퍼")
    sub = parser.add_subparsers(dest="command", required=True)

    # fetch-market
    p_fetch = sub.add_parser("fetch-market", help="시장 데이터 수집")
    p_fetch.add_argument("--futures", action="store_true")
    p_fetch.add_argument("--min-volume", type=float, default=None)
    p_fetch.add_argument("--summary", action="store_true")

    # backtest
    p_bt = sub.add_parser("backtest", help="단일 종목 백테스트")
    p_bt.add_argument("--symbol", required=True)
    p_bt.add_argument("--strategy", required=True)
    p_bt.add_argument("--config", default=None)
    p_bt.add_argument("--interval", default="1m")
    p_bt.add_argument("--days", type=int, default=14)
    p_bt.add_argument("--capital", type=float, default=500)
    p_bt.add_argument("--source", default="exchange")
    p_bt.add_argument("--futures", action="store_true")

    # batch-backtest
    p_batch = sub.add_parser("batch-backtest", help="여러 종목 일괄 백테스트")
    p_batch.add_argument("--candidates", required=True, help="JSON array of symbols or objects")
    p_batch.add_argument("--strategy", required=True)
    p_batch.add_argument("--config", default=None)
    p_batch.add_argument("--interval", default="1m")
    p_batch.add_argument("--days", type=int, default=14)
    p_batch.add_argument("--capital", type=float, default=500)
    p_batch.add_argument("--source", default="exchange")
    p_batch.add_argument("--futures", action="store_true")

    # score
    p_score = sub.add_parser("score", help="결과 파일에 스코어 적용")
    p_score.add_argument("--results-file", required=True)

    # session-info
    p_session = sub.add_parser("session-info", help="세션 정보 조회")
    p_session.add_argument("--session-id", required=True)
    p_session.add_argument("--api-url", default="http://localhost:8001")

    # apply
    p_apply = sub.add_parser("apply", help="종목 선정 결과 적용")
    p_apply.add_argument("--session-id", required=True)
    p_apply.add_argument("--symbol", required=True)
    p_apply.add_argument("--params", default=None, help="Optimized params JSON")
    p_apply.add_argument("--reason", default=None, help="Selection reason")
    p_apply.add_argument("--backtest-results", default=None, help="Top results JSON")
    p_apply.add_argument("--api-url", default="http://localhost:8001")

    args = parser.parse_args()

    handlers = {
        "fetch-market": cmd_fetch_market,
        "backtest": cmd_backtest,
        "batch-backtest": cmd_batch_backtest,
        "score": cmd_score,
        "session-info": cmd_session_info,
        "apply": cmd_apply,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
