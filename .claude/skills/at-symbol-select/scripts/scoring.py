#!/usr/bin/env python3
"""
AI 종목 선정 스코어링 CLI — backend.app.core.symbol_score의 thin wrapper.

신뢰도 가중 복합 점수:
  base_score = (return% × 0.7) + (win_rate% × 0.15)
  reliability = 거래 횟수 기반 승수 (1~2회: 0.3~0.4, 10+회: 1.0~1.2)
  score = base_score × reliability

⚠️ 알고리즘 변경은 backend/app/core/symbol_score.py에서만 수행할 것.
   이 파일은 CLI/import 어댑터일 뿐.

Usage:
    # Python module (호환)
    from scoring import calculate_score, score_results
    score = calculate_score(total_return=5.43, win_rate=62.7, total_cycles=169)

    # CLI
    python scoring.py --return 5.43 --win-rate 62.7 --cycles 169
    python scoring.py --results-file /tmp/bt_results.json
"""

import argparse
import json
import sys
from pathlib import Path

# ─── Bootstrap: backend on sys.path ──────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent.parent.parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Re-export the canonical implementation so existing imports keep working.
from app.core.symbol_score import (  # noqa: E402
    calculate_score,
    calculate_score_from_result,
    score_results,
)

__all__ = ["calculate_score", "calculate_score_from_result", "score_results"]


def main():
    parser = argparse.ArgumentParser(description="AI 종목 선정 스코어 계산 (backend symbol_score wrapper)")
    parser.add_argument("--return", dest="total_return", type=float, help="총 수익률 (%)")
    parser.add_argument("--win-rate", type=float, help="승률 (%)")
    parser.add_argument("--cycles", type=int, help="사이클 수")
    parser.add_argument("--results-file", help="백테스트 결과 JSON 파일")

    args = parser.parse_args()

    if args.results_file:
        with open(args.results_file) as f:
            results = json.load(f)
        scored = score_results(results)
        print(json.dumps(scored, indent=2, ensure_ascii=False))
    elif args.total_return is not None and args.win_rate is not None and args.cycles is not None:
        score = calculate_score(args.total_return, args.win_rate, args.cycles)
        print(f"Score: {score:.4f}")
        print(f"  Return {args.total_return}% × 0.7 = {args.total_return * 0.7:.2f}")
        print(f"  WinRate {args.win_rate}% × 0.15 = {args.win_rate * 0.15:.2f}")
        print(f"  Base = {(args.total_return * 0.7) + (args.win_rate * 0.15):.2f}")
        if args.cycles <= 2:
            rel = 0.2 + (args.cycles * 0.1)
        elif args.cycles <= 4:
            rel = 0.4 + ((args.cycles - 2) * 0.15)
        elif args.cycles <= 9:
            rel = 0.7 + ((args.cycles - 4) * 0.06)
        else:
            rel = 1.0 + (min(args.cycles, 30) - 10) * 0.01
        print(f"  Reliability ({args.cycles} cycles) = {rel:.2f}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
