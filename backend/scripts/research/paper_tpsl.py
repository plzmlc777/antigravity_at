"""페이퍼 원장에 **익절·손절**을 사후 적용한다. 거울 대조 포함.

## 왜 (2026-09-01, 대표님 지시)

페이퍼 14갈래는 **시간 만기가 유일한 청산 조건**이고 익절·손절이 없다
(`kinematics_paper.py` 머리말: "보유 120분 · 익절·손절 없음"). 의도된 설계다 —
규칙을 넣으면 성과가 신호 덕인지 규칙 덕인지 안 갈린다.

그 대가가 잡음6 분포에 그대로 보인다.

    이긴 거래 39건(59.1%) 평균 **+1.833%**
    진 거래  27건(40.9%) 평균 **-2.049%**   ← 지는 쪽이 더 크다
    최악 -10.41% · 최고 +10.57%
    상위 3건(전부 ZORA)이 자본 기여의 **159%**

승률이 높은데 총손익이 소수 거래에 걸린 구조다. 손절이 그 꼬리를 자르면
달라지는가.

## 규약

⚠ **거울 대조 필수**(교훈#91) — 같은 규칙을 방향 뒤집어 돌린다. 양쪽 다 벌면
  규칙 효과가 아니라 국면 효과다. 이 트랙은 그걸로 한 번 속았다.
⚠ **방향맞춤 위약** — 같은 규칙을 무작위 진입에 적용한다.
⚠ 익절·손절이 같은 5분 봉에서 둘 다 닿으면 **손절 먼저**로 본다(보수적).
  그 경우가 몇 건인지 **세어서 남긴다** — 많으면 틱으로 재해석해야 한다.
⚠ 손절 체결가를 문턱 그대로 쓴다. 실제 손절은 시장가라 미끄러진다 —
  **이 표는 손절에 유리하게 기울어 있다**(교훈#107). 선별용으로만 쓴다.
⚠ 기준선은 **규칙 없음**(현행). 그걸 못 이기면 넣을 이유가 없다.

사용:
  python3 -m scripts.research.paper_tpsl --smoke
  python3 -m scripts.research.paper_tpsl
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
LED = ROOT / "runs" / "kinematics_paper"
BARS = ROOT / "runs" / "tickbars5m"
OUT = ROOT / "runs" / "research_track" / "paper_tpsl_2026_09_01"
log = logging.getLogger("tpsl")

BRANCHES = [("s1", "롱1"), ("s10", "롱10"), ("s20", "롱20"),
            ("s10short", "숏10"), ("s10both", "롱숏10"),
            ("s10both_d30", "롱숏d30"), ("s6both_d5_noise", "잡음6"),
            ("s6both", "롱숏3"), ("s2both", "속도저울")]
SLS = [None, 1.0, 2.0, 3.0, 5.0]
TPS = [None, 2.0, 3.0, 5.0, 8.0]
FEE = 0.072


def load_bars():
    """종목별 5분 고가·저가·종가. 틱에서 만든 것(runs/tickbars5m)."""
    B = {}
    for f in sorted(BARS.glob("*.parquet")):
        d = pd.read_parquet(f, columns=["ts_ms", "hi", "lo", "cl"])
        if len(d) < 100:
            continue
        d["ts"] = pd.to_datetime(d.ts_ms, unit="ms", utc=True)
        B[f.stem] = d.set_index("ts")[["hi", "lo", "cl"]].sort_index()
    return B


def apply_rule(path_hi, path_lo, path_cl, entry, short, sl, tp):
    """(순수익%, 사유). 손절·익절이 같은 봉이면 **손절 먼저**(보수적)."""
    if short:
        # 숏 — 가격이 오르면 손절, 내리면 익절
        sl_px = entry*(1 + sl/100) if sl else None
        tp_px = entry*(1 - tp/100) if tp else None
        for h, l in zip(path_hi, path_lo):
            hit_sl = sl_px is not None and h >= sl_px
            hit_tp = tp_px is not None and l <= tp_px
            if hit_sl:
                return -sl, "손절"
            if hit_tp:
                return tp, "익절"
    else:
        sl_px = entry*(1 - sl/100) if sl else None
        tp_px = entry*(1 + tp/100) if tp else None
        for h, l in zip(path_hi, path_lo):
            hit_sl = sl_px is not None and l <= sl_px
            hit_tp = tp_px is not None and h >= tp_px
            if hit_sl:
                return -sl, "손절"
            if hit_tp:
                return tp, "익절"
    r = 100.0*(path_cl[-1]/entry - 1.0)
    return (-r if short else r), "만기"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--smoke", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    t0 = time.time()
    B = load_bars()
    log.info("틱 5분봉 %d종목 · %.1f분", len(B), (time.time()-t0)/60)

    br = BRANCHES[:2] if a.smoke else BRANCHES
    T = []
    for tag, lab in br:
        f = LED/tag/"trades.csv"
        if not f.exists():
            continue
        d = pd.read_csv(f)
        if not len(d):
            continue
        d["갈래"] = lab
        T.append(d)
    D = pd.concat(T, ignore_index=True)
    D["entry"] = pd.to_datetime(D.entry_ts, utc=True)
    D["exit"] = pd.to_datetime(D.exit_ts, utc=True)
    D["is_short"] = D.short.astype(str).str.lower().isin(["true", "1", "1.0"])
    log.info("원장 %s거래 · 갈래 %d · %.1f분", f"{len(D):,}", D.갈래.nunique(),
             (time.time()-t0)/60)

    # 거래마다 보유 구간 경로를 한 번만 뽑는다
    paths, miss = [], 0
    for r in D.itertuples():
        b = B.get(r.symbol)
        if b is None:
            paths.append(None); miss += 1; continue
        seg = b.loc[(b.index > r.entry) & (b.index <= r.exit)]
        if len(seg) < 2:
            paths.append(None); miss += 1; continue
        paths.append((seg.hi.to_numpy(float), seg.lo.to_numpy(float),
                      seg.cl.to_numpy(float)))
    log.info("경로 확보 %s / %s (결손 %d) · %.1f분",
             f"{len(D)-miss:,}", f"{len(D):,}", miss, (time.time()-t0)/60)
    ok = np.array([x is not None for x in paths])

    rng = np.random.default_rng(20260901)
    rows = []
    for mirror in (False, True):
        for sl in SLS:
            for tp in TPS:
                out, why = [], []
                amb = 0
                for i, r in enumerate(D.itertuples()):
                    if paths[i] is None:
                        continue
                    hi, lo, cl = paths[i]
                    sh = (not r.is_short) if mirror else r.is_short
                    v, w = apply_rule(hi, lo, cl, r.entry_px, sh, sl, tp)
                    # 같은 봉에서 둘 다 닿았는지 — 세어만 둔다
                    if sl and tp:
                        e = r.entry_px
                        if sh:
                            amb += int(((hi >= e*(1+sl/100)) &
                                        (lo <= e*(1-tp/100))).any())
                        else:
                            amb += int(((lo <= e*(1-sl/100)) &
                                        (hi >= e*(1+tp/100))).any())
                    out.append(v - FEE); why.append(w)
                v = np.asarray(out)
                if len(v) < 50:
                    continue
                srt = np.sort(v); k = max(1, int(round(len(v)*0.05)))
                wh = pd.Series(why).value_counts(normalize=True)
                rows.append({
                    "방향": "거울" if mirror else "원본",
                    "손절": sl if sl else 0.0, "익절": tp if tp else 0.0,
                    "거래": len(v), "거래당": v.mean(),
                    "상5제외": srt[:-k].mean(), "승률": 100*(v > 0).mean(),
                    "SD": v.std(ddof=1), "최악": v.min(), "최고": v.max(),
                    "만기%": 100*wh.get("만기", 0), "손절%": 100*wh.get("손절", 0),
                    "익절%": 100*wh.get("익절", 0), "동시봉": amb})
        log.info("  %s 완료 · %.1f분", "거울" if mirror else "원본",
                 (time.time()-t0)/60)
    R = pd.DataFrame(rows)
    base = float(R[(R.방향 == "원본") & (R.손절 == 0) & (R.익절 == 0)].거래당.iloc[0])
    R["기준대비"] = R.거래당 - base
    print(f"\n■ 익절·손절 사후 격자 — 원장 {int(ok.sum()):,}거래 · "
          f"왕복 {FEE}% · 기준선(규칙 없음) {base:+.4f}%")
    for mir in ("원본", "거울"):
        s = R[R.방향 == mir].sort_values("거래당", ascending=False)
        print(f"\n  [{mir}] 상위 8")
        print(s.head(8)[["손절", "익절", "거래당", "상5제외", "승률", "SD",
                         "최악", "만기%", "손절%", "익절%", "기준대비"]].to_string(
            index=False, float_format=lambda z: f"{z:+.3f}"))
    print("\n■ 거울 대조 — 같은 규칙이 양방향 다 벌면 **규칙이 아니라 국면**이다")
    m = R.pivot_table(index=["손절", "익절"], columns="방향", values="거래당")
    m["합"] = m.sum(axis=1)
    print(m.sort_values("원본", ascending=False).head(10).to_string(
        float_format=lambda z: f"{z:+.4f}"))
    print(f"\n  원본·거울 **둘 다 양수**인 칸 "
          f"{int(((m.원본 > 0) & (m.거울 > 0)).sum())}/{len(m)}")
    amb = int(R.동시봉.max())
    print(f"  익절·손절이 같은 봉에서 둘 다 닿은 거래 최대 {amb}건 "
          f"({100*amb/max(int(ok.sum()),1):.1f}%) — 손절 먼저로 처리")
    OUT.mkdir(parents=True, exist_ok=True)
    R.to_csv(OUT / "grid.csv", index=False)
    log.info("저장 %s · %.1f분", OUT, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
