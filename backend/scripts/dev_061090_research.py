"""Dev research harness for 061090 (세나테크) single-stock strategy discovery.

Loads 1m OHLCV from DB, resamples per strategy TIMEFRAME, runs a basket of
candidate strategies over: FULL window, TEST-half (second 50%), and N walk-forward
time folds. Reports return / BH / alpha / sharpe / maxDD / winRate / PF / trades.

Read-only on DB. Not wired into prod; lives under scripts/ for ad-hoc research.

Usage:
    cd backend && source venv/bin/activate
    python -m scripts.dev_061090_research --candidates momentum
    python -m scripts.dev_061090_research --candidates s8_supertrend,s19_ema_cross
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import math
import pkgutil
from typing import Any, Dict, List, Optional, Type

import numpy as np

from app.db.session import SessionLocal
from app.kr_strategy_pool import strategies as strat_pkg
from app.kr_strategy_pool.base import KrStrategyBase
from app.kr_strategy_pool.data_utils import resample_ohlcv
from app.kr_strategy_pool.tournament import TIMEFRAME_TO_FREQ
from app.core.kr_backtest_engine import KrBacktestEngine

SYMBOL = "061090"
INITIAL_CAPITAL = 10_000_000


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_feed_1m(symbol: str) -> List[Dict[str, Any]]:
    """Load all 1m OHLCV bars for `symbol` from DB, ordered by timestamp."""
    from sqlalchemy import text

    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT timestamp, open, high, low, close, volume "
                "FROM ohlcv WHERE symbol = :s AND time_frame = '1m' "
                "ORDER BY timestamp ASC"
            ),
            {"s": symbol},
        ).fetchall()
    finally:
        db.close()
    feed = []
    for ts, o, h, l, c, v in rows:
        feed.append(
            {
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ts, "strftime") else str(ts),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": float(v),
            }
        )
    return feed


# ---------------------------------------------------------------------------
# Strategy discovery
# ---------------------------------------------------------------------------
def discover_strategies() -> Dict[str, Type[KrStrategyBase]]:
    """Import every module in strategies/ and collect KrStrategyBase subclasses."""
    out: Dict[str, Type[KrStrategyBase]] = {}
    for mod in pkgutil.iter_modules(strat_pkg.__path__):
        try:
            m = importlib.import_module(f"app.kr_strategy_pool.strategies.{mod.name}")
        except Exception:
            continue
        for _, obj in inspect.getmembers(m, inspect.isclass):
            if issubclass(obj, KrStrategyBase) and obj is not KrStrategyBase:
                nm = getattr(obj, "name", None)
                if nm and nm != "base":
                    out[nm] = obj
    return out


# Momentum / trend / breakout family (long-bias, follows strength)
MOMENTUM_NAMES = [
    "s8_supertrend",
    "s19_ema_cross",
    "s7_macd_cross",
    "s9_volume_spike",
    "s13_last_hour_momentum",
    "s26_open_drive",
    "s12_closing_range_breakout",
    "s15_inside_bar_breakout",
    "s14_daily_trend_5m_pullback",
    "s28_daily_atr_filter",
    "s20_ichimoku",
    "s50_supertrend_adx_1m1h",
    "s53_volume_breakout_1m1h",
]


# ---------------------------------------------------------------------------
# Backtest + KPIs
# ---------------------------------------------------------------------------
def _equity_series(stats: Dict[str, Any]) -> List[float]:
    eq = stats.get("equity_curve") or []
    out = []
    for pt in eq:
        if isinstance(pt, dict):
            # find a numeric value key
            v = pt.get("equity") or pt.get("value") or pt.get("total_value")
            if v is None:
                nums = [x for x in pt.values() if isinstance(x, (int, float))]
                v = nums[-1] if nums else None
            if v is not None:
                out.append(float(v))
        elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
            out.append(float(pt[1]))
    return out


def compute_kpis(stats: Dict[str, Any], feed: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Use the engine's own KPI definitions (system-consistent)."""
    init = INITIAL_CAPITAL
    final = float(stats.get("final_equity", init))
    ret = float(stats.get("return_pct", (final - init) / init * 100.0))

    bh = 0.0
    if feed:
        c0 = feed[0]["close"]
        c1 = feed[-1]["close"]
        if c0 > 0:
            bh = (c1 - c0) / c0 * 100.0
    alpha = ret - bh

    return {
        "ret": ret,
        "bh": bh,
        "alpha": alpha,
        "sharpe": float(stats.get("sharpe_ratio", 0.0) or 0.0),
        "mdd": abs(float(stats.get("max_drawdown", 0.0) or 0.0)),
        "win": float(stats.get("win_rate", 0.0) or 0.0),
        "pf": float(stats.get("profit_factor", 0.0) or 0.0),
        # n_trades gate = round-trip cycles, not buy+sell legs
        "trades": int(stats.get("total_cycles", stats.get("trades_count", 0)) or 0),
    }


async def run_backtest(
    strat_cls: Type[KrStrategyBase],
    feed_slice: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    engine = KrBacktestEngine(strat_cls, exchange_name="Kiwoom")
    cfg = dict(config or {})
    cfg["symbol"] = SYMBOL
    stats = await engine.run_single_backtest(
        config=cfg,
        feed=feed_slice,
        initial_capital=INITIAL_CAPITAL,
        symbol=SYMBOL,
    )
    return compute_kpis(stats, feed_slice)


def resample(feed_1m, tf) -> List[Dict[str, Any]]:
    freq = TIMEFRAME_TO_FREQ.get(tf)
    if freq is None:
        return feed_1m
    return resample_ohlcv(feed_1m, freq)


def split_test_half(feed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    n = len(feed)
    return feed[n // 2 :]


def wf_folds(feed: List[Dict[str, Any]], k: int = 6) -> List[List[Dict[str, Any]]]:
    n = len(feed)
    size = n // k
    return [feed[i * size : (i + 1) * size] for i in range(k)] if size > 0 else []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
_BO = False  # Trigger B (intraday breakout) proven harmful on 061090 — keep OFF
S62_CONFIGS = {
    # open-drive-only; vary drive threshold, flow filter, risk
    "A_d003_noFL":        {"min_open_drive_pct": 0.003, "use_intraday_breakout": _BO, "use_flow_filter": False},
    "B_d003_FL0":         {"min_open_drive_pct": 0.003, "use_intraday_breakout": _BO, "use_flow_filter": True, "flow_min_smart_5d": 0.0},
    "C_d005_noFL":        {"min_open_drive_pct": 0.005, "use_intraday_breakout": _BO, "use_flow_filter": False},
    "D_d005_FL0":         {"min_open_drive_pct": 0.005, "use_intraday_breakout": _BO, "use_flow_filter": True, "flow_min_smart_5d": 0.0},
    "E_d005_FLpos":       {"min_open_drive_pct": 0.005, "use_intraday_breakout": _BO, "use_flow_filter": True, "flow_min_smart_5d": 1.0},
    "F_d007_FL0":         {"min_open_drive_pct": 0.007, "use_intraday_breakout": _BO, "use_flow_filter": True, "flow_min_smart_5d": 0.0},
    "G_d005_FL0_tpTrail": {"min_open_drive_pct": 0.005, "use_intraday_breakout": _BO, "use_flow_filter": True, "flow_min_smart_5d": 0.0, "sl_pct": 0.015, "tp_pct": 0.05},
    "H_d005_FL0_tightSL": {"min_open_drive_pct": 0.005, "use_intraday_breakout": _BO, "use_flow_filter": True, "flow_min_smart_5d": 0.0, "sl_pct": 0.010, "tp_pct": 0.030},
}


async def sweep_s62(wf: int):
    from app.kr_strategy_pool.strategies.s62_open_drive_flow import S62OpenDriveFlow

    feed_1m = load_feed_1m(SYMBOL)
    feed = resample(feed_1m, "5m")
    print(f"Loaded {len(feed_1m)} 1m bars -> {len(feed)} 5m bars for {SYMBOL}\n")
    hdr = f"{'config':<26} {'scope':<6} {'ret%':>8} {'BH%':>8} {'alpha':>8} {'shrp':>6} {'mdd%':>6} {'win%':>6} {'PF':>6} {'trd':>5}"
    print(hdr); print("-" * len(hdr))
    for cfg_name, overrides in S62_CONFIGS.items():
        full = await run_backtest(S62OpenDriveFlow, feed, overrides)
        test = await run_backtest(S62OpenDriveFlow, split_test_half(feed), overrides)
        wf_pos = wf_n = 0
        for fslice in wf_folds(feed, wf):
            if len(fslice) < 20:
                continue
            r = await run_backtest(S62OpenDriveFlow, fslice, overrides)
            wf_n += 1
            if r["alpha"] > 0:
                wf_pos += 1
        for scope, k in (("FULL", full), ("TEST", test)):
            pf = k["pf"]; pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
            print(f"{cfg_name:<26} {scope:<6} {k['ret']:>8.2f} {k['bh']:>8.2f} "
                  f"{k['alpha']:>8.2f} {k['sharpe']:>6.2f} {k['mdd']:>6.1f} "
                  f"{k['win']:>6.1f} {pf_s:>6} {k['trades']:>5}")
        print(f"{cfg_name:<26} {'WF':<6}  -> {wf_pos}/{wf_n} folds alpha>0\n")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", default="momentum",
                    help="'momentum' | 'all' | 'sweep62' | comma-separated strategy names")
    ap.add_argument("--wf", type=int, default=6)
    args = ap.parse_args()

    if args.candidates == "sweep62":
        await sweep_s62(args.wf)
        return

    all_strats = discover_strategies()
    print(f"Discovered {len(all_strats)} strategies in pool.")

    if args.candidates == "momentum":
        names = [n for n in MOMENTUM_NAMES if n in all_strats]
    elif args.candidates == "all":
        names = sorted(all_strats.keys())
    else:
        names = [n.strip() for n in args.candidates.split(",") if n.strip() in all_strats]

    feed_1m = load_feed_1m(SYMBOL)
    print(f"Loaded {len(feed_1m)} 1m bars for {SYMBOL}: "
          f"{feed_1m[0]['timestamp']} -> {feed_1m[-1]['timestamp']}\n")

    hdr = f"{'strategy':<26} {'scope':<6} {'ret%':>8} {'BH%':>8} {'alpha':>8} {'shrp':>6} {'mdd%':>6} {'win%':>6} {'PF':>6} {'trd':>5}"
    print(hdr)
    print("-" * len(hdr))

    for name in names:
        cls = all_strats[name]
        tf = getattr(cls, "TIMEFRAME", "5m")
        feed = resample(feed_1m, tf)
        if len(feed) < 50:
            print(f"{name:<26} SKIP (only {len(feed)} {tf} bars)")
            continue

        # FULL
        full = await run_backtest(cls, feed)
        # TEST half
        test = await run_backtest(cls, split_test_half(feed))
        # WF folds
        wf_pos = 0
        wf_n = 0
        for fslice in wf_folds(feed, args.wf):
            if len(fslice) < 20:
                continue
            r = await run_backtest(cls, fslice)
            wf_n += 1
            if r["alpha"] > 0:
                wf_pos += 1

        for scope, k in (("FULL", full), ("TEST", test)):
            pf = k["pf"]
            pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
            print(f"{name:<26} {scope:<6} {k['ret']:>8.2f} {k['bh']:>8.2f} "
                  f"{k['alpha']:>8.2f} {k['sharpe']:>6.2f} {k['mdd']:>6.1f} "
                  f"{k['win']:>6.1f} {pf_s:>6} {k['trades']:>5}")
        print(f"{name:<26} {'WF':<6}  -> {wf_pos}/{wf_n} folds alpha>0\n")


if __name__ == "__main__":
    asyncio.run(main())
