"""탄성저울(imp) · 방향 · 롱숏3h4(kine) 를 **한 커널**에 태워 비교 (2026-09-09).

## 왜

세 갈래의 원장을 나란히 놓으면 체결 가정·구간·슬롯이 달라 비교가 안 된다.
같은 1분봉 패널 · 같은 진입/손절/만기/수수료 커널에 태워야 순위가 의미를 갖는다
(하네스 규칙 ⑤ 커널 단일경로).

## 신호

    imp   |1분수익|/거래대금 의 60분 평균 ÷ 24h 중앙 — **낮은 쪽 숏**
    dir   직전 k분 수익 — **낮은 쪽 숏**(모멘텀 지속)
    kine  60분 앞 승률의 속도(z_vel)·가속(z_acc). **줄 세우기가 아니라 밴드다**:
              롱  −1.25 ≤ z_vel ≤ −0.25  그리고  z_acc < +0.5
              숏  +0.25 ≤ z_vel ≤ +1.25  그리고  z_acc > −0.5
          밴드를 통과한 것 중에서만 z_vel 로 채운다. 상한이 핵심이다 —
          초판은 상한이 없어 −18.8% 였다(소스 주석).
          ⚠ 2026-09-09 첫 재현에서 이걸 놓쳐 극단값을 뽑았고, 페이퍼 원장
            (+1.59%/일)과 50배 어긋났다. **밴드를 빼면 다른 전략이 된다.**

`kine` 은 종가만 쓰므로 캐시된 패널에서 바로 만든다.

## 한계

14일이다. `imp_direction_grid` 의 최대통계량이 p 0.105 로 통과 못 했다 —
**순위를 보는 용도이지 엣지의 근거가 아니다.**
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("impvskine")


@dataclass
class Cfg:
    panel: str = "runs/research_track/imp_direction_grid/panel_all.npz"
    fee_rt: float = 0.072
    stop_pct: float = 5.0
    cycle_min: int = 5
    need_bars: int = 1500
    min_live: float = 5.0
    # kine 상수 — kinematics_paper.py 에서 옮겨 적음
    # ⚠ 엔진은 틱 파일 **2개**만 읽는다(read_bars days=2). UTC 일 경계 직후엔
    #   (전일 1440분 + 당일 T분) 뿐이라 imp 의 1500봉 요구를 못 채운다.
    #   따라서 매일 **UTC 00:00~01:00 은 진입이 0** 이다(§30-A). 커널에도
    #   같은 구멍을 뚫지 않으면 진입 목록이 통째로 갈린다 — 2026-09-09
    #   재현 실패(원장과 상관 −0.020)의 유력 원인이었다.
    blind_min: int = 60
    win_h: int = 60
    window: int = 360
    delta: int = 180
    z_lo: float = -1.25
    z_hi: float = -0.25
    acc_max: float = 0.5


def kine_z(C: np.ndarray, c: Cfg):
    """(z_vel, z_acc). **종가만** 쓴다 — 엔진 수식 그대로."""
    nT, nS = C.shape
    Z = np.full((nT, nS), np.nan, np.float32)
    A = np.full((nT, nS), np.nan, np.float32)
    neff = max(c.window / c.win_h, 1.0)
    for j in range(nS):
        cl = C[:, j].astype(float)
        fw = np.full(nT, np.nan)
        fw[:nT - c.win_h] = cl[c.win_h:] / cl[:nT - c.win_h] - 1.0
        win = pd.Series(np.where(np.isfinite(fw), (fw > 0).astype(float), np.nan))
        # ⚠ shift(win_h) — 승부가 끝난 앵커만. 빼먹으면 미래참조다.
        rate = win.rolling(c.window, min_periods=c.window // 2).mean().shift(c.win_h)
        vel = rate - rate.shift(c.delta)
        acc = vel - vel.shift(c.delta)
        p = rate.clip(0.01, 0.99)
        se = np.sqrt(p * (1 - p) / neff)
        Z[:, j] = (vel / (se * np.sqrt(2))).to_numpy(np.float32)
        A[:, j] = (acc / (se * 2.0)).to_numpy(np.float32)
    return Z, A


def run(M: dict, c: Cfg, sig: str, slots: int, hold: int, both: bool,
        k: int = 15, SIG: np.ndarray | None = None, offset: int = 0):
    """(날별 자본수익%, 날). 커널은 하나 — 신호와 배치만 바뀐다."""
    C, LIVE, AGE = M["C"], M["LIVE"], M["AGE"]
    nT, nS = C.shape
    st = c.stop_pct / 100.0
    end = np.full(nS, -1, np.int64)
    epx = np.zeros(nS)
    esh = np.zeros(nS, bool)
    n_open = 0
    day = pd.to_datetime(M["grid"], unit="ms", utc=True).tz_convert("Asia/Seoul").date
    per_day: dict = {}
    utcmin = (pd.to_datetime(M["grid"], unit="ms", utc=True).hour * 60
              + pd.to_datetime(M["grid"], unit="ms", utc=True).minute).to_numpy()
    # ⚠ 위상(offset). 3슬롯 장부는 **경로 혼돈**이라 격자를 1분만 밀어도 이후
    #   거래 목록이 통째로 갈린다(교훈#109 — 같은 주가 −11%~+33%). 엔진을
    #   그대로 재현하는 것은 불가능하므로, 여러 위상으로 돌려 **분포로** 본다.
    for t in range(c.need_bars + offset, nT, c.cycle_min):
        blind = utcmin[t] < c.blind_min
        # ⚠ 손절은 **매 사이클** 본다. 만기에 소급 판정하면 손절당한 자리가
        #   보유기간 내내 묶여 **회전이 통째로 사라진다** — 엔진은 즉시 비우고
        #   새로 진입한다. 2026-09-09 재현 실패(원장 92건 vs 커널 소수,
        #   상관 −0.025)의 진짜 원인이었다. §31 의 회전 기전과 같은 자리다.
        for j in np.flatnonzero(end >= 0):
            e, sh = epx[j], esh[j]
            beg = int(end[j]) - hold
            seg = C[max(0, beg):t + 1, j]          # 진입 ~ **지금**
            adv = (np.nanmax(seg) / e - 1) if sh else (1 - np.nanmin(seg) / e)
            hit = bool(np.isfinite(adv) and adv >= st)
            if not hit and end[j] > t:
                continue                            # 아직 살아 있다
            if hit:
                r = -c.stop_pct
            else:
                x = C[min(int(end[j]), nT - 1), j]
                r = (100.0 * (e - x) / e) if sh else (100.0 * (x - e) / e)
            per_day.setdefault(day[t], []).append(float(r) - c.fee_rt)
            end[j] = -1
            n_open -= 1
        free = slots - n_open
        if free <= 0 or blind:      # 사각지대에는 엔진이 진입하지 못한다
            continue
        ok = (np.isfinite(C[t]) & (LIVE[t] >= c.min_live)
              & (AGE[t] >= c.need_bars) & (end < 0))
        if sig == "imp":
            v = M["IMP"][t]
            ok &= np.isfinite(v)
            score = v                      # 낮은 쪽 숏
        elif sig == "dir":
            prev = C[max(0, t - k)]
            v = np.where(prev > 0, 100.0 * (C[t] / prev - 1.0), np.nan)
            ok &= np.isfinite(v)
            score = v                      # 낮은 쪽 숏
        elif sig == "impconf":
            # imp 최저 순 유지 + **직전 k분이 꺾인 것만** 통과
            prev = C[max(0, t - k)]
            r = np.where(prev > 0, 100.0 * (C[t] / prev - 1.0), np.nan)
            v = M["IMP"][t]
            ok &= np.isfinite(v) & np.isfinite(r) & (r < 0)
            score = v
        else:                              # kine — 밴드 통과자만
            zv, za = SIG[0][t], SIG[1][t]
            ok &= np.isfinite(zv) & np.isfinite(za)
            ok_l = ok & (zv >= c.z_lo) & (zv <= c.z_hi) & (za < c.acc_max)
            ok_s = ok & (zv >= -c.z_hi) & (zv <= -c.z_lo) & (za > -c.acc_max)
            score = zv
        if sig == "kine":
            il = np.flatnonzero(ok_l)
            iss = np.flatnonzero(ok_s)
        else:
            il = iss = np.flatnonzero(ok)
        if both:
            half = slots // 2
            nl = int(((end >= 0) & ~esh).sum())
            ns = int(((end >= 0) & esh).sum())
            # 롱은 z_vel 낮은 순, 숏은 높은 순 (엔진과 같다)
            L = il[np.argsort(score[il])][:max(half - nl, 0)] if len(il) else []
            S = (iss[np.argsort(-score[iss])][:max(half - ns, 0)]
                 if len(iss) else [])
            picks = [(j, False) for j in L] + [(j, True) for j in S]
        else:
            base = iss if sig == "kine" else il
            if len(base) == 0:
                continue
            key = -score[base] if sig == "kine" else score[base]
            picks = [(j, True) for j in base[np.argsort(key)][:free]]
        for j, sh in picks:
            if end[j] >= 0:
                continue
            end[j] = t + hold
            epx[j] = C[t, j]
            esh[j] = sh
            n_open += 1
    days = sorted(per_day)
    return np.array([np.sum(per_day[d]) / slots for d in days], float), np.array(days)


def tstat(x):
    return (float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
            if len(x) >= 5 and np.std(x, ddof=1) > 0 else np.nan)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=15)
    a = ap.parse_args()
    c = Cfg()
    z = np.load(ROOT / c.panel, allow_pickle=True)
    M = {kk: z[kk] for kk in ("C", "H", "L", "IMP", "LIVE", "AGE")}
    M["grid"] = z["grid"]
    log.info("패널 %s · %d분 × %d종목", Path(c.panel).name, *M["C"].shape)
    KZ = kine_z(M["C"], c)
    log.info("kine z_vel·z_acc 계산 완료 · 유한 %.1f%% · 밴드 [%.2f, %.2f] acc<%.2f",
             100 * np.isfinite(KZ[0]).mean(), c.z_lo, c.z_hi, c.acc_max)

    rows = []
    cases = [
        ("탄성저울  imp/3숏/480",   "imp",  3, 480, False, None),
        ("방향     dir k=15/3숏/480", "dir", 3, 480, False, None),
        ("롱숏3h4  kine/6양/240",   "kine", 6, 240, True,  KZ),
        ("(참고) kine/6양/480",     "kine", 6, 480, True,  KZ),
        ("(참고) kine/3숏/480",     "kine", 3, 480, False, KZ),
        ("(참고) imp/6양/240",      "imp",  6, 240, True,  None),
    ]
    for name, sig, slots, hold, both, S in cases:
        r, dy = run(M, c, sig, slots, hold, both, a.k, S)
        if len(r) < 3:
            continue
        rows.append({"갈래": name, "날": len(r), "일평균%": r.mean(),
                     "합%": r.sum(), "t": tstat(r), "양수일%": 100 * (r > 0).mean(),
                     "일SD%": r.std(ddof=1)})
    out = pd.DataFrame(rows).sort_values("일평균%", ascending=False)
    print(f"\n■ 같은 커널·같은 14일 — 슬롯/보유/신호만 다르다")
    print(out.round(3).to_string(index=False))
    print("\n⚠ 14일이다. imp_direction_grid 최대통계량이 p 0.105 로 통과 못 했다 —"
          " **순위 참고용이지 엣지의 근거가 아니다.**")


if __name__ == "__main__":
    main()
