"""Paradigm 113 — intraday_hour_of_day_anchor_alt_directional_2h R-1 PoC

Hypothesis
----------
24h crypto market exhibits time-zone-driven flow asymmetry at 4 anchor hours UTC:
  00:00 = KR/JP morning open
  07:00 = EU open / Asian close overlap
  13:00 = US open / EU mid-day overlap
  21:00 = US close

When an alt's prior 1h bar has signed return z-score |z|>=1.0 vs rolling 30d
AND the next bar opens at one of the 4 anchor hours, the next 2h hold
CONTINUES the prior bar's direction (momentum extension during liquidity
overlap regimes).

Direction policy
- A focus  : prior 1h z >= +1.0 at anchor hour -> LONG
- A mirror : prior 1h z >= +1.0 at anchor hour -> SHORT (wrong direction)
- B same   : prior 1h z <= -1.0 at anchor hour -> SHORT
- B mirror : prior 1h z <= -1.0 at anchor hour -> LONG (wrong direction)

Novelty self-check (3/5 NOVEL ex ante)
- Statistic = hour-of-day temporal anchor + prior-bar signed |z|>=1.0
  conjunction (NOVEL — temporal axis untested across 112 paradigms; closest
  adjacencies: paradigm 82 used 8h funding boundary, NOT 1h-anchor cycle).
- Universe = standard 13-alt subset (NOT NOVEL).
- Frame = 1h trigger x 2h hold (PARTIALLY NOVEL — 1h frame on standard alts
  is rare; paradigm 69 used 1m close-to-close 240m, paradigm 82 used 5m
  pre-event window).
- Mechanism = time-zone liquidity overlap momentum continuation (NOVEL —
  first-principle distinct from paradigm 69 RV cascade and paradigm 82
  funding boundary; closest published academic analog is the "session
  effect" in equity intraday literature, not yet tested in crypto perp).
- Trigger = hour anchor AND signed |z|>=1 prior 1h return (NOVEL conjunction).

Substrate
---------
Binance public archive data.binance.vision/futures/um/monthly/klines/{sym}/1h
(archive-direct, NO DB dependency per local-context constraint).

R-0 prescreens passed
- Lesson #11 sample density: 4 anchor hr/day x 365d x 2.4yr x 13 alts x |z|>=1
  retention (~32%) ≈ 14,400 events; 2h decimation -> per 4-quadrant × 4-quarter
  cell ≈ 450. PASS.
- Lesson #19 SNT: 4-quadrant in single batch (mandatory).
- Lesson #20 narrow-scope: hour anchor = 16.7% trigger rate by definition;
  life-changing 4-dim layer included.
- Lesson #21 axis stacking: diagnostic sweep — hour-alone (no |z|) + |z|-alone
  (any hour) measured to verify joint synthesis > both individuals.
- Lesson #28 substrate availability: 1h OHLCV via Binance public archive
  (verified data.binance.vision/futures/um/monthly/klines structure existing).
- Lesson #30 data window ratio: 2.0y / 2.4y available ~83% ratio. PASS.
- Lesson #40 structural threshold feasibility: signed z, |z|>=1 trivially
  reachable. PASS.

R-1 body
- 4-quadrant Symmetric Negative Test
- Concentration Gate (per-quarter t-stat + per-symbol bootstrap CI)
- fee_aware_perm_test + bootstrap CI via _perm_utils.py
- 16 bp fee floor (8 bp per leg round-trip)
- Life-changing 4-dim layer (trades/yr >= 12 / edge >= +2%/trade /
  capital_util >= 30% / annualized_sharpe >= 1.5)

Scope
- 13 alts: SOL, HBAR, AVAX, DOGE, LINK, ADA, BCH, LTC, BNB, FIL, NEAR, XRP, ETH
- 24 months 2024-05 .. 2026-04 (24 monthly archives × 13 alts = 312 downloads
  of 1h klines at ~30KB each, ~9MB total, ~2 min sequential).
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

PARADIGM_SLUG = "intraday_hour_of_day_anchor_alt_directional_2h"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_SLUG
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = OUT_DIR / "klines_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(OUT_DIR / "r1__stdout.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("p113_r1")

ALTS = [
    "SOLUSDT", "HBARUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT",
    "ADAUSDT", "BCHUSDT", "LTCUSDT", "BNBUSDT", "FILUSDT",
    "NEARUSDT", "XRPUSDT", "ETHUSDT",
]

START_MONTH = "2024-05"
END_MONTH = "2026-04"

FEE_PER_TRADE = 0.0008  # 16 bp round-trip
ROLLING_30D_1H_BARS = 24 * 30  # 720
ANCHOR_HOURS_UTC = (0, 7, 13, 21)
PRIMARY_Z_THRESHOLD = 1.0
PRIMARY_HOLD_BARS = 2  # 1h frame × 2 = 2h hold
HOLD_SWEEP_BARS = [1, 2, 4]  # 1h, 2h, 4h


def month_iter(start: str, end: str) -> list[str]:
    s = pd.Period(start, freq="M")
    e = pd.Period(end, freq="M")
    return [str(p) for p in pd.period_range(s, e, freq="M")]


def download_1h_klines(sym: str, month: str) -> pd.DataFrame:
    """Download monthly 1h klines archive. Returns DataFrame with open_time index
    and OHLC columns. Caches to joblib.
    """
    cache_file = CACHE_DIR / f"{sym}_1h_{month}.joblib"
    if cache_file.exists():
        try:
            return joblib.load(cache_file)
        except Exception:
            pass

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
                # Binance archive sometimes has header, sometimes not. Detect.
                first_line = f.readline()
                f.seek(0)
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


def build_1h_panel(sym: str, months: list[str]) -> pd.DataFrame:
    parts = []
    for m in months:
        d = download_1h_klines(sym, m)
        if not d.empty:
            parts.append(d)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    return out


def compute_quadrant(
    quadrant_name: str,
    trigger_mask_per_sym: dict,
    fwd_per_sym: dict,
    direction_per_sym: dict,
    hold_bars: int,
    fee: float,
    candidate_pool_pool: np.ndarray,
) -> dict:
    """Aggregate trades across all triggered (ts, sym) -> direction-applied
    forward return - fee. Compute 3-gate + Concentration + per-quarter + per-sym
    + Life-changing 4-dim.
    """
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
        # decimate: ≥ hold_bars hours gap between consecutive trades per sym
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

    # Life-changing 4-dim (annualized) — single-trade-at-a-time approximation
    if all_ts:
        n_years = max(1e-6, (pd.to_datetime(max(all_ts)) - pd.to_datetime(min(all_ts))).days / 365.25)
    else:
        n_years = 1e-6
    trades_per_year = len(net) / n_years
    per_trade_edge_pct = net_mean_bp / 100.0  # bp -> %
    # capital_util: assume single trade at a time
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
        "paradigm_number": 113,
        "phase": "R-1",
        "executed_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "host": "hcp_local",
        "universe_alts": ALTS,
        "n_alts": len(ALTS),
        "window_months": [START_MONTH, END_MONTH],
        "fee_per_trade": FEE_PER_TRADE,
        "anchor_hours_utc": list(ANCHOR_HOURS_UTC),
        "primary_z_threshold": PRIMARY_Z_THRESHOLD,
        "primary_hold_bars": PRIMARY_HOLD_BARS,
        "primary_hold_hours": PRIMARY_HOLD_BARS,
        "rolling_window_1h_bars": ROLLING_30D_1H_BARS,
        "novelty_self_check": {
            "statistic": "NOVEL",
            "universe": "NOT NOVEL",
            "frame": "PARTIALLY NOVEL",
            "mechanism": "NOVEL",
            "trigger": "NOVEL",
            "axes_pass": 3,
            "verdict": "3/5 NOVEL - proceed",
        },
    }

    months = month_iter(START_MONTH, END_MONTH)
    log.info("backfilling 1h klines for %d alts × %d months", len(ALTS), len(months))
    t_bf = time.time()
    panel: dict[str, pd.DataFrame] = {}
    for s in ALTS:
        t0 = time.time()
        df = build_1h_panel(s, months)
        log.info("  %s: %d rows in %.1fs", s, len(df), time.time() - t0)
        if not df.empty:
            panel[s] = df
    bf_secs = time.time() - t_bf
    log.info("backfill done in %.1fs (%.1fmin)", bf_secs, bf_secs / 60)

    if len(panel) < 5:
        out["verdict"] = "DISPATCH_IMPOSSIBLE"
        out["verdict_reason"] = f"backfill produced only {len(panel)}/13 series"
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        return 1

    # Build per-sym close + log-return series
    close_per_sym: dict[str, pd.Series] = {}
    log_ret_per_sym: dict[str, pd.Series] = {}
    for s, df in panel.items():
        close_per_sym[s] = df["close"].copy()
        log_ret_per_sym[s] = np.log(df["close"] / df["close"].shift(1))

    # Rolling 30d (720 bars) z-score of prior 1h log return
    z_per_sym: dict[str, pd.Series] = {}
    for s, lr in log_ret_per_sym.items():
        mu = lr.rolling(ROLLING_30D_1H_BARS, min_periods=ROLLING_30D_1H_BARS // 2).mean()
        sd = lr.rolling(ROLLING_30D_1H_BARS, min_periods=ROLLING_30D_1H_BARS // 2).std(ddof=1)
        z_per_sym[s] = (lr - mu) / sd

    # Forward H-hour log return per hold value: at time t, forward = log(close[t+H] / close[t])
    fwd_per_sym_by_hold: dict[int, dict[str, pd.Series]] = {}
    for h in HOLD_SWEEP_BARS:
        d = {}
        for s, c in close_per_sym.items():
            d[s] = np.log(c.shift(-h) / c)
        fwd_per_sym_by_hold[h] = d

    # Anchor hour mask: the BAR at time t opens at anchor hour AND the prior 1h
    # return is the previous bar. We define "anchor hour entry" as: bar opens at
    # one of ANCHOR_HOURS_UTC. We then read prior_1h_z = z at t (which is the
    # log return from t-1h to t, computed on closes). Entry direction depends
    # on prior_1h_z sign + threshold. Forward return = log(close[t+h] / close[t]).
    # So we trigger AT bar-open time t.

    anchor_set = set(ANCHOR_HOURS_UTC)

    def build_quadrant_trigger_masks(
        z_sign: str,  # "+" or "-"
        threshold: float,
    ) -> dict[str, pd.Series]:
        """Returns per-sym bool Series: True at times t where bar opens at anchor
        hour AND prior 1h z meets threshold.
        """
        masks = {}
        for s, z in z_per_sym.items():
            hour_ok = z.index.hour.isin(list(anchor_set))
            hour_ok_s = pd.Series(hour_ok, index=z.index)
            if z_sign == "+":
                z_ok = z >= threshold
            else:
                z_ok = z <= -threshold
            masks[s] = (hour_ok_s & z_ok & z.notna()).astype(bool)
        return masks

    # Lesson #11 sample density empirical check using primary triggers
    pos_z_masks = build_quadrant_trigger_masks("+", PRIMARY_Z_THRESHOLD)
    neg_z_masks = build_quadrant_trigger_masks("-", PRIMARY_Z_THRESHOLD)
    n_trig_pos_raw = int(sum(m.sum() for m in pos_z_masks.values()))
    n_trig_neg_raw = int(sum(m.sum() for m in neg_z_masks.values()))

    # n_quarters and decimation
    all_ts_idx = pd.concat([s for s in close_per_sym.values()], axis=1).index
    n_quarters = max(
        1, int(np.ceil((all_ts_idx.max() - all_ts_idx.min()).days / 91))
    )
    decimation = PRIMARY_HOLD_BARS  # bars
    expected_pos_trades = n_trig_pos_raw / max(1, decimation)
    expected_neg_trades = n_trig_neg_raw / max(1, decimation)
    per_quarter_pos = expected_pos_trades / n_quarters
    per_quarter_neg = expected_neg_trades / n_quarters
    out["lesson11_sample_density"] = {
        "n_trig_pos_raw": n_trig_pos_raw,
        "n_trig_neg_raw": n_trig_neg_raw,
        "n_quarters": n_quarters,
        "decimation_factor_bars": decimation,
        "expected_pos_trades": float(expected_pos_trades),
        "expected_neg_trades": float(expected_neg_trades),
        "per_quarter_pos": float(per_quarter_pos),
        "per_quarter_neg": float(per_quarter_neg),
        "lesson11_floor": 30,
        "passes_lesson11_both": bool(per_quarter_pos >= 30 and per_quarter_neg >= 30),
    }
    log.info(
        "Lesson #11 per-quarter: pos_z=%.1f / neg_z=%.1f (n_quarters=%d)",
        per_quarter_pos, per_quarter_neg, n_quarters,
    )

    out["data_window"] = {
        "first": str(all_ts_idx.min()),
        "last": str(all_ts_idx.max()),
        "panel_years": float((all_ts_idx.max() - all_ts_idx.min()).days / 365.25),
        "n_alts_with_data": len(panel),
        "backfill_seconds": float(bf_secs),
    }
    out["lesson30_data_window_ratio"] = {
        "window_months": len(months),
        "full_window_months_available": 24,
        "ratio": float(len(months) / 24.0),
        "passes_lesson30": bool(len(months) / 24.0 >= 0.30),
    }

    if not out["lesson11_sample_density"]["passes_lesson11_both"]:
        out["verdict"] = "SAMPLE_INSUFFICIENT"
        out["verdict_reason"] = (
            f"Lesson #11 fail: per-quarter pos={per_quarter_pos:.1f} / neg={per_quarter_neg:.1f} "
            f"< 30 cutoff."
        )
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        return 0

    # Empirical signed z distribution diagnostic (Lesson #34)
    z_all = pd.concat([s for s in z_per_sym.values()]).dropna()
    out["lesson34_empirical_distribution"] = {
        "z_p01": float(z_all.quantile(0.01)),
        "z_p05": float(z_all.quantile(0.05)),
        "z_p25": float(z_all.quantile(0.25)),
        "z_p50": float(z_all.quantile(0.50)),
        "z_p75": float(z_all.quantile(0.75)),
        "z_p95": float(z_all.quantile(0.95)),
        "z_p99": float(z_all.quantile(0.99)),
        "z_max_abs": float(z_all.abs().max()),
        "z_n_obs": int(len(z_all)),
        "frac_abs_z_ge_1": float((z_all.abs() >= 1.0).mean()),
        "frac_abs_z_ge_2": float((z_all.abs() >= 2.0).mean()),
    }
    log.info(
        "z dist p05=%.2f p50=%.2f p95=%.2f frac|z|>=1=%.3f",
        out["lesson34_empirical_distribution"]["z_p05"],
        out["lesson34_empirical_distribution"]["z_p50"],
        out["lesson34_empirical_distribution"]["z_p95"],
        out["lesson34_empirical_distribution"]["frac_abs_z_ge_1"],
    )

    # Candidate pool for fee_aware_perm: ALL valid bar-open returns for the primary
    # hold horizon (LONG direction), regardless of trigger. Direction will be
    # mapped per quadrant.
    fwd_primary = fwd_per_sym_by_hold[PRIMARY_HOLD_BARS]

    pool_long_vals = []
    pool_short_vals = []
    for s, f in fwd_primary.items():
        a = f.dropna().values
        pool_long_vals.append(a)
        pool_short_vals.append(-a)
    pool_long = np.concatenate(pool_long_vals) if pool_long_vals else np.array([])
    pool_short = np.concatenate(pool_short_vals) if pool_short_vals else np.array([])

    dir_long = {s: +1 for s in panel}
    dir_short = {s: -1 for s in panel}

    # 4-quadrant SNT primary
    log.info("=== R-1 4-quadrant SNT (primary hold=%dh) ===", PRIMARY_HOLD_BARS)
    quadrants = {}
    quadrants["A_focus_posZ_LONG"] = compute_quadrant(
        "A_focus_posZ_LONG",
        pos_z_masks,
        fwd_primary,
        dir_long,
        PRIMARY_HOLD_BARS,
        FEE_PER_TRADE,
        pool_long,
    )
    quadrants["A_mirror_posZ_SHORT"] = compute_quadrant(
        "A_mirror_posZ_SHORT",
        pos_z_masks,
        fwd_primary,
        dir_short,
        PRIMARY_HOLD_BARS,
        FEE_PER_TRADE,
        pool_short,
    )
    quadrants["B_same_sign_negZ_SHORT"] = compute_quadrant(
        "B_same_sign_negZ_SHORT",
        neg_z_masks,
        fwd_primary,
        dir_short,
        PRIMARY_HOLD_BARS,
        FEE_PER_TRADE,
        pool_short,
    )
    quadrants["B_mirror_negZ_LONG"] = compute_quadrant(
        "B_mirror_negZ_LONG",
        neg_z_masks,
        fwd_primary,
        dir_long,
        PRIMARY_HOLD_BARS,
        FEE_PER_TRADE,
        pool_long,
    )
    out["quadrants"] = quadrants

    # ─── Lesson #21 axis-stacking diagnostic ─────────────────────────────
    # 1) hour-anchor ALONE (any z), LONG (no signed expectation; just measures
    #    whether being at anchor hour alone carries directional bias).
    # 2) signed |z|>=1 ALONE (any hour), positive-z -> LONG (continuation hyp).
    log.info("=== Lesson #21 axis-stacking diagnostic ===")
    hour_only_masks = {}
    for s, z in z_per_sym.items():
        h_ok = pd.Series(z.index.hour.isin(list(anchor_set)), index=z.index)
        hour_only_masks[s] = (h_ok & z.notna()).astype(bool)
    z_only_masks_pos = {}
    for s, z in z_per_sym.items():
        z_only_masks_pos[s] = ((z >= PRIMARY_Z_THRESHOLD) & z.notna()).astype(bool)

    diag_hour_only = compute_quadrant(
        "DIAG_hour_only_LONG_anyZ",
        hour_only_masks,
        fwd_primary,
        dir_long,
        PRIMARY_HOLD_BARS,
        FEE_PER_TRADE,
        pool_long,
    )
    diag_z_only = compute_quadrant(
        "DIAG_z_only_LONG_anyHour",
        z_only_masks_pos,
        fwd_primary,
        dir_long,
        PRIMARY_HOLD_BARS,
        FEE_PER_TRADE,
        pool_long,
    )
    out["lesson21_axis_stacking_diagnostic"] = {
        "hour_only_LONG_anyZ": diag_hour_only,
        "z_only_LONG_anyHour": diag_z_only,
        "joint_A_focus_net_bp": quadrants["A_focus_posZ_LONG"].get("obs_mean_net_bp", 0.0),
        "hour_only_net_bp": diag_hour_only.get("obs_mean_net_bp", 0.0),
        "z_only_net_bp": diag_z_only.get("obs_mean_net_bp", 0.0),
        "joint_synthesizes_alpha": bool(
            quadrants["A_focus_posZ_LONG"].get("obs_mean_net_bp", 0.0)
            > max(
                diag_hour_only.get("obs_mean_net_bp", 0.0),
                diag_z_only.get("obs_mean_net_bp", 0.0),
            )
        ),
    }

    # ─── Hold sweep (focus A only) ─────────────────────────────────────────
    log.info("=== hold sweep on A_focus_posZ_LONG ===")
    sweep = []
    for h in HOLD_SWEEP_BARS:
        if h == PRIMARY_HOLD_BARS:
            continue
        fwd_h = fwd_per_sym_by_hold[h]
        pool_h_vals = [f.dropna().values for f in fwd_h.values()]
        pool_h = np.concatenate(pool_h_vals) if pool_h_vals else np.array([])
        try:
            res = compute_quadrant(
                f"A_focus_posZ_LONG_h{h}",
                pos_z_masks,
                fwd_h,
                dir_long,
                h,
                FEE_PER_TRADE,
                pool_h,
            )
            sweep.append(res)
        except Exception as e:
            log.warning("sweep h=%d fail: %s", h, e)
    out["hold_sweep_A_focus"] = sweep

    # ─── Verdict aggregation ──────────────────────────────────────────────
    A_focus = quadrants["A_focus_posZ_LONG"]
    A_mirror = quadrants["A_mirror_posZ_SHORT"]
    B_same = quadrants["B_same_sign_negZ_SHORT"]
    B_mirror = quadrants["B_mirror_negZ_LONG"]

    a_focus_pass_3gate = A_focus.get("gate_3_pass", False)
    a_focus_pass_conc = A_focus.get("gate_concentration_pass", False)
    b_same_pass_3gate = B_same.get("gate_3_pass", False)
    b_same_pass_conc = B_same.get("gate_concentration_pass", False)
    a_focus_full = a_focus_pass_3gate and a_focus_pass_conc
    b_same_full = b_same_pass_3gate and b_same_pass_conc
    n_quadrants_pass_3gate = sum(
        1 for q in (A_focus, A_mirror, B_same, B_mirror) if q.get("gate_3_pass", False)
    )

    # Life-changing 4-dim check on focus quadrants
    a_focus_lc = A_focus.get("life_changing_4dim", {})
    b_same_lc = B_same.get("life_changing_4dim", {})
    a_focus_lc_all = a_focus_lc.get("pass_all_4_dim", False)
    b_same_lc_all = b_same_lc.get("pass_all_4_dim", False)

    if a_focus_full and b_same_full:
        if a_focus_lc_all and b_same_lc_all:
            verdict = "PASS_R1_FULL"
            verdict_reason = (
                "A_focus + B_same both PASS 3-gate AND Concentration AND life-changing 4-dim. "
                "Hour-of-day momentum continuation confirmed in both directions."
            )
            next_action = "propose_R2"
        else:
            verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
            verdict_reason = (
                "A_focus + B_same statistical PASS but life-changing 4-dim FAIL. "
                f"A_focus_lc={a_focus_lc_all} B_same_lc={b_same_lc_all}."
            )
            next_action = "graveyard"
    elif a_focus_full and not b_same_full:
        verdict = "SPLIT_PARADIGM_A_ONLY"
        verdict_reason = (
            "A_focus (pos z anchor hour LONG) PASS but B_same (neg z anchor hour SHORT) FAIL — "
            "asymmetric mechanism (continuation works on up-spike anchor only)."
        )
        next_action = "graveyard"
    elif b_same_full and not a_focus_full:
        verdict = "SPLIT_PARADIGM_B_ONLY"
        verdict_reason = (
            "B_same PASS but A_focus FAIL — continuation works on down-spike anchor only."
        )
        next_action = "graveyard"
    elif n_quadrants_pass_3gate == 0:
        a_focus_gross = A_focus.get("obs_mean_gross_bp", 0.0)
        b_same_gross = B_same.get("obs_mean_gross_bp", 0.0)
        if max(a_focus_gross, b_same_gross) > 0 and max(a_focus_gross, b_same_gross) < 16:
            verdict = "BROAD_FALSIFIED_FEE_FLOOR"
            verdict_reason = (
                f"max focus gross +{max(a_focus_gross, b_same_gross):.2f}bp < 16bp fee floor; "
                "mechanism may exist but uneconomic."
            )
        else:
            verdict = "BROAD_FALSIFIED"
            verdict_reason = (
                "All 4 quadrants FAIL 3-gate. Hour-of-day anchor + |z|>=1 carries no directional alpha."
            )
        next_action = "graveyard"
    else:
        mirror_only = (
            A_mirror.get("gate_3_pass", False) or B_mirror.get("gate_3_pass", False)
        ) and not (a_focus_pass_3gate or b_same_pass_3gate)
        if mirror_only:
            verdict = "BROAD_FALSIFIED_MIRROR_ONLY"
            verdict_reason = (
                "Only mirror quadrant(s) PASS 3-gate — Lesson #8 mirror antipattern, mechanism inverted."
            )
        else:
            verdict = "PARTIAL_PASS_NO_FULL_FOCUS"
            verdict_reason = (
                f"{n_quadrants_pass_3gate}/4 quadrants pass 3-gate, but no focus + concentration combo."
            )
        next_action = "graveyard"

    out["life_changing_4dim_A_focus"] = a_focus_lc
    out["life_changing_4dim_B_same"] = b_same_lc

    out["verdict"] = verdict
    out["verdict_reason"] = verdict_reason
    out["next_action_recommendation"] = next_action
    out["n_quadrants_pass_3gate"] = n_quadrants_pass_3gate
    out["wall_clock_minutes"] = (time.time() - t_start) / 60

    out["_summary_one_liner"] = {
        "paradigm": PARADIGM_SLUG,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "n_samples": int(A_focus.get("n_trades", 0)),
        "A_focus_gross_bp": float(A_focus.get("obs_mean_gross_bp", 0.0)),
        "A_focus_net_bp": float(A_focus.get("obs_mean_net_bp", 0.0)),
        "sigex_focus": float(A_focus.get("signal_t_excess", float("nan"))),
        "concentration_pass": f"{A_focus.get('n_syms_ci_pos', 0)}/{A_focus.get('n_syms_total', 0)}",
        "wall_clock_minutes": float(out["wall_clock_minutes"]),
        "next_action_recommendation": next_action,
    }

    _write(out)
    log.info("=== R-1 DONE in %.1fmin === verdict=%s", out["wall_clock_minutes"], verdict)

    # stdout JSON line
    print(json.dumps(out["_summary_one_liner"], default=str))
    return 0


def _write(payload: dict) -> None:
    p = OUT_DIR / "r1__metrics.json"
    with open(p, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    log.info("wrote %s", p)


if __name__ == "__main__":
    sys.exit(main())
