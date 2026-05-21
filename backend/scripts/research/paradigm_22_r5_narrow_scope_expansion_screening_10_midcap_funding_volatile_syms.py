#!/usr/bin/env python3
"""paradigm 22 R-5 narrow-scope expansion screening — 10 mid-cap funding-volatile syms.

Track classification: **R-5 expansion screening** (Option α — Lesson #70 candidate 2nd dogfood)
- paradigm 22 R-5 LIVE funding_carry survivor (HBARUSDT/AXSUSDT/COMPUSDT seeded)
- Cohort expansion candidates against mid-cap funding-volatile universe
  (DOGE/LDO/UNI/ETC/AVAX/NEAR/FIL/WLD/JUP/PYTH × 2.25yr)
- NOT a new paradigm dispatch — paradigm counter does NOT increase
- Lesson #70 candidate 2nd dogfood (1st = paradigm 173 deep syms 0/10 eligible)

Canonical paradigm 22 R-5 v4 spec (from paper_seed_proposal__{HBAR,AXS,COMP}USDT.json):
  - lookback_funding_periods = 30 (30 * cycle = 10d at 8h cycle, 5d at 4h cycle)
  - entry_z                  = 2.5
  - exit_z                   = 0.5
  - max_hold_funding_periods = 7 (7*cycle = 56h at 8h, 28h at 4h)
  - sl_pct                   = 0.03
  - fee_rate                 = 0.0004 per side (8 bp round-trip)
  - mode                     = mean-reversion (z>+2.5 SHORT / z<-2.5 LONG)

Per-sym screening logic identical to paradigm 173 (same 3-gate + life-changing 4-dim).
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p22_r5_midcap_expansion")

SLUG = "paradigm_22_r5_narrow_scope_expansion_screening_10_midcap_funding_volatile_syms"
OUT_DIR = ROOT / "runs" / "research_track" / SLUG

# Mid-cap funding-volatile cohort (Lesson #70 candidate 2nd dogfood)
SCREENING_UNIVERSE = [
    "DOGEUSDT", "LDOUSDT", "UNIUSDT", "ETCUSDT", "AVAXUSDT",
    "NEARUSDT", "FILUSDT", "WLDUSDT", "JUPUSDT", "PYTHUSDT",
]

# Canonical paradigm 22 R-5 v4 spec
SPEC = {
    "lookback_funding_periods": 30,
    "entry_z": 2.5,
    "exit_z": 0.5,
    "max_hold_funding_periods": 7,
    "sl_pct": 0.03,
    "fee_rate": 0.0004,  # per side
    "capital": 1_000_000.0,
}

FEE_ROUND_TRIP = 2 * SPEC["fee_rate"]


def load_funding(symbol: str) -> pd.DataFrame:
    s = SessionLocal()
    try:
        df = pd.read_sql(
            text("""
                SELECT funding_time AS ts, funding_rate, mark_price
                FROM binance_funding_rate WHERE symbol=:sym
                ORDER BY funding_time
            """),
            s.connection(),
            params={"sym": symbol},
            parse_dates=["ts"],
        )
    finally:
        s.close()
    if df.empty:
        return df
    df = df.drop_duplicates(subset="ts").set_index("ts")
    df["funding_rate"] = df["funding_rate"].astype(float)
    df["mark_price"] = df["mark_price"].astype(float)
    return df


def detect_cycle_hours(df: pd.DataFrame) -> float:
    diffs = df.index.to_series().diff().dt.total_seconds() / 3600.0
    return float(diffs.median())


def simulate_v4(df: pd.DataFrame, *, lookback: int, entry_z: float, exit_z: float,
                max_hold: int, sl_pct: float, fee_rate: float, capital: float
                ) -> dict:
    df = df.copy()
    df["mean_lb"] = df["funding_rate"].rolling(lookback).mean()
    df["std_lb"] = df["funding_rate"].rolling(lookback).std()
    df["z"] = (df["funding_rate"] - df["mean_lb"]) / df["std_lb"]
    df = df.dropna(subset=["z"])

    if len(df) < 50:
        return {"n_trades": 0, "error": "insufficient_post_warmup_n", "n_periods": len(df), "trades": []}

    prices = df["mark_price"].values
    fundings = df["funding_rate"].values
    zs = df["z"].values
    timestamps = df.index

    equity = capital
    equity_curve = [(timestamps[0], equity)]
    trades: list[dict] = []
    in_pos = False
    side = 0
    entry_px = 0.0
    bars_held = 0
    accum_funding = 0.0
    entry_ts = ""
    entry_z_value = 0.0

    prev_z = zs[0]
    for i in range(1, len(df)):
        px = float(prices[i])
        z = float(zs[i])
        t = timestamps[i]
        funding_now = float(fundings[i])

        if in_pos:
            bars_held += 1
            accum_funding += -side * funding_now
            price_pnl = side * (px - entry_px) / entry_px
            unrealized = price_pnl + accum_funding

            exit_reason = None
            if abs(z) < exit_z:
                exit_reason = "mean"
            elif unrealized < -sl_pct:
                exit_reason = "sl"
            elif bars_held >= max_hold:
                exit_reason = "time"

            if exit_reason:
                ret_pct = unrealized - 2 * fee_rate
                gross_pct = unrealized
                equity *= (1 + ret_pct)
                trades.append({
                    "entry_ts": str(entry_ts),
                    "exit_ts": str(t),
                    "side": side,
                    "entry_z": entry_z_value,
                    "exit_z": z,
                    "price_pnl": round(price_pnl, 5),
                    "accum_funding": round(accum_funding, 5),
                    "gross_pct": gross_pct,
                    "return_pct": ret_pct,
                    "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False
                side = 0
                bars_held = 0
                accum_funding = 0.0

        elif not in_pos and not math.isnan(z):
            if prev_z <= entry_z and z > entry_z:
                in_pos = True
                side = -1
                entry_px = px
                entry_ts = t
                entry_z_value = z
                bars_held = 0
                accum_funding = 0.0
            elif prev_z >= -entry_z and z < -entry_z:
                in_pos = True
                side = 1
                entry_px = px
                entry_ts = t
                entry_z_value = z
                bars_held = 0
                accum_funding = 0.0

        if not math.isnan(z):
            prev_z = z
        equity_curve.append((t, equity))

    bh_pct = (prices[-1] / prices[0]) - 1
    total_return_pct = (equity / capital) - 1
    alpha_pct = (total_return_pct - bh_pct) * 100

    eq = np.array([e for _, e in equity_curve])
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    max_dd_pct = float(dd.max() * 100) if len(dd) else 0.0

    if trades:
        rs = np.array([t["return_pct"] for t in trades])
        gross_rs = np.array([t["gross_pct"] for t in trades])
        bars_arr = np.array([t["bars_held"] for t in trades])
        mu = rs.mean()
        sd = rs.std(ddof=1) if len(rs) > 1 else 0.0
        oos_seconds = (timestamps[-1] - timestamps[0]).total_seconds()
        trades_per_year = (len(trades) / oos_seconds * 31536000.0) if oos_seconds > 0 else 0
        sharpe_ann = (
            float(mu / sd * math.sqrt(max(trades_per_year, 1))) if sd > 0 else 0.0
        )
        wins = rs[rs > 0]
        losses = rs[rs < 0]
        win_rate_pct = float(len(wins) / len(rs) * 100)
        gw = float(wins.sum()) if len(wins) else 0.0
        gl = float(-losses.sum()) if len(losses) else 0.0
        profit_factor = (
            float(gw / gl) if gl > 0 else (float("inf") if gw > 0 else 0.0)
        )
        avg_funding_per_trade = float(np.mean([t["accum_funding"] for t in trades]) * 100)
        gross_mean_pct = float(gross_rs.mean() * 100)
        net_mean_pct = float(mu * 100)
        median_bars_held = float(np.median(bars_arr))
        total_bars_in_pos = float(bars_arr.sum())
        total_bars_window = float(len(df))
        capital_util_pct = total_bars_in_pos / total_bars_window * 100
    else:
        sharpe_ann = win_rate_pct = profit_factor = 0.0
        avg_funding_per_trade = 0.0
        gross_mean_pct = net_mean_pct = 0.0
        median_bars_held = 0.0
        trades_per_year = 0.0
        capital_util_pct = 0.0

    oos_days = int((timestamps[-1] - timestamps[0]).total_seconds() // 86400)
    exit_reasons: dict[str, int] = {}
    for tr in trades:
        exit_reasons[tr["exit_reason"]] = exit_reasons.get(tr["exit_reason"], 0) + 1

    return {
        "n_trades": len(trades),
        "alpha_pct": round(alpha_pct, 2),
        "total_return_pct": round(total_return_pct * 100, 2),
        "buy_hold_pct": round(bh_pct * 100, 2),
        "sharpe_ann": round(sharpe_ann, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": (
            round(profit_factor, 3) if profit_factor != float("inf") else "inf"
        ),
        "avg_funding_per_trade_pct": round(avg_funding_per_trade, 4),
        "gross_mean_pct_per_trade": round(gross_mean_pct, 4),
        "net_mean_pct_per_trade": round(net_mean_pct, 4),
        "median_bars_held": median_bars_held,
        "trades_per_year": round(trades_per_year, 2),
        "capital_util_pct": round(capital_util_pct, 2),
        "oos_days": oos_days,
        "exit_reasons": exit_reasons,
        "trades": trades,
    }


def evaluate_three_gate_and_4dim(sim_result: dict) -> dict:
    trades = sim_result.get("trades", [])
    n_trades = len(trades)

    if n_trades < 5:
        return {
            "three_gate_pass": False,
            "life_changing_pass": False,
            "reason": f"insufficient_trades n={n_trades}",
            "sigex": float("nan"),
            "ci_lower_bp": float("nan"),
            "ci_upper_bp": float("nan"),
            "perm_p_two_sided": float("nan"),
            "trades_per_year": sim_result.get("trades_per_year", 0.0),
            "edge_pct_per_trade": sim_result.get("gross_mean_pct_per_trade", 0.0),
            "capital_util_pct": sim_result.get("capital_util_pct", 0.0),
            "sharpe_ann": sim_result.get("sharpe_ann", 0.0),
            "n_trades": n_trades,
        }

    obs_net = np.array([t["return_pct"] for t in trades], dtype=float)
    obs_gross = np.array([t["gross_pct"] for t in trades], dtype=float)

    obs_mean = float(obs_net.mean())
    n = len(obs_net)
    sd = obs_net.std(ddof=1) if n > 1 else 0.0
    obs_t = float(obs_mean / sd * np.sqrt(n)) if sd > 0 else 0.0

    ci = bootstrap_ci(obs_net, n_boot=2000, block_size=1)

    pool = np.concatenate([obs_gross] * 5)
    perm = fee_aware_perm_test(
        observed_net_returns=obs_net,
        candidate_pool_returns=pool,
        fee_per_trade=FEE_ROUND_TRIP,
        n_perms=1000,
    )
    sigex = perm.get("signal_t_excess", float("nan"))
    perm_p = perm.get("perm_p_two_sided", float("nan"))

    ci_lower_bp = ci["ci_lower"] * 10000
    ci_upper_bp = ci["ci_upper"] * 10000

    three_gate_pass = (
        (not math.isnan(sigex)) and sigex >= 2.0
        and (not math.isnan(ci_lower_bp)) and ci_lower_bp > 0
        and (not math.isnan(perm_p)) and perm_p <= 0.10
    )

    trades_per_year = sim_result.get("trades_per_year", 0.0)
    edge_pct = sim_result.get("gross_mean_pct_per_trade", 0.0)
    capital_util = sim_result.get("capital_util_pct", 0.0)
    sharpe = sim_result.get("sharpe_ann", 0.0)

    life_changing_pass = (
        trades_per_year >= 12.0
        and edge_pct >= 2.0
        and capital_util >= 30.0
        and sharpe >= 1.5
    )

    return {
        "three_gate_pass": bool(three_gate_pass),
        "life_changing_pass": bool(life_changing_pass),
        "sigex": round(sigex, 3) if not math.isnan(sigex) else float("nan"),
        "obs_t": round(obs_t, 3),
        "null_mean_t": round(perm.get("null_mean_t", float("nan")), 3),
        "ci_lower_bp": round(ci_lower_bp, 2),
        "ci_upper_bp": round(ci_upper_bp, 2),
        "ci_prob_positive": round(ci.get("prob_positive", float("nan")), 3),
        "perm_p_two_sided": round(perm_p, 4) if not math.isnan(perm_p) else float("nan"),
        "trades_per_year": round(trades_per_year, 2),
        "edge_pct_per_trade": round(edge_pct, 4),
        "capital_util_pct": round(capital_util, 2),
        "sharpe_ann": round(sharpe, 3),
        "n_trades": n_trades,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("paradigm 22 R-5 narrow-scope expansion screening — 10 mid-cap funding-volatile syms")
    log.info("Spec: %s", SPEC)
    log.info("Universe: %s", SCREENING_UNIVERSE)

    per_sym_rows = []
    for sym in SCREENING_UNIVERSE:
        try:
            df = load_funding(sym)
            if df.empty:
                log.warning("%s: no funding rows; skipping", sym)
                continue
            cycle_hrs = detect_cycle_hours(df)
            log.info("%s: %d periods (%s -> %s) cycle=%.1fh",
                     sym, len(df), df.index[0], df.index[-1], cycle_hrs)
            sim = simulate_v4(
                df,
                lookback=SPEC["lookback_funding_periods"],
                entry_z=SPEC["entry_z"],
                exit_z=SPEC["exit_z"],
                max_hold=SPEC["max_hold_funding_periods"],
                sl_pct=SPEC["sl_pct"],
                fee_rate=SPEC["fee_rate"],
                capital=SPEC["capital"],
            )
            gate = evaluate_three_gate_and_4dim(sim)

            row = {
                "symbol": sym,
                "cycle_hours": cycle_hrs,
                "n_periods": int(len(df)),
                "n_trades": sim["n_trades"],
                "alpha_pct": sim["alpha_pct"],
                "sharpe_ann": sim["sharpe_ann"],
                "max_dd_pct": sim["max_dd_pct"],
                "win_rate_pct": sim["win_rate_pct"],
                "profit_factor": sim["profit_factor"],
                "trades_per_year": sim["trades_per_year"],
                "gross_mean_pct_per_trade": sim["gross_mean_pct_per_trade"],
                "net_mean_pct_per_trade": sim["net_mean_pct_per_trade"],
                "median_bars_held": sim["median_bars_held"],
                "capital_util_pct": sim["capital_util_pct"],
                "oos_days": sim["oos_days"],
                "exit_reasons": sim.get("exit_reasons", {}),
                "sigex": gate["sigex"],
                "obs_t": gate.get("obs_t", float("nan")),
                "null_mean_t": gate.get("null_mean_t", float("nan")),
                "ci_lower_bp": gate["ci_lower_bp"],
                "ci_upper_bp": gate["ci_upper_bp"],
                "ci_prob_positive": gate["ci_prob_positive"],
                "perm_p_two_sided": gate["perm_p_two_sided"],
                "three_gate_pass": gate["three_gate_pass"],
                "life_changing_pass": gate["life_changing_pass"],
                "edge_pct_per_trade_life_changing_2pct": gate["edge_pct_per_trade"],
                "capital_util_pct_life_changing_30pct": gate["capital_util_pct"],
                "trades_per_year_life_changing_12": gate["trades_per_year"],
                "sharpe_ann_life_changing_1p5": gate["sharpe_ann"],
                "R5_EXPANSION_ELIGIBLE": bool(
                    gate["three_gate_pass"] and gate["life_changing_pass"]
                ),
            }
            per_sym_rows.append(row)
            log.info(
                "%s [cycle=%.0fh] trades=%d sigex=%.2f ci_lo_bp=%.1f perm_p=%.3f 3gate=%s | "
                "trd/yr=%.1f edge=%.2f%% util=%.1f%% sh=%.2f 4dim=%s | ELIG=%s",
                sym, cycle_hrs, sim["n_trades"],
                gate["sigex"] if not math.isnan(gate["sigex"]) else 0.0,
                gate["ci_lower_bp"] if not math.isnan(gate["ci_lower_bp"]) else 0.0,
                gate["perm_p_two_sided"] if not math.isnan(gate["perm_p_two_sided"]) else 1.0,
                "PASS" if gate["three_gate_pass"] else "FAIL",
                gate["trades_per_year"],
                gate["edge_pct_per_trade"],
                gate["capital_util_pct"],
                gate["sharpe_ann"],
                "PASS" if gate["life_changing_pass"] else "FAIL",
                "YES" if (gate["three_gate_pass"] and gate["life_changing_pass"]) else "NO",
            )
        except Exception:
            log.exception("Failed for %s", sym)

    df_out = pd.DataFrame(per_sym_rows)
    out_csv = OUT_DIR / "per_symbol_screening.csv"
    df_out.to_csv(out_csv, index=False)
    log.info("Wrote %s", out_csv)

    eligible = [r for r in per_sym_rows if r["R5_EXPANSION_ELIGIBLE"]]
    three_gate_only = [r for r in per_sym_rows if r["three_gate_pass"] and not r["life_changing_pass"]]
    four_dim_only = [r for r in per_sym_rows if r["life_changing_pass"] and not r["three_gate_pass"]]

    agg = {
        "track": "R-5 expansion screening (paradigm 22 funding_carry v4, mid-cap funding-volatile cohort)",
        "spec": SPEC,
        "universe": SCREENING_UNIVERSE,
        "n_syms_evaluated": len(per_sym_rows),
        "n_three_gate_pass": int(sum(1 for r in per_sym_rows if r["three_gate_pass"])),
        "n_life_changing_pass": int(sum(1 for r in per_sym_rows if r["life_changing_pass"])),
        "n_r5_expansion_eligible": len(eligible),
        "r5_expansion_eligible_syms": [r["symbol"] for r in eligible],
        "three_gate_only_syms": [r["symbol"] for r in three_gate_only],
        "life_changing_only_syms": [r["symbol"] for r in four_dim_only],
        "lesson_70_candidate_2nd_dogfood_verdict": (
            "CONFIRMED_NARROW_COHORT_ALPHA_NON_TRANSFERABLE"
            if len(eligible) == 0 else
            "PARTIAL_REFUTATION_MID_CAP_TRANSFERABILITY"
        ),
    }

    meta = {
        "slug": SLUG,
        "phase": "R-5_EXPANSION_SCREENING",
        "track_classification": "R-5 LIVE survivor cohort expansion candidate evaluation (mid-cap)",
        "paradigm_counter": "not_increased (R-5 expansion screening, not new paradigm)",
        "evaluated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "aggregate": agg,
        "per_symbol": per_sym_rows,
    }
    out_meta = OUT_DIR / "screening_metrics.json"
    out_meta.write_text(json.dumps(meta, indent=2, default=str))
    log.info("Wrote %s", out_meta)

    print("\n=== R-5 expansion screening verdict (mid-cap cohort) ===")
    print(json.dumps(agg, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
