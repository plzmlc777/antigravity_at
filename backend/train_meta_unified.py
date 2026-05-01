"""
Phase A: Train unified meta-learner — KR/Crypto 양쪽 모두 동일 architecture.

Usage:
    PYTHONPATH=. python3 train_meta_unified.py \\
        --matrix runs/<market>_paper/sweeps/perf_matrix_<sym>_unified.jsonl \\
        --out runs/<market>_paper/models/meta_lgbm_<sym>_unified.pkl
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from app.meta_strategy_pool.meta_learner import (
    save_meta_learner, train_meta_learner, walk_forward_eval,
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--matrix", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--min-train", type=int, default=5)
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    base = Path(__file__).resolve().parent
    matrix_path = base / args.matrix
    out_path = base / args.out

    if not args.quiet:
        print(f"matrix : {matrix_path}")

    eval_res = walk_forward_eval(str(matrix_path), min_train=args.min_train)
    cum = eval_res["cumulative"]
    n_strat = eval_res["n_strategies"]

    print(f"=== Walk-forward CV ({eval_res['n_steps']} steps, {n_strat} strategies) ===")
    print(f"top-1 accuracy        : {eval_res['top1_accuracy']:.2%}  (random baseline = {1/n_strat:.2%})")
    print(f"cumulative ACTUAL sharpe over predictions:")
    print(f"  meta-learner top-1   : {cum['meta_top1']:+.3f}")
    print(f"  oracle (best each)   : {cum['oracle_best_each_window']:+.3f}")
    print(f"  in-sample best (BL)  : {cum['baseline_in_sample_best']:+.3f}")
    print(f"  random pick          : {cum['random']:+.3f}")
    print(f"  meta - BL            : {cum['meta_top1'] - cum['baseline_in_sample_best']:+.3f}")

    print(f"\n=== Acceptance ===")
    accept = []
    if eval_res["top1_accuracy"] > 1.0 / n_strat:
        accept.append(("top1_accuracy > random", True))
    else:
        accept.append(("top1_accuracy > random", False))
    if cum["meta_top1"] > cum["baseline_in_sample_best"]:
        accept.append(("meta cumulative > in-sample-best baseline", True))
    else:
        accept.append(("meta cumulative > in-sample-best baseline", False))
    for label, ok in accept:
        sym = "PASS" if ok else "FAIL"
        print(f"  [{sym}] {label}")

    trained = train_meta_learner(str(matrix_path))
    save_meta_learner(trained, str(out_path))
    print(f"\nSaved: {out_path}  (n_train={trained['n_train']})")

    if not args.quiet:
        print(f"\n=== Feature importance (gain, normalized, per strategy) ===")
        feat_names = trained["feature_names"]
        print(f"{'feature':<24} " + " ".join(f"{s[:8]:>9}" for s in trained["strategies"]))
        print("-" * (24 + 10 * len(trained["strategies"])))
        for f in feat_names:
            row = [f"{f:<24}"]
            for s in trained["strategies"]:
                v = trained["importances"][s][f]
                row.append(f"{v:>9.3f}")
            print(" ".join(row))


if __name__ == "__main__":
    main()
