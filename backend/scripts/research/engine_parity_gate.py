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
  이 게이트는 그 뒤 bars_held off-by-one(Day-30 전략이 Day-31 청산)도 잡아냈다.

무엇을 검사하나:
  **동일한 바 + 동일한 예측값**을 두 실행기에 넣었을 때 거래 시퀀스가 같은가.
  예측은 orchestrator를 먼저 돌려 그 세션이 실제로 쓴 값을 뽑아 backtester에
  주입한다 — 각자 fit/predict하게 두면 ML 컴포저에서 예측 자체가 갈려
  실행기 결함과 구분되지 않는다. 이렇게 하면 source/composer/policy가 변수에서
  빠지고 체결·포지션·브래킷 로직만 남는다.

  런타임 데이터는 운영과 같은 `build_runtime_bundle`로 만든다. 게이트가
  실제로 도는 것과 다른 데이터를 쓰면 검사 의미가 없다.

사용:
  python -m scripts.research.engine_parity_gate --all-lifecycle
  python -m scripts.research.engine_parity_gate --all-sessions        # 전 스펙
  python -m scripts.research.engine_parity_gate --session <session_id>

종료코드 0 = 일치, 1 = 불일치(게이트 실패). CI/배포 전 훅으로 쓸 것.
SKIP 사유는 전부 출력한다 — 조용히 건너뛰면 "전부 통과"로 오독된다.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app.composer_framework import build_pipeline  # noqa: E402
from app.composer_framework.backtester import GenericBacktester  # noqa: E402
from app.composer_framework.orchestrator import PaperOrchestrator  # noqa: E402
from app.composer_framework.paper_session import PaperSession, SessionStore  # noqa: E402
from app.composer_framework.signal_source import SourceContext  # noqa: E402

from paper_session_cli import build_runtime_bundle  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("engine_parity")
for noisy in ("app.composer_framework.orchestrator", "paper_session_cli",
              "app.microstructure.kr_investor_flow"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

STORE_ROOT = ROOT / "runs" / "paper_sessions"


def _norm(t: dict) -> tuple:
    return (
        str(pd.Timestamp(t["entry_ts"])), str(pd.Timestamp(t["exit_ts"])), t["side"],
        round(float(t["entry_price"]), 10), round(float(t["exit_price"]), 10),
        round(float(t["return_pct"]), 10), t["exit_reason"],
    )


def compare(spec: dict, symbol: str, initial_capital: float, fee_rate: float) -> dict:
    eval_freq = int(spec.get("config", {}).get("eval_freq_minutes", 1440))
    sources_used = [s.get("type") for s in (spec.get("sources") or [])]
    try:
        bundle = build_runtime_bundle(symbol, eval_freq, sources_used)
    except Exception as exc:
        return {"skipped": f"런타임 데이터 구성 실패: {type(exc).__name__}: {exc}"}
    df_eval = bundle.ohlcv_eval
    if df_eval is None or len(df_eval) < 5:
        return {"skipped": "eval 바 부족"}

    # ── Engine B: orchestrator (전 구간 catch-up replay) ──
    with tempfile.TemporaryDirectory() as td:
        store = SessionStore(td)
        sess = PaperSession(
            session_id="parity", name=f"parity_{symbol}", symbol=symbol,
            pipeline_spec=spec, initial_capital=initial_capital, fee_rate=fee_rate,
            last_cycle_ts=pd.Timestamp(df_eval.index[0]).isoformat(),
        )
        store.save(sess)
        try:
            PaperOrchestrator(store).run_cycle(sess, bundle)
        except Exception as exc:
            return {"skipped": f"orchestrator 실행 실패: {type(exc).__name__}: {exc}"}
        b_trades = store.read_trades("parity")
        cyc_path = Path(td) / "parity" / "predictions.jsonl"
        cycles = [json.loads(l) for l in cyc_path.read_text().splitlines()] if cyc_path.exists() else []

    # orchestrator가 실제로 쓴 예측을 뽑아 backtester에 그대로 주입
    pairs = [(pd.Timestamp(c["timestamp"]), c.get("prediction"))
             for c in cycles if c.get("prediction") is not None
             and not (isinstance(c["prediction"], float) and np.isnan(c["prediction"]))]
    if len(pairs) < 2:
        reason = cycles[0].get("action_note") if cycles else "사이클 없음"
        return {"skipped": f"유효 예측 부족 ({reason})"}
    idx = [t for t, _ in pairs]
    preds = pd.Series([v for _, v in pairs], index=pd.DatetimeIndex(idx))
    try:
        bars = df_eval.loc[preds.index]
    except KeyError:
        return {"skipped": "예측 타임스탬프가 바 인덱스와 불일치"}

    # ── Engine A: backtester (동일 바 + 동일 예측) ──
    # runtime_data는 orchestrator.run_cycle이 조립하는 것과 **동일하게** 채운다.
    # 일부만 넘기면 소스가 KeyError를 내고 케이스가 통째로 SKIP된다 — 검사하지
    # 못한 것을 통과로 오독하게 만드는, 게이트 자신의 사각지대였다.
    runtime_data = {"symbol": symbol, "ohlcv_1m": bundle.ohlcv_1m, "ohlcv_eval": df_eval}
    for fld in ("signals_df", "flow_df", "binance_metrics_5m", "binance_funding_df",
                "binance_oi_df", "binance_funding_universe_df", "leader_ohlcv_eval",
                "leader_ohlcv_1m", "book_depth_daily", "premium_df", "eth_ohlcv_eval"):
        v = getattr(bundle, fld, None)
        if v is not None:
            runtime_data[fld] = v
    pipeline = build_pipeline(spec, runtime_data)
    bt = GenericBacktester(initial_capital=initial_capital, size_pct=0.95, fee_rate=fee_rate)
    try:
        kpis = bt._simulate(symbol=symbol, bars=bars, predictions=preds, policy=pipeline.policy)
    except Exception as exc:
        return {"skipped": f"backtester 실행 실패: {type(exc).__name__}: {exc}"}
    a_trades = [{"entry_ts": t.entry_ts, "exit_ts": t.exit_ts, "side": t.side,
                 "entry_price": t.entry_price, "exit_price": t.exit_price,
                 "return_pct": t.return_pct, "exit_reason": t.exit_reason}
                for t in kpis.trades]

    # backtester는 데이터 끝에서 잔여 포지션을 강제청산해 `eod` 거래로 남긴다.
    # orchestrator는 라이브 세션이라 열어 둔다 — 정당한 설계 차이이므로 제외.
    a_norm = [_norm(t) for t in a_trades if t["exit_reason"] != "eod"]
    b_norm = [_norm(t) for t in b_trades if t["exit_reason"] != "eod"]
    diffs = []
    for i in range(max(len(a_norm), len(b_norm))):
        x = a_norm[i] if i < len(a_norm) else None
        y = b_norm[i] if i < len(b_norm) else None
        if x != y:
            diffs.append({"idx": i, "backtester": x, "orchestrator": y})
    return {"match": a_norm == b_norm, "n_backtester": len(a_norm),
            "n_orchestrator": len(b_norm), "n_bars": len(bars), "diffs": diffs[:4]}


def collect(only_lifecycle: bool, limit: int | None):
    """세션 스펙 수집. (symbol, spec) 중복 제거."""
    out, seen = [], set()
    for p in sorted(STORE_ROOT.glob("*/session.json")):
        try:
            s = json.loads(p.read_text())
        except Exception:
            continue
        if only_lifecycle and "lifecycle" not in (s.get("name") or ""):
            continue
        spec = s.get("pipeline_spec") or {}
        if not spec:
            continue
        key = (s["symbol"], json.dumps(spec, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        out.append((s["symbol"], spec, float(s.get("initial_capital") or 1e6),
                    float(s.get("fee_rate") or 0.0004),
                    (spec.get("policy") or {}).get("type", "?")))
        if limit and len(out) >= limit:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session")
    ap.add_argument("--all-lifecycle", action="store_true")
    ap.add_argument("--all-sessions", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    if args.session:
        s = json.loads((STORE_ROOT / args.session / "session.json").read_text())
        cases = [(s["symbol"], s["pipeline_spec"], float(s.get("initial_capital") or 1e6),
                  float(s.get("fee_rate") or 0.0004),
                  (s["pipeline_spec"].get("policy") or {}).get("type", "?"))]
    elif args.all_lifecycle or args.all_sessions:
        cases = collect(only_lifecycle=args.all_lifecycle, limit=args.limit)
    else:
        ap.error("--session / --all-lifecycle / --all-sessions 중 하나 필요")

    log.info("정합성 게이트: %d 케이스", len(cases))
    failed, skipped, passed = [], [], 0
    pol_pass, pol_fail = Counter(), Counter()
    for symbol, spec, cap, fee, pol in cases:
        try:
            r = compare(spec, symbol, cap, fee)
        except Exception as exc:
            r = {"skipped": f"예외: {type(exc).__name__}: {exc}"}
        if r.get("skipped"):
            log.info("%-13s %-26s SKIP — %s", symbol, pol, r["skipped"])
            skipped.append((symbol, pol, r["skipped"]))
            continue
        if r["match"]:
            passed += 1
            pol_pass[pol] += 1
            log.info("%-13s %-26s PASS  거래 %d (바 %d)", symbol, pol, r["n_backtester"], r["n_bars"])
        else:
            failed.append((symbol, pol, r))
            pol_fail[pol] += 1
            log.error("%-13s %-26s FAIL  bt=%d orch=%d (바 %d)",
                      symbol, pol, r["n_backtester"], r["n_orchestrator"], r["n_bars"])
            for d in r["diffs"]:
                log.error("      #%d bt  =%s", d["idx"], d["backtester"])
                log.error("         orch=%s", d["orchestrator"])

    print()
    log.info("결과: PASS %d / FAIL %d / SKIP %d (총 %d)",
             passed, len(failed), len(skipped), len(cases))
    log.info("폴리시별 PASS: %s", dict(pol_pass))
    if pol_fail:
        log.error("폴리시별 FAIL: %s", dict(pol_fail))
    if skipped:
        log.info("SKIP 사유 분포: %s", dict(Counter(s[2].split(":")[0] for s in skipped)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
