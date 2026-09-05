"""잡음6 **슬롯 배분 규칙** A/B — 강제 반반 vs 자유 배분.

## 왜 (2026-09-02)

`잡음6`(s6both_d5_noise)은 슬롯을 **강제로 반반** 나눈다.

    half = slots // 2
    L = noisy(롱풀)[:half]      # 롱 후보 중 잡음 상위 3
    S = noisy(숏풀)[:half]      # 숏 후보 중 잡음 상위 3

그래서 숏 후보가 아무리 시원찮아도 3개를 채운다. 비중을 **신호가 아니라
사람이 정한** 셈이다.

⚠ **시장 방향으로 기울이는 길은 오늘 닫혔다.** 유니버스 중앙 되돌림은
  통계는 진짜(1h 자기상관 -0.0701 · t -14.15)인데 지연 1봉에 소멸하고
  최대통계량 p 0.500 이다. 예측에 기대는 배분은 만들지 마라.
⚠ **자기 성과로 기울이는 길도 닫혀 있다**(위약 p 0.112). 실측으로도
  08-31·09-01 숏 우세 → 09-02 롱 +2.237% / 숏 -0.589% 로 반전했다.

남은 길은 **내생적 배분** 하나다 — 롱·숏을 한 통에 넣고 잡음 점수 상위
N개를 그냥 뽑는다. 시장을 예측하지 않고, 그 순간 신호가 센 쪽이 자리를
많이 가져간다.

## 방향 판정은 엔진 그대로 복제한다

    z_vel 밴드   롱 : -1.25 ≤ zv ≤ -0.25 이고 za < 0.5
                 숏 :  0.25 ≤ zv ≤  1.25 이고 za > -0.5   (거울)
    유동성       live = ntr.rolling(60).median().shift(1) ≥ 5.0
    잡음 점수    rank(bump) + rank(irr)  — 앵커 안 횡단면 순위합

⚠ 두 풀은 밴드가 겹치지 않아 **서로소**다. 합쳐서 뽑아도 한 종목이 롱·숏
  양쪽에 들어가지 않는다.

## 단순화 한 가지 — 정직하게 밝힌다

엔진은 5분마다 빈 슬롯만 채우지만, 여기서는 **보유 시간마다 전 슬롯을
새로 배분**한다(비겹침 코호트). 처리량은 같고, 무엇보다 **모든 판본에
똑같이** 적용되므로 A/B 비교는 공정하다.

사용:
  python3 -m scripts.research.noise_alloc --smoke 40
  python3 -m scripts.research.noise_alloc
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.binance import tickbars                          # noqa: E402

log = logging.getLogger("noise_alloc")
OUT = Path(__file__).resolve().parents[2] / "runs" / "research_track" / "noise_alloc"


@dataclass(frozen=True)
class Cfg:
    """⚠ 설정은 **여기 하나뿐**이다. 즉석 하드코딩 금지(하네스 규칙 1)."""
    win_h: int = 60            # 선도 창(분) — 엔진 WIN_H
    window: int = 360          # 승률 평균 창 — 엔진 WINDOW
    delta: int = 180           # 속도 간격 — 엔진 DELTA
    z_lo: float = -1.25        # 엔진 Z_LO
    z_hi: float = -0.25        # 엔진 Z_HI
    acc_max: float = 0.5       # 엔진 ACC_MAX
    min_live: float = 5.0      # 엔진 MIN_LIVE_TR
    fee_rt: float = 0.072      # 왕복 — **편도 아니다**
    hold: int = 120            # 보유(분)
    noise_win: int = 60        # bump·irr 창(분)
    slots: int = 6
    gate_score: float = 1.40   # 문턱 판본 — rank(bump)+rank(irr) 의 절대 문턱
                               #   (각 0~1 의 합이라 0~2. 1.40 = 평균 0.70)
    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=1)


def series(sym: str, c: Cfg):
    """한 종목의 **모든 앵커 값**을 한 번에 만든다(앵커마다 다시 계산하지 않는다)."""
    fs = sorted((tickbars.BARS / sym).glob("*.parquet"))
    if not fs:
        return None
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    d = d.drop_duplicates("ts_ms").sort_values("ts_ms")
    ix = pd.to_datetime(d.ts_ms.to_numpy(), unit="ms", utc=True)
    b = d.set_index(ix)
    full = pd.date_range(b.index.min(), b.index.max(), freq="1min", tz="UTC")
    b = b.reindex(full)
    cl = b.cl.ffill()
    n = len(cl)
    need = c.win_h + c.window + 2*c.delta + 10
    if n < need + c.hold:
        return None
    cc = cl.to_numpy(float)
    fw = np.full(n, np.nan)
    fw[:n-c.win_h] = cc[c.win_h:]/cc[:n-c.win_h] - 1.0
    win = pd.Series(np.where(np.isfinite(fw), (fw > 0).astype(float), np.nan))
    # ⚠ shift(win_h) — 승부가 끝난 앵커만. 빼먹으면 미래참조다(엔진과 동일).
    rate = win.rolling(c.window, min_periods=c.window//2).mean().shift(c.win_h)
    vel = rate - rate.shift(c.delta)
    acc = vel - vel.shift(c.delta)
    neff = max(c.window/c.win_h, 1.0)
    p = rate.clip(0.01, 0.99)
    se = np.sqrt(p*(1-p)/neff)
    zv = (vel/(se*np.sqrt(2))).to_numpy()
    za = (acc/(se*2.0)).to_numpy()
    live = b.ntr.rolling(60).median().shift(1).to_numpy()
    n60 = b.ntr.rolling(c.noise_win).sum().to_numpy()
    f60 = b.flip.rolling(c.noise_win).sum().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        bump = np.where(n60 > 0, f60/n60, np.nan)
        dm = b.dtm.rolling(c.noise_win).mean().to_numpy()
        ds = b.dts.rolling(c.noise_win).mean().to_numpy()
        irr = np.where(dm > 0, ds/dm, np.nan)
    fwd = np.full(n, np.nan)
    fwd[:n-c.hold] = (cc[c.hold:]/cc[:n-c.hold] - 1.0)*100.0
    return pd.DataFrame({"zv": zv, "za": za, "live": live, "bump": bump,
                         "irr": irr, "fwd": fwd}, index=full)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--from", dest="d_from", default="",
                   help="이 시각부터의 앵커만. 실제 갈래 구간과 맞춰 "
                        "**재현 검증**할 때 쓴다(하네스 규칙 2)")
    p.add_argument("--delay", type=int, default=0,
                   help="예약 후 승격까지 대기(분). 갈래 이름의 d5 가 이것이다 — "
                        "신호는 t 에서 보고 진입은 t+delay 다")
    p.add_argument("--universe",
                   default="configs/binance_collect_universe.txt")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    c = Cfg()
    log.info("설정 전문:\n%s", c.dump())
    log.info("인자 도달 확인 — 지연 %d분 · 시작 %s · smoke %d",
             a.delay, a.d_from or "전체", a.smoke)          # 하네스 규칙 7 — 설정 기록

    syms = [x.strip() for x in Path(a.universe).read_text().split() if x.strip()]
    if a.smoke:
        syms = syms[:a.smoke]
    t0 = time.time()
    S = {}
    for i, s in enumerate(syms, 1):
        try:
            r = series(s, c)
        except Exception as e:                                 # noqa: BLE001
            log.debug("%s 실패 %s", s, e); r = None
        if r is not None:
            S[s] = r
        if i % 100 == 0:
            log.info("[%d/%d] 담김 %d · %.1f분", i, len(syms), len(S),
                     (time.time()-t0)/60)
    if len(S) < 30:
        raise SystemExit(f"종목 {len(S)}개 — 너무 적다")
    idx = sorted(set().union(*[x.index for x in S.values()]))
    idx = pd.DatetimeIndex(idx)
    names = sorted(S)
    Z = {k: np.full((len(idx), len(names)), np.nan) for k in
         ("zv","za","live","bump","irr","fwd")}
    for j, s in enumerate(names):
        r = S[s].reindex(idx)
        for k in Z:
            Z[k][:, j] = r[k].to_numpy(float)
    del S
    log.info("행렬 %s × %d종목", Z["zv"].shape, len(names))

    # ── 앵커 = 보유 시간마다 (비겹침 코호트) ─────────────
    anc = np.arange(0, len(idx) - c.hold - a.delay - 1, c.hold)
    if a.d_from:
        f0 = pd.Timestamp(a.d_from, tz="UTC")
        anc = anc[idx[anc] >= f0]
    log.info("앵커 %d개 (%d분 간격) · %s ~ %s", len(anc), c.hold,
             idx[anc[0]], idx[anc[-1]])

    def alloc(t, mode):
        """한 앵커의 배분 → [(종목번호, 숏여부, 순수익%)].

        ⚠ **한 곳에서만** 계산한다. 예전엔 손익용·방향집계용으로 같은
          블록을 두 번 썼고, 한쪽만 고치다 들여쓰기가 깨졌다(2026-09-02).
        ⚠ 방향은 파라미터다 — 롱·숏 판정을 밖에서 하드코딩하지 않는다.
        """
        zv, za, lv = Z["zv"][t], Z["za"][t], Z["live"][t]
        bp, ir = Z["bump"][t], Z["irr"][t]
        # ⚠ 지연 — 신호는 t 에서 보고 **진입은 t+delay**. 갈래 이름의 d5 다.
        fw = Z["fwd"][min(t + a.delay, Z["fwd"].shape[0] - 1)]
        ok = (np.isfinite(zv) & np.isfinite(za) & np.isfinite(lv)
              & np.isfinite(bp) & np.isfinite(ir) & np.isfinite(fw)
              & (lv >= c.min_live))
        okl = ok & (zv >= c.z_lo) & (zv <= c.z_hi) & (za < c.acc_max)
        oks = ok & (zv >= -c.z_hi) & (zv <= -c.z_lo) & (za > -c.acc_max)
        pool = okl | oks
        if not pool.any():
            return []
        rb = pd.Series(np.where(pool, bp, np.nan)).rank(pct=True).to_numpy()
        ri = pd.Series(np.where(pool, ir, np.nan)).rank(pct=True).to_numpy()
        score = rb + ri
        half = c.slots // 2

        def pick(mask, k, gate=None):
            i = np.flatnonzero(mask)
            if not len(i):
                return []
            if gate is not None:
                # ⚠ **횡단면 전체** 기준이어야 한다. 후보 안 상대순위로 걸면
                #   상위 N 은 항상 통과해 문턱이 무효가 된다(2026-09-02 실측:
                #   자유6문턱 132건 = 자유6 132건, 하나도 안 걸렸다).
                i = i[score[i] >= gate]
                if not len(i):
                    return []
            return list(i[np.argsort(-score[i])][:k])

        if mode == "현재":                       # 강제 반반
            sel = [(x, False) for x in pick(okl, half)] + \
                  [(x, True) for x in pick(oks, half)]
        elif mode == "롱만3":
            sel = [(x, False) for x in pick(okl, half)]
        elif mode == "숏만3":
            sel = [(x, True) for x in pick(oks, half)]
        elif mode == "자유6":                    # 한 통에서 상위 N
            sel = [(x, bool(oks[x])) for x in pick(pool, c.slots)]
        elif mode == "자유6문턱":
            sel = [(x, bool(oks[x]))
                   for x in pick(pool, c.slots, gate=c.gate_score)]
        else:
            raise ValueError(mode)
        return [(x, sh, (-fw[x] if sh else fw[x]) - c.fee_rt) for x, sh in sel]

    MODES = ["현재", "롱만3", "숏만3", "자유6", "자유6문턱"]
    res = {m: [] for m in MODES}
    nL = {m: 0 for m in MODES}
    nS = {m: 0 for m in MODES}
    for t in anc:
        for m in MODES:
            for _, sh, r in alloc(t, m):
                res[m].append(r)
                if sh:
                    nS[m] += 1
                else:
                    nL[m] += 1

    print(f"\n■ 슬롯 배분 A/B — 앵커 {len(anc)} · 종목 {len(names)} · "
          f"보유 {c.hold}분 · 왕복 {c.fee_rt}%")
    print(f"  {'판본':<10}{'거래':>7}{'롱':>6}{'숏':>6}{'롱%':>6}"
          f"{'거래당%':>10}{'복리%':>9}{'승률':>7}{'최대낙폭':>9}")
    for m in MODES:
        x = np.array(res[m])
        if not len(x): continue
        sl = 3 if m in ("롱만3","숏만3") else c.slots
        e = np.cumprod(1 + x/sl/100)
        mdd = 100*(1-(e/np.maximum.accumulate(e)).min())
        tot = nL[m]+nS[m]
        print(f"  {m:<10}{len(x):>7,}{nL[m]:>6,}{nS[m]:>6,}"
              f"{100*nL[m]/max(tot,1):>5.0f}%{x.mean():>+10.4f}"
              f"{100*(e[-1]-1):>+9.2f}{100*(x>0).mean():>6.0f}%{mdd:>9.2f}")
    # ── 분해 — 자유 배분의 이득이 **비중 이동**인가 **선별**인가 ──
    #   비중 효과 = (자유의 롱·숏 비중) 으로 **현재 판본의 다리 성적**을 가중
    #   선별 효과 = 나머지
    cur = np.array(res["현재"]); fre = np.array(res["자유6"])
    if len(cur) and len(fre):
        # 현재 판본의 다리별 거래당
        curL, curS = [], []
        freL, freS = [], []
        for t in anc:
            for x, sh, r in alloc(t, "현재"):
                (curS if sh else curL).append(r)
            for x, sh, r in alloc(t, "자유6"):
                (freS if sh else freL).append(r)
        cL, cS = np.mean(curL), np.mean(curS)
        wl = len(freL)/(len(freL)+len(freS))
        mix = wl*cL + (1-wl)*cS            # 비중만 바꾸고 종목은 현재 것
        print(f"\n■ 분해 — 자유6 이득 {fre.mean()-cur.mean():+.4f}%p 의 출처")
        print(f"  현재 판본 다리별 거래당   롱 {cL:+.4f}%  ·  숏 {cS:+.4f}%")
        print(f"  자유 판본 비중            롱 {100*wl:.0f}% : 숏 {100*(1-wl):.0f}%")
        print(f"  **비중 효과** (현재 종목 · 자유 비중) {mix - cur.mean():+.4f}%p")
        print(f"  **선별 효과** (나머지)                {fre.mean() - mix:+.4f}%p")

    # ── 구간을 갈라 방향 일관성 ──────────────────────────
    print(f"\n■ 구간 분할 — 자유6 이 **항상** 이기나")
    k = max(len(anc)//3, 1)
    print(f"  {'구간':<22}{'앵커':>5}{'현재':>10}{'자유6':>10}{'차이':>10}{'숏비중':>8}")
    for q in range(0, len(anc), k):
        sub = anc[q:q+k]
        if len(sub) < 3: continue
        cc, ff, ns_, nt_ = [], [], 0, 0
        for t in sub:
            cc += [r for _, _, r in alloc(t, "현재")]
            for _, sh, r in alloc(t, "자유6"):
                ff.append(r); ns_ += int(sh); nt_ += 1
        if not cc or not ff: continue
        print(f"  {str(idx[sub[0]])[5:16]}~{str(idx[sub[-1]])[5:16]:<10}"
              f"{len(sub):>5}{np.mean(cc):>+10.4f}{np.mean(ff):>+10.4f}"
              f"{np.mean(ff)-np.mean(cc):>+10.4f}{100*ns_/max(nt_,1):>7.0f}%")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"cfg.json").write_text(c.dump())
    pd.DataFrame({m: pd.Series(res[m]) for m in MODES}).to_csv(
        OUT/"trades.csv", index=False)
    log.info("저장 %s · %.1f분", OUT, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
