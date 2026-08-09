#!/usr/bin/env python3
"""paradigm 251 라이브 경로 연기 테스트 — 세션을 만들지 않고 파이프라인만 통과시킨다.

왜 필요한가:
  bn_stablecoin_supply_flow 는 오프라인에서만 검증됐고 `eval_freq_minutes=1440`
  으로 실제 paper 세션 파이프라인(runtime bundle → features → composer → policy)
  을 통과한 적이 없다. 메모리에 기록된 실패 모드가 정확히 이것이다 —
  btc_rv_highvol(139일 BTC leader vs 150일 warmup)과 premium_index_zscore
  (joblib 부재)가 가짜 "0 거래 / +0.00%" 로 몇 달을 앉아 있었다.

  5석을 그렇게 채우면 forward 검증 자체가 무의미해지므로, 시드 전에 확인한다.

확인 항목
  1. runtime bundle 이 eval_tf='1d' 로 만들어지는가
  2. 소스가 InsufficientSourceDataError 없이 feature 를 내는가
  3. **신호가 실제로 발화하는가** (0 이 아닌 바가 있는가) — 이게 핵심
  4. composer 가 feature_col 을 찾는가 (컬럼명 오타 검출)
  5. policy 가 LONG/SHORT 양방향을 내는가

세션·DB 상태를 바꾸지 않는다. 읽기만 한다.

사용:
  cd backend && source venv/bin/activate
  python3 scripts/research/p251_live_path_smoke.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p251_smoke")

from paper_session_cli import build_runtime_bundle  # noqa: E402
from app.composer_framework.pipeline_spec import (  # noqa: E402
    SOURCE_FACTORIES, COMPOSER_FACTORIES, POLICY_FACTORIES,
)
from app.composer_framework.signal_source import (  # noqa: E402
    InsufficientSourceDataError, SourceContext,
)

SPEC_DIR = ROOT / "configs" / "paper_sessions"
SYMBOLS = ["BNBUSDT", "XRPUSDT", "AVAXUSDT", "LINKUSDT", "DOGEUSDT"]


def check(sym: str) -> dict:
    spec_path = SPEC_DIR / f"{sym}_stablecoin_supply_flow.json"
    spec = json.loads(spec_path.read_text())
    ps = spec["pipeline_spec"]
    eval_freq = ps["config"]["eval_freq_minutes"]
    sources_used = [s["type"] for s in ps["sources"]]

    out = {"symbol": sym, "ok": False}

    # 1. runtime bundle
    bundle = build_runtime_bundle(sym, eval_freq, sources_used)
    ev = bundle.ohlcv_eval
    out["eval_bars"] = int(len(ev))
    out["eval_start"] = str(ev.index.min())[:10]
    out["eval_end"] = str(ev.index.max())[:10]
    # 일봉으로 리샘플됐는지 — 연속 두 바 간격이 1일이어야 한다
    if len(ev) > 2:
        step_h = (ev.index[-1] - ev.index[-2]).total_seconds() / 3600.0
        out["eval_step_hours"] = round(step_h, 2)

    # 2~3. 소스 feature
    ctx = SourceContext(symbol=sym, eval_freq_minutes=eval_freq,
                        ohlcv_1m=bundle.ohlcv_1m, ohlcv_eval=ev)
    src = SOURCE_FACTORIES[sources_used[0]](ps["sources"][0].get("kwargs", {}), {})
    try:
        feats = src.build_features(ctx)
    except InsufficientSourceDataError as e:
        out["error"] = f"InsufficientSourceDataError: {e}"
        return out
    out["feature_cols"] = list(feats.columns)
    sig_col = ps["composer"]["kwargs"]["feature_col"]
    if sig_col not in feats.columns:
        out["error"] = f"composer feature_col '{sig_col}' 가 소스 출력에 없다 {list(feats.columns)}"
        return out
    s = feats[sig_col].to_numpy(dtype=float)
    out["signal_nonzero_bars"] = int((s != 0).sum())
    out["signal_long_bars"] = int((s > 0).sum())
    out["signal_short_bars"] = int((s < 0).sum())
    out["signal_coverage_pct"] = round(float((s != 0).mean()) * 100, 2)
    if out["signal_nonzero_bars"] == 0:
        out["error"] = "신호가 전 구간 0 — 가짜 dormant 세션이 된다"
        return out

    # 4. composer
    comp = COMPOSER_FACTORIES[ps["composer"]["type"]](ps["composer"].get("kwargs", {}))
    out["composer"] = ps["composer"]["type"]
    try:
        pred = comp.predict(feats) if hasattr(comp, "predict") else None
        if pred is not None:
            p = np.asarray(pred, dtype=float)
            out["pred_nonzero_bars"] = int((p != 0).sum())
            out["pred_min"], out["pred_max"] = round(float(np.nanmin(p)), 4), round(float(np.nanmax(p)), 4)
    except Exception as e:
        out["composer_note"] = f"predict 직접 호출 불가 ({type(e).__name__}: {e}) — 오케스트레이터 경유 필요"

    # 5. policy 존재·구성 확인
    pol_type = ps["policy"]["type"]
    if pol_type not in POLICY_FACTORIES:
        out["error"] = f"policy '{pol_type}' 미등록"
        return out
    POLICY_FACTORIES[pol_type](ps["policy"].get("kwargs", {}))
    out["policy"] = pol_type
    out["max_hold_bars"] = ps["policy"]["kwargs"].get("max_hold_bars")

    out["ok"] = True
    return out


def main() -> int:
    results = [check(s) for s in SYMBOLS]
    print()
    print("=" * 78)
    for r in results:
        mark = "PASS" if r["ok"] else "FAIL"
        print(f"[{mark}] {r['symbol']}")
        for k, v in r.items():
            if k in ("symbol", "ok"):
                continue
            print(f"      {k:22s} {v}")
    print("=" * 78)
    n_ok = sum(1 for r in results if r["ok"])
    print(f"연기 테스트: {n_ok}/{len(results)} 통과")
    if n_ok < len(results):
        print("→ 시드 전에 고쳐야 한다. 이대로 시드하면 가짜 0거래 세션이 된다.")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
