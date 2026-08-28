"""동결 규칙을 **슬롯 1**로 실현하면 얼마인가 — 페이퍼 배포 전 관문.

## 왜 이걸 먼저 (2026-08-28)

동결 문서의 실측치는 **모든 사건의 평균**이다(z_vel ≤ −1 구간 5,123건).
그런데 슬롯 1 · 보유 120분이면 하루에 최대 **12건**만 잡는다. 하루 2,800건
후보 중 12건을 고르는 것이고, **고르는 방법이 결과를 바꾼다**.

이 트랙에서 반복해 데인 자리다 — 평균이 좋아도 골라낸 소수가 다를 수 있고,
반대로 평균이 나빠도 골라낸 쪽이 좋을 수 있다.

## 무엇을 비교하나

    가장 극단     후보 중 z_vel 최소 (동결 문서의 기본안)
    가장 덜 극단  후보 중 z_vel 최대 (문턱은 넘되 가장 약한 것)
    무작위        후보 중 아무거나 — **선별이 의미 있나**를 가른다
    항상롱        후보를 안 보고 아무 종목이나 — 표류 기준선

⚠ 판정은 **총손익**이다. 거래당 엣지만 보면 빈도가 빠진다(대표님 지시).
⚠ 무작위 선별은 seed 를 바꿔 여러 번 돌려 분포로 본다.

사용:
  python3 -m scripts.research.tick_kinematics_slot1 --smoke 60
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
log = logging.getLogger("slot1")

# ── 신호 파라미터는 동결분 그대로. **진입 조건만** 고친다.
#   구 조건 `z_vel ≤ -1.0` 은 상한이 없어 슬롯 1 이 매번 꼬리 밖을 골랐다.
#   촘촘한 구간 실측(2026-08-28): -2~-1.75 구간은 1.91일에 **95건**뿐이라
#   회전 위약을 못 넘는다(z +0.89). 재본 적 없는 영역이었다.
WIN_H, WINDOW, DELTA = 60, 360, 180
STEP = 5
MIN_LIVE_TR = 5.0


@dataclass(frozen=True)
class Cfg:
    z_lo: float = -1.25      # 진입 밴드 하한 (이보다 낮으면 표본이 없다)
    z_hi: float = -0.25      # 진입 밴드 상한
    acc_max: float = 0.5     # z_acc 가 이보다 크면 배제 — 급등 신호 회피
    hold: int = 120
    slots: int = 1
    fee_pct: float = 0.036
    min_ticks: int = 2_000
    n_rand: int = 60
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
    if len(b) < WIN_H + WINDOW + 2 * DELTA + 120 + 30:
        return None
    cl = b.cl.to_numpy(float); n = len(cl)
    fw = np.full(n, np.nan)
    fw[:n - WIN_H] = cl[WIN_H:] / cl[:n - WIN_H] - 1.0
    win = pd.Series(np.where(np.isfinite(fw), (fw > 0).astype(float), np.nan))
    rate = win.rolling(WINDOW, min_periods=WINDOW // 2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    acc = vel - vel.shift(DELTA)
    neff = max(WINDOW / WIN_H, 1.0)
    p = rate.clip(0.01, 0.99)
    se = np.sqrt(p * (1 - p) / neff)
    out = {"ts": b.index, "symbol": sym,
           "z_vel": (vel / (se * np.sqrt(2))).to_numpy(),
           "z_acc": (acc / (se * 2.0)).to_numpy(),
           "live": (b.ntr.rolling(60).median().shift(1) >= MIN_LIVE_TR).to_numpy()}
    for h in (30, 60, 120):
        r = np.full(n, np.nan)
        r[:n - h] = (cl[h:] / cl[:n - h] - 1.0) * 100.0
        out[f"ret_{h}"] = r
    return pd.DataFrame(out)


def simulate(P: pd.DataFrame, rule: str, cfg: Cfg, rng=None) -> dict:
    """5분 격자를 훑으며 **빈 슬롯을 채운다**.

    ⚠ 자본을 슬롯 수로 나눈다. 슬롯>1 인데 포지션마다 전액을 복리로 굴리면
      없는 돈을 굴리는 것이다 — 이 트랙에서 한 번 그렇게 틀렸다.
      진입 시 stake = equity/slots, 청산 시 equity += stake × 순수익.
    ⚠ 같은 종목을 동시에 두 슬롯에 담지 않는다.
    """
    rc = f"ret_{cfg.hold}"
    held: dict = {}                       # symbol -> (청산시각, stake, 순수익%)
    trades, equity = [], 1.0
    for ts, g in P.groupby("ts", sort=True):
        # ── 만기 도래분 청산
        for sym in [k for k, v in held.items() if v[0] <= ts]:
            _, stake, net = held.pop(sym)
            equity += stake * net / 100.0
        free = cfg.slots - len(held)
        if free <= 0:
            continue
        ok = g.live & g[rc].notna()
        if rule == "항상롱":
            c = g[ok]
        elif rule == "구_하한만":
            c = g[ok & (g.z_vel <= cfg.z_hi)]
        else:
            c = g[ok & (g.z_vel >= cfg.z_lo) & (g.z_vel <= cfg.z_hi)
                  & (g.z_acc < cfg.acc_max)]
        c = c[~c.symbol.isin(held)]
        if c.empty:
            continue
        if rule in ("밴드_최저", "구_하한만"):
            c = c.nsmallest(free, "z_vel")
        elif rule == "밴드_최고":
            c = c.nlargest(free, "z_vel")
        elif rule == "밴드_중앙":
            mid = (cfg.z_lo + cfg.z_hi) / 2
            c = c.assign(_d=(c.z_vel - mid).abs()).nsmallest(free, "_d")
        else:
            c = c.sample(n=min(free, len(c)), random_state=int(
                rng.integers(1 << 31)))
        stake = equity / cfg.slots
        for _, r in c.iterrows():
            net = float(r[rc]) - cfg.fee_pct
            held[r.symbol] = (ts + pd.Timedelta(minutes=cfg.hold), stake, net)
            trades.append({"ts": ts, "symbol": r.symbol,
                           "z_vel": float(r.z_vel), "net": net})
    for sym, (_, stake, net) in held.items():          # 남은 포지션 정산
        equity += stake * net / 100.0
    if not trades:
        return {"n": 0}
    T = pd.DataFrame(trades)
    return {"n": len(T), "net_mean": float(T.net.mean()),
            "total": float(T.net.sum()),
            "compound": float((equity - 1.0) * 100.0),
            "win": float(100.0 * (T.net > 0).mean()),
            "z_mean": float(T.z_vel.mean()),
            "best": float(T.net.max()), "worst": float(T.net.min()),
            "util": float(100.0 * len(T) * cfg.hold
                          / (cfg.slots * P.ts.nunique() * STEP))}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--hold", type=int, default=None)
    p.add_argument("--slots", type=int, default=None)
    p.add_argument("--z-lo", type=float, default=None)
    p.add_argument("--z-hi", type=float, default=None)
    p.add_argument("--acc-max", type=float, default=None)
    p.add_argument("--out", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    over = {k: v for k, v in (("hold", a.hold), ("slots", a.slots),
                              ("z_lo", a.z_lo),
                              ("z_hi", a.z_hi), ("acc_max", a.acc_max))
            if v is not None}
    cfg = Cfg(**over)
    for k, v in over.items():
        assert getattr(cfg, k) == v, f"{k} 가 설정에 도달하지 않았다"
    log.info("규칙 — 지평%d 창%d 간격%d · 밴드 %.2f≤z_vel≤%.2f · z_acc<%.1f "
             "· 보유%d분 · 슬롯%d", WIN_H, WINDOW, DELTA, cfg.z_lo, cfg.z_hi,
             cfg.acc_max, cfg.hold, cfg.slots)

    syms = [s.strip().upper() for s in
            (ROOT / a.universe).read_text().split() if s.strip()]
    if a.smoke:
        syms = syms[:a.smoke]
    t0 = time.time()
    parts = []
    for i, s in enumerate(syms, 1):
        try:
            x = build(s, cfg)
        except Exception as e:                                  # noqa: BLE001
            log.warning("%s 실패: %s", s, str(e)[:90]); x = None
        if x is not None:
            # ⚠ 종목마다 첫 봉 시각이 달라 `x[::STEP]` 는 **정렬 안 된** 격자를
            #   만든다. 그러면 어떤 시각엔 한 종목만 후보라 "최저 z" 선별이
            #   무의미하게 그 종목을 집는다. 벽시계 격자에 맞춘다.
            parts.append(x[x.ts.dt.minute % STEP == 0])
        if i % 100 == 0 or i == len(syms):
            log.info("[%d/%d] %.1f분", i, len(syms), (time.time()-t0)/60)
    P = pd.concat(parts, ignore_index=True)
    days = (P.ts.max() - P.ts.min()).total_seconds() / 86400
    cand = P[P.live & (P.z_vel >= cfg.z_lo) & (P.z_vel <= cfg.z_hi)
             & (P.z_acc < cfg.acc_max)]
    log.info("판 %s행 · 종목 %d · %.2f일 · 후보 %s건(하루 %.0f건)",
             f"{len(P):,}", P.symbol.nunique(), days, f"{len(cand):,}",
             len(cand) / days)

    rng = np.random.default_rng(cfg.seed)
    rows = []
    for rule in ("밴드_최저", "밴드_중앙", "밴드_최고", "구_하한만"):
        r0 = simulate(P, rule, cfg)
        log.info("  %s — n %d · 복리 %+.2f%%", rule, r0.get("n", 0),
                 r0.get("compound", 0.0))
        rows.append({"rule": rule, **r0})
    for rule in ("밴드_무작위", "항상롱"):
        rs = [simulate(P, rule, cfg, rng) for _ in range(cfg.n_rand)]
        rs = [x for x in rs if x.get("n")]
        # ⚠ 집계 키는 simulate() 반환과 **같은 이름**이어야 한다. 다중 슬롯으로
        #   바꾸며 "mean" 을 "net_mean" 으로 갈았는데 여기를 안 고쳐 6개 조합이
        #   전부 마지막 줄에서 죽었다(2026-08-28). 있는 키만 집계한다.
        rows.append({"rule": rule + "(중앙)", "n": int(np.median([x["n"] for x in rs])),
                     "net_mean": float(np.median([x["net_mean"] for x in rs])),
                     "total": float(np.median([x["total"] for x in rs])),
                     "compound": float(np.median([x["compound"] for x in rs])),
                     "win": float(np.median([x["win"] for x in rs])),
                     "z_mean": float(np.median([x["z_mean"] for x in rs])),
                     "best": float(np.median([x["best"] for x in rs])),
                     "worst": float(np.median([x["worst"] for x in rs])),
                     "util": float(np.median([x.get("util", 0) for x in rs]))})
        rows.append({"rule": rule + "(복리 5~95분위)", "n": len(rs),
                     "total": float(np.quantile([x["compound"] for x in rs], .05)),
                     "compound": float(np.quantile([x["compound"] for x in rs], .95))})
    R = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / f"tick_kinematics_slot{cfg.slots}_h{cfg.hold}.csv"
    R.to_csv(path, index=False)
    print(f"\n■ 슬롯 {cfg.slots} · 보유 {cfg.hold}분 · {days:.2f}일 "
          f"· 후보 하루 {len(cand)/days:.0f}건")
    cols = [c for c in ("rule", "n", "net_mean", "total", "compound",
                        "win", "z_mean", "util", "best", "worst")
            if c in R.columns]
    print(R[cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    log.info("저장 %s · %.1f분", path, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
