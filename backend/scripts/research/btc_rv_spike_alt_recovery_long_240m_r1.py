"""R-1 PoC — btc_rv_spike_alt_recovery_long_240m.

Hypothesis (single sentence)
----------------------------
When BTC 30-minute realized volatility z-score(30d rolling) rises above +2.5
(rising edge + 60-min cooldown), 13 altcoin perpetuals show a systematic
LONG-only mean reversion at hold horizon = 240 minutes (4 hours after BTC
trigger), independent of BTC's 30-min return sign. This is the "vol shock
absorption recovery" hypothesis derived from 62nd graveyard's hold=240m
residual finding (t=+2.11, mean +8.1bp gross, but contaminated by direction
selection and fee drift).

Trigger replay
--------------
IDENTICAL trigger construction as 62nd graveyard
(btc_rv_spike_alt_contagion_r1.py):
  - BTC 1m close -> 1m log-returns -> 30-bar rolling std (= 30m realized vol)
  - 30d (43200 1m bars) rolling z-score on RV series
  - Trigger: rv_z[t] > 2.5 AND rv_z[t-1] <= 2.5 (rising edge)
  - 60-min cooldown between triggers

Trade construction (DIFFERENT from 62nd)
----------------------------------------
For EACH trigger event at BTC time t:
  - Entry on each of 13 alts at close[t+1m]
  - Hold = 240 minutes (FIXED, no grid -- H4 sanity check only)
  - Direction = +1 (LONG always, regardless of BTC sign)
  - Exit at close[t+1+240]
  - Net return = gross - 8e-4 (round-trip fee)

Three-gate criteria (NEW)
-------------------------
PASS all three on pooled net returns at hold=240m:
  - signal_t_excess >= 2.0  (obs_t - null_mean_t from fee_aware_perm_test)
  - bootstrap_ci.ci_lower > 0  (95% CI on mean strictly above zero)
  - perm_p_two_sided <= 0.10

GRAVEYARD if any gate fails OR mean negative OR H3 < 8/13 alts excess>1.0
OR H4 240m is single-point overfit (300m AND 180m both negative).
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
from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("btc_rv_recovery_r1")

PARADIGM = "btc_rv_spike_alt_recovery_long_240m"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_PATH = OUT_DIR / "r1__metrics.json"

BTC = "BTCUSDT"
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# Trigger config (IDENTICAL to 62nd graveyard)
RV_WINDOW = 30          # 1m bars (30-minute realized vol)
Z_WINDOW = 30 * 24 * 60  # 43200 bars (30 days of 1m)
Z_THRESH = 2.5
COOLDOWN = 60           # min between triggers

# Trade config
PRIMARY_HOLD = 240      # main hypothesis
HOLD_GRID = [180, 240, 300]  # H4 sanity check
DIRECTION = +1          # LONG-only, unsigned
FEE_RT = 8e-4

# Stat config
PERM_N = 1000
BOOT_N = 2000
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


# ---------- trigger (REUSE 62nd graveyard logic verbatim) ----------


def build_btc_triggers(btc: pd.DataFrame) -> pd.DataFrame:
    """Compute 30m RV, 30d z-score, rising-edge trigger events.

    Returns DataFrame indexed by trigger timestamp with columns:
        rv, rv_z, btc_ret_30m, sign (+1 / -1 -- captured for H5 split only)
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


# ---------- fast lookup ----------


def build_ts_index(closes: pd.Series) -> dict:
    return {ts: i for i, ts in enumerate(closes.index)}


def trades_for_alt_long(close_arr: np.ndarray, ts_to_pos: dict,
                        trig_ts: list, hold_min: int) -> np.ndarray:
    """LONG-only trades at each trigger.

    Returns array of GROSS returns at hold=hold_min. NaN if entry/exit missing.
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
            out[i] = (xp / ep - 1)  # LONG (no sign multiplication)
    return out


def all_forward_returns(close_arr: np.ndarray, hold_min: int) -> np.ndarray:
    """Compute forward `hold_min`-bar (1m) gross returns from each bar.

    Used as the LONG candidate pool for fee_aware_perm_test.
    """
    n = len(close_arr)
    if n <= hold_min + 2:
        return np.array([])
    # Vectorized: forward return from i to i+hold_min (matches 1m alignment;
    # the actual trade entry is at trigger+1m, exit at trigger+1+hold; the
    # forward window has the same hold length so distribution is the same).
    entry = close_arr[: n - hold_min]
    exit_ = close_arr[hold_min:]
    ret = exit_ / entry - 1
    valid = np.isfinite(ret) & (entry > 0)
    return ret[valid]


# ---------- stats ----------


def t_stat(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return float("nan")
    sd = np.std(x, ddof=1)
    if sd == 0:
        return float("nan")
    return float(np.mean(x) / (sd / np.sqrt(len(x))))


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
        data_first = btc.index.min()
        data_last = btc.index.max()
        data_days = (data_last - data_first).days

        triggers = build_btc_triggers(btc)
        n_trig = len(triggers)
        log.info("final triggers (post-cooldown): %d", n_trig)
        if n_trig == 0:
            out = {"verdict": "GRAVEYARD", "reason": "no triggers", "n_triggers": 0}
            OUT_PATH.write_text(json.dumps(out, indent=2))
            return 0

        sign_counts = {int(k): int(v) for k, v in triggers["sign"].value_counts().to_dict().items()}
        log.info("trigger signs: %s", sign_counts)

        # Load alts
        alt_data = {}
        alt_lookup = {}
        for sym in ALTS:
            df = load_ohlcv_1m(db, sym)
            if df.empty:
                log.warning("missing %s", sym)
                continue
            alt_data[sym] = df["close"].to_numpy()
            alt_lookup[sym] = build_ts_index(df["close"])
            log.info("  loaded %s: %d bars", sym, len(df))

        trig_ts_list = list(triggers.index)

        # ============================================================
        # H1 — pooled LONG mean reversion at hold=240m
        # ============================================================
        log.info("== H1: pooled LONG at hold=%dm ==", PRIMARY_HOLD)
        pool_gross_240 = []
        per_alt_240 = {}
        per_alt_returns_240 = {}  # for H3 per-sym fee_aware test
        for sym in alt_data:
            rets = trades_for_alt_long(alt_data[sym], alt_lookup[sym],
                                       trig_ts_list, PRIMARY_HOLD)
            valid = rets[~np.isnan(rets)]
            if len(valid) == 0:
                per_alt_240[sym] = {"n": 0}
                continue
            per_alt_returns_240[sym] = valid
            net = valid - FEE_RT
            pool_gross_240.extend(valid.tolist())
            per_alt_240[sym] = {
                "n": int(len(valid)),
                "mean_gross": float(np.mean(valid)),
                "mean_net": float(np.mean(net)),
                "t_stat_net": t_stat(net),
                "win_rate_net": float(np.mean(net > 0)),
            }
        pool_gross_240 = np.array(pool_gross_240)
        pool_net_240 = pool_gross_240 - FEE_RT
        H1 = {
            "hold_min": PRIMARY_HOLD,
            "n_trades": int(len(pool_net_240)),
            "gross": summarize(pool_gross_240),
            "net": summarize(pool_net_240),
        }
        log.info("H1: n=%d gross_mean=%.6f net_mean=%.6f net_t=%.3f win=%.3f",
                 H1["n_trades"], H1["gross"].get("mean", float("nan")),
                 H1["net"].get("mean", float("nan")),
                 H1["net"].get("t_stat", float("nan")),
                 H1["net"].get("win_rate", float("nan")))

        # ============================================================
        # H2 — fee_aware_perm_test + bootstrap_ci on pooled net @ 240m
        # ============================================================
        log.info("== H2: fee_aware_perm_test + bootstrap_ci @ hold=%d ==", PRIMARY_HOLD)

        # Candidate pool: every possible 240m forward GROSS return across all 13 alts.
        # This is the LONG universe baseline (excluding trigger selection).
        log.info("building candidate pool (all 240m forward returns across %d alts)", len(alt_data))
        candidate_pool = []
        for sym in alt_data:
            fwd = all_forward_returns(alt_data[sym], PRIMARY_HOLD)
            candidate_pool.extend(fwd.tolist())
        log.info("  candidate pool size: %d", len(candidate_pool))

        log.info("fee_aware_perm_test n=%d ...", PERM_N)
        fee_perm = fee_aware_perm_test(
            observed_net_returns=pool_net_240.tolist(),
            candidate_pool_returns=candidate_pool,
            fee_per_trade=FEE_RT,
            n_perms=PERM_N,
            rng_seed=SEED,
        )
        log.info("  obs_t=%.3f null_mean_t=%.3f signal_t_excess=%.3f perm_p_two=%.4f perm_p_above=%.4f",
                 fee_perm["obs_t"], fee_perm["null_mean_t"],
                 fee_perm["signal_t_excess"], fee_perm["perm_p_two_sided"],
                 fee_perm["perm_p_one_sided_above"])

        log.info("bootstrap_ci n=%d block=%d ...", BOOT_N, PRIMARY_HOLD)
        ci = bootstrap_ci(
            observed_net_returns=pool_net_240.tolist(),
            n_boot=BOOT_N,
            block_size=PRIMARY_HOLD,
            rng_seed=SEED,
        )
        log.info("  ci.mean=%.6f lower=%.6f upper=%.6f prob_pos=%.3f",
                 ci["mean"], ci["ci_lower"], ci["ci_upper"], ci["prob_positive"])

        # ============================================================
        # H3 — per-symbol breakdown (signal_t_excess > 1.0 count)
        # ============================================================
        log.info("== H3: per-symbol signal_t_excess @ hold=%d ==", PRIMARY_HOLD)
        per_sym_h3 = {}
        cont_count_excess_1 = 0
        for sym, valid in per_alt_returns_240.items():
            net = valid - FEE_RT
            sym_pool = all_forward_returns(alt_data[sym], PRIMARY_HOLD).tolist()
            if len(sym_pool) < 2 * len(net) or len(net) < 5:
                per_sym_h3[sym] = {
                    "n": int(len(net)),
                    "mean_net": float(np.mean(net)) if len(net) else float("nan"),
                    "signal_t_excess": float("nan"),
                    "perm_p_two_sided": float("nan"),
                    "note": "insufficient pool or trades",
                }
                continue
            sp = fee_aware_perm_test(
                observed_net_returns=net.tolist(),
                candidate_pool_returns=sym_pool,
                fee_per_trade=FEE_RT,
                n_perms=400,  # lighter per-sym
                rng_seed=SEED,
            )
            per_sym_h3[sym] = {
                "n": int(len(net)),
                "mean_net": float(np.mean(net)),
                "obs_t": float(sp["obs_t"]),
                "null_mean_t": float(sp["null_mean_t"]),
                "signal_t_excess": float(sp["signal_t_excess"]),
                "perm_p_two_sided": float(sp["perm_p_two_sided"]),
                "perm_p_one_sided_above": float(sp["perm_p_one_sided_above"]),
            }
            if np.isfinite(sp["signal_t_excess"]) and sp["signal_t_excess"] > 1.0:
                cont_count_excess_1 += 1
        n_total_alts = len(per_alt_returns_240)
        log.info("H3: %d/%d alts with signal_t_excess > 1.0", cont_count_excess_1, n_total_alts)

        # ============================================================
        # H4 — alternative hold sensitivity (180, 240, 300)
        # ============================================================
        log.info("== H4: hold sensitivity %s ==", HOLD_GRID)
        H4 = {}
        for H in HOLD_GRID:
            pool_gross = []
            for sym in alt_data:
                rets = trades_for_alt_long(alt_data[sym], alt_lookup[sym],
                                           trig_ts_list, H)
                valid = rets[~np.isnan(rets)]
                if len(valid):
                    pool_gross.extend(valid.tolist())
            arr = np.array(pool_gross) - FEE_RT if pool_gross else np.array([])
            H4[str(H)] = {
                "hold_min": H,
                "n_trades": int(len(arr)),
                "mean_net": float(np.mean(arr)) if len(arr) else float("nan"),
                "t_stat_net": t_stat(arr),
                "win_rate_net": float(np.mean(arr > 0)) if len(arr) else float("nan"),
            }
            log.info("  hold=%d n=%d mean_net=%.6f t=%.3f",
                     H, H4[str(H)]["n_trades"],
                     H4[str(H)]["mean_net"], H4[str(H)]["t_stat_net"])

        # H4 robustness: 240m should not be the ONLY positive hold
        h180_neg = H4["180"]["mean_net"] < 0 if np.isfinite(H4["180"]["mean_net"]) else False
        h300_neg = H4["300"]["mean_net"] < 0 if np.isfinite(H4["300"]["mean_net"]) else False
        h4_single_point = h180_neg and h300_neg and H4["240"]["mean_net"] > 0

        # ============================================================
        # H5 — BTC sign split (was 62nd's t=+2.11 driven by one side?)
        # ============================================================
        log.info("== H5: BTC sign split (LONG hold @ 240m on each side) ==")
        H5 = {}
        for side, sg in [("up", 1), ("down", -1)]:
            sub_mask = triggers["sign"] == sg
            sub_ts = list(triggers.index[sub_mask])
            if len(sub_ts) == 0:
                H5[side] = {"n_trig": 0}
                continue
            pool = []
            for sym in alt_data:
                rets = trades_for_alt_long(alt_data[sym], alt_lookup[sym],
                                           sub_ts, PRIMARY_HOLD)
                valid = rets[~np.isnan(rets)]
                if len(valid):
                    pool.extend(valid.tolist())
            arr = np.array(pool) - FEE_RT if pool else np.array([])
            H5[side] = {
                "n_trig": int(len(sub_ts)),
                "n_trades": int(len(arr)),
                "mean_net": float(np.mean(arr)) if len(arr) else float("nan"),
                "t_stat_net": t_stat(arr),
                "win_rate_net": float(np.mean(arr > 0)) if len(arr) else float("nan"),
            }
            log.info("  %s: n_trig=%d n_trades=%d mean_net=%.6f t=%.3f",
                     side, H5[side]["n_trig"], H5[side]["n_trades"],
                     H5[side]["mean_net"], H5[side]["t_stat_net"])

        # ============================================================
        # Verdict — three-gate
        # ============================================================
        obs_t = float(H1["net"].get("t_stat", float("nan")))
        obs_mean = float(H1["net"].get("mean", float("nan")))
        signal_t_excess = float(fee_perm["signal_t_excess"])
        ci_lower = float(ci["ci_lower"])
        ci_upper = float(ci["ci_upper"])
        perm_p_two = float(fee_perm["perm_p_two_sided"])
        perm_p_above = float(fee_perm["perm_p_one_sided_above"])
        null_mean_t = float(fee_perm["null_mean_t"])

        reasons = []
        graveyard = False
        if not np.isfinite(obs_mean) or obs_mean <= 0:
            graveyard = True
            reasons.append(f"obs mean={obs_mean:.6f} <= 0 (LONG direction failed)")
        if not np.isfinite(signal_t_excess) or signal_t_excess < 2.0:
            graveyard = True
            reasons.append(f"signal_t_excess={signal_t_excess:.3f} < 2.0")
        if not np.isfinite(ci_lower) or ci_lower <= 0:
            graveyard = True
            reasons.append(f"bootstrap ci_lower={ci_lower:.6f} <= 0")
        if not np.isfinite(perm_p_two) or perm_p_two > 0.10:
            graveyard = True
            reasons.append(f"perm_p_two_sided={perm_p_two:.4f} > 0.10")
        if cont_count_excess_1 < 8:
            graveyard = True
            reasons.append(f"H3: only {cont_count_excess_1}/{n_total_alts} alts signal_t_excess>1 (need >=8)")
        if h4_single_point:
            graveyard = True
            reasons.append("H4: 240m single-point overfit (180m AND 300m both negative)")

        candidate = (
            not graveyard
            and signal_t_excess >= 2.0
            and ci_lower > 0
            and perm_p_two <= 0.10
            and obs_mean > 0
            and cont_count_excess_1 >= 10
            and not h4_single_point
        )
        borderline = (
            not graveyard
            and not candidate
            and (
                (1.5 <= signal_t_excess < 2.0)
                or (-0.0005 <= ci_lower <= 0 and obs_mean > 0)
            )
        )

        if graveyard:
            verdict = "GRAVEYARD"
        elif candidate:
            verdict = "CANDIDATE-FOR-R2"
        elif borderline:
            verdict = "BORDERLINE"
        else:
            verdict = "BORDERLINE"
            reasons.append("neither candidate nor graveyard -> default borderline")

        out = {
            "paradigm": PARADIGM,
            "verdict": verdict,
            "verdict_reasons": reasons,
            "data_window": {
                "btc_first": str(data_first),
                "btc_last": str(data_last),
                "data_days": int(data_days),
            },
            "config": {
                "rv_window_bars": RV_WINDOW,
                "z_window_bars": Z_WINDOW,
                "z_thresh": Z_THRESH,
                "cooldown_min": COOLDOWN,
                "primary_hold_min": PRIMARY_HOLD,
                "hold_grid_min": HOLD_GRID,
                "direction": "+1 LONG-only unsigned",
                "fee_round_trip": FEE_RT,
                "perm_n": PERM_N,
                "boot_n": BOOT_N,
                "alts": ALTS,
            },
            "trigger_summary": {
                "n_triggers": int(n_trig),
                "sign_counts": sign_counts,
            },
            "H1_pooled_240m": H1,
            "H1_per_alt_240m": per_alt_240,
            "H2_fee_aware_perm": {
                "obs_mean": float(fee_perm["obs_mean"]),
                "obs_t": float(fee_perm["obs_t"]),
                "null_mean_t": float(fee_perm["null_mean_t"]),
                "null_std_t": float(fee_perm["null_std_t"]),
                "signal_t_excess": float(fee_perm["signal_t_excess"]),
                "perm_p_two_sided": float(fee_perm["perm_p_two_sided"]),
                "perm_p_one_sided_above": float(fee_perm["perm_p_one_sided_above"]),
                "perm_p_one_sided_below": float(fee_perm["perm_p_one_sided_below"]),
                "n_observed": int(fee_perm["n_observed"]),
                "n_candidate": int(fee_perm["n_candidate"]),
            },
            "H2b_bootstrap_ci": {
                "mean": float(ci["mean"]),
                "ci_lower": float(ci["ci_lower"]),
                "ci_upper": float(ci["ci_upper"]),
                "prob_positive": float(ci["prob_positive"]),
                "n": int(ci["n"]),
                "block_size": int(ci.get("block_size", PRIMARY_HOLD)),
            },
            "H3_per_sym": per_sym_h3,
            "H3_count_excess_gt1": int(cont_count_excess_1),
            "H3_n_total_alts": int(n_total_alts),
            "H4_hold_sensitivity": H4,
            "H4_single_point_overfit": bool(h4_single_point),
            "H5_btc_sign_split": H5,
        }

        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        log.info("wrote %s", OUT_PATH)
        log.info("VERDICT: %s", verdict)
        for r in reasons:
            log.info("  reason: %s", r)
        return 0


if __name__ == "__main__":
    sys.exit(main())
