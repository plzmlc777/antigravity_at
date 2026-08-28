"""급등·급락 되돌림 — **원형 회전** 최대통계량 위약.

## 왜 (2026-08-28)

절대 문턱 사건 연구에서 한 칸이 두드러졌다 — 창 30분 · 문턱 1% · 급락 롱 ·
60분 보유: 4,758사건 · 표류 제거 후 +0.181%p · 수수료 후 +0.145%p · t +4.01.

그런데 격자가 **320칸**이다(창4 × 문턱4 × 시장대비2 × 사건2 × 지평5). 이 크기
에서 t 4 는 우연히 나온다. 칸별 위약은 이미 선택된 칸이라 통과한다(교훈#95).

## 귀무를 어떻게 만드나 — 원형 회전

종목마다 사건 위치를 **통째로 k분 밀어** 시계열 끝에서 앞으로 감는다.

    사건 수      그대로
    사건 간격    그대로 (뭉침 구조 보존)
    가격 움직임과의 연결   **끊어진다**

즉 "같은 수의 사건이 아무 때나 났다면" 이다. 무작위 앵커보다 강한 귀무다 —
사건이 시간에 뭉치는 성질까지 흉내 내기 때문이다.

⚠ 위약도 **같은 320칸을 전부 다시** 훑어 그 최댓값을 쓴다.
⚠ t 는 **시각 클러스터** 기준. 사건은 한 시각에 여러 종목이 동시에 걸린다.
⚠ 표류는 관측·위약 **양쪽에서 똑같이** 뺀다.

사용:
  python3 -m scripts.research.tick_shock_placebo --reps 200
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
log = logging.getLogger("shock_pl")

WINS = (1, 5, 15, 30)
THRS = (1.0, 2.0, 3.0, 5.0)
HORIZONS = (5, 15, 30, 60, 120)


@dataclass(frozen=True)
class Cfg:
    cooldown: int = 30
    min_events: int = 100      # 이보다 적은 칸은 안 센다
    min_hours: int = 8         # 클러스터가 이보다 적으면 t 를 못 믿는다
    min_ticks: int = 2_000
    fee_pct: float = 0.036
    reps: int = 200
    seed: int = 20260828


def _cluster_t(vals: np.ndarray, hours: np.ndarray, cfg: Cfg) -> float:
    """시각 클러스터 평균들의 t. 같은 시각 여러 종목은 한 관측으로 접는다."""
    if len(vals) < cfg.min_events:
        return 0.0
    u, inv = np.unique(hours, return_inverse=True)
    if len(u) < cfg.min_hours:
        return 0.0
    s = np.bincount(inv, weights=vals, minlength=len(u))
    c = np.bincount(inv, minlength=len(u))
    m = s / np.maximum(c, 1)
    sd = m.std(ddof=1)
    return float(m.mean() / (sd / np.sqrt(len(m)))) if sd > 0 else 0.0


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
    over = {k: v for k, v in (("reps", a.reps),) if v is not None}
    cfg = Cfg(**over)
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))
    for k, v in over.items():
        assert getattr(cfg, k) == v, f"{k} 가 설정에 도달하지 않았다"

    syms = [s.strip().upper() for s in
            (ROOT / a.universe).read_text().split() if s.strip()]
    if a.smoke:
        syms = syms[:a.smoke]

    t0 = time.time()
    # ── 평평한 판: 모든 종목의 분봉을 이어 붙이고 종목 경계를 따로 둔다
    EPOCH = pd.Timestamp("1970-01-01", tz="UTC")
    RET = {h: [] for h in HORIZONS}
    HOUR, MIN, START, LEN, CL, SYMS = [], [], [], [], [], []
    off = 0
    for s in syms:
        d = TICKS / s
        fs = sorted(d.glob("*.parquet"))
        if not fs:
            continue
        t = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
                       for f in fs], ignore_index=True)
        t = t[(t.price > 0) & (t.qty > 0)]
        if len(t) < cfg.min_ticks:
            continue
        g = t.sort_values("ts_ms").groupby(t.ts_ms // 60_000)
        cl = g.price.last()
        cl.index = pd.to_datetime(cl.index * 60_000, unit="ms", utc=True)
        cl = cl.reindex(pd.date_range(cl.index.min(), cl.index.max(),
                                      freq="1min", tz="UTC")).ffill()
        n = len(cl)
        if n < max(WINS) + max(HORIZONS) + 30:
            continue
        c = cl.to_numpy(float)
        for h in HORIZONS:
            r = np.full(n, np.nan)
            r[:n - h] = (c[h:] / c[:n - h] - 1.0) * 100.0
            RET[h].append(r)
        # ⚠ `idx.astype("int64")` 는 이 pandas 판본에서 tz 있는 인덱스에 대해
        #   **전부 0** 을 준다(2026-08-28 실측). 그러면 시각 클러스터가 1개로
        #   뭉개져 t 가 통째로 0 이 된다 — 조용히 틀린다. 명시적으로 뺀다.
        HOUR.append(((cl.index - EPOCH) // pd.Timedelta(hours=1)).to_numpy())
        MIN.append(((cl.index - EPOCH) // pd.Timedelta(minutes=1)).to_numpy())
        CL.append(c)
        START.append(off); LEN.append(n); SYMS.append(s)
        off += n
    if len(SYMS) < 20:
        raise SystemExit(f"종목 {len(SYMS)}개뿐 — 틱 구간을 확인하라")
    RET = {h: np.concatenate(v) for h, v in RET.items()}
    HOUR = np.concatenate(HOUR); MIN = np.concatenate(MIN)
    START = np.asarray(START); LEN = np.asarray(LEN)
    log.info("판 %s분봉 · 종목 %d · %.1f분", f"{len(HOUR):,}", len(SYMS),
             (time.time() - t0) / 60)

    # 시장 지수(로그 중앙, %) — **분** 해상도.
    # ⚠ 시간 해상도로 만들었더니 30분 이하 창에서 시장 차이가 통째로 0 이 되어
    #   "시장 대비" 조건이 절대 조건과 **완전히 같아졌다**(2026-08-28 실측).
    lg = np.concatenate([np.log(np.maximum(c, 1e-12)) - np.log(max(c[0], 1e-12))
                         for c in CL])
    MKT_m = pd.Series(lg).groupby(MIN).median() * 100.0
    MKT = MKT_m.reindex(MIN).to_numpy()

    # 표류(대조군) — 전 구간 전체 평균. 관측·위약에서 똑같이 뺀다
    CTL = {h: float(np.nanmean(RET[h])) for h in HORIZONS}
    log.info("표류 " + " · ".join(f"{h}분 {CTL[h]:+.4f}%" for h in HORIZONS))

    # ── 사건 위치 — 칸(창·문턱·시장대비·사건종류)마다 (종목idx, 위치)
    events: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}
    for si, (st, n) in enumerate(zip(START, LEN)):
        c = CL[si]; m = MKT[st:st + n]
        for W in WINS:
            past = np.full(n, np.nan)
            past[W:] = (c[W:] / c[:-W] - 1.0) * 100.0
            mw = np.full(n, np.nan)
            mw[W:] = m[W:] - m[:-W]
            for thr, rel in itertools.product(THRS, (False, True)):
                v = (past - mw) if rel else past
                for ev, sign in (("급락", -1), ("급등", 1)):
                    hit = np.where(np.isfinite(v) &
                                   (v * sign >= thr))[0]
                    # 재무장 — 한 번 걸리면 cooldown 분간 같은 종목 재발화 금지
                    keep, last = [], -10 ** 9
                    for i in hit:
                        if i - last >= cfg.cooldown:
                            keep.append(i); last = i
                    if not keep:
                        continue
                    k = (W, thr, rel, ev)
                    a1, a2 = events.setdefault(k, ([], []))
                    a1.append(np.full(len(keep), si)); a2.append(np.asarray(keep))
    events = {k: (np.concatenate(v[0]), np.concatenate(v[1]))
              for k, v in events.items()}
    log.info("사건 집합 %d개 · 총 사건 %s · %.1f분", len(events),
             f"{sum(len(v[1]) for v in events.values()):,}",
             (time.time() - t0) / 60)

    def scan(shift: np.ndarray | None) -> tuple[float, list[dict]]:
        """모든 칸을 훑어 (최대 |t|, 칸별 결과). shift 가 있으면 원형 회전."""
        best, rows = 0.0, []
        for (W, thr, rel, ev), (si, pos) in events.items():
            p2 = pos if shift is None else (pos + shift[si]) % LEN[si]
            g = START[si] + p2
            hh = HOUR[g]
            sign = 1.0 if ev == "급락" else -1.0      # 급락=롱, 급등=숏
            for h in HORIZONS:
                r = RET[h][g]
                ok = np.isfinite(r)
                if ok.sum() < cfg.min_events:
                    continue
                val = sign * r[ok] - sign * CTL[h]
                t = _cluster_t(val, hh[ok], cfg)
                best = max(best, abs(t))
                if shift is None:
                    rows.append({"W": W, "thr": thr, "rel": rel, "event": ev,
                                 "horizon": h, "n": int(ok.sum()),
                                 "excess": float(val.mean()),
                                 "net": float(val.mean() - cfg.fee_pct),
                                 "total": float((val.mean() - cfg.fee_pct)
                                                * ok.sum()),
                                 "t": t})
        return best, rows

    obs, rows = scan(None)
    R = pd.DataFrame(rows)
    log.info("관측 — 칸 %d · 최대 |t| %.2f · %.1f분", len(R), obs,
             (time.time() - t0) / 60)

    rng = np.random.default_rng(cfg.seed)
    null = np.empty(cfg.reps)
    for r in range(cfg.reps):
        sh = rng.integers(1, LEN)          # 종목마다 다른 회전량
        null[r] = scan(sh)[0]
        if (r + 1) % 25 == 0:
            log.info("위약 %d/%d · %.1f분", r + 1, cfg.reps,
                     (time.time() - t0) / 60)
    p_max = float((null >= obs).mean())

    R["abs_t"] = R.t.abs()
    R = R.sort_values("abs_t", ascending=False)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_shock_placebo.csv"
    R.to_csv(path, index=False)
    path.with_suffix(".null.json").write_text(json.dumps(
        {"obs": obs, "p_max": p_max, "reps": cfg.reps,
         "null_median": float(np.median(null)),
         "null_p95": float(np.quantile(null, 0.95)),
         "null_max": float(null.max()),
         "null": [round(float(x), 4) for x in null],
         "cfg": asdict(cfg)}, ensure_ascii=False, indent=1))

    print(f"\n■ 원형 회전 최대통계량 위약 ({cfg.reps}회 · {len(R)}칸 재탐색)")
    print(f"  관측 최대 |t| {obs:.2f} · 위약 중앙 {np.median(null):.2f} "
          f"· 95분위 {np.quantile(null,0.95):.2f} · 최대 {null.max():.2f}")
    print(f"  **p = {p_max:.3f}**")
    p95 = float(np.quantile(null, 0.95))
    s = R[R.abs_t >= p95]
    print(f"\n■ 위약 95분위({p95:.2f}) 를 넘은 칸: {len(s)} / {len(R)}")
    if len(s):
        print(s.head(15)[["W", "thr", "rel", "event", "horizon", "n",
                          "excess", "net", "total", "t"]].to_string(
              index=False, float_format=lambda x: f"{x:.3f}"))
    print(f"\n  저장 {path} · 총 {(time.time()-t0)/60:.1f}분")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
