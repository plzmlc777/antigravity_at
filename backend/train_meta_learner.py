"""
Phase 4 acceptance: train meta-learner, run walk-forward eval, save model artifact.

  - Top-1 accuracy vs random (1/N)
  - Top-1 cumulative actual Sharpe vs (a) oracle, (b) in-sample best, (c) random
  - Feature importance per strategy
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from app.kr_strategy_pool.meta_learner import (
    save_meta_learner, train_meta_learner, walk_forward_eval,
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--matrix", default="runs/kr_paper/sweeps/perf_matrix_v1.jsonl")
    p.add_argument("--out", default="runs/kr_paper/models/meta_lgbm_v1.pkl")
    p.add_argument("--min-train", type=int, default=5)
    args = p.parse_args()

    base = Path(__file__).resolve().parent
    matrix_path = base / args.matrix
    out_path = base / args.out

    print(f"matrix : {matrix_path}")

    # 1. walk-forward eval
    eval_res = walk_forward_eval(str(matrix_path), min_train=args.min_train)
    cum = eval_res["cumulative"]
    n_strat = eval_res["n_strategies"]

    print(f"\n=== Walk-forward CV ({eval_res['n_steps']} steps, {n_strat} strategies) ===")
    print(f"top-1 accuracy        : {eval_res['top1_accuracy']:.2%}  (random baseline = {1/n_strat:.2%})")
    print(f"\ncumulative ACTUAL sharpe over predictions:")
    print(f"  meta-learner top-1   : {cum['meta_top1']:+.3f}")
    print(f"  oracle (best each)   : {cum['oracle_best_each_window']:+.3f}")
    print(f"  in-sample best (BL)  : {cum['baseline_in_sample_best']:+.3f}")
    print(f"  random pick          : {cum['random']:+.3f}")

    print(f"\n--- per-step picks ---")
    for p_ in eval_res["picks"]:
        print(f"  win {p_['window_id']:>2d}  pick={p_['pred_best']:<28}"
              f"  actual_sh={p_['actual_picked_sharpe']:+6.2f}"
              f"  oracle={p_['actual_best']:<28}"
              f"  baseline={p_['baseline_pick']:<28} sh={p_['baseline_sharpe']:+5.2f}")

    # acceptance check
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
        sym = "✔" if ok else "✘"
        print(f"  [{sym}] {label}")

    # 2. train final model on all rows + save
    trained = train_meta_learner(str(matrix_path))
    save_meta_learner(trained, str(out_path))
    print(f"\nSaved: {out_path}  (n_train={trained['n_train']})")

    # 3. feature importance summary
    print(f"\n=== Feature importance (gain, normalized, per strategy) ===")
    feat_names = trained["feature_names"]
    print(f"{'feature':<18} " + " ".join(f"{s[:8]:>9}" for s in trained["strategies"]))
    print("-" * (18 + 10 * len(trained["strategies"])))
    for f in feat_names:
        row = [f"{f:<18}"]
        for s in trained["strategies"]:
            v = trained["importances"][s][f]
            row.append(f"{v:>9.3f}")
        print(" ".join(row))


if __name__ == "__main__":
    main()
