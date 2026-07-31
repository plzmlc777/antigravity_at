#!/usr/bin/env python3
"""
R-0 구조적 타당성 프리스크린 — 미국 ETF 일봉 스윙 트랙.

왜 이걸 먼저 하는가 (Lesson #40 계열):
    Research Track 의 R-4 elite gate 4-dim 은 암호화폐 시장에서 보정된 값이다.
      trades/yr >= 12, edge >= +2%/trade, util >= 30%, sharpe >= 1.5
    미국 ETF 일봉 스윙에 이 값을 그대로 적용했을 때 **애초에 도달 가능한
    분포인지**를 먼저 확인하지 않으면, 패러다임 수십 개를 만들어 전부
    graveyard 시키는 낭비가 된다.

    Lesson #40 의 교훈이 정확히 이것 — 임계값이 구조적으로 불가능하면
    가설이 아니라 임계값(또는 유니버스)을 다시 잡아야 한다.

측정:
    유니버스 그룹(core / leveraged) × 보유일(1/3/5/10/20)에 대해
      - 순방향 수익률 분포 (p50/p75/p90/p95 of |ret|)
      - 수수료 왕복(0.502%) 차감 후 +2% 이상 나오는 바 비율
      - "완벽한 방향 예측" 상한 = E[|ret|] - fee (이게 2%를 못 넘으면 구조적 불가)

    상한이 2%를 못 넘으면 그 그룹×보유일 조합은 elite gate 도달 불가로 판정한다.
    (완벽 예측조차 못 넘는 구간에서 실제 신호가 넘을 수는 없다)

출력: backend/runs/research_track/us_etf_daily_swing_feasibility/r0__metrics.json
실행: cd backend && PYTHONPATH=. python3 -m scripts.research.us_r0_structural_feasibility
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND.parent / ".env")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("us_r0_feasibility")

PARADIGM = "us_etf_daily_swing_feasibility"
OUT_DIR = BACKEND / "runs" / "research_track" / PARADIGM
UNIVERSE_PATH = BACKEND / "configs" / "us_universe.json"

# 키움 미국주식 온라인 수수료 0.25% 편도 + SEC Fee 매도 0.00206%
FEE_ONE_WAY = 0.0025
FEE_ROUND_TRIP = FEE_ONE_WAY * 2 + 0.0000206

HOLDS = (1, 3, 5, 10, 20)
EDGE_TARGET = 0.02          # R-4 elite gate: edge >= +2%/trade (net)
MIN_BARS = 500


def load_group(symbols: list) -> dict:
    """심볼별 일봉 종가 시리즈. first_valid_date 이후만."""
    db = SessionLocal()
    out = {}
    try:
        for sym in symbols:
            rows = db.execute(text(
                "SELECT timestamp, close FROM ohlcv "
                "WHERE symbol = :s AND time_frame = '1d' ORDER BY timestamp"
            ), {"s": sym}).all()
            if len(rows) < MIN_BARS:
                continue
            s = pd.Series([float(r[1]) for r in rows],
                          index=pd.to_datetime([r[0] for r in rows]))
            out[sym] = s
    finally:
        db.close()
    return out


def measure(series_map: dict, hold: int) -> dict:
    """보유일 hold 의 순방향 수익률 분포."""
    all_rets = []
    per_symbol = {}
    for sym, s in series_map.items():
        fwd = (s.shift(-hold) / s - 1.0).dropna()
        if len(fwd) < 50:
            continue
        arr = fwd.to_numpy()
        all_rets.append(arr)
        per_symbol[sym] = {
            "n": int(len(arr)),
            "abs_mean": float(np.mean(np.abs(arr))),
            "abs_p90": float(np.percentile(np.abs(arr), 90)),
        }
    if not all_rets:
        return {}

    r = np.concatenate(all_rets)
    a = np.abs(r)

    # 완벽한 방향 예측 상한: 매 거래에서 |ret| 을 전부 취하고 수수료만 차감
    perfect_edge = float(np.mean(a) - FEE_ROUND_TRIP)
    # 실전 근사 상한: 상위 30% 강한 움직임만 골라 잡았을 때
    strong = a[a >= np.percentile(a, 70)]
    selective_edge = float(np.mean(strong) - FEE_ROUND_TRIP)

    return {
        "hold_days": hold,
        "n_bars": int(len(r)),
        "n_symbols": len(per_symbol),
        "ret_mean": float(np.mean(r)),
        "abs_ret_p50": float(np.percentile(a, 50)),
        "abs_ret_p75": float(np.percentile(a, 75)),
        "abs_ret_p90": float(np.percentile(a, 90)),
        "abs_ret_p95": float(np.percentile(a, 95)),
        "abs_ret_mean": float(np.mean(a)),
        "frac_gross_above_target": float(np.mean(a >= EDGE_TARGET + FEE_ROUND_TRIP)),
        "perfect_direction_edge": perfect_edge,
        "selective_top30_edge": selective_edge,
        "gate_reachable_perfect": bool(perfect_edge >= EDGE_TARGET),
        "gate_reachable_selective": bool(selective_edge >= EDGE_TARGET),
        # trades/yr >= 12 & util >= 30% 동시 충족에 필요한 최소 트리거율
        "trades_per_yr_if_always_in": round(252 / hold, 1),
        "util_at_12_trades": round(12 * hold / 252, 3),
    }


def main() -> int:
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    groups = {
        "core": [r["symbol"] for r in universe["core"]],
        "leveraged": [r["symbol"] for r in universe["leveraged"]],
    }

    result = {
        "paradigm": PARADIGM,
        "phase": "R-0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "fee_one_way": FEE_ONE_WAY,
        "fee_round_trip": FEE_ROUND_TRIP,
        "edge_target": EDGE_TARGET,
        "groups": {},
    }

    for gname, syms in groups.items():
        series_map = load_group(syms)
        logger.info("[%s] %d/%d 종목 로드 (>=%d봉)", gname, len(series_map), len(syms), MIN_BARS)
        holds = {}
        for h in HOLDS:
            m = measure(series_map, h)
            if m:
                holds[str(h)] = m
                logger.info(
                    "  hold=%2dd  |ret| mean %.2f%% p90 %.2f%%  perfect_edge %+.2f%%  "
                    "selective %+.2f%%  gate_reachable=%s",
                    h, m["abs_ret_mean"] * 100, m["abs_ret_p90"] * 100,
                    m["perfect_direction_edge"] * 100, m["selective_top30_edge"] * 100,
                    m["gate_reachable_selective"],
                )
        result["groups"][gname] = {"n_symbols": len(series_map), "holds": holds}

    # 판정
    verdicts = {}
    for gname, g in result["groups"].items():
        reachable = [h for h, m in g["holds"].items() if m["gate_reachable_selective"]]
        perfect_only = [h for h, m in g["holds"].items()
                        if m["gate_reachable_perfect"] and not m["gate_reachable_selective"]]
        verdicts[gname] = {
            "selective_reachable_holds": reachable,
            "perfect_only_holds": perfect_only,
            "verdict": ("FEASIBLE" if reachable else
                        "MARGINAL" if perfect_only else "STRUCTURALLY_UNREACHABLE"),
        }
    result["verdicts"] = verdicts

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "r0__metrics.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    logger.info("판정: %s", json.dumps(verdicts, ensure_ascii=False))
    logger.info("저장: %s", out_path)
    print(json.dumps({"verdicts": verdicts, "out": str(out_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
