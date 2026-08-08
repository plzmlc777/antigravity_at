#!/usr/bin/env python3
"""3군 새 판정 기준 검증 — 양성/음성 대조.

새 기준이 옳은지는 실체를 아는 두 대조군으로 확인한다.

  양성: lifecycle pump-decay   실계좌 3개월 +240.17 USDT 실현  → PASS 나와야 함
  음성: volume_burst (lookahead 제거 후)  재측정 엣지 0.0175%,
        5분 지연 시 96% 소멸, 실전 재현 실패           → FAIL 나와야 함

둘 다 맞히면 기준이 작동하는 것이고, 못 맞히면 임계값을 재조정한다.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "research"))
os.chdir(ROOT)

from app.db.session import SessionLocal  # noqa: E402
from tier3_gate import Trade, ExecContext, evaluate, render  # noqa: E402

FEE_RT = 0.0008
LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"


def daily(db, sym):
    rows = db.execute(text(
        "SELECT timestamp, open, high, low, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"), {"s": sym}).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return pd.DataFrame({
        "open": df["open"].resample("1D").first(),
        "high": df["high"].resample("1D").max(),
        "low": df["low"].resample("1D").min(),
        "close": df["close"].resample("1D").last()}).dropna()


# ────────────────────────────── 양성 대조 ──────────────────────────────
def positive_control(db):
    listings = json.loads(LISTINGS.read_text())
    today = date.today()
    syms = sorted({r[0] for r in db.execute(text(
        "SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m'")).fetchall()})
    trades = []
    for sym in syms:
        meta = listings.get(sym)
        if not isinstance(meta, dict) or not meta.get("onboard_date"):
            continue
        ld = datetime.strptime(meta["onboard_date"], "%Y-%m-%d").date()
        if not (30 <= (today - ld).days <= 365):
            continue
        d = daily(db, sym)
        if d.empty or len(d) < 35:
            continue
        try:
            pos = d.index.get_indexer([pd.Timestamp(ld)], method="nearest")[0]
        except Exception:
            continue
        if abs((d.index[pos].date() - ld).days) > 2 or pos >= len(d) - 30:
            continue
        ep = float(d.iloc[pos]["close"])
        if ep <= 0:
            continue
        sl = ep * 1.5
        mx = min(pos + 30, len(d) - 1)
        xp = float(d.iloc[mx]["close"])
        xi = mx
        for i in range(pos + 1, mx + 1):
            if float(d.iloc[i]["high"]) >= sl:
                xp, xi = sl, i
                break
        trades.append(Trade(entry_ts=d.index[pos].to_pydatetime(),
                            exit_ts=d.index[xi].to_pydatetime(),
                            net_ret=(ep - xp) / ep - FEE_RT))
    # G2: lifecycle 은 일봉·30일 보유 → 지연 내성이 구조적으로 높다.
    #     오늘 실측: 38시간 지연에도 성과 유지(오히려 유리하게 작용한 사례 2건).
    #     보수적으로 1바(1일) 지연 재시뮬 대신 실측 기반 값을 쓴다.
    return trades


def positive_delay_edge(db, trades):
    """양성 대조의 1바(1일) 지연 엣지 — 진입을 하루 늦춘다."""
    listings = json.loads(LISTINGS.read_text())
    today = date.today()
    syms = sorted({r[0] for r in db.execute(text(
        "SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m'")).fetchall()})
    rets = []
    for sym in syms:
        meta = listings.get(sym)
        if not isinstance(meta, dict) or not meta.get("onboard_date"):
            continue
        ld = datetime.strptime(meta["onboard_date"], "%Y-%m-%d").date()
        if not (30 <= (today - ld).days <= 365):
            continue
        d = daily(db, sym)
        if d.empty or len(d) < 36:
            continue
        try:
            pos = d.index.get_indexer([pd.Timestamp(ld)], method="nearest")[0] + 1  # 1일 지연
        except Exception:
            continue
        if pos >= len(d) - 30:
            continue
        ep = float(d.iloc[pos]["close"])
        if ep <= 0:
            continue
        sl = ep * 1.5
        mx = min(pos + 30, len(d) - 1)
        xp = float(d.iloc[mx]["close"])
        for i in range(pos + 1, mx + 1):
            if float(d.iloc[i]["high"]) >= sl:
                xp = sl
                break
        rets.append((ep - xp) / ep - FEE_RT)
    return float(np.mean(rets)) if rets else 0.0


# ────────────────────────────── 음성 대조 ──────────────────────────────
def negative_control(db):
    """volume_burst (lookahead 제거본) FILUSDT — 오늘 재측정한 그 전략."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from paper_session_cli import build_runtime_bundle
    from app.composer_framework import build_pipeline
    from app.composer_framework.backtester import GenericBacktester
    from app.composer_framework.signal_source import SourceContext

    sid, meta = None, None
    root = ROOT / "runs" / "paper_sessions"
    for d in sorted(os.listdir(root)):
        p = root / d / "session.json"
        if not p.exists():
            continue
        m = json.loads(p.read_text())
        if m.get("symbol") != "FILUSDT" or m.get("status") != "active":
            continue
        srcs = [x.get("type") for x in ((m.get("pipeline_spec") or {}).get("sources") or [])]
        if any("neg_reversion" in (x or "") for x in srcs):
            sid, meta = d, m
            break
    if not meta:
        return [], 0.0
    spec = meta["pipeline_spec"]
    freq = int((spec.get("config") or {}).get("eval_freq_minutes", 5))
    srcs = [x.get("type") for x in (spec.get("sources") or [])]
    b = build_runtime_bundle("FILUSDT", freq, srcs)
    rt = {"symbol": "FILUSDT", "ohlcv_1m": b.ohlcv_1m, "ohlcv_eval": b.ohlcv_eval}
    for f in ("signals_df", "binance_metrics_5m", "binance_funding_df", "binance_oi_df",
              "binance_funding_universe_df", "leader_ohlcv_eval", "leader_ohlcv_1m",
              "book_depth_daily", "premium_df", "eth_ohlcv_eval", "flow_df"):
        v = getattr(b, f, None)
        if v is not None:
            rt[f] = v
    pipe = build_pipeline(spec, rt)
    feat = pipe.build_features(SourceContext(symbol="FILUSDT", eval_freq_minutes=freq,
                                             ohlcv_1m=b.ohlcv_1m, ohlcv_eval=b.ohlcv_eval))
    try:
        pipe.fit(feat.iloc[:0])
    except Exception:
        pass
    preds = pd.Series(pipe.predict(feat), index=feat.index)
    bars = b.ohlcv_eval.loc[preds.index]
    bt = GenericBacktester(initial_capital=1e6, size_pct=0.95, fee_rate=0.0004)
    res = bt._simulate(symbol="FILUSDT", bars=bars, predictions=preds, policy=pipe.policy)
    trades = [Trade(entry_ts=pd.Timestamp(t.entry_ts).to_pydatetime(),
                    exit_ts=pd.Timestamp(t.exit_ts).to_pydatetime(),
                    net_ret=t.return_pct) for t in res.trades]
    res_d = bt._simulate(symbol="FILUSDT", bars=bars, predictions=preds.shift(1),
                         policy=pipe.policy)
    delayed = float(np.mean([t.return_pct for t in res_d.trades])) if res_d.trades else 0.0
    return trades, delayed


def main():
    db = SessionLocal()
    try:
        print("\n### 양성 대조 — lifecycle pump-decay (실계좌 +240.17 USDT)")
        pos_tr = positive_control(db)
        pos_delay = positive_delay_edge(db, pos_tr)
        pos_ctx = ExecContext(
            lookahead_clean=True,           # 일봉 종가 진입, 오늘 게이트 스캔에서 누출 0
            edge_after_1bar_delay=pos_delay,
            roundtrip_friction=0.0010,      # 신규상장 알트 왕복 마찰 보수 가정 10bp
            hold_minutes=30 * 24 * 60,      # 30일
            cycle_minutes=24 * 60,          # 하루 1회 사이클
        )
        r1 = evaluate(pos_tr, pos_ctx, label="lifecycle pump-decay (양성)")
        print(render(r1))

        print("\n### 음성 대조 — volume_burst FILUSDT (lookahead 제거본)")
        neg_tr, neg_delay = negative_control(db)
        neg_ctx = ExecContext(
            lookahead_clean=True,           # 오늘 수정 완료
            edge_after_1bar_delay=neg_delay,
            roundtrip_friction=0.000142 + 0.0004,  # FIL 스프레드 1.42bp + 수수료
            hold_minutes=10,                # max_hold 2바 × 5분
            cycle_minutes=24 * 60,          # 현재 인프라: 하루 1회
        )
        r2 = evaluate(neg_tr, neg_ctx, label="volume_burst FILUSDT (음성)")
        print(render(r2))

        print("\n" + "=" * 66)
        ok = r1.passed and not r2.passed
        print(f"검증 결과: 양성 {'PASS' if r1.passed else 'FAIL'} / "
              f"음성 {'PASS' if r2.passed else 'FAIL'}")
        print("→ " + ("기준이 작동한다 (양성 통과 + 음성 차단)" if ok
                      else "기준 재조정 필요"))
        print("=" * 66)
        return 0 if ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
