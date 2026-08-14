"""Paradigm 236 R-3 Robustness — Permutation Test + Regime Stratify + Fee Sweep.

Winner cell: thr=1.0, hold=3d, quadrant=B_focus (SHORT on z<=-1.0)
Top symbols from R-2: BTC, FIL, LTC (+ WF-stable: ADA, BCH, DOGE, ETH, SOL)

R-3 tests:
  1. Permutation test (n=200): shuffle imb_z within symbol, break temporal alignment
     - target perm_sigma >= 4.0 for elite gate
  2. Regime stratify: BTC trend (bull/bear via BTCUSDT 30d slope) x symbol
  3. Fee sensitivity: report edge at fee_bp = 4/8/12/16
  4. Temporal decay check: split window into thirds, verify alpha stability
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
log = logging.getLogger('p236_r3')

REPO = Path('/home/mint/auto_trading')
BOOK_DEPTH_DIR = REPO / 'backend/runs/book_depth'
OHLCV_DIR = REPO / 'backend/runs/ohlcv_cache'
OUT_DIR = REPO / 'backend/runs/research_track/alt_book_depth_imbalance_mean_rolling_z_bilateral_swing_1d_to_3d'

TOP_SYMS = ['BTC', 'FIL', 'LTC', 'ADA', 'BCH', 'DOGE', 'ETH', 'SOL']
ALL_SYMS = ['ADA', 'AVAX', 'BCH', 'BNB', 'BTC', 'DOGE', 'ETH', 'FIL', 'LINK', 'LTC', 'NEAR', 'SOL', 'WIF', 'XRP']

THR = 1.0
HOLD = 3
ROLLING_WIN = 30
FEE_BP_DEFAULT = 8.0
N_PERM = 200


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


def short_alpha(df: pd.DataFrame, fee_bp: float = FEE_BP_DEFAULT) -> Tuple[float, int]:
    mask = df['imb_z'] <= -THR
    rets = df.loc[mask, f'fwd_{HOLD}d'].values
    net = (-rets) * 10000.0 - fee_bp
    if len(net) == 0:
        return 0.0, 0
    return float(net.mean()), len(net)


def perm_test(df: pd.DataFrame, n_perm: int = N_PERM, fee_bp: float = FEE_BP_DEFAULT) -> Dict:
    real_alpha, real_n = short_alpha(df, fee_bp)
    if real_n < 10:
        return {'real_alpha_bp': real_alpha, 'real_n': real_n, 'perm_mean': None,
                'perm_std': None, 'perm_sigma': None, 'perm_p_gt': None}
    z_series = df['imb_z'].values.copy()
    perm_alphas = []
    rng = np.random.default_rng(42)
    for _ in range(n_perm):
        z_perm = z_series.copy()
        rng.shuffle(z_perm)
        df2 = df.copy()
        df2['imb_z'] = z_perm
        a, _ = short_alpha(df2, fee_bp)
        perm_alphas.append(a)
    perm_alphas = np.array(perm_alphas)
    pm = float(perm_alphas.mean())
    ps = float(perm_alphas.std(ddof=1))
    sigma = (real_alpha - pm) / ps if ps > 0 else 0.0
    p_gt = float((perm_alphas >= real_alpha).mean())
    return {
        'real_alpha_bp': round(real_alpha, 2),
        'real_n': int(real_n),
        'perm_mean_bp': round(pm, 2),
        'perm_std_bp': round(ps, 2),
        'perm_sigma': round(float(sigma), 3),
        'perm_p_gt': round(p_gt, 4),
    }


def temporal_thirds(df: pd.DataFrame, fee_bp: float = FEE_BP_DEFAULT) -> List[Dict]:
    df = df.sort_index()
    n = len(df)
    third = n // 3
    out = []
    for i, (label, s, e) in enumerate([('early', 0, third), ('mid', third, 2*third), ('late', 2*third, n)]):
        sub = df.iloc[s:e]
        a, k = short_alpha(sub, fee_bp)
        out.append({
            'window': label,
            'range': [str(sub.index[0]), str(sub.index[-1])],
            'n_trades': k, 'mean_bp': round(a, 2),
        })
    return out


def fee_sweep(df: pd.DataFrame) -> List[Dict]:
    out = []
    for f in [4.0, 8.0, 12.0, 16.0]:
        a, k = short_alpha(df, f)
        out.append({'fee_bp': f, 'n_trades': k, 'mean_bp': round(a, 2)})
    return out


def btc_trend_stratify(df: pd.DataFrame, btc_daily_close: pd.Series, fee_bp: float = FEE_BP_DEFAULT) -> Dict:
    btc_slope = btc_daily_close.pct_change(30)
    btc_bull = btc_slope > 0
    df2 = df.join(btc_bull.rename('btc_bull'), how='left').dropna()
    result = {}
    for regime, sel in [('bull', df2['btc_bull'] == True), ('bear', df2['btc_bull'] == False)]:
        sub = df2[sel]
        a, k = short_alpha(sub, fee_bp)
        result[regime] = {'n_trades': k, 'mean_bp': round(a, 2)}
    return result


def main():
    # Load BTC daily for regime
    btc = load_symbol('BTC')
    btc_close = btc['close']

    results = {}
    for sym in TOP_SYMS:
        log.info(f'processing {sym} ...')
        df = load_symbol(sym)
        r = {
            'perm_test': perm_test(df),
            'temporal_thirds': temporal_thirds(df),
            'fee_sweep': fee_sweep(df),
            'btc_regime': btc_trend_stratify(df, btc_close),
        }
        results[sym] = r
        pt = r['perm_test']
        log.info(f"  {sym}: real={pt['real_alpha_bp']}bp perm_sigma={pt['perm_sigma']} p={pt['perm_p_gt']}")

    # Elite gate summary
    n_perm_pass = sum(1 for sym, r in results.items()
                      if r['perm_test'].get('perm_sigma') is not None
                      and r['perm_test']['perm_sigma'] >= 4.0)
    n_perm_marginal = sum(1 for sym, r in results.items()
                          if r['perm_test'].get('perm_sigma') is not None
                          and r['perm_test']['perm_sigma'] >= 2.0)

    # Temporal decay diagnostic: how many syms show late < early meaningfully?
    decay_flag_count = 0
    decay_details = []
    for sym, r in results.items():
        thirds = r['temporal_thirds']
        early = thirds[0]['mean_bp']
        late = thirds[2]['mean_bp']
        decayed = (early > 0 and late < 0) or (early > 0 and late < early * 0.3)
        if decayed:
            decay_flag_count += 1
        decay_details.append({'sym': sym, 'early_bp': early, 'mid_bp': thirds[1]['mean_bp'], 'late_bp': late, 'decayed': decayed})

    log.info(f'perm_sigma >= 4.0 (elite): {n_perm_pass}/{len(results)}')
    log.info(f'perm_sigma >= 2.0 (marginal): {n_perm_marginal}/{len(results)}')
    log.info(f'temporal decay flagged: {decay_flag_count}/{len(results)}')

    # Verdict
    if n_perm_pass >= 2:
        verdict = 'PASS_TO_R4'
    elif n_perm_pass >= 1 and n_perm_marginal >= 4:
        verdict = 'MARGINAL_PROCEED_R4_CAUTIOUS'
    else:
        verdict = 'GRAVEYARD_R3_PERM_TEST_INSUFFICIENT'

    if decay_flag_count >= 4:
        verdict = 'GRAVEYARD_R3_TEMPORAL_ALPHA_DECAY'

    out = {
        'paradigm': 'alt_book_depth_imbalance_mean_rolling_z_bilateral_swing_1d_to_3d',
        'phase': 'R-3',
        'cell': {'threshold': THR, 'hold_days': HOLD, 'quadrant': 'B_focus_SHORT'},
        'per_symbol': results,
        'elite_gate_summary': {
            'n_perm_sigma_ge_4': n_perm_pass,
            'n_perm_sigma_ge_2': n_perm_marginal,
            'temporal_decay_flags': decay_flag_count,
            'decay_details': decay_details,
        },
        'verdict': verdict,
    }
    p = OUT_DIR / 'r3__metrics.json'
    p.write_text(json.dumps(out, indent=2, default=str))
    log.info(f'wrote {p}')
    log.info(f'VERDICT: {verdict}')


if __name__ == '__main__':
    main()
