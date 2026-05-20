"""Paradigm 116 — alt_volume_confirmed_atr_breakout_continuation_long_2h R-1 PoC

Hypothesis
----------
Paradigm 115 (ATR-normalized Donchian breakout, k=1.5, 13-alt × 2h/4h hold)
returned `CONCENTRATION_DISPERSION_FAIL`:
  - At k=1.5 / hold=4h: gross +29.11bp, net +21.11bp (clears 16bp fee floor),
    sigex +4.28, perm_p_one_sided 0.000, q_pos 6/9, 9/13 syms positive-mean,
    pool ci_lower +5.58bp.
  - BUT syms_ci_pos = 0/13 because per-sym n=63-98 too small for tight CIs.
  - Lesson #41 candidate: diffuse positive alpha, per-sym CI tightness limited
    by per-sym n.

Paradigm 116 layers a **volume confirmation overlay** on paradigm 115's
ATR-buffered breakout trigger:

  Trigger = (close > rolling_max(24h) + k×ATR_14d × prev_close)
            AND
            (1h volume on breakout bar >= rolling_p80_30d 1h volume)

Hypothesis statement
  Real breakouts (institutional/HFT participation, deep liquidity) show
  ELEVATED volume on the breakout bar; noise breakouts (smart money selling
  into thin liquidity, mean-reversion traps) show SUPPRESSED volume. Adding
  a volume gate should:
    H1. Filter out fake breakouts -> per-trade edge UP
    H2. Reduce n further (to ~20% of paradigm 115) -> harder Lesson #11/41
    H3. May homogenize per-sym subset, possibly recovering Concentration Gate

  Competing outcomes:
    POSITIVE 6th dogfood: volume filter amplifies (e.g. gross +50bp at k=1.5)
      -> Lesson #21 axis stacking strengthens, possibly R-2 candidate
    NEUTRAL: volume filter doesn't add or marginally reduces (gross ~+20bp,
      same trend as p115) -> Lesson #21 saturates at 2-axis
    NEGATIVE: volume filter REDUCES alpha -> Lesson #21 saturates earlier

5-axis novelty self-check vs paradigm 115
  - Statistic = (close > rmax + k×ATR) AND (vol >= p80_30d) (NOVEL,
    dual-conditioning vs single ATR-buffer in 115)
  - Universe = 13-alt (NOT NOVEL)
  - Frame = 1h × 2h/4h (NOT NOVEL)
  - Mechanism = vol-conditioned price level event + LIQUIDITY confirmation
    (NEW extension of 115 — adds volume axis distinct from ATR vol-band)
  - Trigger = price-level k-buffer + volume p80 percentile (NOVEL —
    percentile-rank overlay vs ATR-buffer only in 115)
  Verdict: 3/5 NOVEL — proceed.

DNA collision check
  - vs paradigm 115: 3/5 dim distinct (statistic, mechanism, trigger). NOT
    a DNA collision — paradigm 115 explicit follow-up reco (per
    CONCENTRATION_DISPERSION_FAIL graveyard §Lesson #41 paradigm-architect
    spec amendment recommendation).
  - vs paradigm 23 (taker_buy_vol family): 23 used taker-side aggressive
    volume z-score as STANDALONE trigger (60m hold fee-floor family retire).
    Here volume is OVERLAY on price-level event, not standalone. Volume
    statistic is percentile rank not z-score. NOT a DNA collision.

Lesson prescreens
  - #11 sample density: 115 k=1.5 had 1082 deb up events. Volume p80 filter
    retains ~20% (paradigm-defined), so ~216 events. Per-cell (4Q × 9q) =
    ~6 each — SAMPLE_INSUFFICIENT risk. Also try p70 (~30% retention,
    ~325 events, ~9/cell) and p60 (~40%, ~433, ~12/cell). All likely fail.
    Document empirical retention per percentile.
  - #19 SNT: 4-quadrant per (k, percentile) cell.
  - #20 narrow-scope: tested per cell via life-changing 4-dim.
  - #21 axis stacking 6th dogfood: joint (breakout × ATR × volume) vs
    paradigm 115 baseline (breakout × ATR). Joint must beat +20bp at SOME
    cell to demonstrate volume axis synthesizes.
  - #28 substrate availability: paradigm 113/114/115 1h OHLCV cache reuse.
    Volume column verified present.
  - #30 data window ratio: 2yr / 2.4yr ≈ 83%. PASS.
  - #34 empirical distribution: trigger rate per (k, percentile) measured.
  - #35 fee-trap distinction: if all cells FAIL fee floor → strengthen
    Lesson #35.
  - #39 sub-class A antipattern: A_focus + A_mirror perfectly symmetric
    (mechanical, same trigger). Document.
  - #40 structural threshold feasibility: rolling p80 trivially reachable
    (definition: ≥ 20% of bars at-or-above). PASS.
  - #41 candidate 2nd dogfood: per-sym n drops further with volume gate.
    If pool signal preserved but syms_ci_pos still 0/13 -> Lesson #41
    confirmed. If volume gate REVERSES concentration (e.g. syms_ci_pos
    rises to 3+/13 despite smaller n), it's a counterexample.

R-1 body
  - Per (k ∈ {1.0, 1.5}, vol_pct ∈ {60, 70, 80}): 4-quadrant SNT + 3-gate +
    Concentration Gate + life-changing 4-dim.
  - Fix primary k=1.5 (paradigm 115 strongest), primary vol_pct=80.
  - Sweep both because Lesson #11 risk + need to characterize percentile
    sensitivity.
  - fee_aware_perm_test + bootstrap_ci via _perm_utils.
  - 16bp fee floor.
  - Lesson #21 axis-stacking diagnostic: best cell joint vs paradigm 115
    baseline +20bp (k=1.5 A_focus 2h) and +29bp (k=1.5 A_focus 4h).
  - Hold sweep [2, 4] on best cell.

Scope
  - 13 alts (paradigm 113-115 universe).
  - 24 months 2024-05..2026-04 from paradigm 113 cache.
"""
from __future__ import annotations

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

PARADIGM_SLUG = "alt_volume_confirmed_atr_breakout_continuation_long_2h"
PARADIGM_NUMBER = 116
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
log = logging.getLogger("p116_r1")

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
HOLD_SWEEP_BARS = [2, 4]
ATR_BARS = 14 * 24  # 14 days × 24 hourly bars rolling
VOL_ROLLING_BARS = 30 * 24  # 30 days × 24 hourly bars
K_SWEEP = [1.0, 1.5]
PRIMARY_K = 1.5
VOL_PCT_SWEEP = [60, 70, 80]
PRIMARY_VOL_PCT = 80


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


def compute_vol_pct(volume: pd.Series, n_bars: int) -> pd.Series:
    """For each bar, compute rolling-30d percentile rank of its 1h volume.

    Uses shifted(1) lookback to avoid look-ahead (today's bar volume gets
    rank vs PRIOR 30d only).
    """
    # rolling rank percentile: rank of current value within (prior window)
    # use rolling(...).rank(pct=True) on volume shifted appropriately
    # We want: for bar at t, what fraction of last n_bars (excluding t) were <= vol[t]?
    # Implementation: rolling.apply with raw=True
    def _pct_in_window(arr):
        if len(arr) < 10:
            return np.nan
        last = arr[-1]
        # rank in window (including last); subtract self to get strictly-less fraction
        return float(np.mean(arr <= last))

    # Use shift(0) but include current bar in window: rank of current = (count<=)/n
    # That's still no-lookahead because the rolling window ends at current bar
    pct = volume.rolling(n_bars, min_periods=max(48, n_bars // 3)).apply(
        _pct_in_window, raw=True
    )
    return pct


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
    syms_pos_mean = sum(
        1 for v in per_sym_ci.values() if v.get("mean_bp", 0.0) > 0 and v["n"] >= 5
    )

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
        "n_syms_pos_mean": int(syms_pos_mean),
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
        "vol_rolling_bars": VOL_ROLLING_BARS,
        "k_sweep": K_SWEEP,
        "primary_k": PRIMARY_K,
        "vol_pct_sweep": VOL_PCT_SWEEP,
        "primary_vol_pct": PRIMARY_VOL_PCT,
        "paradigm_115_baseline": {
            "k15_2h_A_focus_gross_bp": 20.03,
            "k15_2h_A_focus_net_bp": 12.03,
            "k15_2h_A_focus_sigex": 3.99,
            "k15_2h_A_focus_n": 1082,
            "k15_2h_A_focus_syms_ci_pos": 0,
            "k15_2h_A_focus_syms_pos_mean": 9,
            "k15_4h_A_focus_gross_bp": 29.11,
            "k15_4h_A_focus_net_bp": 21.11,
            "k15_4h_A_focus_sigex": 4.28,
            "verdict": "CONCENTRATION_DISPERSION_FAIL (verdict-tree label BROAD_FALSIFIED)",
        },
        "novelty_self_check": {
            "statistic": "NOVEL (dual-conditioning: ATR-buffer × volume-pct-rank)",
            "universe": "NOT NOVEL (same 13 alts)",
            "frame": "NOT NOVEL (1h × 2h/4h)",
            "mechanism": "NOVEL (price-level event + ATR vol-band + LIQUIDITY confirmation)",
            "trigger": "NOVEL (k-buffer × volume-percentile-rank overlay)",
            "axes_pass": 3,
            "verdict": "3/5 NOVEL — proceed",
        },
        "substrate_source": "paradigm113_klines_cache_reuse (volume column verified)",
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

    # Per-sym close + rolling max/min + ATR + volume pct
    close_per_sym: dict[str, pd.Series] = {}
    rolling_max_per_sym: dict[str, pd.Series] = {}
    rolling_min_per_sym: dict[str, pd.Series] = {}
    atr_per_sym: dict[str, pd.Series] = {}
    vol_pct_per_sym: dict[str, pd.Series] = {}
    log.info("computing rolling stats + volume percentile rank (30d window)")
    t_pre = time.time()
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
        atr_per_sym[s] = (atr_abs / c).shift(1)
        # volume percentile rank: rolling 30d window includes current bar
        # to avoid look-ahead by shift(0)
        vol = df["volume"].copy()
        vol_pct_per_sym[s] = compute_vol_pct(vol, VOL_ROLLING_BARS)
    log.info("rolling stats done in %.1fs", time.time() - t_pre)

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

    n_bars_total = sum(int(close_per_sym[s].notna().sum()) for s in panel)
    empirical_per_cell = {}
    per_cell_results: dict = {}

    # Build cells: (k × vol_pct)
    for k in K_SWEEP:
        for vp in VOL_PCT_SWEEP:
            cell_key = f"k_{k}_vol_pct_{vp}"
            log.info("=== cell %s === computing combined trigger masks", cell_key)
            vol_thresh = vp / 100.0
            atr_up_per_sym: dict[str, pd.Series] = {}
            atr_dn_per_sym: dict[str, pd.Series] = {}
            for s in panel:
                c = close_per_sym[s]
                rmax = rolling_max_per_sym[s]
                rmin = rolling_min_per_sym[s]
                atr_norm = atr_per_sym[s]
                vol_pct = vol_pct_per_sym[s]
                buffer_abs = k * atr_norm * c.shift(1)
                vol_pass = (vol_pct >= vol_thresh)
                atr_up_per_sym[s] = (
                    (c > (rmax + buffer_abs))
                    & rmax.notna()
                    & atr_norm.notna()
                    & vol_pass
                ).astype(bool)
                atr_dn_per_sym[s] = (
                    (c < (rmin - buffer_abs))
                    & rmin.notna()
                    & atr_norm.notna()
                    & vol_pass
                ).astype(bool)

            # Debounce
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

            empirical_per_cell[cell_key] = {
                "k": k,
                "vol_pct": vp,
                "raw_up_events": n_raw_up,
                "raw_dn_events": n_raw_dn,
                "deb_up_events": n_deb_up,
                "deb_dn_events": n_deb_dn,
                "deb_up_rate_pct": float(100 * n_deb_up / max(1, n_bars_total)),
                "deb_dn_rate_pct": float(100 * n_deb_dn / max(1, n_bars_total)),
            }

            # retention vs paradigm 115 same-k baseline
            p115_baselines_deb_up = {1.0: 1884, 1.5: 1082}
            p115_baselines_deb_dn = {1.0: 1959, 1.5: 1084}
            p115_up_base = p115_baselines_deb_up.get(k, 1)
            p115_dn_base = p115_baselines_deb_dn.get(k, 1)
            empirical_per_cell[cell_key]["retention_vs_p115_up_pct"] = float(
                100 * n_deb_up / max(1, p115_up_base)
            )
            empirical_per_cell[cell_key]["retention_vs_p115_dn_pct"] = float(
                100 * n_deb_dn / max(1, p115_dn_base)
            )
            log.info(
                "cell %s: deb up=%d dn=%d (retention vs p115: up=%.1f%% dn=%.1f%%)",
                cell_key, n_deb_up, n_deb_dn,
                empirical_per_cell[cell_key]["retention_vs_p115_up_pct"],
                empirical_per_cell[cell_key]["retention_vs_p115_dn_pct"],
            )

            # Lesson #11 prescreen per cell
            all_ts_idx = pd.concat([s for s in close_per_sym.values()], axis=1).index
            n_quarters = max(
                1, int(np.ceil((all_ts_idx.max() - all_ts_idx.min()).days / 91))
            )
            per_q_up = n_deb_up / max(1, PRIMARY_HOLD_BARS) / n_quarters
            per_q_dn = n_deb_dn / max(1, PRIMARY_HOLD_BARS) / n_quarters
            empirical_per_cell[cell_key]["per_quarter_up"] = float(per_q_up)
            empirical_per_cell[cell_key]["per_quarter_dn"] = float(per_q_dn)
            empirical_per_cell[cell_key]["passes_lesson11_both"] = bool(
                per_q_up >= 30 and per_q_dn >= 30
            )

            if not (per_q_up >= 30 and per_q_dn >= 30):
                log.warning(
                    "cell %s Lesson #11 FAIL per_q_up=%.1f per_q_dn=%.1f — skip quadrant computation",
                    cell_key, per_q_up, per_q_dn,
                )
                per_cell_results[cell_key] = {
                    "k": k,
                    "vol_pct": vp,
                    "skip_reason": "lesson11_sample_density_fail",
                    "per_quarter_up": float(per_q_up),
                    "per_quarter_dn": float(per_q_dn),
                    "n_deb_up": n_deb_up,
                    "n_deb_dn": n_deb_dn,
                }
                continue

            # 4-quadrant SNT for this cell
            log.info(
                "=== cell %s 4-quadrant SNT (primary hold=%dh) ===",
                cell_key, PRIMARY_HOLD_BARS,
            )
            quadrants_c = {}
            quadrants_c["A_focus_breakUp_LONG"] = compute_quadrant(
                f"A_focus_breakUp_LONG_{cell_key}",
                deb_up_per_sym,
                fwd_primary,
                dir_long,
                PRIMARY_HOLD_BARS,
                FEE_PER_TRADE,
                pool_long,
            )
            quadrants_c["A_mirror_breakUp_SHORT"] = compute_quadrant(
                f"A_mirror_breakUp_SHORT_{cell_key}",
                deb_up_per_sym,
                fwd_primary,
                dir_short,
                PRIMARY_HOLD_BARS,
                FEE_PER_TRADE,
                pool_short,
            )
            quadrants_c["B_same_sign_breakDn_SHORT"] = compute_quadrant(
                f"B_same_sign_breakDn_SHORT_{cell_key}",
                deb_dn_per_sym,
                fwd_primary,
                dir_short,
                PRIMARY_HOLD_BARS,
                FEE_PER_TRADE,
                pool_short,
            )
            quadrants_c["B_mirror_breakDn_LONG"] = compute_quadrant(
                f"B_mirror_breakDn_LONG_{cell_key}",
                deb_dn_per_sym,
                fwd_primary,
                dir_long,
                PRIMARY_HOLD_BARS,
                FEE_PER_TRADE,
                pool_long,
            )
            per_cell_results[cell_key] = {
                "k": k,
                "vol_pct": vp,
                "quadrants": quadrants_c,
                "deb_up_trigger_masks_per_sym": {
                    s: int(deb_up_per_sym[s].sum()) for s in deb_up_per_sym
                },
                "deb_dn_trigger_masks_per_sym": {
                    s: int(deb_dn_per_sym[s].sum()) for s in deb_dn_per_sym
                },
            }
            # Cache best-cell debounced masks for hold sweep
            per_cell_results[cell_key]["_deb_up_masks"] = deb_up_per_sym
            per_cell_results[cell_key]["_deb_dn_masks"] = deb_dn_per_sym

            # Lesson #39 symmetry diagnostic per cell
            a_focus_gross = quadrants_c["A_focus_breakUp_LONG"].get("obs_mean_gross_bp", 0.0)
            a_mirror_gross = quadrants_c["A_mirror_breakUp_SHORT"].get("obs_mean_gross_bp", 0.0)
            sym_diff_abs = abs(a_focus_gross + a_mirror_gross)
            per_cell_results[cell_key]["lesson39_symmetry"] = {
                "A_focus_gross_bp": a_focus_gross,
                "A_mirror_gross_bp": a_mirror_gross,
                "sum_abs_bp": float(sym_diff_abs),
                "is_perfect_mirror": bool(sym_diff_abs < 1.0),
            }

    out["lesson34_empirical_distribution_per_cell"] = empirical_per_cell

    # Strip non-serializable masks before writing
    per_cell_results_serializable = {}
    for k_cell, v_cell in per_cell_results.items():
        d = {kk: vv for kk, vv in v_cell.items() if not kk.startswith("_")}
        per_cell_results_serializable[k_cell] = d
    out["per_cell_results"] = per_cell_results_serializable

    # Lesson #21 axis-stacking: volume overlay vs paradigm 115 baseline
    p115_k15_2h_gross = 20.03
    p115_k15_2h_net = 12.03
    p115_k15_4h_gross = 29.11
    p115_k15_4h_net = 21.11
    p115_k10_2h_gross = 8.04
    stacking = {}
    for k in K_SWEEP:
        for vp in VOL_PCT_SWEEP:
            cell_key = f"k_{k}_vol_pct_{vp}"
            cell = per_cell_results.get(cell_key, {})
            if "skip_reason" in cell:
                stacking[cell_key] = {
                    "skipped": True,
                    "reason": cell["skip_reason"],
                    "per_q_up": cell.get("per_quarter_up"),
                    "per_q_dn": cell.get("per_quarter_dn"),
                }
                continue
            q = cell["quadrants"]["A_focus_breakUp_LONG"]
            baseline_g = p115_k15_2h_gross if k == 1.5 else p115_k10_2h_gross
            baseline_n = p115_k15_2h_net if k == 1.5 else (p115_k10_2h_gross - 8.0)
            stacking[cell_key] = {
                "k": k,
                "vol_pct": vp,
                "A_focus_gross_bp": q.get("obs_mean_gross_bp", 0.0),
                "A_focus_net_bp": q.get("obs_mean_net_bp", 0.0),
                "A_focus_sigex": q.get("signal_t_excess", float("nan")),
                "A_focus_n": q.get("n_trades", 0),
                "vs_p115_gross_delta_bp": q.get("obs_mean_gross_bp", 0.0) - baseline_g,
                "vs_p115_net_delta_bp": q.get("obs_mean_net_bp", 0.0) - baseline_n,
                "joint_beats_p115_on_gross": bool(q.get("obs_mean_gross_bp", 0.0) > baseline_g),
                "joint_clears_fee_floor": bool(q.get("obs_mean_net_bp", 0.0) > 0),
            }
    out["lesson21_axis_stacking_diagnostic"] = stacking

    # Lesson #21 6th dogfood determination — does volume axis amplify gross?
    measurable_cells = [
        v for k_, v in stacking.items() if not v.get("skipped")
    ]
    if measurable_cells:
        max_amp_cell = max(measurable_cells, key=lambda c: c.get("vs_p115_gross_delta_bp", -np.inf))
        amp_delta = max_amp_cell.get("vs_p115_gross_delta_bp", 0.0)
        if amp_delta > 5.0:
            dogfood_verdict = "positive"
            dogfood_reason = (
                f"Best cell {max_amp_cell.get('vol_pct')}/k={max_amp_cell.get('k')} "
                f"beats p115 baseline by +{amp_delta:.1f}bp on gross. Volume axis "
                f"synthesizes additional alpha."
            )
        elif amp_delta > -5.0:
            dogfood_verdict = "neutral"
            dogfood_reason = (
                f"Best cell delta {amp_delta:+.1f}bp ~ p115 baseline. Volume axis "
                f"does not synthesize but does not destroy. Lesson #21 saturation."
            )
        else:
            dogfood_verdict = "negative"
            dogfood_reason = (
                f"Best cell delta {amp_delta:+.1f}bp — volume axis DESTROYS alpha. "
                f"Lesson #21 saturates earlier than 2-axis."
            )
    else:
        dogfood_verdict = "n/a"
        dogfood_reason = "All cells failed Lesson #11 prescreen — no measurable amplification"

    out["lesson21_6th_dogfood"] = {
        "verdict": dogfood_verdict,
        "reason": dogfood_reason,
    }

    # Best cell selection for hold sweep
    best_cell_key = None
    best_cell_gross = -np.inf
    for cell_key, cell in per_cell_results.items():
        if "skip_reason" in cell:
            continue
        g = cell["quadrants"]["A_focus_breakUp_LONG"].get("obs_mean_gross_bp", -np.inf)
        if g > best_cell_gross:
            best_cell_gross = g
            best_cell_key = cell_key

    sweep_results = []
    if best_cell_key is not None:
        log.info("=== hold sweep on best cell %s ===", best_cell_key)
        best_cell = per_cell_results[best_cell_key]
        deb_up_best = best_cell["_deb_up_masks"]
        for h in HOLD_SWEEP_BARS:
            if h == PRIMARY_HOLD_BARS:
                continue
            fwd_h = fwd_per_sym_by_hold[h]
            pool_h = np.concatenate([f.dropna().values for f in fwd_h.values()])
            try:
                res = compute_quadrant(
                    f"A_focus_breakUp_LONG_{best_cell_key}_h{h}",
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
    out["best_cell_key"] = best_cell_key
    out["best_cell_gross_bp"] = float(best_cell_gross) if best_cell_gross != -np.inf else None
    out["hold_sweep_best_cell_A_focus"] = sweep_results

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
    any_pass_cell_full = None
    any_pass_cell_full_lc = False
    max_focus_gross_any_cell = -np.inf
    max_focus_gross_cellref = None
    for cell_key, cell in per_cell_results.items():
        if "skip_reason" in cell:
            continue
        quadrants_c = cell["quadrants"]
        A_focus = quadrants_c["A_focus_breakUp_LONG"]
        B_same = quadrants_c["B_same_sign_breakDn_SHORT"]
        ag = A_focus.get("obs_mean_gross_bp", -np.inf)
        bg = B_same.get("obs_mean_gross_bp", -np.inf)
        if ag > max_focus_gross_any_cell:
            max_focus_gross_any_cell = ag
            max_focus_gross_cellref = cell_key
        if bg > max_focus_gross_any_cell:
            max_focus_gross_any_cell = bg
            max_focus_gross_cellref = cell_key + "_B_same"
        a_full = A_focus.get("gate_3_pass", False) and A_focus.get("gate_concentration_pass", False)
        b_full = B_same.get("gate_3_pass", False) and B_same.get("gate_concentration_pass", False)
        if a_full or b_full:
            any_pass_cell_full = cell_key
            a_lc = A_focus.get("life_changing_4dim", {}).get("pass_all_4_dim", False)
            b_lc = B_same.get("life_changing_4dim", {}).get("pass_all_4_dim", False)
            if (a_full and a_lc) or (b_full and b_lc):
                any_pass_cell_full_lc = True

    n_quadrants_pass_3gate_total = 0
    n_cells_measurable = 0
    for cell_key, cell in per_cell_results.items():
        if "skip_reason" in cell:
            continue
        n_cells_measurable += 1
        for qname, q in cell["quadrants"].items():
            if q.get("gate_3_pass", False):
                n_quadrants_pass_3gate_total += 1

    n_cells_total = len(K_SWEEP) * len(VOL_PCT_SWEEP)
    out["max_focus_gross_any_cell_bp"] = (
        float(max_focus_gross_any_cell) if max_focus_gross_any_cell != -np.inf else None
    )
    out["max_focus_gross_cellref"] = max_focus_gross_cellref
    out["n_quadrants_pass_3gate_total"] = n_quadrants_pass_3gate_total
    out["n_cells_measurable"] = n_cells_measurable
    out["n_cells_total"] = n_cells_total
    out["n_cells_lesson11_skip"] = n_cells_total - n_cells_measurable

    # Lesson #41 candidate 2nd dogfood diagnostic
    # Find best measurable cell pool-level evidence
    p115_syms_pos_mean = 9
    best_cell_concentration_diag = None
    if best_cell_key is not None:
        bc_focus = per_cell_results[best_cell_key]["quadrants"]["A_focus_breakUp_LONG"]
        best_cell_concentration_diag = {
            "cell": best_cell_key,
            "gross_bp": bc_focus.get("obs_mean_gross_bp"),
            "net_bp": bc_focus.get("obs_mean_net_bp"),
            "sigex": bc_focus.get("signal_t_excess"),
            "perm_p_one_sided_above": bc_focus.get("perm_p_one_sided_above"),
            "q_pos_ratio": bc_focus.get("q_pos_ratio"),
            "ci_lower_bp": bc_focus.get("ci_lower_bp"),
            "n_trades": bc_focus.get("n_trades"),
            "n_syms_ci_pos": bc_focus.get("n_syms_ci_pos"),
            "n_syms_pos_mean": bc_focus.get("n_syms_pos_mean"),
            "n_syms_total": bc_focus.get("n_syms_total"),
            "pool_evidence_strong": bool(
                bc_focus.get("signal_t_excess", 0) >= 4.0
                and bc_focus.get("q_pos_ratio", 0) >= 0.5
                and bc_focus.get("ci_lower_bp", -1) > 0
            ),
            "concentration_fails": bool(bc_focus.get("n_syms_ci_pos", 0) < 3),
            "p115_syms_pos_mean_baseline": p115_syms_pos_mean,
        }
        if (
            best_cell_concentration_diag["pool_evidence_strong"]
            and best_cell_concentration_diag["concentration_fails"]
        ):
            lesson41_2nd_dogfood = "confirmed_diffuse_positive_concentration_fail"
        elif (
            best_cell_concentration_diag["concentration_fails"]
            and not best_cell_concentration_diag["pool_evidence_strong"]
        ):
            lesson41_2nd_dogfood = "concentration_fail_but_pool_evidence_weak"
        elif not best_cell_concentration_diag["concentration_fails"]:
            lesson41_2nd_dogfood = "counterexample_volume_filter_concentrates"
        else:
            lesson41_2nd_dogfood = "ambiguous"
    else:
        lesson41_2nd_dogfood = "all_cells_lesson11_skip_no_diagnostic"
    out["lesson41_candidate_2nd_dogfood"] = {
        "verdict": lesson41_2nd_dogfood,
        "best_cell_diag": best_cell_concentration_diag,
    }

    # Decision tree
    if n_cells_measurable == 0:
        verdict = "SAMPLE_INSUFFICIENT"
        verdict_reason = (
            f"All {n_cells_total} cells (k × vol_pct) failed Lesson #11 prescreen "
            f"(per-cell-per-quarter < 30). Volume confirmation overlay reduces n "
            f"too aggressively. Lesson #11 4th dogfood (paradigm 84+85+86 family)."
        )
        next_action = "graveyard"
    elif any_pass_cell_full is not None and any_pass_cell_full_lc:
        verdict = "PASS_R1_FULL"
        verdict_reason = (
            f"At cell {any_pass_cell_full}, focus quadrant PASS 3-gate + Concentration "
            f"+ life-changing 4-dim. Volume confirmation overlay synthesizes."
        )
        next_action = "propose_R2"
    elif any_pass_cell_full is not None and not any_pass_cell_full_lc:
        verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
        verdict_reason = (
            f"At cell {any_pass_cell_full}, focus PASS 3-gate + Concentration BUT "
            f"life-changing 4-dim FAIL (edge or trade-frequency or sharpe sub-grade)."
        )
        next_action = "NARROW_SCOPE_LIFE_CHANGING_FAIL_graveyard"
    elif n_quadrants_pass_3gate_total == 0:
        if max_focus_gross_any_cell != -np.inf and 0 < max_focus_gross_any_cell < 16:
            verdict = "BROAD_FALSIFIED_FEE_FLOOR"
            verdict_reason = (
                f"All measurable cells × 4-quadrant FAIL 3-gate. Max focus gross "
                f"+{max_focus_gross_any_cell:.2f}bp (at {max_focus_gross_cellref}) "
                f"< 16bp fee floor. Volume overlay reduces alpha below fee floor "
                f"vs paradigm 115 (20bp). Lesson #21 6th dogfood NEGATIVE."
            )
        elif max_focus_gross_any_cell != -np.inf:
            verdict = "BROAD_FALSIFIED"
            verdict_reason = (
                f"All measurable cells × 4-quadrant FAIL 3-gate. Max focus gross "
                f"+{max_focus_gross_any_cell:.2f}bp (at {max_focus_gross_cellref}). "
                f"Concentration Gate fails (Lesson #41 candidate 2nd dogfood)."
            )
        else:
            verdict = "BROAD_FALSIFIED"
            verdict_reason = (
                "All measurable cells × 4-quadrant FAIL 3-gate. No directional alpha."
            )
        next_action = "graveyard"
    else:
        verdict = "PARTIAL_PASS_NO_FULL_FOCUS"
        verdict_reason = (
            f"{n_quadrants_pass_3gate_total} quadrant×cell pass 3-gate, "
            f"but no focus + concentration + life-changing combo."
        )
        next_action = "graveyard"

    out["verdict"] = verdict
    out["verdict_reason"] = verdict_reason
    out["next_action_recommendation"] = next_action
    out["wall_clock_minutes"] = (time.time() - t_start) / 60

    # Summary one-liner
    out["_summary_one_liner"] = {
        "paradigm": PARADIGM_SLUG,
        "paradigm_number": PARADIGM_NUMBER,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "best_cell_key": best_cell_key,
        "best_cell_gross_bp": out["best_cell_gross_bp"],
        "max_focus_gross_any_cell_bp": out["max_focus_gross_any_cell_bp"],
        "max_focus_gross_cellref": max_focus_gross_cellref,
        "n_cells_measurable": n_cells_measurable,
        "n_cells_lesson11_skip": n_cells_total - n_cells_measurable,
        "lesson_21_6th_dogfood": dogfood_verdict,
        "lesson_41_candidate_2nd_dogfood": lesson41_2nd_dogfood,
        "wall_clock_minutes": float(out["wall_clock_minutes"]),
        "next_action_recommendation": next_action,
    }

    _write(out)
    log.info(
        "=== R-1 DONE in %.1fmin === verdict=%s",
        out["wall_clock_minutes"], verdict,
    )
    print(json.dumps(out["_summary_one_liner"], default=str))
    return 0


def _write(payload: dict) -> None:
    p = OUT_DIR / "r1__metrics.json"
    # Strip non-serializable mask references if any leaked through
    def _scrub(obj):
        if isinstance(obj, dict):
            return {kk: _scrub(vv) for kk, vv in obj.items() if not kk.startswith("_deb_")}
        if isinstance(obj, list):
            return [_scrub(x) for x in obj]
        return obj
    scrubbed = _scrub(payload)
    with open(p, "w") as f:
        json.dump(scrubbed, f, indent=2, default=str)
    log.info("wrote %s", p)


if __name__ == "__main__":
    sys.exit(main())
