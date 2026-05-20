"""Paradigm 115 — alt_atr_normalized_range_breakout_continuation_long_2h R-1 PoC

Hypothesis
----------
Paradigm 114 (raw 24h trailing-high breakout, debounced, 13-alt × 2h hold)
confirmed mechanism IS real: A_focus gross +5.41bp, sigex +2.54, perm_p
one-sided 0.006 — but net -2.59bp = BROAD_FALSIFIED_FEE_FLOOR (8 bp / leg
round-trip).

Paradigm 114 explicitly recommended ATR-normalized follow-up: only "genuine"
breakouts where close strictly clears the prior 24h max by k×ATR_14d
buffer. Hypothesis: noise breakouts (close kissing the line) drag the mean;
filtering them out concentrates alpha into a tighter subset that may clear
16bp fee floor at appropriate k.

Trigger (4-quadrant SNT per Lesson #19, per k value)
  A_focus  : close > prior_24h_max + k×ATR_14d AND debounced -> LONG (continuation)
  A_mirror : same trigger -> SHORT (wrong direction)
  B_same   : close < prior_24h_min - k×ATR_14d AND debounced -> SHORT (continuation)
  B_mirror : same trigger -> LONG (wrong direction)

k sweep: [0.5, 1.0, 1.5] (1.5 = aggressive subset selection, ~30-50% fewer events)

5-axis novelty self-check vs paradigm 114
  - Statistic = close > rolling_max + k×ATR (NOVEL, vol-normalized buffer
    not raw price-level; paradigm 114 was pure deterministic crossing)
  - Universe = 13-alt (NOT NOVEL)
  - Frame = 1h × 2h (NOT NOVEL vs 114)
  - Mechanism = vol-conditioned level-crossing (NOVEL — intra-paradigm
    subset selection by volatility band, distinct from raw threshold)
  - Trigger = k-buffer parameter family k∈{0.5,1.0,1.5} (NOVEL — sweep
    construct vs single-binary 114)
  Verdict: 3/5 NOVEL — proceed.

DNA collision check
  - vs paradigm 114 alt_range_breakout_24h_trailing_high_continuation_long_2h:
    3/5 dim distinct (statistic, mechanism, trigger). NOT a DNA collision —
    paradigm 114 explicit follow-up reco.
  - vs paradigm `range_compression_directional_break_alt_30m_240m`
    (graveyard 2026-05-15): uses path tortuosity z + |return|>2×vol
    (compression -> expansion). Different statistic (vol compression vs
    rolling-extremum buffer), different mechanism (volatility regime
    transition vs price-level escape with vol buffer). NOT a DNA collision.

Lesson prescreens
  - #11 sample density: 114 had 2,858 debounced raw breakouts. k=0.5 ~ 70%
    retention ≈ 2,000, k=1.0 ~ 50% ≈ 1,400, k=1.5 ~ 30% ≈ 850. Per-cell
    (4-quadrant × 9 quarters) ≈ 23-55 at k=1.5 — MARGINAL but should PASS
    floor 30 at k≤1.0. Document empirical trigger rate per k.
  - #19 SNT: 4-quadrant in single batch per k.
  - #20 narrow-scope: tested per k via life-changing 4-dim.
  - #21 axis stacking: joint (breakout × ATR buffer) vs raw breakout
    (paradigm 114 result is the diagnostic baseline — joint must beat
    +5.41bp at SOME k to demonstrate synthesis).
  - #28 substrate availability: paradigm 113 1h OHLCV cache (verified).
  - #30 data window ratio: 2yr / 2.4yr ≈ 83%. PASS.
  - #34 empirical distribution: trigger rate measured + logged per k.
  - #35 fee-trap distinction: if all k FAIL fee floor → 3rd dogfood + level-
    crossing single-domain family Tier 4 retire eligible (104 + 114 + 115).
  - #39 sub-class A antipattern: pure price-level breakout inherently
    asymmetric, BUT here we add symmetric ±k×ATR buffer; check whether
    A_focus + A_mirror perfectly mirror per k.
  - #40 structural threshold feasibility: rolling max + k×ATR trivially
    reachable in trending markets. PASS.

R-1 body
  - Per k ∈ {0.5, 1.0, 1.5}: 4-quadrant SNT + 3-gate + Concentration Gate
    + life-changing 4-dim.
  - fee_aware_perm_test + bootstrap_ci via _perm_utils.
  - 16bp fee floor.
  - Lesson #21 axis-stacking diagnostic: compare best k joint vs paradigm
    114 raw +5.41bp baseline.
  - Hold sweep [1, 2, 4] hours on best-k A_focus (Lesson #37 sweep scan).

Scope
  - 13 alts (paradigm 113/114 universe).
  - 24 months 2024-05..2026-04 from paradigm 113 cache.
"""
from __future__ import annotations

import io
import json
import logging
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path("/home/hcpark/antigravity/backend")
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

PARADIGM_SLUG = "alt_atr_normalized_range_breakout_continuation_long_2h"
PARADIGM_NUMBER = 115
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_SLUG
OUT_DIR.mkdir(parents=True, exist_ok=True)

SHARED_CACHE_DIR = (
    ROOT
    / "runs"
    / "research_track"
    / "intraday_hour_of_day_anchor_alt_directional_2h"
    / "klines_cache"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(OUT_DIR / "r1__stdout.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("p115_r1")

ALTS = [
    "SOLUSDT", "HBARUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT",
    "ADAUSDT", "BCHUSDT", "LTCUSDT", "BNBUSDT", "FILUSDT",
    "NEARUSDT", "XRPUSDT", "ETHUSDT",
]

START_MONTH = "2024-05"
END_MONTH = "2026-04"

FEE_PER_TRADE = 0.0008  # 16 bp round-trip
ROLLING_WINDOW_BARS = 24
DEBOUNCE_BARS = 12
PRIMARY_HOLD_BARS = 2
HOLD_SWEEP_BARS = [1, 2, 4]
ATR_BARS = 14 * 24  # 14 days × 24 hourly bars rolling
K_SWEEP = [0.5, 1.0, 1.5]
PRIMARY_K = 1.0


def month_iter(start: str, end: str) -> list[str]:
    s = pd.Period(start, freq="M")
    e = pd.Period(end, freq="M")
    return [str(p) for p in pd.period_range(s, e, freq="M")]


def load_1h_klines_from_cache(sym: str, month: str) -> pd.DataFrame:
    cache_file = SHARED_CACHE_DIR / f"{sym}_1h_{month}.joblib"
    if cache_file.exists():
        try:
            return joblib.load(cache_file)
        except Exception as e:
            log.warning("cache load fail %s %s: %s", sym, month, e)
            return pd.DataFrame()
    log.warning("cache miss %s %s", sym, month)
    return pd.DataFrame()


def build_1h_panel(sym: str, months: list[str]) -> pd.DataFrame:
    parts = []
    for m in months:
        d = load_1h_klines_from_cache(sym, m)
        if not d.empty:
            parts.append(d)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    return out


def compute_atr(df: pd.DataFrame, n_bars: int) -> pd.Series:
    """Rolling ATR (Wilder-style approximation; SMA of true range)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(n_bars, min_periods=n_bars).mean()
    return atr


def compute_quadrant(
    quadrant_name: str,
    trigger_mask_per_sym: dict,
    fwd_per_sym: dict,
    direction_per_sym: dict,
    hold_bars: int,
    fee: float,
    candidate_pool_pool: np.ndarray,
) -> dict:
    """3-gate + Concentration + per-quarter + per-sym + life-changing."""
    trades_per_sym: dict[str, list[float]] = {s: [] for s in trigger_mask_per_sym}
    ts_per_sym: dict[str, list[pd.Timestamp]] = {s: [] for s in trigger_mask_per_sym}

    for s, mask in trigger_mask_per_sym.items():
        fwd = fwd_per_sym.get(s)
        d = direction_per_sym[s]
        if fwd is None or len(fwd) == 0:
            continue
        idx_trig = mask.index[mask & fwd.notna()]
        if len(idx_trig) == 0:
            continue
        min_gap = pd.Timedelta(hours=hold_bars)
        last_t = None
        for t in idx_trig:
            if last_t is None or (t - last_t) >= min_gap:
                trades_per_sym[s].append(d * float(fwd.loc[t]))
                ts_per_sym[s].append(t)
                last_t = t

    all_trades: list[float] = []
    all_ts: list[pd.Timestamp] = []
    all_sym: list[str] = []
    for s, lst in trades_per_sym.items():
        all_trades.extend(lst)
        all_ts.extend(ts_per_sym[s])
        all_sym.extend([s] * len(lst))

    if len(all_trades) < 5:
        return {
            "quadrant": quadrant_name,
            "hold_bars": hold_bars,
            "hold_hours": hold_bars,
            "n_trades": len(all_trades),
            "error": "n_trades<5",
        }

    gross = np.asarray(all_trades, dtype=float)
    net = gross - fee
    sd = net.std(ddof=1)
    obs_t = float(net.mean() / sd * np.sqrt(len(net))) if sd > 0 else 0.0
    gross_mean_bp = float(gross.mean() * 10000)
    net_mean_bp = float(net.mean() * 10000)

    ci = bootstrap_ci(net, n_boot=1000, rng_seed=42)

    if len(candidate_pool_pool) < len(net) * 2:
        perm = {
            "perm_p_two_sided": float("nan"),
            "signal_t_excess": float("nan"),
            "null_mean_t": float("nan"),
            "perm_p_one_sided_above": float("nan"),
        }
    else:
        perm = fee_aware_perm_test(
            net, candidate_pool_pool, fee_per_trade=fee, n_perms=1000, rng_seed=42
        )

    per_sym_ci = {}
    for s, lst in trades_per_sym.items():
        if len(lst) < 5:
            per_sym_ci[s] = {"n": len(lst), "ci_lower_bp": float("nan"), "ci_pos": False}
            continue
        net_s = np.asarray(lst) - fee
        ci_s = bootstrap_ci(net_s, n_boot=500, rng_seed=42)
        per_sym_ci[s] = {
            "n": int(len(lst)),
            "mean_bp": float(net_s.mean() * 10000),
            "ci_lower_bp": float(ci_s["ci_lower"] * 10000),
            "ci_upper_bp": float(ci_s["ci_upper"] * 10000),
            "ci_pos": bool(ci_s["ci_lower"] > 0),
        }
    n_syms_ci_pos = sum(1 for v in per_sym_ci.values() if v["ci_pos"])
    syms_ci_pos_ratio = n_syms_ci_pos / len(per_sym_ci) if per_sym_ci else 0.0

    df_q = pd.DataFrame({"ts": all_ts, "ret": net, "sym": all_sym})
    df_q["quarter"] = pd.to_datetime(df_q["ts"]).dt.to_period("Q").astype(str)
    per_q = {}
    for q, sub in df_q.groupby("quarter"):
        if len(sub) < 5:
            per_q[q] = {"n": int(len(sub)), "t": float("nan"), "pos_t": False}
            continue
        sd_q = sub["ret"].std(ddof=1)
        tq = sub["ret"].mean() / sd_q * np.sqrt(len(sub)) if sd_q > 0 else 0
        per_q[q] = {
            "n": int(len(sub)),
            "mean_bp": float(sub["ret"].mean() * 10000),
            "t": float(tq),
            "pos_t": bool(tq > 0),
        }
    n_q_measurable = sum(1 for v in per_q.values() if pd.notna(v["t"]) and v["n"] >= 5)
    n_q_pos = sum(1 for v in per_q.values() if v["pos_t"] and v["n"] >= 5)
    q_pos_ratio = n_q_pos / n_q_measurable if n_q_measurable > 0 else 0.0

    gate_3 = bool(
        perm.get("signal_t_excess", float("nan")) >= 2.0
        and ci["ci_lower"] > 0
        and perm.get("perm_p_two_sided", 1.0) <= 0.10
    )
    gate_conc = bool(
        q_pos_ratio >= 0.5 and syms_ci_pos_ratio >= 0.30 and n_syms_ci_pos >= 3
    )

    if all_ts:
        n_years = max(
            1e-6, (pd.to_datetime(max(all_ts)) - pd.to_datetime(min(all_ts))).days / 365.25
        )
    else:
        n_years = 1e-6
    trades_per_year = len(net) / n_years
    per_trade_edge_pct = net_mean_bp / 100.0
    capital_util_pct = min(100.0, (hold_bars * trades_per_year) / (365.25 * 24) * 100)
    sharpe_annual = (net.mean() / sd) * np.sqrt(trades_per_year) if sd > 0 else 0.0
    life_changing_dims = {
        "trades_per_year": float(trades_per_year),
        "per_trade_edge_pct": float(per_trade_edge_pct),
        "capital_util_pct": float(capital_util_pct),
        "annualized_sharpe": float(sharpe_annual),
        "pass_trades_per_year_12": bool(trades_per_year >= 12),
        "pass_edge_2pct": bool(per_trade_edge_pct >= 2.0),
        "pass_util_30pct": bool(capital_util_pct >= 30),
        "pass_sharpe_1_5": bool(sharpe_annual >= 1.5),
        "pass_all_4_dim": bool(
            trades_per_year >= 12
            and per_trade_edge_pct >= 2.0
            and capital_util_pct >= 30
            and sharpe_annual >= 1.5
        ),
    }

    return {
        "quadrant": quadrant_name,
        "hold_bars": hold_bars,
        "hold_hours": hold_bars,
        "n_trades": int(len(net)),
        "n_trades_per_sym": {s: int(len(trades_per_sym[s])) for s in trades_per_sym},
        "obs_mean_gross_bp": gross_mean_bp,
        "obs_mean_net_bp": net_mean_bp,
        "obs_t": obs_t,
        "ci_lower_bp": float(ci["ci_lower"] * 10000),
        "ci_upper_bp": float(ci["ci_upper"] * 10000),
        "ci_pos": bool(ci["ci_lower"] > 0),
        "perm_p_two_sided": float(perm.get("perm_p_two_sided", float("nan"))),
        "perm_p_one_sided_above": float(perm.get("perm_p_one_sided_above", float("nan"))),
        "null_mean_t": float(perm.get("null_mean_t", float("nan"))),
        "signal_t_excess": float(perm.get("signal_t_excess", float("nan"))),
        "gate_3_pass": gate_3,
        "per_quarter": per_q,
        "n_q_measurable": int(n_q_measurable),
        "n_q_pos": int(n_q_pos),
        "q_pos_ratio": float(q_pos_ratio),
        "per_symbol_ci": per_sym_ci,
        "n_syms_ci_pos": int(n_syms_ci_pos),
        "n_syms_total": len(per_sym_ci),
        "syms_ci_pos_ratio": float(syms_ci_pos_ratio),
        "gate_concentration_pass": gate_conc,
        "life_changing_4dim": life_changing_dims,
    }


def main() -> int:
    t_start = time.time()
    out: dict = {
        "paradigm_name": PARADIGM_SLUG,
        "paradigm_number": PARADIGM_NUMBER,
        "phase": "R-1",
        "executed_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "host": "hcp_local",
        "universe_alts": ALTS,
        "n_alts": len(ALTS),
        "window_months": [START_MONTH, END_MONTH],
        "fee_per_trade": FEE_PER_TRADE,
        "rolling_window_bars": ROLLING_WINDOW_BARS,
        "debounce_bars": DEBOUNCE_BARS,
        "primary_hold_bars": PRIMARY_HOLD_BARS,
        "primary_hold_hours": PRIMARY_HOLD_BARS,
        "hold_sweep_bars": HOLD_SWEEP_BARS,
        "atr_bars": ATR_BARS,
        "k_sweep": K_SWEEP,
        "primary_k": PRIMARY_K,
        "paradigm_114_baseline": {
            "raw_breakUp_LONG_gross_bp": 5.41,
            "raw_breakUp_LONG_net_bp": -2.59,
            "raw_breakUp_LONG_sigex": 2.54,
            "raw_breakUp_LONG_n_trades": 2858,
            "verdict": "BROAD_FALSIFIED_FEE_FLOOR",
        },
        "novelty_self_check": {
            "statistic": "NOVEL (close > rolling_max + k×ATR vs paradigm 114 pure rolling_max)",
            "universe": "NOT NOVEL (same 13 alts)",
            "frame": "NOT NOVEL (same 1h × 2h)",
            "mechanism": "NOVEL (vol-conditioned subset selection)",
            "trigger": "NOVEL (k-buffer parameter family k∈{0.5,1.0,1.5})",
            "axes_pass": 3,
            "verdict": "3/5 NOVEL — proceed",
        },
        "substrate_source": "paradigm113_klines_cache_reuse",
    }

    months = month_iter(START_MONTH, END_MONTH)
    log.info(
        "loading 1h klines for %d alts × %d months from cache",
        len(ALTS), len(months),
    )
    t_bf = time.time()
    panel: dict[str, pd.DataFrame] = {}
    for s in ALTS:
        t0 = time.time()
        df = build_1h_panel(s, months)
        log.info("  %s: %d rows in %.1fs", s, len(df), time.time() - t0)
        if not df.empty:
            panel[s] = df
    bf_secs = time.time() - t_bf
    log.info("cache load done in %.1fs", bf_secs)

    if len(panel) < 5:
        out["verdict"] = "DISPATCH_IMPOSSIBLE"
        out["verdict_reason"] = f"cache load produced only {len(panel)}/13 series"
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        return 1

    # Build per-sym close + rolling max/min + ATR
    close_per_sym: dict[str, pd.Series] = {}
    rolling_max_per_sym: dict[str, pd.Series] = {}
    rolling_min_per_sym: dict[str, pd.Series] = {}
    atr_per_sym: dict[str, pd.Series] = {}
    for s, df in panel.items():
        c = df["close"].copy()
        close_per_sym[s] = c
        rolling_max_per_sym[s] = c.shift(1).rolling(
            ROLLING_WINDOW_BARS, min_periods=ROLLING_WINDOW_BARS
        ).max()
        rolling_min_per_sym[s] = c.shift(1).rolling(
            ROLLING_WINDOW_BARS, min_periods=ROLLING_WINDOW_BARS
        ).min()
        atr_abs = compute_atr(df, ATR_BARS)
        # ATR normalized by close (proportional band); shift(1) to avoid look-ahead
        atr_per_sym[s] = (atr_abs / c).shift(1)

    # Forward H-bar log returns per hold
    fwd_per_sym_by_hold: dict[int, dict[str, pd.Series]] = {}
    for h in HOLD_SWEEP_BARS:
        d = {}
        for s, c in close_per_sym.items():
            d[s] = np.log(c.shift(-h) / c)
        fwd_per_sym_by_hold[h] = d

    fwd_primary = fwd_per_sym_by_hold[PRIMARY_HOLD_BARS]
    pool_long = np.concatenate(
        [f.dropna().values for f in fwd_primary.values()]
    ) if fwd_primary else np.array([])
    pool_short = -pool_long

    dir_long = {s: +1 for s in panel}
    dir_short = {s: -1 for s in panel}

    # Empirical trigger rate per k (Lesson #34)
    n_bars_total = sum(int(close_per_sym[s].notna().sum()) for s in panel)
    empirical_per_k = {}

    # Per-k 4-quadrant + diagnostics
    per_k_results: dict = {}
    for k in K_SWEEP:
        log.info("=== k = %.2f === computing ATR-buffered breakout masks", k)
        atr_up_per_sym: dict[str, pd.Series] = {}
        atr_dn_per_sym: dict[str, pd.Series] = {}
        for s in panel:
            c = close_per_sym[s]
            rmax = rolling_max_per_sym[s]
            rmin = rolling_min_per_sym[s]
            atr_norm = atr_per_sym[s]
            # close > rolling_max × (1 + k × atr_norm) equivalent: close - rmax > k × atr_abs
            # but since atr_per_sym is ATR/close ratio (relative), we use:
            # close > rmax * (1 + k * atr_norm) approximated as:
            # close > rmax + k * atr_norm * c.shift(1) (prev close * relative ATR ~ ATR_abs)
            buffer_abs = k * atr_norm * c.shift(1)  # approx ATR magnitude
            atr_up_per_sym[s] = ((c > (rmax + buffer_abs)) & rmax.notna() & atr_norm.notna()).astype(bool)
            atr_dn_per_sym[s] = ((c < (rmin - buffer_abs)) & rmin.notna() & atr_norm.notna()).astype(bool)

        # Debounce: no prior breakout (raw OR atr) in last DEBOUNCE_BARS — use ATR-buffered events only
        deb_up_per_sym: dict[str, pd.Series] = {}
        deb_dn_per_sym: dict[str, pd.Series] = {}
        for s in panel:
            any_brk = (atr_up_per_sym[s] | atr_dn_per_sym[s]).astype(int)
            prior_count = any_brk.shift(1).rolling(
                DEBOUNCE_BARS, min_periods=1
            ).sum().fillna(0)
            fresh = prior_count == 0
            deb_up_per_sym[s] = (atr_up_per_sym[s] & fresh).astype(bool)
            deb_dn_per_sym[s] = (atr_dn_per_sym[s] & fresh).astype(bool)

        n_raw_up = int(sum(m.sum() for m in atr_up_per_sym.values()))
        n_raw_dn = int(sum(m.sum() for m in atr_dn_per_sym.values()))
        n_deb_up = int(sum(m.sum() for m in deb_up_per_sym.values()))
        n_deb_dn = int(sum(m.sum() for m in deb_dn_per_sym.values()))

        empirical_per_k[f"k_{k}"] = {
            "k": k,
            "atr_raw_up_breakouts": n_raw_up,
            "atr_raw_dn_breakouts": n_raw_dn,
            "atr_debounced_up_breakouts": n_deb_up,
            "atr_debounced_dn_breakouts": n_deb_dn,
            "atr_debounced_up_rate_pct": float(100 * n_deb_up / max(1, n_bars_total)),
            "atr_debounced_dn_rate_pct": float(100 * n_deb_dn / max(1, n_bars_total)),
            "retention_vs_paradigm114_up_pct": float(100 * n_deb_up / 2858),
            "retention_vs_paradigm114_dn_pct": float(100 * n_deb_dn / 2996),
        }
        log.info(
            "k=%.2f: deb up=%d dn=%d (retention vs p114: up=%.1f%% dn=%.1f%%)",
            k, n_deb_up, n_deb_dn,
            empirical_per_k[f"k_{k}"]["retention_vs_paradigm114_up_pct"],
            empirical_per_k[f"k_{k}"]["retention_vs_paradigm114_dn_pct"],
        )

        # Lesson #11 prescreen per-k
        if not panel:
            n_quarters = 1
        else:
            all_ts_idx = pd.concat([s for s in close_per_sym.values()], axis=1).index
            n_quarters = max(
                1, int(np.ceil((all_ts_idx.max() - all_ts_idx.min()).days / 91))
            )
        per_q_up = n_deb_up / max(1, PRIMARY_HOLD_BARS) / n_quarters
        per_q_dn = n_deb_dn / max(1, PRIMARY_HOLD_BARS) / n_quarters
        empirical_per_k[f"k_{k}"]["per_quarter_up"] = float(per_q_up)
        empirical_per_k[f"k_{k}"]["per_quarter_dn"] = float(per_q_dn)
        empirical_per_k[f"k_{k}"]["passes_lesson11_both"] = bool(per_q_up >= 30 and per_q_dn >= 30)

        if not (per_q_up >= 30 and per_q_dn >= 30):
            log.warning(
                "k=%.2f Lesson #11 FAIL per_q_up=%.1f per_q_dn=%.1f — skip quadrant computation",
                k, per_q_up, per_q_dn,
            )
            per_k_results[f"k_{k}"] = {
                "k": k,
                "skip_reason": "lesson11_sample_density_fail",
                "per_quarter_up": float(per_q_up),
                "per_quarter_dn": float(per_q_dn),
            }
            continue

        # 4-quadrant SNT for this k
        log.info("=== k=%.2f 4-quadrant SNT (primary hold=%dh) ===", k, PRIMARY_HOLD_BARS)
        quadrants_k = {}
        quadrants_k["A_focus_breakUp_LONG"] = compute_quadrant(
            f"A_focus_breakUp_LONG_k{k}",
            deb_up_per_sym,
            fwd_primary,
            dir_long,
            PRIMARY_HOLD_BARS,
            FEE_PER_TRADE,
            pool_long,
        )
        quadrants_k["A_mirror_breakUp_SHORT"] = compute_quadrant(
            f"A_mirror_breakUp_SHORT_k{k}",
            deb_up_per_sym,
            fwd_primary,
            dir_short,
            PRIMARY_HOLD_BARS,
            FEE_PER_TRADE,
            pool_short,
        )
        quadrants_k["B_same_sign_breakDn_SHORT"] = compute_quadrant(
            f"B_same_sign_breakDn_SHORT_k{k}",
            deb_dn_per_sym,
            fwd_primary,
            dir_short,
            PRIMARY_HOLD_BARS,
            FEE_PER_TRADE,
            pool_short,
        )
        quadrants_k["B_mirror_breakDn_LONG"] = compute_quadrant(
            f"B_mirror_breakDn_LONG_k{k}",
            deb_dn_per_sym,
            fwd_primary,
            dir_long,
            PRIMARY_HOLD_BARS,
            FEE_PER_TRADE,
            pool_long,
        )
        per_k_results[f"k_{k}"] = {"k": k, "quadrants": quadrants_k}

        # Lesson #39 symmetry diagnostic per k
        a_focus_gross = quadrants_k["A_focus_breakUp_LONG"].get("obs_mean_gross_bp", 0.0)
        a_mirror_gross = quadrants_k["A_mirror_breakUp_SHORT"].get("obs_mean_gross_bp", 0.0)
        sym_diff_abs = abs(a_focus_gross + a_mirror_gross)
        per_k_results[f"k_{k}"]["lesson39_symmetry"] = {
            "A_focus_gross_bp": a_focus_gross,
            "A_mirror_gross_bp": a_mirror_gross,
            "sum_abs_bp": float(sym_diff_abs),
            "is_perfect_mirror": bool(sym_diff_abs < 1.0),
        }

    out["lesson34_empirical_distribution_per_k"] = empirical_per_k
    out["per_k_results"] = per_k_results

    # Lesson #21 axis-stacking: ATR k=1.0 joint vs paradigm 114 raw baseline
    p114_baseline_gross = 5.41
    p114_baseline_net = -2.59
    stacking = {}
    for k in K_SWEEP:
        key = f"k_{k}"
        if "skip_reason" in per_k_results.get(key, {}):
            stacking[key] = {"skipped": True, "reason": per_k_results[key]["skip_reason"]}
            continue
        q = per_k_results[key]["quadrants"]["A_focus_breakUp_LONG"]
        stacking[key] = {
            "k": k,
            "A_focus_gross_bp": q.get("obs_mean_gross_bp", 0.0),
            "A_focus_net_bp": q.get("obs_mean_net_bp", 0.0),
            "A_focus_sigex": q.get("signal_t_excess", float("nan")),
            "vs_p114_raw_gross_delta_bp": q.get("obs_mean_gross_bp", 0.0) - p114_baseline_gross,
            "vs_p114_raw_net_delta_bp": q.get("obs_mean_net_bp", 0.0) - p114_baseline_net,
            "joint_beats_raw_on_gross": bool(q.get("obs_mean_gross_bp", 0.0) > p114_baseline_gross),
            "joint_clears_fee_floor": bool(q.get("obs_mean_net_bp", 0.0) > 0),
        }
    out["lesson21_axis_stacking_diagnostic"] = stacking

    # Hold sweep on best-k A_focus (Lesson #37)
    best_k = None
    best_gross = -np.inf
    for k in K_SWEEP:
        key = f"k_{k}"
        if "skip_reason" in per_k_results.get(key, {}):
            continue
        g = per_k_results[key]["quadrants"]["A_focus_breakUp_LONG"].get("obs_mean_gross_bp", -np.inf)
        if g > best_gross:
            best_gross = g
            best_k = k

    sweep_results = []
    if best_k is not None:
        log.info("=== hold sweep on best k=%.2f A_focus_breakUp_LONG ===", best_k)
        # Recompute trigger masks for best_k
        atr_up_best: dict[str, pd.Series] = {}
        atr_dn_best: dict[str, pd.Series] = {}
        for s in panel:
            c = close_per_sym[s]
            rmax = rolling_max_per_sym[s]
            rmin = rolling_min_per_sym[s]
            atr_norm = atr_per_sym[s]
            buffer_abs = best_k * atr_norm * c.shift(1)
            atr_up_best[s] = ((c > (rmax + buffer_abs)) & rmax.notna() & atr_norm.notna()).astype(bool)
            atr_dn_best[s] = ((c < (rmin - buffer_abs)) & rmin.notna() & atr_norm.notna()).astype(bool)
        deb_up_best: dict[str, pd.Series] = {}
        for s in panel:
            any_brk = (atr_up_best[s] | atr_dn_best[s]).astype(int)
            prior_count = any_brk.shift(1).rolling(DEBOUNCE_BARS, min_periods=1).sum().fillna(0)
            fresh = prior_count == 0
            deb_up_best[s] = (atr_up_best[s] & fresh).astype(bool)

        for h in HOLD_SWEEP_BARS:
            if h == PRIMARY_HOLD_BARS:
                continue
            fwd_h = fwd_per_sym_by_hold[h]
            pool_h = np.concatenate([f.dropna().values for f in fwd_h.values()])
            try:
                res = compute_quadrant(
                    f"A_focus_breakUp_LONG_k{best_k}_h{h}",
                    deb_up_best,
                    fwd_h,
                    dir_long,
                    h,
                    FEE_PER_TRADE,
                    pool_h,
                )
                sweep_results.append(res)
            except Exception as e:
                log.warning("sweep h=%d fail: %s", h, e)
    out["best_k"] = best_k
    out["best_k_gross_bp"] = float(best_gross) if best_gross != -np.inf else None
    out["hold_sweep_best_k_A_focus"] = sweep_results

    # Lesson #37 sweep verdict scan
    sweep_cells_pass = []
    for res in sweep_results:
        if res.get("gate_3_pass", False) and res.get("gate_concentration_pass", False):
            lc = res.get("life_changing_4dim", {})
            sweep_cells_pass.append(
                {
                    "cell": res.get("quadrant"),
                    "hold_hours": res.get("hold_hours"),
                    "gross_bp": res.get("obs_mean_gross_bp"),
                    "net_bp": res.get("obs_mean_net_bp"),
                    "sigex": res.get("signal_t_excess"),
                    "lc_all_4dim_pass": lc.get("pass_all_4_dim", False),
                }
            )
    out["lesson37_sweep_scan"] = {
        "n_sweep_cells_3gate_AND_conc_pass": len(sweep_cells_pass),
        "cells": sweep_cells_pass,
    }

    # ─── Verdict aggregation ──────────────────────────────────────────────
    # Find the best PRIMARY-hold quadrant cell across k for verdict
    any_pass_k_full = None
    any_pass_k_full_lc = False
    max_focus_gross_any_k = -np.inf
    max_focus_gross_any_k_kref = None
    for k in K_SWEEP:
        key = f"k_{k}"
        if "skip_reason" in per_k_results.get(key, {}):
            continue
        quadrants_k = per_k_results[key]["quadrants"]
        A_focus = quadrants_k["A_focus_breakUp_LONG"]
        B_same = quadrants_k["B_same_sign_breakDn_SHORT"]
        ag = A_focus.get("obs_mean_gross_bp", -np.inf)
        bg = B_same.get("obs_mean_gross_bp", -np.inf)
        if ag > max_focus_gross_any_k:
            max_focus_gross_any_k = ag
            max_focus_gross_any_k_kref = k
        if bg > max_focus_gross_any_k:
            max_focus_gross_any_k = bg
            max_focus_gross_any_k_kref = k
        a_full = A_focus.get("gate_3_pass", False) and A_focus.get("gate_concentration_pass", False)
        b_full = B_same.get("gate_3_pass", False) and B_same.get("gate_concentration_pass", False)
        if a_full or b_full:
            any_pass_k_full = k
            a_lc = A_focus.get("life_changing_4dim", {}).get("pass_all_4_dim", False)
            b_lc = B_same.get("life_changing_4dim", {}).get("pass_all_4_dim", False)
            if (a_full and a_lc) or (b_full and b_lc):
                any_pass_k_full_lc = True

    n_quadrants_pass_3gate_total = 0
    for k in K_SWEEP:
        key = f"k_{k}"
        if "skip_reason" in per_k_results.get(key, {}):
            continue
        for qname, q in per_k_results[key]["quadrants"].items():
            if q.get("gate_3_pass", False):
                n_quadrants_pass_3gate_total += 1

    out["max_focus_gross_any_k_bp"] = float(max_focus_gross_any_k) if max_focus_gross_any_k != -np.inf else None
    out["max_focus_gross_any_k_kref"] = max_focus_gross_any_k_kref
    out["n_quadrants_pass_3gate_total"] = n_quadrants_pass_3gate_total

    # Decision tree
    if any_pass_k_full is not None and any_pass_k_full_lc:
        verdict = "PASS_R1_FULL"
        verdict_reason = (
            f"At k={any_pass_k_full}, focus quadrant PASS 3-gate + Concentration "
            f"+ life-changing 4-dim. ATR-normalized breakout clears fee floor."
        )
        next_action = "propose_R2"
    elif any_pass_k_full is not None and not any_pass_k_full_lc:
        verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
        verdict_reason = (
            f"At k={any_pass_k_full}, focus PASS 3-gate + Concentration BUT "
            f"life-changing 4-dim FAIL (edge or trade-frequency or sharpe sub-grade)."
        )
        next_action = "NARROW_SCOPE_LIFE_CHANGING_FAIL_graveyard"
    elif n_quadrants_pass_3gate_total == 0:
        if max_focus_gross_any_k != -np.inf and 0 < max_focus_gross_any_k < 16:
            verdict = "BROAD_FALSIFIED_FEE_FLOOR"
            verdict_reason = (
                f"All k×4-quadrant FAIL 3-gate. Max focus gross +{max_focus_gross_any_k:.2f}bp "
                f"(at k={max_focus_gross_any_k_kref}) < 16bp fee floor. Mechanism may exist "
                f"but uneconomic at any k tested. Lesson #35 3rd dogfood — level-crossing "
                f"single-domain family Tier 4 retire eligible (paradigm 104 + 114 + 115)."
            )
        else:
            verdict = "BROAD_FALSIFIED"
            verdict_reason = (
                f"All k×4-quadrant FAIL 3-gate. Max focus gross "
                f"{max_focus_gross_any_k:.2f}bp does not even point positive. ATR-normalized "
                f"subset selection ineffective."
            )
        next_action = "graveyard"
    else:
        verdict = "PARTIAL_PASS_NO_FULL_FOCUS"
        verdict_reason = (
            f"{n_quadrants_pass_3gate_total}/12 quadrant×k cells PASS 3-gate, "
            f"but no focus + concentration + life-changing combo."
        )
        next_action = "graveyard"

    out["verdict"] = verdict
    out["verdict_reason"] = verdict_reason
    out["next_action_recommendation"] = next_action
    out["wall_clock_minutes"] = (time.time() - t_start) / 60

    # Lesson #35 fee-trap distinction dogfood marker
    out["lesson35_fee_trap_dogfood"] = {
        "paradigm_115_verdict": verdict,
        "is_fee_floor_failure": (verdict == "BROAD_FALSIFIED_FEE_FLOOR"),
        "is_3rd_fee_trap_dogfood": (verdict == "BROAD_FALSIFIED_FEE_FLOOR"),
        "family_retire_eligible": (verdict == "BROAD_FALSIFIED_FEE_FLOOR"),
    }

    # Best-k summary
    best_k_summary = None
    if best_k is not None and f"k_{best_k}" in per_k_results and "quadrants" in per_k_results[f"k_{best_k}"]:
        q_best = per_k_results[f"k_{best_k}"]["quadrants"]["A_focus_breakUp_LONG"]
        best_k_summary = {
            "best_k": best_k,
            "best_k_gross_bp": q_best.get("obs_mean_gross_bp"),
            "best_k_net_bp": q_best.get("obs_mean_net_bp"),
            "best_k_sigex": q_best.get("signal_t_excess"),
            "best_k_n_trades": q_best.get("n_trades"),
            "best_k_concentration_n_pos": q_best.get("n_syms_ci_pos"),
            "best_k_concentration_n_total": q_best.get("n_syms_total"),
        }

    out["_summary_one_liner"] = {
        "paradigm": PARADIGM_SLUG,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "best_k": best_k,
        "best_k_summary": best_k_summary,
        "max_focus_gross_any_k_bp": out["max_focus_gross_any_k_bp"],
        "lesson_35_fee_trap_dogfood": "3rd_confirm" if verdict == "BROAD_FALSIFIED_FEE_FLOOR" else "n/a",
        "family_retire_eligible": (verdict == "BROAD_FALSIFIED_FEE_FLOOR"),
        "wall_clock_minutes": float(out["wall_clock_minutes"]),
        "next_action_recommendation": next_action,
    }

    _write(out)
    log.info("=== R-1 DONE in %.1fmin === verdict=%s", out["wall_clock_minutes"], verdict)
    print(json.dumps(out["_summary_one_liner"], default=str))
    return 0


def _write(payload: dict) -> None:
    p = OUT_DIR / "r1__metrics.json"
    with open(p, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    log.info("wrote %s", p)


if __name__ == "__main__":
    sys.exit(main())
