#!/usr/bin/env python3
"""
AI 종목 선정 스코어링 — 백엔드 _calculate_score()와 100% 동일.

신뢰도 가중 복합 점수:
  base_score = (return% × 0.7) + (win_rate% × 0.15)
  reliability = 거래 횟수 기반 승수 (1~2회: 0.2~0.4, 10+회: 1.0~1.2)
  score = base_score × reliability

Usage:
    # Python module
    from scoring import calculate_score
    score = calculate_score(total_return=5.43, win_rate=62.7, total_cycles=169)

    # CLI
    python scoring.py --return 5.43 --win-rate 62.7 --cycles 169
    python scoring.py --results-file /tmp/bt_results.json
"""

import argparse
import json
import sys
from typing import Dict, List, Any


def calculate_score(
    total_return: float,
    win_rate: float,
    total_cycles: int,
) -> float:
    """백엔드 _calculate_score()와 동일한 신뢰도 가중 점수 계산.

    Args:
        total_return: 총 수익률 (%, e.g., 5.43)
        win_rate: 승률 (%, e.g., 62.7)
        total_cycles: 완료된 매매 사이클 수

    Returns:
        reliability-weighted composite score
    """
    if total_cycles == 0:
        return float('-inf')

    # Base score: return-dominant + win_rate as tiebreaker
    base_score = (total_return * 0.7) + (win_rate * 0.15)

    # Reliability multiplier based on trade count
    if total_cycles <= 2:
        reliability = 0.2 + (total_cycles * 0.1)       # 0.3 ~ 0.4
    elif total_cycles <= 4:
        reliability = 0.4 + ((total_cycles - 2) * 0.15) # 0.55 ~ 0.7
    elif total_cycles <= 9:
        reliability = 0.7 + ((total_cycles - 4) * 0.06) # 0.76 ~ 1.0
    else:
        reliability = 1.0 + (min(total_cycles, 30) - 10) * 0.01  # 1.0 ~ 1.2

    return base_score * reliability


def score_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """백테스트 결과 목록에 스코어를 추가하고 정렬.

    Args:
        results: 백테스트 결과 목록 (total_return, win_rate, total_cycles 포함)

    Returns:
        score 내림차순 정렬된 결과 (각 항목에 'score' 키 추가)
    """
    scored = []
    for r in results:
        ret = float(str(r.get("total_return", "0")).replace('%', '').replace(',', ''))
        wr = float(str(r.get("win_rate", "0")).replace('%', ''))
        cycles = int(r.get("total_cycles", 0))

        entry = dict(r)
        entry["score"] = round(calculate_score(ret, wr, cycles), 4)
        scored.append(entry)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def main():
    parser = argparse.ArgumentParser(description="AI 종목 선정 스코어 계산")
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
