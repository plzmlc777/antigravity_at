"""
Meta-Learner — Phase 4 of Meta-Strategy MoE plan.

Trains one LightGBM regressor per strategy from the walk-forward perf_matrix.
Inputs are env_vectors (Phase 2), targets are next-window Sharpe of each strategy
(Phase 3, forward-shifted).

Provides:
  - train_meta_learner(perf_matrix_path) -> dict of fitted models + metadata
  - predict_top_strategy(models, env_vec) -> (best_name, predicted_sharpe, ranked)

Designed for the very small data regime (~15 (X,Y) pairs):
  - LightGBM with shallow trees, few leaves, low n_estimators
  - early stop disabled (no holdout big enough)
  - feature gain importance saved per strategy
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

import lightgbm as lgb

from .env_encoder import FEATURE_NAMES


def _load_matrix(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r["window_id"])
    return rows


def _build_xy(
    rows: List[Dict[str, Any]],
    no_trade_min: int = 3,
    no_trade_penalty: float = -1.0,
) -> Tuple[np.ndarray, Dict[str, np.ndarray], List[int]]:
    """Forward-shift: X[k] = env at window k, Y[k] = sharpe at window k+1.

    Strategies with trades < no_trade_min in the target window get their Y
    replaced with no_trade_penalty. Without this, sharpe=0 for trade-sparse
    strategies looks safer than truly bad ones (e.g. -1) and the model learns
    to recommend "do nothing", which is worse than the safety gate's cash-hold
    on truly poor predictions.
    """
    if len(rows) < 2:
        raise ValueError("need >=2 windows to forward-shift")
    X = np.array([r["env"] for r in rows[:-1]], dtype=float)
    strategies = sorted(rows[0]["strategies"].keys())
    Y: Dict[str, np.ndarray] = {}
    for s in strategies:
        ys = []
        for k in range(len(rows) - 1):
            ent = rows[k + 1]["strategies"].get(s, {})
            sharpe = ent.get("sharpe", 0.0) or 0.0
            trades = int(ent.get("trades", 0) or 0)
            if trades < no_trade_min:
                sharpe = no_trade_penalty
            ys.append(sharpe)
        Y[s] = np.array(ys, dtype=float)
    window_ids = [r["window_id"] for r in rows[:-1]]
    return X, Y, window_ids


def _fit_model(X: np.ndarray, y: np.ndarray) -> lgb.LGBMRegressor:
    model = lgb.LGBMRegressor(
        n_estimators=30,
        max_depth=3,
        num_leaves=7,
        learning_rate=0.08,
        min_child_samples=2,
        reg_alpha=0.1,
        reg_lambda=0.1,
        verbose=-1,
        force_row_wise=True,
    )
    model.fit(X, y)
    return model


def train_meta_learner(perf_matrix_path: str) -> Dict[str, Any]:
    """Train one regressor per strategy on the entire matrix (no holdout).

    Returns dict with keys: models, strategies, feature_names, n_train.
    Persist via save_meta_learner.
    """
    rows = _load_matrix(Path(perf_matrix_path))
    X, Y, _ = _build_xy(rows)
    models = {s: _fit_model(X, Y[s]) for s in Y}

    importances = {}
    for s, m in models.items():
        # gain importance, normalized
        gain = m.booster_.feature_importance(importance_type="gain")
        total = float(gain.sum()) or 1.0
        importances[s] = {FEATURE_NAMES[i]: float(gain[i] / total)
                          for i in range(len(FEATURE_NAMES))}

    return {
        "models": models,
        "strategies": list(models.keys()),
        "feature_names": FEATURE_NAMES,
        "n_train": int(len(X)),
        "importances": importances,
    }


def walk_forward_eval(perf_matrix_path: str, min_train: int = 5) -> Dict[str, Any]:
    """Walk-forward CV: at step t (t >= min_train), train on rows [0..t-1],
    predict for row t (env -> sharpe of next window), choose top-1 strategy.

    Returns:
      - top1_picks: list of (window_id, predicted_best, actual_best, picked_sharpe, baseline_sharpe)
      - cumulative_picked_sharpe, cumulative_best_pool_sharpe, cumulative_random
    """
    rows = _load_matrix(Path(perf_matrix_path))
    X, Y, window_ids = _build_xy(rows)
    strategies = sorted(Y.keys())

    picks = []
    rng = np.random.default_rng(seed=0)

    for t in range(min_train, len(X)):
        # train on [0..t-1], predict for X[t]
        models_t = {}
        for s in strategies:
            models_t[s] = _fit_model(X[:t], Y[s][:t])

        # predict
        preds = {s: float(models_t[s].predict(X[t : t + 1])[0]) for s in strategies}
        actual = {s: float(Y[s][t]) for s in strategies}

        pred_best = max(preds.items(), key=lambda x: x[1])[0]
        actual_best = max(actual.items(), key=lambda x: x[1])[0]

        # baseline: use the best in-sample strategy (max mean Y over training rows)
        in_sample_means = {s: float(np.mean(Y[s][:t])) for s in strategies}
        baseline_pick = max(in_sample_means.items(), key=lambda x: x[1])[0]
        random_pick = strategies[int(rng.integers(0, len(strategies)))]

        picks.append({
            "window_id": int(window_ids[t]),
            "pred_best": pred_best,
            "pred_sharpe": preds[pred_best],
            "actual_picked_sharpe": actual[pred_best],
            "actual_best": actual_best,
            "actual_best_sharpe": actual[actual_best],
            "baseline_pick": baseline_pick,
            "baseline_sharpe": actual[baseline_pick],
            "random_pick": random_pick,
            "random_sharpe": actual[random_pick],
        })

    if not picks:
        return {"picks": [], "cumulative": {}, "accuracy": 0.0}

    cum_picked = float(sum(p["actual_picked_sharpe"] for p in picks))
    cum_best = float(sum(p["actual_best_sharpe"] for p in picks))
    cum_baseline = float(sum(p["baseline_sharpe"] for p in picks))
    cum_random = float(sum(p["random_sharpe"] for p in picks))

    correct = sum(1 for p in picks if p["pred_best"] == p["actual_best"])
    top_n_correct = lambda n: sum(
        1 for p in picks
        if p["pred_best"] in [
            s for s, _ in sorted(
                {s: float(Y[s][_idx]) for s in strategies}.items(),
                key=lambda x: -x[1],
            )[:n]
        ]
        for _idx in [next(i for i, w in enumerate(window_ids) if w == p["window_id"])]
    )

    return {
        "picks": picks,
        "cumulative": {
            "meta_top1": cum_picked,
            "oracle_best_each_window": cum_best,
            "baseline_in_sample_best": cum_baseline,
            "random": cum_random,
        },
        "top1_accuracy": correct / max(1, len(picks)),
        "n_steps": len(picks),
        "n_strategies": len(strategies),
    }


def save_meta_learner(trained: Dict[str, Any], path: str) -> None:
    out = {k: v for k, v in trained.items() if k != "models"}
    out["models_pickle"] = {s: pickle.dumps(m) for s, m in trained["models"].items()}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(out, f)


def load_meta_learner(path: str) -> Dict[str, Any]:
    with open(path, "rb") as f:
        raw = pickle.load(f)
    raw["models"] = {s: pickle.loads(b) for s, b in raw.pop("models_pickle").items()}
    return raw


def predict_top_strategy(
    trained: Dict[str, Any], env_vec: np.ndarray, top_k: int = 1,
) -> List[Tuple[str, float]]:
    preds = {
        s: float(m.predict(env_vec.reshape(1, -1))[0])
        for s, m in trained["models"].items()
    }
    ranked = sorted(preds.items(), key=lambda x: -x[1])
    return ranked[:top_k]
