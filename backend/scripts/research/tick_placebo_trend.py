"""위약 승률의 **추세**를 신호로 — 가장 단순한 형태.

## 착상 (대표님, 2026-08-28)

"그 종목에서 아무 때나 롱을 걸었을 때의 성공률"이 위약이다. 그게 **오르고
있으면** 그 종목은 상승 국면에 들어가는 중이다. 그때 롱을 친다. 반대도 같이.

앞선 검정에서 위약 승률이 방향별로 크게 갈렸다 — 롱 위약 47~52%, 숏 위약
45~47%. 이 값이 종목·시점마다 움직인다면 그 움직임 자체가 국면 신호다.

## 🚫 미래참조를 막는 한 줄

시각 t 에서 "지평 h 짜리 승률"을 쓰려면 그 승부가 **이미 끝나 있어야** 한다.
앵커 j 의 승패는 j+h 에 확정되므로 t 에서 쓸 수 있는 건 **j ≤ t−h** 뿐이다.

    rate(t) = mean(win[t-h-W : t-h])       ← h 만큼 뒤로 물러난다
    rise(t) = rate(t) − rate(t-D)

이 h 만큼의 후퇴를 빼먹으면 승률이 미래를 안다. 이 세션에서 창 겹침으로
t 가 1.7 → 95.8 이 된 적이 있다 — 같은 계열의 실수다.

## 무엇과 비교하나

  ① 방향별 위약   원형 회전. 롱 위약과 숏 위약은 기준선이 다르다(교훈#101)
  ② 반대 방향     rise>0 에 숏, rise<0 에 롱 (교훈#91)
  ③ 항상 롱       국면 신호 없이 그냥 롱 — 표류만큼은 누구나 번다

⚠ 판정은 **총손익**과 위약 대비 초과분. 승률은 성과가 아니다 — 이 세션에서
  급등 뒤 숏이 승률은 위약보다 높은데 수익은 마이너스였다.

사용:
  python3 -m scripts.research.tick_placebo_trend --smoke 60
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
log = logging.getLogger("pltrend")

WIN_H = (30, 60)          # 승률을 정의하는 지평(분)
WINDOWS = (120, 360)      # 승률을 재는 창(분)
DELTAS = (60, 180)        # "오르고 있다"를 재는 뒤돌아보기(분)
FWD = (15, 30, 60, 120)   # 실제 보유(분)


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
    need = max(WIN_H) + max(WINDOWS) + max(DELTAS) + max(FWD) + 30
    if len(b) < need:
        return None
    cl = b.cl.to_numpy(float)
    n = len(cl)
    out = {"sym": sym, "cl": cl, "n": n,
           "live": (b.ntr.rolling(60).median().shift(1) >= cfg.min_live_tr
                    ).to_numpy(),
           "hour": ((b.index - pd.Timestamp("1970-01-01", tz="UTC"))
                    // pd.Timedelta(hours=1)).to_numpy()}
    for h in WIN_H:
        fw = np.full(n, np.nan)
        fw[:n - h] = cl[h:] / cl[:n - h] - 1.0
        win = pd.Series(np.where(np.isfinite(fw), (fw > 0).astype(float),
                                 np.nan))
        for W in WINDOWS:
            # ⚠ shift(h) — 앵커 j 의 승패는 j+h 에 확정된다. h 만큼 물러난다.
            rate = win.rolling(W, min_periods=W // 2).mean().shift(h)
            for D in DELTAS:
                out[f"rise_{h}_{W}_{D}"] = (rate - rate.shift(D)).to_numpy()
    for f in FWD:
        r = np.full(n, np.nan)
        r[:n - f] = (cl[f:] / cl[:n - f] - 1.0) * 100.0
        out[f"r_{f}"] = r
    return out


def scan(S, cfg: Cfg, shift=None) -> dict:
    acc: dict = {}
    for si, s in enumerate(S):
        n = s["n"]
        idx = np.arange(0, n, cfg.step_min)
        idx = idx[s["live"][idx] == True]                        # noqa: E712
        if not len(idx):
            continue
        for h, W, D in itertools.product(WIN_H, WINDOWS, DELTAS):
            rise = s[f"rise_{h}_{W}_{D}"][idx]
            ok = np.isfinite(rise)
            if ok.sum() < 20:
                continue
            ii = idx[ok]; rr = rise[ok]
            pos = (ii + shift[si]) % n if shift is not None else ii
            sgn = np.sign(rr); sgn[sgn == 0] = 1.0
            for f in FWD:
                v = s[f"r_{f}"][pos]
                m = np.isfinite(v)
                if m.sum() < 20:
                    continue
                hr = s["hour"][pos][m]
                for arm, sg in (("실측", sgn[m]), ("반대", -sgn[m]),
                                ("항상롱", np.ones(m.sum()))):
                    k = (h, W, D, f, arm)
                    a = acc.setdefault(k, {"r": [], "hr": []})
                    a["r"].append(sg * v[m]); a["hr"].append(hr)
                # 방향별로도 따로 — 롱 신호일 때와 숏 신호일 때
                for lab, sel in (("상승중_롱", sgn[m] > 0),
                                 ("하락중_숏", sgn[m] < 0)):
                    if sel.sum() < 20:
                        continue
                    k = (h, W, D, f, lab)
                    a = acc.setdefault(k, {"r": [], "hr": []})
                    a["r"].append(np.sign(sgn[m][sel]) * v[m][sel])
                    a["hr"].append(hr[sel])
    out = {}
    for k, v in acc.items():
        r = np.concatenate(v["r"]); hr = np.concatenate(v["hr"])
        if len(r) < 50:
            continue
        u, inv = np.unique(hr, return_inverse=True)
        cm = (np.bincount(inv, weights=r, minlength=len(u))
              / np.maximum(np.bincount(inv, minlength=len(u)), 1))
        t = (cm.mean() / (cm.std(ddof=1) / np.sqrt(len(cm)))
             if len(cm) > 3 and cm.std(ddof=1) > 0 else 0.0)
        out[k] = {"n": int(len(r)), "mean": float(r.mean()),
                  "net": float(r.mean() - cfg.fee_pct),
                  "total": float((r.mean() - cfg.fee_pct) * len(r)),
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
            log.warning("%s 실패: %s", s, str(e)[:90]); x = None
        if x:
            S.append(x)
        if i % 100 == 0 or i == len(syms):
            log.info("[%d/%d] %.1f분", i, len(syms), (time.time()-t0)/60)
    log.info("종목 %d · %.1f분", len(S), (time.time()-t0)/60)

    obs = scan(S, cfg)
    R = pd.DataFrame([{"win_h": k[0], "window": k[1], "delta": k[2],
                       "fwd": k[3], "arm": k[4], **v} for k, v in obs.items()])
    LEN = np.array([x["n"] for x in S])
    rng = np.random.default_rng(cfg.seed)
    acc: dict = {}
    for r in range(cfg.reps):
        for k, v in scan(S, cfg, rng.integers(1, LEN)).items():
            acc.setdefault(k, []).append(v)
        if (r + 1) % 25 == 0:
            log.info("위약 %d/%d · %.1f분", r+1, cfg.reps, (time.time()-t0)/60)
    rows = []
    for _, x in R.iterrows():
        k = (x.win_h, x.window, x.delta, x.fwd, x.arm)
        pl = acc.get(k, [])
        if not pl:
            continue
        pm = np.array([q["mean"] for q in pl])
        pw = np.array([q["win"] for q in pl])
        rows.append({**x.to_dict(), "pl_mean": float(pm.mean()),
                     "excess": float(x["mean"] - pm.mean()),
                     "net_excess": float(x["mean"] - pm.mean() - cfg.fee_pct),
                     "pl_win": float(pw.mean()),
                     "win_ex": float(x["win"] - pw.mean()),
                     "pct": float(100 * (pm < x["mean"]).mean())})
    D = pd.DataFrame(rows).sort_values("t", key=abs, ascending=False)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_placebo_trend.csv"
    D.to_csv(path, index=False)
    log.info("저장 %s — %d칸 · %.1f분", path, len(D), (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
