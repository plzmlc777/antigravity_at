"""횡단면 되돌림은 **언제** 작동하나 — 번 구간과 잃은 구간의 추상화.

## 왜 (2026-08-31 새벽, 대표님 지시 ②)

"최종 결과가 이득이 아니더라도 이득 본 구간과 손해 본 구간의 특징을 추상화하라."

축 자체는 종결됐다 — 충격12봉 × 보유24h 의 수익은 **전부 숏 다리**에서 나오고
(롱 -0.019 / 숏 +0.121), 무작위 숏이 +0.087% 를 벌어 신호 몫은 +0.019%p 뿐이다
(p 0.392). 2년 알트 하락 표류였다.

그래도 **국면 질문은 남는다**. 평균이 0 이어도 어떤 국면에서만 크게 벌고
다른 국면에서 잃는다면, 그 국면을 관측 가능한 변수로 가를 수 있다면
게이트가 된다. 지금까지 이 트랙은 **되나 안 되나**만 물었다.

## 추론을 t 로 하지 않는 이유

보유 24시간을 1시간 앵커로 재면 창이 **24겹**으로 겹친다. 겹친 표본의 t 는
믿을 수 없다 — 이 트랙에서 r +0.470 이 비겹침에서 +0.001 이 된 적이 있다.
그래서 **위약 분포를 눈금으로 쓴다**. 위약도 같은 겹침을 가지므로 상쇄된다.

## 반드시

⚠ 특징은 전부 **앵커 이전** 자료다. 게이트가 되려면 진입 전에 알아야 한다.
⚠ 스프레드(롱−숏)로 본다 — 시장 표류가 빠진다.
⚠ 다리도 따로 본다 — 어느 쪽이 국면을 타는지 알아야 한다.
⚠ 최대통계량 — 특징 × 분위를 전부 뒤지므로 위약도 전부 뒤진다(교훈#95).

사용:
  python3 -m scripts.research.xsec_regime --smoke 60 --reps 30
  python3 -m scripts.research.xsec_regime --reps 500
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
log = logging.getLogger("xreg")

BAR, ANCH, Q = 5, 12, 0.2
FEE1, FEE2 = 0.036, 0.072
SIG_BARS = 12          # 충격12봉 = 1시간 되돌림
HOLD_H, DELAY = 24, 1  # 보유 24시간 · 진입 5분 지연
NQ = 5


@dataclass(frozen=True)
class Cfg:
    min_syms: int = 20
    min_bars_in_5: float = 3.0
    min_per_bin: int = 200
    reps: int = 500
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


def build_features(CL, NB) -> pd.DataFrame:
    """전부 **앵커 이전** 정보. 선도값은 하나도 없다."""
    lr = np.log(CL).diff()
    med = lr.median(axis=1)
    up = (lr > 0).mean(axis=1) * 100.0
    disp = lr.std(axis=1) * 100.0
    F = pd.DataFrame(index=CL.index)
    for nm, k in (("1h", 12), ("6h", 72), ("24h", 288), ("7d", 2016)):
        F[f"시장수익{nm}"] = med.rolling(k).sum() * 100.0
    for nm, k in (("1h", 12), ("6h", 72), ("24h", 288)):
        F[f"변동성{nm}"] = med.rolling(k).std() * np.sqrt(k) * 100.0
    F["횡단면분산6h"] = disp.rolling(72).mean()
    F["분산비"] = disp.rolling(72).mean() / (disp.rolling(2016).mean() + 1e-9)
    F["상승비율6h"] = up.rolling(72).mean()
    F["상승비율변화"] = up.rolling(72).mean() - up.rolling(72).mean().shift(288)
    F["동조6h"] = (med.rolling(72).std() * 100.0) / (disp.rolling(72).mean() + 1e-9)
    F["거래활성"] = (NB.mean(axis=1).rolling(72).mean()
                    / (NB.mean(axis=1).rolling(2016).mean() + 1e-9))
    F["UTC시각"] = CL.index.hour.astype(float)
    F["요일"] = CL.index.dayofweek.astype(float)
    keep = [c for c in F.columns if c not in ("UTC시각", "요일")]
    F[keep] = F[keep].shift(1)          # 앵커 봉 자신도 빼고
    return F


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
    t0 = time.time()
    CL, NB, idx = load(fs)
    n = len(CL)
    log.info("판 %s봉 × %d종목 · %s ~ %s", f"{n:,}", CL.shape[1],
             idx.min().date(), idx.max().date())
    F = build_features(CL, NB)
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    C = CL.to_numpy(np.float32)
    r = np.full(C.shape, np.nan, np.float32)
    r[SIG_BARS:] = (C[SIG_BARS:] / C[:-SIG_BARS] - 1.0) * 100.0
    X = np.where(live, -r, np.nan)                    # 큰 값 = 롱
    k, d = HOLD_H * 12, DELAY
    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - k - d
    R[:hi_] = (C[d+k:d+k+hi_] / C[d:d+hi_] - 1.0) * 100.0

    warm = 2016 + SIG_BARS
    anc = np.arange(warm, n - k - d - 1)
    anc = anc[anc % ANCH == 0]
    Xa, Ra = X[anc], R[anc]
    Fa = F.iloc[anc].reset_index(drop=True)
    cnt = np.isfinite(Xa).sum(1)
    good = cnt >= cfg.min_syms
    Xa, Ra, Fa = Xa[good], Ra[good], Fa[good].reset_index(drop=True)
    with np.errstate(invalid="ignore"):
        qs = np.nanquantile(Xa, [Q, 1 - Q], axis=1)
    ok = qs[1] > qs[0]
    Xa, Ra, Fa = Xa[ok], Ra[ok], Fa[ok].reset_index(drop=True)
    TOP = Xa >= qs[1][ok][:, None]
    BOT = Xa <= qs[0][ok][:, None]
    rows_idx = anc[good][ok]
    log.info("앵커 %s개 (1시간 격자, 24겹 중첩) · %.1f분",
             f"{len(Ra):,}", (time.time()-t0)/60)

    feats = list(F.columns)
    QB = {}
    for c in feats:
        x = Fa[c].to_numpy(float)
        q = np.full(len(x), -1)
        m = np.isfinite(x)
        if m.sum() < NQ * cfg.min_per_bin:
            continue
        q[m] = pd.qcut(pd.Series(x[m]).rank(method="first"), NQ,
                       labels=False, duplicates="drop").to_numpy()
        if min((q == i).sum() for i in range(NQ)) < cfg.min_per_bin:
            continue
        QB[c] = q
    log.info("특징 %d종 · 분위 %d", len(QB), NQ)

    def profile(Rm: np.ndarray):
        """(특징, 분위) 별 스프레드·롱·숏 평균."""
        rr = Rm[np.arange(len(Rm))[:, None], np.arange(Rm.shape[1])] \
            if False else Rm
        with np.errstate(invalid="ignore"):
            L = np.nanmean(np.where(TOP, rr, np.nan), axis=1)
            S = np.nanmean(np.where(BOT, rr, np.nan), axis=1)
        sp = L - S
        out = {}
        for c, q in QB.items():
            v = []
            for i in range(NQ):
                m = (q == i) & np.isfinite(sp)
                v.append((float(np.nanmean(sp[m])), float(np.nanmean(L[m])),
                          float(np.nanmean(S[m]))))
            out[c] = v
        return out, sp, L, S

    OBS, sp0, L0, S0 = profile(Ra)
    print(f"\n■ 전체 — 앵커 {len(sp0):,}개 · 스프레드 {np.nanmean(sp0):+.4f}% "
          f"· 롱 {np.nanmean(L0):+.4f}% · 숏 {-np.nanmean(S0):+.4f}% "
          f"(마찰 두다리 {FEE2}%)")

    rng = np.random.default_rng(cfg.seed)
    nA = len(Ra)
    memmax = max(2016 // ANCH + HOLD_H, HOLD_H * 2)
    NUL = {c: np.empty((cfg.reps, NQ)) for c in QB}
    gnull = np.empty(cfg.reps)
    for i in range(cfg.reps):
        sh = int(rng.integers(memmax, nA - memmax))
        PL, _, _, _ = profile(np.roll(Ra, sh, axis=0))
        g = 0.0
        for c in QB:
            v = np.array([x[0] for x in PL[c]])
            NUL[c][i] = v
            g = max(g, float(np.nanmax(v) - np.nanmin(v)))
        gnull[i] = g
        if (i+1) % 25 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)

    rows, lev = [], []
    for c in QB:
        sp = np.array([x[0] for x in OBS[c]])
        lg = np.array([x[1] for x in OBS[c]])
        st = np.array([-x[2] for x in OBS[c]])
        nulmed = np.nanmedian(NUL[c], axis=0)
        exc = sp - nulmed                       # 위약 대비 증분
        rng_obs = float(np.nanmax(sp) - np.nanmin(sp))
        rng_nul = np.nanmax(NUL[c], axis=1) - np.nanmin(NUL[c], axis=1)
        # ⚠ **증분**(위약 대비)은 추론용, **수준**은 추상화용이다. 둘 다 낸다.
        #   "이 국면에서 +0.15%" 라고 말하려면 수준이 있어야 한다.
        rows.append({"특징": c,
                     **{f"e{i+1}": exc[i] for i in range(NQ)},
                     "폭": rng_obs, "위약폭중앙": float(np.nanmedian(rng_nul)),
                     "p폭": float((rng_nul >= rng_obs).mean()),
                     # 다리 기울기가 **거울처럼 대칭**이면 방향 노출이지 신호가
                     # 아니다 — 스프레드에서 상쇄된다. 비대칭인 것만 후보다.
                     "롱기울기": float(lg[-1]-lg[0]),
                     "숏기울기": float(st[-1]-st[0]),
                     "대칭도": float(abs(lg[-1]-lg[0] + st[-1]-st[0]))})
        lev.append({"특징": c,
                    **{f"Q{i+1}": sp[i] - FEE2 for i in range(NQ)},
                    "최상-최하": float(sp[-1] - sp[0])})
    D = pd.DataFrame(rows).sort_values("p폭")
    LV = pd.DataFrame(lev).set_index("특징").loc[D.특징].reset_index()
    print("\n■ 국면별 스프레드 **수준** — 수수료 후(%). 분위 낮은→높은")
    print(LV.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print("\n■ 같은 것의 **위약 대비 증분**(%) + 다리 기울기")
    print(D.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    gobs = float(D.폭.max())
    gp = float((gnull >= gobs).mean())
    print(f"\n■ 최대통계량 ({cfg.reps}회 · 특징 {len(QB)} × 분위 {NQ})")
    print(f"  관측 최대 분위폭 {gobs:.4f}%p · 귀무 중앙 {np.median(gnull):.4f}%p "
          f"· 95분위 {np.quantile(gnull,.95):.4f}%p")
    print(f"  **p = {gp:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    D.to_csv(OUT / "xsec_regime.csv", index=False)
    LV.to_csv(OUT / "xsec_regime_levels.csv", index=False)
    (OUT / "xsec_regime.null.json").write_text(json.dumps(
        {"obs_range": gobs, "p": gp, "reps": cfg.reps, "anchors": int(nA),
         "spread": float(np.nanmean(sp0)), "long": float(np.nanmean(L0)),
         "short": float(-np.nanmean(S0)),
         "null_median": float(np.median(gnull))}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
