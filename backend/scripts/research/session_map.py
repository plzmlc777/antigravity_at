"""세션 지형 — 아시아·유럽·미주가 각각 무엇을 만드는가. 2년 5분봉.

## 왜 (2026-08-31, 대표님 지시)

연속 횡단면 선별이 통행료에서 막혔다(여섯 계열 · 회수율 0~117%). 세션 기반은
하루 최대 세 번 거래하고 세션 한 칸이 보통 1~2% 움직이니 **통행료 비율이
두 자릿수 유리하다** — 애초에 그 벽에 안 걸리는 자리다.

전략을 짜기 전에 지형부터 그린다. 어느 세션이 움직임을 만드는지 모르면
연관성을 잰다는 말이 성립하지 않는다.

## 구획 (UTC · 겹치지 않게 24시간을 넷으로)

    아시아  00:00-08:00   09-17 KST · 도쿄/서울 정규장
    유럽    08:00-13:00   09-14 런던
    미주    13:00-21:00   09-17 뉴욕 (13-16 은 유럽과 겹치는 진짜 피크)
    야간    21:00-24:00

## 재는 것 (종목 × 날짜 × 세션)

    ret    세션 수익률(%)          펀딩 반영 전 순수 가격
    vol    5분 로그수익 표준편차(%)
    vshare 그 날 거래대금 중 이 세션 몫
    rng    (고-저)/시가 평균

⚠ 판정이 아니라 **지형**이다. 여기서 뭘 고르든 그 다음에 위약·최대통계량으로
  다시 재야 한다.
⚠ 날짜는 UTC 기준. 세션은 UTC 시각으로 정의하므로 한 UTC 날짜 안에 넷이
  차례로 들어온다 — 날짜 경계와 세션 경계가 어긋나지 않는다.

사용:
  python3 -m scripts.research.session_map --smoke
  python3 -m scripts.research.session_map
  python3 -m scripts.research.session_map --cache runs/bars5m_oos
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "research_track" / "session_2026_08_31"
log = logging.getLogger("sessmap")

SESS = [("아시아", 0, 8), ("유럽", 8, 13), ("미주", 13, 21), ("야간", 21, 24)]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default="runs/bars5m")
    p.add_argument("--smoke", type=int, default=0, help="N종목만")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    t0 = time.time()
    fs = sorted((ROOT/a.cache).glob("*.parquet"))
    if a.smoke:
        fs = fs[:a.smoke]
    parts = []
    for i, f in enumerate(fs, 1):
        d = pd.read_parquet(f, columns=["ts", "h", "l", "c", "v", "n"])
        if len(d) < 5_000:
            continue
        ts = pd.to_datetime(d.ts, utc=True)
        d = d.assign(ts=ts, date=ts.dt.normalize(), hour=ts.dt.hour)
        d["lr"] = np.log(d.c.clip(lower=1e-12)).diff()
        d["hl"] = (d.h - d.l)/d.c.clip(lower=1e-12)*100.0
        lab = pd.Series("", index=d.index, dtype=object)
        for nm, a_, b_ in SESS:
            lab[(d.hour >= a_) & (d.hour < b_)] = nm
        d["sess"] = lab
        g = d.groupby(["date", "sess"], sort=False)
        r = pd.DataFrame({
            "bars": g.size(),
            "nsum": g.n.sum(),
            "ret": g.c.last()/g.c.first()*0 + 0.0,      # 아래에서 정확히
            "vol": g.lr.std()*100.0,
            "rng": g.hl.mean(),
            "vsum": g.v.sum(),
        })
        # 세션 수익률 — **첫 봉 시가가 없으므로** 직전 세션 종가 대비로 잡지 않고
        # 세션 안 첫 종가 → 마지막 종가로 잡는다(세션 내부 움직임만 본다)
        r["ret"] = (g.c.last()/g.c.first() - 1.0)*100.0
        r = r.reset_index()
        r["symbol"] = f.stem
        parts.append(r)
        if i % 40 == 0 or i == len(fs):
            log.info("[%d/%d] 행 %s · %.1f분", i, len(fs),
                     f"{sum(len(x) for x in parts):,}", (time.time()-t0)/60)
    R = pd.concat(parts, ignore_index=True)
    R = R[R.sess != ""]
    # 하루 거래대금 몫
    tot = R.groupby(["symbol", "date"]).vsum.transform("sum")
    R["vshare"] = 100.0*R.vsum/tot.replace(0, np.nan)
    # 커버리지 — 세션마다 봉이 다 찼는지(결손이 조용히 섞이면 전부 오독된다)
    full = {nm: (b_-a_)*12 for nm, a_, b_ in SESS}
    R["full"] = R.sess.map(full)
    # ⚠ 열 이름 `cov` 는 DataFrame.cov 메서드와 충돌한다 — R.cov 가 함수가 된다
    R["cover"] = 100.0*R.bars/R["full"]
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "oos" if "oos" in a.cache else "is"
    R.to_parquet(OUT / f"session_map_{tag}.parquet", index=False)

    ok = R[R.cover >= 90]
    print(f"\n■ 세션 지형 — 종목 {R.symbol.nunique()} · 날짜 {R.date.nunique()} "
          f"· 행 {len(R):,} (봉 90% 이상만 {len(ok):,})")
    t = ok.groupby("sess").agg(
        행=("ret", "size"), 커버리지=("cover", "median"),
        평균수익=("ret", "mean"), 중앙수익=("ret", "median"),
        수익SD=("ret", "std"), 변동성=("vol", "median"),
        고저폭=("rng", "median"), 거래대금몫=("vshare", "median"))
    t = t.reindex([s[0] for s in SESS])
    print(t.round(4).to_string())
    print("\n■ 시간당으로 고르면 (세션 길이가 다르다)")
    hrs = {nm: b_-a_ for nm, a_, b_ in SESS}
    t2 = pd.DataFrame({
        "시간": pd.Series(hrs),
        "시간당수익": t.평균수익/pd.Series(hrs),
        "시간당SD": t.수익SD/np.sqrt(pd.Series(hrs)),
        "시간당거래대금몫": t.거래대금몫/pd.Series(hrs)})
    print(t2.round(4).to_string())
    print("\n■ 세션 수익률 상관 (같은 종목·같은 날, 종목별 평균)")
    piv = ok.pivot_table(index=["symbol", "date"], columns="sess", values="ret")
    piv = piv[[s[0] for s in SESS]]
    print(piv.corr().round(3).to_string())
    print(f"\n  짝 완비 행 {len(piv.dropna()):,}")
    log.info("저장 %s · %.1f분", OUT, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
