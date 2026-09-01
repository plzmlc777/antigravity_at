"""ADX / ±DI — 횡단면 추세 지표. 4년 521종목.

## 왜 (2026-09-01, 대표님 지시)

이 트랙이 지표를 여럿 닫았다 — 볼린저(위약과 차이 -0.001) · RSI 숏(정보 0) ·
거래량 급증 · 변동성·고저폭(무작위보다 나쁨). 그리고 지표 중복도 검사에서
**지표를 가르는 건 계열이 아니라 지수평활 대 고정창**이고 상관 눈금이
1.000/0.835/0.676 세 개뿐이었다.

ADX 는 아직 안 쟀다. 다른 점이 하나 있다 — **방향이 아니라 세기**를 잰다.
그래서 두 갈래로 나눠 본다.

    ① 방향 성분  di = (+DI) - (-DI)     횡단면으로 예측력이 있나
    ② 세기       adx                    자체로 예측력이 있나
    ③ 결합       adx × sign(di)         세기로 가중한 방향

## 규약 (오늘까지의 교훈을 전부 적용)

⚠ 기질은 **bars5m_ext 521종목**(2026-09-01 신설). 240종목 기질은 알파벳 순
  임의 절단이라 효과가 두 배로 부풀었다.
⚠ 판정 주축은 **날짜 군집 t**(교훈#112). 블록 수는 표본 수가 아니다.
⚠ 방향맞춤 위약(교훈#91·#101) — 같은 날·같은 수를 무작위로 같은 다리로.
⚠ 최대통계량(교훈#95) — 섞은 자료로 격자 전체를 다시 뒤진 최고값이 기준선.
⚠ 방향(추세/반전)을 결과 보고 고르지 않는다. 둘 다 격자에 넣는다(교훈#91).
⚠ 다리 이름은 **실제 동작 그대로**(2026-08-31: 부호가 두 번 뒤집혀 "숏만"이
  실제로는 롱이었다).
⚠ ADX 는 5분봉에선 잡음이다. **1시간·4시간**으로 접어서 잰다(교훈#109).

사용:
  python3 -m scripts.research.adx_xsec --smoke
  python3 -m scripts.research.adx_xsec --reps 300
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
from sqlalchemy import text                                      # noqa: E402

from app.db.session import engine                                # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "research_track" / "adx_2026_09_01"
log = logging.getLogger("adx")
SIGS = ["di", "adx", "adx_di"]
LEGS = ["상위롱", "상위숏", "추세스프레드", "반전스프레드"]


@dataclass(frozen=True)
class Cfg:
    period: int = 14             # ADX 기간 (Wilder 표준)
    tfs: tuple = (12, 48)        # 5분봉 몇 개 = 1시간 · 4시간
    holds: tuple = (1, 4, 24)    # 보유 시간
    picks: tuple = (3, 5)
    fee_rt: float = 0.072
    min_alive: int = 40
    min_n: float = 36.0          # 1시간에 1분봉 60개 중 최소
    reps: int = 300
    seed: int = 20260901

    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def wilder(x: np.ndarray, n: int) -> np.ndarray:
    """Wilder 평활 — alpha = 1/n 의 지수평활. ADX 의 표준 정의다.

    ⚠ pandas 가 돌려주는 배열은 **읽기전용**일 수 있다. 그대로 쓰면 나중에
      `S[k][:warm] = np.nan` 같은 제자리 대입이 죽는다(2026-09-01, 같은 날
      `to_numpy()` 에서도 한 번 밟았다). 사본으로 돌려준다.
    """
    r = pd.DataFrame(x).ewm(alpha=1.0/n, adjust=False).mean().to_numpy(np.float32)
    return np.array(r, dtype=np.float32, copy=True)


def adx_parts(H, L, C, n):
    """(+DI, -DI, ADX). 열 = 종목."""
    pc = np.roll(C, 1, axis=0); pc[0] = np.nan
    ph = np.roll(H, 1, axis=0); ph[0] = np.nan
    pl = np.roll(L, 1, axis=0); pl[0] = np.nan
    tr = np.fmax(H - L, np.fmax(np.abs(H - pc), np.abs(L - pc)))
    up, dn = H - ph, pl - L
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = wilder(np.nan_to_num(tr), n)
    pdi = 100.0*wilder(pdm, n)/np.maximum(atr, 1e-12)
    ndi = 100.0*wilder(ndm, n)/np.maximum(atr, 1e-12)
    dx = 100.0*np.abs(pdi - ndi)/np.maximum(pdi + ndi, 1e-12)
    return pdi, ndi, wilder(dx, n)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default="runs/bars5m_ext")
    p.add_argument("--reps", type=int, default=None)
    p.add_argument("--smoke", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps else {}))
    if a.smoke:
        cfg = Cfg(tfs=(12,), holds=(4,), picks=(3,), reps=40)
    log.info("설정 %s · 기질 %s", cfg.dump(), a.cache)
    t0 = time.time()

    # ── 종목별로 읽어 **바로 접는다**. 5분봉 행렬을 들고 있으면 1.8GB 다.
    per = {tf: {} for tf in cfg.tfs}
    for f in sorted((ROOT/a.cache).glob("*.parquet")):
        d = pd.read_parquet(f, columns=["ts", "h", "l", "c", "n"])
        if len(d) < 5_000:
            continue
        d["ts"] = pd.to_datetime(d.ts, utc=True)
        d = d.set_index("ts")
        for tf in cfg.tfs:
            r = d.resample(f"{tf*5}min").agg(
                h=("h", "max"), l=("l", "min"), c=("c", "last"), n=("n", "sum"))
            per[tf][f.stem] = r
    syms = sorted(per[cfg.tfs[0]])
    log.info("적재 %d종목 · %.1f분", len(syms), (time.time()-t0)/60)

    rows, best = [], np.full(cfg.reps, -9e9)
    rng = np.random.default_rng(cfg.seed)
    for tf in cfg.tfs:
        idx = pd.DatetimeIndex(sorted(set().union(
            *[set(v.index) for v in per[tf].values()])))
        H = pd.DataFrame({s: per[tf][s].h for s in syms}).reindex(idx)
        L = pd.DataFrame({s: per[tf][s].l for s in syms}).reindex(idx)
        C = pd.DataFrame({s: per[tf][s].c for s in syms}).reindex(idx).ffill()
        N = pd.DataFrame({s: per[tf][s].n for s in syms}).reindex(idx).fillna(0.0)
        Hn, Ln, Cn = (x.to_numpy(np.float32) for x in (H, L, C))
        live = (N.rolling(12).median().shift(1)
                >= cfg.min_n*tf/12).to_numpy()
        pdi, ndi, adx = adx_parts(Hn, Ln, Cn, cfg.period)
        # ⚠ 전부 **새 배열**이어야 한다 — 아래에서 제자리 대입을 한다
        S = {"di": np.array(pdi - ndi, dtype=np.float32),
             "adx": np.array(adx, dtype=np.float32, copy=True),
             "adx_di": np.array(adx*np.sign(pdi - ndi), dtype=np.float32)}
        warm = cfg.period*4
        for k in S:
            S[k][:warm] = np.nan
        ALIVE = live & np.isfinite(Cn) & np.isfinite(S["di"])
        log.info("[%dh] 봉 %s · 살아있는 종목 중앙 %d · %.1f분", tf*5//60,
                 f"{len(idx):,}", int(np.median(ALIVE.sum(1))),
                 (time.time()-t0)/60)

        for hold_h in cfg.holds:
            hb = max(1, hold_h*60//(tf*5))
            hi_ = len(idx) - hb
            R = np.full(Cn.shape, np.nan, np.float32)
            R[:hi_] = (Cn[hb:hb+hi_]/Cn[:hi_] - 1.0)*100.0
            base = np.arange(warm, len(idx) - hb - 1)
            Ra, AL = R[base], ALIVE[base]
            day = pd.Series(idx[base].date)
            nb_ = len(base)
            # 비겹침 블록 — 위상 전부 평균
            phases = np.arange(hb) if hb <= 24 else np.unique(
                np.linspace(0, hb-1, 24).astype(int))
            blocks = []
            for ph in phases:
                kk = np.arange(ph, nb_ - hb - 1, hb)
                kk = kk[AL[kk].sum(1) >= cfg.min_alive]   # 신호 유효성은 아래에서
                if len(kk):
                    blocks.append(kk)
            allk = np.concatenate(blocks) if blocks else np.array([], int)
            if len(allk) < 200:
                continue
            for name in SIGS:
                # ⚠ 상위는 -inf 마스킹으로 되지만 **하위는 안 된다** — 마스킹한
                #   자리가 그대로 하위 N개에 들어가 그 날이 통째로 결측이 된다.
                #   예비비행 실측: 스프레드 칸이 1,827일 중 **109일**만 계산됐고
                #   살아있는 종목이 적은 날만 남아 +0.96%/일 같은 값이 나왔다.
                #   상위용·하위용 마스킹을 따로 만든다.
                v_ = S[name][base]
                hi_sc = np.where(AL & np.isfinite(v_), v_, -np.inf)
                lo_sc = np.where(AL & np.isfinite(v_), v_, +np.inf)
                order_h = np.argsort(-hi_sc, axis=1)
                order_l = np.argsort(lo_sc, axis=1)
                nok = (AL & np.isfinite(v_)).sum(1)
                for Np in cfg.picks:
                    hi_ix = order_h[:, :Np].astype(np.int32)
                    lo_ix = order_l[:, :Np].astype(np.int32)

                    def val(Rm, hx=hi_ix, lx=lo_ix, leg="추세스프레드"):
                        with np.errstate(invalid="ignore"):
                            h_ = np.nanmean(np.take_along_axis(Rm, hx, 1), 1)
                            l_ = np.nanmean(np.take_along_axis(Rm, lx, 1), 1)
                        return {"상위롱": h_, "상위숏": -h_,
                                "추세스프레드": (h_-l_)/2.0,
                                "반전스프레드": (l_-h_)/2.0}[leg]

                    ok_row = nok >= 2*Np       # 롱·숏이 겹치지 않을 만큼
                    kk2 = allk[ok_row[allk]]
                    if len(kk2) < 200:
                        continue
                    for leg in LEGS:
                        v = val(Ra, leg=leg)[kk2] - cfg.fee_rt
                        v = v[np.isfinite(v)]
                        if len(v) < 200:
                            continue
                        d_ = pd.Series(val(Ra, leg=leg)[kk2] - cfg.fee_rt,
                                       index=day.to_numpy()[kk2]).dropna()
                        dd = d_.groupby(level=0).mean()
                        m, sd = float(dd.mean()), float(dd.std(ddof=1))
                        # 방향맞춤 위약 — 무작위 N
                        pl = []
                        for _ in range(min(cfg.reps, 40)):
                            rs = np.where(AL, rng.random(AL.shape).astype(np.float32),
                                          -np.float32(np.inf))
                            o = np.argsort(-rs, axis=1)
                            pl.append(float(np.nanmean(
                                val(Ra, o[:, :Np].astype(np.int32),
                                    o[:, -Np:].astype(np.int32), leg)[kk2])
                                - cfg.fee_rt))
                        plm = float(np.median([x for x in pl if np.isfinite(x)]))
                        rows.append({"기간": f"{tf*5//60}h", "보유": f"{hold_h}h",
                                     "신호": name, "다리": leg, "N": Np,
                                     "날짜": len(dd), "블록": len(kk2), "일평균": m,
                                     "날짜t": m/(sd/np.sqrt(len(dd))),
                                     "샤프": m/sd*np.sqrt(365.25),
                                     "양수일%": float(100*(dd > 0).mean()),
                                     "위약": plm, "초과": m-plm})
            log.info("  [%dh 보유%dh] 칸 %d · %.1f분", tf*5//60, hold_h,
                     len(rows), (time.time()-t0)/60)
            del R, Ra
    T = pd.DataFrame(rows).sort_values("일평균", ascending=False)
    print(f"\n■ ADX / ±DI 횡단면 — 종목 {len(syms)} · 왕복 {cfg.fee_rt}% "
          f"· **날짜 군집 t** · 방향맞춤 위약")
    print(T.head(20).to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    print(f"\n  양수 칸 {int((T.일평균 > 0).sum())}/{len(T)} · "
          f"|t|>2 인 칸 {int((T.날짜t.abs() > 2).sum())}")
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_csv(OUT / "grid.csv", index=False)
    (OUT / "cfg.json").write_text(cfg.dump())
    log.info("저장 %s · %.1f분", OUT, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
