"""방향 축 6년 검정 — "직전 k분 최대 하락 3종목 숏" (2026-09-09).

## 왜 이것만 아카이브로 잴 수 있나

`imp` 는 1분 |수익|과 거래대금이 필요해 5분봉으로 못 만든다(교훈#108).
그런데 **방향 신호는 종가만 필요하다** — "직전 15분 수익"은 5분봉에서 정확히
3봉 수익이다. 그래서 `bars5m_ext`(521종목 · 2020~2026)로 잴 수 있고,
14일이 2,000일이 된다. `imp_direction_grid` 가 검정력 부족(p 0.105)으로
판정 못 한 것을 여기서 판정한다.

## 엔진과 맞춘 것 / 다른 것

    맞춤   슬롯 3 숏 · 보유 480분(96봉) · 손절 5% · 왕복 0.072%
           손절 판정은 **종가** 기준 (엔진 `hi10` 이 종가의 최대다)
    다름   진입가가 5분봉 종가다(엔진은 1분봉 종가)
           유동성 관문이 **거래대금**이다 — `n` 칸은 체결 수가 아니라
           5분봉에 들어간 1분봉 개수(전부 5)라 분산이 0이다(§24)

## 메모리

6년 × 521종목을 통째로 올리면 행렬 하나가 1.3 GB 다. 2026-09-01 에 20 GB 를
요구해 서버가 멈춘 전례가 있으므로 **시간 조각(기본 60일)으로 나눠** 돈다.
조각 경계에서 열려 있던 자리는 버린다 — 8시간 보유라 60일 중 0.5% 수준이다.

## 판정

격자를 뒤지므로 **최대통계량**(교훈#95). 관측 단위는 **날**.
대조군 둘 — 거울(같은 선별을 롱으로 · 교훈#91) · 무작위 3종목 숏.
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
log = logging.getLogger("dirarch")


@dataclass
class Cfg:
    bars: str = "runs/bars5m_ext"
    out: str = "runs/research_track/dir_archive"
    bar_min: int = 5
    slots: int = 3
    hold_min: int = 480
    stop_pct: float = 5.0
    fee_rt: float = 0.072
    ks: tuple = (5, 15, 30, 60)          # 방향 창(분) — 격자
    min_dv_usd: float = 50_000.0         # 직전 24h 5분 거래대금 중앙 하한
    min_cand: int = 30                   # 하루 후보 하한 (교훈#99)
    chunk_days: int = 180   # ⚠ 조각을 키워 파일 재읽기를 줄인다(부하 절감). 60일이면 41회, 180일이면 14회.
    start: str = "2020-01-01"
    n_perm: int = 200
    seed: int = 20260909


def simulate(C, DV, ok0, c: Cfg, k_bars: int, mode: str, rng=None,
             short: bool = True):
    """조각 하나의 (날, 자본수익%) 목록. mode: dir | random."""
    nT, nS = C.shape
    hold = c.hold_min // c.bar_min
    st = c.stop_pct / 100.0
    end = np.full(nS, -1, np.int64)
    epx = np.zeros(nS)
    n_open = 0
    out = []
    for t in range(k_bars + 1, nT):
        for j in np.flatnonzero(end >= 0):
            if end[j] > t:
                continue
            e = epx[j]
            seg = C[max(0, int(end[j]) - hold):int(end[j]) + 1, j]
            adv = (np.nanmax(seg) / e - 1) if short else (1 - np.nanmin(seg) / e)
            if np.isfinite(adv) and adv >= st:
                r = -c.stop_pct
            else:
                x = C[min(int(end[j]), nT - 1), j]
                r = (100.0 * (e - x) / e) if short else (100.0 * (x - e) / e)
            out.append((t, float(r) - c.fee_rt))
            end[j] = -1
            n_open -= 1
        free = c.slots - n_open
        if free <= 0:
            continue
        prev = C[t - k_bars]
        ret = np.where((prev > 0) & np.isfinite(C[t]),
                       100.0 * (C[t] / prev - 1.0), np.nan)
        ok = ok0[t] & np.isfinite(ret) & (end < 0)
        idx = np.flatnonzero(ok)
        if len(idx) < c.min_cand:
            continue
        order = (rng.permutation(idx) if mode == "random"
                 else idx[np.argsort(ret[idx])])
        for j in order[:free]:
            end[j] = t + hold
            epx[j] = C[t, j]
            n_open += 1
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="예비비행 — 1조각")
    ap.add_argument("--start", default="")
    ap.add_argument("--perm", type=int, default=0)
    a = ap.parse_args()
    c = Cfg(n_perm=a.perm, start=a.start or Cfg.start)
    log.info("설정 — 창 %s분 · 슬롯 %d · 보유 %d분 · 손절 %.1f%% · 통행료 %.3f%% "
             "· 거래대금 하한 $%.0f · 조각 %d일 · 시작 %s · 위약 %d",
             c.ks, c.slots, c.hold_min, c.stop_pct, c.fee_rt, c.min_dv_usd,
             c.chunk_days, c.start, c.n_perm)

    base = ROOT / c.bars
    files = sorted(base.glob("*.parquet"))
    log.info("종목 파일 %d개", len(files))
    rng = np.random.default_rng(c.seed)

    # 조각 경계
    t0 = pd.Timestamp(c.start, tz="UTC")
    t1 = pd.Timestamp.utcnow().tz_localize(None).tz_localize("UTC")
    edges = pd.date_range(t0, t1, freq=f"{c.chunk_days}D")
    if a.smoke:
        edges = edges[-3:-1]
    log.info("조각 %d개", max(len(edges) - 1, 1))

    cells = [(f"dir k={k}", k // c.bar_min, "dir", True) for k in c.ks]
    cells += [(f"거울 k={k}", k // c.bar_min, "dir", False) for k in c.ks]
    cells += [("무작위 숏", 1, "random", True)]
    acc = {name: {} for name, *_ in cells}

    tstart = time.time()
    for ci in range(len(edges) - 1):
        s0, s1 = edges[ci], edges[ci + 1]
        cols, names = [], []
        for f in files:
            try:
                d = pd.read_parquet(f, columns=["ts", "c", "v"])
            except Exception:                                   # noqa: BLE001
                continue
            d = d[(d.ts >= s0 - pd.Timedelta(days=2)) & (d.ts < s1)]
            if len(d) < 500:
                continue
            cols.append(d.set_index("ts")[["c", "v"]])
            names.append(f.stem)
        if len(cols) < c.min_cand:
            continue
        grid = pd.date_range(min(x.index[0] for x in cols),
                             max(x.index[-1] for x in cols),
                             freq=f"{c.bar_min}min")
        C = np.full((len(grid), len(cols)), np.nan, np.float32)
        V = np.zeros((len(grid), len(cols)), np.float32)
        gi = {t: i for i, t in enumerate(grid)}
        for j, x in enumerate(cols):
            ix = np.array([gi[t] for t in x.index if t in gi], int)
            xs = x[x.index.isin(gi)]
            C[ix, j] = xs.c.to_numpy(np.float32)
            V[ix, j] = xs.v.to_numpy(np.float32)
            C[:, j] = pd.Series(C[:, j]).ffill().to_numpy(np.float32)
        DV = pd.DataFrame(V).rolling(288, min_periods=96).median().shift(1).to_numpy(np.float32)
        ok0 = np.isfinite(C) & (DV >= c.min_dv_usd)
        day = pd.Series(grid).dt.tz_convert("Asia/Seoul").dt.date.to_numpy()
        for name, kb, mode, sh in cells:
            for t, r in simulate(C, DV, ok0, c, kb, mode, rng, sh):
                acc[name].setdefault(day[t], []).append(r)
        el = time.time() - tstart
        log.info("  조각 %d/%d (%s) · 종목 %d · %.1f분 · 남은 %.1f분",
                 ci + 1, len(edges) - 1, f"{s0:%Y-%m}", len(cols), el / 60,
                 el / 60 * (len(edges) - 1 - ci - 1) / (ci + 1))

    rows = []
    for name in acc:
        days = sorted(acc[name])
        if len(days) < 30:
            continue
        r = np.array([np.sum(acc[name][d]) / c.slots for d in days])
        t = (r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))) if r.std(ddof=1) else np.nan
        rows.append({"갈래": name, "날": len(r), "일평균%": r.mean(),
                     "합%": r.sum(), "t": t, "양수일%": 100 * (r > 0).mean()})
    obs = pd.DataFrame(rows).sort_values("t", ascending=False)
    d = ROOT / c.out
    d.mkdir(parents=True, exist_ok=True)
    obs.to_csv(d / "observed.csv", index=False)
    (d / "config.json").write_text(json.dumps(asdict(c), ensure_ascii=False,
                                              indent=1, default=list))
    print(f"\n■ 방향 축 아카이브 — {c.start}~ · {len(obs)}칸")
    print(obs.round(4).to_string(index=False))
    print(f"\n⚠ 거울과 짝지어 보라. 숏+롱 합이 {-2*c.fee_rt:.3f} 근처면 정보 없음(교훈#91).")


if __name__ == "__main__":
    main()
