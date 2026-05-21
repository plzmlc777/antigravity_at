"""R-1 PoC: intra_symbol_spot_perp_lead_lag_alt_5m

4-quadrant Symmetric Negative Test (Lesson #19):
  A focus: perp-leads (tau* > 0) + perp-up → spot LONG (predict spot follow up)
  A mirror: perp-leads + perp-up → spot SHORT
  B same-sign: spot-leads (tau* < 0) + spot-up → perp LONG
  B mirror: spot-leads + spot-up → perp SHORT

Forward holds sweep: {15m=3, 30m=6, 60m=12, 120m=24, 240m=48} bars
Threshold sweep: |tau*| ∈ {1,2,3} × corr ∈ {0.5, 0.7, 0.85}

Lessons applied: #11/#19/#20/#21/#29/#34/#37
"""
import sys
import json
import time
import joblib
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, '/home/mint/auto_trading/backend')
from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci

OHLCV_DIR = Path('/home/mint/auto_trading/backend/runs/ohlcv_cache')
PREM_DIR = Path('/home/mint/auto_trading/backend/runs/premium_index')
OUT_DIR = Path('/home/mint/auto_trading/backend/runs/research_track/intra_symbol_spot_perp_lead_lag_alt_5m')
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = ['ADAUSDT', 'AVAXUSDT', 'BCHUSDT', 'BNBUSDT', 'BTCUSDT',
           'DOGEUSDT', 'ETHUSDT', 'FILUSDT', 'LINKUSDT', 'LTCUSDT',
           'NEARUSDT', 'SOLUSDT', 'WIFUSDT', 'XRPUSDT']

WINDOW = 6  # 30m in 5m bars
MAX_LAG = 5  # ±25m
HOLDS = {'15m': 3, '30m': 6, '60m': 12, '120m': 24, '240m': 48}
FEE_PER_TRADE = 0.0016  # 16bp round-trip fee (decimal)


def load_5m_pair(sym):
    ohlcv = joblib.load(OHLCV_DIR / f'{sym}_1m.joblib')
    perp_5m = ohlcv['close'].resample('5min').last()
    prem_5m = joblib.load(PREM_DIR / f'{sym}_premium_5m.joblib')['close']
    aligned = pd.concat({'perp': perp_5m, 'prem': prem_5m}, axis=1).dropna()
    aligned['spot'] = aligned['perp'] / (1.0 + aligned['prem'])
    return aligned['perp'], aligned['spot']


def rolling_xcorr(perp, spot, window=WINDOW, max_lag=MAX_LAG):
    perp_ret = perp.pct_change()
    spot_ret = spot.pct_change()
    n = len(perp_ret)
    lags = list(range(-max_lag, max_lag + 1))
    corr_mat = np.full((n, len(lags)), np.nan)
    for i, lag in enumerate(lags):
        shifted_spot = spot_ret.shift(lag)
        c = perp_ret.rolling(window).corr(shifted_spot)
        corr_mat[:, i] = c.values
    abs_corr = np.abs(corr_mat)
    safe = np.where(np.isnan(abs_corr), -np.inf, abs_corr)
    star_idx = safe.argmax(axis=1)
    tau_star = np.array([lags[i] for i in star_idx], dtype=float)
    corr_star = corr_mat[np.arange(n), star_idx]
    return pd.Series(tau_star, index=perp.index, name='tau_star'), \
           pd.Series(corr_star, index=perp.index, name='corr_star')


def build_events_and_pool(sym):
    """Return (events_df, pool_dict) where pool_dict[hold_key] = full forward returns."""
    perp, spot = load_5m_pair(sym)
    tau, corr = rolling_xcorr(perp, spot)

    perp_ret = perp.pct_change()
    spot_ret = spot.pct_change()
    perp_dir = np.sign(perp_ret)
    spot_dir = np.sign(spot_ret)

    df = pd.DataFrame({
        'tau': tau,
        'corr': corr,
        'perp_dir': perp_dir,
        'spot_dir': spot_dir,
    })
    pool = {}
    for hkey, h in HOLDS.items():
        df[f'fwd_perp_{hkey}'] = perp.pct_change(h).shift(-h)
        df[f'fwd_spot_{hkey}'] = spot.pct_change(h).shift(-h)
        # Pool = ALL valid forward returns (non-NaN) — universe of candidate trades
        pool[f'perp_{hkey}'] = df[f'fwd_perp_{hkey}'].dropna().values
        pool[f'spot_{hkey}'] = df[f'fwd_spot_{hkey}'].dropna().values

    df = df.dropna()
    df['abs_tau'] = df['tau'].abs()
    df['symbol'] = sym
    df['quarter'] = df.index.to_period('Q').astype(str)
    return df, pool


def signed_return_for_quadrant(events, quadrant, hold_key):
    if quadrant == 'A_focus':
        mask = (events['tau'] > 0) & (events['perp_dir'] > 0)
        sign = +1
        col = f'fwd_spot_{hold_key}'
        venue_key = f'spot_{hold_key}'
    elif quadrant == 'A_mirror':
        mask = (events['tau'] > 0) & (events['perp_dir'] > 0)
        sign = -1
        col = f'fwd_spot_{hold_key}'
        venue_key = f'spot_{hold_key}'
    elif quadrant == 'B_same':
        mask = (events['tau'] < 0) & (events['spot_dir'] > 0)
        sign = +1
        col = f'fwd_perp_{hold_key}'
        venue_key = f'perp_{hold_key}'
    elif quadrant == 'B_mirror':
        mask = (events['tau'] < 0) & (events['spot_dir'] > 0)
        sign = -1
        col = f'fwd_perp_{hold_key}'
        venue_key = f'perp_{hold_key}'
    else:
        raise ValueError(quadrant)

    sel = events[mask]
    if len(sel) == 0:
        return np.array([]), sel, venue_key, sign
    rets = sign * sel[col].values
    return rets, sel, venue_key, sign


def evaluate_cell(rets, sel, venue_key, sign, pool_all, label):
    """3-gate evaluation. rets = signed gross returns (sign already applied)."""
    n = len(rets)
    if n < 30:
        return {'label': label, 'n': n, 'verdict': 'INSUFFICIENT', 'gate_pass': False}

    gross_mean = float(rets.mean())
    gross_bp = gross_mean * 10000
    # Build pool: all universe forward returns signed appropriately
    # For LONG side: pool = sign * forward_return for each candidate. To match fee subtraction in perm:
    # We pass signed pool returns (already direction-applied)
    sign_pool = sign * pool_all[venue_key]
    # observed_net = rets - fee (signed already)
    observed_net = rets - FEE_PER_TRADE

    perm = fee_aware_perm_test(
        observed_net_returns=observed_net,
        candidate_pool_returns=sign_pool,
        fee_per_trade=FEE_PER_TRADE,
        n_perms=2000,
        rng_seed=42,
    )
    ci = bootstrap_ci(observed_net, n_boot=2000, rng_seed=42)

    obs_t = perm['obs_t']
    null_mean_t = perm['null_mean_t']
    sig_t_ex = perm.get('signal_t_excess', float('nan'))
    perm_p = perm['perm_p_two_sided']
    ci_lower = ci['ci_lower'] * 10000
    ci_upper = ci['ci_upper'] * 10000

    gate_pass = (
        not np.isnan(sig_t_ex) and sig_t_ex >= 2.0 and
        not np.isnan(ci_lower) and ci_lower > 0 and
        not np.isnan(perm_p) and perm_p <= 0.10
    )

    return {
        'label': label,
        'n': int(n),
        'gross_bp': round(gross_bp, 3),
        'net_bp': round(gross_bp - FEE_PER_TRADE * 10000, 3),
        'obs_t': round(obs_t, 3) if not np.isnan(obs_t) else None,
        'null_mean_t': round(null_mean_t, 3) if not np.isnan(null_mean_t) else None,
        'signal_t_excess': round(sig_t_ex, 3) if not np.isnan(sig_t_ex) else None,
        'ci_lower_bp': round(ci_lower, 3) if not np.isnan(ci_lower) else None,
        'ci_upper_bp': round(ci_upper, 3) if not np.isnan(ci_upper) else None,
        'perm_p': round(perm_p, 4) if not np.isnan(perm_p) else None,
        'gate_pass': bool(gate_pass),
    }


def concentration_diag(events_all, pool_all, quadrant, hold_key):
    rets_arr, sel_arr, venue_key, sign = signed_return_for_quadrant(events_all, quadrant, hold_key)
    if len(rets_arr) < 30:
        return {'quarter_t': {}, 'symbol_ci': {}, 'n_total': len(rets_arr), 'concentration_pass': False}

    q_stats = {}
    for q, sub in sel_arr.groupby('quarter'):
        sub_rets, _, _, _ = signed_return_for_quadrant(sub, quadrant, hold_key)
        if len(sub_rets) >= 15:
            net = sub_rets - FEE_PER_TRADE
            t = float(net.mean() / (net.std(ddof=1) / np.sqrt(len(net)))) if net.std() > 0 else 0
            q_stats[q] = {'n': int(len(sub_rets)), 't': round(t, 2),
                          'gross_bp': round(sub_rets.mean()*10000, 2)}

    sym_stats = {}
    for s, sub in sel_arr.groupby('symbol'):
        sub_rets, _, _, _ = signed_return_for_quadrant(sub, quadrant, hold_key)
        if len(sub_rets) >= 15:
            ci = bootstrap_ci(sub_rets - FEE_PER_TRADE, n_boot=1000, rng_seed=42)
            sym_stats[s] = {
                'n': int(len(sub_rets)),
                'ci_lower_bp': round(ci['ci_lower']*10000, 2),
                'ci_pos': bool(ci['ci_lower'] > 0),
                'mean_bp': round(sub_rets.mean()*10000, 2),
            }

    n_pos_t = sum(1 for v in q_stats.values() if v['t'] > 0)
    n_meas = len(q_stats)
    n_ci_pos = sum(1 for v in sym_stats.values() if v['ci_pos'])
    n_sym_meas = len(sym_stats)

    return {
        'n_total': int(len(rets_arr)),
        'quarter_t': q_stats,
        'quarter_n_measurable': n_meas,
        'quarter_n_pos_t': n_pos_t,
        'quarter_pos_t_ratio': round(n_pos_t / max(n_meas, 1), 2),
        'symbol_ci': sym_stats,
        'symbol_n_measurable': n_sym_meas,
        'symbol_n_ci_pos': n_ci_pos,
        'symbol_ci_pos_ratio': round(n_ci_pos / max(n_sym_meas, 1), 2),
        'concentration_pass': bool(
            n_pos_t / max(n_meas, 1) >= 0.5 and
            n_ci_pos / max(n_sym_meas, 1) >= 0.30 and
            n_ci_pos >= 3
        ),
    }


def lesson_21_axis_alone(events_all, hold_key):
    df = events_all.copy()
    corr_only = df[(df['corr'] >= 0.7) & (df['perp_dir'] > 0)]
    tau_only = df[(df['abs_tau'] >= 2) & (df['perp_dir'] > 0)]
    joint = df[(df['abs_tau'] >= 2) & (df['corr'] >= 0.7) & (df['perp_dir'] > 0)]
    col = f'fwd_spot_{hold_key}'
    out = {}
    for name, sub in [('corr_alone_perp_up', corr_only), ('tau_alone_perp_up', tau_only), ('joint_perp_up', joint)]:
        if len(sub) < 30:
            out[name] = {'n': len(sub), 'mean_bp': None, 't': None}
        else:
            r = sub[col].values
            net = r - FEE_PER_TRADE
            t = float(net.mean()/(net.std(ddof=1)/np.sqrt(len(net)))) if net.std() > 0 else 0
            out[name] = {'n': int(len(sub)), 'gross_mean_bp': round(r.mean()*10000, 2),
                         'net_t': round(t, 2)}
    return out


def main():
    t0 = time.time()
    log = {'start': pd.Timestamp.now().isoformat(), 'universe': SYMBOLS,
           'fee_per_trade_bp': FEE_PER_TRADE * 10000}

    print(f'[{time.time()-t0:.0f}s] Loading all 14 symbols (events + pool)...')
    all_events = []
    pool_concat = {f'{v}_{h}': [] for v in ['perp', 'spot'] for h in HOLDS}
    for sym in SYMBOLS:
        try:
            ev, pool = build_events_and_pool(sym)
            ev_liberal = ev[(ev['abs_tau'] >= 1) & (ev['corr'] >= 0.5)]
            print(f'  {sym}: n_events_liberal={len(ev_liberal)} pool_size~{len(pool["perp_60m"])}')
            all_events.append(ev_liberal)
            for k in pool_concat:
                pool_concat[k].append(pool[k])
        except Exception as e:
            print(f'  {sym}: ERROR {e}')

    pool_all = {k: np.concatenate(v) if v else np.array([]) for k, v in pool_concat.items()}
    events_all = pd.concat(all_events, axis=0).sort_index()
    print(f'\n[{time.time()-t0:.0f}s] Total liberal events: {len(events_all)}, pool 60m: {len(pool_all["perp_60m"])}')
    log['total_events_liberal'] = int(len(events_all))
    log['pool_size_60m'] = int(len(pool_all['perp_60m']))

    primary_events = events_all[(events_all['abs_tau'] >= 2) & (events_all['corr'] >= 0.7)]
    print(f'[{time.time()-t0:.0f}s] Primary trigger events: n={len(primary_events)}')
    log['primary_n'] = int(len(primary_events))

    # 4-quadrant SNT
    print(f'\n=== 4-Quadrant SNT (primary: |tau|>=2, corr>=0.7, hold=60m) ===')
    quadrants = ['A_focus', 'A_mirror', 'B_same', 'B_mirror']
    snt_results = {}
    for q in quadrants:
        rets, sel, venue_key, sign = signed_return_for_quadrant(primary_events, q, '60m')
        res = evaluate_cell(rets, sel, venue_key, sign, pool_all, f'{q}_60m')
        snt_results[q] = res
        print(f'  {q}: n={res["n"]}, gross={res.get("gross_bp")}bp, sig_t_ex={res.get("signal_t_excess")}, '
              f'ci_lower={res.get("ci_lower_bp")}bp, perm_p={res.get("perm_p")}, PASS={res["gate_pass"]}')
    log['snt_primary'] = snt_results

    # Sweep
    print(f'\n=== Lesson #37 Hold × Threshold sweep (A_focus only) ===')
    sweep = {}
    for tau_t in [1, 2, 3]:
        for corr_t in [0.5, 0.7, 0.85]:
            cell_events = events_all[(events_all['abs_tau'] >= tau_t) & (events_all['corr'] >= corr_t)]
            for hkey in HOLDS:
                rets, sel, vkey, sign = signed_return_for_quadrant(cell_events, 'A_focus', hkey)
                if len(rets) < 30:
                    continue
                res = evaluate_cell(rets, sel, vkey, sign, pool_all,
                                    f'A_focus_tau{tau_t}_corr{corr_t}_{hkey}')
                sweep[res['label']] = res
                marker = '***PASS***' if res['gate_pass'] else ''
                print(f'  tau>={tau_t} corr>={corr_t} h={hkey}: n={res["n"]:5d} '
                      f'gross={res.get("gross_bp"):8.2f} sigex={res.get("signal_t_excess")} '
                      f'ci_low={res.get("ci_lower_bp")} perm={res.get("perm_p")} {marker}')
    log['sweep'] = sweep

    # Concentration on focus 60m
    print(f'\n=== Concentration (A_focus 60m) ===')
    conc = concentration_diag(primary_events, pool_all, 'A_focus', '60m')
    print(f'  n_total={conc["n_total"]}')
    print(f'  quarters: pos_t_ratio={conc.get("quarter_pos_t_ratio")} n_pos={conc.get("quarter_n_pos_t")}/{conc.get("quarter_n_measurable")}')
    for q, v in sorted(conc.get('quarter_t', {}).items()):
        print(f'    {q}: n={v["n"]} t={v["t"]} gross={v["gross_bp"]}bp')
    print(f'  symbols: ci_pos_ratio={conc.get("symbol_ci_pos_ratio")} n_ci_pos={conc.get("symbol_n_ci_pos")}/{conc.get("symbol_n_measurable")}')
    for s, v in sorted(conc.get('symbol_ci', {}).items()):
        print(f'    {s}: n={v["n"]} ci_low={v["ci_lower_bp"]}bp mean={v["mean_bp"]}bp ci_pos={v["ci_pos"]}')
    print(f'  Concentration PASS: {conc.get("concentration_pass")}')
    log['concentration_focus_60m'] = conc

    # Lesson #21
    print(f'\n=== Lesson #21 axis-alone test ===')
    axis = lesson_21_axis_alone(events_all, '60m')
    for name, v in axis.items():
        print(f'  {name}: n={v["n"]} gross={v.get("gross_mean_bp")}bp net_t={v.get("net_t")}')
    log['lesson_21_axis_alone'] = axis

    # Life-changing 4-dim projection
    print(f'\n=== Life-changing 4-dim projection (A_focus 60m) ===')
    focus = snt_results.get('A_focus', {})
    if focus.get('n', 0) > 0:
        days = (events_all.index.max() - events_all.index.min()).days
        years = max(days / 365.0, 0.01)
        trades_yr = focus['n'] / years
        util = trades_yr * (60/525600)
        edge_pct = focus.get('net_bp', 0) / 100
        sharpe = focus.get('obs_t', 0) / np.sqrt(focus['n']) * np.sqrt(trades_yr) if focus['n'] > 0 else 0
        lc = {
            'full_span_days': int(days),
            'trades_per_year': round(trades_yr, 1),
            'capital_util_pct': round(util*100, 2),
            'edge_per_trade_pct': round(edge_pct, 3),
            'approx_sharpe': round(sharpe, 2),
            'pass_trades_yr': bool(trades_yr >= 12),
            'pass_util': bool(util >= 0.30),
            'pass_edge': bool(edge_pct >= 2),
            'pass_sharpe': bool(sharpe >= 3),
        }
        print(f'  span: {days}d ({years:.2f}yr)')
        print(f'  trades/yr: {lc["trades_per_year"]} (>=12: {lc["pass_trades_yr"]})')
        print(f'  util: {lc["capital_util_pct"]}% (>=30%: {lc["pass_util"]})')
        print(f'  edge: {lc["edge_per_trade_pct"]}% (>=2%: {lc["pass_edge"]})')
        print(f'  sharpe: {lc["approx_sharpe"]} (>=3: {lc["pass_sharpe"]})')
        log['life_changing_4dim'] = lc
    else:
        log['life_changing_4dim'] = None

    # Verdict
    print(f'\n=== VERDICT ===')
    focus_pass = snt_results.get('A_focus', {}).get('gate_pass', False)
    any_quadrant_pass = any(v.get('gate_pass', False) for v in snt_results.values())
    sweep_passes = [k for k, v in sweep.items() if v.get('gate_pass', False)]

    # Check if all gross returns are below fee floor (Lesson #35 fee-trap)
    all_below_fee = all(
        v.get('gross_bp') is not None and abs(v.get('gross_bp', 0)) < FEE_PER_TRADE * 10000
        for v in snt_results.values() if v.get('gross_bp') is not None
    )

    if not any_quadrant_pass and len(sweep_passes) == 0:
        if all_below_fee:
            verdict = 'BROAD_FALSIFIED_FEE_FLOOR'
        else:
            verdict = 'BROAD_FALSIFIED'
    elif focus_pass:
        lc = log.get('life_changing_4dim') or {}
        all_4dim = all([lc.get('pass_trades_yr'), lc.get('pass_util'), lc.get('pass_edge'), lc.get('pass_sharpe')])
        if conc.get('concentration_pass') and all_4dim:
            verdict = 'PASS_R1_FULL'
        elif conc.get('concentration_pass') and not all_4dim:
            verdict = 'NARROW_SCOPE_LIFE_CHANGING_FAIL_CANDIDATE'
        else:
            verdict = 'CONCENTRATED_R1_PASS'
    elif len(sweep_passes) > 0:
        verdict = 'PARTIAL_SWEEP_PASS_FOCUS_FAIL'
    else:
        verdict = 'BROAD_FALSIFIED'

    log['verdict'] = verdict
    log['focus_pass'] = focus_pass
    log['any_quadrant_pass'] = any_quadrant_pass
    log['sweep_passes'] = sweep_passes
    log['wall_clock_seconds'] = round(time.time() - t0, 1)

    print(f'  VERDICT: {verdict}')
    print(f'  wall_clock: {log["wall_clock_seconds"]}s')

    out_path = OUT_DIR / 'r1__metrics.json'
    with open(out_path, 'w') as f:
        json.dump(log, f, indent=2, default=str)
    print(f'\nSaved → {out_path}')


if __name__ == '__main__':
    main()
