"""env_encoder 검증 — Phase 2 acceptance criteria.

  1. encode_environment 호출이 1초 미만
  2. feature vector NaN/Inf 없음
  3. distribution snapshot 저장 → runs/kr_paper/sweeps/env_features_dist.json
"""
import json
import os
import sys
import time as _time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.kr_strategy_pool.data_utils import fetch_1m_feed
from app.kr_strategy_pool.env_encoder import (
    FEATURE_DIM, FEATURE_NAMES, encode_environment,
)


def main():
    feed = fetch_1m_feed(engine, "061090",
                         start_date="2025-11-14", end_date="2026-04-30")
    print(f"feed bars: {len(feed)}")

    # 매일 14:00 시점 1개씩 sampling → ~120 timepoints
    df = pd.DataFrame(feed)
    df["ts"] = pd.to_datetime(df["timestamp"])
    df["t"] = df["ts"].dt.strftime("%H:%M")
    df["d"] = df["ts"].dt.normalize()
    points = df[df["t"] == "14:00"]["timestamp"].tolist()
    print(f"sample timepoints: {len(points)}")

    # 1. timing
    t0 = _time.time()
    vectors = []
    for ts in points:
        v = encode_environment(feed, ts)
        vectors.append(v)
    elapsed_total = _time.time() - t0
    avg_ms = elapsed_total * 1000 / max(1, len(points))
    print(f"avg encode time: {avg_ms:.1f} ms (n={len(points)})")
    assert avg_ms < 1000, f"encode_environment > 1s: {avg_ms:.1f} ms"

    # 2. nan/inf
    arr = np.stack(vectors)
    assert arr.shape == (len(points), FEATURE_DIM), f"shape mismatch: {arr.shape}"
    assert np.isfinite(arr).all(), "vector contains NaN/Inf"
    print("all vectors finite ✔")

    # 3. distribution
    dist = {}
    for i, name in enumerate(FEATURE_NAMES):
        col = arr[:, i]
        dist[name] = {
            "mean": float(np.mean(col)),
            "std": float(np.std(col)),
            "min": float(np.min(col)),
            "max": float(np.max(col)),
            "p25": float(np.percentile(col, 25)),
            "p50": float(np.percentile(col, 50)),
            "p75": float(np.percentile(col, 75)),
        }

    out_dir = Path(__file__).resolve().parent / "runs" / "kr_paper" / "sweeps"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "env_features_dist.json"
    with open(out_path, "w") as f:
        json.dump({
            "n_samples": len(points),
            "feature_dim": FEATURE_DIM,
            "avg_encode_ms": avg_ms,
            "features": dist,
        }, f, indent=2, ensure_ascii=False)
    print(f"distribution saved to {out_path}")

    # short summary table
    print(f"\n{'feature':<18} {'mean':>9} {'std':>9} {'min':>9} {'max':>9}")
    print("-" * 60)
    for name, d in dist.items():
        print(f"{name:<18} {d['mean']:>+9.4f} {d['std']:>9.4f} {d['min']:>+9.4f} {d['max']:>+9.4f}")


if __name__ == "__main__":
    main()
