"""
Crypto Meta-Learner 주간 retrain — KR retrain_meta_learner.py의 mirror.

env CRYPTO_META_RETRAIN_SYMBOL=BTCUSDT (default).
PM2 cron으로 매주 발화. atomic swap (write to .new, fsync, rename).

워크플로:
  1. 기존 perf_matrix를 base로 사용 (perf_matrix는 별도 cron에서 갱신 — 향후)
     v1: 매주 perf_matrix를 fully rebuild하지 않음 (compute 무거움).
         build_perf_matrix_crypto.py를 monthly로 별도 발화 권장.
  2. train_meta_learner로 새 모델 학습
  3. .new 파일에 저장 후 atomic rename
  4. 결과 로그
"""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from app.crypto_strategy_pool.meta_learner import (
    save_meta_learner, train_meta_learner, walk_forward_eval,
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=os.environ.get("CRYPTO_META_RETRAIN_SYMBOL", "BTCUSDT"))
    p.add_argument("--matrix", default=None,
                   help="default: runs/crypto_paper/sweeps/perf_matrix_<symbol>.jsonl")
    p.add_argument("--out", default=None,
                   help="default: runs/crypto_paper/models/meta_lgbm_<symbol>.pkl")
    args = p.parse_args()

    base = Path(__file__).resolve().parent
    sym = args.symbol
    matrix_path = base / (args.matrix or f"runs/crypto_paper/sweeps/perf_matrix_{sym}.jsonl")
    out_path = base / (args.out or f"runs/crypto_paper/models/meta_lgbm_{sym}.pkl")
    new_path = out_path.with_suffix(out_path.suffix + ".new")

    started = datetime.now()
    print(f"[{started.isoformat()}] Crypto meta retrain — symbol={sym}")
    print(f"  matrix : {matrix_path}")
    print(f"  out    : {out_path}")

    if not matrix_path.exists():
        raise SystemExit(f"perf_matrix not found: {matrix_path}")

    # walk-forward eval (informational)
    eval_res = walk_forward_eval(str(matrix_path), min_train=5)
    cum = eval_res["cumulative"]
    print(f"\n  WF eval: top1={eval_res['top1_accuracy']:.2%}  "
          f"meta_cum={cum['meta_top1']:+.2f}  BL_cum={cum['baseline_in_sample_best']:+.2f}")

    # train final model
    trained = train_meta_learner(str(matrix_path))
    save_meta_learner(trained, str(new_path))
    os.replace(new_path, out_path)  # atomic on POSIX
    print(f"\n  ATOMIC SWAP: {new_path} → {out_path}")
    print(f"  n_train={trained['n_train']}, strategies={len(trained['strategies'])}")
    print(f"  Done in {(datetime.now() - started).total_seconds():.1f}s")


if __name__ == "__main__":
    main()
