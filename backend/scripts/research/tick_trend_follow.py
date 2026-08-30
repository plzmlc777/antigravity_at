"""일반 규모 움직임에서 **추세추종** — 어디서 부호가 뒤집히나.

## 왜 (2026-08-29, 대표님 질문)

지금까지 나온 결과가 규모마다 방향이 다르다.

    1분 극단 점프(z>10)   되돌림 (상당 부분 호가 튐 — 1분 미루면 30% 로 축소)
    30분 5% 충격          **지속** (되돌림 방향으로 걸면 -0.4%)
    승률 속도 z_vel       되돌림 (양쪽 꼬리 모두)

**중간 규모**를 안 봤다. 작은 움직임은 되돌리고 큰 움직임은 이어진다면 그
사이 어딘가에 뒤집히는 지점이 있다. 그 지점을 찾는다.

## 설계

    과거   W분 수익률을 **변동성으로 정규화** — 종목 간 비교가 되게
           z_ret = ret_W / (실현변동성 × √(W/60))
    방향   **추세추종**. z_ret>0 이면 롱, <0 이면 숏
    구간   z_ret 을 촘촘히 갈라 어디서 초과분 부호가 바뀌는지 본다

⚠ 롱과 숏을 **따로** 낸다. 합치면 시장 표류가 한쪽에 숨는다(교훈#91).
   그리고 위약도 방향별로 따로 세운다 — 롱 위약과 숏 위약은 기준선이 다르다
   (실측: 120분 롱 위약 +0.18% vs 숏 위약 -0.25%).
⚠ 위약은 **원형 회전**. 흩뿌려 뽑으면 뭉침이 깨져 위약이 좁아지고 z 가
   부풀려진다(2026-08-28 실측: 흩뿌리기 58 → 회전 15).
⚠ 격자가 크므로 최대통계량(교훈#95).

사용:
  python3 -m scripts.research.tick_trend_follow --smoke 60
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
log = logging.getLogger("trend")

WINS = (5, 15, 30, 60)                 # 과거를 재는 창(분)
FWD = (15, 30, 60, 120)                # 선도(분)
EDGES = (-4, -3, -2, -1.5, -1, -0.5, 0.5, 1, 1.5, 2, 3, 4)
LABELS = ("≤-4", "-4~-3", "-3~-2", "-2~-1.5", "-1.5~-1", "-1~-0.5",
          "-0.5~0.5", "0.5~1", "1~1.5", "1.5~2", "2~3", "3~4", "≥4")


@dataclass(frozen=True)
class Cfg:
    step_min: int = 5
    lookback: int = 60          # 실현변동성 창
    min_live_tr: float = 5.0
    min_ticks: int = 2_000
    fee_pct: float = 0.036
    min_n: int = 200
    reps: int = 300
    seed: int = 20260829


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
    b = pd.DataFrame({"cl": g.price.last(), "ntr": g.price.size()})
    b.index = pd.to_datetime(b.index * 60_000, unit="ms", utc=True)
    b = b.reindex(pd.date_range(b.index.min(), b.index.max(), freq="1min",
                                tz="UTC"))
    b["cl"] = b.cl.ffill(); b["ntr"] = b.ntr.fillna(0.0)
    n = len(b)
    if n < cfg.lookback + max(WINS) + max(FWD) + 30:
        return None
    c = b.cl.to_numpy(float)
    lr = np.log(np.maximum(c, 1e-12))
    rv1 = pd.Series(np.diff(lr, prepend=lr[0])).rolling(cfg.lookback).std()
    out = {"n": n, "cl": c,
           "live": (b.ntr.rolling(60).median().shift(1) >= cfg.min_live_tr).to_numpy(),
           "grid": np.asarray(b.index.minute % cfg.step_min == 0),
           "hour": ((b.index - pd.Timestamp("1970-01-01", tz="UTC"))
                    // pd.Timedelta(hours=1)).to_numpy()}
    for W in WINS:
        r = np.full(n, np.nan)
        r[W:] = (c[W:] / c[:-W] - 1.0) * 100.0
        # 변동성 정규화 — 종목·시점 간 비교가 되게
        out[f"z_{W}"] = r / (rv1.to_numpy() * np.sqrt(W) * 100.0 + 1e-12)
    for f in FWD:
        r = np.full(n, np.nan)
        r[:n - f] = (c[f:] / c[:n - f] - 1.0) * 100.0
        out[f"r_{f}"] = r
    return out


def scan(S, cfg: Cfg, shift=None) -> dict:
    acc: dict = {}
    for si, s in enumerate(S):
        n = s["n"]
        base = np.where(s["live"] & s["grid"])[0]
        base = base[(base >= cfg.lookback + max(WINS))
                    & (base < n - max(FWD) - 1)]
        if not len(base):
            continue
        for W in WINS:
            z = s[f"z_{W}"][base]
            ok = np.isfinite(z)
            if ok.sum() < 20:
                continue
            ii, zz = base[ok], z[ok]
            bi = np.digitize(zz, EDGES)
            pos = ((ii + shift[si]) % (n - max(FWD) - 1)) if shift is not None else ii
            sgn = np.sign(zz); sgn[sgn == 0] = 1.0
            for f in FWD:
                r = s[f"r_{f}"][pos]
                m = np.isfinite(r)
                if m.sum() < 20:
                    continue
                hr = s["hour"][pos]
                for k in range(len(LABELS)):
                    sel = m & (bi == k)
                    if sel.sum() < 3:
                        continue
                    # 추세추종 = 움직인 방향으로
                    key = (W, LABELS[k], f, "롱" if sgn[sel][0] > 0 else "숏")
                    a = acc.setdefault(key, {"r": [], "hr": []})
                    a["r"].append(sgn[sel] * r[sel]); a["hr"].append(hr[sel])
    out = {}
    for k, v in acc.items():
        r = np.concatenate(v["r"]); hr = np.concatenate(v["hr"])
        if len(r) < cfg.min_n:
            continue
        u, inv = np.unique(hr, return_inverse=True)
        cm = (np.bincount(inv, weights=r, minlength=len(u))
              / np.maximum(np.bincount(inv, minlength=len(u)), 1))
        out[k] = {"n": int(len(r)), "mean": float(r.mean()),
                  "win": float(100.0 * (r > 0).mean()),
                  "t": float(cm.mean() / (cm.std(ddof=1) / np.sqrt(len(cm))))
                       if len(cm) > 3 and cm.std(ddof=1) > 0 else 0.0}
    return out


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
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))

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
        if x:
            S.append(x)
        if i % 100 == 0 or i == len(syms):
            log.info("[%d/%d] %.1f분", i, len(syms), (time.time()-t0)/60)
    log.info("종목 %d", len(S))

    obs = scan(S, cfg)
    LEN = np.array([x["n"] for x in S])
    MEM = cfg.lookback + max(WINS) + max(FWD)
    log.info("위약 시프트 하한 %d분 (기억) · 판 중앙 %d분", MEM, int(np.median(LEN)))
    rng = np.random.default_rng(cfg.seed)
    pl: dict = {}
    for r in range(cfg.reps):
        # ⚠ 시프트 하한 = 신호 기억(실현변동성창 + 과거창) + 선도. 교훈#108.
        for k, v in scan(S, cfg,
                         rng.integers(MEM, np.maximum(LEN - MEM, MEM + 1))).items():
            pl.setdefault(k, []).append(v["mean"])
        if (r + 1) % 50 == 0:
            log.info("위약 %d/%d · %.1f분", r+1, cfg.reps, (time.time()-t0)/60)

    keys = [k for k in obs if len(pl.get(k, [])) == cfg.reps]
    M = np.array([[pl[k][r] for k in keys] for r in range(cfg.reps)])
    ov = np.array([obs[k]["mean"] for k in keys])
    mu, sd = M.mean(0), M.std(0, ddof=1)
    sd = np.where(sd > 0, sd, np.nan)
    z = (ov - mu) / sd
    obs_max = float(np.nanmax(np.abs(z)))
    null = np.empty(cfg.reps)
    for r in range(cfg.reps):
        keep = np.ones(cfg.reps, bool); keep[r] = False
        m2, s2 = M[keep].mean(0), M[keep].std(0, ddof=1)
        s2 = np.where(s2 > 0, s2, np.nan)
        null[r] = float(np.nanmax(np.abs((M[r] - m2) / s2)))
    p_max = float((null >= obs_max).mean())

    R = pd.DataFrame([{"win_min": k[0], "bin": k[1], "fwd": k[2], "dir": k[3],
                       **obs[k], "pl_mean": float(mu[i]),
                       "excess": float(ov[i] - mu[i]),
                       "net_excess": float(ov[i] - mu[i] - cfg.fee_pct),
                       "z": float(z[i])} for i, k in enumerate(keys)])
    R = R.sort_values("z", key=abs, ascending=False)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_trend_follow.csv"
    R.to_csv(path, index=False)
    path.with_suffix(".null.json").write_text(json.dumps(
        {"obs_max_z": obs_max, "p_max": p_max, "reps": cfg.reps,
         "n_cells": len(keys), "null_median": float(np.median(null)),
         "null_p95": float(np.quantile(null, .95)),
         "null_max": float(null.max())}, ensure_ascii=False, indent=1))
    print(f"\n■ 최대통계량 위약 ({cfg.reps}회 · {len(keys)}칸 · 원형회전 · 하나빼기)")
    print(f"  관측 최대 |z| {obs_max:.2f} · 위약 중앙 {np.median(null):.2f} "
          f"· 95분위 {np.quantile(null,.95):.2f} · 최대 {null.max():.2f}")
    print(f"  **p = {p_max:.3f}**")
    log.info("저장 %s · %.1f분", path, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
