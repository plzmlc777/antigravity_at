"""
Weekly meta-learner retrain — atomic hot-swap.

  1. rebuild perf_matrix from latest data
  2. retrain LightGBM models
  3. atomic rename onto canonical model path

Usage (PM2 cron, weekly):
    python3 retrain_meta_learner.py
"""
import argparse
import asyncio
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from app.kr_strategy_pool.meta_learner import (
    save_meta_learner, train_meta_learner, walk_forward_eval,
)


async def rebuild_matrix(symbol: str, end_date: str, window_days: int,
                         warmup_days: int, out_path: Path) -> None:
    # Reuse build_perf_matrix's main() — invoke as subprocess to keep this module pure
    import subprocess
    backend_root = Path(__file__).resolve().parent
    cmd = [
        sys.executable, str(backend_root / "build_perf_matrix.py"),
        "--symbol", symbol,
        "--end", end_date,
        "--window-days", str(window_days),
        "--warmup-days", str(warmup_days),
        "--out", out_path.name,
    ]
    print(f"[retrain] rebuilding matrix → {out_path}")
    proc = subprocess.run(cmd, cwd=backend_root, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise RuntimeError(f"build_perf_matrix failed: rc={proc.returncode}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="061090")
    p.add_argument("--end-date", default=str(date.today()))
    p.add_argument("--window-days", type=int, default=3)
    p.add_argument("--warmup-days", type=int, default=30)
    p.add_argument("--matrix-out", default="perf_matrix_latest.jsonl")
    p.add_argument("--model-out", default="runs/kr_paper/models/meta_lgbm_latest.pkl")
    p.add_argument("--canonical", default="runs/kr_paper/models/meta_lgbm.pkl",
                   help="atomic-replace target path used by live cycle")
    args = p.parse_args()

    backend_root = Path(__file__).resolve().parent
    sweeps = backend_root / "runs" / "kr_paper" / "sweeps"
    matrix_path = sweeps / args.matrix_out
    asyncio.run(rebuild_matrix(args.symbol, args.end_date, args.window_days,
                               args.warmup_days, matrix_path))

    # walk-forward sanity check before swap
    eval_res = walk_forward_eval(str(matrix_path), min_train=10)
    print(f"[retrain] walk-forward: top1_acc={eval_res['top1_accuracy']:.2%}  "
          f"meta_cum={eval_res['cumulative']['meta_top1']:+.3f}  "
          f"baseline={eval_res['cumulative']['baseline_in_sample_best']:+.3f}")

    if eval_res["top1_accuracy"] <= 1.0 / max(1, eval_res["n_strategies"]):
        print(f"[retrain] FAIL: top1_acc not better than random — abort hot-swap")
        sys.exit(2)

    trained = train_meta_learner(str(matrix_path))
    model_out = backend_root / args.model_out
    save_meta_learner(trained, str(model_out))
    print(f"[retrain] saved fresh model → {model_out} (n_train={trained['n_train']})")

    canonical = backend_root / args.canonical
    canonical.parent.mkdir(parents=True, exist_ok=True)
    # atomic replace via os.replace (POSIX rename)
    tmp = canonical.with_suffix(canonical.suffix + ".tmp")
    shutil.copyfile(model_out, tmp)
    os.replace(tmp, canonical)
    print(f"[retrain] hot-swapped → {canonical}")


if __name__ == "__main__":
    main()
