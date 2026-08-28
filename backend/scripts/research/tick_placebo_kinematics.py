"""위약 승률의 **수준·속도·가속도** — 표준오차 단위로 수치화.

## 왜 (2026-08-28, 대표님 지시)

앞선 검정은 승률 추세의 **부호만** 썼다(오르면 롱). 결과는 부호가 반대였다.
그런데 부호만 보면 "조금 오르는 것"과 "급격히 오르는 것"이 같아진다. 크기를
넣으면 비선형이 보일 수 있다.

## 수치화 — 표준오차 단위

승률은 비율이라 표준오차가 √(p(1−p)/N) 이다. 그런데 승패 계열은 **겹치는 창**
이라 자기상관이 크다 — 창 W 분에 지평 h 분이면 독립 관측은 W/h 개뿐이다.
그걸 안 낮추면 z 가 몇 배로 부풀려진다.

    수준  lvl = rate(t)                          그 종목이 지금 얼마나 이기나
    속도  vel = rate(t) − rate(t−D)              오르고 있나
    가속  acc = vel(t) − vel(t−D)                더 빨리 오르고 있나

    z_vel = vel / (se·√2)      z_acc = acc / (se·2)      se = √(p(1−p)/(W/h))

## 방향을 미리 정하지 않는다

칸마다 **롱 수익**만 재고 같은 칸의 **롱 위약**과 견준다. 그러면 "이 상태에서
롱이 좋은가 나쁜가"가 그대로 나온다. 방향을 먼저 박으면 숏 쪽 정보를 잃는다.

⚠ 미래참조 차단 — rate 는 지평 h 만큼 뒤로 물러난 값만 쓴다(`shift(h)`).
⚠ 위약은 원형 회전. 롱 위약은 표류를 포함하므로 **초과분**으로만 판단한다.

사용:
  python3 -m scripts.research.tick_placebo_kinematics --smoke 60
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
log = logging.getLogger("kine")

WIN_H = 60          # 승률을 정의하는 지평(분)
WINDOW = 360        # 승률을 재는 창(분)
DELTA = 180         # 속도·가속을 재는 간격(분)
FWD = (30, 60, 120)
EDGES = (-2.0, -1.0, -0.3, 0.3, 1.0, 2.0)
LABELS = ("≤-2", "-2~-1", "-1~-0.3", "-0.3~0.3", "0.3~1", "1~2", "≥2")


@dataclass(frozen=True)
class Cfg:
    step_min: int = 5
    min_ticks: int = 2_000
    min_live_tr: float = 5.0
    fee_pct: float = 0.036
    reps: int = 200
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
    b = pd.DataFrame({"cl": g.price.last(), "ntr": g.price.size()})
    b.index = pd.to_datetime(b.index * 60_000, unit="ms", utc=True)
    b = b.reindex(pd.date_range(b.index.min(), b.index.max(), freq="1min",
                                tz="UTC"))
    b["cl"] = b.cl.ffill(); b["ntr"] = b.ntr.fillna(0.0)
    need = WIN_H + WINDOW + 2 * DELTA + max(FWD) + 30
    if len(b) < need:
        return None
    cl = b.cl.to_numpy(float); n = len(cl)
    fw = np.full(n, np.nan)
    fw[:n - WIN_H] = cl[WIN_H:] / cl[:n - WIN_H] - 1.0
    win = pd.Series(np.where(np.isfinite(fw), (fw > 0).astype(float), np.nan))
    # ⚠ shift(WIN_H) — 앵커의 승패는 지평이 지나야 확정된다
    rate = win.rolling(WINDOW, min_periods=WINDOW // 2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    acc = vel - vel.shift(DELTA)
    # ⚠ 유효 표본 = 창/지평. 겹치는 창을 독립으로 세면 z 가 몇 배 부풀려진다
    neff = max(WINDOW / WIN_H, 1.0)
    p = rate.clip(0.01, 0.99)
    se = np.sqrt(p * (1 - p) / neff)
    out = {"sym": sym, "n": n, "cl": cl,
           "lvl": rate.to_numpy(),
           "z_vel": (vel / (se * np.sqrt(2))).to_numpy(),
           "z_acc": (acc / (se * 2.0)).to_numpy(),
           "live": (b.ntr.rolling(60).median().shift(1) >= cfg.min_live_tr
                    ).to_numpy(),
           "hour": ((b.index - pd.Timestamp("1970-01-01", tz="UTC"))
                    // pd.Timedelta(hours=1)).to_numpy()}
    for f in FWD:
        r = np.full(n, np.nan)
        r[:n - f] = (cl[f:] / cl[:n - f] - 1.0) * 100.0
        out[f"r_{f}"] = r
    return out


def scan(S, cfg: Cfg, shift=None) -> dict:
    acc_: dict = {}
    for si, s in enumerate(S):
        n = s["n"]
        idx = np.arange(0, n, cfg.step_min)
        idx = idx[s["live"][idx] == True]                        # noqa: E712
        if not len(idx):
            continue
        for axis in ("z_vel", "z_acc"):
            v = s[axis][idx]
            ok = np.isfinite(v)
            if ok.sum() < 20:
                continue
            ii, vv = idx[ok], v[ok]
            bin_id = np.digitize(vv, EDGES)
            pos = (ii + shift[si]) % n if shift is not None else ii
            for f in FWD:
                r = s[f"r_{f}"][pos]
                m = np.isfinite(r)
                if m.sum() < 20:
                    continue
                for bi in range(len(LABELS)):
                    sel = m & (bin_id == bi)
                    if sel.sum() < 5:
                        continue
                    k = (axis, LABELS[bi], f)
                    a = acc_.setdefault(k, {"r": [], "hr": []})
                    a["r"].append(r[sel]); a["hr"].append(s["hour"][pos][sel])
        # 사분면 — 속도와 가속의 부호 조합
        zv, za = s["z_vel"][idx], s["z_acc"][idx]
        ok = np.isfinite(zv) & np.isfinite(za)
        if ok.sum() >= 20:
            ii = idx[ok]
            quad = np.where(zv[ok] > 0,
                            np.where(za[ok] > 0, "상승가속", "상승감속"),
                            np.where(za[ok] > 0, "하락감속", "하락가속"))
            pos = (ii + shift[si]) % n if shift is not None else ii
            for f in FWD:
                r = s[f"r_{f}"][pos]
                m = np.isfinite(r)
                for q in ("상승가속", "상승감속", "하락감속", "하락가속"):
                    sel = m & (quad == q)
                    if sel.sum() < 5:
                        continue
                    k = ("사분면", q, f)
                    a = acc_.setdefault(k, {"r": [], "hr": []})
                    a["r"].append(r[sel]); a["hr"].append(s["hour"][pos][sel])
    out = {}
    for k, v in acc_.items():
        r = np.concatenate(v["r"]); hr = np.concatenate(v["hr"])
        if len(r) < 200:
            continue
        u, inv = np.unique(hr, return_inverse=True)
        cm = (np.bincount(inv, weights=r, minlength=len(u))
              / np.maximum(np.bincount(inv, minlength=len(u)), 1))
        t = (cm.mean() / (cm.std(ddof=1) / np.sqrt(len(cm)))
             if len(cm) > 3 and cm.std(ddof=1) > 0 else 0.0)
        out[k] = {"n": int(len(r)), "mean": float(r.mean()),
                  "win": float(100.0 * (r > 0).mean()), "t": float(t)}
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
    log.info("설정 %s · 지평 %d · 창 %d · 간격 %d",
             json.dumps(asdict(cfg), ensure_ascii=False), WIN_H, WINDOW, DELTA)

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
            log.warning("%s 실패: %s", s, str(e)[:90]); x = None
        if x:
            S.append(x)
        if i % 100 == 0 or i == len(syms):
            log.info("[%d/%d] %.1f분", i, len(syms), (time.time()-t0)/60)
    log.info("종목 %d", len(S))

    obs = scan(S, cfg)
    LEN = np.array([x["n"] for x in S])
    rng = np.random.default_rng(cfg.seed)
    pl: dict = {}
    for r in range(cfg.reps):
        for k, v in scan(S, cfg, rng.integers(1, LEN)).items():
            pl.setdefault(k, []).append(v)
        if (r + 1) % 25 == 0:
            log.info("위약 %d/%d · %.1f분", r+1, cfg.reps, (time.time()-t0)/60)

    # ── 칸마다 위약 평균 행렬 (reps × cells)
    keys = [k for k in obs if len(pl.get(k, [])) == cfg.reps]
    M = np.array([[pl[k][r]["mean"] for k in keys] for r in range(cfg.reps)])
    obs_v = np.array([obs[k]["mean"] for k in keys])

    # ⚠ **하나 빼기 표준화**. 회전 자신이 자기 기준선에 들어가면 z 가 작아져
    #   귀무가 약해진다. 관측은 전체 평균·표준편차로 표준화한다.
    mu, sd = M.mean(0), M.std(0, ddof=1)
    sd = np.where(sd > 0, sd, np.nan)
    z_obs = (obs_v - mu) / sd
    obs_max = float(np.nanmax(np.abs(z_obs)))
    null = np.empty(cfg.reps)
    for r in range(cfg.reps):
        keep = np.ones(cfg.reps, bool); keep[r] = False
        m2, s2 = M[keep].mean(0), M[keep].std(0, ddof=1)
        s2 = np.where(s2 > 0, s2, np.nan)
        null[r] = float(np.nanmax(np.abs((M[r] - m2) / s2)))
    p_max = float((null >= obs_max).mean())

    rows = []
    for i, k in enumerate(keys):
        o = obs[k]
        pm = np.array([x["mean"] for x in pl[k]])
        pw = np.array([x["win"] for x in pl[k]])
        rows.append({"axis": k[0], "bin": k[1], "fwd": k[2], **o,
                     "pl_mean": float(pm.mean()), "pl_sd": float(pm.std(ddof=1)),
                     "excess": float(o["mean"] - pm.mean()),
                     "net_excess": float(o["mean"] - pm.mean() - cfg.fee_pct),
                     "z": float(z_obs[i]),
                     "pl_win": float(pw.mean()),
                     "win_ex": float(o["win"] - pw.mean()),
                     "pct": float(100 * (pm < o["mean"]).mean())})
    R = pd.DataFrame(rows).sort_values("z", key=abs, ascending=False)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_placebo_kinematics.csv"
    R.to_csv(path, index=False)
    path.with_suffix(".null.json").write_text(json.dumps(
        {"obs_max_z": obs_max, "p_max": p_max, "reps": cfg.reps,
         "n_cells": len(keys),
         "null_median": float(np.median(null)),
         "null_p95": float(np.quantile(null, 0.95)),
         "null_max": float(null.max()),
         "null": [round(float(x), 4) for x in null]},
        ensure_ascii=False, indent=1))
    print(f"\n■ 최대통계량 위약 ({cfg.reps}회 · {len(keys)}칸 재탐색 · 하나빼기 표준화)")
    print(f"  관측 최대 |z| {obs_max:.2f} · 위약 중앙 {np.median(null):.2f} "
          f"· 95분위 {np.quantile(null,0.95):.2f} · 최대 {null.max():.2f}")
    print(f"  **p = {p_max:.3f}**")
    p95 = float(np.quantile(null, 0.95))
    s2 = R[R.z.abs() >= p95]
    print(f"\n■ 위약 95분위({p95:.2f}) 를 넘은 칸: {len(s2)} / {len(R)}")
    if len(s2):
        print(s2[["axis", "bin", "fwd", "n", "mean", "pl_mean", "excess",
                  "net_excess", "z", "win_ex"]].to_string(
              index=False, float_format=lambda x: f"{x:.3f}"))
    log.info("저장 %s — %d칸 · %.1f분", path, len(R), (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
