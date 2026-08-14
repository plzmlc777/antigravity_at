"""Paradigm 236 R-1 PoC.

Hypothesis: per-symbol Binance Futures perp daily book-depth imbalance_mean
rolling 30d z-score is a bilateral swing predictor.
  - z > +threshold => LONG (next 1..3d)
  - z < -threshold => SHORT (next 1..3d)

Lesson compliance:
  - #11 sample density: extrapolate n per (sym, dir, cell)
  - #37 full sweep: 3 thresholds x 3 holds x 4 quadrants
  - #39 sub-class A/B mirror pathology: report A_focus + A_mirror sum
  - #40 structural feasibility: bounded imbalance -> z<=|1.5| achievable
  - #79 OOS pretest already run (14/14 pass)

Data:
  - book_depth: runs/book_depth/{SYM}USDT_bookdepth.joblib
  - forward returns: runs/ohlcv_cache/{SYM}USDT_1m.joblib -> daily close

Universe: 14 perp symbols
Fee: 8bp round-trip

Output: runs/research_track/alt_book_depth_imbalance_mean_rolling_z_bilateral_swing_1d_to_3d/r1__metrics.json
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
log = logging.getLogger('p236_r1')

REPO = Path('/home/mint/auto_trading')
BOOK_DEPTH_DIR = REPO / 'backend/runs/book_depth'
OHLCV_DIR = REPO / 'backend/runs/ohlcv_cache'
OUT_DIR = REPO / 'backend/runs/research_track/alt_book_depth_imbalance_mean_rolling_z_bilateral_swing_1d_to_3d'
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMS = ['ADA', 'AVAX', 'BCH', 'BNB', 'BTC', 'DOGE', 'ETH', 'FIL', 'LINK', 'LTC', 'NEAR', 'SOL', 'WIF', 'XRP']
Z_THRESHOLDS = [1.0, 1.5, 2.0]
HOLDS = [1, 2, 3]
ROLLING_WIN = 30
FEE_BP = 8.0  # round-trip


def load_symbol(sym: str) -> pd.DataFrame:
    bd = joblib.load(BOOK_DEPTH_DIR / f'{sym}USDT_bookdepth.joblib').sort_index()
    ohlcv = joblib.load(OHLCV_DIR / f'{sym}USDT_1m.joblib')
    if not isinstance(ohlcv.index, pd.DatetimeIndex):
        ohlcv.index = pd.to_datetime(ohlcv.index)
    d_close = ohlcv['close'].resample('1D').last().dropna()
    bd.index = bd.index.normalize()
    m = pd.DataFrame({'imb': bd['imbalance_mean'], 'close': d_close}).dropna()
    m['imb_z'] = (m['imb'] - m['imb'].rolling(ROLLING_WIN).mean()) / m['imb'].rolling(ROLLING_WIN).std()
    for h in HOLDS:
        m[f'fwd_{h}d'] = m['close'].shift(-h) / m['close'] - 1
    return m.dropna()


def bootstrap_ci(x: np.ndarray, n_iter: int = 2000, alpha: float = 0.05) -> Tuple[float, float]:
    """Return (ci_lower, ci_upper) of the mean."""
    if len(x) < 5:
        return float('nan'), float('nan')
    rng = np.random.default_rng(42)
    idx = rng.integers(0, len(x), size=(n_iter, len(x)))
    means = x[idx].mean(axis=1)
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def cell_stats(rets_net_bp: np.ndarray) -> Dict:
    if len(rets_net_bp) == 0:
        return {'n': 0, 'mean_net_bp': None, 'ci_lower_bp': None, 'ci_upper_bp': None,
                't_excess': None, 'three_gate_pass': False}
    mean_bp = float(rets_net_bp.mean())
    n = len(rets_net_bp)
    std_bp = float(rets_net_bp.std(ddof=1)) if n > 1 else 0.0
    se_bp = std_bp / np.sqrt(n) if n > 1 else float('inf')
    t_excess = mean_bp / se_bp if se_bp > 0 else 0.0
    lo, hi = bootstrap_ci(rets_net_bp)
    three = (n >= 20) and (lo is not None and lo > 0) and (t_excess >= 2.0)
    return {
        'n': int(n),
        'mean_net_bp': round(mean_bp, 2),
        'ci_lower_bp': round(lo, 2) if lo == lo else None,
        'ci_upper_bp': round(hi, 2) if hi == hi else None,
        't_excess': round(float(t_excess), 3),
        'three_gate_pass': bool(three),
    }


def run_cell(df: pd.DataFrame, thr: float, hold: int, quadrant: str) -> Dict:
    """quadrant: A_focus = long on z>=+thr; A_mirror = long on z<=-thr;
    B_focus = short on z<=-thr; B_mirror = short on z>=+thr."""
    z = df['imb_z']
    fwd = df[f'fwd_{hold}d']
    if quadrant == 'A_focus':
        mask = z >= thr
        direction = +1
    elif quadrant == 'A_mirror':
        mask = z <= -thr
        direction = +1
    elif quadrant == 'B_focus':
        mask = z <= -thr
        direction = -1
    elif quadrant == 'B_mirror':
        mask = z >= thr
        direction = -1
    else:
        raise ValueError(quadrant)
    sel = fwd[mask].values * direction
    net_bp = sel * 10000.0 - FEE_BP
    stats = cell_stats(net_bp)
    stats['quadrant'] = quadrant
    stats['threshold'] = thr
    stats['hold'] = hold
    return stats


def main():
    all_data = {}
    for sym in SYMS:
        try:
            all_data[sym] = load_symbol(sym)
            log.info(f'{sym}: {len(all_data[sym])} rows after warmup+fwd')
        except Exception as e:
            log.warning(f'{sym} skipped: {e}')

    # For each cell, compute per-symbol stats + aggregate
    per_symbol_cells: Dict[str, List[Dict]] = {}
    for sym, df in all_data.items():
        per_symbol_cells[sym] = []
        for thr in Z_THRESHOLDS:
            for h in HOLDS:
                for q in ['A_focus', 'A_mirror', 'B_focus', 'B_mirror']:
                    s = run_cell(df, thr, h, q)
                    per_symbol_cells[sym].append(s)

    # Aggregate across symbols per (thr, hold, quadrant)
    aggregate = []
    for thr in Z_THRESHOLDS:
        for h in HOLDS:
            for q in ['A_focus', 'A_mirror', 'B_focus', 'B_mirror']:
                cell_rows = []
                for sym in per_symbol_cells:
                    for s in per_symbol_cells[sym]:
                        if s['threshold'] == thr and s['hold'] == h and s['quadrant'] == q:
                            cell_rows.append((sym, s))
                total_n = sum(s['n'] for _, s in cell_rows)
                n_pass = sum(1 for _, s in cell_rows if s['three_gate_pass'])
                mean_of_means = np.mean([s['mean_net_bp'] for _, s in cell_rows if s['mean_net_bp'] is not None]) if cell_rows else None
                aggregate.append({
                    'threshold': thr,
                    'hold': h,
                    'quadrant': q,
                    'total_events': int(total_n),
                    'n_symbols_pass_three_gate': int(n_pass),
                    'mean_of_symbol_means_bp': round(float(mean_of_means), 2) if mean_of_means is not None else None,
                    'per_symbol': [{'sym': sym, **s} for sym, s in cell_rows],
                })

    # Lesson #39 sub-class A signature: A_focus + A_mirror sum per (thr, hold, sym)
    lesson39_report = []
    for thr in Z_THRESHOLDS:
        for h in HOLDS:
            for sym in per_symbol_cells:
                af = next((s for s in per_symbol_cells[sym] if s['threshold'] == thr and s['hold'] == h and s['quadrant'] == 'A_focus'), None)
                am = next((s for s in per_symbol_cells[sym] if s['threshold'] == thr and s['hold'] == h and s['quadrant'] == 'A_mirror'), None)
                if af and am and af['mean_net_bp'] is not None and am['mean_net_bp'] is not None:
                    s_sum = af['mean_net_bp'] + am['mean_net_bp']
                    # Sub-class A: sum ~ -2*FEE_BP (i.e. -16) => pure fee drag
                    sub_A = abs(s_sum + 2 * FEE_BP) < 3.0
                    lesson39_report.append({
                        'sym': sym, 'threshold': thr, 'hold': h,
                        'A_focus_bp': af['mean_net_bp'], 'A_mirror_bp': am['mean_net_bp'],
                        'sum_bp': round(s_sum, 2), 'sub_class_A_signature': bool(sub_A),
                    })

    subA_count = sum(1 for r in lesson39_report if r['sub_class_A_signature'])
    subA_pct = subA_count / max(len(lesson39_report), 1)

    # Best cell scan (Lesson #37): find any cell with n_symbols_pass_three_gate >= 3
    best_cells = [c for c in aggregate if c['n_symbols_pass_three_gate'] >= 3]
    best_cells.sort(key=lambda c: (-c['n_symbols_pass_three_gate'], -(c['mean_of_symbol_means_bp'] or -999)))

    # Overall verdict
    verdict_dict = {
        'best_cells_count': len(best_cells),
        'top_5_best_cells': best_cells[:5],
        'lesson_39_subA_pct': round(subA_pct, 3),
        'lesson_39_subA_count': subA_count,
        'lesson_39_total_pairs': len(lesson39_report),
    }

    if len(best_cells) == 0:
        verdict = 'GRAVEYARD_R1_NO_CELL_PASSES_THREE_GATE'
    elif subA_pct > 0.7:
        verdict = 'GRAVEYARD_R1_LESSON_39_SUB_A_MIRROR_PATHOLOGY'
    else:
        verdict = 'PASS_TO_R2'

    out = {
        'paradigm': 'alt_book_depth_imbalance_mean_rolling_z_bilateral_swing_1d_to_3d',
        'phase': 'R-1',
        'universe': SYMS,
        'z_thresholds': Z_THRESHOLDS,
        'holds_days': HOLDS,
        'fee_bp_round_trip': FEE_BP,
        'rolling_window_days': ROLLING_WIN,
        'aggregate_cells': aggregate,
        'lesson_39_pairs': lesson39_report,
        'verdict': verdict,
        'verdict_dict': verdict_dict,
    }
    out_path = OUT_DIR / 'r1__metrics.json'
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info(f'wrote {out_path}')
    log.info(f'verdict = {verdict}')
    log.info(f'best_cells (n_pass>=3): {len(best_cells)}')
    for c in best_cells[:5]:
        log.info(f'  thr={c["threshold"]} hold={c["hold"]}d quad={c["quadrant"]} '
                 f'n_pass={c["n_symbols_pass_three_gate"]} mean_bp={c["mean_of_symbol_means_bp"]}')
    log.info(f'Lesson #39 sub-class A pathology: {subA_count}/{len(lesson39_report)} '
             f'pairs ({subA_pct*100:.1f}%)')


if __name__ == '__main__':
    main()
