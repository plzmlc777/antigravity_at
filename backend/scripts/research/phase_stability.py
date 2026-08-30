"""일중 시각 효과가 **분기에 걸쳐 일관된가** — 열린 실마리의 마지막 검정.

## 왜 (2026-08-31 06:30)

위상 점검에서 나온 것:

    시각별 변동은 두 구간 모두 위약을 압도한다   IS p 0.010 · OOS p 0.000
    그런데 **패턴이 안 남는다**                  회전 상관 3~7위 · p 0.125~0.292
    다만 네 profile 이 전부 **UTC 01시 최고**    ← 사후 관찰

⚠ UTC 01 은 자료를 **보고 나서** 찾았다. 같은 자료를 분기로 쪼개 UTC 01 만
  검정하면 독립 증거가 아니다.

그래서 질문을 바꾼다 — **어떤 시각이든 분기에 걸쳐 일관되게 상위인 시각이
있는가?** 24시각 전체가 대상이고 최대통계량이 다중검정을 처리하므로
사전지정이 필요 없다.

두 구간이 우연히 맞는 것과 16분기 중 14분기가 맞는 것은 완전히 다르다.

## 통계량

각 분기 안에서 24위상의 **순위**를 매기고, 시각마다 분기 평균 순위를 낸다.
우연이면 12.5 다. 통계량은 **최고 시각의 평균 순위**(작을수록 좋다 → 부호 뒤집어
최대통계량으로). 위약도 같은 24시각을 전부 뒤져 최고를 낸다.

⚠ 순위를 쓰는 이유 — 분기마다 변동성 수준이 달라 원값을 평균하면 큰 분기가
  지배한다. 순위는 각 분기 안에서만 비교한다.

사용:
  python3 -m scripts.research.phase_stability --reps 300
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import text                                     # noqa: E402

from app.db.session import engine                               # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("pstab")

BAR, ANCH = 5, 12
SIG_BARS, HOLD_H, DELAY = 12, 24, 1
FEE1 = 0.036
SLOT = 10


@dataclass(frozen=True)
class Cfg:
    min_bars_in_5: float = 3.0
    min_blocks_q: int = 15      # 분기당 위상별 최소 블록
    reps: int = 300
    seed: int = 20260831


def load(files):
    cl, nb, vv = {}, {}, {}
    for f in files:
        d = pd.read_parquet(f)
        if len(d) < 5_000:
            continue
        ts = pd.to_datetime(d.ts, utc=True); s = f.stem
        cl[s] = pd.Series(d.c.to_numpy(np.float32), index=ts)
        nb[s] = pd.Series(d.n.to_numpy(np.float32), index=ts)
        vv[s] = pd.Series(d.v.to_numpy(np.float32), index=ts)
    idx = pd.date_range(min(v.index.min() for v in cl.values()),
                        max(v.index.max() for v in cl.values()),
                        freq=f"{BAR}min", tz="UTC")
    return (pd.DataFrame(cl).reindex(idx).ffill(),
            pd.DataFrame(nb).reindex(idx).fillna(0.0),
            pd.DataFrame(vv).reindex(idx).fillna(0.0), idx)


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
    p.add_argument("--signal", default="되돌림", choices=["되돌림", "거래량"])
    p.add_argument("--reps", type=int, default=None)
    p.add_argument("--delays", default="1",
                   help="진입 지연(봉) 쉼표 구분. UTC01 이 정시 경계의 미시구조면 "
                        "늦출수록 사라진다")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    t0 = time.time()
    # ⚠ 두 캐시를 **합쳐** 4년을 만든다. 종목 집합이 다르므로 교집합만 쓴다
    A = {x.stem for x in (ROOT/"runs"/"bars5m").glob("*.parquet")}
    B = {x.stem for x in (ROOT/"runs"/"bars5m_oos").glob("*.parquet")}
    common = sorted(A & B)
    log.info("교집합 %d종목 (2024~ %d · 2022~ %d)", len(common), len(A), len(B))
    parts = []
    for s in common:
        d1 = pd.read_parquet(ROOT/"runs"/"bars5m_oos"/f"{s}.parquet")
        d2 = pd.read_parquet(ROOT/"runs"/"bars5m"/f"{s}.parquet")
        d = pd.concat([d1, d2], ignore_index=True).drop_duplicates("ts")
        d["sym"] = s
        parts.append(d)
    cl = {s: g.set_index(pd.to_datetime(g.ts, utc=True)).c.astype(np.float32)
          for s, g in pd.concat(parts).groupby("sym")}
    nb = {s: g.set_index(pd.to_datetime(g.ts, utc=True)).n.astype(np.float32)
          for s, g in pd.concat(parts).groupby("sym")}
    vv = {s: g.set_index(pd.to_datetime(g.ts, utc=True)).v.astype(np.float32)
          for s, g in pd.concat(parts).groupby("sym")}
    del parts
    idx = pd.date_range(min(v.index.min() for v in cl.values()),
                        max(v.index.max() for v in cl.values()),
                        freq=f"{BAR}min", tz="UTC")
    CL = pd.DataFrame(cl).reindex(idx).ffill()
    NB = pd.DataFrame(nb).reindex(idx).fillna(0.0)
    V = pd.DataFrame(vv).reindex(idx).fillna(0.0)
    del cl, nb, vv
    syms = list(CL.columns); n = len(CL)
    CUM = funding_cum(syms, idx)
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    C = CL.to_numpy(np.float32)
    if a.signal == "거래량":
        v1 = V.rolling(SIG_BARS).sum()
        v24 = V.rolling(288).sum().shift(SIG_BARS) / 24.0
        X = np.where(live, -(v1/(v24+1e-9)).to_numpy(np.float32), np.nan)
    else:
        r = np.full(C.shape, np.nan, np.float32)
        r[SIG_BARS:] = (C[SIG_BARS:] / C[:-SIG_BARS] - 1.0) * 100.0
        X = np.where(live, -r, np.nan)
    DL = [int(x) for x in a.delays.split(",")]
    kk = HOLD_H*12
    RD = {}
    for d in DL:
        f = np.full(C.shape, np.nan, np.float32)
        hi_ = n - kk - d
        f[:hi_] = ((C[d+kk:d+kk+hi_] / C[d:d+hi_] - 1.0)*100.0
                   - (CUM[d+kk:d+kk+hi_] - CUM[d:d+hi_]))
        RD[d] = f
    R = RD[DL[0]]
    base = np.arange(300, n - kk - max(DL) - 1)
    base = base[base % ANCH == 0]
    XA, RA = X[base], R[base]
    na = len(base)
    qtr = pd.Series(idx[base]).dt.to_period("Q").astype(str).to_numpy()
    hours = idx[base].hour.to_numpy()
    log.info("판 %s봉 × %d종목 · 앵커 %s · %s ~ %s · 분기 %d · %.1f분",
             f"{n:,}", len(syms), f"{na:,}", idx[base].min().date(),
             idx[base].max().date(), len(set(qtr)), (time.time()-t0)/60)

    def profile_by_quarter(Rm):
        """분기 × 시각 평균. 분기 안에서 순위를 매긴다."""
        rec = {}
        for ph in range(HOLD_H):
            pos = np.arange(ph, na - HOLD_H - 1, HOLD_H)
            vals, qs = [], []
            for i in pos:
                x, rr = XA[i], Rm[i]
                m = np.isfinite(x) & np.isfinite(rr)
                if m.sum() < 2*SLOT + 10:
                    continue
                ii = np.where(m)[0]
                o = ii[np.argsort(x[ii])]
                vals.append(float(rr[o[-SLOT:]].mean() - rr[o[:SLOT]].mean())
                            - 2*FEE1)
                qs.append(qtr[i])
            if not vals:
                continue
            df = pd.DataFrame({"q": qs, "v": vals})
            g = df.groupby("q").agg(m=("v", "mean"), n=("v", "size"))
            g = g[g.n >= cfg.min_blocks_q]
            rec[int(np.median(hours[pos]))] = g.m
        M = pd.DataFrame(rec)                       # 분기 × 시각
        M = M.dropna(axis=0, how="any")
        if M.empty or M.shape[1] < 20:
            return None, None
        # ⚠ 분기 안에서 **순위**. 원값 평균은 변동성 큰 분기가 지배한다
        Rk = M.rank(axis=1, ascending=False)
        return M, Rk

    if len(DL) > 1:
        # ⚠ 지연 감쇠부터 본다 — 정시 경계 미시구조면 늦출수록 사라진다
        print(f"\n■ 최고 시각의 진입 지연 감쇠 (신호 {a.signal} · 슬롯 {SLOT})")
        rows = []
        for d in DL:
            Md, _ = profile_by_quarter(RD[d][base])
            if Md is None:
                continue
            mm = Md.mean()
            best = mm.idxmax()
            rows.append({"지연분": d*BAR, "최고시각": f"UTC{int(best):02d}",
                         "그 값": float(mm.max()),
                         "UTC01": float(mm.get(1, np.nan)),
                         "전체평균": float(Md.values.mean()),
                         "UTC01양수분기": int((Md[1] > 0).sum()) if 1 in Md else -1,
                         "분기수": len(Md)})
        D = pd.DataFrame(rows)
        print(D.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
        if len(D) > 1 and D.UTC01.iloc[0]:
            print("  UTC01 5분 대비 남은 비율(%): " + " · ".join(
                f"{int(r.지연분)}분 {100*r.UTC01/D.UTC01.iloc[0]:.0f}"
                for r in D.itertuples()))
    M, Rk = profile_by_quarter(RA)
    if M is None:
        raise SystemExit("분기 × 시각 표를 못 만들었다")
    mean_rank = Rk.mean(axis=0).sort_values()
    print(f"\n■ 분기 {len(M)}개 × 시각 {M.shape[1]}개 · 신호 {a.signal} · 슬롯 {SLOT}")
    print("  각 분기 안에서 매긴 순위의 평균 (1=최고, 우연이면 12.5)")
    print("\n  상위 6시각: " + " · ".join(
        f"UTC{h:02d} {v:.2f}" for h, v in mean_rank.head(6).items()))
    print("  하위 6시각: " + " · ".join(
        f"UTC{h:02d} {v:.2f}" for h, v in mean_rank.tail(6).items()))
    print(f"\n  최고 시각 UTC{int(mean_rank.index[0]):02d} — 분기별 순위: "
          + " ".join(f"{int(x)}" for x in Rk[mean_rank.index[0]]))

    rng = np.random.default_rng(cfg.seed)
    obs = float(mean_rank.iloc[0])
    # ⚠ **순위 통과와 수준 통과는 다르다.** 24시각이 전부 음수면 최고 시각도
    #   덜 나쁜 것에 불과하다. 수준의 최대통계량을 나란히 낸다.
    obs_lv = float(M.mean().max())
    null = np.full(cfg.reps, np.nan); null_lv = np.full(cfg.reps, np.nan)
    for i in range(cfg.reps):
        sh = int(rng.integers(HOLD_H, na - HOLD_H))
        M2, Rk2 = profile_by_quarter(np.roll(RA, sh, axis=0))
        if Rk2 is not None:
            null[i] = float(Rk2.mean(axis=0).min())
            null_lv[i] = float(M2.mean().max())
        if (i+1) % 25 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    nn = null[np.isfinite(null)]
    pm = float((nn <= obs).mean())
    print(f"\n■ 회전 위약 최대통계량 ({len(nn)}회 · 24시각 전부 뒤짐)")
    print(f"  관측 최고 평균순위 {obs:.3f} · 귀무 중앙 {np.median(nn):.3f} "
          f"· 5분위 {np.quantile(nn,.05):.3f}")
    print(f"  **p = {pm:.3f}**  (작을수록 좋다 — 일관되게 상위인 시각이 있다는 뜻)")
    nlv = null_lv[np.isfinite(null_lv)]
    plv = float((nlv >= obs_lv).mean())
    print(f"\n■ **수준**의 최대통계량 (같은 위약 · 24시각 전부)")
    print(f"  관측 최고 시각 평균 {obs_lv:+.4f}% · 귀무 중앙 {np.median(nlv):+.4f}% "
          f"· 95분위 {np.quantile(nlv,.95):+.4f}%")
    print(f"  **p = {plv:.3f}**")
    print(f"  전체 24시각 평균 {float(M.values.mean()):+.4f}% "
          f"· 양수 시각 {int((M.mean()>0).sum())}/24")
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "vol" if a.signal == "거래량" else "rev"
    M.to_csv(OUT / f"phase_stability_{tag}_means.csv")
    Rk.to_csv(OUT / f"phase_stability_{tag}_ranks.csv")
    (OUT / f"phase_stability_{tag}.null.json").write_text(json.dumps(
        {"obs_best_mean_rank": obs, "best_hour": int(mean_rank.index[0]),
         "p_rank": pm, "obs_best_level": obs_lv, "p_level": plv,
         "reps": int(len(nn)), "quarters": int(len(M)),
         "null_rank_median": float(np.median(nn)),
         "null_level_median": float(np.median(nlv))}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
