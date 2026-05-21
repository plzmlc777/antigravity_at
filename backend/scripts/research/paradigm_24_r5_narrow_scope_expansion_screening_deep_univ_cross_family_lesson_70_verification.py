#!/usr/bin/env python3
"""paradigm 175 — paradigm 24 R-5 narrow-scope expansion screening (cross-family Lesson #70 verification).

Track classification: **R-5 expansion screening** (paradigm 173/174 precedent)
- paradigm 24 R-5 LIVE premium_index_zscore survivor (DOGE/SOL/LDO seeded 2026-05-06)
- Cohort expansion candidates against premium joblib substrate (17 syms × 2.19yr)
- Cross-family Lesson #70 verification: does the funding-family R-5 expansion null
  result generalize to premium_index paradigm 24?
- NOT a new paradigm dispatch - paradigm counter does NOT increase

Canonical paradigm 24 R-5 spec (from runs/research_track/premium_index_zscore/gate_eval__3_seeds.md):
  - zwin     = 30  (30-day rolling premium z)
  - entry_z  = 2.0
  - hold_days = 5
  - sl_pct   = 0.05
  - fee_rate = 0.0004 per side (8 bp round-trip)
  - mode     = follow (NOT fade) - premium high → LONG, premium low → SHORT
  - capital  = 1,000,000

Universe (17 syms, R-5 seeded DOGE/SOL/LDO excluded):
  Deep cohort (paradigm 173 minus SOL): BTC ETH LINK ADA DOT XRP BNB BCH LTC (9)
  Mid-cap cohort (paradigm 174 minus DOGE/LDO): UNI ETC AVAX NEAR FIL WLD JUP PYTH (8)

Per-sym screening logic (paradigm 173/174 precedent):
  1. Pull 1m ohlcv from DB, resample 1d UTC last → daily close series.
  2. Load premium joblib → daily premium close series.
  3. Inner-join, compute 30d rolling z on premium.
  4. Simulate paradigm 24 follow mode on **full window** (no train/test split,
     since R-5 expansion screening evaluates 자격 of NEW syms with same spec
     on independent OOS window).
  5. Three-gate evaluation: sigex >= 2.0 AND ci_lower > 0 AND perm_p <= 0.10
  6. Life-changing 4-dim gate: trd/yr >= 12, edge >= +2%, util >= 30%, sharpe >= 1.5
  7. R-5 expansion eligible candidates = (three-gate PASS) AND (4-dim PASS)
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p24_r5_expansion_xfamily")

SLUG = "paradigm_24_r5_narrow_scope_expansion_screening_deep_univ_cross_family_lesson_70_verification"
OUT_DIR = ROOT / "runs" / "research_track" / SLUG
PREMIUM_DIR = ROOT / "runs" / "premium_index"

# 17 syms (R-5 seeded DOGE/SOL/LDO excluded)
SCREENING_UNIVERSE = [
    # Deep cohort (paradigm 173 minus SOL)
    "BTCUSDT", "ETHUSDT", "LINKUSDT", "ADAUSDT", "DOTUSDT",
    "XRPUSDT", "BNBUSDT", "BCHUSDT", "LTCUSDT",
    # Mid-cap cohort (paradigm 174 minus DOGE/LDO)
    "UNIUSDT", "ETCUSDT", "AVAXUSDT", "NEARUSDT", "FILUSDT",
    "WLDUSDT", "JUPUSDT", "PYTHUSDT",
]

# Canonical paradigm 24 R-5 follow_z2.0_h5 spec
SPEC = {
    "zwin": 30,
    "entry_z": 2.0,
    "hold_days": 5,
    "sl_pct": 0.05,
    "fee_rate": 0.0004,  # per side
    "capital": 1_000_000.0,
    "mode": "follow",
}

FEE_ROUND_TRIP = 2 * SPEC["fee_rate"]  # 0.0008


def load_close_1d(symbol: str) -> pd.Series:
    """Load 1m close from DB, resample to 1d UTC last."""
    s = SessionLocal()
    try:
        df = pd.read_sql(
            text("""
                SELECT timestamp AS ts, close
                FROM ohlcv WHERE symbol=:sym AND time_frame='1m'
                ORDER BY timestamp
            """),
            s.connection(),
            params={"sym": symbol},
            parse_dates=["ts"],
        )
    finally:
        s.close()
    if df.empty:
        raise ValueError(f"No 1m ohlcv for {symbol}")
    series = df.set_index("ts")["close"].astype(float)
    daily = series.resample("1D", label="right", closed="right").last().dropna()
    daily.index = daily.index.normalize()
    return daily


def load_premium_1d(symbol: str) -> pd.Series:
    p = PREMIUM_DIR / f"{symbol}_premium.joblib"
    if not p.exists():
        raise FileNotFoundError(f"No premium joblib for {symbol}: {p}")
    df = joblib.load(p)
    if "close" not in df.columns:
        raise ValueError(f"{symbol} premium joblib missing close column")
    s = df["close"].astype(float).copy()
    s.index = pd.to_datetime(s.index).normalize()
    s = s.sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s


def simulate_p24_follow(close: pd.Series, premium: pd.Series, *,
                        zwin: int, entry_z: float, hold_days: int,
                        sl_pct: float, fee_rate: float, capital: float,
                        mode: str = "follow",
                        ) -> dict:
    """Replicate paradigm 24 R-5 follow_z2.0_h5 spec on **full window** (R-5 expansion screening)."""
    df = pd.concat({"close": close, "premium": premium}, axis=1, join="inner").dropna()
    df["prem_z"] = (df["premium"] - df["premium"].rolling(zwin).mean()) / df["premium"].rolling(zwin).std()
    df = df.dropna(subset=["prem_z"])

    n = len(df)
    if n < 100:
        return {"error": f"too few bars ({n})", "n_trades": 0, "trades": []}

    # **R-5 expansion screening uses full window** (paradigm 173/174 pattern)
    test = df.copy()

    equity = capital
    equity_curve = [(test.index[0], equity)]
    trades: list[dict] = []
    in_pos = False
    side = 0
    entry_px = 0.0
    bars_held = 0
    entry_ts = ""
    target_hold = 0
    entry_z_val = 0.0
    n_long = 0
    n_short = 0

    for i in range(1, len(test)):
        ts = test.index[i]
        px = float(test["close"].iloc[i])
        if in_pos:
            bars_held += 1
            price_pnl = side * (px - entry_px) / entry_px
            unrealized = price_pnl
            exit_reason = None
            if unrealized < -sl_pct:
                exit_reason = "sl"
            elif bars_held >= target_hold:
                exit_reason = "time"
            if exit_reason:
                gross_pct = unrealized  # for life-changing edge
                ret_pct = unrealized - 2 * fee_rate
                equity *= (1 + ret_pct)
                trades.append({
                    "entry_ts": entry_ts, "exit_ts": str(ts),
                    "side": side, "entry_z": entry_z_val,
                    "gross_pct": gross_pct,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False
                side = 0
                bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            pz = float(row["prem_z"])
            if math.isnan(pz):
                equity_curve.append((ts, equity))
                continue
            if abs(pz) > entry_z:
                if mode == "fade":
                    side = -1 if pz > 0 else 1
                else:  # follow
                    side = 1 if pz > 0 else -1
                if side > 0:
                    n_long += 1
                else:
                    n_short += 1
                in_pos = True
                entry_px = px
                entry_ts = str(ts)
                entry_z_val = pz
                bars_held = 0
                target_hold = hold_days
        equity_curve.append((ts, equity))

    bh_pct = (test["close"].iloc[-1] / test["close"].iloc[0]) - 1
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
        oos_seconds = (test.index[-1] - test.index[0]).total_seconds()
        trades_per_year = (
            len(trades) / oos_seconds * 31536000.0 if oos_seconds > 0 else 0
        )
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
        gross_mean_pct = float(gross_rs.mean() * 100)
        net_mean_pct = float(mu * 100)
        median_bars_held = float(np.median(bars_arr))
        total_bars_in_pos = float(bars_arr.sum())
        total_bars_window = float(len(df))
        capital_util_pct = total_bars_in_pos / total_bars_window * 100
    else:
        sharpe_ann = win_rate_pct = profit_factor = 0.0
        gross_mean_pct = net_mean_pct = 0.0
        median_bars_held = 0.0
        trades_per_year = 0.0
        capital_util_pct = 0.0

    oos_days = int((test.index[-1] - test.index[0]).total_seconds() // 86400)
    exit_reasons: dict[str, int] = {}
    for tr in trades:
        exit_reasons[tr["exit_reason"]] = exit_reasons.get(tr["exit_reason"], 0) + 1

    return {
        "n_trades": len(trades),
        "n_long_entries": n_long,
        "n_short_entries": n_short,
        "alpha_pct": round(alpha_pct, 2),
        "total_return_pct": round(total_return_pct * 100, 2),
        "buy_hold_pct": round(bh_pct * 100, 2),
        "sharpe_ann": round(sharpe_ann, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": (
            round(profit_factor, 3) if profit_factor != float("inf") else "inf"
        ),
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
    """Three-gate (sigex/ci/perm_p) + life-changing 4-dim eval per-sym (paradigm 173/174 pattern)."""
    trades = sim_result.get("trades", [])
    n_trades = len(trades)

    if n_trades < 5:
        return {
            "three_gate_pass": False,
            "life_changing_pass": False,
            "reason": f"insufficient_trades n={n_trades}",
            "sigex": float("nan"),
            "obs_t": float("nan"),
            "null_mean_t": float("nan"),
            "ci_lower_bp": float("nan"),
            "ci_upper_bp": float("nan"),
            "ci_prob_positive": float("nan"),
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

    # fee-aware perm null (paradigm 173/174 pattern: replicate observed gross 5x for n_pool >= 2*n_obs)
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

    log.info("paradigm 175 — paradigm 24 R-5 narrow-scope expansion screening (cross-family Lesson #70)")
    log.info("Spec: %s", SPEC)
    log.info("Universe (17 syms): %s", SCREENING_UNIVERSE)

    per_sym_rows = []
    for sym in SCREENING_UNIVERSE:
        try:
            close = load_close_1d(sym)
            premium = load_premium_1d(sym)
            log.info("%s close: %d days (%s → %s), premium: %d days (%s → %s)",
                     sym, len(close), close.index[0].date(), close.index[-1].date(),
                     len(premium), premium.index[0].date(), premium.index[-1].date())
            sim = simulate_p24_follow(
                close, premium,
                zwin=SPEC["zwin"],
                entry_z=SPEC["entry_z"],
                hold_days=SPEC["hold_days"],
                sl_pct=SPEC["sl_pct"],
                fee_rate=SPEC["fee_rate"],
                capital=SPEC["capital"],
                mode=SPEC["mode"],
            )
            gate = evaluate_three_gate_and_4dim(sim)

            row = {
                "symbol": sym,
                "n_trades": sim["n_trades"],
                "n_long_entries": sim.get("n_long_entries", 0),
                "n_short_entries": sim.get("n_short_entries", 0),
                "alpha_pct": sim["alpha_pct"],
                "total_return_pct": sim.get("total_return_pct", 0.0),
                "buy_hold_pct": sim.get("buy_hold_pct", 0.0),
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
                "%s | trd=%d sigex=%.2f ci_lo=%.1fbp perm_p=%.3f 3gate=%s | "
                "trd/yr=%.1f edge=%.2f%% util=%.1f%% sh=%.2f 4dim=%s | ELIG=%s",
                sym, sim["n_trades"],
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

    # Cohort split for diagnostics
    deep_set = {"BTCUSDT", "ETHUSDT", "LINKUSDT", "ADAUSDT", "DOTUSDT",
                "XRPUSDT", "BNBUSDT", "BCHUSDT", "LTCUSDT"}
    deep_eligible = [r["symbol"] for r in eligible if r["symbol"] in deep_set]
    midcap_eligible = [r["symbol"] for r in eligible if r["symbol"] not in deep_set]

    agg = {
        "track": "R-5 expansion screening (paradigm 24 premium_index_zscore follow_z2.0_h5) — cross-family Lesson #70 verification",
        "spec": SPEC,
        "universe": SCREENING_UNIVERSE,
        "n_syms_evaluated": len(per_sym_rows),
        "n_three_gate_pass": int(sum(1 for r in per_sym_rows if r["three_gate_pass"])),
        "n_life_changing_pass": int(sum(1 for r in per_sym_rows if r["life_changing_pass"])),
        "n_r5_expansion_eligible": len(eligible),
        "r5_expansion_eligible_syms": [r["symbol"] for r in eligible],
        "three_gate_only_syms": [r["symbol"] for r in three_gate_only],
        "life_changing_only_syms": [r["symbol"] for r in four_dim_only],
        "lesson_70_cross_family_dogfood_verdict": (
            "CONFIRMED_UNIVERSAL_PROPERTY_3RD_DOGFOOD" if len(eligible) == 0
            else "FUNDING_FAMILY_SPECIFIC_REFUTED_BY_PREMIUM_FAMILY"
        ),
        "cohort_split": {
            "deep_eligible": deep_eligible,
            "midcap_eligible": midcap_eligible,
        },
    }

    meta = {
        "slug": SLUG,
        "phase": "R-5_EXPANSION_SCREENING",
        "track_classification": "R-5 LIVE survivor cohort expansion candidate evaluation (cross-family Lesson #70 verification)",
        "paradigm_counter": "not_increased (R-5 expansion screening, not new paradigm)",
        "source_paradigm": "paradigm 24 R-5 LIVE premium_index_zscore (DOGE/SOL/LDO seeded 2026-05-06)",
        "spec_source": "runs/research_track/premium_index_zscore/gate_eval__3_seeds.md (follow_z2.0_h5)",
        "evaluated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "aggregate": agg,
        "per_symbol": per_sym_rows,
    }
    out_meta = OUT_DIR / "screening_metrics.json"
    out_meta.write_text(json.dumps(meta, indent=2, default=str))
    log.info("Wrote %s", out_meta)

    print("\n=== R-5 expansion screening verdict (paradigm 175 — cross-family Lesson #70) ===")
    print(json.dumps(agg, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
