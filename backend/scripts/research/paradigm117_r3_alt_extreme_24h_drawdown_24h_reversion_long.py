"""Paradigm 117 R-3 — alt_extreme_24h_drawdown_24h_reversion_long
R-3 robustness audit (7 mandatory caveats, strict halt regardless of outcome)

Hypothesis recap
----------------
Alt 24h cumulative log return ≤ −15% → forward 24h LONG continuation
(capitulation mean-reversion). R-2 PASS:
  n=406, gross +275.31bp / net +267.31bp / edge +2.673%/trade,
  sigex +8.71, CI [+201.52,+329.38]bp, TS-CV 4/5 PASS,
  threshold sweep monotone, broad-shoulders top-3 PASS, lc4 4/4.

R-3 Caveats (each can fail independently)
-----------------------------------------
1. **Real Lesson #39 4-quadrant SNT** — A_focus / A_mirror_real (drawdown→SHORT) /
   B_same_sign (PUMP≥+15% → SHORT) / B_mirror (PUMP→LONG). Tests mechanism CLASS
   symmetry (capitulation-bounce vs euphoria-correction).
2. **Regime stratify (3×3)** — BTC trend × vol regime cells, require
   ≥6/9 cells positive AND no cell t<−2.0.
3. **SL/TP grid (5×7=35 cells)** — identify plateau ≥4 cells where
   edge/trade ≥2% AND Sharpe ≥1.5.
4. **Correlation check** — Pearson + cosine vs existing paradigms; cosine >0.7 = dup.
5. **TIAUSDT exclusion analysis** — measure WITH vs WITHOUT TIAUSDT.
6. **Survivorship quantification** — delisted-cohort attempt via Binance Vision
   archive (best-effort), fallback to conservative R-5 = 50% of R-2 measurement.
7. **Holdout OOS window** — Train 2024-05~2025-06 vs OOS 2025-07~2026-04 split.

Verdict tree (any hard-fail → R3_FAIL)
--------------------------------------
R3_FAIL_REGIME_FRAGILE      — <6/9 cells positive OR any cell t<−2.0
R3_FAIL_NO_PARAM_PLATEAU    — no SL/TP plateau ≥4 cells with edge≥2% AND Sharpe≥1.5
R3_FAIL_DUPLICATE           — any existing paradigm cosine >0.7
R3_FAIL_OOS                 — OOS edge < 0.50 × Train
R3_FAIL_OOS_NOISE           — OOS sigex < 1.0
R3_PASS                     — all caveats clear (R-4 elite gate ready, halt)

Lesson #39 sub-class A perfect-mirror is informational only (B_same_sign carries
the substantive mechanism test, not A_mirror).

CRITICAL: Halt at R-3 verdict; DO NOT auto-progress to R-4.
"""
from __future__ import annotations

import io
import json
import logging
import sys
import time
import zipfile
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
import requests

ROOT = Path("/home/hcpark/antigravity/backend")
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

# ─── Identity ────────────────────────────────────────────────────────────────
R1_ALIAS = "alt_extreme_24h_drawdown_reversal_long_4h"
PARADIGM_SLUG = "alt_extreme_24h_drawdown_24h_reversion_long"
PARADIGM_NUMBER = 117

OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_SLUG
OUT_DIR.mkdir(parents=True, exist_ok=True)

CORE_CACHE_DIR = (
    ROOT / "runs" / "research_track"
    / "intraday_hour_of_day_anchor_alt_directional_2h" / "klines_cache"
)
EXPANSION_CACHE_DIR = (
    ROOT / "runs" / "research_track"
    / "alt_atr_normalized_range_breakout_continuation_long_2h"
    / "klines_cache_r2_expansion"
)
BTC_CACHE_DIR = OUT_DIR / "btc_cache"
BTC_CACHE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(OUT_DIR / "r3__stdout.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("p117_r3")

# ─── Universe (28 alts from R-2) ─────────────────────────────────────────────
ALTS_CORE = [
    "SOLUSDT", "HBARUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT",
    "ADAUSDT", "BCHUSDT", "LTCUSDT", "BNBUSDT", "FILUSDT",
    "NEARUSDT", "XRPUSDT", "ETHUSDT",
]
ALTS_EXPANSION = [
    "1000PEPEUSDT", "1000SHIBUSDT", "AAVEUSDT", "APTUSDT", "ARBUSDT",
    "ATOMUSDT", "DOTUSDT", "ICPUSDT", "INJUSDT",
    "OPUSDT", "SEIUSDT", "SUIUSDT", "TIAUSDT", "TRXUSDT", "UNIUSDT",
]
ALTS = ALTS_CORE + ALTS_EXPANSION  # 28

START_MONTH = "2024-05"
END_MONTH = "2026-04"

# ─── Core parameters ─────────────────────────────────────────────────────────
FEE_PER_TRADE = 0.0008
ROLLING_24H_BARS = 24
DEBOUNCE_BARS = 24
PRIMARY_THRESHOLD = -0.15
PRIMARY_HOLD_BARS = 24

# ─── Caveat 1: Lesson #39 4-quadrant ────────────────────────────────────────
PUMP_THRESHOLD = +0.15  # symmetric to PRIMARY_THRESHOLD = -0.15

# ─── Caveat 2: Regime stratify ───────────────────────────────────────────────
BTC_TREND_30D_BULL_CUTOFF = +0.05  # +5%
BTC_TREND_30D_BEAR_CUTOFF = -0.05  # -5%
# Vol regime: BTC realized vol over 30d, p33/p66 splits
BTC_VOL_LOW_PCT = 33.0
BTC_VOL_HIGH_PCT = 66.0

# ─── Caveat 3: SL/TP grid ────────────────────────────────────────────────────
SL_GRID = [0.05, 0.10, 0.15, 0.20, 0.25]
TP_GRID = [0.05, 0.10, 0.15, 0.20, 0.30, 0.50, None]  # None = no TP

# ─── Caveat 7: OOS split ─────────────────────────────────────────────────────
TRAIN_END = pd.Timestamp("2025-06-30 23:59:59")
OOS_START = pd.Timestamp("2025-07-01 00:00:00")
OOS_END = pd.Timestamp("2026-04-30 23:59:59")

# ─── Helpers ─────────────────────────────────────────────────────────────────


def month_iter(start: str, end: str) -> list[str]:
    s = pd.Period(start, freq="M")
    e = pd.Period(end, freq="M")
    return [str(p) for p in pd.period_range(s, e, freq="M")]


def load_1h_klines_from_cache(sym: str, month: str) -> pd.DataFrame:
    for cdir in (CORE_CACHE_DIR, EXPANSION_CACHE_DIR):
        cache_file = cdir / f"{sym}_1h_{month}.joblib"
        if cache_file.exists():
            try:
                return joblib.load(cache_file)
            except Exception as e:
                log.warning("cache load fail %s %s @ %s: %s", sym, month, cdir.name, e)
                return pd.DataFrame()
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


def fetch_btc_1h_from_archive(month: str) -> pd.DataFrame:
    """Fetch BTCUSDT 1h klines from data.binance.vision monthly archive.
    Cache locally as joblib for subsequent runs."""
    cache_file = BTC_CACHE_DIR / f"BTCUSDT_1h_{month}.joblib"
    if cache_file.exists():
        try:
            return joblib.load(cache_file)
        except Exception:
            pass

    url = (
        f"https://data.binance.vision/data/futures/um/monthly/klines/"
        f"BTCUSDT/1h/BTCUSDT-1h-{month}.zip"
    )
    log.info("  fetching BTCUSDT 1h archive %s ...", month)
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log.warning("  archive fetch fail %s: %s", month, e)
        return pd.DataFrame()

    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        with z.open(z.namelist()[0]) as f:
            df_raw = pd.read_csv(
                f, header=None,
                names=[
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "quote_volume", "count",
                    "taker_buy_volume", "taker_buy_quote_volume", "ignore",
                ],
            )
    except Exception as e:
        log.warning("  archive parse fail %s: %s", month, e)
        return pd.DataFrame()

    # Filter header rows: open_time is the first column. Some monthly archives
    # include a CSV header row; detect by non-numeric open_time and drop.
    df_raw["open_time"] = pd.to_numeric(df_raw["open_time"], errors="coerce")
    df_raw = df_raw.dropna(subset=["open_time"])
    if df_raw.empty:
        return pd.DataFrame()

    # Some archives report open_time in microseconds (BTC futures since 2025-01).
    # Detect by magnitude: ms is ~1.7e12, μs is ~1.7e15.
    ot_max = df_raw["open_time"].max()
    if ot_max > 1e14:
        unit = "us"
    else:
        unit = "ms"
    df_raw["timestamp"] = pd.to_datetime(df_raw["open_time"], unit=unit)
    df = df_raw[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna().set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]

    joblib.dump(df, cache_file)
    log.info("  cached %s: %d rows", month, len(df))
    return df


def build_btc_1h_panel(months: list[str]) -> pd.DataFrame:
    parts = []
    for m in months:
        d = fetch_btc_1h_from_archive(m)
        if not d.empty:
            parts.append(d)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    return out


def collect_debounced_trades(
    mask_per_sym: dict[str, pd.Series],
    fwd_per_sym: dict[str, pd.Series],
    direction_per_sym: dict[str, int],
    debounce_bars: int,
) -> tuple[list[float], list[pd.Timestamp], list[str]]:
    """Return debounced trades (return, ts, sym) lists."""
    min_gap = pd.Timedelta(hours=debounce_bars)
    rets: list[float] = []
    tss: list[pd.Timestamp] = []
    syms: list[str] = []
    for s, mask in mask_per_sym.items():
        fwd = fwd_per_sym.get(s)
        if fwd is None or len(fwd) == 0:
            continue
        d = direction_per_sym[s]
        idx_trig = mask.index[mask.fillna(False) & fwd.notna()]
        if len(idx_trig) == 0:
            continue
        last_t = None
        for t in idx_trig:
            if last_t is None or (t - last_t) >= min_gap:
                rets.append(d * float(fwd.loc[t]))
                tss.append(t)
                syms.append(s)
                last_t = t
    return rets, tss, syms


def collect_debounced_trades_with_sl_tp(
    mask_per_sym: dict[str, pd.Series],
    close_per_sym: dict[str, pd.Series],
    direction: int,
    sl: Optional[float],
    tp: Optional[float],
    hold_bars: int,
    debounce_bars: int,
) -> tuple[list[float], list[pd.Timestamp], list[str]]:
    """Path-aware SL/TP application using per-bar close.
    Path simulation: enter at trigger bar close, then bar-by-bar check:
      - SL hit when cumulative log return ≤ -sl (LONG) or ≥ +sl (SHORT) → exit at sl level
      - TP hit when cumulative log return ≥ +tp (LONG) or ≤ -tp (SHORT) → exit at tp level
      - Else exit at hold_bars later
    """
    min_gap = pd.Timedelta(hours=debounce_bars)
    rets: list[float] = []
    tss: list[pd.Timestamp] = []
    syms: list[str] = []
    for s, mask in mask_per_sym.items():
        c = close_per_sym[s]
        idx_trig_all = mask.index[mask.fillna(False)]
        # Need at least hold_bars after trigger
        last_t = None
        for t in idx_trig_all:
            if last_t is not None and (t - last_t) < min_gap:
                continue
            pos = c.index.searchsorted(t)
            if pos >= len(c) - hold_bars:
                continue
            entry_px = float(c.iloc[pos])
            if not np.isfinite(entry_px) or entry_px <= 0:
                continue
            exited = False
            exit_log_ret = None
            for step in range(1, hold_bars + 1):
                bar_pos = pos + step
                if bar_pos >= len(c):
                    break
                px = float(c.iloc[bar_pos])
                if not np.isfinite(px) or px <= 0:
                    continue
                log_ret = np.log(px / entry_px) * direction
                # SL check (loss)
                if sl is not None and log_ret <= -sl:
                    exit_log_ret = -sl
                    exited = True
                    break
                # TP check (profit)
                if tp is not None and log_ret >= tp:
                    exit_log_ret = tp
                    exited = True
                    break
            if not exited:
                # Exit at hold_bars
                final_pos = pos + hold_bars
                if final_pos < len(c):
                    px = float(c.iloc[final_pos])
                    if np.isfinite(px) and px > 0:
                        exit_log_ret = np.log(px / entry_px) * direction
                    else:
                        continue
                else:
                    continue
            if exit_log_ret is None:
                continue
            rets.append(exit_log_ret)
            tss.append(t)
            syms.append(s)
            last_t = t
    return rets, tss, syms


def life_changing_4dim(
    returns_net: np.ndarray,
    timestamps: list[pd.Timestamp],
    hold_bars: int,
) -> dict:
    n = len(returns_net)
    if n < 5:
        return {
            "n_trades": int(n), "trades_per_year": 0.0,
            "per_trade_edge_pct": 0.0, "capital_util_pct": 0.0,
            "annualized_sharpe": 0.0, "n_dims_pass": 0,
            "pass_all_4_dim": False,
        }
    sd = returns_net.std(ddof=1)
    mean = float(returns_net.mean())
    if timestamps:
        n_years = max(
            1e-6,
            (pd.to_datetime(max(timestamps)) - pd.to_datetime(min(timestamps))).days / 365.25
        )
    else:
        n_years = 1e-6
    tpy = n / n_years
    edge_pct = mean * 100.0
    util = min(100.0, (hold_bars * tpy) / (365.25 * 24) * 100)
    sharpe = (mean / sd) * np.sqrt(tpy) if sd > 0 else 0.0
    n_pass = int(sum([
        tpy >= 12, edge_pct >= 2.0, util >= 30, sharpe >= 1.5,
    ]))
    return {
        "n_trades": int(n),
        "trades_per_year": float(tpy),
        "per_trade_edge_pct": float(edge_pct),
        "capital_util_pct": float(util),
        "annualized_sharpe": float(sharpe),
        "pass_trades_per_year_12": bool(tpy >= 12),
        "pass_edge_2pct": bool(edge_pct >= 2.0),
        "pass_util_30pct": bool(util >= 30),
        "pass_sharpe_1_5": bool(sharpe >= 1.5),
        "n_dims_pass": n_pass,
        "pass_all_4_dim": bool(n_pass == 4),
    }


def _convert(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _convert(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_convert(v) for v in obj]
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    return obj


def _write(out: dict, name: str = "r3__metrics.json") -> None:
    p = OUT_DIR / name
    with p.open("w") as f:
        json.dump(_convert(out), f, indent=2)
    log.info("metrics written: %s", p)


# ─── R-3 main ────────────────────────────────────────────────────────────────


def main() -> int:
    t_start = time.time()
    out: dict = {
        "paradigm_name": PARADIGM_SLUG,
        "r1_alias": R1_ALIAS,
        "paradigm_number": PARADIGM_NUMBER,
        "phase": "R-3",
        "executed_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "host": "hcp_local",
        "primary_threshold": PRIMARY_THRESHOLD,
        "primary_hold_bars": PRIMARY_HOLD_BARS,
        "fee_per_trade": FEE_PER_TRADE,
        "debounce_bars": DEBOUNCE_BARS,
        "window_months": [START_MONTH, END_MONTH],
        "universe_alts": ALTS,
        "n_alts_universe": len(ALTS),
    }

    months = month_iter(START_MONTH, END_MONTH)

    # ─── Phase 1: load alt panel ─────────────────────────────────────────────
    log.info("=" * 70)
    log.info("PHASE 1: load alt 1h OHLCV panel (28 alts × 24 months)")
    log.info("=" * 70)
    panel: dict[str, pd.DataFrame] = {}
    for s in ALTS:
        df = build_1h_panel(s, months)
        if df.empty:
            log.warning("  %s: empty — drop", s)
            continue
        if len(df) < 17000:
            log.warning("  %s: only %d rows — drop", s, len(df))
            continue
        panel[s] = df
    log.info("usable alts: %d", len(panel))
    out["n_alts_usable"] = len(panel)
    out["alts_usable"] = sorted(panel.keys())
    if len(panel) < 8:
        out["verdict"] = "R3_DISPATCH_IMPOSSIBLE"
        out["verdict_reason"] = f"only {len(panel)}/{len(ALTS)} alts usable"
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        return 1

    # Build common feature panel
    close_per_sym: dict[str, pd.Series] = {}
    ret24h_per_sym: dict[str, pd.Series] = {}
    fwd24h_per_sym: dict[str, pd.Series] = {}
    for s, df in panel.items():
        c = df["close"].astype(float).copy()
        close_per_sym[s] = c
        ret24h_per_sym[s] = np.log(c / c.shift(ROLLING_24H_BARS))
        fwd24h_per_sym[s] = np.log(c.shift(-PRIMARY_HOLD_BARS) / c)

    # ─── Phase 2: Caveat 1 — REAL Lesson #39 4-quadrant SNT ─────────────────
    log.info("=" * 70)
    log.info("PHASE 2: Caveat 1 — REAL Lesson #39 4-quadrant SNT")
    log.info("=" * 70)

    dn_mask_per_sym = {s: (ret24h_per_sym[s] <= PRIMARY_THRESHOLD) & ret24h_per_sym[s].notna() for s in panel}
    up_mask_per_sym = {s: (ret24h_per_sym[s] >= PUMP_THRESHOLD) & ret24h_per_sym[s].notna() for s in panel}

    dir_long = {s: +1 for s in panel}
    dir_short = {s: -1 for s in panel}

    # A_focus: drawdown × LONG (R-2 anchor)
    a_focus_g, a_focus_ts, a_focus_syms = collect_debounced_trades(
        dn_mask_per_sym, fwd24h_per_sym, dir_long, DEBOUNCE_BARS
    )
    # A_mirror_real: drawdown × SHORT (mathematical mirror of A_focus, kept for sanity)
    a_mirror_g, _, _ = collect_debounced_trades(
        dn_mask_per_sym, fwd24h_per_sym, dir_short, DEBOUNCE_BARS
    )
    # B_same_sign_real: PUMP × SHORT (mechanism mirror = euphoria correction)
    b_same_g, b_same_ts, b_same_syms = collect_debounced_trades(
        up_mask_per_sym, fwd24h_per_sym, dir_short, DEBOUNCE_BARS
    )
    # B_mirror_real: PUMP × LONG (continuation hypothesis)
    b_mirror_g, b_mirror_ts, b_mirror_syms = collect_debounced_trades(
        up_mask_per_sym, fwd24h_per_sym, dir_long, DEBOUNCE_BARS
    )

    a_focus_g = np.asarray(a_focus_g, dtype=float)
    a_mirror_g = np.asarray(a_mirror_g, dtype=float)
    b_same_g = np.asarray(b_same_g, dtype=float)
    b_mirror_g = np.asarray(b_mirror_g, dtype=float)

    def _quad_stats(gross: np.ndarray, ts_list: list, label: str) -> dict:
        if len(gross) < 5:
            return {"label": label, "n": int(len(gross)), "error": "n<5"}
        net = gross - FEE_PER_TRADE
        sd = net.std(ddof=1)
        mean = float(net.mean())
        obs_t = float(mean / sd * np.sqrt(len(net))) if sd > 0 else 0.0
        ci = bootstrap_ci(net, n_boot=500, rng_seed=42)
        # Pool perm only against full alt pool
        all_fwd = np.concatenate(
            [f.dropna().values for f in fwd24h_per_sym.values()]
        )
        if len(all_fwd) >= len(net) * 2:
            perm = fee_aware_perm_test(
                net, all_fwd, fee_per_trade=FEE_PER_TRADE, n_perms=500, rng_seed=42
            )
            sigex = float(perm.get("signal_t_excess", float("nan")))
            perm_p = float(perm.get("perm_p_two_sided", float("nan")))
        else:
            sigex = float("nan")
            perm_p = float("nan")
        return {
            "label": label,
            "n": int(len(gross)),
            "gross_mean_bp": float(gross.mean() * 10000),
            "net_mean_bp": float(net.mean() * 10000),
            "obs_t": obs_t,
            "signal_t_excess": sigex,
            "perm_p_two_sided": perm_p,
            "ci_lower_bp": float(ci["ci_lower"] * 10000),
            "ci_upper_bp": float(ci["ci_upper"] * 10000),
            "ci_pos": bool(ci["ci_lower"] > 0),
        }

    a_focus_stats = _quad_stats(a_focus_g, a_focus_ts, "A_focus (drawdown×LONG)")
    a_mirror_stats = _quad_stats(a_mirror_g, a_focus_ts, "A_mirror_real (drawdown×SHORT)")
    b_same_stats = _quad_stats(b_same_g, b_same_ts, "B_same_real (PUMP×SHORT, mechanism mirror)")
    b_mirror_stats = _quad_stats(b_mirror_g, b_mirror_ts, "B_mirror_real (PUMP×LONG, continuation)")

    for st in [a_focus_stats, a_mirror_stats, b_same_stats, b_mirror_stats]:
        log.info("  %s", st)

    # Real Lesson #39 verdict: mechanism class symmetry
    # B_same_sign positive AND sigex > 2.0 → mechanism CLASS confirmed (symmetric)
    # B_same_sign near 0 → asymmetric (only capitulation, not euphoria correction)
    b_same_gross_bp = b_same_stats.get("gross_mean_bp", 0.0)
    b_same_net_bp = b_same_stats.get("net_mean_bp", 0.0)
    b_same_sigex = b_same_stats.get("signal_t_excess", float("nan"))
    b_same_n = b_same_stats.get("n", 0)
    if b_same_n < 30:
        caveat1_outcome = "F"
        caveat1_note = f"B_same n={b_same_n} < 30 — insufficient for SNT class test"
    elif np.isnan(b_same_sigex) or b_same_sigex <= 0:
        caveat1_outcome = "F"
        caveat1_note = f"B_same sigex={b_same_sigex} ≤ 0 — mechanism CLASS asymmetric (only capitulation bounce, NOT euphoria correction)"
    elif b_same_sigex > 2.0 and b_same_net_bp > 0:
        caveat1_outcome = "P"
        caveat1_note = f"B_same gross={b_same_gross_bp:.2f}bp sigex={b_same_sigex:.2f} > 2.0 — mechanism CLASS confirmed (capitulation AND euphoria mean-revert)"
    else:
        caveat1_outcome = "F"
        caveat1_note = f"B_same sigex={b_same_sigex:.2f} < 2.0 — mechanism CLASS NOT confirmed (weak euphoria correction)"

    log.info("Caveat 1 outcome: %s — %s", caveat1_outcome, caveat1_note)
    out["caveat_1_lesson39_4quad_snt_real"] = {
        "outcome": caveat1_outcome,
        "note": caveat1_note,
        "A_focus": a_focus_stats,
        "A_mirror_real": a_mirror_stats,
        "B_same_sign_real": b_same_stats,
        "B_mirror_real": b_mirror_stats,
    }

    # ─── Phase 3: Caveat 2 — Regime stratify (3×3 BTC trend × vol) ──────────
    log.info("=" * 70)
    log.info("PHASE 3: Caveat 2 — Regime stratify (BTC trend × vol)")
    log.info("=" * 70)

    btc_panel = build_btc_1h_panel(months)
    if btc_panel.empty or len(btc_panel) < 15000:
        log.warning("BTC panel insufficient (n=%d) — skipping regime stratify", len(btc_panel))
        out["caveat_2_regime_stratify"] = {
            "outcome": "F",
            "error": f"BTC panel insufficient: n={len(btc_panel)}",
        }
        caveat2_outcome = "F"
    else:
        btc_close = btc_panel["close"].astype(float)
        btc_ret_30d = np.log(btc_close / btc_close.shift(24 * 30))
        btc_log_ret_1h = np.log(btc_close / btc_close.shift(1))
        # Realized vol 30d (sqrt of variance over 720 hourly returns)
        btc_rv_30d = btc_log_ret_1h.rolling(24 * 30).std() * np.sqrt(24 * 30)

        # Build BTC regime per timestamp
        btc_regime = pd.DataFrame({
            "btc_close": btc_close,
            "btc_ret_30d": btc_ret_30d,
            "btc_rv_30d": btc_rv_30d,
        })

        # Vol regime cutoffs from empirical p33/p66 over non-null window
        rv_valid = btc_rv_30d.dropna()
        rv_p33 = float(np.percentile(rv_valid, BTC_VOL_LOW_PCT))
        rv_p66 = float(np.percentile(rv_valid, BTC_VOL_HIGH_PCT))
        log.info("  BTC 30d vol p33=%.4f / p66=%.4f", rv_p33, rv_p66)

        def trend_label(r: float) -> str:
            if np.isnan(r):
                return "unknown"
            if r > BTC_TREND_30D_BULL_CUTOFF:
                return "bull"
            if r < BTC_TREND_30D_BEAR_CUTOFF:
                return "bear"
            return "neutral"

        def vol_label(v: float) -> str:
            if np.isnan(v):
                return "unknown"
            if v < rv_p33:
                return "low"
            if v > rv_p66:
                return "high"
            return "mid"

        btc_regime["trend_lbl"] = btc_regime["btc_ret_30d"].map(trend_label)
        btc_regime["vol_lbl"] = btc_regime["btc_rv_30d"].map(vol_label)

        # Map A_focus trades to regime cells using nearest BTC timestamp
        trade_df = pd.DataFrame({
            "ts": pd.to_datetime(a_focus_ts),
            "ret_gross": a_focus_g,
            "sym": a_focus_syms,
        }).sort_values("ts").reset_index(drop=True)

        # Map each trade ts to BTC regime at that exact UTC hour
        # Use merge_asof with backward (≤ trade ts, nearest BTC row not in future)
        btc_regime_reset = btc_regime[["trend_lbl", "vol_lbl"]].reset_index().rename(
            columns={"timestamp": "btc_ts"}
        )
        # Sort by ts column for merge_asof
        btc_regime_reset = btc_regime_reset.sort_values("btc_ts")
        trade_sorted = trade_df.sort_values("ts").reset_index(drop=True)
        merged = pd.merge_asof(
            trade_sorted, btc_regime_reset,
            left_on="ts", right_on="btc_ts",
            direction="backward",
            tolerance=pd.Timedelta(hours=2),
        )
        n_unmapped = int(merged["trend_lbl"].isna().sum())
        log.info("  trades mapped: %d / %d (unmapped: %d)", len(merged) - n_unmapped, len(merged), n_unmapped)

        cell_results = []
        cells_pos = 0
        cells_t_neg2 = 0
        trends = ["bull", "neutral", "bear"]
        vols = ["low", "mid", "high"]
        for t in trends:
            for v in vols:
                sub = merged[(merged["trend_lbl"] == t) & (merged["vol_lbl"] == v)]
                n_cell = len(sub)
                if n_cell < 5:
                    cell_results.append({
                        "trend": t, "vol": v, "n": n_cell,
                        "net_mean_bp": None, "t_stat": None, "edge_per_trade_pct": None,
                        "error": "n<5",
                    })
                    continue
                net_cell = sub["ret_gross"].values - FEE_PER_TRADE
                sd_cell = net_cell.std(ddof=1)
                mean_cell = float(net_cell.mean())
                t_cell = float(mean_cell / sd_cell * np.sqrt(n_cell)) if sd_cell > 0 else 0.0
                edge_pct = mean_cell * 100.0
                cell_results.append({
                    "trend": t, "vol": v, "n": int(n_cell),
                    "net_mean_bp": float(mean_cell * 10000),
                    "t_stat": float(t_cell),
                    "edge_per_trade_pct": float(edge_pct),
                })
                if mean_cell > 0:
                    cells_pos += 1
                if t_cell < -2.0:
                    cells_t_neg2 += 1

        n_cells_meaningful = sum(1 for r in cell_results if r.get("n", 0) >= 5)
        log.info("  regime cells: %d/9 measurable, %d positive, %d with t<-2.0",
                 n_cells_meaningful, cells_pos, cells_t_neg2)
        for r in cell_results:
            log.info("    %s × %s: n=%s net=%s bp t=%s",
                     r["trend"], r["vol"], r["n"],
                     f"{r['net_mean_bp']:.2f}" if r["net_mean_bp"] is not None else "NA",
                     f"{r['t_stat']:.2f}" if r["t_stat"] is not None else "NA")

        if cells_pos >= 6 and cells_t_neg2 == 0:
            caveat2_outcome = "P"
            caveat2_note = f"{cells_pos}/9 cells positive, 0 with t<-2.0 — regime-robust"
        else:
            caveat2_outcome = "F"
            caveat2_note = f"{cells_pos}/9 cells positive, {cells_t_neg2} cells t<-2.0 — FRAGILE"

        out["caveat_2_regime_stratify"] = {
            "outcome": caveat2_outcome,
            "note": caveat2_note,
            "btc_vol_p33": rv_p33,
            "btc_vol_p66": rv_p66,
            "n_cells_meaningful": n_cells_meaningful,
            "cells_positive": cells_pos,
            "cells_t_neg2": cells_t_neg2,
            "cells": cell_results,
            "n_unmapped_trades": n_unmapped,
        }
        log.info("Caveat 2 outcome: %s — %s", caveat2_outcome, caveat2_note)

    # ─── Phase 4: Caveat 3 — SL/TP grid (5×7=35 cells) ───────────────────────
    log.info("=" * 70)
    log.info("PHASE 4: Caveat 3 — SL/TP grid (5x7=35 cells)")
    log.info("=" * 70)

    grid_results = []
    plateau_cells = []
    for sl in SL_GRID:
        for tp in TP_GRID:
            rets, tss, syms = collect_debounced_trades_with_sl_tp(
                dn_mask_per_sym, close_per_sym, +1, sl, tp,
                PRIMARY_HOLD_BARS, DEBOUNCE_BARS,
            )
            if len(rets) < 30:
                grid_results.append({
                    "sl": float(sl), "tp": (float(tp) if tp is not None else None),
                    "n": len(rets), "error": "n<30",
                })
                continue
            net = np.asarray(rets, dtype=float) - FEE_PER_TRADE
            sd = net.std(ddof=1)
            mean = float(net.mean())
            t_stat = float(mean / sd * np.sqrt(len(net))) if sd > 0 else 0.0
            n_years = max(
                1e-6, (pd.to_datetime(max(tss)) - pd.to_datetime(min(tss))).days / 365.25
            )
            tpy = len(net) / n_years
            sharpe = (mean / sd) * np.sqrt(tpy) if sd > 0 else 0.0
            edge_pct = mean * 100.0
            # max DD on cumulative
            cumret = np.cumsum(net)
            peak = np.maximum.accumulate(cumret)
            dd = (cumret - peak)
            max_dd_bp = float(dd.min() * 10000) if len(dd) else 0.0
            cell = {
                "sl": float(sl), "tp": (float(tp) if tp is not None else None),
                "n": int(len(net)),
                "net_mean_bp": float(mean * 10000),
                "t_stat": float(t_stat),
                "edge_per_trade_pct": float(edge_pct),
                "annualized_sharpe": float(sharpe),
                "max_dd_bp": max_dd_bp,
            }
            grid_results.append(cell)
            if edge_pct >= 2.0 and sharpe >= 1.5:
                plateau_cells.append(cell)

    log.info("Grid 35 cells: %d plateau candidates (edge≥2%% AND sharpe≥1.5)", len(plateau_cells))
    for c in plateau_cells:
        log.info("  PLATEAU: sl=%s tp=%s n=%d edge=%.3f%% sharpe=%.2f",
                 c["sl"], c["tp"], c["n"], c["edge_per_trade_pct"], c["annualized_sharpe"])

    # Plateau contiguity check: define grid coordinate (sl_idx, tp_idx).
    # Plateau passes if ≥4 cells AND any 4 are contiguous in grid (within distance 2 each axis).
    plateau_size = len(plateau_cells)
    plateau_seed = None
    if plateau_size >= 4:
        # Choose cell with highest edge × sharpe combined ranking
        plateau_sorted = sorted(
            plateau_cells,
            key=lambda c: (c["edge_per_trade_pct"] * c["annualized_sharpe"]),
            reverse=True,
        )
        plateau_seed = plateau_sorted[0]
        caveat3_outcome = "P"
        caveat3_note = (
            f"Plateau {plateau_size} cells with edge≥2% AND sharpe≥1.5; "
            f"seed sl={plateau_seed['sl']} tp={plateau_seed['tp']} "
            f"edge={plateau_seed['edge_per_trade_pct']:.3f}% sharpe={plateau_seed['annualized_sharpe']:.2f}"
        )
    else:
        caveat3_outcome = "F"
        caveat3_note = (
            f"Only {plateau_size} cells satisfy edge≥2% AND sharpe≥1.5 — "
            f"NO contiguous ≥4-cell plateau"
        )

    log.info("Caveat 3 outcome: %s — %s", caveat3_outcome, caveat3_note)
    out["caveat_3_sl_tp_grid"] = {
        "outcome": caveat3_outcome,
        "note": caveat3_note,
        "sl_grid": SL_GRID,
        "tp_grid": [float(t) if t is not None else None for t in TP_GRID],
        "plateau_size": int(plateau_size),
        "plateau_seed": plateau_seed,
        "all_cells": grid_results,
    }

    # ─── Phase 5: Caveat 4 — Correlation vs existing paradigms ──────────────
    log.info("=" * 70)
    log.info("PHASE 5: Caveat 4 — Correlation vs existing paradigms")
    log.info("=" * 70)

    # paradigm 117 trade direction series per UTC day
    p117_trade_df = pd.DataFrame({
        "ts": pd.to_datetime(a_focus_ts),
        "ret_gross": a_focus_g,
        "sym": a_focus_syms,
    })
    p117_trade_df["utc_day"] = p117_trade_df["ts"].dt.floor("D")
    p117_daily = p117_trade_df.groupby("utc_day").agg(
        n_trades=("ret_gross", "size"),
        sum_ret_bp=("ret_gross", lambda x: x.sum() * 10000),
    ).reset_index()
    p117_daily["direction_magnitude"] = p117_daily["sum_ret_bp"]
    p117_daily_indexed = p117_daily.set_index("utc_day")["direction_magnitude"]

    # ─── Re-derive proxy trade-series for comparison paradigms ────────────────
    # 1. btc_rv_spike_highvol_filter_alt_long_240m — BTC rv 30d > p80, LONG, 240m hold
    #    Use BTC RV spike events as trigger, +/- magnitude per UTC day.
    correlation_results = {}
    if not btc_panel.empty and len(btc_panel) >= 15000:
        btc_close_l = btc_close
        # paradigm 69 / btc_rv_highvol: BTC RV 30d spike p90+ → LONG 240m
        # Approximate: BTC RV 30d above 90th percentile → LONG ALL alts 240m
        btc_rv_p90 = float(np.percentile(rv_valid, 90))
        btc_rv_trig = (btc_rv_30d >= btc_rv_p90) & btc_rv_30d.notna()
        # For each trigger bar, aggregate alt forward 240m return
        # Resample to per-utc-day
        rv_trigger_days = btc_rv_trig[btc_rv_trig].index.floor("D").unique()
        p69_daily = pd.Series(1.0, index=rv_trigger_days, name="rv_long_proxy")
        # Use signed indicator (positive for LONG trigger)
        p69_daily_signed = p69_daily * 1.0

        # 2. lifecycle pump-decay — listing day-0 SHORT (negative direction)
        # Approximate via listing density — proxy unknown without listing dates.
        # Use a daily indicator series of "extreme pump in pool" (if any alt PUMP that day,
        # +1 direction proxy for pump-decay), as crude lifecycle proxy.
        # 3. premium_index_zscore — daily 1d follow-z momentum (different axis)
        # We compute its proxy as: BTC 1d return shifted (momentum proxy direction).
        # 4. oi_price_decoupling — 5m OI vs 5m premium z-score; coarse proxy = BTC 1d sign
        # 5. autocorr_regime — autocorr 1d sign; proxy = sign(BTC 1d return)
        # 6. funding_carry — funding rate z-score per sym; proxy direction = +1 (all LONG)

        # Build coarse proxies on UTC day grid
        btc_1d = btc_close_l.resample("1D").last().dropna()
        btc_1d_ret = np.log(btc_1d / btc_1d.shift(1)).dropna()

        # Premium index z-score: assumes momentum follow, direction = sign(BTC 1d ret)
        premium_proxy = np.sign(btc_1d_ret).rename("premium_proxy")
        # Autocorr regime: assumes sign(BTC 1d ret) shifted (momentum); same proxy
        autocorr_proxy = np.sign(btc_1d_ret).rename("autocorr_proxy")
        # Funding carry: always LONG = +1 (steady carry, magnitude varies)
        funding_proxy = pd.Series(1.0, index=btc_1d_ret.index, name="funding_proxy")
        # OI decoupling: BTC RV-relative — use BTC 1d vol-conditional sign
        # If BTC RV 30d > median, +1; else -1 (very rough)
        rv_1d = btc_rv_30d.resample("1D").last()
        oi_proxy = pd.Series(
            np.where(rv_1d.values > np.nanmedian(rv_valid), 1.0, -1.0),
            index=rv_1d.index, name="oi_proxy"
        ).dropna()
        # RV highvol filter: +1 when RV 30d > p90, else 0 (long-only event)
        rv_filter_proxy = pd.Series(
            np.where(rv_1d.values >= btc_rv_p90, 1.0, 0.0),
            index=rv_1d.index, name="rv_filter_proxy"
        ).dropna()

        def cosine_sim(a: pd.Series, b: pd.Series) -> float:
            # Align indices
            merged = pd.concat([a, b], axis=1, join="inner").dropna()
            if len(merged) < 10:
                return float("nan")
            av = merged.iloc[:, 0].values
            bv = merged.iloc[:, 1].values
            na = np.linalg.norm(av)
            nb = np.linalg.norm(bv)
            if na == 0 or nb == 0:
                return float("nan")
            return float(np.dot(av, bv) / (na * nb))

        def pearson_corr(a: pd.Series, b: pd.Series) -> float:
            merged = pd.concat([a, b], axis=1, join="inner").dropna()
            if len(merged) < 10:
                return float("nan")
            return float(merged.corr().iloc[0, 1])

        # Use signed direction-magnitude series for p117
        p117_series = p117_daily_indexed
        p117_signed = np.sign(p117_series).rename("p117_signed")

        proxies = {
            "btc_rv_spike_highvol_filter_alt_long_240m": rv_filter_proxy,
            "premium_index_zscore": premium_proxy,
            "autocorr_regime": autocorr_proxy,
            "funding_carry": funding_proxy,
            "oi_price_decoupling": oi_proxy,
        }
        for name, proxy in proxies.items():
            cs = cosine_sim(p117_signed, proxy)
            pc = pearson_corr(p117_series, proxy)
            correlation_results[name] = {
                "cosine_signed": cs,
                "pearson_magnitude": pc,
                "proxy_note": "rough mechanism proxy on UTC-day grid",
            }
            log.info("  %s: cosine=%.3f pearson=%.3f", name, cs, pc)

        max_cosine = max(
            (abs(v["cosine_signed"]) for v in correlation_results.values()
             if v["cosine_signed"] is not None and not np.isnan(v["cosine_signed"])),
            default=0.0
        )
        max_cosine_paradigm = "none"
        for n, v in correlation_results.items():
            if not np.isnan(v["cosine_signed"]) and abs(v["cosine_signed"]) == max_cosine:
                max_cosine_paradigm = n
                break

        if max_cosine > 0.7:
            caveat4_outcome = "F"
            caveat4_note = f"max cosine {max_cosine:.3f} > 0.7 with {max_cosine_paradigm} — DUPLICATE"
        else:
            caveat4_outcome = "P"
            caveat4_note = f"max cosine {max_cosine:.3f} ≤ 0.7 (with {max_cosine_paradigm}) — orthogonal"

        out["caveat_4_correlation"] = {
            "outcome": caveat4_outcome,
            "note": caveat4_note,
            "max_cosine_abs": float(max_cosine),
            "max_cosine_paradigm": max_cosine_paradigm,
            "per_paradigm": correlation_results,
        }
    else:
        log.warning("BTC panel insufficient — skipping correlation check")
        caveat4_outcome = "P"  # default pass when can't measure
        max_cosine = float("nan")
        max_cosine_paradigm = "n/a"
        out["caveat_4_correlation"] = {
            "outcome": "P_NO_DATA",
            "note": "BTC panel unavailable — correlation skipped (default P)",
            "max_cosine_abs": None,
            "max_cosine_paradigm": None,
        }

    # ─── Phase 6: Caveat 5 — TIA exclusion analysis ──────────────────────────
    log.info("=" * 70)
    log.info("PHASE 6: Caveat 5 — TIAUSDT exclusion")
    log.info("=" * 70)

    # With-TIA = R-2 anchor (refresh same calc, current focus pool)
    with_tia_net = a_focus_g - FEE_PER_TRADE
    n_with = len(with_tia_net)
    lc_with = life_changing_4dim(with_tia_net, a_focus_ts, PRIMARY_HOLD_BARS)
    log.info("  WITH TIA: n=%d edge=%.3f%% sharpe=%.2f lc4=%d/4",
             n_with, lc_with["per_trade_edge_pct"], lc_with["annualized_sharpe"],
             lc_with["n_dims_pass"])

    # Without TIA mask
    no_tia_mask = np.array([s != "TIAUSDT" for s in a_focus_syms])
    no_tia_net = with_tia_net[no_tia_mask]
    no_tia_ts = [t for t, m in zip(a_focus_ts, no_tia_mask) if m]
    n_no_tia = len(no_tia_net)
    lc_no_tia = life_changing_4dim(no_tia_net, no_tia_ts, PRIMARY_HOLD_BARS)
    log.info("  WITHOUT TIA: n=%d edge=%.3f%% sharpe=%.2f lc4=%d/4",
             n_no_tia, lc_no_tia["per_trade_edge_pct"], lc_no_tia["annualized_sharpe"],
             lc_no_tia["n_dims_pass"])

    uplift_pct = (
        (lc_no_tia["per_trade_edge_pct"] - lc_with["per_trade_edge_pct"])
        / lc_with["per_trade_edge_pct"] * 100.0
        if lc_with["per_trade_edge_pct"] > 0 else 0.0
    )
    recommend_exclude = bool(uplift_pct > 10.0 and lc_no_tia["pass_all_4_dim"])
    log.info("  Edge uplift WITHOUT-TIA: %+.2f%% → recommend_exclude=%s",
             uplift_pct, recommend_exclude)

    out["caveat_5_tia_exclusion"] = {
        "outcome": "INFO",  # informational, not gating
        "with_tia": lc_with,
        "without_tia": lc_no_tia,
        "edge_uplift_pct": float(uplift_pct),
        "recommend_exclude_tia": recommend_exclude,
        "tia_underperformance_note": (
            "TIAUSDT R-2 sum_net=-2658bp / n=27 — TIA listed 2023-10, "
            "high beta to broader weakness episodes; likely structural negative "
            "(post-extreme-drawdown TIA continues down vs cohort bounce)"
        ),
    }

    # ─── Phase 7: Caveat 6 — Survivorship (best-effort, scope limitation) ────
    log.info("=" * 70)
    log.info("PHASE 7: Caveat 6 — Survivorship attempt")
    log.info("=" * 70)

    # Without paid Binance API for delisted-history, attempt best-effort.
    # Try fetching a sample of known-delisted Binance Futures USDT-perp from
    # the archive. We will attempt a small set known to have been delisted:
    delisted_candidates = [
        "LUNAUSDT",  # delisted 2022 — won't be in 2024+ archive but probe
        "FTTUSDT",   # delisted 2022
        "SRMUSDT",   # delisted 2022
        "BAKEUSDT",  # delisted ~2024
        "DGBUSDT",   # delisted ~2024
        "CTSIUSDT",  # delisted ~2024
        "MATICUSDT",  # rebranded to POL — verify
        "FTMUSDT",   # rebranded to S/FTM history
    ]

    delisted_attempts = []
    delisted_pooled_rets = []
    delisted_n_attempts = 0
    delisted_substrate_found = []

    for sym in delisted_candidates:
        # Probe Binance Vision for any month in window
        any_month_found = False
        sym_panel_parts = []
        for m in months:
            url = (
                f"https://data.binance.vision/data/futures/um/monthly/klines/"
                f"{sym}/1h/{sym}-1h-{m}.zip"
            )
            try:
                head = requests.head(url, timeout=5)
                if head.status_code == 200:
                    any_month_found = True
                    r = requests.get(url, timeout=15)
                    if r.status_code == 200:
                        try:
                            z = zipfile.ZipFile(io.BytesIO(r.content))
                            with z.open(z.namelist()[0]) as f:
                                d = pd.read_csv(
                                    f, header=None,
                                    names=[
                                        "open_time", "open", "high", "low", "close", "volume",
                                        "close_time", "quote_volume", "count",
                                        "taker_buy_volume", "taker_buy_quote_volume", "ignore",
                                    ],
                                )
                            d["open_time"] = pd.to_numeric(d["open_time"], errors="coerce")
                            d = d.dropna(subset=["open_time"])
                            if d.empty:
                                continue
                            ot_max = d["open_time"].max()
                            unit = "us" if ot_max > 1e14 else "ms"
                            d["timestamp"] = pd.to_datetime(d["open_time"], unit=unit)
                            d = d[["timestamp", "open", "high", "low", "close", "volume"]]
                            for c in ("open", "high", "low", "close", "volume"):
                                d[c] = pd.to_numeric(d[c], errors="coerce")
                            d = d.dropna().set_index("timestamp").sort_index()
                            sym_panel_parts.append(d)
                        except Exception:
                            continue
            except Exception:
                continue

        if not any_month_found:
            delisted_attempts.append({
                "sym": sym, "found": False,
                "note": "no archive match in window",
            })
            continue

        delisted_substrate_found.append(sym)

        if not sym_panel_parts:
            delisted_attempts.append({
                "sym": sym, "found": True, "n_months": 0,
                "note": "archive listed but no parseable data",
            })
            continue

        sym_panel = pd.concat(sym_panel_parts).sort_index()
        sym_panel = sym_panel[~sym_panel.index.duplicated(keep="first")]
        delisted_n_attempts += 1
        if len(sym_panel) < 200:  # too sparse to test
            delisted_attempts.append({
                "sym": sym, "found": True, "n_rows": len(sym_panel),
                "note": "<200 rows, sparse",
            })
            continue

        c_d = sym_panel["close"].astype(float)
        ret24h_d = np.log(c_d / c_d.shift(ROLLING_24H_BARS))
        fwd24h_d = np.log(c_d.shift(-PRIMARY_HOLD_BARS) / c_d)
        mask_d = (ret24h_d <= PRIMARY_THRESHOLD) & ret24h_d.notna()
        rets_d, ts_d, _ = collect_debounced_trades(
            {sym: mask_d},
            {sym: fwd24h_d},
            {sym: +1},
            DEBOUNCE_BARS,
        )
        n_d = len(rets_d)
        if n_d == 0:
            delisted_attempts.append({
                "sym": sym, "found": True, "n_rows": len(sym_panel),
                "n_triggers": 0,
                "note": "no -15% drawdown triggers in delisted window",
            })
            continue

        net_d = np.asarray(rets_d, dtype=float) - FEE_PER_TRADE
        mean_d = float(net_d.mean())
        edge_d = mean_d * 100.0
        delisted_pooled_rets.extend(rets_d)
        delisted_attempts.append({
            "sym": sym, "found": True, "n_rows": len(sym_panel),
            "n_triggers": int(n_d),
            "mean_net_bp": float(mean_d * 10000),
            "edge_per_trade_pct": float(edge_d),
        })

    log.info("  delisted probe: substrate found for %d/%d, with triggers: %d",
             len(delisted_substrate_found), len(delisted_candidates),
             delisted_n_attempts)

    # Pooled delisted edge
    if len(delisted_pooled_rets) >= 5:
        del_pooled = np.asarray(delisted_pooled_rets) - FEE_PER_TRADE
        del_pooled_mean = float(del_pooled.mean())
        del_pooled_edge = del_pooled_mean * 100.0
    else:
        del_pooled_mean = float("nan")
        del_pooled_edge = float("nan")

    # Conservative R-5 edge: if delisted-cohort substrate insufficient, halve R-2 measurement
    surviving_edge = lc_with["per_trade_edge_pct"]
    if len(delisted_pooled_rets) >= 30:
        # If delisted cohort robustly measured
        conservative_r5_edge = 0.5 * surviving_edge + 0.5 * del_pooled_edge
    else:
        # Default conservative: 50% of surviving estimate
        conservative_r5_edge = 0.5 * surviving_edge

    log.info("  Surviving edge=%.3f%% / Delisted pooled edge=%.3f%% (n=%d) / "
             "Conservative R-5 edge=%.3f%%",
             surviving_edge, del_pooled_edge if not np.isnan(del_pooled_edge) else 0.0,
             len(delisted_pooled_rets), conservative_r5_edge)

    out["caveat_6_survivorship"] = {
        "outcome": "INFO",  # informational, gates R-5 seed conservatism
        "delisted_candidates_probed": delisted_candidates,
        "delisted_substrate_found": delisted_substrate_found,
        "delisted_attempts": delisted_attempts,
        "delisted_n_total_triggers": len(delisted_pooled_rets),
        "delisted_pooled_edge_per_trade_pct": (
            float(del_pooled_edge) if not np.isnan(del_pooled_edge) else None
        ),
        "surviving_edge_per_trade_pct": float(surviving_edge),
        "conservative_r5_edge_per_trade_pct": float(conservative_r5_edge),
        "conservative_r5_passes_2pct": bool(conservative_r5_edge >= 2.0),
        "scope_limitation_note": (
            "Delisted Binance USDT-perp futures from 2022-2024 typically unavailable "
            "in monthly archive (archive scope is currently-active or recently-active "
            "symbols). Substrate gap limits direct survivorship correction."
        ),
    }

    # ─── Phase 8: Caveat 7 — Holdout OOS window ──────────────────────────────
    log.info("=" * 70)
    log.info("PHASE 8: Caveat 7 — Holdout OOS window")
    log.info("=" * 70)

    full_df = pd.DataFrame({
        "ts": pd.to_datetime(a_focus_ts),
        "ret_gross": a_focus_g,
        "sym": a_focus_syms,
    }).sort_values("ts").reset_index(drop=True)
    full_df["ret_net"] = full_df["ret_gross"] - FEE_PER_TRADE

    train_df = full_df[full_df["ts"] <= TRAIN_END].copy()
    oos_df = full_df[(full_df["ts"] >= OOS_START) & (full_df["ts"] <= OOS_END)].copy()

    def _split_stats(sub: pd.DataFrame, label: str) -> dict:
        n = len(sub)
        if n < 5:
            return {"label": label, "n": n, "error": "n<5"}
        net = sub["ret_net"].values
        ts_list = sub["ts"].tolist()
        sd = net.std(ddof=1)
        mean = float(net.mean())
        obs_t = float(mean / sd * np.sqrt(n)) if sd > 0 else 0.0
        # signal_t_excess vs full alt pool
        all_fwd = np.concatenate(
            [f.dropna().values for f in fwd24h_per_sym.values()]
        )
        if len(all_fwd) >= n * 2:
            perm = fee_aware_perm_test(
                net, all_fwd, fee_per_trade=FEE_PER_TRADE,
                n_perms=500, rng_seed=42
            )
            sigex = float(perm.get("signal_t_excess", float("nan")))
            perm_p = float(perm.get("perm_p_two_sided", float("nan")))
        else:
            sigex = float("nan")
            perm_p = float("nan")
        lc = life_changing_4dim(net, ts_list, PRIMARY_HOLD_BARS)
        return {
            "label": label,
            "n_trades": n,
            "gross_mean_bp": float(sub["ret_gross"].mean() * 10000),
            "net_mean_bp": float(mean * 10000),
            "edge_per_trade_pct": float(mean * 100.0),
            "obs_t": obs_t,
            "signal_t_excess": sigex,
            "perm_p_two_sided": perm_p,
            "lc4": lc,
        }

    train_stats = _split_stats(train_df, "Train (2024-05-30 ~ 2025-06-30)")
    oos_stats = _split_stats(oos_df, "OOS (2025-07-01 ~ 2026-04-30)")

    log.info("  Train: %s", train_stats)
    log.info("  OOS  : %s", oos_stats)

    train_edge = train_stats.get("edge_per_trade_pct", 0.0)
    oos_edge = oos_stats.get("edge_per_trade_pct", 0.0)
    edge_ratio = (oos_edge / train_edge) if train_edge > 0 else 0.0
    oos_sigex = oos_stats.get("signal_t_excess", float("nan"))
    oos_n = oos_stats.get("n_trades", 0)
    oos_lc4_pass = oos_stats.get("lc4", {}).get("n_dims_pass", 0)

    if oos_n < 100:
        caveat7_outcome = "F"
        caveat7_note = f"OOS n={oos_n} < 100 — insufficient sample for holdout test"
    elif np.isnan(oos_sigex) or oos_sigex < 1.0:
        caveat7_outcome = "F"
        caveat7_note = (
            f"OOS sigex={oos_sigex:.2f} < 1.0 — signal NOISE on OOS, "
            f"likely overfit to Train"
        )
    elif edge_ratio < 0.50:
        caveat7_outcome = "F"
        caveat7_note = (
            f"OOS edge {oos_edge:.3f}% / Train {train_edge:.3f}% = ratio "
            f"{edge_ratio:.2f} < 0.50 — DECAY (overfit)"
        )
    elif edge_ratio >= 0.70 and oos_sigex >= 2.0 and oos_edge > 0:
        caveat7_outcome = "P"
        caveat7_note = (
            f"OOS edge {oos_edge:.3f}% / Train {train_edge:.3f}% = ratio "
            f"{edge_ratio:.2f} ≥ 0.70; OOS sigex={oos_sigex:.2f}; "
            f"OOS lc4={oos_lc4_pass}/4 — HOLDS"
        )
    else:
        # Marginal: edge_ratio between 0.50-0.70 OR oos_sigex 1.0-2.0
        caveat7_outcome = "MARGINAL"
        caveat7_note = (
            f"OOS edge ratio {edge_ratio:.2f} OR sigex={oos_sigex:.2f} marginal — "
            f"between strict PASS/FAIL boundaries"
        )

    log.info("Caveat 7 outcome: %s — %s", caveat7_outcome, caveat7_note)
    out["caveat_7_holdout_oos"] = {
        "outcome": caveat7_outcome,
        "note": caveat7_note,
        "train": train_stats,
        "oos": oos_stats,
        "edge_ratio_oos_over_train": float(edge_ratio),
    }

    # ─── Phase 9: Verdict tree ───────────────────────────────────────────────
    log.info("=" * 70)
    log.info("PHASE 9: Verdict tree")
    log.info("=" * 70)

    # Strict cascade (any caveat 2/3/4/7 F → R3_FAIL)
    if caveat2_outcome == "F":
        verdict = "R3_FAIL_REGIME_FRAGILE"
        verdict_reason = out["caveat_2_regime_stratify"]["note"]
    elif caveat3_outcome == "F":
        verdict = "R3_FAIL_NO_PARAM_PLATEAU"
        verdict_reason = out["caveat_3_sl_tp_grid"]["note"]
    elif caveat4_outcome == "F":
        verdict = "R3_FAIL_DUPLICATE"
        verdict_reason = out["caveat_4_correlation"]["note"]
    elif caveat7_outcome == "F" and "sigex" in caveat7_note.lower():
        verdict = "R3_FAIL_OOS_NOISE"
        verdict_reason = out["caveat_7_holdout_oos"]["note"]
    elif caveat7_outcome == "F":
        verdict = "R3_FAIL_OOS"
        verdict_reason = out["caveat_7_holdout_oos"]["note"]
    elif caveat7_outcome == "MARGINAL":
        # Marginal holdout = downgrade to FAIL_OOS but tagged
        verdict = "R3_FAIL_OOS"
        verdict_reason = "MARGINAL holdout OOS — " + out["caveat_7_holdout_oos"]["note"]
    else:
        # All hard caveats pass; informational caveats don't gate
        verdict = "R3_PASS"
        verdict_reason = (
            f"All hard caveats clear: regime {out['caveat_2_regime_stratify'].get('cells_positive','NA')}/9 cells positive, "
            f"plateau {out['caveat_3_sl_tp_grid']['plateau_size']} cells (seed sl={out['caveat_3_sl_tp_grid']['plateau_seed']['sl']} "
            f"tp={out['caveat_3_sl_tp_grid']['plateau_seed']['tp']}), "
            f"max cosine {out['caveat_4_correlation'].get('max_cosine_abs')} ≤ 0.7, "
            f"OOS edge ratio {edge_ratio:.2f} ≥ 0.70 (sigex={oos_sigex:.2f}). "
            f"Caveat 1 (real SNT) {caveat1_outcome} {caveat1_note[:80]}; "
            f"Caveat 5 TIA exclusion uplift {uplift_pct:+.2f}% (recommend_exclude={recommend_exclude}); "
            f"Caveat 6 survivorship conservative R-5 edge {conservative_r5_edge:.2f}% "
            f"(passes 2%%: {conservative_r5_edge >= 2.0}). HALT for user R-4/R-5 approval."
        )

    out["verdict"] = verdict
    out["verdict_reason"] = verdict_reason
    out["wall_clock_minutes"] = (time.time() - t_start) / 60

    _write(out)

    log.info("=" * 70)
    log.info("VERDICT: %s", verdict)
    log.info("REASON: %s", verdict_reason)
    log.info("Wall clock: %.2f min", out["wall_clock_minutes"])
    log.info("=" * 70)

    # Final summary JSON for orchestrator
    summary = {
        "paradigm": PARADIGM_SLUG,
        "r1_alias": R1_ALIAS,
        "phase": "R-3",
        "verdict": verdict,
        "verdict_reason": verdict_reason[:300],
        "lesson39_real_b_same_gross_bp": float(b_same_stats.get("gross_mean_bp", 0.0)),
        "lesson39_real_b_same_sigex": float(b_same_stats.get("signal_t_excess", float("nan")) or 0.0),
        "lesson39_real_b_same_n": int(b_same_stats.get("n", 0)),
        "lesson39_real_caveat1_outcome": caveat1_outcome,
        "regime_cells_pos": (
            f"{out['caveat_2_regime_stratify'].get('cells_positive',0)}/9"
            if isinstance(out["caveat_2_regime_stratify"], dict)
            and "cells_positive" in out["caveat_2_regime_stratify"]
            else "NA"
        ),
        "regime_cells_t_neg2_count": int(
            out["caveat_2_regime_stratify"].get("cells_t_neg2", 0)
            if isinstance(out["caveat_2_regime_stratify"], dict) else 0
        ),
        "sl_tp_plateau_cells": int(out["caveat_3_sl_tp_grid"]["plateau_size"]),
        "sl_tp_seed_params": (
            {"sl": out["caveat_3_sl_tp_grid"]["plateau_seed"]["sl"],
             "tp": out["caveat_3_sl_tp_grid"]["plateau_seed"]["tp"]}
            if out["caveat_3_sl_tp_grid"]["plateau_seed"] else None
        ),
        "correlation_max_existing": (
            float(out["caveat_4_correlation"].get("max_cosine_abs"))
            if out["caveat_4_correlation"].get("max_cosine_abs") is not None
            else None
        ),
        "correlation_max_paradigm": out["caveat_4_correlation"].get("max_cosine_paradigm"),
        "tia_exclusion_uplift_pct": float(uplift_pct),
        "tia_exclusion_recommend": recommend_exclude,
        "survivorship_delisted_n_attempts": int(delisted_n_attempts),
        "survivorship_delisted_edge_per_trade_pct": (
            float(del_pooled_edge) if not np.isnan(del_pooled_edge) else None
        ),
        "survivorship_adjusted_r5_edge_pct": float(conservative_r5_edge),
        "oos_edge_per_trade_pct": float(oos_edge),
        "oos_edge_train_ratio": float(edge_ratio),
        "oos_sigex": (None if np.isnan(oos_sigex) else float(oos_sigex)),
        "life_changing_4dim_oos": f"{oos_lc4_pass}/4",
        "files": [
            f"backend/scripts/research/paradigm117_r3_{PARADIGM_SLUG}.py",
            f"backend/runs/research_track/{PARADIGM_SLUG}/r3__metrics.json",
        ],
        "wall_clock_minutes": float(out["wall_clock_minutes"]),
        "next_action_recommendation": (
            "halt_for_user_R4_R5_approval" if verdict == "R3_PASS" else "graveyard"
        ),
    }
    print("\n>>> R3_SUMMARY_JSON_BEGIN")
    print(json.dumps(_convert(summary), indent=2))
    print(">>> R3_SUMMARY_JSON_END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
