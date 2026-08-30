"""번 구간과 잃은 구간을 **서술한다** — p값이 아니라 날짜와 모양으로.

## 왜 (2026-08-31 새벽, 대표님 지시 ②)

추론은 끝났다 — 구조가 없다:

    관측 가능한 상태 15종으로 갈리지 않는다   p 0.713 / 0.175
    지속되지 않는다                          자기상관 0 · 런 2.07 = 무작위 2.00
    어떤 국면에도 마찰을 못 넘는다            75칸 중 74칸 음수
    어느 종목에서도 안 된다                  p 0.733

그런데 "구조가 없다"를 p값으로만 말하면 불충분하다. **실제로 어떻게 생겼는지**
보여야 한다. 그리고 서술에서만 보이는 성질이 있다 — 집중도·꼬리·자본곡선 모양.

## 무엇을 내나

    ① 자본곡선            2년 단리 누적. 위약 20개 계열을 배경으로 깐다
    ② 상·하위 20블록      날짜 · 그때 시장이 뭘 했나 · 얼마였나
    ③ 집중도              상위 N블록이 총손익의 몇 %인가 (복권인가)
    ④ 분포                왜도·첨도·분위. 위약과 나란히
    ⑤ 달별 표             언제 벌고 언제 잃었나 (사람이 읽는 형태)

⚠ 서술이지 검정이 아니다. **위약을 나란히 놓지 않으면 아무 이야기나 만들어진다** —
  무작위 계열도 "2025년 3월에 특히 좋았다"는 서술을 낳는다.

사용:
  python3 -m scripts.research.profile_periods --smoke 80
  python3 -m scripts.research.profile_periods
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import text                                     # noqa: E402

from app.db.session import engine                               # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "runs" / "bars5m"
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("profile")

BAR, ANCH, Q = 5, 12, 0.2
FEE2 = 0.072
SIG_BARS, HOLD_H, DELAY = 12, 24, 1


@dataclass(frozen=True)
class Cfg:
    min_syms: int = 20
    min_bars_in_5: float = 3.0
    n_placebo: int = 200
    seed: int = 20260831


def load(files):
    cl, nb = {}, {}
    for f in files:
        d = pd.read_parquet(f)
        if len(d) < 5_000:
            continue
        ts = pd.to_datetime(d.ts, utc=True)
        cl[f.stem] = pd.Series(d.c.to_numpy(np.float32), index=ts)
        nb[f.stem] = pd.Series(d.n.to_numpy(np.float32), index=ts)
    idx = pd.date_range(min(v.index.min() for v in cl.values()),
                        max(v.index.max() for v in cl.values()),
                        freq=f"{BAR}min", tz="UTC")
    return (pd.DataFrame(cl).reindex(idx).ffill(),
            pd.DataFrame(nb).reindex(idx).fillna(0.0), idx)


def funding_cum(syms, idx):
    q = text("SELECT funding_time, funding_rate FROM binance_funding_rate "
             "WHERE symbol=:s AND funding_time >= :a AND funding_time < :b "
             "ORDER BY funding_time")
    a = idx.min().tz_convert(None); b = idx.max().tz_convert(None)
    cum = np.zeros((len(idx), len(syms)), np.float32)
    with engine.connect() as c:
        c.execute(text("SET statement_timeout='240s'"))
        for j, s in enumerate(syms):
            r = c.execute(q, {"s": s, "a": a, "b": b}).all()
            if not r:
                continue
            t = pd.to_datetime([x[0] for x in r], utc=True)
            v = np.asarray([float(x[1]) for x in r], np.float64) * 100.0
            pos = np.clip(idx.searchsorted(t, side="left"), 0, len(idx)-1)
            acc = np.zeros(len(idx)); np.add.at(acc, pos, v)
            cum[:, j] = np.cumsum(acc).astype(np.float32)
    return cum


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--smoke", type=int, default=0)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg()
    fs = sorted(CACHE.glob("*.parquet"))
    if a.smoke:
        fs = fs[:a.smoke]
    t0 = time.time()
    CL, NB, idx = load(fs)
    syms = list(CL.columns); n = len(CL)
    CUM = funding_cum(syms, idx)
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    C = CL.to_numpy(np.float32)
    lr = np.log(CL).diff()
    mkt = (lr.median(axis=1) * 100.0).to_numpy()
    r = np.full(C.shape, np.nan, np.float32)
    r[SIG_BARS:] = (C[SIG_BARS:] / C[:-SIG_BARS] - 1.0) * 100.0
    X = np.where(live, -r, np.nan)
    k, d = HOLD_H * 12, DELAY
    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - k - d
    R[:hi_] = ((C[d+k:d+k+hi_] / C[d:d+hi_] - 1.0) * 100.0
               - (CUM[d+k:d+k+hi_] - CUM[d:d+hi_]))
    warm = SIG_BARS + 12
    anc = np.arange(warm, n - k - d - 1)
    anc = anc[anc % ANCH == 0]
    XA, RA = X[anc], R[anc]
    na = len(anc)
    pos = np.arange(0, na - HOLD_H - 1, HOLD_H)
    x = XA[pos]
    good = np.isfinite(x).sum(1) >= cfg.min_syms
    x = x[good]
    with np.errstate(invalid="ignore"):
        qs = np.nanquantile(x, [Q, 1-Q], axis=1)
    ok = qs[1] > qs[0]
    x = x[ok]
    rows = pos[good][ok]
    TOP, BOT = x >= qs[1][ok][:, None], x <= qs[0][ok][:, None]
    ts = idx[anc[rows]]

    def ser(Rm):
        rr = Rm[rows]
        with np.errstate(invalid="ignore"):
            return (np.nanmean(np.where(TOP, rr, np.nan), axis=1)
                    - np.nanmean(np.where(BOT, rr, np.nan), axis=1)) - FEE2

    v = ser(RA)
    m = np.isfinite(v)
    v, tsv, rowsv = v[m], ts[m], rows[m]
    log.info("비겹침 블록 %d개 · %s ~ %s · %.1f분", len(v),
             tsv.min().date(), tsv.max().date(), (time.time()-t0)/60)

    rng = np.random.default_rng(cfg.seed)
    mem = HOLD_H * 2 + SIG_BARS
    PL = []
    for _ in range(cfg.n_placebo):
        sh = int(rng.integers(mem, na - mem))
        w = ser(np.roll(RA, sh, axis=0))
        PL.append(w[np.isfinite(w)])
    L = min(len(v), min(len(w) for w in PL))
    PLm = np.vstack([w[:L] for w in PL])

    print(f"\n■ 실측 — 블록 {len(v)}개 · 단리합 {v.sum():+.2f}% · "
          f"평균 {v.mean():+.4f}% · 승률 {100*(v>0).mean():.1f}%")
    print(f"  위약 {cfg.n_placebo}계열 — 단리합 중앙 {np.median(PLm.sum(1)):+.2f}% "
          f"· 5~95분위 [{np.quantile(PLm.sum(1),.05):+.1f}, "
          f"{np.quantile(PLm.sum(1),.95):+.1f}]")

    print("\n■ 분포 — 실측 대 위약")
    def dist(w):
        s = pd.Series(w)
        return {"평균": s.mean(), "표준편차": s.std(), "왜도": s.skew(),
                "첨도": s.kurt(), "p05": s.quantile(.05), "중앙": s.median(),
                "p95": s.quantile(.95), "최악": s.min(), "최고": s.max()}
    dd = pd.DataFrame([{"계열": "실측", **dist(v)},
                       {"계열": "위약중앙", **{k_: np.median([dist(w)[k_]
                        for w in PLm]) for k_ in dist(v)}}])
    print(dd.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))

    print("\n■ 집중도 — 상위 N블록이 단리합의 몇 %인가")
    srt = np.sort(v)[::-1]
    tot = v.sum()
    cc = []
    for nn in (1, 5, 10, 20, 50):
        if nn <= len(srt):
            pl_ = np.median([np.sort(w)[::-1][:nn].sum() / max(w.sum(), 1e-9)
                             for w in PLm])
            cc.append({"상위N": nn, "합": srt[:nn].sum(),
                       "총합대비%": 100*srt[:nn].sum()/tot if tot else np.nan,
                       "위약중앙%": 100*pl_})
    print(pd.DataFrame(cc).to_string(index=False,
                                     float_format=lambda z: f"{z:+.1f}"))

    print("\n■ 상위 10블록 / 하위 10블록 — 날짜와 그때 시장")
    mk24 = pd.Series(mkt).rolling(288).sum().to_numpy()
    def show(ix, label):
        rr = []
        for i in ix:
            b = anc[rowsv[i]]
            rr.append({"구분": label, "시각(UTC)": str(tsv[i])[:16],
                       "스프레드": v[i], "직전24h시장": mk24[b]})
        return rr
    hi10 = np.argsort(v)[::-1][:10]; lo10 = np.argsort(v)[:10]
    print(pd.DataFrame(show(hi10, "최고") + show(lo10, "최악")).to_string(
        index=False, float_format=lambda z: f"{z:+.3f}"))

    print("\n■ 달별 (단리합 %) — 실측 대 위약 5~95분위")
    dfm = pd.DataFrame({"ym": tsv.to_period("M").astype(str), "v": v})
    g = dfm.groupby("ym").v.agg(["sum", "size", "mean"])
    pm_ = []
    for w in PLm:
        dd2 = pd.DataFrame({"ym": tsv[:L].to_period("M").astype(str), "v": w})
        pm_.append(dd2.groupby("ym").v.sum())
    P = pd.DataFrame(pm_)
    g["위약p05"] = P.quantile(.05).reindex(g.index).to_numpy()
    g["위약p95"] = P.quantile(.95).reindex(g.index).to_numpy()
    g["위약밖"] = np.where(g["sum"] > g["위약p95"], "↑",
                          np.where(g["sum"] < g["위약p05"], "↓", ""))
    print(g.to_string(float_format=lambda z: f"{z:+.2f}"))
    nout = int((g["위약밖"] != "").sum())
    print(f"\n  달 {len(g)}개 중 위약 90% 구간 밖: **{nout}개** "
          f"(우연이면 {0.1*len(g):.1f}개)")

    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ts": tsv, "spread": v}).to_csv(
        OUT / "profile_blocks.csv", index=False)
    g.to_csv(OUT / "profile_monthly.csv")
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
