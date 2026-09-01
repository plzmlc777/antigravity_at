"""틱 횡단면 격자 — 가설별 신호를 **밴드 없이 전 유니버스**에서 잰다.

## 왜 (2026-09-01, 대표님 지시)

오늘 닫은 것들에서 두 가지를 배웠다.

  ① z_vel 밴드와 결합하면 성과가 **절반**이 된다 — 밴드는 후보를 줄일 뿐이다.
     그래서 이 하네스는 밴드를 안 쓴다. 살아있는 종목 전부가 후보다.
  ② 격자를 좁게 잡으면 최대통계량 귀무 기준선이 낮아져 통과처럼 보인다
     (교훈#117: 보유 3종 → 6종으로 p 0.000 이 0.135 가 됐다).
     그래서 격자를 **먼저 선언하고** 좁히지 않는다.

## H3 — 가격 충격 계수 (아미후드 비유동성)

    amihud    최근 L봉의 mean(|5분 로그수익| / 5분 거래대금)
    impact    |L분 누적 수익| / L분 거래대금 합
    amihud_z  amihud / 그 종목의 후행 중앙값   ← **지금 유난히** 충격이 큰가

세 번째가 핵심이다. 수준만 쓰면 시가총액 순위를 다시 그리는 것에 불과하다.
**변화**를 봐야 사건이 된다 — 이 트랙은 이미 그 구분으로 한 번 성공했다
(z_vel 자체가 "승률의 수준"이 아니라 "승률의 속도"다).

기제: 적은 거래로 크게 움직인 종목은 떠받치는 게 없다. 그 움직임은 정보가
아니라 압력이라 되돌아온다.

왜 새로운가: 변동성 단독(atr)과 거래대금 단독(qsum)은 각각 닫혔지만
**둘의 비**는 안 재봤다.

## 규약 (오늘까지의 교훈 전부)

⚠ 상위/하위 마스킹 **따로**(교훈#116) · 유효 종목 2N 미만 행 제외 · 블록 수 표기
⚠ 판정 주축은 **날짜 군집 t**(교훈#112). 앵커 수는 표본 수가 아니다
⚠ 방향맞춤 위약(교훈#91·#101) + 회전 위약 최대통계량(교훈#95)
⚠ p 는 **칸 수·귀무 95분위와 함께** 읽는다(교훈#117)
⚠ 방향(±1)과 다리 4종을 격자에 함께 넣어 **결과 보고 안 고른다**
⚠ 틱 6~7일 — 독립 단위는 날짜 6~7개. **선별이지 판정이 아니다**

사용:
  python3 -m scripts.research.tick_xsec_grid --family h3 --smoke
  python3 -m scripts.research.tick_xsec_grid --family h3 --reps 200
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research.tick_synergy import Cfg, build_all       # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "research_track" / "tick_xsec_2026_09_01"
log = logging.getLogger("xsec")
LEGS = ["상위롱", "상위숏", "추세스프레드", "반전스프레드"]
MIN_ALIVE = 60          # 앵커당 살아있는 종목 최소 (밴드 없음)


def build_h3(F, C, L=12, med=288):
    """H3 — 가격 충격 계수. |수익| 대비 거래대금."""
    QS = F["qsum"].fillna(0.0)
    lr = pd.DataFrame(np.log(np.maximum(C, 1e-12)))
    absr = lr.diff().abs()*100.0
    dv = QS.to_numpy(np.float32)
    ami = (absr.to_numpy(np.float32)/np.maximum(dv, 1e-9))
    ami = pd.DataFrame(ami).rolling(L).mean().to_numpy(np.float32)
    cum = np.abs(C/np.roll(C, L, axis=0) - 1.0)*100.0
    cum[:L] = np.nan
    vsum = QS.rolling(L).sum().to_numpy(np.float32)
    imp = cum/np.maximum(vsum, 1e-9)
    # ⚠ 수준만 쓰면 시총 순위를 다시 그린다. **자기 대비**가 사건이다.
    amed = (pd.DataFrame(ami).rolling(med, min_periods=med//4).median()
            .shift(1).to_numpy(np.float32))
    return {"amihud": np.array(ami, np.float32),
            "impact": np.array(imp, np.float32),
            "amihud_z": np.array(ami/np.maximum(amed, 1e-12), np.float32)}


FAMILIES = {"h3": ("가격 충격 계수", build_h3)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--family", default="h3", choices=list(FAMILIES))
    p.add_argument("--holds", default="12,24,48,96")   # 1·2·4·8시간
    p.add_argument("--picks", default="3,5")
    p.add_argument("--reps", type=int, default=200)
    p.add_argument("--smoke", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    holds = [int(x) for x in a.holds.split(",")]
    picks = [int(x) for x in a.picks.split(",")]
    reps = 10 if a.smoke else a.reps
    if a.smoke:
        holds, picks = holds[:2], picks[:1]
    cfg = Cfg()
    t0 = time.time()
    S0, ZV, ZA, live, C, idx, syms, F = build_all(cfg)
    n, m = C.shape
    lab, fn = FAMILIES[a.family]
    SIG = fn(F, C)
    warm = 288 + 24
    for k in SIG:
        SIG[k][:warm] = np.nan
    # ⚠ 밴드 없음 — 살아있는 종목 전부가 후보
    ALIVE = live & np.isfinite(C)
    log.info("[%s] 신호 %d종 · 살아있는 종목 중앙 %d · %.1f분", lab, len(SIG),
             int(np.median(ALIVE.sum(1))), (time.time()-t0)/60)

    rng = np.random.default_rng(cfg.seed)
    rows, best = [], np.full(reps, -9e9)
    ncell = len(SIG)*2*len(LEGS)*len(picks)*len(holds)
    log.info("격자 선언 — 신호 %d × 방향 2 × 다리 %d × 종목 %d × 보유 %d "
             "= **%d칸**", len(SIG), len(LEGS), len(picks), len(holds), ncell)

    for H in holds:
        hi_ = n - H
        R = np.full(C.shape, np.nan, np.float32)
        R[:hi_] = (C[H:H+hi_]/C[:hi_] - 1.0)*100.0
        base = np.arange(warm, n - H - 1)
        Ra, AL = R[base], ALIVE[base]
        nb_ = len(base)
        day = pd.Series(pd.DatetimeIndex(idx[base]).date).to_numpy()
        blocks = []
        for ph in range(H):
            kk = np.arange(ph, nb_ - H - 1, H)
            # ⚠ 밴드를 안 쓰므로 `min_side`(다리별 최소)가 아니라
            #   **전 유니버스 최소 종목 수**가 필요하다. Cfg 에는 없어 여기서 둔다.
            kk = kk[AL[kk].sum(1) >= MIN_ALIVE]
            if len(kk):
                blocks.append(kk)
        allk = np.concatenate(blocks) if blocks else np.array([], int)
        if len(allk) < 100:
            continue
        log.info("보유 %d분 · 앵커 %s · 날짜 %d · %.1f분", H*5, f"{len(allk):,}",
                 len(set(day[allk])), (time.time()-t0)/60)

        def stat(hx, lx, Rm, leg):
            with np.errstate(invalid="ignore"):
                h_ = np.nanmean(np.take_along_axis(Rm, hx, 1), 1)
                l_ = np.nanmean(np.take_along_axis(Rm, lx, 1), 1)
            v = {"상위롱": h_, "상위숏": -h_,
                 "추세스프레드": (h_-l_)/2.0,
                 "반전스프레드": (l_-h_)/2.0}[leg]
            return v - cfg.fee_rt

        cells = []
        rr = rng.random(AL.shape).astype(np.float32)
        o = np.argsort(-np.where(AL, rr, -np.inf), axis=1)
        for Np in picks:
            cells.append(("무작위", 0, "추세스프레드", Np,
                          o[:, :Np].astype(np.int32), o[:, -Np:].astype(np.int32)))
        for name, v0 in SIG.items():
            v_ = v0[base]
            for dr in (1, -1):
                v = v_*dr
                # 교훈#116 — 상위·하위 마스킹을 따로
                hs = np.where(AL & np.isfinite(v), v, -np.inf)
                ls = np.where(AL & np.isfinite(v), v, +np.inf)
                oh, ol = np.argsort(-hs, axis=1), np.argsort(ls, axis=1)
                nok = (AL & np.isfinite(v)).sum(1)
                for Np in picks:
                    ok_row = nok >= 2*Np
                    for leg in LEGS:
                        cells.append((name, dr, leg, Np,
                                      oh[:, :Np].astype(np.int32),
                                      ol[:, :Np].astype(np.int32), ok_row))
        for c in cells:
            name, dr, leg, Np, hx, lx = c[:6]
            kk2 = allk if len(c) < 7 else allk[c[6][allk]]
            if len(kk2) < 100:
                continue
            v = stat(hx, lx, Ra, leg)[kk2]
            d_ = pd.Series(v, index=day[kk2]).dropna()
            if len(d_) < 50:
                continue
            dd = d_.groupby(level=0).mean()
            mn, sdv = float(dd.mean()), float(dd.std(ddof=1))
            rows.append({"보유분": H*5, "신호": name, "방향": dr, "다리": leg,
                         "N": Np, "앵커": len(d_), "날짜": len(dd),
                         "거래당": float(d_.mean()), "일평균": mn,
                         "날짜t": mn/(sdv/np.sqrt(len(dd))) if len(dd) > 2 else np.nan,
                         "샤프": mn/sdv*np.sqrt(365.25) if sdv else np.nan,
                         "양수일": f"{int((dd>0).sum())}/{len(dd)}"})
        lo_s = max(warm, H) + 10
        for rep in range(reps):
            sh = int(rng.integers(lo_s, nb_ - lo_s))
            Rs = Ra[(np.arange(nb_) - sh) % nb_]
            mx = -9e9
            for c in cells:
                name, dr, leg, Np, hx, lx = c[:6]
                if name == "무작위":
                    continue
                kk2 = allk if len(c) < 7 else allk[c[6][allk]]
                if len(kk2) < 100:
                    continue
                v = stat(hx, lx, Rs, leg)[kk2]
                v = v[np.isfinite(v)]
                if len(v):
                    mx = max(mx, float(v.mean()))
            best[rep] = max(best[rep], mx)
            if (rep+1) % 50 == 0:
                log.info("    위약 %d/%d · %.1f분", rep+1, reps,
                         (time.time()-t0)/60)
        del R, Ra
    T = pd.DataFrame(rows)
    rb = T[T.신호 == "무작위"].set_index("보유분").일평균.to_dict()
    T["위약대비"] = T.일평균 - T.보유분.map(rb)
    print(f"\n■ {lab} — 틱 {m}종목 · **밴드 없음** · 칸 {len(T)} · "
          f"왕복 {cfg.fee_rt}%")
    print("  무작위 기준선  " + " · ".join(
        f"{k}분 {v:+.4f}" for k, v in sorted(rb.items())))
    print("\n  상위 15 (일평균)")
    print(T[T.신호 != "무작위"].nlargest(15, "일평균")[
        ["보유분", "신호", "방향", "다리", "N", "날짜", "거래당", "일평균",
         "날짜t", "샤프", "양수일", "위약대비"]].to_string(
        index=False, float_format=lambda z: f"{z:+.4f}"))
    obs = float(T[T.신호 != "무작위"].일평균.max())
    bb = best[np.isfinite(best) & (best > -8e9)]
    pm = float((bb >= obs).mean()) if len(bb) else np.nan
    print(f"\n■ 회전 위약 최대통계량")
    print(f"  **칸 {len(T)}** · 위약 {len(bb)}회 · 관측 최대 {obs:+.4f}%/일")
    print(f"  귀무 중앙 {np.median(bb):+.4f} · **95분위 {np.quantile(bb,.95):+.4f}** "
          f"· **p = {pm:.3f}**")
    print(f"\n  위약을 이긴 칸 {int((T.위약대비 > 0).sum())}/{len(T)} · "
          f"그중 날짜t>2 {int(((T.위약대비>0)&(T.날짜t>2)).sum())}")
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_csv(OUT / f"{a.family}.csv", index=False)
    log.info("저장 %s · %.1f분", OUT, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
