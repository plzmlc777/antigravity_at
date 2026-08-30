"""번 구간과 잃은 구간은 **무엇이 다른가** — 관측 가능한 상태로 추상화한다.

## 왜 (2026-08-30 밤, 대표님 지시)

"최종 결과가 이득이 아니더라도 이득 본 구간과 손해 본 구간의 특징을
추상화하라." 지금까지 이 트랙은 **전략이 되나 안 되나**만 물었다. 되는
순간과 안 되는 순간이 관측 가능한 변수로 무엇이 다른지는 안 봤다.
그게 게이트로 바뀔 수 있는 유일한 형태다.

## 무엇을 하나

전략(동결 규칙)을 2년 돌려 **120분 블록마다 성과**를 낸다. 각 블록에
**그 시점에 관측 가능한** 상태를 붙이고, 성과를 가르는 축을 찾는다.

    시장수익 1h/6h/24h/7d      그 전까지 유니버스 중앙 수익률
    실현변동성 1h/6h/24h        중앙 수익률의 표준편차
    횡단면분산                  종목 간 수익률 흩어짐
    상승비율(breadth)           오른 종목 비율
    평균상관                    종목 간 동조
    후보수                      밴드에 들어온 종목 수
    선택z_vel                   실제로 잡은 것들의 평균 극단도
    UTC시각 · 요일              시간대 효과 (교훈#85)

## 반드시 지키는 것

⚠ **선도값 금지.** 전부 블록 시작 **이전** 자료로만 만든다.
⚠ **위약 대조 필수.** 같은 특징으로 **위약 블록**을 갈랐을 때도 갈라지면
  그건 시장 성질이지 신호 성질이 아니다. 실측−위약 **증분**만 본다.
⚠ **최대통계량.** 특징 × 분위 격자를 전부 뒤지므로 위약에서도 같은 격자를
  전부 뒤진 최고가 기준선이다 (교훈#95).
⚠ **과거 변동성을 이겨라.** 어떤 상태 변수든 변동성의 대리변수이기 쉽다.
  이중정렬로 증분을 확인한다 (교훈#94).

사용:
  python3 -m scripts.research.regime_abstract --smoke 40 --reps 20
  python3 -m scripts.research.regime_abstract --reps 500
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "runs" / "bars5m"
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("regabs")

BAR = 5
WIN_H, WINDOW, DELTA, HOLD = 12, 72, 36, 24      # 60·360·180·120분
Z_LO, Z_HI, ACC_MAX = -1.25, -0.25, 0.5
MEMORY = WINDOW + DELTA + WIN_H + HOLD           # 144봉
NQ = 5                                           # 분위 수


@dataclass(frozen=True)
class Cfg:
    slots: int = 10
    fee_pct: float = 0.036
    min_bars_in_5: float = 3.0
    block_bars: int = 24
    min_per_bin: int = 60      # 분위칸 최소 블록 수
    reps: int = 500
    seed: int = 20260831


def load(files, cfg: Cfg):
    cl, hi, lo, nb = {}, {}, {}, {}
    for f in files:
        d = pd.read_parquet(f)
        if len(d) < 5_000:
            continue
        ts = pd.to_datetime(d.ts, utc=True); s = f.stem
        cl[s] = pd.Series(d.c.to_numpy(np.float32), index=ts)
        hi[s] = pd.Series(d.h.to_numpy(np.float32), index=ts)
        lo[s] = pd.Series(d.l.to_numpy(np.float32), index=ts)
        nb[s] = pd.Series(d.n.to_numpy(np.float32), index=ts)
    idx = pd.date_range(min(v.index.min() for v in cl.values()),
                        max(v.index.max() for v in cl.values()),
                        freq=f"{BAR}min", tz="UTC")
    return (pd.DataFrame(cl).reindex(idx).ffill(),
            pd.DataFrame(hi).reindex(idx).ffill(),
            pd.DataFrame(lo).reindex(idx).ffill(),
            pd.DataFrame(nb).reindex(idx).fillna(0.0), idx)


def features(CL, NB, cfg: Cfg) -> pd.DataFrame:
    """블록 시작 시점에 **관측 가능한** 상태들. 선도값은 하나도 없다."""
    lr = np.log(CL).diff()
    med = lr.median(axis=1)                       # 시장(중앙) 로그수익
    up = (lr > 0).mean(axis=1) * 100.0            # 상승 비율
    disp = lr.std(axis=1) * 100.0                 # 횡단면 분산
    F = pd.DataFrame(index=CL.index)
    for nm, k in (("1h", 12), ("6h", 72), ("24h", 288), ("7d", 2016)):
        F[f"시장수익{nm}"] = med.rolling(k).sum() * 100.0
    for nm, k in (("1h", 12), ("6h", 72), ("24h", 288)):
        F[f"변동성{nm}"] = med.rolling(k).std() * np.sqrt(k) * 100.0
    F["분산6h"] = disp.rolling(72).mean()
    F["상승비율6h"] = up.rolling(72).mean()
    F["상승비율변화"] = up.rolling(72).mean() - up.rolling(72).mean().shift(72)
    # 평균 상관의 대리 — 시장 변동성 대비 횡단면 분산이 작으면 동조가 크다
    F["동조6h"] = (med.rolling(72).std() * 100.0) / (F["분산6h"] + 1e-9)
    F["거래활성"] = (NB.mean(axis=1).rolling(72).mean()
                    / (NB.mean(axis=1).rolling(2016).mean() + 1e-9))
    F["UTC시각"] = CL.index.hour.astype(float)
    F["요일"] = CL.index.dayofweek.astype(float)
    # ⚠ 전부 **한 봉 밀어** 블록 시작 전 정보만 남긴다
    keep = [c for c in F.columns if c not in ("UTC시각", "요일")]
    F[keep] = F[keep].shift(1)
    return F


def strategy_blocks(CL, HI, LO, NB, cfg: Cfg):
    """동결 규칙을 돌려 블록별 성과 + 블록별 신호 상태를 낸다."""
    n = len(CL)
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    fw = CL.shift(-WIN_H) / CL - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(WINDOW, min_periods=WINDOW // 2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    acc = vel - vel.shift(DELTA)
    p_ = rate.clip(0.01, 0.99)
    se = np.sqrt(p_ * (1 - p_) / (WINDOW / WIN_H))
    ZV = (vel / (se * np.sqrt(2))).to_numpy()
    ZA = (acc / (se * 2.0)).to_numpy()
    C = CL.to_numpy(np.float64)
    RET = np.full_like(C, np.nan)
    RET[:n-HOLD] = (C[HOLD:] / C[:n-HOLD] - 1.0) * 100.0 - cfg.fee_pct
    OK = live & (ZV >= Z_LO) & (ZV <= Z_HI) & (ZA < ACC_MAX) & np.isfinite(RET)
    return ZV, RET, OK


def realize(RET, OK, ZV, cfg: Cfg, shift: int = 0):
    """슬롯 실현. `shift` 는 수익률 판을 통째로 미는 회전 위약."""
    n = RET.shape[0]
    R = np.roll(RET, shift, axis=0) if shift else RET
    held: dict = {}
    tb, mm, nn = [], [], []
    for k in range(MEMORY, n - HOLD):
        for s in [s for s, v in held.items() if v <= k]:
            held.pop(s)
        free = cfg.slots - len(held)
        if free <= 0:
            continue
        cand = np.where(OK[k])[0]
        cand = np.array([c for c in cand if c not in held], dtype=int)
        if not len(cand):
            continue
        pick = cand[np.argsort(ZV[k][cand], kind="stable")][:free]
        vals = R[k][pick]
        vals = vals[np.isfinite(vals)]
        if not len(vals):
            continue
        for s in pick:
            held[int(s)] = k + HOLD
        tb.append(k); mm.append(float(vals.mean())); nn.append(len(vals))
    tb = np.asarray(tb); mm = np.asarray(mm); nn = np.asarray(nn, float)
    if not len(tb):
        return None
    blk = tb // cfg.block_bars
    d = pd.DataFrame({"blk": blk, "m": mm, "n": nn, "bar": tb})
    g = d.groupby("blk")
    # ⚠ 블록 성과는 **거래 가중**이다 — 거래가 많은 시각이 자본을 더 넣은 시각
    return pd.DataFrame({
        "블록성과": g.apply(lambda x: np.average(x.m, weights=x.n),
                          include_groups=False),
        "거래수": g.n.sum(), "첫봉": g.bar.min()})


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--reps", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    fs = sorted(CACHE.glob("*.parquet"))
    if a.smoke:
        fs = fs[:a.smoke]
    log.info("설정 %s · 종목 %d", json.dumps(asdict(cfg), ensure_ascii=False), len(fs))

    t0 = time.time()
    CL, HI, LO, NB, idx = load(fs, cfg)
    log.info("판 %s봉 × %d종목 · %.1f분", f"{len(CL):,}", CL.shape[1],
             (time.time()-t0)/60)
    F = features(CL, NB, cfg)
    ZV, RET, OK = strategy_blocks(CL, HI, LO, NB, cfg)
    log.info("특징 %d종 · 후보 %s건 · %.1f분", F.shape[1], f"{int(OK.sum()):,}",
             (time.time()-t0)/60)

    B = realize(RET, OK, ZV, cfg)
    if B is None:
        raise SystemExit("거래가 하나도 없다 — 밴드/생존 조건을 확인하라")
    Fb = F.iloc[B["첫봉"].to_numpy()].reset_index(drop=True)
    B = B.reset_index(drop=True)
    log.info("블록 %s개 · 거래 %s건 · 블록평균 %.4f%%", f"{len(B):,}",
             f"{int(B.거래수.sum()):,}", float(B.블록성과.mean()))

    feats = list(F.columns)
    print(f"\n■ 전체 — 블록 {len(B):,}개 · 거래 {int(B.거래수.sum()):,}건 · "
          f"블록평균 {B.블록성과.mean():+.4f}% · t "
          f"{B.블록성과.mean()/(B.블록성과.std(ddof=1)/np.sqrt(len(B))):+.2f}")

    # ── 단변량 분위 — 관측
    def profile(y: np.ndarray, Fm: pd.DataFrame) -> pd.DataFrame:
        rr = []
        for c in feats:
            x = Fm[c].to_numpy(float)
            m = np.isfinite(x) & np.isfinite(y)
            if m.sum() < NQ * cfg.min_per_bin:
                continue
            xm, ym = x[m], y[m]
            q = pd.qcut(pd.Series(xm).rank(method="first"), NQ,
                        labels=False, duplicates="drop")
            means = [ym[q == i].mean() for i in range(NQ)]
            ns = [int((q == i).sum()) for i in range(NQ)]
            if min(ns) < cfg.min_per_bin:
                continue
            hi_, lo_ = ym[q == NQ-1], ym[q == 0]
            sp = hi_.mean() - lo_.mean()
            se = np.sqrt(hi_.var(ddof=1)/len(hi_) + lo_.var(ddof=1)/len(lo_))
            rr.append({"특징": c, "최하": means[0], "2": means[1], "3": means[2],
                       "4": means[3], "최상": means[4], "최상-최하": sp,
                       "t": sp/se if se > 0 else np.nan, "n": int(m.sum())})
        return pd.DataFrame(rr)

    P = profile(B.블록성과.to_numpy(float), Fb)
    P = P.sort_values("t", key=abs, ascending=False)
    print("\n■ 단변량 분위 — 각 특징의 최하~최상 분위 블록평균(%)")
    print(P.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    # ── 회전 위약: **같은 특징으로 위약 블록을 갈랐을 때** 얼마나 갈라지나
    rng = np.random.default_rng(cfg.seed)
    nbar = RET.shape[0]
    null = np.empty(cfg.reps)
    percell: dict = {c: [] for c in P.특징}
    for i in range(cfg.reps):
        sh = int(rng.integers(MEMORY + HOLD, nbar - MEMORY - HOLD))
        Bp = realize(RET, OK, ZV, cfg, shift=sh)
        if Bp is None or Bp.empty:
            null[i] = 0.0
            continue
        Fp = F.iloc[Bp["첫봉"].to_numpy()].reset_index(drop=True)
        Pp = profile(Bp.블록성과.to_numpy(float), Fp)
        if Pp.empty:
            null[i] = 0.0
            continue
        null[i] = float(Pp.t.abs().max())
        for r in Pp.itertuples():
            if r.특징 in percell:
                percell[r.특징].append(abs(r.t))
        if (i+1) % 25 == 0:
            log.info("위약 %d/%d · 귀무중앙 %.2f · %.1f분", i+1, cfg.reps,
                     float(np.median(null[:i+1])), (time.time()-t0)/60)
    obs = float(P.t.abs().max())
    pm = float((null >= obs).mean())
    P["위약중앙|t|"] = [float(np.median(percell[c])) if percell.get(c) else np.nan
                       for c in P.특징]
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(P)}특징 × {NQ}분위)")
    print(f"  관측 최대 |t| {obs:.2f} · 귀무 중앙 {np.median(null):.2f} "
          f"· 95분위 {np.quantile(null,.95):.2f} · 최대 {null.max():.2f}")
    print(f"  **p = {pm:.3f}**")
    print("\n■ 특징별 관측 |t| 대 위약 중앙 |t| (증분이 있는 것만 의미)")
    print(P[["특징", "최상-최하", "t", "위약중앙|t|", "n"]].to_string(
        index=False, float_format=lambda x: f"{x:.4f}"))

    OUT.mkdir(parents=True, exist_ok=True)
    P.to_csv(OUT / "regime_abstract.csv", index=False)
    B.assign(**{c: Fb[c] for c in feats}).to_csv(
        OUT / "regime_blocks.csv", index=False)
    (OUT / "regime_abstract.null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "reps": cfg.reps, "blocks": int(len(B)),
         "null_median": float(np.median(null)),
         "null_p95": float(np.quantile(null, .95))}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
