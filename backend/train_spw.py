"""Train with scale_pos_weight for top symbols."""
import sys
sys.path.insert(0, "/home/ubuntu/auto_trading/backend")

from app.ml.trainer import TrendTrainer

symbols = ["LINKUSDT", "BTCUSDT", "SOLUSDT"]

for sym in symbols:
    print(f"\n{'='*60}")
    print(f"Training {sym} (1h, horizon=24, threshold=0, auto_weight=True)")
    print(f"{'='*60}")
    t = TrendTrainer(sym, timeframe="1h", horizon=24, threshold=0.0, auto_weight=True)
    r = t.train(days=90)
    if "metrics" in r:
        m = r["metrics"]
        print(f"  Accuracy:  {m['accuracy']}")
        print(f"  AUC:       {m['auc']}")
        print(f"  Precision: {m['precision']}")
        print(f"  Recall:    {m['recall']}")
        print(f"  F1:        {m['f1']}")
        print(f"  Pos Ratio: {m['positive_ratio']}")
        print(f"  Train/Test: {m['train_samples']}/{m['test_samples']}")
        print(f"  Best Iter: {m['best_iteration']}")
        if "top_features" in r:
            print(f"  Top 5 features:")
            for fname, fval in r["top_features"][:5]:
                print(f"    {fname}: {fval:.1f}")
    else:
        print(f"  ERROR: {r}")

print("\nDone!")
