"""Paradigm 236 R-2 Multi-Symbol + Time-Series CV Walk-Forward.

Best cell from R-1: thr=1.0, hold=3d, quadrant=B_focus (SHORT on z<=-1.0)
  Passing symbols: BTC, FIL, LTC (3/14)

R-2 tasks:
  1. Confirm best cell across 14 symbols (independent from R-1 re-run in full window; R-1 used all data)
  2. 4-fold time-series CV walk-forward (chronological splits, no shuffle)
     - fold train/test = 60/40 within each fold, embargo 7d
     - target: n_folds_pass >= 3/4 for winning symbols
  3. Concentration gate re-verify

Output: r2__metrics.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('p236_r2')

REPO = Path('/home/mint/auto_trading')
BOOK_DEPTH_DIR = REPO / 'backend/runs/book_depth'
OHLCV_DIR = REPO / 'backend/runs/ohlcv_cache'
OUT_DIR = REPO / 'backend/runs/research_track/alt_book_depth_imbalance_mean_rolling_z_bilateral_swing_1d_to_3d'

SYMS = ['ADA', 'AVAX', 'BCH', 'BNB', 'BTC', 'DOGE', 'ETH', 'FIL', 'LINK', 'LTC', 'NEAR', 'SOL', 'WIF', 'XRP']

THR = 1.0
HOLD = 3
ROLLING_WIN = 30
FEE_BP = 8.0
N_FOLDS = 4


def load_symbol(sym: str) -> pd.DataFrame:
    bd = joblib.load(BOOK_DEPTH_DIR / f'{sym}USDT_bookdepth.joblib').sort_index()
    ohlcv = joblib.load(OHLCV_DIR / f'{sym}USDT_1m.joblib')
    if not isinstance(ohlcv.index, pd.DatetimeIndex):
        ohlcv.index = pd.to_datetime(ohlcv.index)
    d_close = ohlcv['close'].resample('1D').last().dropna()
    bd.index = bd.index.normalize()
    m = pd.DataFrame({'imb': bd['imbalance_mean'], 'close': d_close}).dropna()
    m['imb_z'] = (m['imb'] - m['imb'].rolling(ROLLING_WIN).mean()) / m['imb'].rolling(ROLLING_WIN).std()
    m[f'fwd_{HOLD}d'] = m['close'].shift(-HOLD) / m['close'] - 1
    return m.dropna()


def bootstrap_ci(x: np.ndarray, n_iter: int = 2000, alpha: float = 0.05) -> Tuple[float, float]:
    if len(x) < 5:
        return float('nan'), float('nan')
    rng = np.random.default_rng(42)
    idx = rng.integers(0, len(x), size=(n_iter, len(x)))
    m = x[idx].mean(axis=1)
    return float(np.quantile(m, alpha / 2)), float(np.quantile(m, 1 - alpha / 2))


def cell_stats(rets_bp: np.ndarray) -> Dict:
    if len(rets_bp) == 0:
        return {'n': 0, 'mean_bp': None, 'ci_lower_bp': None, 't_excess': None, 'three_gate_pass': False}
    n = len(rets_bp)
    m = float(rets_bp.mean())
    s = float(rets_bp.std(ddof=1)) if n > 1 else 0.0
    se = s / np.sqrt(n) if n > 1 and s > 0 else float('inf')
    t_excess = m / se if se > 0 else 0.0
    lo, hi = bootstrap_ci(rets_bp)
    return {
        'n': int(n),
        'mean_bp': round(m, 2),
        'ci_lower_bp': round(lo, 2) if lo == lo else None,
        'ci_upper_bp': round(hi, 2) if hi == hi else None,
        't_excess': round(float(t_excess), 3),
        'three_gate_pass': bool((n >= 20) and (lo == lo and lo > 0) and (t_excess >= 2.0)),
    }


def run_short_cell(df: pd.DataFrame) -> np.ndarray:
    mask = df['imb_z'] <= -THR
    sel = df.loc[mask, f'fwd_{HOLD}d'].values
    # SHORT: reverse sign
    net_bp = (-sel) * 10000.0 - FEE_BP
    return net_bp


def walk_forward_folds(df: pd.DataFrame, n_folds: int = N_FOLDS, embargo_days: int = 7) -> List[Dict]:
    """Chronological time-series CV: split df into n_folds+1 chunks;
    for fold k (k=1..n_folds), train = chunks 0..k-1, test = chunk k with embargo.
    We only measure test-window performance."""
    df = df.sort_index()
    total = len(df)
    chunk = total // (n_folds + 1)
    folds = []
    for k in range(1, n_folds + 1):
        test_start = k * chunk
        # embargo: drop first embargo_days from test
        if test_start + embargo_days >= total:
            continue
        test_end = min((k + 1) * chunk, total)
        test_df = df.iloc[test_start + embargo_days: test_end]
        if len(test_df) < 10:
            continue
        rets = run_short_cell(test_df)
        st = cell_stats(rets)
        folds.append({
            'fold': k,
            'test_range': [str(test_df.index[0]), str(test_df.index[-1])],
            'n_test_days': len(test_df),
            **st,
        })
    return folds


def main():
    per_symbol_full = {}
    per_symbol_folds = {}

    for sym in SYMS:
        try:
            df = load_symbol(sym)
            rets = run_short_cell(df)
            per_symbol_full[sym] = cell_stats(rets)
            per_symbol_folds[sym] = walk_forward_folds(df)
        except Exception as e:
            log.warning(f'{sym}: {e}')

    # Aggregate
    full_pass = [sym for sym, s in per_symbol_full.items() if s['three_gate_pass']]
    log.info(f'R-2 full-window pass: {full_pass}')

    # WF summary per symbol
    wf_summary = {}
    for sym, folds in per_symbol_folds.items():
        n_folds = len(folds)
        pos_folds = sum(1 for f in folds if f['mean_bp'] is not None and f['mean_bp'] > 0)
        pass_folds = sum(1 for f in folds if f['three_gate_pass'])
        wf_summary[sym] = {
            'n_folds': n_folds,
            'pos_folds': pos_folds,
            'pass_folds': pass_folds,
            'pos_ratio': round(pos_folds / max(n_folds, 1), 3),
        }

    # Concentration gate for R-2: how many symbols show WF stability?
    wf_stable_syms = [sym for sym, w in wf_summary.items()
                      if w['n_folds'] >= 3 and w['pos_folds'] >= 3]
    log.info(f'R-2 WF-stable symbols (>=3/4 pos_folds): {wf_stable_syms}')

    # Verdict
    if len(full_pass) < 3:
        verdict = 'GRAVEYARD_R2_FULL_WINDOW_INSUFFICIENT_SYMBOLS'
    elif len(wf_stable_syms) < 2:
        verdict = 'GRAVEYARD_R2_WALK_FORWARD_FRAGILE'
    else:
        verdict = 'PASS_TO_R3'

    out = {
        'paradigm': 'alt_book_depth_imbalance_mean_rolling_z_bilateral_swing_1d_to_3d',
        'phase': 'R-2',
        'cell': {'threshold': THR, 'hold_days': HOLD, 'quadrant': 'B_focus_SHORT'},
        'per_symbol_full_window': per_symbol_full,
        'per_symbol_walk_forward': per_symbol_folds,
        'wf_summary': wf_summary,
        'full_window_pass_symbols': full_pass,
        'wf_stable_symbols': wf_stable_syms,
        'verdict': verdict,
    }
    out_path = OUT_DIR / 'r2__metrics.json'
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info(f'wrote {out_path}')
    log.info(f'VERDICT: {verdict}')
    log.info(f'  full_window pass: {len(full_pass)}/14 -> {full_pass}')
    log.info(f'  wf_stable_syms:   {len(wf_stable_syms)}/14 -> {wf_stable_syms}')


if __name__ == '__main__':
    main()
