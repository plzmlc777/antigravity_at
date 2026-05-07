#!/usr/bin/env python3
"""Binance OOS validation — mirror of ml_kr_oos but on Binance Futures symbols.

Variants tested per symbol (same IS/OOS 50/50 split, forward=5):
  - Pattern only       : Pattern + Market + Regime, LGBM
  - Combined (if avail): Pattern + Market + Regime + BinanceMicro, LGBM

Symbols with microstructure data (BTC/ETH/SOL) get the Combined variant; others
fall back to Pattern only. Trade simulator uses Binance Futures fee rate
(0.0004 taker round-trip approximation) and conservative SL/TP defaults.
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.composer_framework.signal_source import SourceContext  # noqa: E402
from app.composer_framework.sources import (  # noqa: E402
    BinanceFundingOISource,
    BinanceSmartMoneySource,
    BinanceTakerFlowSource,
    BinanceOIDynamicsSource,
)
from app.microstructure.features import aggregate_to_eval_bars  # noqa: E402
from app.pattern_ml.features import build_feature_matrix  # noqa: E402
from app.pattern_ml.lgbm_composer import LGBMComposer, LGBMComposerConfig  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")
warnings.filterwarnings("ignore", category=UserWarning)


def load_1m(sym: str) -> pd.DataFrame:
    db = SessionLocal()
    try:
        sql = text("SELECT timestamp, open, high, low, close, volume FROM ohlcv "
                   "WHERE symbol = :sym AND time_frame = '1m' ORDER BY timestamp")
        rows = db.execute(sql, {"sym": sym}).fetchall()
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df[c])
        return df.dropna(subset=["open", "high", "low", "close", "volume"])
    finally:
        db.close()


def load_signals(sym: str) -> pd.DataFrame:
    for d in (365, 364, 363, 200, 540, 800):
        p = ROOT / "runs" / "pattern_scanner" / f"{sym}__{d}d__signals.joblib"
        if p.exists():
            return joblib.load(p)
    for p in (ROOT / "runs" / "pattern_scanner").glob(f"{sym}__*d__signals.joblib"):
        return joblib.load(p)
    raise FileNotFoundError(sym)


def load_micro(sym: str) -> pd.DataFrame | None:
    p = ROOT / "runs" / "microstructure" / f"{sym}_full_metrics.joblib"
    if p.exists():
        return joblib.load(p)
    return None


def load_funding_db(sym: str) -> pd.DataFrame | None:
    db = SessionLocal()
    try:
        sql = text("SELECT symbol, funding_time, funding_rate, mark_price "
                   "FROM binance_funding_rate WHERE symbol = :s ORDER BY funding_time")
        rows = db.execute(sql, {"s": sym}).fetchall()
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["symbol", "funding_time", "funding_rate", "mark_price"])
        df["funding_time"] = pd.to_datetime(df["funding_time"])
        df["funding_rate"] = pd.to_numeric(df["funding_rate"])
        return df
    finally:
        db.close()


def load_oi_db(sym: str, period: str = "1d") -> pd.DataFrame | None:
    db = SessionLocal()
    try:
        sql = text("SELECT symbol, timestamp, interval_str, sum_open_interest, sum_open_interest_value "
                   "FROM binance_open_interest_hist WHERE symbol = :s AND interval_str = :p ORDER BY timestamp")
        rows = db.execute(sql, {"s": sym, "p": period}).fetchall()
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["symbol", "timestamp", "interval_str",
                                         "sum_open_interest", "sum_open_interest_value"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["sum_open_interest"] = pd.to_numeric(df["sum_open_interest"])
        return df
    finally:
        db.close()


def attach_funding_oi(features: pd.DataFrame, funding_df: pd.DataFrame | None,
                       oi_df: pd.DataFrame | None, eval_freq_min: int) -> pd.DataFrame:
    """Join BinanceFundingOI features onto an existing feature matrix.
    The eval index of `features` is used as ohlcv_eval.index for the source."""
    if funding_df is None and oi_df is None:
        return features
    src = BinanceFundingOISource(funding_df=funding_df, oi_df=oi_df)
    ohlcv_eval = pd.DataFrame({"close": np.nan}, index=features.index)
    ctx = SourceContext(symbol="", eval_freq_minutes=eval_freq_min, ohlcv_eval=ohlcv_eval)
    feats = src.build_features(ctx)
    return features.join(feats, how="left")


def attach_smart_money(features: pd.DataFrame, metrics_5m: pd.DataFrame | None,
                        eval_freq_min: int) -> pd.DataFrame:
    """Join BinanceSmartMoney (cumulative top-trader L/S) features."""
    if metrics_5m is None or metrics_5m.empty:
        return features
    src = BinanceSmartMoneySource(metrics_5m=metrics_5m)
    ohlcv_eval = pd.DataFrame({"close": np.nan}, index=features.index)
    ctx = SourceContext(symbol="", eval_freq_minutes=eval_freq_min, ohlcv_eval=ohlcv_eval)
    feats = src.build_features(ctx)
    return features.join(feats, how="left")


def attach_taker_flow(features: pd.DataFrame, metrics_5m: pd.DataFrame | None,
                       eval_freq_min: int) -> pd.DataFrame:
    """Join BinanceTakerFlow (cumulative taker buy/sell pressure) features."""
    if metrics_5m is None or metrics_5m.empty:
        return features
    src = BinanceTakerFlowSource(metrics_5m=metrics_5m)
    ohlcv_eval = pd.DataFrame({"close": np.nan}, index=features.index)
    ctx = SourceContext(symbol="", eval_freq_minutes=eval_freq_min, ohlcv_eval=ohlcv_eval)
    feats = src.build_features(ctx)
    return features.join(feats, how="left")


def attach_oi_dynamics(features: pd.DataFrame, metrics_5m: pd.DataFrame | None,
                        ohlcv_eval: pd.DataFrame, eval_freq_min: int) -> pd.DataFrame:
    """Join BinanceOIDynamics (OI×price 4-quadrant) features."""
    if metrics_5m is None or metrics_5m.empty:
        return features
    src = BinanceOIDynamicsSource(metrics_5m=metrics_5m)
    ctx = SourceContext(symbol="", eval_freq_minutes=eval_freq_min, ohlcv_eval=ohlcv_eval)
    feats = src.build_features(ctx)
    return features.join(feats, how="left")


def attach_micro(features: pd.DataFrame, metrics_5m: pd.DataFrame, eval_freq_min: int) -> pd.DataFrame:
    """Join aggregated microstructure features onto pattern features."""
    if metrics_5m is None or len(metrics_5m) == 0:
        return features
    micro = aggregate_to_eval_bars(metrics_5m, features.index, eval_freq_min)
    if "micro_" not in "".join(micro.columns):
        micro = micro.add_prefix("micro_")
    out = features.join(micro, how="left")
    return out


def diagnose(name, preds, actuals):
    mask = ~(np.isnan(preds) | np.isnan(actuals))
    p = preds[mask]
    a = actuals[mask]
    if len(p) < 5:
        print(f"  {name}: too few (n={len(p)})")
        return
    corr = float(np.corrcoef(p, a)[0, 1])
    sign = float((np.sign(p) == np.sign(a)).mean())
    from scipy import stats as scistats
    binom_p = scistats.binomtest(int((np.sign(p) == np.sign(a)).sum()), len(p), 0.5).pvalue if len(p) > 0 else 1.0
    q75, q25 = np.quantile(p, [0.75, 0.25])
    top = float(a[p >= q75].mean()) if (p >= q75).any() else 0.0
    bot = float(a[p <= q25].mean()) if (p <= q25).any() else 0.0
    sig = "***" if binom_p < 0.001 else ("**" if binom_p < 0.01 else ("*" if binom_p < 0.05 else " "))
    print(f"  {name}: n={len(p):3d} | corr={corr:+.4f} | sign={sign*100:.1f}%{sig} | "
          f"top25={top*100:+.3f}% bot25={bot*100:+.3f}% spread={(top-bot)*100:+.3f}% | binomial p={binom_p:.4f}")


def trade_sim(bars, preds, *, threshold, sl, tp, hold, fee=0.0004, policy="long_only"):
    """Long-only or long+short trade simulation with Binance Futures fee.

    For short trades the SL is hit when price RISES by sl pct, TP hit when price
    FALLS by tp pct. PnL is (ent_p - exit_p) * qty - fees.
    """
    cash = 1_000_000
    qty = 0
    ent_p = 0
    ent_i = -1
    side = "flat"
    trades = []
    eq = []
    for i in range(len(bars)):
        o = float(bars.iloc[i]["open"])
        c = float(bars.iloc[i]["close"])
        pred = preds[i] if i < len(preds) else np.nan

        if side == "long":
            held = i - ent_i
            ex_r = None
            ex_p = o
            if c <= ent_p * (1 - sl):
                ex_r = "sl"; ex_p = ent_p * (1 - sl)
            elif c >= ent_p * (1 + tp):
                ex_r = "tp"; ex_p = ent_p * (1 + tp)
            elif held >= hold:
                ex_r = "time"; ex_p = o
            if ex_r:
                proc = qty * ex_p * (1 - fee)
                cost = qty * ent_p * (1 + fee)
                ret = (proc - cost) / cost
                cash += proc
                trades.append({"ret": ret, "side": "long"})
                qty = 0; side = "flat"
        elif side == "short":
            held = i - ent_i
            ex_r = None
            ex_p = o
            # short SL: price rises (loss); short TP: price falls (gain)
            if c >= ent_p * (1 + sl):
                ex_r = "sl"; ex_p = ent_p * (1 + sl)
            elif c <= ent_p * (1 - tp):
                ex_r = "tp"; ex_p = ent_p * (1 - tp)
            elif held >= hold:
                ex_r = "time"; ex_p = o
            if ex_r:
                # short PnL: (ent_p - exit_p) * qty, minus fees
                # We held qty units at ent_p (notional = qty*ent_p, taken from collateral).
                # Exit cost = qty * exit_p * (1 + fee); we recover collateral + PnL.
                pnl = qty * (ent_p - ex_p) - qty * ent_p * fee - qty * ex_p * fee
                cash += qty * ent_p + pnl  # release collateral + add PnL
                ret = pnl / (qty * ent_p)
                trades.append({"ret": ret, "side": "short"})
                qty = 0; side = "flat"

        if side == "flat" and not np.isnan(pred):
            if pred > threshold:
                qty = (cash * 0.95) / (o * (1 + fee))
                cash -= qty * o * (1 + fee)
                side = "long"; ent_p = o; ent_i = i
            elif policy == "long_short" and pred < -threshold:
                # Short: lock collateral equal to notional, no upfront cost beyond fee.
                qty = (cash * 0.95) / o
                cash -= qty * o  # collateral
                # entry fee taken from cash separately
                cash -= qty * o * fee
                side = "short"; ent_p = o; ent_i = i

        # mark-to-market equity
        if side == "long":
            eq.append(cash + qty * c)
        elif side == "short":
            # collateral + unrealized PnL
            eq.append(cash + qty * ent_p + qty * (ent_p - c))
        else:
            eq.append(cash)

    # close any open at end
    if side == "long":
        last = float(bars.iloc[-1]["close"])
        proc = qty * last * (1 - fee)
        cost = qty * ent_p * (1 + fee)
        cash += proc
        trades.append({"ret": (proc - cost) / cost, "side": "long"})
    elif side == "short":
        last = float(bars.iloc[-1]["close"])
        pnl = qty * (ent_p - last) - qty * ent_p * fee - qty * last * fee
        cash += qty * ent_p + pnl
        trades.append({"ret": pnl / (qty * ent_p), "side": "short"})

    rets = np.array([t["ret"] for t in trades]) if trades else np.array([])
    longs = sum(1 for t in trades if t["side"] == "long")
    shorts = sum(1 for t in trades if t["side"] == "short")
    eq_arr = np.array(eq)
    peaks = np.maximum.accumulate(eq_arr) if len(eq_arr) else np.array([])
    dd = (peaks - eq_arr) / peaks if len(eq_arr) else np.array([])
    return {"trades": len(trades), "longs": longs, "shorts": shorts,
            "ret": (cash - 1_000_000) / 1_000_000,
            "wr": float((rets > 0).mean()) if len(rets) else 0.0,
            "mdd": float(dd.max()) if len(dd) else 0.0}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,DOGEUSDT,AVAXUSDT")
    p.add_argument("--forward", type=int, default=5)
    p.add_argument("--sl", type=float, default=0.06, help="stop loss (Binance default wider than KR)")
    p.add_argument("--tp", type=float, default=0.15, help="take profit (Binance default wider than KR)")
    p.add_argument("--threshold", type=float, default=0.005)
    p.add_argument("--policy", default="long_short", choices=["long_only", "long_short"])
    p.add_argument("--include-funding", action="store_true", default=True,
                   help="Include funding-rate features variant (default on)")
    p.add_argument("--include-oi", action="store_true", default=False,
                   help="Also attach OI hist features (note: 30-day Binance limit)")
    p.add_argument("--include-smart-money", action="store_true", default=True,
                   help="Include smart-money (toptrader L/S cumulative) variant (default on, requires micro_5m)")
    p.add_argument("--include-taker-flow", action="store_true", default=True,
                   help="Include taker-flow (cumulative taker buy/sell) variant")
    p.add_argument("--include-oi-dynamics", action="store_true", default=True,
                   help="Include OI dynamics (OI*price quadrant) variant")
    args = p.parse_args()

    syms = [s.strip() for s in args.symbols.split(",")]
    print(f"Binance OOS — strict IS/OOS 50/50, forward={args.forward}, "
          f"fee=0.0004, sl={args.sl}, tp={args.tp}, threshold={args.threshold}, policy={args.policy}")
    print()

    rows = []
    for sym in syms:
        try:
            df_1m = load_1m(sym)
            df_eval = resample_ohlcv(df_1m, "1d")
            signals = load_signals(sym)
        except FileNotFoundError as e:
            print(f"=== {sym} === SKIP (missing signals: {e})")
            continue

        cls = RegimeClassifier.for_daily()
        regime_eval = cls.classify(df_eval)
        micro = load_micro(sym)
        has_micro = micro is not None

        feat_pat = build_feature_matrix(
            ohlcv_eval=df_eval, signals_df=signals, regime_eval=regime_eval,
            eval_freq_minutes=1440, forward_bars=args.forward,
        )
        if has_micro:
            feat_combined = attach_micro(feat_pat, micro, 1440)
        else:
            feat_combined = feat_pat

        # Optional Pat+Funding(+OI) variant
        feat_funding = None
        funding_df = oi_df = None
        if args.include_funding:
            funding_df = load_funding_db(sym)
            oi_df = load_oi_db(sym) if args.include_oi else None
            if funding_df is not None or oi_df is not None:
                feat_funding = attach_funding_oi(feat_pat, funding_df, oi_df, 1440)

        # Optional Pat+SmartMoney variant (requires 5min metrics)
        feat_smart = None
        if args.include_smart_money and has_micro:
            feat_smart = attach_smart_money(feat_pat, micro, 1440)

        # Optional Pat+TakerFlow variant
        feat_taker = None
        if args.include_taker_flow and has_micro:
            feat_taker = attach_taker_flow(feat_pat, micro, 1440)

        # Optional Pat+OIDynamics variant
        feat_oid = None
        if args.include_oi_dynamics and has_micro:
            feat_oid = attach_oi_dynamics(feat_pat, micro, df_eval, 1440)

        n = len(feat_combined)
        split = n // 2
        train = feat_combined.iloc[:split].dropna(subset=["target_fwd_ret"])
        test = feat_combined.iloc[split:]

        if len(train) < 30 or len(test) < 30:
            print(f"=== {sym} === SKIP train/test too small (train={len(train)}, test={len(test)})")
            continue

        print(f"=== {sym} (train: {train.index[0].date()} → {train.index[-1].date()}, "
              f"test: {test.index[0].date()} → {test.index[-1].date()}) ===")
        print(f"  micro={has_micro}, funding={funding_df is not None and len(funding_df)>0}, "
              f"oi={oi_df is not None and len(oi_df)>0}, "
              f"train n={len(train)}, test n={len(test)}")

        # Variant comparison via diagnose()
        feat_pat_train = feat_pat.iloc[:split].dropna(subset=["target_fwd_ret"])
        feat_pat_test = feat_pat.iloc[split:]
        variants = [("Pattern only ", feat_pat_train, feat_pat_test),
                    ("Combined     ", train, test)]
        if feat_funding is not None:
            ff_train = feat_funding.iloc[:split].dropna(subset=["target_fwd_ret"])
            ff_test = feat_funding.iloc[split:]
            variants.append(("Pat+Funding  ", ff_train, ff_test))
        if feat_smart is not None:
            fs_train = feat_smart.iloc[:split].dropna(subset=["target_fwd_ret"])
            fs_test = feat_smart.iloc[split:]
            variants.append(("Pat+SmartMon ", fs_train, fs_test))
        if feat_taker is not None:
            ft_train = feat_taker.iloc[:split].dropna(subset=["target_fwd_ret"])
            ft_test = feat_taker.iloc[split:]
            variants.append(("Pat+TakerFlow", ft_train, ft_test))
        if feat_oid is not None:
            fo_train = feat_oid.iloc[:split].dropna(subset=["target_fwd_ret"])
            fo_test = feat_oid.iloc[split:]
            variants.append(("Pat+OIDyn    ", fo_train, fo_test))

        diag_results = {}
        for name, ft, fte in variants:
            if len(ft) < 30 or len(fte) < 30:
                print(f"  {name}: SKIP")
                continue
            cfg = LGBMComposerConfig()
            comp = LGBMComposer(cfg)
            comp.fit(ft, target_col="target_fwd_ret")
            preds = comp.predict(fte)
            actuals = fte["target_fwd_ret"].values
            diagnose(name, preds, actuals)
            # capture sign + binom_p for seed gate
            mask = ~(np.isnan(preds) | np.isnan(actuals))
            p_arr, a_arr = preds[mask], actuals[mask]
            if len(p_arr) >= 5:
                from scipy import stats as scistats
                hits = int((np.sign(p_arr) == np.sign(a_arr)).sum())
                sign = float(hits / len(p_arr))
                binom_p = scistats.binomtest(hits, len(p_arr), 0.5).pvalue
                diag_results[name.strip()] = (sign, binom_p, len(p_arr))

        # OOS Backtest of each available variant
        backtest_targets = [("Combined", train, test, feat_combined)]
        if feat_funding is not None:
            ff_train = feat_funding.iloc[:split].dropna(subset=["target_fwd_ret"])
            ff_test = feat_funding.iloc[split:]
            backtest_targets.append(("Pat+Funding", ff_train, ff_test, feat_funding))
        if feat_smart is not None:
            fs_train = feat_smart.iloc[:split].dropna(subset=["target_fwd_ret"])
            fs_test = feat_smart.iloc[split:]
            backtest_targets.append(("Pat+SmartMon", fs_train, fs_test, feat_smart))
        if feat_taker is not None:
            ft_train = feat_taker.iloc[:split].dropna(subset=["target_fwd_ret"])
            ft_test = feat_taker.iloc[split:]
            backtest_targets.append(("Pat+TakerFlow", ft_train, ft_test, feat_taker))
        if feat_oid is not None:
            fo_train = feat_oid.iloc[:split].dropna(subset=["target_fwd_ret"])
            fo_test = feat_oid.iloc[split:]
            backtest_targets.append(("Pat+OIDyn", fo_train, fo_test, feat_oid))

        for vname, vtrain, vtest, _ in backtest_targets:
            cfg = LGBMComposerConfig()
            comp = LGBMComposer(cfg)
            comp.fit(vtrain, target_col="target_fwd_ret")
            preds = comp.predict(vtest)
            bars_test = df_eval.loc[vtest.index]
            kpi = trade_sim(bars_test, preds, threshold=args.threshold,
                            sl=args.sl, tp=args.tp, hold=args.forward, policy=args.policy)
            bh_test = (bars_test.iloc[-1]["close"] - bars_test.iloc[0]["open"]) / bars_test.iloc[0]["open"]
            alpha = (kpi["ret"] - bh_test) * 100
            print(f"  OOS BT ({vname:11s},{args.policy}): trades={kpi['trades']:3d} "
                  f"(L{kpi.get('longs',0)}/S{kpi.get('shorts',0)}) | ret={kpi['ret']*100:+8.2f}% | "
                  f"wr={kpi['wr']*100:.1f}% | mdd={kpi['mdd']*100:.1f}% | "
                  f"BH={bh_test*100:+.2f}% | alpha={alpha:+7.2f}pts")
            sign_p = diag_results.get(vname.replace("Pat+Funding", "Pat+Funding").replace("Combined", "Combined"))
            rows.append({"symbol": sym, "variant": vname, "has_micro": has_micro,
                         "alpha_pts": alpha, "ret_pct": kpi["ret"] * 100,
                         "bh_pct": bh_test * 100, "wr_pct": kpi["wr"] * 100,
                         "mdd_pct": kpi["mdd"] * 100, "trades": kpi["trades"],
                         "sign_pct": sign_p[0] * 100 if sign_p else np.nan,
                         "binom_p": sign_p[1] if sign_p else np.nan})
        print()

    if rows:
        df = pd.DataFrame(rows).sort_values(["variant", "alpha_pts"], ascending=[True, False])
        print("=" * 100)
        print("SUMMARY (per variant, sorted by alpha):")
        print(df.to_string(index=False))
        print()
        # Seed gate evaluation
        print("=" * 100)
        print(f"SEED GATE: sign≥60% AND p<0.01 AND alpha>0  (policy={args.policy})")
        for variant_name in df["variant"].unique():
            sub = df[df["variant"] == variant_name]
            passed = sub[(sub["sign_pct"] >= 60) & (sub["binom_p"] < 0.01) & (sub["alpha_pts"] > 0)]
            print(f"  [{variant_name}] passed {len(passed)}/{len(sub)}: "
                  f"{', '.join(passed['symbol'].tolist()) if len(passed) else '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
