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


def build_h1(F, C, L=12, med=288):
    """H1 — 고래 각인. 단일 대량 체결이 남긴 자국.

    ⚠ `qsum`(합계)만으로는 고래 한 건과 잔거래 천 건이 구분이 안 된다.
      `qty` 의 **분포**를 쓴다 — 2026-09-01 에 tick_features 에 추가했다.
    """
    QX = F["qmax"].fillna(0.0)          # 5분 칸의 단일 체결 최대 거래대금
    QM = F["qmed"].replace(0, np.nan)
    Q9 = F["q90"].replace(0, np.nan)
    QS = F["qsum"].fillna(0.0)
    # 최근 L봉의 최대 단일 체결 / 그 종목의 하루 후행 중앙 체결
    wmax = QX.rolling(L).max()
    wmed = QM.rolling(med, min_periods=med//4).median().shift(1)
    whale = (wmax/np.maximum(wmed, 1e-9)).to_numpy(np.float32)
    # 대량 체결 비중 — 최대 체결이 그 구간 거래대금에서 차지하는 몫
    lshare = (wmax/np.maximum(QS.rolling(L).sum(), 1e-9)).to_numpy(np.float32)
    # 체결 크기 분포의 쏠림
    qskew = (Q9/np.maximum(QM, 1e-9)).rolling(L).mean().to_numpy(np.float32)
    # 방향 있는 고래 — 최대 체결이 테이커 매수였나(가중)
    dirn = (F["qmax_buy"].rolling(L).mean()*2 - 1).to_numpy(np.float32)
    return {"whale": np.array(whale, np.float32),
            "lshare": np.array(lshare, np.float32),
            "qskew": np.array(qskew, np.float32),
            "whale_dir": np.array(whale*dirn, np.float32)}


def build_h2(F, C, med=288):
    """H2 — 테이커 불균형의 **변화**. 수준이 아니라 전환.

    ⚠ 수준(tkb)은 2026-09-01 오전에 전 유니버스 p 0.550 으로 닫혔다.
      **변화**는 안 재봤다. 이 트랙은 이미 그 구분으로 한 번 성공했다 —
      z_vel 자체가 "승률의 수준"이 아니라 "승률의 속도"다.

    기제: 수준은 종목마다 늘 다르다(시장조성 구조·상장 방식). **바뀌는
    순간**이 사건이다. 매도 우위에서 매수 우위로 뒤집히면 무언가 시작된 것이다.
    """
    TQ = F["tkq"]                       # 수량가중 테이커 매수 비율
    TB = F["tkb"]                       # 건수 기준
    # 최근 15분 대 직전 45분
    q3 = TQ.rolling(3).mean()
    q12 = TQ.rolling(12).mean()
    chg_q = (q3 - (q12*12 - q3*3)/9).to_numpy(np.float32)
    b3 = TB.rolling(3).mean()
    b12 = TB.rolling(12).mean()
    chg_b = (b3 - (b12*12 - b3*3)/9).to_numpy(np.float32)
    # 자기 대비 수준 — 그 종목의 평소 불균형에서 얼마나 벗어났나
    tmed = TQ.rolling(med, min_periods=med//4).median().shift(1)
    tz = (q12 - tmed).to_numpy(np.float32)
    # 변화의 변화 (2차)
    acc = (chg_q - np.roll(chg_q, 3, axis=0)).astype(np.float32)
    acc[:3] = np.nan
    return {"tk_chg": np.array(chg_q, np.float32),
            "tk_chg_b": np.array(chg_b, np.float32),
            "tk_z": np.array(tz, np.float32),
            "tk_acc": np.array(acc, np.float32)}


def build_h4(F, C, L=12):
    """H4 — 체결 자기여기. **어떻게** 뭉치는가.

    ⚠ `irr`(봉 안 체결 간격의 변동계수)은 2026-09-01 오전 전 유니버스
      p 0.575 로 닫혔다. irr 은 "고르지 않다"만 잰다 — 한 번에 몰렸는지
      산발적인지는 못 가른다. 여기서는 **봉 사이의 뭉침 구조**를 본다.

    기제: 정보 거래는 뭉쳐서 온다(자기여기). 균등하게 흩어진 체결은 잡거래다.

        burst   최근 L봉 중 가장 바쁜 봉의 체결 수 / 그 구간 평균
        vburst  같은 것을 거래대금으로
        hhi     체결 수의 허핀달 집중도 (1/L = 완전 균등, 1 = 한 봉에 몰림)
        ac1     체결 수의 1차 자기상관 — 양수면 자기여기
    """
    NT = F["ntr"].fillna(0.0)
    QS = F["qsum"].fillna(0.0)
    nmax = NT.rolling(L).max()
    nmean = NT.rolling(L).mean()
    burst = (nmax/np.maximum(nmean, 1e-9)).to_numpy(np.float32)
    vmax = QS.rolling(L).max()
    vmean = QS.rolling(L).mean()
    vburst = (vmax/np.maximum(vmean, 1e-9)).to_numpy(np.float32)
    s2 = (NT**2).rolling(L).sum()
    s1 = NT.rolling(L).sum()
    hhi = (s2/np.maximum(s1**2, 1e-9)).to_numpy(np.float32)
    # ⚠ 자기상관은 열마다 계산해야 한다. rolling.corr 는 두 DataFrame 을
    #   열 이름으로 맞추므로 **같은 이름**이어야 한다(합집합 사고 방지).
    ac1 = NT.rolling(L).corr(NT.shift(1)).to_numpy(np.float32)
    return {"burst": np.array(burst, np.float32),
            "vburst": np.array(vburst, np.float32),
            "hhi": np.array(hhi, np.float32),
            "ac1": np.array(np.nan_to_num(ac1, nan=np.nan), np.float32)}


def build_h5(F, C, L=12, med=288):
    """H5 — 테이커 연속 길이. 한 참여자가 밀고 있는가.

    ⚠ `flip` 은 **가격** 방향 반전을, 이건 **테이커** 방향 연속을 잰다.
      가격이 안 움직여도 같은 방향 체결이 이어질 수 있다 — 다른 것이다.
      flip 은 2026-09-01 오전 전 유니버스 p 0.575 로 닫혔다.

    ⚠⚠ **핵심은 정규화다.** 평균 연속 길이는 매수 비율 p 에 그냥 딸려 온다 —
      무작위 시퀀스도 p 가 치우치면 길어진다(기대값 1/(2p(1-p))).
      정규화 없이 쓰면 **테이커 불균형(tkb)을 다시 재는 것**이고, 그건 이미
      p 0.550 으로 닫혔다. 기대값으로 나눠 **우연을 넘는 몫**만 남긴다.

    기제: 같은 방향 체결이 우연보다 길게 이어지면 한 주체가 주문을 쪼개
    집행 중이다. 그 집행이 끝나면 되돌아온다.
    """
    NT = F["ntr"].fillna(0.0)
    NR = F["nrun"].replace(0, np.nan)
    RM = F["run_max"]
    TB = F["tkb"]
    rmean = (NT.rolling(L).sum()/np.maximum(NR.rolling(L).sum(), 1e-9))
    pb = TB.rolling(L).mean().clip(0.02, 0.98)
    exp_ = 1.0/(2*pb*(1-pb))            # 무작위 시퀀스의 기대 연속 길이
    excess = (rmean/exp_).to_numpy(np.float32)
    rmax = RM.rolling(L).max()
    rmax_z = (rmax/np.maximum(
        RM.rolling(med, min_periods=med//4).median().shift(1), 1e-9)
    ).to_numpy(np.float32)
    return {"run_excess": np.array(excess, np.float32),
            "run_mean": np.array(rmean.to_numpy(np.float32), np.float32),
            "run_max_z": np.array(rmax_z, np.float32),
            "run_max": np.array(rmax.to_numpy(np.float32), np.float32)}


FAMILIES = {"h3": ("가격 충격 계수", build_h3),
            "h1": ("고래 각인", build_h1),
            "h2": ("테이커 불균형의 변화", build_h2),
            "h4": ("체결 자기여기", build_h4),
            "h5": ("테이커 연속 길이", build_h5)}


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
        # ⚠ 다리별 무작위 기준선(교훈#118). H3 에서 상위숏 칸이 최대통계량을
        #   통과했는데 **무작위 숏도 +0.122** 였다 — 하락장 효과였다.
        #   회전 위약은 시장 방향을 못 걷어내므로 다리마다 따로 재야 한다.
        rr = rng.random(AL.shape).astype(np.float32)
        o = np.argsort(-np.where(AL, rr, -np.inf), axis=1)
        for Np in picks:
            for leg in LEGS:
                cells.append((f"무작위", 0, leg, Np,
                              o[:, :Np].astype(np.int32),
                              o[:, -Np:].astype(np.int32)))
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
    # ⚠ 위약 기준선은 **다리별**이다. 하나로 빼면 하락장에서 상위숏이
    #   전부 통과한다(교훈#118).
    rb = (T[T.신호 == "무작위"].groupby(["보유분", "다리", "N"]).일평균.mean())
    T["위약대비"] = T.일평균 - [
        rb.get((h, l, n_), np.nan)
        for h, l, n_ in zip(T.보유분, T.다리, T.N)]
    print(f"\n■ {lab} — 틱 {m}종목 · **밴드 없음** · 칸 {len(T)} · "
          f"왕복 {cfg.fee_rt}%")
    print("  다리별 무작위 기준선 (보유·다리·N)")
    print("    " + rb.round(4).to_string().replace("\n", "\n    "))
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
