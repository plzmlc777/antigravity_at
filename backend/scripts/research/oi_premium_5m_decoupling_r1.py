"""R-1 PoC for paradigm 80: oi_premium_5m_decoupling

Mechanism A (Decouple-reversal):
- 5m OI z-score and 5m premium z-score over rolling 24h window (W=288)
- LONG trigger:  oi_z >  Z and premium_z < -Z  (perp underpriced relative to spot,
                                                arb pushes price up)
- SHORT trigger: oi_z < -Z and premium_z >  Z  (perp overpriced, arb pushes down)
- Focus threshold Z = 2.0
- Hold sweep: 5m, 15m, 30m, 60m, 240m (focus 60m)
- Fee: 8 bp round-trip (Binance perp taker assumption already used by paradigm 69 + 21)
- 14 syms × ~1.48 yr overlap (OI window-limited)

Stat suite (mandatory):
- fee_aware_perm_test vs candidate pool = all non-trigger 60m hold windows
- bootstrap_ci block_size = hold_bars
- Three-gate + Concentration Gate (Lesson #16) + per-symbol bootstrap

Outputs to runs/research_track/oi_premium_5m_decoupling/:
  r1__metrics.json   r1__per_symbol.csv   r1__hold_sweep.csv
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("p80_r1")

SYMS = [
    "BTCUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "BCHUSDT",
    "BNBUSDT",
    "DOGEUSDT",
    "ETHUSDT",
    "FILUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "NEARUSDT",
    "SOLUSDT",
    "WIFUSDT",
    "XRPUSDT",
]

ROLL_WINDOW = 288  # 24h of 5m bars
Z_THRESHOLD = 2.0  # focus
HOLD_BARS = {  # in 5m bars
    "5m": 1,
    "15m": 3,
    "30m": 6,
    "60m": 12,
    "240m": 48,
}
FOCUS_HOLD = "60m"
FEE = 0.0008  # 8 bp round-trip

OUT_DIR = ROOT / "runs" / "research_track" / "oi_premium_5m_decoupling"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_sym(sym: str) -> pd.DataFrame:
    """Return aligned 5m frame with columns:
    [premium, oi, close5m, oi_z, premium_z, fwd_return_<hold>]
    """
    prem_path = ROOT / "runs" / "premium_index" / f"{sym}_premium_5m.joblib"
    micro_path = ROOT / "runs" / "microstructure" / f"{sym}_full_metrics.joblib"
    ohlcv_path = ROOT / "runs" / "ohlcv_cache" / f"{sym}_1m.joblib"

    if not prem_path.exists() or not micro_path.exists() or not ohlcv_path.exists():
        log.warning("[%s] missing inputs", sym)
        return pd.DataFrame()

    prem = joblib.load(prem_path)[["close"]].rename(columns={"close": "premium"})
    if prem.index.tz is not None:
        prem.index = prem.index.tz_localize(None)

    micro = joblib.load(micro_path)
    if micro.index.tz is not None:
        micro.index = micro.index.tz_localize(None)
    if "open_interest" not in micro.columns:
        log.warning("[%s] no open_interest column", sym)
        return pd.DataFrame()
    oi_5m = micro[["open_interest"]].resample("5min").last().dropna()

    ohlcv = joblib.load(ohlcv_path)
    if ohlcv.index.tz is not None:
        ohlcv.index = ohlcv.index.tz_localize(None)
    # ohlcv 1m -> 5m last close
    close5m = ohlcv["close"].resample("5min").last().to_frame("close5m").dropna()

    df = prem.join(oi_5m, how="inner").join(close5m, how="inner").dropna()

    # z-scores
    df["oi_logret"] = np.log(df["open_interest"]).diff()
    # guard against -inf from log(0)
    df["oi_logret"] = df["oi_logret"].replace([np.inf, -np.inf], np.nan)
    df["oi_z"] = (
        df["oi_logret"] - df["oi_logret"].rolling(ROLL_WINDOW).mean()
    ) / df["oi_logret"].rolling(ROLL_WINDOW).std()

    df["premium_z"] = (
        df["premium"] - df["premium"].rolling(ROLL_WINDOW).mean()
    ) / df["premium"].rolling(ROLL_WINDOW).std()

    # forward returns for each hold horizon (gross, before fee)
    for name, bars in HOLD_BARS.items():
        df[f"fwd_{name}"] = df["close5m"].shift(-bars) / df["close5m"] - 1.0

    df = df.dropna(subset=["oi_z", "premium_z", f"fwd_{FOCUS_HOLD}"])
    df["symbol"] = sym
    return df


def label_triggers(df: pd.DataFrame, z_thr: float) -> pd.Series:
    """Returns +1 (LONG), -1 (SHORT), 0 (no trigger)."""
    long_mask = (df["oi_z"] > z_thr) & (df["premium_z"] < -z_thr)
    short_mask = (df["oi_z"] < -z_thr) & (df["premium_z"] > z_thr)
    out = pd.Series(0, index=df.index, dtype=int)
    out[long_mask] = 1
    out[short_mask] = -1
    return out


def signed_net_return(side: int, fwd_ret: float) -> float:
    """Apply direction and fee."""
    return side * fwd_ret - FEE


def main() -> None:
    log.info("loading 14 syms ...")
    sym_frames: dict[str, pd.DataFrame] = {}
    for sym in SYMS:
        df = load_sym(sym)
        if df.empty:
            continue
        sym_frames[sym] = df
        log.info(
            "[%s] rows=%d range=%s -> %s",
            sym, len(df), df.index.min(), df.index.max(),
        )

    if not sym_frames:
        raise RuntimeError("no symbols loaded")

    # ============================================================
    # Aggregate trigger pass (focus Z=2.0, focus hold=60m)
    # ============================================================
    log.info("computing triggers + net returns at Z=%.1f focus hold=%s",
             Z_THRESHOLD, FOCUS_HOLD)
    fwd_col = f"fwd_{FOCUS_HOLD}"

    trade_records: list[dict] = []          # observed (trigger) trades
    candidate_pool_grossret: list[float] = []  # non-trigger gross returns (universe)
    per_sym_trades: dict[str, list[float]] = {sym: [] for sym in sym_frames}

    for sym, df in sym_frames.items():
        side = label_triggers(df, Z_THRESHOLD)
        is_trig = side != 0

        # observed trades
        trig_df = df.loc[is_trig].copy()
        if not trig_df.empty:
            trig_df["side"] = side[is_trig]
            trig_df["gross_ret"] = trig_df["side"] * trig_df[fwd_col]
            trig_df["net_ret"] = trig_df["gross_ret"] - FEE
            for ts, row in trig_df.iterrows():
                trade_records.append(
                    {
                        "ts": ts,
                        "symbol": sym,
                        "side": int(row["side"]),
                        "oi_z": float(row["oi_z"]),
                        "premium_z": float(row["premium_z"]),
                        "gross_ret": float(row["gross_ret"]),
                        "net_ret": float(row["net_ret"]),
                    }
                )
                per_sym_trades[sym].append(float(row["net_ret"]))

        # candidate pool: random direction × non-trigger fwd_return
        # we use absolute fwd_ret as a sign-agnostic proxy for "what a random trade would earn"
        # but to match the perm semantics (signed trade), we sample sign equally
        # Use signed fwd_ret as-is (LONG direction) for half pool, -fwd_ret for the other half.
        non_trig = df.loc[~is_trig, fwd_col].dropna().values
        if len(non_trig) > 0:
            # Take a random half as LONG (gross = fwd_ret), other half as SHORT (gross = -fwd_ret).
            # This represents what a random direction trade would gross before fee.
            rng = np.random.default_rng(42 + hash(sym) % 1000)
            sign_assign = rng.choice([-1, 1], size=len(non_trig))
            candidate_pool_grossret.extend((sign_assign * non_trig).tolist())

    observed_net = np.array([t["net_ret"] for t in trade_records])
    candidate_pool = np.array(candidate_pool_grossret)
    log.info(
        "observed trades=%d  candidate pool=%d",
        len(observed_net), len(candidate_pool),
    )

    if len(observed_net) < 30:
        raise RuntimeError(
            f"insufficient triggers: {len(observed_net)} < 30 minimum. "
            "Halt R-1; sample density too thin."
        )

    # Stat suite
    log.info("running fee_aware_perm_test (n_perms=1000) ...")
    fee_res = fee_aware_perm_test(
        observed_net_returns=observed_net,
        candidate_pool_returns=candidate_pool,
        fee_per_trade=FEE,
        n_perms=1000,
        rng_seed=42,
    )
    log.info("fee_aware_perm: %s", fee_res)

    log.info("running bootstrap_ci (n_boot=2000, block_size=12) ...")
    ci_res = bootstrap_ci(
        observed_net,
        n_boot=2000,
        block_size=HOLD_BARS[FOCUS_HOLD],  # 12 bars for 60m
        rng_seed=42,
    )
    log.info("bootstrap_ci: %s", ci_res)

    # Three-gate
    gate_a = float(fee_res["signal_t_excess"]) >= 2.0
    gate_b = float(ci_res["ci_lower"]) > 0
    gate_c = float(fee_res["perm_p_two_sided"]) <= 0.10
    three_gate_pass = gate_a and gate_b and gate_c

    # ============================================================
    # Concentration diagnostics (Lesson #16)
    # ============================================================
    obs_df = pd.DataFrame(trade_records)
    obs_df["ts"] = pd.to_datetime(obs_df["ts"])

    # Per-quarter
    obs_df["quarter"] = obs_df["ts"].dt.to_period("Q").astype(str)

    def _t(s: pd.Series) -> float:
        if len(s) < 3 or s.std(ddof=1) == 0:
            return float("nan")
        return float(s.mean() / s.std(ddof=1) * np.sqrt(len(s)))

    per_q = obs_df.groupby("quarter").agg(
        n_trades=("net_ret", "size"),
        mean_bp=("net_ret", lambda s: float(s.mean() * 10000)),
        t_stat=("net_ret", _t),
    ).reset_index()
    per_q_records = per_q.to_dict(orient="records")
    n_q_measurable = int((per_q["n_trades"] >= 10).sum())
    n_q_pos_t = int(
        ((per_q["t_stat"] > 0) & (per_q["n_trades"] >= 10)).sum()
    )
    q_pos_ratio = (n_q_pos_t / n_q_measurable) if n_q_measurable else float("nan")

    # Per-symbol bootstrap CI
    per_sym_records: list[dict] = []
    for sym, sub in obs_df.groupby("symbol"):
        if len(sub) < 10:
            per_sym_records.append(
                {
                    "symbol": sym,
                    "n_trades": int(len(sub)),
                    "mean_bp": float(sub["net_ret"].mean() * 10000) if len(sub) else float("nan"),
                    "ci_lower_bp": float("nan"),
                    "ci_upper_bp": float("nan"),
                    "ci_lower_pos": False,
                    "skip": "n<10",
                }
            )
            continue
        ci = bootstrap_ci(
            sub["net_ret"].values,
            n_boot=2000,
            block_size=1,
            rng_seed=42,
        )
        per_sym_records.append(
            {
                "symbol": sym,
                "n_trades": int(len(sub)),
                "mean_bp": float(sub["net_ret"].mean() * 10000),
                "ci_lower_bp": float(ci["ci_lower"] * 10000),
                "ci_upper_bp": float(ci["ci_upper"] * 10000),
                "ci_lower_pos": bool(ci["ci_lower"] > 0),
                "skip": None,
            }
        )

    n_sym_measurable = sum(1 for r in per_sym_records if r["skip"] is None)
    n_sym_ci_pos = sum(1 for r in per_sym_records if r["ci_lower_pos"])
    sym_ci_pos_ratio = (
        n_sym_ci_pos / n_sym_measurable if n_sym_measurable else float("nan")
    )

    # Concentration Gate (Lesson #16 final spec)
    conc_pass = (
        q_pos_ratio >= 0.5
        and sym_ci_pos_ratio >= 0.30
        and n_sym_ci_pos >= 3
    )

    # Verdict
    if three_gate_pass and conc_pass:
        verdict = "R1_PASS"
    elif three_gate_pass and not conc_pass:
        verdict = "CONCENTRATED_R1_PASS"
    else:
        verdict = "R1_FAIL"

    # ============================================================
    # Hold sweep (5m / 15m / 30m / 60m / 240m), same Z=2.0
    # ============================================================
    log.info("running hold sweep ...")
    hold_rows: list[dict] = []
    for hname, bars in HOLD_BARS.items():
        fwd_c = f"fwd_{hname}"
        obs_list: list[float] = []
        pool_list: list[float] = []
        for sym, df in sym_frames.items():
            if fwd_c not in df.columns:
                continue
            df2 = df.dropna(subset=[fwd_c])
            side = label_triggers(df2, Z_THRESHOLD)
            is_trig = side != 0
            tdf = df2.loc[is_trig]
            if not tdf.empty:
                gross = side[is_trig] * tdf[fwd_c]
                net = gross - FEE
                obs_list.extend(net.values.tolist())
            non_trig = df2.loc[~is_trig, fwd_c].dropna().values
            if len(non_trig) > 0:
                rng = np.random.default_rng(42 + hash(sym + hname) % 1000)
                sa = rng.choice([-1, 1], size=len(non_trig))
                pool_list.extend((sa * non_trig).tolist())
        if len(obs_list) < 10:
            hold_rows.append(
                {
                    "hold": hname,
                    "n_obs": len(obs_list),
                    "mean_bp": float("nan"),
                    "obs_t": float("nan"),
                    "null_mean_t": float("nan"),
                    "signal_t_excess": float("nan"),
                    "perm_p_two_sided": float("nan"),
                    "ci_lower_bp": float("nan"),
                    "ci_upper_bp": float("nan"),
                }
            )
            continue
        fres = fee_aware_perm_test(
            observed_net_returns=np.array(obs_list),
            candidate_pool_returns=np.array(pool_list),
            fee_per_trade=FEE,
            n_perms=500,
            rng_seed=42,
        )
        cres = bootstrap_ci(
            np.array(obs_list),
            n_boot=1000,
            block_size=bars,
            rng_seed=42,
        )
        hold_rows.append(
            {
                "hold": hname,
                "n_obs": len(obs_list),
                "mean_bp": float(np.mean(obs_list) * 10000),
                "obs_t": float(fres["obs_t"]),
                "null_mean_t": float(fres["null_mean_t"]),
                "signal_t_excess": float(fres["signal_t_excess"]),
                "perm_p_two_sided": float(fres["perm_p_two_sided"]),
                "ci_lower_bp": float(cres["ci_lower"] * 10000),
                "ci_upper_bp": float(cres["ci_upper"] * 10000),
            }
        )
    hold_df = pd.DataFrame(hold_rows)
    hold_df.to_csv(OUT_DIR / "r1__hold_sweep.csv", index=False)
    log.info("\n%s", hold_df.to_string(index=False))

    # ============================================================
    # Per-symbol CSV
    # ============================================================
    per_sym_df = pd.DataFrame(per_sym_records)
    per_sym_df.to_csv(OUT_DIR / "r1__per_symbol.csv", index=False)

    # ============================================================
    # Sample density prescreen (Lesson #11)
    # ============================================================
    # universe = sum of df rows across syms
    total_rows = sum(len(df) for df in sym_frames.values())
    expected_trigger_rate = len(observed_net) / total_rows if total_rows else 0.0
    # cells = quarters × directions (~4Q × 2 sides = 8 cells minimum)
    n_quarters = obs_df["quarter"].nunique()
    n_cells = max(n_quarters * 2, 1)
    expected_n_per_cell = len(observed_net) / n_cells

    # ============================================================
    # Assemble metrics
    # ============================================================
    metrics = {
        "paradigm_name": "oi_premium_5m_decoupling",
        "phase": "R-1",
        "type": "E",
        "mechanism": "A_decouple_reversal",
        "hypothesis": (
            "OI 5m z-score vs premium 5m z-score opposite-sign joint event "
            "(|z|>=2 each) -> directional mean-reversal. "
            "LONG: oi_z>+2 AND premium_z<-2. "
            "SHORT: oi_z<-2 AND premium_z>+2."
        ),
        "config": {
            "symbols": list(sym_frames.keys()),
            "n_symbols": len(sym_frames),
            "z_threshold": Z_THRESHOLD,
            "rolling_window_bars": ROLL_WINDOW,
            "focus_hold": FOCUS_HOLD,
            "hold_bars_map": HOLD_BARS,
            "fee_per_trade": FEE,
        },
        "data_window": {
            "earliest": str(min(df.index.min() for df in sym_frames.values())),
            "latest": str(max(df.index.max() for df in sym_frames.values())),
            "total_5m_rows_across_syms": int(total_rows),
        },
        "aggregate_focus_hold": {
            "n_trades": int(len(observed_net)),
            "n_long": int((obs_df["side"] == 1).sum()),
            "n_short": int((obs_df["side"] == -1).sum()),
            "mean_net_bp": float(np.mean(observed_net) * 10000),
            "median_net_bp": float(np.median(observed_net) * 10000),
            "fee_aware_perm": {
                k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                for k, v in fee_res.items()
            },
            "bootstrap_ci_bp": {
                "mean_bp": float(ci_res["mean"] * 10000),
                "ci_lower_bp": float(ci_res["ci_lower"] * 10000),
                "ci_upper_bp": float(ci_res["ci_upper"] * 10000),
                "prob_positive": float(ci_res["prob_positive"]),
                "n": int(ci_res["n"]),
                "block_size": int(ci_res["block_size"]),
            },
        },
        "three_gate": {
            "gate_a_signal_t_excess_ge_2": bool(gate_a),
            "gate_b_ci_lower_gt_0": bool(gate_b),
            "gate_c_perm_p_le_0_10": bool(gate_c),
            "pass": bool(three_gate_pass),
        },
        "concentration": {
            "per_quarter_t_stats": per_q_records,
            "n_quarters_measurable": int(n_q_measurable),
            "n_quarters_pos_t": int(n_q_pos_t),
            "quarter_pos_t_ratio": float(q_pos_ratio) if not np.isnan(q_pos_ratio) else None,
            "per_symbol_bootstrap": per_sym_records,
            "n_symbols_measurable": int(n_sym_measurable),
            "n_symbols_ci_pos": int(n_sym_ci_pos),
            "symbol_ci_pos_ratio": float(sym_ci_pos_ratio) if not np.isnan(sym_ci_pos_ratio) else None,
            "concentration_gate_pass": bool(conc_pass),
        },
        "sample_density_prescreen": {
            "trigger_rate": float(expected_trigger_rate),
            "expected_n_per_cell_quarters_x_sides": float(expected_n_per_cell),
            "cell_floor_30": bool(expected_n_per_cell >= 30),
        },
        "hold_sweep": hold_rows,
        "verdict": verdict,
    }

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    log.info("wrote %s", out_path)

    # Console summary
    print("\n" + "=" * 70)
    print(f"VERDICT: {verdict}")
    print("=" * 70)
    print(f"  trades:        {len(observed_net)} (LONG={metrics['aggregate_focus_hold']['n_long']} SHORT={metrics['aggregate_focus_hold']['n_short']})")
    print(f"  mean_net_bp:   {metrics['aggregate_focus_hold']['mean_net_bp']:+.3f}")
    print(f"  obs_t:         {fee_res['obs_t']:+.3f}")
    print(f"  null_mean_t:   {fee_res['null_mean_t']:+.3f}  (fee floor drift)")
    print(f"  signal_t_excess: {fee_res['signal_t_excess']:+.3f}  (>=2.0 ?)")
    print(f"  perm_p_two:    {fee_res['perm_p_two_sided']:.4f}  (<=0.10 ?)")
    print(f"  ci_lower_bp:   {ci_res['ci_lower']*10000:+.3f}  (>0 ?)")
    print(f"  ci_upper_bp:   {ci_res['ci_upper']*10000:+.3f}")
    print(f"  three-gate: A={gate_a} B={gate_b} C={gate_c}  PASS={three_gate_pass}")
    print()
    print(f"  quarters measured: {n_q_measurable}  pos-t: {n_q_pos_t}  ratio: {q_pos_ratio:.3f}  (>=0.5 ?)")
    print(f"  syms measured:     {n_sym_measurable}  ci_pos: {n_sym_ci_pos}  ratio: {sym_ci_pos_ratio:.3f}  (>=0.30 & n>=3 ?)")
    print(f"  concentration gate: PASS={conc_pass}")
    print()
    print(f"  sample density: trigger_rate={expected_trigger_rate:.4%}  exp_n_per_cell={expected_n_per_cell:.1f}  (>=30 ?)")


if __name__ == "__main__":
    main()
