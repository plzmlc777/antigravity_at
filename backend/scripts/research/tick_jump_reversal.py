"""1분 극단 점프의 되돌림 — 크기·방향·지평·진입시점을 다 가른다.

## 왜 (2026-08-28)

결합 탐지기에서 점프 상위 13건이 **전부** 추세추종으로 졌다(= 되돌림으로는
이겼다). 가장 극단 8건에서 되돌림 방향 60분 평균 **+2.95%**.

그런데 앞선 검정(`tick_shock_rebound`)은 **고정 5% 문턱**에서 반대로
"지속"이라 했다. 두 결과가 충돌하는지, 조건이 다른지부터 갈라야 한다.

    고정 문턱   5% 는 변동성 큰 종목엔 평범, 작은 종목엔 극단
    변동성 정규화  |1분 수익률| / 직전 60분 실현변동성 — 종목 간 비교가 된다

## 🚫 반드시 먼저 죽여야 할 가설 — 호가 튐

1분 극단 움직임은 **단일 체결이 얇은 호가를 뚫은 것**일 수 있다. 그러면
다음 분에 중간값으로 돌아오고, 그건 알파가 아니라 스프레드다. 실측에서
1분 되돌림 1.7bp 가 호가 스프레드(1~5bp)와 같은 자릿수였다.

가르는 방법: **진입을 미룬다**.

    진입 A  점프 분 종가        (튐이 있으면 그걸 먹는다)
    진입 B  다음 분 종가        (튐이 지나간 뒤)
    진입 C  다음 5분 뒤 종가     (더 확실히 지난 뒤)

A 에서만 나오고 B·C 에서 사라지면 **호가 튐**이다. B·C 에서도 남으면 진짜다.

⚠ 방향을 가른다 — 급등 뒤 숏과 급락 뒤 롱은 다른 현상일 수 있다(교훈#91).
⚠ 죽은 종목 배제 — 거래 없다 깨어난 것을 점프로 읽지 않는다.
⚠ 위약은 원형 회전 최대통계량(교훈#95).
⚠ 표본 1.83일. 지형이지 결론이 아니다.

사용:
  python3 -m scripts.research.tick_jump_reversal --smoke 60
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
log = logging.getLogger("jumprev")

BINS = [(5, 10), (10, 15), (15, 20), (20, 30), (30, 50), (50, 1e9)]
HORIZONS = (5, 15, 30, 60, 120)
DELAYS = (0, 1, 5)                 # 진입을 몇 분 미룰까


@dataclass(frozen=True)
class Cfg:
    lookback: int = 60
    cooldown: int = 60
    min_ticks: int = 2_000
    min_live_tr: float = 5.0
    min_qv: float = 5_000.0
    fee_pct: float = 0.036
    reps: int = 300
    seed: int = 20260828


def build(sym: str, cfg: Cfg) -> dict | None:
    d = TICKS / sym
    fs = sorted(d.glob("*.parquet"))
    if not fs:
        return None
    t = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
                   for f in fs], ignore_index=True)
    t = t[(t.price > 0) & (t.qty > 0)]
    if len(t) < cfg.min_ticks:
        return None
    t = t.sort_values("ts_ms")
    t["qv"] = t.price * t.qty
    g = t.groupby(t.ts_ms // 60_000)
    b = pd.DataFrame({"cl": g.price.last(), "hi": g.price.max(),
                      "lo": g.price.min(), "qv": g.qv.sum(),
                      "ntr": g.price.size()})
    b.index = pd.to_datetime(b.index * 60_000, unit="ms", utc=True)
    b = b.reindex(pd.date_range(b.index.min(), b.index.max(), freq="1min",
                                tz="UTC"))
    b[["cl", "hi", "lo"]] = b[["cl", "hi", "lo"]].ffill()
    b[["qv", "ntr"]] = b[["qv", "ntr"]].fillna(0.0)
    L = cfg.lookback
    if len(b) < L + max(HORIZONS) + max(DELAYS) + 30:
        return None
    lr = np.log(b.cl.clip(lower=1e-12)).diff()
    rv = lr.rolling(L).std().shift(1)
    z = (lr / (rv + 1e-12)).to_numpy()
    live = ((b.ntr.rolling(L).median().shift(1) >= cfg.min_live_tr)
            & (b.qv >= cfg.min_qv)).to_numpy()
    return {"sym": sym, "z": z, "live": live,
            "cl": b.cl.to_numpy(float), "hi": b.hi.to_numpy(float),
            "lo": b.lo.to_numpy(float),
            "hour": ((b.index - pd.Timestamp("1970-01-01", tz="UTC"))
                     // pd.Timedelta(hours=1)).to_numpy(),
            "ts": b.index}


def events(S: list[dict], cfg: Cfg, shift: np.ndarray | None = None) -> dict:
    """칸별 결과. shift 가 있으면 점프 위치를 원형 회전한다(위약)."""
    acc: dict = {}
    for si, s in enumerate(S):
        z, live, n = s["z"], s["live"], len(s["cl"])
        cand = np.where(np.isfinite(z) & live)[0]
        if not len(cand):
            continue
        az = np.abs(z[cand])
        for lo_b, hi_b in BINS:
            m = cand[(az >= lo_b) & (az < hi_b)]
            if not len(m):
                continue
            keep, last = [], -10 ** 9
            for i in m:
                if i - last >= cfg.cooldown:
                    keep.append(i); last = i
            if not keep:
                continue
            pos = np.asarray(keep)
            sgn = np.sign(z[pos])                     # 점프 방향
            if shift is not None:
                pos = (pos + shift[si]) % n           # 위약: 위치만 민다
            for delay in DELAYS:
                e = pos + delay
                ok0 = e < n - max(HORIZONS)
                if ok0.sum() == 0:
                    continue
                e2, sg = e[ok0], sgn[ok0]
                entry = s["cl"][e2]
                for h in HORIZONS:
                    j = e2 + h
                    nxt = s["cl"][j]
                    top = np.array([s["hi"][a + 1:b + 1].max()
                                    for a, b in zip(e2, j)])
                    bot = np.array([s["lo"][a + 1:b + 1].min()
                                    for a, b in zip(e2, j)])
                    r = 100.0 * (nxt / entry - 1.0)
                    # 되돌림 = 점프 **반대** 방향에 건다
                    rev = -sg * r
                    mfe = np.where(-sg > 0, 100.0 * (top / entry - 1.0),
                                   100.0 * (1.0 - bot / entry))
                    for updn in ("급등", "급락", "합계"):
                        sel = (sg > 0) if updn == "급등" else (
                            sg < 0) if updn == "급락" else np.ones(len(sg), bool)
                        if sel.sum() < 3:
                            continue
                        k = (lo_b, hi_b, delay, h, updn)
                        a1 = acc.setdefault(k, {"r": [], "m": [], "hr": []})
                        a1["r"].append(rev[sel]); a1["m"].append(mfe[sel])
                        a1["hr"].append(s["hour"][e2][sel])
    out = {}
    for k, v in acc.items():
        r = np.concatenate(v["r"]); m = np.concatenate(v["m"])
        hr = np.concatenate(v["hr"])
        ok = np.isfinite(r)
        if ok.sum() < 20:
            continue
        r, m, hr = r[ok], m[ok], hr[ok]
        u, inv = np.unique(hr, return_inverse=True)
        cm = np.bincount(inv, weights=r, minlength=len(u)) / np.maximum(
            np.bincount(inv, minlength=len(u)), 1)
        t = (cm.mean() / (cm.std(ddof=1) / np.sqrt(len(cm)))
             if len(cm) > 3 and cm.std(ddof=1) > 0 else 0.0)
        out[k] = {"n": int(len(r)), "mean": float(r.mean()),
                  "med": float(np.median(r)),
                  "net": float(r.mean() - Cfg.fee_pct),
                  "total": float((r.mean() - Cfg.fee_pct) * len(r)),
                  "mfe_med": float(np.median(m)), "t": float(t),
                  "win": float(100.0 * (r > 0).mean())}
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

    obs = events(S, cfg)
    R = pd.DataFrame([{"z_lo": k[0], "z_hi": k[1], "delay": k[2],
                       "horizon": k[3], "side": k[4], **v}
                      for k, v in obs.items()])
    log.info("관측 칸 %d · 최대 |t| %.2f · %.1f분", len(R), R.t.abs().max(),
             (time.time()-t0)/60)

    LEN = np.array([len(x["cl"]) for x in S])
    rng = np.random.default_rng(cfg.seed)
    null = np.empty(cfg.reps)
    for r in range(cfg.reps):
        null[r] = max((abs(v["t"]) for v in
                       events(S, cfg, rng.integers(1, LEN)).values()),
                      default=0.0)
        if (r + 1) % 25 == 0:
            log.info("위약 %d/%d · %.1f분", r+1, cfg.reps, (time.time()-t0)/60)
    obs_max = float(R.t.abs().max())
    p_max = float((null >= obs_max).mean())

    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_jump_reversal.csv"
    R.sort_values("t", key=abs, ascending=False).to_csv(path, index=False)
    path.with_suffix(".null.json").write_text(json.dumps(
        {"obs": obs_max, "p_max": p_max, "reps": cfg.reps,
         "null_median": float(np.median(null)),
         "null_p95": float(np.quantile(null, 0.95)),
         "null_max": float(null.max()),
         "null": [round(float(x), 4) for x in null]},
        ensure_ascii=False, indent=1))
    print(f"\n■ 원형 회전 최대통계량 위약 ({cfg.reps}회 · {len(R)}칸)")
    print(f"  관측 최대 |t| {obs_max:.2f} · 위약 중앙 {np.median(null):.2f} "
          f"· 95분위 {np.quantile(null,0.95):.2f} · 최대 {null.max():.2f}")
    print(f"  **p = {p_max:.3f}**")
    log.info("저장 %s · %.1f분", path, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
