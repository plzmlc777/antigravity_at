"""
paradigm 206 R-1 PoC

Hypothesis: BTC 90d daily-return KS 2-sample statistic (recent 45d vs prior 45d) → 180d rolling z-score
→ |z|>=2 spike trigger × BTC heavier-tail sign × 20 alt forward return at +1d/+2d/+3d × 4-quadrant SNT.

Lesson #39 sub-class A explicit avoidance: cell A and cell B disjoint trigger sets
(recent_heavier vs recent_lighter mutually exclusive sign partition).

Item 6 (alpha decay informational learning audit) + Item 7 (SNT structural integrity) per Lesson #69 7-item template.
"""
import logging
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
import json
import sys

sys.path.insert(0, str(Path(__file__).parent))
from _perm_utils import fee_aware_perm_test, bootstrap_ci

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

PARADIGM_SLUG = "alt_btc_lead_lag_90d_ks_2sample_distribution_shift_cross_asset_cascade_directional_4h_bilateral"
CACHE_DIR = Path("backend/runs/ohlcv_cache_12col")
OUT_DIR = Path(f"backend/runs/research_track/{PARADIGM_SLUG}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE = [
    "ADA", "AVAX", "BCH", "BNB", "DOGE", "DOT", "ETC", "ETH", "FIL", "JUP",
    "LDO", "LINK", "LTC", "NEAR", "PYTH", "SOL", "UNI", "WIF", "WLD", "XRP"
]
FEE_BPS = 8.0
FEE_DECIMAL_RT = 0.0016  # round-trip 16bp decimal
HOLDS = [1, 2, 3]
KS_WINDOW = 45
ZSCORE_WINDOW = 180
Z_THRESHOLD = 2.0
N_PERM = 2000
N_BOOT = 2000


def compute_btc_ks_trigger():
    btc = joblib.load(CACHE_DIR / "BTCUSDT_4h.joblib")
    btc_daily = btc['close'].resample('1D').last().dropna()
    btc_ret = btc_daily.pct_change().dropna()

    ks_stats, recent_heavier, dates = [], [], []
    for i in range(2 * KS_WINDOW, len(btc_ret)):
        prior = btc_ret.iloc[i - 2 * KS_WINDOW:i - KS_WINDOW].values
        recent = btc_ret.iloc[i - KS_WINDOW:i].values
        ks_stat, _ = ks_2samp(recent, prior)
        ks_stats.append(ks_stat)
        recent_heavier.append(1 if np.std(recent) > np.std(prior) else -1)
        dates.append(btc_ret.index[i])

    ks_series = pd.Series(ks_stats, index=dates)
    sign_series = pd.Series(recent_heavier, index=dates)
    ks_z = (ks_series - ks_series.rolling(ZSCORE_WINDOW).mean()) / ks_series.rolling(ZSCORE_WINDOW).std()
    ks_z = ks_z.dropna()
    sign_series = sign_series.reindex(ks_z.index)

    trigger_mask = ks_z >= Z_THRESHOLD
    trigger_dates = ks_z.index[trigger_mask]
    cell_A = trigger_dates[(sign_series.reindex(trigger_dates) == +1).values]
    cell_B = trigger_dates[(sign_series.reindex(trigger_dates) == -1).values]

    log.info(f"Trigger |z|>={Z_THRESHOLD}: {len(trigger_dates)} dates, cell_A={len(cell_A)}, cell_B={len(cell_B)}")
    log.info(f"Disjoint A ∩ B = {len(set(cell_A) & set(cell_B))}")
    return cell_A, cell_B, ks_z, sign_series


def build_candidate_pool(hold_days):
    """Build pool of ALL candidate +hold_days gross returns across the 20-alt panel."""
    pool = []
    for sym in UNIVERSE:
        p = CACHE_DIR / f"{sym}USDT_4h.joblib"
        df = joblib.load(p)
        daily_close = df['close'].resample('1D').last().dropna()
        fwd = (daily_close.shift(-hold_days) / daily_close - 1.0).dropna()
        pool.extend(fwd.values.tolist())
    return np.asarray(pool, dtype=float)


def load_alt_fwd_returns(sym, hold_days):
    df = joblib.load(CACHE_DIR / f"{sym}USDT_4h.joblib")
    daily_close = df['close'].resample('1D').last().dropna()
    return (daily_close.shift(-hold_days) / daily_close - 1.0)


def evaluate_quadrant(label, side, trigger_dates, hold_days, candidate_pool):
    """side = +1 for LONG, -1 for SHORT. Returns dict of metrics."""
    gross_dec = []  # decimal
    syms = []
    dates = []
    for sym in UNIVERSE:
        fwd = load_alt_fwd_returns(sym, hold_days)
        rets = fwd.reindex(trigger_dates).dropna()
        for d, r in rets.items():
            gross_dec.append(side * r)
            syms.append(sym)
            dates.append(d)
    gross_dec = np.asarray(gross_dec, dtype=float)
    if len(gross_dec) < 30:
        return {"label": label, "n": int(len(gross_dec)), "skipped": True}

    # signed-pool for SHORT (mirror pool sign)
    pool_signed = side * candidate_pool

    net_dec = gross_dec - FEE_DECIMAL_RT  # apply round-trip fee
    mean_gross_bp = float(np.mean(gross_dec) * 10000)
    mean_net_bp = float(np.mean(net_dec) * 10000)
    std_net = float(np.std(net_dec, ddof=1))
    t_stat = float(net_dec.mean() / (std_net / np.sqrt(len(net_dec)))) if std_net > 0 else 0.0

    perm = fee_aware_perm_test(net_dec, pool_signed, fee_per_trade=FEE_DECIMAL_RT, n_perms=N_PERM, rng_seed=42)
    boot = bootstrap_ci(net_dec, n_boot=N_BOOT, rng_seed=42)

    sigex = perm.get('signal_t_excess', float('nan'))
    perm_p = perm.get('perm_p_one_sided_above', perm.get('perm_p_two_sided', float('nan')))
    ci_lower_bp = float(boot['ci_lower'] * 10000)
    ci_upper_bp = float(boot['ci_upper'] * 10000)

    gate_pass = (not np.isnan(sigex)) and (sigex >= 2.0) and (ci_lower_bp > 0) and (perm_p <= 0.10)

    df_q = pd.DataFrame({'date': pd.to_datetime(dates), 'net_bp': net_dec * 10000, 'sym': syms})
    df_q['quarter'] = df_q['date'].dt.to_period('Q').astype(str)
    quarter_stats = {}
    for q, grp in df_q.groupby('quarter'):
        if len(grp) >= 5:
            sd = grp['net_bp'].std(ddof=1)
            tq = float(grp['net_bp'].mean() / (sd / np.sqrt(len(grp)))) if sd > 0 else 0.0
            quarter_stats[q] = {"n": int(len(grp)), "t": tq, "mean_bp": float(grp['net_bp'].mean())}
    n_meas_q = len(quarter_stats)
    n_pos_q = sum(1 for v in quarter_stats.values() if v['t'] > 0)

    sym_stats = {}
    for sym, grp in df_q.groupby('sym'):
        if len(grp) >= 5:
            sci = bootstrap_ci(grp['net_bp'].values / 10000.0, n_boot=500, rng_seed=42)
            sym_stats[sym] = {
                "n": int(len(grp)),
                "ci_lower_bp": float(sci['ci_lower'] * 10000),
                "ci_pos": bool(sci['ci_lower'] > 0),
            }
    n_meas_s = len(sym_stats)
    n_ci_pos_s = sum(1 for v in sym_stats.values() if v['ci_pos'])

    era_stats = {}
    df_q['era'] = df_q['date'].dt.year.astype(str)
    for era, grp in df_q.groupby('era'):
        if len(grp) >= 5:
            sd = grp['net_bp'].std(ddof=1)
            te = float(grp['net_bp'].mean() / (sd / np.sqrt(len(grp)))) if sd > 0 else 0.0
            era_stats[era] = {"n": int(len(grp)), "t": te, "mean_bp": float(grp['net_bp'].mean())}

    return {
        "label": label,
        "side": int(side),
        "hold_days": int(hold_days),
        "n": int(len(gross_dec)),
        "mean_gross_bp": mean_gross_bp,
        "mean_net_bp": mean_net_bp,
        "t_stat": t_stat,
        "signal_t_excess": float(sigex) if not np.isnan(sigex) else None,
        "perm_p_one_sided_above": float(perm_p) if not np.isnan(perm_p) else None,
        "perm_p_two_sided": float(perm.get('perm_p_two_sided', float('nan'))) if not np.isnan(perm.get('perm_p_two_sided', float('nan'))) else None,
        "ci_lower_bp": ci_lower_bp,
        "ci_upper_bp": ci_upper_bp,
        "three_gate_pass": bool(gate_pass),
        "concentration": {
            "n_measurable_q": n_meas_q,
            "n_pos_t_q": n_pos_q,
            "quarter_pos_t_ratio": float(n_pos_q / n_meas_q) if n_meas_q else 0.0,
            "n_measurable_s": n_meas_s,
            "n_ci_pos_s": n_ci_pos_s,
            "symbol_ci_pos_ratio": float(n_ci_pos_s / n_meas_s) if n_meas_s else 0.0,
            "per_quarter": quarter_stats,
            "per_symbol": sym_stats,
        },
        "era_stratify": era_stats,
    }


def main():
    log.info(f"paradigm 206 R-1 dispatch: {PARADIGM_SLUG}")
    cell_A, cell_B, ks_z, sign_series = compute_btc_ks_trigger()

    results = {
        "paradigm": PARADIGM_SLUG,
        "phase": "R-1",
        "config": {
            "ks_window_days": KS_WINDOW,
            "zscore_window_days": ZSCORE_WINDOW,
            "z_threshold": Z_THRESHOLD,
            "fee_bps_one_way": FEE_BPS,
            "n_perm": N_PERM,
            "n_boot": N_BOOT,
            "universe_n": len(UNIVERSE),
            "universe": UNIVERSE,
        },
        "trigger_stats": {
            "n_cell_A": int(len(cell_A)),
            "n_cell_B": int(len(cell_B)),
            "disjoint_intersection": int(len(set(cell_A) & set(cell_B))),
            "ks_z_p50": float(ks_z.median()),
            "ks_z_p90": float(ks_z.quantile(0.9)),
            "ks_z_p99": float(ks_z.quantile(0.99)),
        },
        "quadrants_1d": {},
        "hold_sweep": {},
    }

    for hold_days in HOLDS:
        log.info(f"--- Hold = +{hold_days}d ---")
        pool = build_candidate_pool(hold_days)
        log.info(f"  candidate pool size: {len(pool)}")
        q = {}
        q['A_focus_heavier_LONG'] = evaluate_quadrant("A_focus_LONG", +1, cell_A, hold_days, pool)
        q['A_mirror_heavier_SHORT'] = evaluate_quadrant("A_mirror_SHORT", -1, cell_A, hold_days, pool)
        q['B_same_lighter_SHORT'] = evaluate_quadrant("B_same_SHORT", -1, cell_B, hold_days, pool)
        q['B_mirror_lighter_LONG'] = evaluate_quadrant("B_mirror_LONG", +1, cell_B, hold_days, pool)
        results['hold_sweep'][f'+{hold_days}d'] = q
        if hold_days == 1:
            results['quadrants_1d'] = q

    h1 = results['hold_sweep']['+1d']
    Afg = h1['A_focus_heavier_LONG'].get('mean_gross_bp')
    Amg = h1['A_mirror_heavier_SHORT'].get('mean_gross_bp')
    Bsg = h1['B_same_lighter_SHORT'].get('mean_gross_bp')
    Bmg = h1['B_mirror_lighter_LONG'].get('mean_gross_bp')
    snt = {
        "A_focus_gross_bp": Afg,
        "A_mirror_gross_bp": Amg,
        "A_within_trigger_sum_bp": (Afg + Amg) if (Afg is not None and Amg is not None) else None,
        "B_same_gross_bp": Bsg,
        "B_mirror_gross_bp": Bmg,
        "B_within_trigger_sum_bp": (Bsg + Bmg) if (Bsg is not None and Bmg is not None) else None,
        "cross_set_disjoint": True,
        "note": "A_focus + A_mirror = exact ±same by mirror tautology within same trigger set. cell A vs cell B disjoint → cross-set asymmetric magnitudes possible.",
    }
    results['item7_snt_structural_integrity'] = snt

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    log.info(f"Wrote {out_path}")

    print("\n" + "=" * 80)
    print("paradigm 206 R-1 SUMMARY")
    print("=" * 80)
    print(f"\nTrigger: cell_A={len(cell_A)} cell_B={len(cell_B)} (disjoint)")
    print(f"\nItem 7 SNT structural integrity (+1d hold):")
    print(f"  A_focus  (heavier×LONG)   gross = {Afg}")
    print(f"  A_mirror (heavier×SHORT)  gross = {Amg}")
    print(f"  A within-trigger sum     = {snt['A_within_trigger_sum_bp']}")
    print(f"  B_same   (lighter×SHORT) gross = {Bsg}")
    print(f"  B_mirror (lighter×LONG)  gross = {Bmg}")
    print(f"  B within-trigger sum     = {snt['B_within_trigger_sum_bp']}")
    print(f"\n4-quadrant @ +1d:")
    for k, v in h1.items():
        if v.get('skipped'):
            print(f"  {k}: SKIPPED n={v['n']}")
        else:
            print(f"  {k}: n={v['n']} gross={v['mean_gross_bp']:+.2f}bp net={v['mean_net_bp']:+.2f}bp "
                  f"sigex={v.get('signal_t_excess')} perm_p_above={v.get('perm_p_one_sided_above')} "
                  f"ci=[{v['ci_lower_bp']:+.2f},{v['ci_upper_bp']:+.2f}] "
                  f"q_pos_t={v['concentration']['quarter_pos_t_ratio']:.2f} "
                  f"sym_ci_pos={v['concentration']['symbol_ci_pos_ratio']:.2f} "
                  f"PASS={v['three_gate_pass']}")
    print(f"\nHold sweep:")
    for hd in HOLDS:
        hdk = f'+{hd}d'
        print(f"  --- {hdk} ---")
        for k, v in results['hold_sweep'][hdk].items():
            if not v.get('skipped'):
                print(f"    {k}: net={v['mean_net_bp']:+.2f}bp sigex={v.get('signal_t_excess')} "
                      f"perm_p_above={v.get('perm_p_one_sided_above')} "
                      f"ci_lo={v['ci_lower_bp']:+.2f} PASS={v['three_gate_pass']}")
    print(f"\nEra stratify (A_focus_LONG +1d):")
    for era, st in h1['A_focus_heavier_LONG'].get('era_stratify', {}).items():
        print(f"  {era}: n={st['n']} t={st['t']:+.2f} mean={st['mean_bp']:+.2f}bp")
    print(f"\nEra stratify (B_same_SHORT +1d):")
    for era, st in h1['B_same_lighter_SHORT'].get('era_stratify', {}).items():
        print(f"  {era}: n={st['n']} t={st['t']:+.2f} mean={st['mean_bp']:+.2f}bp")
    return results


if __name__ == "__main__":
    main()
