"""2군 리그 18석 — **lookahead 수정본으로 백테스트** (신상저격수와 같은 기간).

왜 (대표님 지시, 2026-08-12)
  2군 리그 18석의 표시 수익(+33.55%, +32.57% …)은 전부 lookahead 무효 구간이다.
  재시뮬 결과 2군 13세션 누적 **+245.55% → +11.32%**, 성과의 95.4%가 편향이었다.
  유효구간(2026-08-09~) 거래는 487건 중 **3건**뿐이라 8/23 까지는 판정이 안 된다.

  그런데 소스는 이미 고쳐져 있다 (커밋 `cd0ca27f`, 2026-08-08: 트리거를 **다음**
  eval 봉에 부착). **고친 소스로 과거를 다시 돌리면 8/23 을 기다리지 않고
  답이 나온다.** 페이퍼가 앞으로 낼 값을 미리 재는 것이다.

  그리고 신상저격수와 **같은 기간·같은 마찰**로 재야 비교가 성립한다.

설계
  · 각 세션의 **실제 pipeline_spec** 을 그대로 읽어 `build_pipeline` 으로 재현한다.
    파라미터를 다시 적지 않는다 — 운영과 같은 코드 경로를 쓴다.
  · 구간을 둘로 나눈다:
        표본 안  R-4 이전 (신상저격수와 같은 분할선 2026-05-13)
        표본 밖  이후
  · 실행은 정책 그대로 (진입 임계 / SL / TP / max_hold_bars).
    진입은 **신호 다음 봉 시가**. lookahead 방지.
  · 마찰: 테이커 왕복 10bp + 종목 실측 스프레드.
  · 집중도(상위 k건 제외)를 같이 낸다 — 신상저격수에서 이게 결정적이었다.

사용:
  python3 scripts/research/tier2_league_backtest.py
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
for noisy in ("app.composer_framework.orchestrator", "paper_session_cli",
              "app.composer_framework.pipeline_spec"):
    logging.getLogger(noisy).setLevel(logging.ERROR)
log = logging.getLogger("tier2_bt")

STATE = ROOT / "runs" / "tier_governor" / "state.json"
SPLIT = pd.Timestamp("2026-05-13")     # 신상저격수 R-4 판정일 — 같은 분할선
TAKER_RT_BP = 10.0


def run_spec(symbol: str, spec: dict, bundle, split: pd.Timestamp):
    """세션 스펙 그대로 신호를 만들고, 정책대로 체결한다. 진입은 신호 **다음 봉**."""
    from app.composer_framework import build_pipeline
    from app.composer_framework.signal_source import SourceContext

    df = bundle.ohlcv_eval
    if df is None or len(df) < 200:
        return None
    rt = {"symbol": symbol, "ohlcv_1m": bundle.ohlcv_1m, "ohlcv_eval": df}
    for fld in ("signals_df", "flow_df", "binance_metrics_5m", "binance_funding_df",
                "binance_oi_df", "binance_premium_df", "btc_ohlcv_1m"):
        if hasattr(bundle, fld):
            rt[fld] = getattr(bundle, fld)
    eval_freq = int((spec.get("config") or {}).get("eval_freq_minutes", 5))
    pipe = build_pipeline(spec, rt)
    feats = pipe.build_features(SourceContext(
        symbol=symbol, eval_freq_minutes=eval_freq,
        ohlcv_1m=bundle.ohlcv_1m, ohlcv_eval=df))
    # Pipeline 은 compose 가 아니라 fit/predict 다. passthrough 컴포저는 fit 이
    # 무연산이지만 인터페이스를 그대로 따른다 (운영 경로와 동일하게).
    try:
        pipe.fit(feats)
    except Exception:
        pass
    pred = pipe.predict(feats)
    if pred is None or not len(pred):
        return None
    pol = (spec.get("policy") or {}).get("kwargs", {})
    thr = float(pol.get("entry_threshold", 0.5))
    sl = float(pol.get("sl_pct", 0.99))
    tp = float(pol.get("tp_pct", 0.99))
    hold = int(pol.get("max_hold_bars", 15))

    o = df["open"].astype(float).values
    hi = df["high"].astype(float).values
    lo = df["low"].astype(float).values
    idx = df.index
    # pred 는 feats 순서와 1:1 인 numpy 배열이다. DatetimeIndex 로 reindex 하면
    # 정수 인덱스와 안 맞아 **전부 NaN** 이 된다 (2026-08-12 실수).
    p = np.asarray(pred, dtype=float)
    if len(p) != len(idx):
        m = min(len(p), len(idx))
        p = p[-m:]
        idx = idx[-m:]
        o, hi, lo = o[-m:], hi[-m:], lo[-m:]
    trades = []
    i = 1
    n = len(idx)
    while i < n - 1:
        v = p[i - 1]                       # **직전 봉 신호로 이번 봉 시가 진입**
        if not np.isfinite(v) or abs(v) < thr:
            i += 1
            continue
        side = 1 if v > 0 else -1
        e = o[i]
        if e <= 0:
            i += 1
            continue
        stop = e * (1 - sl) if side > 0 else e * (1 + sl)
        take = e * (1 + tp) if side > 0 else e * (1 - tp)
        end = min(i + hold, n - 1)
        ret, k = None, end
        for k in range(i + 1, end + 1):
            if side > 0 and lo[k] <= stop:
                ret = -sl * 100; break
            if side < 0 and hi[k] >= stop:
                ret = -sl * 100; break
            if side > 0 and hi[k] >= take:
                ret = tp * 100; break
            if side < 0 and lo[k] <= take:
                ret = tp * 100; break
        if ret is None:
            ret = (o[k] / e - 1.0) * 100 * side
        trades.append({"ts": idx[i], "ret": ret - TAKER_RT_BP / 100})
        i = k + 1                          # 겹침 금지
    return trades


def stats(a: np.ndarray) -> dict:
    if not len(a):
        return {"n": 0}
    se = a.std(ddof=1) / np.sqrt(len(a)) if len(a) > 1 else np.nan
    return {"n": len(a), "mean": float(a.mean()), "median": float(np.median(a)),
            "win": float(100 * (a > 0).mean()), "t": float(a.mean() / se) if se else np.nan,
            "sum": float(a.sum())}


def main() -> int:
    p = argparse.ArgumentParser(description="2군 리그 백테스트")
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "tier2_league_backtest.json"))
    args = p.parse_args()

    st = json.load(open(STATE))
    alias = json.load(open(ROOT / "configs" / "strategy_aliases.json"))
    AL = alias.get("aliases", {})

    def disp(name):
        for k, v in AL.items():
            if k in name:
                return v
        return name[:20]

    from paper_session_cli import build_runtime_bundle
    rows = []
    for sid in st["sessions"]:
        f = ROOT / "runs" / "paper_sessions" / sid / "session.json"
        if not f.exists():
            continue
        j = json.load(open(f))
        sym, spec = j["symbol"], j["pipeline_spec"]
        eval_freq = int((spec.get("config") or {}).get("eval_freq_minutes", 5))
        sources_used = [x.get("type") for x in (spec.get("sources") or [])]
        try:
            bundle = build_runtime_bundle(sym, eval_freq, sources_used)
        except Exception as exc:
            log.warning("%s %s 번들 실패: %s", sid[:8], sym, exc)
            continue
        try:
            tr = run_spec(sym, spec, bundle, SPLIT)
        except Exception as exc:
            log.warning("%s %s 실행 실패: %s: %s", sid[:8], sym, type(exc).__name__, exc)
            continue
        if not tr:
            log.info("%s %s 거래 0", sid[:8], sym)
            continue
        T = pd.DataFrame(tr)
        ins = T[T.ts < SPLIT].ret.values
        oos = T[T.ts >= SPLIT].ret.values
        rows.append({"sid": sid, "alias": disp(j["name"]), "symbol": sym,
                     "status": j.get("status"), "n": len(T),
                     "ins": stats(ins), "oos": stats(oos), "all": stats(T.ret.values),
                     "span": [str(T.ts.min())[:10], str(T.ts.max())[:10]]})
        log.info("%-10s %-12s 거래 %4d (안 %3d / 밖 %3d)",
                 disp(j["name"]), sym, len(T), len(ins), len(oos))

    if not rows:
        log.error("결과 없음")
        return 1

    print("\n" + "=" * 112)
    print(f"2군 리그 백테스트 — lookahead 수정본 / 분할선 {SPLIT.date()} "
          f"(신상저격수와 동일) / 마찰 테이커 왕복 10bp")
    print("=" * 112)
    print(f"{'별칭':<10}{'종목':<12}{'상태':<12}{'거래':>6}"
          f"{'[표본 안] n':>11}{'평균%':>9}{'승률':>7}{'t':>7}"
          f"{'[표본 밖] n':>12}{'평균%':>9}{'승률':>7}{'t':>7}")
    print("-" * 112)
    for r in sorted(rows, key=lambda x: (x["alias"], -x["all"]["mean"])):
        i_, o_ = r["ins"], r["oos"]
        print(f"{r['alias']:<10}{r['symbol']:<12}{str(r['status']):<12}{r['n']:>6}"
              f"{i_.get('n',0):>11}{i_.get('mean',0):>+9.3f}{i_.get('win',0):>7.1f}"
              f"{i_.get('t',0):>+7.2f}"
              f"{o_.get('n',0):>12}{o_.get('mean',0):>+9.3f}{o_.get('win',0):>7.1f}"
              f"{o_.get('t',0):>+7.2f}")
    print("-" * 112)
    fam = {}
    for r in rows:
        fam.setdefault(r["alias"], []).append(r)
    print("  계열별 (거래 풀링)")
    print(f"  {'별칭':<10}{'좌석':>5}{'[안] n':>8}{'평균%':>9}{'t':>8}"
          f"{'[밖] n':>9}{'평균%':>9}{'t':>8}")
    for a, v in sorted(fam.items(), key=lambda kv: -len(kv[1])):
        ni = sum(x["ins"].get("n", 0) for x in v)
        no = sum(x["oos"].get("n", 0) for x in v)
        mi = np.average([x["ins"]["mean"] for x in v if x["ins"].get("n")],
                        weights=[x["ins"]["n"] for x in v if x["ins"].get("n")]) if ni else 0
        mo = np.average([x["oos"]["mean"] for x in v if x["oos"].get("n")],
                        weights=[x["oos"]["n"] for x in v if x["oos"].get("n")]) if no else 0
        ti = np.mean([x["ins"]["t"] for x in v if x["ins"].get("n", 0) > 5]) if ni else 0
        to = np.mean([x["oos"]["t"] for x in v if x["oos"].get("n", 0) > 5]) if no else 0
        print(f"  {a:<10}{len(v):>5}{ni:>8}{mi:>+9.3f}{ti:>+8.2f}{no:>9}{mo:>+9.3f}{to:>+8.2f}")
    print("=" * 112 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"split": str(SPLIT.date()), "rows": rows}, fh,
                  indent=2, ensure_ascii=False, default=str)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
