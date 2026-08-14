"""Paradigm #248 R-1 PoC — BTC on-chain AdrActCnt regime → alt bilateral 24h.

BUGFIX v2 (2026-08-08): the previous version used `resample('1D').last()` which
places daily bars at midnight but with 23:59 close values. This caused an
inadvertent look-ahead: `pct_change()[D]` represented a return ENDING at D 23:59
UTC, which is FUTURE from the presumed entry time D 00:00 UTC.

Corrected data pipeline:
- Use 1m OPEN at 00:00 UTC of each day as the "trigger-time" price.
- `btc_ret_prior_day` at index D = (btc_00_D - btc_00_D-1) / btc_00_D-1
  = the return from D-1 00:00 UTC to D 00:00 UTC, KNOWN at D 00:00.
- Trade entry: alt_00_D. Exit: alt_00_{D+hold_days}.
- Regime pct30 uses AdrActCnt SHIFTED (yesterday's AAC is knowable at today 00:00).

4-quadrant Symmetric Negative Test (Lesson #19) unchanged in structure.
"""
from __future__ import annotations

import json
import logging
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p248_r1")

PARADIGM = "btc_onchain_active_address_regime_alt_bilateral_24h"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)

POC_ALTS = ["SOLUSDT", "DOGEUSDT", "ETHUSDT"]

FEE_ONE_SIDE = 0.0004
FEE_RT = 2 * FEE_ONE_SIDE

CM_URL_TMPL = (
    "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    "?assets=btc&metrics=AdrActCnt&frequency=1d"
    "&start_time={start}&end_time={end}&page_size=10000"
)


def fetch_adr_act_cnt() -> pd.Series:
    end_iso = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    url = CM_URL_TMPL.format(start="2023-06-01T00:00:00Z", end=end_iso)
    log.info("Fetching CoinMetrics AdrActCnt")
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read())
    rows = data.get("data", [])
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_localize(None).dt.normalize()
    df["AdrActCnt"] = pd.to_numeric(df["AdrActCnt"], errors="coerce")
    return df.set_index("time")["AdrActCnt"].sort_index()


def load_open_at_midnight(sym: str) -> pd.Series:
    """Return series of 1m OPEN price at 00:00 UTC each day, indexed by that day's midnight."""
    df = load_ohlcv_1m_cached(sym)
    if df.empty:
        return pd.Series(dtype=float)
    idx = df.index
    if idx.tz is not None:
        df.index = idx.tz_convert(None)
    at_midnight = df.loc[df.index.time == pd.Timestamp("00:00").time(), "open"]
    at_midnight.index = at_midnight.index.normalize()
    at_midnight = at_midnight[~at_midnight.index.duplicated(keep="first")]
    return at_midnight.sort_index()


def load_open_hourly(sym: str) -> pd.Series:
    """Return 1m OPEN price at each hour boundary (:00 minute), for intraday hold windows."""
    df = load_ohlcv_1m_cached(sym)
    if df.empty:
        return pd.Series(dtype=float)
    idx = df.index
    if idx.tz is not None:
        df.index = idx.tz_convert(None)
    hourly = df.loc[df.index.minute == 0, "open"]
    hourly = hourly[~hourly.index.duplicated(keep="first")]
    return hourly.sort_index()


def pct_rank_30d(s: pd.Series) -> pd.Series:
    return s.rolling(30, min_periods=20).apply(
        lambda w: (w < w.iloc[-1]).sum() / (len(w) - 1) if len(w) > 1 else np.nan,
        raw=False,
    )


def build_trades(
    regime_series: pd.Series,          # pct30_lag1 indexed by day at midnight
    btc_sign_series: pd.Series,        # sign of BTC (D-1 00:00 → D 00:00) return, indexed by day
    alt_hourly_open: pd.Series,        # alt 1m OPEN at each hour boundary
    lo: float, hi: float,
    hold_hours: int,
    quadrant: str,
) -> pd.DataFrame:
    q_dir_focus = quadrant.endswith("focus")

    if quadrant.startswith("A"):
        regime_mask = regime_series > hi
        btc_sign_ok = btc_sign_series > 0
        direction = +1 if q_dir_focus else -1
    elif quadrant.startswith("B"):
        regime_mask = regime_series > hi
        btc_sign_ok = btc_sign_series < 0
        direction = -1 if q_dir_focus else +1
    elif quadrant.startswith("C"):
        regime_mask = regime_series < lo
        btc_sign_ok = btc_sign_series > 0
        direction = +1 if q_dir_focus else -1
    else:  # D
        regime_mask = regime_series < lo
        btc_sign_ok = btc_sign_series < 0
        direction = -1 if q_dir_focus else +1

    entries = regime_series.index[(regime_mask & btc_sign_ok).fillna(False)]
    if len(entries) == 0:
        return pd.DataFrame()

    trades = []
    last_exit_ts = None
    for entry_ts in entries:
        if last_exit_ts is not None and entry_ts < last_exit_ts:
            continue
        e_ts = entry_ts
        x_ts = entry_ts + pd.Timedelta(hours=hold_hours)
        e_idx = alt_hourly_open.index.get_indexer([e_ts], method="nearest", tolerance=pd.Timedelta("30min"))
        x_idx = alt_hourly_open.index.get_indexer([x_ts], method="nearest", tolerance=pd.Timedelta("30min"))
        if e_idx[0] == -1 or x_idx[0] == -1:
            continue
        ep = alt_hourly_open.iloc[e_idx[0]]
        xp = alt_hourly_open.iloc[x_idx[0]]
        if pd.isna(ep) or pd.isna(xp) or ep <= 0:
            continue
        raw_ret = (xp / ep - 1.0) * direction
        net_ret = raw_ret - FEE_RT
        trades.append({
            "entry_ts": entry_ts,
            "exit_ts": x_ts,
            "raw_ret": raw_ret,
            "net_ret": net_ret,
        })
        last_exit_ts = x_ts
    return pd.DataFrame(trades)


def evaluate_cell(trades_df: pd.DataFrame) -> dict:
    if trades_df.empty or len(trades_df) < 5:
        return {"n": int(len(trades_df)), "insufficient": True}
    r = trades_df["net_ret"].values
    n = len(r)
    mean = float(np.mean(r))
    std = float(np.std(r, ddof=1)) if n > 1 else 0.0
    t = mean / std * np.sqrt(n) if std > 0 else 0.0
    winrate = float(np.mean(r > 0))
    return {
        "n": int(n),
        "mean_net_bp": round(mean * 10000, 2),
        "median_net_bp": round(float(np.median(r)) * 10000, 2),
        "std_bp": round(std * 10000, 2),
        "t_stat": round(float(t), 3),
        "winrate": round(winrate, 3),
    }


def concentration_diagnostics(trades_df: pd.DataFrame) -> dict:
    if trades_df.empty or len(trades_df) < 10:
        return {"insufficient": True}
    sym_ci = {}
    for sym, g in trades_df.groupby("symbol"):
        if len(g) < 5:
            continue
        ci = bootstrap_ci(g["net_ret"].values, n_boot=1000, block_size=1)
        sym_ci[sym] = {"n": int(len(g)),
                       "mean_bp": round(float(ci["mean"]) * 10000, 2),
                       "ci_lower_bp": round(float(ci["ci_lower"]) * 10000, 2),
                       "ci_upper_bp": round(float(ci["ci_upper"]) * 10000, 2),
                       "ci_pos": bool(ci["ci_lower"] > 0)}
    n_sym = len(sym_ci)
    n_sym_ci_pos = sum(1 for v in sym_ci.values() if v["ci_pos"])

    trades_df = trades_df.copy()
    trades_df["quarter"] = pd.PeriodIndex(pd.to_datetime(trades_df["entry_ts"]), freq="Q")
    q_ts = {}
    for q, g in trades_df.groupby("quarter"):
        if len(g) < 3:
            continue
        m = g["net_ret"].mean()
        s = g["net_ret"].std(ddof=1) if len(g) > 1 else 0
        t = m / s * np.sqrt(len(g)) if s > 0 else 0.0
        q_ts[str(q)] = {"n": int(len(g)), "mean_bp": round(float(m) * 10000, 2),
                        "t": round(float(t), 3), "pos_t": bool(t > 0)}
    n_q = len(q_ts)
    n_q_pos = sum(1 for v in q_ts.values() if v["pos_t"])
    return {
        "per_symbol": sym_ci,
        "n_sym_measurable": int(n_sym),
        "n_sym_ci_pos": int(n_sym_ci_pos),
        "sym_ci_pos_ratio": round(n_sym_ci_pos / n_sym, 3) if n_sym else 0.0,
        "per_quarter": q_ts,
        "n_q_measurable": int(n_q),
        "n_q_pos_t": int(n_q_pos),
        "q_pos_t_ratio": round(n_q_pos / n_q, 3) if n_q else 0.0,
    }


def main():
    log.info("=== Paradigm #248 R-1 (bugfix v2): on-chain AdrActCnt regime × BTC-sign → alt bilateral ===")

    aac = fetch_adr_act_cnt().dropna()
    log.info("AdrActCnt loaded: n=%d span=%s→%s", len(aac), aac.index.min().date(), aac.index.max().date())

    pct30 = pct_rank_30d(aac).dropna()
    pct30_lag1 = pct30.shift(1).dropna()   # yesterday's pct-rank is knowable at today 00:00
    log.info("pct30_lag1: n=%d", len(pct30_lag1))

    # BTC open at midnight for prior-day return (KNOWN at entry time D 00:00 UTC)
    btc_00 = load_open_at_midnight("BTCUSDT")
    log.info("BTC open@00:00: n=%d span=%s→%s", len(btc_00), btc_00.index.min().date(), btc_00.index.max().date())
    btc_ret_prior_day = btc_00.pct_change()   # (btc[D 00:00] - btc[D-1 00:00]) / btc[D-1 00:00]
    btc_sign_prior = np.sign(btc_ret_prior_day)

    # Alt hourly open series (for entry at any hour boundary + hold_hours later)
    alt_hourly = {}
    for sym in POC_ALTS:
        h = load_open_hourly(sym)
        if h.empty:
            log.warning("no data for %s", sym)
            continue
        alt_hourly[sym] = h
        log.info("%s hourly open: n=%d span=%s→%s", sym, len(h), h.index.min(), h.index.max())

    # Align trigger dates
    common = pct30_lag1.index.intersection(btc_sign_prior.dropna().index)
    log.info("aligned trigger dates: n=%d", len(common))
    regime = pct30_lag1.reindex(common)
    btc_sign_series = btc_sign_prior.reindex(common)

    # ---- Sweep ----
    hold_hours_list = [12, 24, 48, 72]
    threshold_pairs = [(0.30, 0.70), (0.25, 0.75), (0.20, 0.80)]
    quadrants = ["A_focus", "A_mirror", "B_focus", "B_mirror",
                 "C_focus", "C_mirror", "D_focus", "D_mirror"]

    results = []
    per_cell_trades = {}

    for (lo, hi) in threshold_pairs:
        for h in hold_hours_list:
            for q in quadrants:
                pooled = []
                for sym, alt_h in alt_hourly.items():
                    t = build_trades(regime, btc_sign_series, alt_h, lo, hi, h, q)
                    if not t.empty:
                        t["symbol"] = sym
                        pooled.append(t)
                pooled_df = pd.concat(pooled, ignore_index=True) if pooled else pd.DataFrame()
                per_cell_trades[(lo, hi, h, q)] = pooled_df
                ev = evaluate_cell(pooled_df)
                results.append({"lo": lo, "hi": hi, "hold_h": h, "quadrant": q, **ev})

    df = pd.DataFrame(results)
    log.info("swept %d cells", len(df))

    valid = df[(df["n"].fillna(0) >= 30) & (df["mean_net_bp"].fillna(-9999) > 0)].copy()
    valid["t_stat"] = pd.to_numeric(valid["t_stat"], errors="coerce")
    valid = valid.sort_values("t_stat", ascending=False)
    log.info("cells n>=30 & mean_net_bp>0: %d", len(valid))

    gated = []
    for _, row in valid.head(15).iterrows():
        lo, hi, h, q = float(row["lo"]), float(row["hi"]), int(row["hold_h"]), row["quadrant"]
        pooled_df = per_cell_trades[(lo, hi, h, q)]
        if pooled_df.empty or len(pooled_df) < 30:
            continue

        obs = pooled_df["net_ret"].values
        ci = bootstrap_ci(obs, n_boot=2000, block_size=5)

        _dir_map = {"A_focus": +1, "A_mirror": -1, "B_focus": -1, "B_mirror": +1,
                    "C_focus": +1, "C_mirror": -1, "D_focus": -1, "D_mirror": +1}
        direction = _dir_map[q]
        cand_gross = []
        for sym, alt_h in alt_hourly.items():
            days = pd.date_range(regime.index.min(), regime.index.max(), freq="D")
            for d in days:
                e_ts = d
                x_ts = d + pd.Timedelta(hours=h)
                e_idx = alt_h.index.get_indexer([e_ts], method="nearest", tolerance=pd.Timedelta("30min"))
                x_idx = alt_h.index.get_indexer([x_ts], method="nearest", tolerance=pd.Timedelta("30min"))
                if e_idx[0] == -1 or x_idx[0] == -1:
                    continue
                ep = alt_h.iloc[e_idx[0]]; xp = alt_h.iloc[x_idx[0]]
                if pd.notna(ep) and pd.notna(xp) and ep > 0:
                    cand_gross.append((xp / ep - 1.0) * direction)

        perm = fee_aware_perm_test(observed_net_returns=obs, candidate_pool_returns=cand_gross,
                                   fee_per_trade=FEE_RT, n_perms=1000)
        conc = concentration_diagnostics(pooled_df)

        three_gate_pass = (
            (perm.get("signal_t_excess", -999) >= 2.0)
            and (ci.get("ci_lower", -999) > 0)
            and (perm.get("perm_p_two_sided", 1.0) <= 0.10)
        )
        conc_gate_pass = (
            conc.get("sym_ci_pos_ratio", 0) >= 0.30
            and conc.get("q_pos_t_ratio", 0) >= 0.50
            and conc.get("n_sym_ci_pos", 0) >= 1
        )

        gated.append({
            "lo": lo, "hi": hi, "hold_h": h, "quadrant": q,
            "n": int(row["n"]),
            "mean_net_bp": float(row["mean_net_bp"]),
            "t_stat": float(row["t_stat"]),
            "winrate": float(row["winrate"]),
            "ci_lower_bp": round(float(ci.get("ci_lower", np.nan)) * 10000, 2),
            "ci_upper_bp": round(float(ci.get("ci_upper", np.nan)) * 10000, 2),
            "signal_t_excess": round(float(perm.get("signal_t_excess", np.nan)), 3),
            "perm_p_two_sided": round(float(perm.get("perm_p_two_sided", np.nan)), 4),
            "perm_null_mean_t": round(float(perm.get("null_mean_t", np.nan)), 3),
            "sym_ci_pos_ratio": conc.get("sym_ci_pos_ratio", 0),
            "n_sym_ci_pos": conc.get("n_sym_ci_pos", 0),
            "q_pos_t_ratio": conc.get("q_pos_t_ratio", 0),
            "n_q_pos_t": conc.get("n_q_pos_t", 0),
            "three_gate_pass": bool(three_gate_pass),
            "concentration_gate_pass": bool(conc_gate_pass),
            "per_symbol": conc.get("per_symbol", {}),
            "per_quarter": conc.get("per_quarter", {}),
        })

    # SNT Lesson #19 pairs
    snt = []
    for (lo, hi, h) in {(c["lo"], c["hi"], c["hold_h"]) for c in results}:
        for letter in ["A", "B", "C", "D"]:
            focus = next((c for c in results if c["lo"] == lo and c["hi"] == hi
                          and c["hold_h"] == h and c["quadrant"] == f"{letter}_focus"), None)
            mirror = next((c for c in results if c["lo"] == lo and c["hi"] == hi
                           and c["hold_h"] == h and c["quadrant"] == f"{letter}_mirror"), None)
            if not focus or not mirror or focus.get("insufficient") or mirror.get("insufficient"):
                continue
            sum_bp = focus["mean_net_bp"] + mirror["mean_net_bp"]
            fee_floor_bp = -2 * FEE_RT * 10000
            snt.append({
                "lo": lo, "hi": hi, "hold_h": h, "quadrant_pair": letter,
                "focus_bp": focus["mean_net_bp"],
                "mirror_bp": mirror["mean_net_bp"],
                "sum_bp": round(sum_bp, 2),
                "fee_floor_bp": round(fee_floor_bp, 2),
                "broad_fee_symmetric": bool(sum_bp < -1.5 * FEE_RT * 10000),
            })

    pass_cells = [g for g in gated if g["three_gate_pass"] and g["concentration_gate_pass"]]

    verdict = "R1_GRAVEYARD"
    reason = ""
    if len(pass_cells) >= 1:
        verdict = "R1_PASS"
        reason = f"{len(pass_cells)} cells pass 3-gate + concentration"
    elif len(gated) == 0:
        verdict = "R1_GRAVEYARD_INSUFFICIENT_TRADES"
        reason = "no cell reached n>=30 with mean_net_bp>0"
    elif all(g["three_gate_pass"] is False for g in gated):
        verdict = "R1_GRAVEYARD_3GATE_FAIL"
        reason = "no cell passed signal_t_excess>=2 AND ci_lower>0 AND perm_p<=0.10"

    all_sub_a = all(s["broad_fee_symmetric"] for s in snt) if snt else False
    if all_sub_a and verdict.startswith("R1_GRAVEYARD"):
        verdict = "R1_GRAVEYARD_BROAD_FALSIFIED_LESSON39_SUBCLASS_A"
        reason = "all A/B/C/D pairs show focus+mirror ≈ -2×fee → trigger carries no directional info"

    out = {
        "paradigm": PARADIGM,
        "phase": "R-1",
        "bugfix_note": "v2: entry at 1m open @ 00:00 UTC + prior-day BTC return knowable at that timestamp",
        "pool_alts": POC_ALTS,
        "n_cells": len(df),
        "n_valid_cells_n30_pos": len(valid),
        "n_gated_cells": len(gated),
        "n_pass_3gate_concentration": len(pass_cells),
        "verdict": verdict,
        "verdict_reason": reason,
        "regime_aligned_n": int(len(regime)),
        "regime_span": [str(regime.index.min().date()), str(regime.index.max().date())],
        "all_cells": results,
        "gated_cells": gated,
        "snt_lesson19_pairs": snt,
        "snt_all_pairs_broad_fee_symmetric": bool(all_sub_a),
        "pass_cells": pass_cells,
    }

    out_path = OUT_DIR / "r1__metrics.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("wrote %s", out_path)
    log.info("VERDICT: %s (%s)", verdict, reason)
    print(json.dumps({"paradigm": PARADIGM, "phase": "R-1",
                      "verdict": verdict, "n_pass": len(pass_cells),
                      "n_gated": len(gated), "n_cells": len(df)}))


if __name__ == "__main__":
    main()
