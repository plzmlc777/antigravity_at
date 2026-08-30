"""운동학 신호에 익절·손절을 달면 — **대조군도 같은 규칙을 쓴다**.

## 왜 이 설계 (2026-08-28)

동결 규칙은 시간 청산만 한다(120분, 익절·손절 없음). 검정한 형태가 그것이기
때문이다. 익절·손절을 달려면 **연구에서 먼저** 재야 한다.

그런데 오늘 이 함정을 밟았다 — 같은 원장·같은 전략인데 대조군의 청산 규칙만
다르게 잡으니 부호가 뒤집혔다.

    무작위 시각 + **같은** 익절·손절   롱 초과 +0.393%p
    무작위 시각 + 무제한 보유          롱 초과 -0.590%p

익절이 상방을 자르는데 무제한 보유와 대면 전략이 부당하게 진다. 그래서
여기서는 **위약도 같은 익절·손절을 적용한다**. 원형 회전으로 진입 위치만
옮기고 청산 규칙은 그대로 둔다.

## 규약

  · 진입가 = 그 분 종가. 걸음은 **다음 분부터** — 진입 봉은 이미 지났다
  · 같은 분에 익절·손절 둘 다 닿으면 **손절 우선**(보수적). 분 안 순서는 모른다
  · 만기까지 아무것도 안 닿으면 종가 청산
  · 마찰 0.036% 왕복(지정가). 익절은 지정가로 채워진다고 본다
  · 손절은 **불리하게** 본다 — 손절가 그대로 체결(슬리피지 0 가정). 실전은 더 나쁘다

⚠ 격자 60칸이므로 최대통계량 위약(교훈#95).
⚠ 표본 1.96일. 지형이지 결론이 아니다.

사용:
  python3 -m scripts.research.tick_kinematics_tpsl --smoke 60
"""
from __future__ import annotations

import argparse
import itertools
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
log = logging.getLogger("tpsl")

# ── 신호는 동결분 그대로
WIN_H, WINDOW, DELTA = 60, 360, 180
Z_LO, Z_HI, ACC_MAX = -1.25, -0.25, 0.5
STEP, MIN_LIVE_TR = 5, 5.0

TPS = (0.5, 1.0, 1.5, 2.0, 3.0)
SLS = (0.5, 1.0, 1.5, 2.0, 3.0, 99.0)      # 99 = 손절 없음
HOLDS = (60, 120)


@dataclass(frozen=True)
class Cfg:
    fee_pct: float = 0.036
    reps: int = 200
    min_ticks: int = 2_000
    seed: int = 20260828


def build(sym: str, cfg: Cfg):
    d = TICKS / sym
    fs = sorted(d.glob("*.parquet"))
    if not fs:
        return None
    t = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
                   for f in fs], ignore_index=True)
    t = t[(t.price > 0) & (t.qty > 0)]
    if len(t) < cfg.min_ticks:
        return None
    g = t.sort_values("ts_ms").groupby(t.ts_ms // 60_000)
    b = pd.DataFrame({"cl": g.price.last(), "hi": g.price.max(),
                      "lo": g.price.min(), "ntr": g.price.size()})
    b.index = pd.to_datetime(b.index * 60_000, unit="ms", utc=True)
    b = b.reindex(pd.date_range(b.index.min(), b.index.max(), freq="1min",
                                tz="UTC"))
    b[["cl", "hi", "lo"]] = b[["cl", "hi", "lo"]].ffill()
    b["ntr"] = b.ntr.fillna(0.0)
    n = len(b)
    if n < WIN_H + WINDOW + 2 * DELTA + max(HOLDS) + 30:
        return None
    c = b.cl.to_numpy(float)
    fw = np.full(n, np.nan)
    fw[:n - WIN_H] = c[WIN_H:] / c[:n - WIN_H] - 1.0
    win = pd.Series(np.where(np.isfinite(fw), (fw > 0).astype(float), np.nan))
    rate = win.rolling(WINDOW, min_periods=WINDOW // 2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    acc = vel - vel.shift(DELTA)
    neff = max(WINDOW / WIN_H, 1.0)
    p = rate.clip(0.01, 0.99)
    se = np.sqrt(p * (1 - p) / neff)
    zv = (vel / (se * np.sqrt(2))).to_numpy()
    za = (acc / (se * 2.0)).to_numpy()
    live = (b.ntr.rolling(60).median().shift(1) >= MIN_LIVE_TR).to_numpy()
    # ⚠ `b.index.minute % STEP == 0` 은 이미 ndarray 다 — .to_numpy() 가 없다.
    #   그리고 벽시계 격자만 쓴다(종목별 시작 시각이 달라 어긋난다).
    grid = np.asarray(b.index.minute % STEP == 0)
    ok = (np.isfinite(zv) & np.isfinite(za) & live & grid
          & (zv >= Z_LO) & (zv <= Z_HI) & (za < ACC_MAX))
    ok[n - max(HOLDS) - 1:] = False
    return {"cl": c, "hi": b.hi.to_numpy(float), "lo": b.lo.to_numpy(float),
            "ev": np.where(ok)[0], "n": n,
            "elig": np.where(live & grid & np.isfinite(zv))[0]}


def outcomes(S, picks, cfg: Cfg) -> dict:
    """(종목idx, 위치) 목록에 대해 모든 (익절·손절·만기) 칸의 손익."""
    H = max(HOLDS)
    ent, hi_m, lo_m, cl_end = [], [], [], {}
    for si, pos in picks:
        s = S[si]
        e = s["cl"][pos]
        idx = pos[:, None] + np.arange(1, H + 1)[None, :]
        ent.append(e)
        hi_m.append(s["hi"][idx] / e[:, None] - 1.0)
        lo_m.append(1.0 - s["lo"][idx] / e[:, None])
        for h in HOLDS:
            cl_end.setdefault(h, []).append(s["cl"][pos + h] / e - 1.0)
    if not ent:
        return {}
    up = np.concatenate(hi_m) * 100.0        # 유리 최대 (누적 전)
    dn = np.concatenate(lo_m) * 100.0        # 불리 최대
    cum_up = np.maximum.accumulate(up, axis=1)
    cum_dn = np.maximum.accumulate(dn, axis=1)
    endr = {h: np.concatenate(v) * 100.0 for h, v in cl_end.items()}
    res = {}
    for tp, sl, h in itertools.product(TPS, SLS, HOLDS):
        cu, cd = cum_up[:, :h], cum_dn[:, :h]
        hit_u = cu >= tp
        hit_d = cd >= sl
        t_u = np.where(hit_u.any(1), hit_u.argmax(1), 10 ** 6)
        t_d = np.where(hit_d.any(1), hit_d.argmax(1), 10 ** 6)
        # ⚠ 같은 분에 둘 다 닿으면 **손절 우선**. 분 안 순서는 모른다.
        pnl = np.where(t_d <= t_u, np.where(t_d < 10 ** 6, -sl, np.nan),
                       np.where(t_u < 10 ** 6, tp, np.nan))
        pnl = np.where(np.isnan(pnl), endr[h], pnl)
        res[(tp, sl, h)] = pnl - cfg.fee_pct
    return res


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--reps", type=int, default=None)
    p.add_argument("--out", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    log.info("설정 %s · 격자 %d칸", json.dumps(asdict(cfg), ensure_ascii=False),
             len(TPS) * len(SLS) * len(HOLDS))

    syms = [s.strip().upper() for s in
            (ROOT / a.universe).read_text().split() if s.strip()]
    if a.smoke:
        syms = syms[:a.smoke]
    t0 = time.time()
    S = []
    for i, s in enumerate(syms, 1):
        try:
            x = build(s, cfg)
        except Exception as e:                                  # noqa: BLE001
            log.warning("%s 실패: %s", s, str(e)[:80]); x = None
        if x and len(x["ev"]):
            S.append(x)
        if i % 100 == 0 or i == len(syms):
            log.info("[%d/%d] %.1f분", i, len(syms), (time.time()-t0)/60)
    n_ev = sum(len(x["ev"]) for x in S)
    log.info("종목 %d · 사건 %s · %.1f분", len(S), f"{n_ev:,}",
             (time.time()-t0)/60)

    obs = outcomes(S, [(i, s["ev"]) for i, s in enumerate(S)], cfg)
    log.info("관측 완료 %.1f분", (time.time()-t0)/60)

    # ── 위약: 진입 위치만 원형 회전. **청산 규칙은 그대로**
    rng = np.random.default_rng(cfg.seed)
    acc: dict = {}
    # ⚠ 위약은 **원형 회전**이다. 무작위로 흩뿌려 뽑으면 안 된다 —
    #   실측 사건은 국면을 타서 시간에 뭉쳐 있는데 흩뿌린 표본은 그렇지 않아
    #   위약 분포가 실제보다 좁아지고 z 가 부풀려진다(2026-08-28: 흩뿌리기 58,
    #   그 전에 건수까지 틀렸을 땐 218). 회전은 건수·간격·뭉침을 전부 보존한다.
    for r in range(cfg.reps):
        picks = []
        for i, s in enumerate(S):
            ev = s["ev"]
            lim = s["n"] - max(HOLDS) - 1
            if len(ev) < 1 or lim < 10:
                continue
            # ⚠ 시프트는 **신호의 기억 + 보유** 보다 길어야 한다(교훈#108).
            #   짧으면 위약 거래가 실측 거래와 시간이 겹쳐 위약 평균이 실측에
            #   붙고, 귀무가 진실보다 넓어져 무엇도 통과 못 한다.
            #   기억 = 창 360 + 간격 180 + 지평 60 + 보유 = 720분.
            mem = WINDOW + DELTA + WIN_H + max(HOLDS)
            if lim <= 2 * mem:
                continue          # 이 종목은 회전 위약을 쓸 만큼 길지 않다
            sh = int(rng.integers(mem, lim - mem))
            picks.append((i, (ev + sh) % lim))
        for k, v in outcomes(S, picks, cfg).items():
            acc.setdefault(k, []).append(float(np.nanmean(v)))
        if (r + 1) % 25 == 0:
            log.info("위약 %d/%d · %.1f분", r+1, cfg.reps, (time.time()-t0)/60)

    rows = []
    for k, v in obs.items():
        pl = np.asarray(acc.get(k, []))
        if not len(pl):
            continue
        m = float(np.nanmean(v))
        sd = float(pl.std(ddof=1))
        rows.append({"tp": k[0], "sl": k[1] if k[1] < 99 else np.nan,
                     "hold": k[2], "n": int(np.isfinite(v).sum()),
                     "net_mean": m, "pl_mean": float(pl.mean()),
                     "excess": m - float(pl.mean()),
                     "z": (m - pl.mean()) / sd if sd > 0 else 0.0,
                     "total": m * int(np.isfinite(v).sum()),
                     "win": float(100.0 * np.nanmean(v > 0))})
    R = pd.DataFrame(rows)
    if R.empty:
        raise SystemExit("한 칸도 못 냈다 — 종목·사건 수를 확인하라"
                         f" (종목 {len(S)} · 사건 {n_ev})")
    obs_max = float(R.z.abs().max())
    keys = list(obs.keys())
    M = np.array([acc[k] for k in keys if k in acc]).T          # reps × cells
    mu, sd = M.mean(0), M.std(0, ddof=1)
    null = np.empty(len(M))
    for r in range(len(M)):
        keep = np.ones(len(M), bool); keep[r] = False
        m2, s2 = M[keep].mean(0), M[keep].std(0, ddof=1)
        s2 = np.where(s2 > 0, s2, np.nan)
        null[r] = float(np.nanmax(np.abs((M[r] - m2) / s2)))
    p_max = float((null >= obs_max).mean())

    R = R.sort_values("z", key=abs, ascending=False)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_kinematics_tpsl.csv"
    R.to_csv(path, index=False)
    path.with_suffix(".null.json").write_text(json.dumps(
        {"obs_max_z": obs_max, "p_max": p_max, "reps": cfg.reps,
         "null_median": float(np.median(null)),
         "null_p95": float(np.quantile(null, .95)),
         "null_max": float(null.max())}, ensure_ascii=False, indent=1))
    print(f"\n■ 최대통계량 위약 ({cfg.reps}회 · {len(R)}칸 · 위약도 **같은 익절·손절**)")
    print(f"  관측 최대 |z| {obs_max:.2f} · 위약 중앙 {np.median(null):.2f} "
          f"· 95분위 {np.quantile(null,.95):.2f} · 최대 {null.max():.2f}")
    print(f"  **p = {p_max:.3f}**")
    print(f"\n■ |z| 상위 14칸")
    print(R.head(14).to_string(index=False,
          float_format=lambda x: f"{x:.3f}"))
    log.info("저장 %s · %.1f분", path, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
