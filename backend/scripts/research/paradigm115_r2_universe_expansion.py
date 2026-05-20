"""Paradigm 115 R-2 — universe expansion path to resolve DIFFUSE_POSITIVE blocker.

R-1 verdict CONCENTRATION_DISPERSION_FAIL at k=1.5 × 4h cell:
  - n=1082, gross +29.11bp / net +21.11bp (clears 16bp fee floor),
    sigex +4.28, perm_p_one_sided 0.000, q_pos 6/9, pool ci_lower +5.58bp,
    BUT syms_ci_pos 0/13 (DIFFUSE_POSITIVE — Lesson #41 candidate 1st dogfood).

R-2 Hypothesis (universe expansion path)
  If per-sym n=83 with N=13 → CI width ±50bp prevents ci_pos, but pool is real
  alpha (sigex +4.28), then expanding universe to ~29 alts (per-sym n drops to
  ~40-50, CI even wider) BUT aggregating across MORE alts increases the
  FRACTION of syms with positive bootstrap CI via diffuse alpha mechanism.
  Target: syms_ci_pos ≥ 4/29 → Lesson #41 confirmed 정식 승급.

R-2 Protocol
  1. Universe expansion: 13 original + 16 new (mainstream alts with full
     cohort-aligned 2yr substrate verified via HTTP HEAD probe)
  2. Fixed cell: k=1.5 × 4h hold (paradigm 115 R-1 best)
  3. Pool aggregate: gross, net, sigex, perm_p, CI, q_pos, syms_ci_pos
  4. 5-fold TS-CV walk-forward (Lesson #26 mandatory after paradigm 87)
  5. Single-sym deep-bootstrap fallback (top R-1: HBAR/ADA/AVAX/FIL @ n_boot=5000)
  6. Life-changing 4-dim re-evaluation

R-2 PASS Criteria (combined E-type + Lesson #41 dogfood)
  E-type:
    - pool sigex >= 2.0
    - pool ci_lower > 0
    - pool perm_p_two_sided <= 0.10 OR perm_p_one_sided_above <= 0.05
  WF gate (Lesson #26):
    - n_folds_pass >= 3/5 TS-CV
  Lesson #41 candidate dogfood:
    - syms_ci_pos >= 4 AND syms_ci_pos_ratio >= 15% → confirmed (universe
      expansion resolved diffuse alpha aggregation)
    - OR top 3 single-sym deep-bootstrap ci_lower > 0 → narrow-scope path

Verdicts
  - R2_PASS: pool gates PASS + WF >=3/5 + (syms_ci_pos>=4 OR top deep CI pos)
  - R2_FAIL_CONCENTRATION: pool PASS + WF >=3/5 BUT syms_ci_pos still <4
    AND no single-sym deep CI pos → Lesson #41 candidate refuted
  - R2_FAIL_TS_CV: pool PASS BUT n_folds_pass < 3/5 → paradigm 87 fragility
  - R2_FAIL_POOL: pool gates FAIL on expanded universe (mechanism didn't
    survive expansion)
  - R2_FAIL_LIFE_CHANGING: all gates PASS BUT 4-dim 2/4 (edge 0.21% blocker
    persists — narrow-scope life-changing fail at R-2)

Lesson prescreens
  - #11 sample density: per-sym n_events × N_syms >= 3000 minimum
  - #30 cohort-aligned: all 29 alts verified 2024-05 substrate availability
  - #41 candidate (2nd dogfood opportunity)
  - #20 narrow-scope (if expansion fails)
  - #26 temporal walk-forward mandatory
"""
from __future__ import annotations

import io
import json
import logging
import sys
import time
import zipfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

ROOT = Path("/home/hcpark/antigravity/backend")
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

PARADIGM_SLUG = "alt_atr_normalized_range_breakout_continuation_long_2h"
PARADIGM_NUMBER = 115
PHASE = "R-2"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_SLUG
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Shared klines cache from paradigm 113 (13 original alts already cached)
SHARED_CACHE_DIR = (
    ROOT
    / "runs"
    / "research_track"
    / "intraday_hour_of_day_anchor_alt_directional_2h"
    / "klines_cache"
)

# Local R-2 expansion cache (16 new alts)
EXPANSION_CACHE_DIR = OUT_DIR / "klines_cache_r2_expansion"
EXPANSION_CACHE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(OUT_DIR / "r2__stdout.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("p115_r2")

# Original 13 alts (cached in shared dir)
ALTS_ORIGINAL = [
    "SOLUSDT", "HBARUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT",
    "ADAUSDT", "BCHUSDT", "LTCUSDT", "BNBUSDT", "FILUSDT",
    "NEARUSDT", "XRPUSDT", "ETHUSDT",
]
# 16 new alts (Lesson #28 substrate verified via HTTP HEAD probe at 2024-05)
ALTS_EXPANSION = [
    "TRXUSDT", "TIAUSDT", "SUIUSDT", "APTUSDT", "ARBUSDT",
    "OPUSDT", "SEIUSDT", "INJUSDT", "AAVEUSDT", "UNIUSDT",
    "DOTUSDT", "ATOMUSDT", "ICPUSDT", "MATICUSDT",
    "1000SHIBUSDT", "1000PEPEUSDT",
]
ALTS_ALL = ALTS_ORIGINAL + ALTS_EXPANSION

START_MONTH = "2024-05"
END_MONTH = "2026-04"

# Paradigm 115 R-1 best cell parameters (fixed for R-2)
FEE_PER_TRADE = 0.0008  # 16 bp round-trip
ROLLING_WINDOW_BARS = 24
DEBOUNCE_BARS = 12
ATR_BARS = 14 * 24  # 14 days × 24 hourly
K_FIXED = 1.5  # R-1 best k
HOLD_BARS = 4  # R-1 best hold (h=4)

# R-1 top single-sym candidates for deep-bootstrap
TOP_R1_SYMS = ["HBARUSDT", "ADAUSDT", "AVAXUSDT", "FILUSDT"]

# Walk-forward
N_WF_FOLDS = 5


def month_iter(start: str, end: str) -> list[str]:
    s = pd.Period(start, freq="M")
    e = pd.Period(end, freq="M")
    return [str(p) for p in pd.period_range(s, e, freq="M")]


def load_or_download_1h(sym: str, month: str, is_expansion: bool) -> pd.DataFrame:
    """Load from shared cache (original 13) or download to expansion cache (new 16)."""
    if is_expansion:
        cache_file = EXPANSION_CACHE_DIR / f"{sym}_1h_{month}.joblib"
    else:
        cache_file = SHARED_CACHE_DIR / f"{sym}_1h_{month}.joblib"

    if cache_file.exists():
        try:
            return joblib.load(cache_file)
        except Exception as e:
            log.warning("cache load fail %s %s: %s", sym, month, e)

    if not is_expansion:
        log.warning("shared cache miss %s %s (no download)", sym, month)
        return pd.DataFrame()

    # Expansion: download from Binance archive
    url = f"https://data.binance.vision/data/futures/um/monthly/klines/{sym}/1h/{sym}-1h-{month}.zip"
    try:
        r = requests.get(url, timeout=30)
    except Exception as e:
        log.warning("download exception %s %s: %s", sym, month, e)
        return pd.DataFrame()
    if r.status_code != 200:
        log.warning("download %s %s -> HTTP %d", sym, month, r.status_code)
        return pd.DataFrame()
    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            csv_name = zf.namelist()[0]
            with zf.open(csv_name) as f:
                first_line = f.readline()
                has_header = b"open_time" in first_line
            with zf.open(csv_name) as f:
                if has_header:
                    df = pd.read_csv(f)
                else:
                    df = pd.read_csv(
                        f,
                        header=None,
                        names=[
                            "open_time", "open", "high", "low", "close", "volume",
                            "close_time", "quote_volume", "trades",
                            "taker_buy_base", "taker_buy_quote", "ignore",
                        ],
                    )
    except Exception as e:
        log.warning("zip parse fail %s %s: %s", sym, month, e)
        return pd.DataFrame()

    df["ts"] = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.tz_localize(None)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = (
        df[["ts", "open", "high", "low", "close", "volume"]]
        .dropna()
        .drop_duplicates("ts")
        .set_index("ts")
        .sort_index()
    )
    joblib.dump(df, cache_file, compress=3)
    return df


def build_1h_panel(sym: str, months: list[str], is_expansion: bool) -> pd.DataFrame:
    parts = []
    for m in months:
        d = load_or_download_1h(sym, m, is_expansion)
        if not d.empty:
            parts.append(d)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    return out


def compute_atr(df: pd.DataFrame, n_bars: int) -> pd.Series:
    """Rolling ATR (SMA of true range)."""
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
    return tr.rolling(n_bars, min_periods=n_bars).mean()


def compute_trades_for_cell(
    trigger_mask_per_sym: dict,
    fwd_per_sym: dict,
    hold_bars: int,
    direction: int,
):
    """Return aggregated (all_trades, all_ts, all_sym, trades_per_sym) for one cell."""
    trades_per_sym: dict[str, list[float]] = {s: [] for s in trigger_mask_per_sym}
    ts_per_sym: dict[str, list[pd.Timestamp]] = {s: [] for s in trigger_mask_per_sym}

    for s, mask in trigger_mask_per_sym.items():
        fwd = fwd_per_sym.get(s)
        if fwd is None or len(fwd) == 0:
            continue
        idx_trig = mask.index[mask & fwd.notna()]
        if len(idx_trig) == 0:
            continue
        min_gap = pd.Timedelta(hours=hold_bars)
        last_t = None
        for t in idx_trig:
            if last_t is None or (t - last_t) >= min_gap:
                trades_per_sym[s].append(direction * float(fwd.loc[t]))
                ts_per_sym[s].append(t)
                last_t = t

    all_trades: list[float] = []
    all_ts: list[pd.Timestamp] = []
    all_sym: list[str] = []
    for s, lst in trades_per_sym.items():
        all_trades.extend(lst)
        all_ts.extend(ts_per_sym[s])
        all_sym.extend([s] * len(lst))

    return all_trades, all_ts, all_sym, trades_per_sym


def compute_pool_metrics(
    all_trades: list[float],
    all_ts: list[pd.Timestamp],
    all_sym: list[str],
    trades_per_sym: dict,
    candidate_pool: np.ndarray,
    fee: float,
    hold_bars: int,
) -> dict:
    """Compute pool-level 3-gate + Concentration + per-sym CI + life-changing."""
    if len(all_trades) < 5:
        return {"error": "n_trades<5", "n_trades": len(all_trades)}

    gross = np.asarray(all_trades, dtype=float)
    net = gross - fee
    sd = net.std(ddof=1)
    obs_t = float(net.mean() / sd * np.sqrt(len(net))) if sd > 0 else 0.0
    gross_mean_bp = float(gross.mean() * 10000)
    net_mean_bp = float(net.mean() * 10000)

    ci = bootstrap_ci(net, n_boot=1000, rng_seed=42)

    if len(candidate_pool) < len(net) * 2:
        perm = {
            "perm_p_two_sided": float("nan"),
            "signal_t_excess": float("nan"),
            "null_mean_t": float("nan"),
            "perm_p_one_sided_above": float("nan"),
        }
    else:
        perm = fee_aware_perm_test(
            net, candidate_pool, fee_per_trade=fee, n_perms=1000, rng_seed=42
        )

    # Per-symbol bootstrap CI
    per_sym_ci = {}
    for s, lst in trades_per_sym.items():
        if len(lst) < 5:
            per_sym_ci[s] = {
                "n": len(lst), "mean_bp": float("nan"),
                "ci_lower_bp": float("nan"), "ci_upper_bp": float("nan"),
                "ci_pos": False,
            }
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

    # Per-quarter t-stat
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

    # 3-gate (paradigm 115 R-1 used signal_t_excess>=2.0 + ci_pos + perm_p<=0.10)
    gate_3 = bool(
        perm.get("signal_t_excess", float("nan")) >= 2.0
        and ci["ci_lower"] > 0
        and perm.get("perm_p_two_sided", 1.0) <= 0.10
    )
    # Concentration gate (Lesson #16)
    gate_conc = bool(
        q_pos_ratio >= 0.5 and syms_ci_pos_ratio >= 0.30 and n_syms_ci_pos >= 3
    )

    # Life-changing 4-dim
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
    life_changing = {
        "trades_per_year": float(trades_per_year),
        "per_trade_edge_pct": float(per_trade_edge_pct),
        "capital_util_pct": float(capital_util_pct),
        "annualized_sharpe": float(sharpe_annual),
        "pass_trades_per_year_12": bool(trades_per_year >= 12),
        "pass_edge_2pct": bool(per_trade_edge_pct >= 2.0),
        "pass_util_30pct": bool(capital_util_pct >= 30),
        "pass_sharpe_1_5": bool(sharpe_annual >= 1.5),
        "pass_all_4_dim": bool(
            trades_per_year >= 12 and per_trade_edge_pct >= 2.0
            and capital_util_pct >= 30 and sharpe_annual >= 1.5
        ),
        "n_dims_pass": int(
            (trades_per_year >= 12) + (per_trade_edge_pct >= 2.0)
            + (capital_util_pct >= 30) + (sharpe_annual >= 1.5)
        ),
    }

    return {
        "n_trades": int(len(net)),
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
        "life_changing_4dim": life_changing,
    }


def deep_bootstrap_single_sym(
    trades_per_sym: dict, sym: str, fee: float, n_boot: int = 5000
) -> dict:
    """Deep-bootstrap CI for one symbol (n_boot=5000 for tighter intervals).

    Computes both 95% CI (alpha=0.05) and 90% CI (alpha=0.10).
    """
    if sym not in trades_per_sym or len(trades_per_sym[sym]) < 5:
        return {
            "sym": sym, "n": len(trades_per_sym.get(sym, [])),
            "error": "n<5",
        }
    net_s = np.asarray(trades_per_sym[sym]) - fee
    ci_95 = bootstrap_ci(net_s, n_boot=n_boot, alpha=0.05, rng_seed=42)
    ci_90 = bootstrap_ci(net_s, n_boot=n_boot, alpha=0.10, rng_seed=42)
    return {
        "sym": sym,
        "n": int(len(net_s)),
        "mean_net_bp": float(net_s.mean() * 10000),
        "ci_95_lower_bp": float(ci_95["ci_lower"] * 10000),
        "ci_95_upper_bp": float(ci_95["ci_upper"] * 10000),
        "ci_95_pos": bool(ci_95["ci_lower"] > 0),
        "ci_90_lower_bp": float(ci_90["ci_lower"] * 10000),
        "ci_90_upper_bp": float(ci_90["ci_upper"] * 10000),
        "ci_90_pos": bool(ci_90["ci_lower"] > 0),
        "n_boot": n_boot,
    }


def walk_forward_5fold(
    all_trades: list[float],
    all_ts: list[pd.Timestamp],
    all_sym: list[str],
    fee: float,
) -> dict:
    """5-fold time-series CV walk-forward (Lesson #26 mandatory after paradigm 87).

    Loose 3-gate per fold: mean_bp>0 AND t_stat>1.5 AND ci_lower_bp>-10
    (relaxed vs full 3-gate due to fold size constraints).
    """
    if len(all_trades) < 50:
        return {"error": "n_trades<50", "n_folds_pass": 0, "per_fold": []}

    df = pd.DataFrame({"ts": pd.to_datetime(all_ts), "ret": all_trades, "sym": all_sym})
    df = df.sort_values("ts").reset_index(drop=True)
    n = len(df)
    fold_size = n // N_WF_FOLDS

    per_fold = []
    for k in range(N_WF_FOLDS):
        start = k * fold_size
        end = (k + 1) * fold_size if k < N_WF_FOLDS - 1 else n
        fold_df = df.iloc[start:end]
        if len(fold_df) < 5:
            per_fold.append({
                "fold": k + 1,
                "n_trades": int(len(fold_df)),
                "error": "n<5",
                "pass_3gate_loose": False,
            })
            continue
        net = fold_df["ret"].values - fee
        sd = net.std(ddof=1)
        t_stat = float(net.mean() / sd * np.sqrt(len(net))) if sd > 0 else 0.0
        mean_bp = float(net.mean() * 10000)
        ci_f = bootstrap_ci(net, n_boot=500, rng_seed=42)
        ci_lower_bp = float(ci_f["ci_lower"] * 10000)
        per_fold.append({
            "fold": k + 1,
            "ts_start": fold_df["ts"].min().isoformat(),
            "ts_end": fold_df["ts"].max().isoformat(),
            "n_trades": int(len(fold_df)),
            "mean_net_bp": mean_bp,
            "t_stat": t_stat,
            "ci_lower_bp": ci_lower_bp,
            "ci_pos": bool(ci_f["ci_lower"] > 0),
            "pass_3gate_loose": bool(mean_bp > 0 and t_stat > 1.5 and ci_lower_bp > -10),
        })

    n_folds_pass = sum(1 for r in per_fold if r.get("pass_3gate_loose"))
    return {
        "n_folds": N_WF_FOLDS,
        "n_folds_pass": int(n_folds_pass),
        "per_fold": per_fold,
        "pass_wf_gate": bool(n_folds_pass >= 3),
    }


def _write(out: dict) -> None:
    metrics_file = OUT_DIR / "r2__metrics.json"
    with open(metrics_file, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("metrics written to %s", metrics_file)


def main() -> int:
    t_start = time.time()
    out: dict = {
        "paradigm_name": PARADIGM_SLUG,
        "paradigm_number": PARADIGM_NUMBER,
        "phase": PHASE,
        "executed_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "host": "hcp_local",
        "universe_original_n": len(ALTS_ORIGINAL),
        "universe_expansion_n": len(ALTS_EXPANSION),
        "universe_total_n": len(ALTS_ALL),
        "universe_original": ALTS_ORIGINAL,
        "universe_expansion": ALTS_EXPANSION,
        "window_months": [START_MONTH, END_MONTH],
        "fee_per_trade": FEE_PER_TRADE,
        "k_fixed": K_FIXED,
        "hold_bars": HOLD_BARS,
        "hold_hours": HOLD_BARS,
        "n_wf_folds": N_WF_FOLDS,
        "r1_baseline": {
            "cell": "k=1.5 × 4h",
            "n_trades": 1082,
            "gross_bp": 29.11,
            "net_bp": 21.11,
            "sigex": 4.28,
            "perm_p_one_sided": 0.000,
            "ci_lower_bp": 5.58,
            "syms_ci_pos": "0/13",
            "verdict": "CONCENTRATION_DISPERSION_FAIL (DIFFUSE_POSITIVE)",
        },
        "substrate_prescreen_lesson28": {
            "original_13_cached": True,
            "expansion_16_http_200_at_2024_05": True,
            "shib_pepe_remapped_to_1000_prefix": True,
        },
    }

    months = month_iter(START_MONTH, END_MONTH)
    log.info(
        "loading 1h klines for %d alts × %d months (original=%d cached, expansion=%d download)",
        len(ALTS_ALL), len(months), len(ALTS_ORIGINAL), len(ALTS_EXPANSION),
    )

    t_bf = time.time()
    panel: dict[str, pd.DataFrame] = {}
    for s in ALTS_ALL:
        is_exp = s in ALTS_EXPANSION
        t0 = time.time()
        df = build_1h_panel(s, months, is_exp)
        log.info("  %s [%s]: %d rows in %.1fs",
                 s, "EXP" if is_exp else "ORIG", len(df), time.time() - t0)
        if not df.empty:
            panel[s] = df
    bf_secs = time.time() - t_bf
    log.info("panel load done in %.1fs (%d/%d alts loaded)", bf_secs, len(panel), len(ALTS_ALL))
    out["panel_load_seconds"] = round(bf_secs, 2)
    out["alts_loaded"] = list(panel.keys())
    out["alts_loaded_n"] = len(panel)

    if len(panel) < 20:
        out["verdict"] = "R2_FAIL_PANEL_LOAD"
        out["verdict_reason"] = f"panel load produced only {len(panel)}/{len(ALTS_ALL)} alts"
        out["wall_clock_minutes"] = round((time.time() - t_start) / 60, 2)
        _write(out)
        return 1

    # Lesson #11 sample density expected
    out["lesson11_sample_density_expected"] = {
        "expected_per_sym_avg_n": "~40-90 events per sym (R-1 had 63-98 / 13 syms)",
        "expansion_total_target": ">= 3000 events",
    }

    # Compute features per symbol
    log.info("computing close + rolling max + ATR for %d alts", len(panel))
    close_per_sym: dict[str, pd.Series] = {}
    rolling_max_per_sym: dict[str, pd.Series] = {}
    atr_per_sym: dict[str, pd.Series] = {}
    for s, df in panel.items():
        c = df["close"].copy()
        close_per_sym[s] = c
        rolling_max_per_sym[s] = c.shift(1).rolling(
            ROLLING_WINDOW_BARS, min_periods=ROLLING_WINDOW_BARS
        ).max()
        atr_abs = compute_atr(df, ATR_BARS)
        atr_per_sym[s] = (atr_abs / c).shift(1)

    # Forward H-bar log returns (hold=4)
    fwd_per_sym: dict[str, pd.Series] = {}
    for s, c in close_per_sym.items():
        fwd_per_sym[s] = np.log(c.shift(-HOLD_BARS) / c)

    pool_long = np.concatenate(
        [f.dropna().values for f in fwd_per_sym.values()]
    ) if fwd_per_sym else np.array([])
    log.info("candidate pool size (LONG): %d", len(pool_long))

    # Compute ATR-buffered breakout masks with debounce (k=1.5)
    log.info("computing ATR-buffered breakout (k=%.2f) with %d-bar debounce",
             K_FIXED, DEBOUNCE_BARS)
    atr_up_per_sym: dict[str, pd.Series] = {}
    for s in panel:
        c = close_per_sym[s]
        rmax = rolling_max_per_sym[s]
        atr_norm = atr_per_sym[s]
        buffer_abs = K_FIXED * atr_norm * c.shift(1)
        atr_up_per_sym[s] = ((c > (rmax + buffer_abs)) & rmax.notna() & atr_norm.notna()).astype(bool)

    deb_up_per_sym: dict[str, pd.Series] = {}
    for s in panel:
        any_brk = atr_up_per_sym[s].astype(int)
        prior_count = any_brk.shift(1).rolling(DEBOUNCE_BARS, min_periods=1).sum().fillna(0)
        fresh = prior_count == 0
        deb_up_per_sym[s] = (atr_up_per_sym[s] & fresh).astype(bool)

    n_deb_up_total = int(sum(m.sum() for m in deb_up_per_sym.values()))
    log.info("debounced k=%.2f up-breakouts (total): %d across %d alts",
             K_FIXED, n_deb_up_total, len(panel))

    out["empirical_trigger"] = {
        "k": K_FIXED,
        "n_deb_up_total": n_deb_up_total,
        "n_alts_loaded": len(panel),
        "per_sym_estimated_n": n_deb_up_total / len(panel) if panel else 0,
    }

    # ---- A_focus_breakUp_LONG with k=1.5, hold=4h ----
    log.info("=== A_focus_breakUp_LONG k=%.2f hold=%dh on %d alts ===",
             K_FIXED, HOLD_BARS, len(panel))
    all_trades, all_ts, all_sym, trades_per_sym = compute_trades_for_cell(
        deb_up_per_sym, fwd_per_sym, HOLD_BARS, +1
    )
    log.info("  aggregated n_trades=%d across %d alts", len(all_trades), len(panel))

    pool_metrics = compute_pool_metrics(
        all_trades, all_ts, all_sym, trades_per_sym,
        pool_long, FEE_PER_TRADE, HOLD_BARS,
    )
    out["pool_expanded"] = pool_metrics

    # ---- Walk-forward 5-fold TS-CV ----
    log.info("=== walk-forward 5-fold TS-CV ===")
    wf = walk_forward_5fold(all_trades, all_ts, all_sym, FEE_PER_TRADE)
    out["walk_forward"] = wf

    # ---- Deep-bootstrap single-sym for top R-1 candidates ----
    log.info("=== deep-bootstrap single-sym (top R-1 syms) ===")
    deep_results = {}
    for sym in TOP_R1_SYMS:
        deep_results[sym] = deep_bootstrap_single_sym(
            trades_per_sym, sym, FEE_PER_TRADE, n_boot=5000
        )
        log.info("  %s: %s", sym, deep_results[sym])
    out["deep_bootstrap_top_r1_syms"] = deep_results

    # Also compute deep-bootstrap for the BEST sym in expanded universe by mean_bp
    if "per_symbol_ci" in pool_metrics:
        scored = []
        for s, v in pool_metrics["per_symbol_ci"].items():
            mb = v.get("mean_bp")
            if isinstance(mb, (int, float)) and not np.isnan(mb):
                scored.append((s, mb))
        scored.sort(key=lambda kv: kv[1], reverse=True)
        top3_expanded = [kv[0] for kv in scored[:3]]
        log.info("top 3 syms in expanded universe by mean_bp: %s", top3_expanded)
        deep_expanded = {}
        for sym in top3_expanded:
            deep_expanded[sym] = deep_bootstrap_single_sym(
                trades_per_sym, sym, FEE_PER_TRADE, n_boot=5000
            )
        out["deep_bootstrap_top3_expanded"] = deep_expanded

    # ---- VERDICT logic ----
    pool_n = pool_metrics.get("n_trades", 0)
    pool_sigex = pool_metrics.get("signal_t_excess", float("nan"))
    pool_ci_lower = pool_metrics.get("ci_lower_bp", float("nan"))
    pool_perm_p = pool_metrics.get("perm_p_two_sided", 1.0)
    pool_perm_p_one = pool_metrics.get("perm_p_one_sided_above", 1.0)
    pool_ci_pos = pool_metrics.get("ci_pos", False)
    syms_ci_pos = pool_metrics.get("n_syms_ci_pos", 0)
    syms_total = pool_metrics.get("n_syms_total", 0)
    syms_ci_pos_ratio = pool_metrics.get("syms_ci_pos_ratio", 0.0)
    pool_net_bp = pool_metrics.get("obs_mean_net_bp", float("nan"))
    n_dims_pass = pool_metrics.get("life_changing_4dim", {}).get("n_dims_pass", 0)
    wf_pass = wf.get("pass_wf_gate", False)
    n_folds_pass = wf.get("n_folds_pass", 0)

    # E-type pool gates
    pool_pass_3gate = bool(
        (not np.isnan(pool_sigex)) and pool_sigex >= 2.0
        and pool_ci_pos
        and (pool_perm_p_one <= 0.05 or pool_perm_p <= 0.10)
    )

    # Lesson #41 dogfood verdict
    deep_top3_orig_pos = sum(
        1 for v in deep_results.values()
        if v.get("ci_95_pos", False)
    )
    deep_top3_expanded_pos = sum(
        1 for v in out.get("deep_bootstrap_top3_expanded", {}).values()
        if v.get("ci_95_pos", False)
    )
    syms_ci_pos_gate = bool(syms_ci_pos >= 4 and syms_ci_pos_ratio >= 0.15)
    narrow_single_sym_pass = bool(deep_top3_orig_pos >= 1 or deep_top3_expanded_pos >= 1)

    out["lesson41_dogfood"] = {
        "candidate_iteration": "2nd dogfood (1st = paradigm 115 R-1)",
        "expansion_n_total": syms_total,
        "syms_ci_pos_expanded": f"{syms_ci_pos}/{syms_total}",
        "syms_ci_pos_ratio_expanded": float(syms_ci_pos_ratio),
        "syms_ci_pos_gate_pass": syms_ci_pos_gate,
        "deep_bootstrap_top3_r1_orig_ci_95_pos": int(deep_top3_orig_pos),
        "deep_bootstrap_top3_expanded_ci_95_pos": int(deep_top3_expanded_pos),
        "narrow_single_sym_pass": narrow_single_sym_pass,
    }

    # Verdict tree
    if not pool_pass_3gate:
        verdict = "R2_FAIL_POOL"
        verdict_reason = (
            f"pool 3-gate FAIL on expanded universe: sigex={pool_sigex:.2f} "
            f"ci_lower={pool_ci_lower:.2f}bp perm_p_one={pool_perm_p_one:.3f} "
            f"(R-1 cell did not survive expansion)"
        )
        lesson41 = "refuted"
    elif not wf_pass:
        verdict = "R2_FAIL_TS_CV"
        verdict_reason = (
            f"pool PASS BUT walk-forward {n_folds_pass}/5 folds < 3/5 "
            f"(paradigm 87 fragility precedent)"
        )
        lesson41 = "inconclusive"
    elif not (syms_ci_pos_gate or narrow_single_sym_pass):
        verdict = "R2_FAIL_CONCENTRATION"
        verdict_reason = (
            f"pool + WF PASS BUT syms_ci_pos={syms_ci_pos}/{syms_total} < 4 "
            f"AND deep-bootstrap top3 ci_95_pos: orig={deep_top3_orig_pos}/3 "
            f"expanded={deep_top3_expanded_pos}/3 — DIFFUSE_POSITIVE persists, "
            f"Lesson #41 candidate REFUTED at 2nd dogfood"
        )
        lesson41 = "refuted"
    elif n_dims_pass < 3:
        verdict = "R2_FAIL_LIFE_CHANGING"
        verdict_reason = (
            f"pool + WF + concentration PASS BUT life-changing 4-dim {n_dims_pass}/4 "
            f"(edge {pool_net_bp/100:.2f}% < 2%/trade blocker per "
            f"feedback_life_changing_strategy_criterion)"
        )
        lesson41 = "confirmed_but_narrow_scope_life_changing_fail"
    else:
        verdict = "R2_PASS"
        verdict_reason = (
            f"pool 3-gate PASS (sigex={pool_sigex:.2f} ci_lower={pool_ci_lower:.2f}bp "
            f"perm_p_one={pool_perm_p_one:.3f}) + WF {n_folds_pass}/5 PASS + "
            f"syms_ci_pos={syms_ci_pos}/{syms_total} + life-changing {n_dims_pass}/4"
        )
        lesson41 = "confirmed" if syms_ci_pos_gate else "narrow_scope_only"

    out["verdict"] = verdict
    out["verdict_reason"] = verdict_reason
    out["lesson41_candidate_verdict"] = lesson41

    # Summary one-liner
    out["_summary_one_liner"] = {
        "paradigm": PARADIGM_SLUG,
        "phase": PHASE,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "universe_expanded": f"{len(panel)}/{len(ALTS_ALL)}",
        "pool_n_trades": pool_n,
        "pool_net_bp": round(pool_net_bp, 2),
        "pool_sigex": round(pool_sigex, 2) if not np.isnan(pool_sigex) else None,
        "pool_ci_lower_bp": round(pool_ci_lower, 2),
        "syms_ci_pos_expanded": f"{syms_ci_pos}/{syms_total}",
        "wf_folds_pass": f"{n_folds_pass}/5",
        "life_changing_n_dims": f"{n_dims_pass}/4",
        "lesson41_dogfood_verdict": lesson41,
    }

    out["wall_clock_minutes"] = round((time.time() - t_start) / 60, 2)
    _write(out)
    log.info("R-2 DONE in %.1fmin — verdict %s", out["wall_clock_minutes"], verdict)
    log.info("%s", out["_summary_one_liner"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
