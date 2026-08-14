"""독주자·사중주 — **walk-forward 재검정** (in-sample fit 정정).

왜 (2026-08-12)
  두 세션은 규칙 신호가 아니라 **LGBM 모델**이다 (composer: lgbm, refit 30일).
  그런데 내 백테스트는 `pipe.fit(feats)` → `pipe.predict(feats)` 를 **같은
  데이터로** 했다. 전 구간으로 학습한 모델로 그 전 구간을 예측한 것이므로
  "표본 밖"이 표본 밖이 아니었다.

  그렇게 나온 값(표본 밖 t +2.18/+2.37, 승률 93.8~100%, 손익비 제거 시
  +15.576%)은 전부 **in-sample 재현**이다. 전량 무효로 하고 여기서 다시 잰다.

walk-forward 설계
  · 일봉, 재학습 주기 30일 (세션의 refit_interval_days 그대로).
  · 학습은 **확장 창** — 재학습 시점까지의 전 구간.
  · **타깃 누출 차단**: 타깃 `target_fwd_ret` 은 forward_bars 만큼 미래를 본다.
    학습 구간 끝의 마지막 forward_bars 개는 테스트 구간을 훔쳐보므로 잘라낸다.
    이걸 안 하면 walk-forward 를 해도 여전히 새는 것이다.
  · 예측은 그 다음 30일에만. 이어 붙이면 순수 표본 밖 예측열이 된다.
  · 최소 학습 표본 200개 확보 후 시작.

실행
  · 원 정책(sl 6% / tp 15%)과 손익비 제거를 같이 돌린다.
  · 진입은 신호 **다음 봉 시가**. 마찰 테이커 왕복 10bp.
  · 대조군: **예측을 무작위로 섞은 것**(shuffle). 같은 진입 횟수·같은 구간에서
    모델이 무작위를 이기는지 본다. 이게 이번 검정의 핵심 관문이다.

사용:
  python3 scripts/research/tier2_ml_walkforward.py
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
for n in ("app.composer_framework.orchestrator", "paper_session_cli",
          "app.composer_framework.pipeline"):
    logging.getLogger(n).setLevel(logging.ERROR)
log = logging.getLogger("ml_wf")

TARGETS = {"880bbb6d-97b": "사중주 ICPUSDT", "30a107ba-293": "독주자 WLDUSDT"}
FRIC = 0.10
MIN_TRAIN = 200


def build(sid: str):
    from paper_session_cli import build_runtime_bundle
    from app.composer_framework import build_pipeline
    from app.composer_framework.signal_source import SourceContext
    j = json.load(open(ROOT / "runs" / "paper_sessions" / sid / "session.json"))
    spec, sym = j["pipeline_spec"], j["symbol"]
    ef = int(spec["config"]["eval_freq_minutes"])
    fb = int(spec["config"].get("forward_bars", 1))
    refit = int(j.get("refit_interval_days") or 30)
    b = build_runtime_bundle(sym, ef, [x["type"] for x in spec["sources"]])
    rt = {"symbol": sym, "ohlcv_1m": b.ohlcv_1m, "ohlcv_eval": b.ohlcv_eval}
    for f in ("signals_df", "flow_df", "binance_metrics_5m", "binance_funding_df",
              "binance_oi_df", "binance_premium_df", "btc_ohlcv_1m"):
        if hasattr(b, f):
            rt[f] = getattr(b, f)
    pipe = build_pipeline(spec, rt)
    feats = pipe.build_features(SourceContext(
        symbol=sym, eval_freq_minutes=ef, ohlcv_1m=b.ohlcv_1m, ohlcv_eval=b.ohlcv_eval))
    return j, spec, sym, ef, fb, refit, pipe, feats, b.ohlcv_eval


def walk_forward(spec, pipe, feats, fb: int, refit_bars: int):
    """확장 창 walk-forward. 반환: 표본 밖 예측 시리즈."""
    from app.composer_framework import build_pipeline
    idx = feats.index
    n = len(feats)
    preds = pd.Series(np.nan, index=idx)
    start = MIN_TRAIN + fb
    t = start
    n_fit = 0
    while t < n:
        end = min(t + refit_bars, n)
        # **타깃 누출 차단** — 학습 구간 끝에서 forward_bars 만큼 잘라낸다
        tr = feats.iloc[: max(t - fb, 0)]
        te = feats.iloc[t:end]
        if len(tr) < MIN_TRAIN or not len(te):
            t = end
            continue
        try:
            pipe.fit(tr)
            n_fit += 1
            preds.iloc[t:end] = np.asarray(pipe.predict(te), dtype=float)
        except Exception as exc:
            log.warning("fit 실패 @%s: %s", idx[t], exc)
        t = end
    return preds, n_fit


def execute(pred: pd.Series, df: pd.DataFrame, thr, sl, tp, hold):
    o = df["open"].astype(float).values
    hi = df["high"].astype(float).values
    lo = df["low"].astype(float).values
    idx = df.index
    m = min(len(pred), len(idx))
    p = pred.values[-m:]
    idx, o, hi, lo = idx[-m:], o[-m:], hi[-m:], lo[-m:]
    out, i, n = [], 1, len(idx)
    while i < n - 1:
        v = p[i - 1]
        if not np.isfinite(v) or abs(v) < thr:
            i += 1
            continue
        side = 1 if v > 0 else -1
        e = o[i]
        if e <= 0:
            i += 1
            continue
        end = min(i + hold, n - 1)
        ret, k = None, end
        if sl is not None:
            stop = e * (1 - sl) if side > 0 else e * (1 + sl)
            take = e * (1 + tp) if side > 0 else e * (1 - tp)
            for k in range(i + 1, end + 1):
                if (side > 0 and lo[k] <= stop) or (side < 0 and hi[k] >= stop):
                    ret = -sl * 100
                    break
                if (side > 0 and hi[k] >= take) or (side < 0 and lo[k] <= take):
                    ret = tp * 100
                    break
        if ret is None:
            ret = (o[k] / e - 1.0) * 100 * side
        out.append({"ts": idx[i], "ret": ret - FRIC})
        i = k + 1
    return pd.DataFrame(out)


def st(a):
    if len(a) < 3:
        return f"n={len(a):>4}  표본부족"
    se = a.std(ddof=1) / np.sqrt(len(a))
    return (f"n={len(a):>4}  {a.mean():+7.3f}%  t {a.mean()/se:+6.2f}  "
            f"승률 {100*(a>0).mean():5.1f}%")


def main() -> int:
    p = argparse.ArgumentParser(description="ML 세션 walk-forward")
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "tier2_ml_walkforward.json"))
    args = p.parse_args()
    rng = np.random.default_rng(20260812)
    res = {}
    print("\n" + "=" * 98)
    print("독주자·사중주 walk-forward — 확장 창 / 30일 재학습 / 타깃 누출 차단")
    print("=" * 98)
    for sid, lab in TARGETS.items():
        j, spec, sym, ef, fb, refit, pipe, feats, df = build(sid)
        refit_bars = refit if ef >= 1440 else refit * (1440 // ef)
        pred, n_fit = walk_forward(spec, pipe, feats, fb, refit_bars)
        valid = int(pred.notna().sum())
        pol = spec["policy"]["kwargs"]
        thr = float(pol["entry_threshold"])
        sl0, tp0 = float(pol["sl_pct"]), float(pol["tp_pct"])
        hold = int(pol["max_hold_bars"])
        print(f"\n■ {lab}   재학습 {n_fit}회 / 표본밖 예측 {valid}봉 / "
              f"forward_bars {fb} / 임계 {thr}")
        rows = {}
        for name, sl, tp in (("원 정책 (15:6)", sl0, tp0), ("손익비 제거", None, None)):
            T = execute(pred, df, thr, sl, tp, hold)
            a = T.ret.values if len(T) else np.array([])
            print(f"   {name:<16} {st(a)}")
            rows[name] = {"n": len(a), "mean": float(a.mean()) if len(a) else None,
                          "t": float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a))))
                          if len(a) > 2 else None}
        # 대조군 — 예측을 섞어 같은 구간에서 무작위와 비교
        sh = pred.copy()
        v = sh.dropna().values.copy()
        rng.shuffle(v)
        sh.loc[sh.notna()] = v
        Ts = execute(sh, df, thr, sl0, tp0, hold)
        a2 = Ts.ret.values if len(Ts) else np.array([])
        print(f"   {'**무작위 대조**':<16} {st(a2)}")
        rows["shuffle"] = {"n": len(a2), "mean": float(a2.mean()) if len(a2) else None}
        res[lab] = rows
    print("=" * 98 + "\n")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(res, open(args.out, "w"), ensure_ascii=False, indent=2)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
