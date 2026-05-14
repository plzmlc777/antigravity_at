"""R-1 PoC — btc_rv_spike_alt_contagion_long.

Hypothesis
----------
Immediately after BTC 30-minute realized volatility z-score(30d rolling)
exceeds +2.5 (rising edge: prev z <= +2.5, curr z > +2.5), 13 altcoin
perpetuals show systematic directional momentum continuation aligned
with BTC's same-30min sign over the next 30-240 minutes from trigger
close.

Mechanism
---------
BTC RV spike = vol-regime shock (news / liquidation cascade / macro).
Within seconds-minutes, alt order books adjust to BTC's regime; aggressive
traders front-run BTC's direction -> alts develop momentum tail.

Sub-hypotheses
--------------
H1  Pooled directional EV positive at best hold window (30/60/90/120/180/240 min)
H2  Net of 8 bp round-trip fee, EV still positive; annualized alpha per sym
H3  Permutation null (shuffle trigger times) two-sided p <= 0.05
H4  Cross-sym continuation count: >= 8/13 alts t > +1.0 at best hold
H5  Asymmetry: up triggers -> alt long EV positive; down triggers -> alt short EV
    positive (sign of (alt_ret * btc_trigger_sign)).

Trigger
-------
- BTC 1m ohlcv -> rolling 30m windows (every 1m, lookback 30 bars).
- 30m realized vol = std(1m log-returns over 30 bars).
- Rolling z-score: window = 30d * 24 * 60 = 43200 1m bars on the 30m-rolling-RV series.
- Trigger event: RV_z[t] > 2.5 AND RV_z[t-1] <= 2.5 (rising edge).
- Trigger sign = sign(BTC close[t] / close[t-30] - 1) (30m return).
- Cooldown: drop trigger if previous trigger within 60 min (re-arm gate).

Trade
-----
For each trigger at BTC time t (1m timestamp aligned across all syms):
- Entry on alt at close[t+1m].
- Hold H in {30, 60, 90, 120, 180, 240} minutes -> exit at close[t+1+H].
- Direction = BTC trigger sign.
- Gross return = direction * (exit / entry - 1).
- Net return = gross - 8e-4 (round-trip 8 bp fee).

Output
------
backend/runs/research_track/btc_rv_spike_alt_contagion_long/r1__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("btc_rv_spike_r1")

PARADIGM = "btc_rv_spike_alt_contagion_long"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_PATH = OUT_DIR / "r1__metrics.json"

BTC = "BTCUSDT"
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

RV_WINDOW = 30          # 1m bars (30-minute realized vol)
Z_WINDOW = 30 * 24 * 60  # 43200 bars = 30 days of 1m
Z_THRESH = 2.5
COOLDOWN = 60           # bars (1m) between trigger re-arm
HOLDS = [30, 60, 90, 120, 180, 240]
FEE_RT = 8e-4           # 8 bp round-trip
PERM_N = 1000
SEED = 42

# ---------- data ----------


def load_ohlcv_1m(db, sym: str) -> pd.DataFrame:
    rows = db.execute(text(
        "SELECT timestamp, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    ), {"s": sym}).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df


# ---------- signal ----------


def build_btc_triggers(btc: pd.DataFrame) -> pd.DataFrame:
    """Compute 30m RV, 30d z-score, rising-edge trigger events.

    Returns DataFrame indexed by trigger timestamp with columns:
        rv, rv_z, btc_ret_30m, sign (+1 / -1)
    """
    log.info("computing 1m log-returns over %d bars (BTC)", len(btc))
    lr = np.log(btc["close"]).diff()
    rv = lr.rolling(RV_WINDOW, min_periods=RV_WINDOW).std()
    rv_mu = rv.rolling(Z_WINDOW, min_periods=Z_WINDOW).mean()
    rv_sd = rv.rolling(Z_WINDOW, min_periods=Z_WINDOW).std()
    rv_z = (rv - rv_mu) / rv_sd

    btc_ret_30m = btc["close"] / btc["close"].shift(RV_WINDOW) - 1

    sig = pd.DataFrame({"rv": rv, "rv_z": rv_z, "btc_ret_30m": btc_ret_30m}).dropna()

    z_prev = sig["rv_z"].shift(1)
    fire = (sig["rv_z"] > Z_THRESH) & (z_prev <= Z_THRESH)
    triggers = sig[fire].copy()
    triggers["sign"] = np.sign(triggers["btc_ret_30m"]).astype(int)
    triggers = triggers[triggers["sign"] != 0]
    log.info("raw triggers (rising edge): %d", len(triggers))

    if len(triggers) == 0:
        return triggers
    keep = [True]
    last_t = triggers.index[0]
    for ts in triggers.index[1:]:
        delta_min = (ts - last_t).total_seconds() / 60.0
        if delta_min < COOLDOWN:
            keep.append(False)
        else:
            keep.append(True)
            last_t = ts
    triggers = triggers[keep]
    log.info("after %dmin cooldown: %d", COOLDOWN, len(triggers))
    return triggers


# ---------- fast lookup: timestamp -> position ----------


def build_ts_index(closes: pd.Series) -> dict:
    """Returns dict of pd.Timestamp -> integer position into closes.values array."""
    return {ts: i for i, ts in enumerate(closes.index)}


def trades_for_alt(close_arr: np.ndarray, ts_to_pos: dict,
                   trig_ts: list, trig_signs: np.ndarray,
                   hold_min: int) -> np.ndarray:
    """Vectorized-ish: for each trigger, look up entry/exit prices via dict.

    Returns 1D array of gross returns (signed). NaN where lookup failed.
    """
    n = len(trig_ts)
    out = np.full(n, np.nan)
    for i, ts in enumerate(trig_ts):
        entry_ts = ts + pd.Timedelta(minutes=1)
        exit_ts = ts + pd.Timedelta(minutes=1 + hold_min)
        ei = ts_to_pos.get(entry_ts)
        xi = ts_to_pos.get(exit_ts)
        if ei is None or xi is None:
            continue
        ep = close_arr[ei]
        xp = close_arr[xi]
        if ep > 0 and not np.isnan(ep) and not np.isnan(xp):
            out[i] = (xp / ep - 1) * trig_signs[i]
    return out


# ---------- stats ----------


def t_stat(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return float("nan")
    return float(np.mean(x) / (np.std(x, ddof=1) / np.sqrt(len(x))))


def summarize(arr: np.ndarray) -> dict:
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return {"n": 0}
    return {
        "n": int(len(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else float("nan"),
        "t_stat": t_stat(arr),
        "win_rate": float(np.mean(arr > 0)),
    }


# ---------- main ----------


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("== R-1 PoC: %s ==", PARADIGM)

    with SessionLocal() as db:
        btc = load_ohlcv_1m(db, BTC)
        if btc.empty:
            log.error("no BTC ohlcv")
            return 2
        log.info("BTC bars: %d, range %s -> %s", len(btc), btc.index.min(), btc.index.max())

        triggers = build_btc_triggers(btc)
        n_trig = len(triggers)
        log.info("final triggers (post-cooldown): %d", n_trig)
        if n_trig == 0:
            out = {"verdict": "GRAVEYARD", "reason": "no triggers", "n_triggers": 0}
            OUT_PATH.write_text(json.dumps(out, indent=2))
            return 0

        sign_counts = {int(k): int(v) for k, v in triggers["sign"].value_counts().to_dict().items()}
        log.info("trigger signs: %s", sign_counts)

        # Load alts and build fast lookup tables
        alt_data = {}      # sym -> close np.ndarray
        alt_lookup = {}    # sym -> dict ts -> int pos
        for sym in ALTS:
            df = load_ohlcv_1m(db, sym)
            if df.empty:
                log.warning("missing %s", sym)
                continue
            alt_data[sym] = df["close"].to_numpy()
            alt_lookup[sym] = build_ts_index(df["close"])
            log.info("  loaded %s: %d bars", sym, len(df))

        trig_ts_list = list(triggers.index)
        trig_signs = triggers["sign"].to_numpy()

        # ---- H1: per-hold pooled and per-alt ----
        per_hold = {}
        per_alt_by_hold = {}
        for H in HOLDS:
            log.info("-- hold=%d min --", H)
            pool_gross = []
            pool_net = []
            per_alt = {}
            for sym in alt_data:
                rets = trades_for_alt(alt_data[sym], alt_lookup[sym],
                                      trig_ts_list, trig_signs, H)
                valid = rets[~np.isnan(rets)]
                if len(valid) == 0:
                    per_alt[sym] = {"n": 0, "t_stat": float("nan"), "mean_net": float("nan")}
                    continue
                net = valid - FEE_RT
                pool_gross.extend(valid.tolist())
                pool_net.extend(net.tolist())
                per_alt[sym] = {
                    "n": int(len(valid)),
                    "t_stat": t_stat(net),
                    "mean_net": float(np.mean(net)),
                    "mean_gross": float(np.mean(valid)),
                    "win_rate": float(np.mean(net > 0)),
                }
            pg = np.array(pool_gross)
            pn = np.array(pool_net)
            per_hold[str(H)] = {
                "n_trades": int(len(pn)),
                "gross": summarize(pg),
                "net": summarize(pn),
            }
            per_alt_by_hold[str(H)] = per_alt
            log.info("  pooled n=%d net_mean=%.5f net_t=%.2f win_rate=%.3f",
                     len(pn),
                     float(np.mean(pn)) if len(pn) else float("nan"),
                     t_stat(pn),
                     float(np.mean(pn > 0)) if len(pn) else float("nan"))

        # Best hold by |t_stat|
        def _t_for(H):
            v = per_hold[str(H)]["net"].get("t_stat")
            return abs(v) if (v is not None and not np.isnan(v)) else 0
        best_hold = max(HOLDS, key=_t_for)
        best = per_hold[str(best_hold)]
        log.info("best hold by |t|: %d min, t=%.2f, net_mean=%.5f",
                 best_hold, best["net"]["t_stat"], best["net"]["mean"])

        # ---- H2: annualized alpha ----
        data_days = (btc.index.max() - btc.index.min()).days
        triggers_per_year = n_trig * (365.0 / max(data_days, 1))
        h2_per_alt = {}
        best_per_alt = per_alt_by_hold[str(best_hold)]
        for sym, d in best_per_alt.items():
            if d["n"] > 0:
                h2_per_alt[sym] = {
                    "mean_net": d["mean_net"],
                    "n": d["n"],
                    "ann_alpha_estimate": float(d["mean_net"] * triggers_per_year),
                }
        portfolio_ann = best["net"]["mean"] * triggers_per_year
        log.info("H2: triggers/year=%.1f portfolio_ann=%.4f", triggers_per_year, portfolio_ann)

        # ---- H3: permutation null at best hold ----
        log.info("H3: permutation null (n=%d) at hold=%d ...", PERM_N, best_hold)
        rng = np.random.default_rng(SEED)
        # Valid candidate bars: any BTC bar with hold_min+2 forward bars available
        # We use BTC index as the universe; alts are aligned (all 547200 bars).
        valid_idx = btc.index[: -(best_hold + 2)]
        if len(valid_idx) < n_trig:
            perm_out = {"obs_t": best["net"]["t_stat"], "perm_p_two_sided": None,
                        "note": "insufficient candidate bars"}
        else:
            perm_t = np.full(PERM_N, np.nan)
            n_valid = len(valid_idx)
            for k in range(PERM_N):
                sample_pos = rng.choice(n_valid, size=n_trig, replace=False)
                sample_ts = valid_idx[sample_pos]
                signs = rng.choice(trig_signs, size=n_trig, replace=True)
                all_net = []
                for sym in alt_data:
                    rets = trades_for_alt(alt_data[sym], alt_lookup[sym],
                                          list(sample_ts), signs, best_hold)
                    valid_r = rets[~np.isnan(rets)]
                    if len(valid_r) > 0:
                        all_net.extend((valid_r - FEE_RT).tolist())
                if len(all_net) > 1:
                    arr = np.array(all_net)
                    perm_t[k] = np.mean(arr) / (np.std(arr, ddof=1) / np.sqrt(len(arr)))
                if (k + 1) % 200 == 0:
                    log.info("  perm progress: %d/%d", k + 1, PERM_N)
            obs_t = best["net"]["t_stat"]
            ts_arr = perm_t[~np.isnan(perm_t)]
            p_two = float(np.mean(np.abs(ts_arr) >= abs(obs_t))) if len(ts_arr) else None
            perm_out = {
                "obs_t": float(obs_t),
                "perm_p_two_sided": p_two,
                "perm_n_done": int(len(ts_arr)),
                "perm_t_mean": float(np.mean(ts_arr)) if len(ts_arr) else None,
                "perm_t_std": float(np.std(ts_arr)) if len(ts_arr) else None,
            }
        log.info("H3: perm_p=%s", perm_out.get("perm_p_two_sided"))

        # ---- H4: cross-sym continuation count ----
        cont_count = sum(1 for sym, d in best_per_alt.items()
                         if d["n"] > 0 and (d["t_stat"] or 0) > 1.0)
        opp_count = sum(1 for sym, d in best_per_alt.items()
                        if d["n"] > 0 and (d["t_stat"] or 0) < -1.0)
        log.info("H4: continuation alts (t>+1)=%d / opposite (t<-1)=%d / total=%d",
                 cont_count, opp_count, len(best_per_alt))

        # ---- H5: asymmetry by trigger sign ----
        h5 = {}
        for side, sg in [("up", 1), ("down", -1)]:
            sub_mask = triggers["sign"] == sg
            sub_ts = list(triggers.index[sub_mask])
            sub_signs = triggers["sign"].to_numpy()[sub_mask.to_numpy()]
            if len(sub_ts) == 0:
                h5[side] = {"n_trig": 0}
                continue
            pool = []
            for sym in alt_data:
                rets = trades_for_alt(alt_data[sym], alt_lookup[sym],
                                      sub_ts, sub_signs, best_hold)
                valid_r = rets[~np.isnan(rets)]
                if len(valid_r):
                    pool.extend((valid_r - FEE_RT).tolist())
            arr = np.array(pool)
            h5[side] = {
                "n_trig": int(len(sub_ts)),
                "n_trades": int(len(arr)),
                "mean_net": float(np.mean(arr)) if len(arr) else float("nan"),
                "t_stat": t_stat(arr),
                "win_rate": float(np.mean(arr > 0)) if len(arr) else float("nan"),
            }
        h5_consistent = (
            not np.isnan(h5.get("up", {}).get("mean_net", float("nan")))
            and not np.isnan(h5.get("down", {}).get("mean_net", float("nan")))
            and h5["up"]["mean_net"] > 0
            and h5["down"]["mean_net"] > 0
        )
        log.info("H5: up_mean_net=%.5f down_mean_net=%.5f consistent=%s",
                 h5.get("up", {}).get("mean_net", float("nan")),
                 h5.get("down", {}).get("mean_net", float("nan")),
                 h5_consistent)

        # ---- Verdict ----
        verdict_reasons = []
        graveyard = False
        obs_t = best["net"]["t_stat"]
        if obs_t is None or np.isnan(obs_t) or abs(obs_t) < 1.8:
            graveyard = True
            verdict_reasons.append(f"|H1 t|={obs_t} < 1.8")
        if best["net"]["mean"] <= 0:
            graveyard = True
            verdict_reasons.append(f"H2 net_mean={best['net']['mean']:.5f} <= 0 after fee")
        p_two_val = perm_out.get("perm_p_two_sided")
        if p_two_val is not None and p_two_val > 0.05:
            graveyard = True
            verdict_reasons.append(f"H3 perm_p={p_two_val:.3f} > 0.05")
        if n_trig * len(alt_data) < 200:
            graveyard = True
            verdict_reasons.append(f"H4 total samples={n_trig*len(alt_data)} < 200")
        if cont_count < 8:
            graveyard = True
            verdict_reasons.append(f"H4 only {cont_count}/13 alts continuation (need >=8)")
        if not h5_consistent:
            graveyard = True
            verdict_reasons.append("H5 directional asymmetry inconsistent")

        candidate = (
            not graveyard
            and abs(obs_t) >= 2.5
            and best["net"]["mean"] > 0
            and (p_two_val is not None and p_two_val <= 0.01)
            and cont_count >= 10
            and h5_consistent
        )
        borderline = (
            not graveyard
            and not candidate
            and (
                (1.8 <= abs(obs_t) < 2.5)
                or (p_two_val is not None and 0.01 < p_two_val <= 0.05)
            )
            and best["net"]["mean"] > 0
        )

        if graveyard:
            verdict = "GRAVEYARD"
        elif candidate:
            verdict = "CANDIDATE-FOR-R2"
        elif borderline:
            verdict = "BORDERLINE"
        else:
            verdict = "BORDERLINE"
            verdict_reasons.append("neither candidate nor graveyard - default borderline")

        out = {
            "paradigm": PARADIGM,
            "verdict": verdict,
            "verdict_reasons": verdict_reasons,
            "data_window": {
                "btc_first": str(btc.index.min()),
                "btc_last": str(btc.index.max()),
                "data_days": int(data_days),
            },
            "config": {
                "rv_window_bars": RV_WINDOW,
                "z_window_bars": Z_WINDOW,
                "z_thresh": Z_THRESH,
                "cooldown_min": COOLDOWN,
                "holds_min": HOLDS,
                "fee_round_trip": FEE_RT,
                "perm_n": PERM_N,
                "alts": ALTS,
            },
            "trigger_summary": {
                "n_triggers": int(n_trig),
                "sign_counts": sign_counts,
                "triggers_per_year_est": float(triggers_per_year),
            },
            "H1_per_hold": per_hold,
            "H1_best_hold_min": int(best_hold),
            "H1_per_alt_at_best": best_per_alt,
            "H2_portfolio_ann_alpha": float(portfolio_ann),
            "H2_per_alt": h2_per_alt,
            "H3_perm": perm_out,
            "H4_continuation_count": int(cont_count),
            "H4_opposite_count": int(opp_count),
            "H4_alts_total": int(len(best_per_alt)),
            "H5_asymmetry": h5,
            "H5_consistent_both_sides": bool(h5_consistent),
        }

        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        log.info("wrote %s", OUT_PATH)
        log.info("VERDICT: %s", verdict)
        for r in verdict_reasons:
            log.info("  reason: %s", r)
        return 0


if __name__ == "__main__":
    sys.exit(main())
