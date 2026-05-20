"""paradigm 121 R-1 PoC — hmm_realized_vol_state_x_markprice_basis_extreme_alt_directional_4h

Hypothesis
----------
HMM (3-state Gaussian, per-symbol, weekly walk-forward refit on 1h log-returns)
provides an unsupervised endogenous vol-state decomposition. State HIGH (highest
emission variance ordering, posterior >= 0.8) is used as a **conditioning filter**.

External orthogonal axis: markPrice basis 1h z-score (rolling 30d, |z|>2). The
basis axis is structurally orthogonal to per-sym 1h log-return volatility —
basis is mark - index_spot_composite divergence, not realized return.

Joint trigger (4-quadrant Symmetric Negative Test, Lesson #19):
  A_focus  : HMM HIGH-vol × basis z>+2 × SHORT 4h
             (mechanism: rich-perp during high vol = squeeze setup → mean-revert)
  A_mirror : HMM HIGH-vol × basis z>+2 × LONG 4h
  B_focus  : HMM HIGH-vol × basis z<-2 × LONG 4h
             (mechanism: cheap-perp during high vol = capitulation → mean-revert)
  B_mirror : HMM HIGH-vol × basis z<-2 × SHORT 4h

Lesson #45 candidate UMBREELLA-PATH verification (CRITICAL):
- paradigm 119 (graveyard) used HMM state-identity as trigger (endogenous-only)
  → broad-falsified, "Lesson #45 violation"
- paradigm 121 uses HMM state as **conditioning filter** + external orthogonal
  axis (markPrice basis) as trigger
- This is the Lesson #45 candidate "umbrella path" — HMM + exogenous axis
- If R-1 PASS_R1_FULL → Lesson #45 candidate refinement (HMM is OK as filter
  conditioning, not state-identity trigger)
- If R-1 BROAD_FALSIFIED → Lesson #45 candidate strengthening (HMM × any axis
  combination broadly broken, formal confirmation pending)

paradigm 105 (mark_index_basis percentile rank single-axis at 5m) distinction:
- paradigm 105 used signed percentile rank on 5m basis as trigger (BROAD_FALSIFIED)
- paradigm 121 uses 1h basis z-score as joint conditioning with HMM vol state
- Family-distinct: 105 single-axis, 121 joint (HMM + basis) at 1h granularity

R-0 prescreen executed 2026-05-20 17:17 KST:
- substrate PASS (6 alts × 1y × 1h aggregate from paradigm 105 5m archive cache)
- Lesson #11 marginal (per-cell ~50, after 4-quarter binning ~12-13 borderline)
- Lesson #34 |basis z|>2 rate = 4.86% (PASS)
- **Lesson #46 candidate: A_focus pool n=202 gross +43.46bp > 16bp fee floor (CI lower +16.3bp), PASS**
- VERDICT: R0_PASS_PROCEED_R1

R-1 universe scope: paradigm 105 cache subset 6 alts (SOL/HBAR/AVAX/DOGE/ETH/LINK).
Full 13-alt expansion deferred to R-2 if R-1 PASS.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

# hmmlearn (paradigm 119 template — local install confirmed 2026-05-20 17:15 KST)
try:
    from hmmlearn import hmm  # type: ignore
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("paradigm121_r1")

PARADIGM_NAME = "hmm_realized_vol_state_x_markprice_basis_extreme_alt_directional_4h"
PARADIGM_ID = 121
OUTPUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Universe — paradigm 105 cache subset
ALTS = ["SOLUSDT", "HBARUSDT", "AVAXUSDT", "DOGEUSDT", "ETHUSDT", "LINKUSDT"]

MARK_INDEX_CACHE = ROOT / "runs" / "research_track" / "binance_perp_mark_index_basis_extreme_alt_directional_4h" / "mark_index_cache"

# Frame params
ROLLING_WIN_1H = 24 * 30          # 30 days for basis z-score
HOLD_BARS_1H = 4                  # 4h hold = 4 1h bars
BASIS_Z_THRESHOLD = 2.0
HMM_N_STATES = 3
HMM_POSTERIOR_MIN = 0.80          # posterior >= 0.8 high-confidence filter
HMM_TRAIN_WIN_DAYS = 90           # rolling 90d training window
HMM_REFIT_FREQ_DAYS = 7           # weekly walk-forward refit
HMM_RANDOM_SEED = 42

FEE_PER_TRADE = 0.0008            # 8 bp single trade; net = direction*fwd - fee
RNG_SEED = 42

# Concentration gate thresholds (Lesson #16/#41 amendment)
CONC_QUARTER_POS_T_MIN = 0.50
CONC_SYM_CI_POS_RATIO_MIN = 0.30
CONC_N_SYMS_CI_POS_MIN = 3        # adjusted from 3 to fit 6-alt cohort proportionally

# Three-gate (R-1)
GATE_SIGEX_MIN = 2.0
GATE_CI_LOWER_MIN = 0.0
GATE_PERM_P_MAX = 0.10

# Lesson #41 life-changing
LIFE_CHANGING_EDGE_MIN_PCT = 2.0  # 2%/trade


def load_mark_index(sym: str) -> tuple[pd.Series, pd.Series]:
    """Load + concat monthly markPriceKlines + indexPriceKlines from paradigm 105 cache."""
    mark_files = sorted(MARK_INDEX_CACHE.glob(f"{sym}_markPriceKlines_*.joblib"))
    index_files = sorted(MARK_INDEX_CACHE.glob(f"{sym}_indexPriceKlines_*.joblib"))

    def load_concat(files: list[Path]) -> pd.Series:
        dfs = []
        for f in files:
            obj = joblib.load(f)
            if isinstance(obj, pd.DataFrame):
                if "close" in obj.columns:
                    dfs.append(obj["close"])
                else:
                    num = obj.select_dtypes(include=[np.number])
                    if not num.empty:
                        dfs.append(num.iloc[:, 0])
            elif isinstance(obj, pd.Series):
                dfs.append(obj)
        s = pd.concat(dfs).sort_index()
        s = s[~s.index.duplicated(keep="first")]
        return s

    mark = load_concat(mark_files)
    index = load_concat(index_files)
    return mark, index


def aggregate_1h(s: pd.Series) -> pd.Series:
    return s.resample("1h").last().dropna()


def fit_hmm_walk_forward(
    log_returns: pd.Series, train_win_days: int = HMM_TRAIN_WIN_DAYS,
    refit_freq_days: int = HMM_REFIT_FREQ_DAYS, n_states: int = HMM_N_STATES,
) -> pd.DataFrame:
    """Per-symbol weekly walk-forward HMM fit.

    Returns DataFrame indexed by time, columns:
      - state: argmax posterior state index (variance-ordered: 0=LOW, n-1=HIGH)
      - posterior_high: posterior probability of HIGH state
      - high_conf: bool (state==HIGH AND posterior_high >= HMM_POSTERIOR_MIN)
    """
    if not HMM_AVAILABLE:
        raise RuntimeError("hmmlearn not available")

    log_returns = log_returns.dropna()
    times = log_returns.index
    train_win = train_win_days * 24  # 1h frame: 24 bars/day
    refit_freq = refit_freq_days * 24

    if len(log_returns) < train_win + refit_freq:
        log.warning(f"insufficient series ({len(log_returns)} < {train_win + refit_freq}) — skip HMM")
        return pd.DataFrame(index=times, columns=["state", "posterior_high", "high_conf"]).fillna(np.nan)

    out_state = pd.Series(index=times, dtype=float)
    out_post_high = pd.Series(index=times, dtype=float)

    # Walk-forward indices
    start_idx = train_win
    while start_idx < len(log_returns):
        end_idx = min(start_idx + refit_freq, len(log_returns))
        # Train on prior train_win bars
        train_data = log_returns.iloc[start_idx - train_win:start_idx].values.reshape(-1, 1)
        try:
            model = hmm.GaussianHMM(
                n_components=n_states,
                covariance_type="full",
                n_iter=50,
                random_state=HMM_RANDOM_SEED,
            )
            model.fit(train_data)
            # Order states by emission variance (ascending → 0=LOW, n-1=HIGH)
            variances = np.array([model.covars_[i, 0, 0] for i in range(n_states)])
            order = np.argsort(variances)  # idx of state ordered low→high vol
            # Apply to oos segment
            oos_data = log_returns.iloc[start_idx:end_idx].values.reshape(-1, 1)
            if len(oos_data) > 0:
                # Posterior for each state at each time
                posteriors = model.predict_proba(oos_data)
                # Reorder to variance-sorted
                posteriors_sorted = posteriors[:, order]  # cols: low → high vol
                states_sorted = posteriors_sorted.argmax(axis=1)  # 0=LOW, n-1=HIGH
                post_high = posteriors_sorted[:, -1]  # HIGH state posterior
                oos_times = log_returns.iloc[start_idx:end_idx].index
                out_state.loc[oos_times] = states_sorted
                out_post_high.loc[oos_times] = post_high
        except Exception as e:
            log.warning(f"HMM fit failed at idx {start_idx}: {e}")
        start_idx = end_idx

    df = pd.DataFrame({
        "state": out_state,
        "posterior_high": out_post_high,
    })
    df["high_conf"] = ((df["state"] == HMM_N_STATES - 1) & (df["posterior_high"] >= HMM_POSTERIOR_MIN)).astype(int)
    return df


def evaluate_quadrant(
    label: str, per_sym_returns: Dict[str, np.ndarray], pool_returns: np.ndarray,
    per_sym_quarter_returns: Dict[str, Dict[str, np.ndarray]],
) -> Dict:
    """Same as paradigm 120 evaluate_quadrant — 3-gate + Concentration + life-changing."""
    all_obs = np.concatenate([v for v in per_sym_returns.values() if len(v) > 0])
    n_obs = len(all_obs)
    if n_obs < 30:
        return {
            "quadrant": label, "n_obs": n_obs, "verdict": "SAMPLE_INSUFFICIENT",
            "error": "n_obs < 30",
        }

    mean_bp = float(all_obs.mean() * 1e4)
    median_bp = float(np.median(all_obs) * 1e4)
    sd = float(all_obs.std(ddof=1))
    obs_t = float(all_obs.mean() / sd * math.sqrt(n_obs)) if sd > 0 else 0.0

    fee_res = fee_aware_perm_test(
        observed_net_returns=all_obs, candidate_pool_returns=pool_returns,
        fee_per_trade=FEE_PER_TRADE, n_perms=1000, rng_seed=RNG_SEED,
    )
    ci_res = bootstrap_ci(all_obs, n_boot=2000, block_size=4, alpha=0.05, rng_seed=RNG_SEED)

    sym_ci = {}
    sym_ci_pos_count = 0
    sym_measurable = 0
    for sym, arr in per_sym_returns.items():
        if len(arr) < 20:
            sym_ci[sym] = {"n": len(arr), "ci_pos": None}
            continue
        sym_measurable += 1
        s_ci = bootstrap_ci(arr, n_boot=500, block_size=4, alpha=0.05, rng_seed=RNG_SEED)
        ci_pos = s_ci["ci_lower"] > 0
        if ci_pos:
            sym_ci_pos_count += 1
        sym_ci[sym] = {
            "n": int(len(arr)),
            "mean_bp": float(arr.mean() * 1e4),
            "ci_lower_bp": float(s_ci["ci_lower"] * 1e4),
            "ci_upper_bp": float(s_ci["ci_upper"] * 1e4),
            "ci_pos": bool(ci_pos),
        }

    quarter_stats = {}
    quarter_pos_t = 0
    quarter_measurable = 0
    quarter_keys: set = set()
    for q_dict in per_sym_quarter_returns.values():
        quarter_keys.update(q_dict.keys())
    for q in sorted(quarter_keys):
        q_arr = []
        for sym, qd in per_sym_quarter_returns.items():
            if q in qd and len(qd[q]) > 0:
                q_arr.append(qd[q])
        if not q_arr:
            continue
        q_concat = np.concatenate(q_arr)
        if len(q_concat) < 15:
            quarter_stats[q] = {"n": len(q_concat), "t": None, "skipped": True}
            continue
        quarter_measurable += 1
        q_sd = q_concat.std(ddof=1)
        q_t = float(q_concat.mean() / q_sd * math.sqrt(len(q_concat))) if q_sd > 0 else 0.0
        if q_t > 0:
            quarter_pos_t += 1
        quarter_stats[q] = {
            "n": int(len(q_concat)),
            "mean_bp": float(q_concat.mean() * 1e4),
            "t": float(q_t),
            "skipped": False,
        }

    quarter_pos_t_ratio = quarter_pos_t / quarter_measurable if quarter_measurable > 0 else 0.0
    sym_ci_pos_ratio = sym_ci_pos_count / sym_measurable if sym_measurable > 0 else 0.0

    gate_sigex = fee_res.get("signal_t_excess", float("nan"))
    gate_ci = ci_res.get("ci_lower", float("nan"))
    direction_one_sided = (
        fee_res.get("perm_p_one_sided_above")
        if "LONG" in label else fee_res.get("perm_p_one_sided_below")
    )
    gate_perm = direction_one_sided if direction_one_sided is not None else fee_res.get(
        "perm_p_two_sided", float("nan")
    )

    pass_sigex = (not math.isnan(gate_sigex)) and gate_sigex >= GATE_SIGEX_MIN
    pass_ci = (not math.isnan(gate_ci)) and gate_ci > GATE_CI_LOWER_MIN
    pass_perm = (not math.isnan(gate_perm)) and gate_perm <= GATE_PERM_P_MAX
    three_gate_pass = pass_sigex and pass_ci and pass_perm

    conc_pass = (
        quarter_pos_t_ratio >= CONC_QUARTER_POS_T_MIN
        and sym_ci_pos_ratio >= CONC_SYM_CI_POS_RATIO_MIN
        and sym_ci_pos_count >= CONC_N_SYMS_CI_POS_MIN
    )

    per_trade_edge_pct = mean_bp / 100.0
    life_changing_pass = per_trade_edge_pct >= LIFE_CHANGING_EDGE_MIN_PCT

    return {
        "quadrant": label,
        "n_obs": int(n_obs),
        "n_syms_measurable": int(sym_measurable),
        "mean_bp": mean_bp,
        "median_bp": median_bp,
        "obs_t": obs_t,
        "fee_aware_perm": fee_res,
        "bootstrap_ci_bp": {
            "mean_bp": float(ci_res["mean"] * 1e4),
            "ci_lower_bp": float(ci_res["ci_lower"] * 1e4) if not math.isnan(ci_res.get("ci_lower", float("nan"))) else float("nan"),
            "ci_upper_bp": float(ci_res["ci_upper"] * 1e4) if not math.isnan(ci_res.get("ci_upper", float("nan"))) else float("nan"),
            "prob_positive": ci_res.get("prob_positive", float("nan")),
            "n": ci_res.get("n"),
        },
        "three_gate": {
            "signal_t_excess": gate_sigex,
            "ci_lower_bp": float(gate_ci * 1e4) if not math.isnan(gate_ci) else float("nan"),
            "perm_p_directional": gate_perm,
            "pass_sigex": bool(pass_sigex),
            "pass_ci": bool(pass_ci),
            "pass_perm": bool(pass_perm),
            "pass_all": bool(three_gate_pass),
        },
        "concentration": {
            "quarter_stats": quarter_stats,
            "n_quarters_measurable": int(quarter_measurable),
            "quarter_pos_t_ratio": float(quarter_pos_t_ratio),
            "per_symbol_ci": sym_ci,
            "n_symbols_ci_pos": int(sym_ci_pos_count),
            "sym_ci_pos_ratio": float(sym_ci_pos_ratio),
            "concentration_gate_pass": bool(conc_pass),
        },
        "life_changing": {
            "per_trade_edge_pct": float(per_trade_edge_pct),
            "edge_threshold_pct": LIFE_CHANGING_EDGE_MIN_PCT,
            "pass": bool(life_changing_pass),
        },
    }


def main() -> int:
    t0 = time.time()
    log.info(f"paradigm {PARADIGM_ID} R-1 — {PARADIGM_NAME}")
    if not HMM_AVAILABLE:
        log.error("hmmlearn not available — cannot proceed")
        return 4
    log.info(f"Universe: {len(ALTS)} alts (paradigm 105 cache subset)")

    # 1. Build per-sym basis 1h series + HMM walk-forward fit
    sym_data: Dict[str, pd.DataFrame] = {}
    pool_returns_all: List[float] = []

    for sym in ALTS:
        log.info(f"Loading {sym} mark+index...")
        mark5, index5 = load_mark_index(sym)
        m1h = aggregate_1h(mark5)
        i1h = aggregate_1h(index5)
        df = pd.DataFrame({"mark": m1h, "index": i1h}).dropna()
        df["basis_pct"] = (df["mark"] - df["index"]) / df["index"]
        df["basis_mu"] = df["basis_pct"].rolling(ROLLING_WIN_1H, min_periods=ROLLING_WIN_1H // 2).mean()
        df["basis_sd"] = df["basis_pct"].rolling(ROLLING_WIN_1H, min_periods=ROLLING_WIN_1H // 2).std()
        df["basis_z"] = (df["basis_pct"] - df["basis_mu"]) / df["basis_sd"].replace(0, np.nan)
        df["basis_z"] = df["basis_z"].replace([np.inf, -np.inf], np.nan)
        df["log_ret_1h"] = np.log(df["mark"]).diff()
        df["mark_fwd_4h"] = df["mark"].shift(-HOLD_BARS_1H) / df["mark"] - 1.0

        # HMM walk-forward fit on log_ret_1h
        log.info(f"  HMM walk-forward fit (n_states={HMM_N_STATES}, train={HMM_TRAIN_WIN_DAYS}d, refit={HMM_REFIT_FREQ_DAYS}d)...")
        hmm_df = fit_hmm_walk_forward(df["log_ret_1h"])
        df = df.join(hmm_df)
        df = df.dropna(subset=["basis_z", "mark_fwd_4h", "high_conf"])
        sym_data[sym] = df

        hc_rate = float(df["high_conf"].mean())
        z_rate = float((df["basis_z"].abs() > BASIS_Z_THRESHOLD).mean())
        log.info(f"  {sym}: n_aligned={len(df)}, HMM HIGH-conf rate={hc_rate:.2%}, |basis z|>2 rate={z_rate:.2%}")

        # Pool sample for fee-aware perm (random gross 4h returns)
        pool_returns_all.extend(df["mark_fwd_4h"].sample(
            n=min(3000, len(df)), random_state=RNG_SEED
        ).tolist())

    pool_arr = np.array(pool_returns_all)
    log.info(f"Pool size for fee-aware perm: {len(pool_arr)}")

    # 2. Build 4 quadrants
    def quadrant_trades(
        trigger_mask: pd.Series, fwd: pd.Series, direction: int
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        triggered_idx = trigger_mask[trigger_mask].index
        if len(triggered_idx) == 0:
            return np.array([]), {}
        # Dedup: 4h hold = 4 1h bars
        kept = [triggered_idx[0]]
        for ts in triggered_idx[1:]:
            if (ts - kept[-1]).total_seconds() / 3600 >= HOLD_BARS_1H:
                kept.append(ts)
        kept = pd.DatetimeIndex(kept)
        rets = fwd.reindex(kept).dropna()
        nets = direction * rets.values - FEE_PER_TRADE
        q_map = {ts: f"{ts.year}Q{((ts.month-1)//3)+1}" for ts in rets.index}
        q_dict: Dict[str, List[float]] = {}
        for ts, net in zip(rets.index, nets):
            q = q_map[ts]
            q_dict.setdefault(q, []).append(net)
        q_arr = {q: np.array(vs) for q, vs in q_dict.items()}
        return nets, q_arr

    quadrants = {
        "A_focus_zpos_HIGHvol_SHORT_4h": (
            lambda d: (d["basis_z"] > BASIS_Z_THRESHOLD) & (d["high_conf"] == 1), -1,
        ),
        "A_mirror_zpos_HIGHvol_LONG_4h": (
            lambda d: (d["basis_z"] > BASIS_Z_THRESHOLD) & (d["high_conf"] == 1), +1,
        ),
        "B_focus_zneg_HIGHvol_LONG_4h": (
            lambda d: (d["basis_z"] < -BASIS_Z_THRESHOLD) & (d["high_conf"] == 1), +1,
        ),
        "B_mirror_zneg_HIGHvol_SHORT_4h": (
            lambda d: (d["basis_z"] < -BASIS_Z_THRESHOLD) & (d["high_conf"] == 1), -1,
        ),
    }

    results: Dict[str, Dict] = {}
    for q_label, (trigger_fn, direction) in quadrants.items():
        log.info(f"=== Quadrant {q_label} ===")
        per_sym_rets: Dict[str, np.ndarray] = {}
        per_sym_quarter_rets: Dict[str, Dict[str, np.ndarray]] = {}
        for sym, d in sym_data.items():
            mask = trigger_fn(d)
            nets, q_arr = quadrant_trades(mask, d["mark_fwd_4h"], direction)
            per_sym_rets[sym] = nets
            per_sym_quarter_rets[sym] = q_arr
            log.info(f"  {sym}: n_trades={len(nets)}, mean_bp={nets.mean()*1e4 if len(nets)>0 else 0:.2f}")

        res = evaluate_quadrant(q_label, per_sym_rets, pool_arr, per_sym_quarter_rets)
        results[q_label] = res

    # 3. Overall verdict — same tree as paradigm 120
    pass_quadrants = [q for q, r in results.items() if r.get("three_gate", {}).get("pass_all", False)]
    conc_pass_quadrants = [
        q for q, r in results.items()
        if r.get("three_gate", {}).get("pass_all", False)
        and r.get("concentration", {}).get("concentration_gate_pass", False)
    ]
    life_pass_quadrants = [
        q for q in conc_pass_quadrants
        if results[q].get("life_changing", {}).get("pass", False)
    ]

    # Lesson #39 symmetric check (A_focus + A_mirror exact ±k bp)
    a_focus = results.get("A_focus_zpos_HIGHvol_SHORT_4h", {})
    a_mirror = results.get("A_mirror_zpos_HIGHvol_LONG_4h", {})
    symmetric_diff_bp = None
    if a_focus.get("mean_bp") is not None and a_mirror.get("mean_bp") is not None:
        symmetric_diff_bp = abs(abs(a_focus["mean_bp"]) - abs(a_mirror["mean_bp"]))

    if not pass_quadrants:
        if symmetric_diff_bp is not None and symmetric_diff_bp < 5.0:
            verdict = "BROAD_FALSIFIED_LESSON39_SYMMETRIC_NO_AXIS_SYNTHESIS"
        else:
            # Check if focus quadrant has gross drift > fee floor (mechanism positive, fee-bound)
            a_focus_gross = a_focus.get("mean_bp", 0) + FEE_PER_TRADE * 1e4
            b_focus = results.get("B_focus_zneg_HIGHvol_LONG_4h", {})
            b_focus_gross = b_focus.get("mean_bp", 0) + FEE_PER_TRADE * 1e4
            if abs(a_focus_gross) > 16.0 or abs(b_focus_gross) > 16.0:
                verdict = "BROAD_FALSIFIED_FEE_FLOOR_GROSS_INSUFFICIENT"
            else:
                verdict = "BROAD_FALSIFIED"
    elif life_pass_quadrants:
        verdict = "PASS_R1_FULL"
    elif conc_pass_quadrants:
        verdict = "PASS_R1_LIFE_CHANGING_FAIL"
    else:
        verdict = "DIFFUSE_POSITIVE_CONCENTRATION_FAIL"

    elapsed = time.time() - t0
    metrics = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_id": PARADIGM_ID,
        "hypothesis": "HMM HIGH-vol state (per-sym 3-state Gaussian, weekly WF, posterior>=0.8) × markPrice basis 1h |z|>2 × 4-quadrant 4h directional",
        "type": "E",
        "universe": ALTS,
        "params": {
            "rolling_win_1h_basis": ROLLING_WIN_1H,
            "hold_bars_1h": HOLD_BARS_1H,
            "basis_z_threshold": BASIS_Z_THRESHOLD,
            "hmm_n_states": HMM_N_STATES,
            "hmm_posterior_min": HMM_POSTERIOR_MIN,
            "hmm_train_win_days": HMM_TRAIN_WIN_DAYS,
            "hmm_refit_freq_days": HMM_REFIT_FREQ_DAYS,
            "fee_per_trade": FEE_PER_TRADE,
        },
        "quadrants": results,
        "summary": {
            "pass_three_gate_quadrants": pass_quadrants,
            "pass_concentration_gate_quadrants": conc_pass_quadrants,
            "pass_life_changing_quadrants": life_pass_quadrants,
            "lesson39_symmetric_diff_bp": symmetric_diff_bp,
            "verdict": verdict,
        },
        "lesson45_candidate_umbrella_path_verification": {
            "framework_used": "HMM as conditioning filter + external orthogonal axis (markPrice basis)",
            "vs_paradigm_119_endogenous_only": "paradigm 119 used HMM state-identity as direct trigger → BROAD_FALSIFIED. paradigm 121 uses HMM as filter not trigger.",
            "verdict_class": (
                "REFINE_LESSON45_HMM_FILTER_OK" if "PASS" in verdict
                else "STRENGTHEN_LESSON45_HMM_UMBRELLA_BROKEN"
            ),
        },
        "lesson46_candidate_2nd_dogfood": {
            "r0_prescreen_gross_drift_a_focus_bp": 43.46,
            "r0_prescreen_gross_drift_a_focus_n": 202,
            "r0_prescreen_passed": True,
            "r1_focus_realized_net_bp": results.get("A_focus_zpos_HIGHvol_SHORT_4h", {}).get("mean_bp"),
            "validation_class": (
                "CONFIRM_LESSON46" if "PASS" in verdict else "DECLINE_LESSON46_R0_PROXY_DECEIVED"
            ),
        },
        "wall_clock_seconds": elapsed,
    }
    out_path = OUTPUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    log.info(f"Wrote {out_path} (wall={elapsed:.1f}s)")
    log.info(f"VERDICT: {verdict}")
    log.info(f"  pass_three_gate={pass_quadrants}")
    log.info(f"  pass_concentration={conc_pass_quadrants}")
    log.info(f"  pass_life_changing={life_pass_quadrants}")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.parse_args()
    sys.exit(main())
