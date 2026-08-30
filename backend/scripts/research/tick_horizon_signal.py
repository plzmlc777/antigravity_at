"""보유 지평 × 신호 축 — 마찰을 넘는 조합이 있나.

## 왜 이 둘인가 (2026-08-30, 대표님 지시로 탐색 계속)

지금까지 좁혀진 제약:

    ① 방향은 예측 안 된다 (5회 실패)
    ② **엣지가 마찰과 같은 크기다** — 스프레드 0.04~0.10% vs 왕복 0.072%
    ③ 시각 가중이 맞다 (셀 가중은 부풀린다 — 이 세션에서 두 번 속았다)
    ④ 변동성을 키우면 잡음도 같이 커진다 (위험조정 개선 없음)

②가 근본이다. 공략은 둘 중 하나다.

  A. **보유를 늘린다** — 엣지가 시간에 비례해 크면 고정 수수료가 희석된다.
     동결 규칙은 120분이고 그 위로는 **한 번도 안 재봤다**.

  B. **다른 신호축** — 주문 흐름 불균형(`is_buyer_maker`)을 z_vel 처럼
     횡단면 순위로 쓴다. 결합 탐지기에서 필터로만 썼지 줄 세우는 데는 안 썼다.

## 검정 규약 (이 세션에서 배운 것 전부 반영)

  · **시각 가중** — 시각마다 스프레드를 내고 시각을 똑같이 센다
  · **비겹침** — 지평만큼 띄운 시각만
  · **회전 위약 최대통계량** — 격자(지평 × 신호) 전체 재탐색
  · 마찰 왕복 0.072%(롱·숏 두 다리) 고정

⚠ 지평이 길수록 비겹침 시각이 준다. 720분이면 5일에 8개뿐이다 — 못 믿는다.
  그래서 지평별 시각 수를 반드시 같이 본다.

사용:
  python3 -m scripts.research.tick_horizon_signal --reps 1000
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
TICKS = ROOT / "runs" / "ticks"
OUT = ROOT / "runs" / "research_track" / "regime"
log = logging.getLogger("horiz")

WIN_H, WINDOW, DELTA = 60, 360, 180
Q = 0.2                      # 상·하위 분위
HOLDS = (60, 120, 240, 360, 480, 720)
MIN_LIVE_TR, FEE2 = 5.0, 0.072


@dataclass(frozen=True)
class Cfg:
    n_sym: int = 200
    min_ticks: int = 2_000
    min_times: int = 20      # 이보다 시각이 적은 칸은 **격자에서 뺀다**
    reps: int = 1_000
    seed: int = 20260830


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--reps", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))
    uni = [s.strip().upper() for s in
           (ROOT / a.universe).read_text().split() if s.strip()]
    t0 = time.time()
    CLs, NTs, BQs, QVs = {}, {}, {}, {}
    for s in uni[::max(len(uni)//cfg.n_sym, 1)][:cfg.n_sym]:
        fs = sorted((TICKS / s).glob("*.parquet"))
        if not fs:
            continue
        try:
            t = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
        except Exception:                                       # noqa: BLE001
            continue
        t = t[(t.price > 0) & (t.qty > 0)]
        if len(t) < cfg.min_ticks:
            continue
        t = t.sort_values("ts_ms")
        qv = t.price * t.qty
        g = t.groupby(t.ts_ms // 60_000)
        c = g.price.last(); n = g.price.size()
        bq = qv.where(~t.is_buyer_maker, 0.0).groupby(t.ts_ms // 60_000).sum()
        tq = qv.groupby(t.ts_ms // 60_000).sum()
        ix = pd.to_datetime(c.index * 60_000, unit="ms", utc=True)
        for d, v in ((CLs, c), (NTs, n), (BQs, bq), (QVs, tq)):
            v.index = ix; d[s] = v
    idx = pd.date_range(min(c.index.min() for c in CLs.values()),
                        max(c.index.max() for c in CLs.values()), freq="1min", tz="UTC")
    CL = pd.DataFrame(CLs).reindex(idx).ffill()
    NT = pd.DataFrame(NTs).reindex(idx).fillna(0.0)
    BQ = pd.DataFrame(BQs).reindex(idx).fillna(0.0)
    QV = pd.DataFrame(QVs).reindex(idx).fillna(0.0)
    log.info("판 %d분 × %d종목 · %.1f분", len(CL), CL.shape[1], (time.time()-t0)/60)

    fw = CL.shift(-WIN_H) / CL - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(WINDOW, min_periods=WINDOW // 2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    p_ = rate.clip(0.01, 0.99)
    live = (NT.rolling(60).median().shift(1) >= MIN_LIVE_TR)

    SIG = {}
    SIG["z_vel(동결)"] = -(vel / (np.sqrt(p_*(1-p_)/(WINDOW/WIN_H)) * np.sqrt(2)))
    # ⚠ 부호를 뒤집어 **큰 값 = 롱** 으로 통일한다. 되돌림이므로 z_vel 낮은 쪽이 롱.
    imb = (2.0 * BQ - QV) / (QV + 1e-9)
    SIG["흐름불균형"] = -(imb.rolling(60).mean())          # 매수 과열 → 숏
    SIG["흐름t"] = -(imb.rolling(60).mean() * np.sqrt(NT.rolling(60).sum()))
    SIG["대금가중되돌림"] = -((CL / CL.shift(60) - 1.0)
                          * np.log1p(QV.rolling(60).sum()))
    SIG["단순되돌림60"] = -(CL / CL.shift(60) - 1.0)

    lvm = live.to_numpy()
    need = WINDOW + 2 * DELTA + WIN_H
    rows, keys, PER = [], [], {}
    # ⚠ 생존 마스크를 **수익률에도** 씌운다. 가격을 ffill 했으므로 틱이 없는
    #   구간은 수익률이 정확히 0.0 이다. 마스크를 신호에만 걸면 실측은 멀쩡한데
    #   **위약에서 짝이 깨져** 살아 있는 신호에 죽은 구간의 0 이 붙는다.
    #   그러면 스프레드가 거의 상수가 되어 귀무 t 가 41.86 까지 터진다(실측).
    RM = {h: np.where(lvm, ((CL.shift(-h) / CL - 1.0) * 100.0).to_numpy(), np.nan)
          for h in HOLDS}
    for h in HOLDS:
        rf = RM[h]
        pos = np.arange(need, len(CL) - h, h)          # ⚠ 비겹침
        if len(pos) < cfg.min_times:
            continue
        for nm, sg in SIG.items():
            X = np.where(lvm, sg.to_numpy(), np.nan)[pos]
            R = rf[pos]
            per = []
            for k in range(len(pos)):
                x, r = X[k], R[k]
                m = np.isfinite(x) & np.isfinite(r)
                if m.sum() < 20:
                    continue
                lo, hi = np.quantile(x[m], [Q, 1-Q])
                if hi <= lo:
                    continue
                per.append(float(r[m][x[m] >= hi].mean() - r[m][x[m] <= lo].mean()))
            v = np.asarray([p for p in per if np.isfinite(p)])
            # ⚠ 추정 불가능한 칸을 격자에 넣으면 위약 분포가 망가진다.
            #   720분은 5일에 시각 7개뿐이라 t 가 우연히 아무 값이나 나오고,
            #   최대통계량 귀무가 8.3 까지 부풀어 검정력이 0 이 된다(실측).
            if len(v) < cfg.min_times:
                continue
            t = v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))
            rows.append({"보유": h, "신호": nm, "시각수": len(v),
                         "스프레드": v.mean(), "수수료후": v.mean()-FEE2,
                         "표준편차": v.std(ddof=1), "t": t})
            keys.append((h, nm)); PER[(h, nm)] = (pos, X)
    R0 = pd.DataFrame(rows)
    print(f"\n■ 보유 × 신호 (시각 가중 · 비겹침 · 마찰 {FEE2}%)")
    print(R0.sort_values("t", ascending=False).to_string(
        index=False, float_format=lambda x: f"{x:.4f}"))

    # ── 회전 위약 최대통계량
    rng = np.random.default_rng(cfg.seed)
    n = len(CL)
    # ⚠ **시프트는 신호 자신의 기억보다 멀어야 한다.**
    #   z_vel 의 기억 = 창 360 + 간격 360 + 지평 60 = 780분. 그보다 짧게 밀면
    #   회전시킨 수익률이 **신호가 이미 아는 구간**에 남는다. z_vel 은 정의상
    #   과거 하락을 기억하므로(하락→선도승률↓→vel 음수) 그 짝은 우연이 아니라
    #   기계적이다. 실측: sh 151~546 에서 평균 스프레드가 -1.25 ~ +1.41 로
    #   진짜 크게 나와 귀무 t 가 22~27 까지 갔다(분산 문제가 아니었다).
    #   귀무가 진실보다 **넓어지면 검정력이 0** 이 된다.
    memory = need + max(HOLDS)
    lo_sh, hi_sh = memory, n - memory
    if hi_sh <= lo_sh:
        raise SystemExit(f"판 {n}분이 기억 {memory}분의 두 배가 안 된다 — "
                         f"회전 위약을 쓸 수 없다. 자료를 더 모아라.")
    log.info("위약 시프트 범위 %d ~ %d (기억 %d분)", lo_sh, hi_sh, memory)
    obs = float(R0.t.abs().max())
    null = np.empty(cfg.reps)
    for i in range(cfg.reps):
        sh = int(rng.integers(lo_sh, hi_sh))
        best = 0.0
        for (h, nm) in keys:
            pos, X = PER[(h, nm)]
            R = np.roll(RM[h], sh, axis=0)[pos]   # 마스크가 수익률과 함께 돈다
            per = []
            for k in range(len(pos)):
                x, r = X[k], R[k]
                m = np.isfinite(x) & np.isfinite(r)
                if m.sum() < 20:
                    continue
                lo, hi = np.quantile(x[m], [Q, 1-Q])
                if hi <= lo:
                    continue
                per.append(float(r[m][x[m] >= hi].mean() - r[m][x[m] <= lo].mean()))
            v = np.asarray([p for p in per if np.isfinite(p)])
            if len(v) >= cfg.min_times and v.std(ddof=1) > 0:
                best = max(best, abs(v.mean()/(v.std(ddof=1)/np.sqrt(len(v)))))
        null[i] = best
        if (i+1) % 200 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    pmax = float((null >= obs).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(keys)}칸)")
    print(f"  관측 최대 |t| {obs:.2f} · 위약 중앙 {np.median(null):.2f} "
          f"· 95분위 {np.quantile(null,.95):.2f} · 최대 {null.max():.2f}")
    print(f"  **p = {pmax:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    R0.to_csv(OUT / "horizon_signal.csv", index=False)
    (OUT / "horizon_signal.null.json").write_text(json.dumps(
        {"obs_max_t": obs, "p_max": pmax, "reps": cfg.reps,
         "null_median": float(np.median(null)),
         "null_p95": float(np.quantile(null, .95))}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
