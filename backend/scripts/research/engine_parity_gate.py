#!/usr/bin/env python3
"""실행기 정합성 게이트 — backtester.py vs orchestrator.py.

왜 필요한가 (2026-08-08 사고):
  R-3 검증은 `GenericBacktester`(backtester.py)로 돌고, 실계좌 의사결정은
  System-2 페이퍼 세션 = `PaperOrchestrator`(orchestrator.py)로 돈다. 두 실행기는
  별개 코드인데 배포 계획은 "source/policy를 재구현하지 않았으니 backtest→live
  divergence가 구조적으로 제거됐다"고 가정했다. divergence는 source/policy가
  아니라 **실행기**에서 났다:
      backtester : tp_price = action.tp_price or 0.0          → 익절 없음
      orchestrator: tp_price = action.tp_price or price*0.90  → 익절 10%
  같은 policy, 다른 실행기, 다른 전략. 실자금이 43일간 미검증 규칙으로 돌았다.

이 게이트가 검사하는 것:
  **동일한 바 + 동일한 예측값**을 두 실행기에 넣었을 때 거래 시퀀스가 같은가.
  source/composer/policy는 양쪽이 공유하므로 변수에서 제거되고, 순수하게
  체결·포지션·브래킷 로직만 대조된다.

사용:
  python -m scripts.research.engine_parity_gate --session <session_id>
  python -m scripts.research.engine_parity_gate --spec <spec.json> --symbol GRVTUSDT
  python -m scripts.research.engine_parity_gate --all-lifecycle      # 회귀 스위트

종료코드 0 = 일치, 1 = 불일치(게이트 실패). CI/배포 전 훅으로 쓸 것.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))

from app.composer_framework import build_pipeline  # noqa: E402
from app.composer_framework.backtester import GenericBacktester  # noqa: E402
from app.composer_framework.orchestrator import PaperOrchestrator, RuntimeBundle  # noqa: E402
from app.composer_framework.paper_session import PaperSession, SessionStore  # noqa: E402
from app.composer_framework.signal_source import SourceContext  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("engine_parity")
logging.getLogger("app.composer_framework.orchestrator").setLevel(logging.ERROR)

STORE_ROOT = ROOT / "runs" / "paper_sessions"

# 비교 필드. qty/cash는 initial_capital 스케일이 달라질 수 있어 제외하고,
# 전략 동일성을 결정하는 값만 본다.
TRADE_KEYS = ("entry_ts", "exit_ts", "side", "entry_price", "exit_price",
              "return_pct", "exit_reason")
PRICE_TOL = 1e-9
RET_TOL = 1e-9


def load_ohlcv(db, symbol: str, eval_freq_minutes: int):
    rows = db.execute(text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    ), {"s": symbol}).fetchall()
    if not rows:
        return None, None
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    rule = f"{eval_freq_minutes}min"
    ev = pd.DataFrame({
        "open": df["open"].resample(rule).first(),
        "high": df["high"].resample(rule).max(),
        "low": df["low"].resample(rule).min(),
        "close": df["close"].resample(rule).last(),
        "volume": df["volume"].resample(rule).sum(),
    }).dropna()
    return df, ev


def _norm(t: dict) -> tuple:
    return (
        str(pd.Timestamp(t["entry_ts"])), str(pd.Timestamp(t["exit_ts"])), t["side"],
        round(float(t["entry_price"]), 12), round(float(t["exit_price"]), 12),
        round(float(t["return_pct"]), 12), t["exit_reason"],
    )


def compare(spec: dict, symbol: str, initial_capital: float, fee_rate: float) -> dict:
    eval_freq = int(spec.get("config", {}).get("eval_freq_minutes", 1440))
    db = SessionLocal()
    try:
        df_1m, df_eval = load_ohlcv(db, symbol, eval_freq)
    finally:
        db.close()
    if df_eval is None or len(df_eval) < 5:
        return {"symbol": symbol, "skipped": "ohlcv 부족"}

    runtime = {"symbol": symbol, "ohlcv_1m": df_1m, "ohlcv_eval": df_eval}
    ctx = SourceContext(symbol=symbol, eval_freq_minutes=eval_freq,
                        ohlcv_1m=df_1m, ohlcv_eval=df_eval)

    # ── 공통: 피처 + 예측을 한 번만 만들어 두 실행기에 동일하게 투입 ──
    pipeline = build_pipeline(spec, runtime)
    feat = pipeline.build_features(ctx)
    try:
        pipeline.fit(feat.iloc[:0])
    except Exception:
        pass
    positions = list(range(1, len(df_eval)))   # orchestrator가 replay할 구간과 동일
    preds = pd.Series(pipeline.predict(feat.iloc[positions]), index=df_eval.index[positions])
    bars = df_eval.iloc[positions]

    # ── Engine A: backtester ──
    bt = GenericBacktester(initial_capital=initial_capital, size_pct=0.95, fee_rate=fee_rate)
    kpis = bt._simulate(symbol=symbol, bars=bars, predictions=preds, policy=pipeline.policy)
    a_trades = [{
        "entry_ts": t.entry_ts, "exit_ts": t.exit_ts, "side": t.side,
        "entry_price": t.entry_price, "exit_price": t.exit_price,
        "return_pct": t.return_pct, "exit_reason": t.exit_reason,
    } for t in kpis.trades]

    # ── Engine B: orchestrator (전 구간 catch-up replay) ──
    with tempfile.TemporaryDirectory() as td:
        store = SessionStore(td)
        sess = PaperSession(
            session_id="parity", name=f"parity_{symbol}", symbol=symbol,
            pipeline_spec=spec, initial_capital=initial_capital, fee_rate=fee_rate,
            last_cycle_ts=pd.Timestamp(df_eval.index[0]).isoformat(),
        )
        store.save(sess)
        PaperOrchestrator(store).run_cycle(sess, RuntimeBundle(ohlcv_1m=df_1m, ohlcv_eval=df_eval))
        b_trades = store.read_trades("parity")

    # backtester는 데이터 끝에서 잔여 포지션을 강제 청산해 `eod` 거래로 남긴다.
    # orchestrator는 라이브 세션이라 열어 둔다 — 정당한 설계 차이이므로 비교에서 제외.
    a_norm = [_norm(t) for t in a_trades if t["exit_reason"] != "eod"]
    b_norm = [_norm(t) for t in b_trades if t["exit_reason"] != "eod"]
    match = a_norm == b_norm

    diffs = []
    for i in range(max(len(a_norm), len(b_norm))):
        x = a_norm[i] if i < len(a_norm) else None
        y = b_norm[i] if i < len(b_norm) else None
        if x != y:
            diffs.append({"idx": i, "backtester": x, "orchestrator": y})
    return {
        "symbol": symbol, "match": match,
        "n_backtester": len(a_norm), "n_orchestrator": len(b_norm),
        "n_bars": len(bars), "diffs": diffs[:6],
    }


def lifecycle_specs(limit: int | None) -> list[tuple[str, dict, float, float]]:
    """활성 lifecycle 세션에서 (symbol, spec, capital, fee) 추출. 심볼×스펙 중복 제거."""
    out, seen = [], set()
    for p in sorted(STORE_ROOT.glob("*/session.json")):
        try:
            s = json.loads(p.read_text())
        except Exception:
            continue
        if "lifecycle" not in (s.get("name") or ""):
            continue
        spec = s.get("pipeline_spec") or {}
        key = (s["symbol"], json.dumps(spec, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        out.append((s["symbol"], spec, float(s.get("initial_capital") or 1e6),
                    float(s.get("fee_rate") or 0.0004)))
        if limit and len(out) >= limit:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session")
    ap.add_argument("--spec")
    ap.add_argument("--symbol")
    ap.add_argument("--all-lifecycle", action="store_true")
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()

    cases: list[tuple[str, dict, float, float]] = []
    if args.all_lifecycle:
        cases = lifecycle_specs(args.limit)
    elif args.session:
        s = json.loads((STORE_ROOT / args.session / "session.json").read_text())
        cases = [(s["symbol"], s["pipeline_spec"], float(s.get("initial_capital") or 1e6),
                  float(s.get("fee_rate") or 0.0004))]
    elif args.spec and args.symbol:
        cases = [(args.symbol, json.loads(Path(args.spec).read_text()), 1e6, 0.0004)]
    else:
        ap.error("--session / --spec+--symbol / --all-lifecycle 중 하나 필요")

    log.info("정합성 게이트: %d 케이스", len(cases))
    failed, skipped = [], []
    for symbol, spec, cap, fee in cases:
        try:
            r = compare(spec, symbol, cap, fee)
        except Exception as exc:
            log.error("%-13s 실행 오류: %s", symbol, exc)
            failed.append({"symbol": symbol, "error": str(exc)})
            continue
        if r.get("skipped"):
            log.info("%-13s SKIP (%s)", symbol, r["skipped"])
            skipped.append(r)
            continue
        tag = "PASS" if r["match"] else "FAIL"
        log.info("%-13s %s  거래 bt=%d orch=%d  (바 %d)",
                 symbol, tag, r["n_backtester"], r["n_orchestrator"], r["n_bars"])
        if not r["match"]:
            failed.append(r)
            for d in r["diffs"]:
                log.info("      #%d bt=%s", d["idx"], d["backtester"])
                log.info("         orch=%s", d["orchestrator"])

    n_run = len(cases) - len(skipped)
    if failed:
        log.error("게이트 실패: %d/%d 케이스 불일치", len(failed), n_run)
        return 1
    log.info("게이트 통과: %d/%d 케이스 일치", n_run, n_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
