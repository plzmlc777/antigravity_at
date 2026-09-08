"""**통합 익절** — 세 다리 손익을 합쳐 문턱에 닿으면 책 전체를 걷는다.

## 왜 개별 익절과 다른가 (2026-09-08 대표님 제안)

개별 익절은 승자를 문턱에서 자르고 패자는 만기까지 끌고 간다 — 어제 기각된
그 형태다(핸드오버 §16). 통합 익절은 **승자를 살려두고 책이 목표에 닿으면
패자까지 같이 걷는다.** 논리적으로 다른 물건이라 기각 결과를 옮길 수 없다.

⚠ 다만 세 다리가 전부 "저(低) 탄성 종목 숏"이라 서로 양의 상관일 수 있다.
  상관이 높으면 책이 함께 움직여 사실상 개별 익절처럼 작동한다 — 그래서 잰다.

## 왜 새 하네스인가

`imp_tp_grid` 는 앵커마다 독립이고 보유 구간의 **고·저만** 남긴다. 통합 익절은
"세 다리의 합이 **언제** 문턱을 넘는가"를 알아야 하므로 **동시 경로**가 필요하다.

## 규약 (앞 하네스와 맞춘다)

  · 기질 `runs/bars5m_ext` 5분봉(고·저·종가) — imp_tp_grid 와 같은 것
  · 신호 `imp_sig` 를 **그대로 가져다 쓴다**. 다시 구현하지 않는다
  · 격자 5분 · 슬롯 3 · 전량 숏 · 보유 480분 · 손절 5% · 마찰 왕복 0.072%
  · 손절은 5분봉 **고가**로 판정(숏). 익절 합은 5분봉 **종가**로 판정한다 —
    엔진이 사이클마다 평가하므로 그 결이 맞다
  · 같은 5분봉에서 손절과 통합익절이 겹치면 **손절 우선**(보수적, 동결 규약)

## 문턱의 단위 — 둘 다 잰다

  A(sum)  r1+r2+r3 ≥ X%      → 자본 기준 X/3 %
  B(cap)  (r1+r2+r3)/3 ≥ X%  → 자본 기준 X%

사용:
  python3 -m scripts.research.imp_book_tp --smoke 30 --tps 0,5,10,20
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

from scripts.research.imp_tp_grid import Cfg as GridCfg
from scripts.research.imp_tp_grid import imp_sig

log = logging.getLogger("bookTP")
ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Run:
    """설정 전문. 하네스 규칙 — 즉석 하드코딩 금지."""
    bars: str = "runs/bars5m_ext"
    since: str = "2024-01-01"
    bar_min: int = 5
    hold_min: int = 480
    slots: int = 3
    stop_pct: float = 5.0
    fee_rt: float = 0.072
    min_dv_usd: float = 50_000.0
    unit: str = "sum"          # sum | cap
    n_side_min: int = 6        # 앵커에 후보가 이만큼은 있어야 뽑는다
    mirror: bool = False       # 방향 반전 대조군 — imp **최고** 3종목

    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def load(r: Run, smoke: int = 0):
    """(격자, 종가, 고가, imp, 유동성통과) 를 5분 격자에 맞춰 돌려준다."""
    g = GridCfg(bars=r.bars, bar_min=r.bar_min)
    fs = sorted((ROOT / r.bars).glob("*.parquet"))
    if smoke:
        fs = fs[:smoke]
    since = pd.Timestamp(r.since, tz="UTC")
    cols, names, t0 = [], [], time.time()
    for i, f in enumerate(fs, 1):
        d = pd.read_parquet(f, columns=["ts", "h", "c", "v"])
        d = d.sort_values("ts")
        d = d[pd.DatetimeIndex(d.ts) >= since]
        if len(d) < g.warm + 200:
            continue
        c = d.c.to_numpy(np.float64)
        qv = d.v.to_numpy(np.float64) * c
        imp = imp_sig(c, qv, g)
        dvm = pd.Series(qv).rolling(288, min_periods=96).median().shift(1).to_numpy()
        cols.append(pd.DataFrame(
            {"c": c.astype(np.float32), "h": d.h.to_numpy(np.float32),
             "imp": imp.astype(np.float32),
             "ok": (dvm >= r.min_dv_usd).astype(bool)},
            index=pd.DatetimeIndex(d.ts)))
        names.append(f.stem)
        if i % 100 == 0:
            log.info("  [%d/%d] %.1f분", i, len(fs), (time.time() - t0) / 60)
    if not names:
        raise SystemExit("읽힌 종목이 0 — 경로·기간을 확인하라")
    lo = min(x.index.min() for x in cols)
    hi = max(x.index.max() for x in cols)
    grid = pd.date_range(lo, hi, freq=f"{r.bar_min}min", tz="UTC")
    n, m = len(grid), len(names)
    C = np.full((n, m), np.nan, np.float32)
    H = np.full((n, m), np.nan, np.float32)
    I = np.full((n, m), np.nan, np.float32)
    OK = np.zeros((n, m), bool)
    for j, x in enumerate(cols):
        y = x.reindex(grid)
        C[:, j] = y["c"].to_numpy(np.float32)
        H[:, j] = y["h"].to_numpy(np.float32)
        I[:, j] = y["imp"].to_numpy(np.float32)
        OK[:, j] = y["ok"].fillna(False).to_numpy(bool)
    log.info("종목 %d · 격자 %s (%s ~ %s) · 배열 %.0f MB",
             m, f"{n:,}", grid[0].date(), grid[-1].date(),
             (C.nbytes + H.nbytes + I.nbytes + OK.nbytes) / 1e6)
    return grid, C, H, I, OK, names


def simulate(grid, C, H, I, OK, r: Run, tp: float):
    """5분 격자 장부. (거래목록, 통합익절 발동 횟수) 를 돌려준다.

    거래 = (순수익%, 사유) · 사유 ∈ {stop, tp, exp}
    """
    n, m = C.shape
    hb = r.hold_min // r.bar_min
    book: dict[int, tuple[int, float]] = {}      # 종목 → (진입스텝, 진입가)
    trades, n_tp = [], 0
    for t in range(n - 1):
        px = C[t]
        # ── 개별 손절 (숏: 고가가 +5% 를 스치면)
        for j in list(book):
            t0, p0 = book[j]
            if r.stop_pct > 0 and np.isfinite(H[t, j]) and \
                    H[t, j] >= p0 * (1 + r.stop_pct / 100):
                trades.append((-r.stop_pct - r.fee_rt, "stop"))
                del book[j]
        # ── 통합 익절 — 열린 다리 수익률의 **합**(또는 평균)
        if tp > 0 and book:
            rs = [100.0 * (p0 - px[j]) / p0 for j, (t0, p0) in book.items()
                  if np.isfinite(px[j])]
            if len(rs) == len(book) and rs:
                v = sum(rs) if r.unit == "sum" else sum(rs) / r.slots
                if v >= tp:
                    for ret in rs:
                        trades.append((ret - r.fee_rt, "tp"))
                    book.clear()
                    n_tp += 1
        # ── 만기
        for j in list(book):
            t0, p0 = book[j]
            if t - t0 >= hb:
                if not np.isfinite(px[j]):
                    continue                      # 시세 없으면 다음 격자
                trades.append((100.0 * (p0 - px[j]) / p0 - r.fee_rt, "exp"))
                del book[j]
        # ── 빈 슬롯 채움 — imp 최저 3(거울이면 최고 3)
        free = r.slots - len(book)
        if free <= 0:
            continue
        v = I[t].copy()
        bad = ~(OK[t] & np.isfinite(v) & np.isfinite(px))
        for j in book:
            bad[j] = True
        v[bad] = np.inf if not r.mirror else -np.inf
        if r.mirror:
            order = np.argsort(-v)
        else:
            order = np.argsort(v)
        for j in order[:free]:
            if bad[j]:
                break
            book[int(j)] = (t, float(px[j]))
    return trades, n_tp


def anchor_sweep(grid, C, H, I, OK, r: Run, lookahead: bool):
    """슬롯 없이 **앵커 단위**로 뽑는다 — `imp_tp_grid` 재현용.

    lookahead=True  : 하루치 앵커를 **전부 모은 뒤** imp 최저 3행을 고른다.
                      `imp_tp_grid.cell()` 이 하는 그대로다. 01시에는 그날
                      최저가 14시에 나올 것을 알 수 없으므로 **선택에 미래가
                      들어간다.**
    lookahead=False : 매 정시 앵커에서 **그 시각 후보 중** imp 최저 3을 고르고,
                      그날의 모든 앵커 픽을 평균한다. 인과적이다.

    돌려주는 것은 일별 수익률 — `imp_tp_grid` 의 `일평균%` 와 같은 눈금이다.
    """
    n, m = C.shape
    hb = r.hold_min // r.bar_min
    step = 60 // r.bar_min                     # 정시 앵커 간격
    st = r.stop_pct / 100.0
    days_idx = pd.DatetimeIndex(grid).normalize()
    pool: dict = {}                            # 날 → [(imp, net%)]  (lookahead)
    percyc: dict = {}                          # 날 → [net%]         (causal)
    for t in range(0, n - hb - 1, step):
        px, v = C[t], I[t]
        good = OK[t] & np.isfinite(v) & np.isfinite(px) & np.isfinite(C[t + hb])
        if good.sum() < r.n_side_min:
            continue
        hmax = np.nanmax(H[t + 1:t + hb + 1], axis=0)
        hit = hmax >= px * (1 + st)
        ret = np.where(hit, -st, (px - C[t + hb]) / px) * 100.0 - r.fee_rt
        d = days_idx[t]
        idx = np.flatnonzero(good)
        # ── 인과: 이 앵커에서 imp 최저 3
        sel = idx[np.argsort(v[idx])[:r.slots]]
        percyc.setdefault(d, []).extend(float(ret[j]) for j in sel)
        # ── 미래참조: 나중에 하루 전체에서 고르려고 전부 모아둔다
        pool.setdefault(d, []).extend((float(v[j]), float(ret[j])) for j in idx)
    out = []
    for d in sorted(pool):
        if lookahead:
            rows = sorted(pool[d], key=lambda x: x[0])[:r.slots]
            if len(rows) < r.slots:
                continue
            out.append(float(np.mean([x[1] for x in rows])))
        else:
            v = percyc.get(d) or []
            if len(v) < r.slots:
                continue
            out.append(float(np.mean(v)))
    return np.asarray(out)


def report(tag: str, trades, n_tp: int, r: Run, days: float) -> dict:
    if not trades:
        return {"tag": tag, "n": 0}
    net = np.array([x[0] for x in trades])
    why = [x[1] for x in trades]
    e = np.cumprod(1 + net / r.slots / 100)
    mdd = 100 * (1 - (e / np.maximum.accumulate(e)).min())
    return {"tag": tag, "n": len(net), "mean": float(net.mean()),
            "t": float(net.mean() / (net.std(ddof=1) / np.sqrt(len(net)))),
            "win": float(100 * (net > 0).mean()),
            "stop": why.count("stop"), "tp": why.count("tp"), "ntp": n_tp,
            "compound": float(100 * (e[-1] - 1)),
            "daily": float(net.sum() / r.slots / max(days, 1e-9)), "mdd": mdd}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tps", default="0,5,10,15,20,30")
    p.add_argument("--unit", default="sum", choices=["sum", "cap"])
    p.add_argument("--since", default="2024-01-01")
    p.add_argument("--hold-min", type=int, default=480)
    p.add_argument("--slots", type=int, default=3)
    p.add_argument("--stop-pct", type=float, default=5.0)
    p.add_argument("--mirror", action="store_true",
                   help="방향 반전 대조군을 같이 낸다(교훈#91)")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--diag", action="store_true",
                   help="기준선 진단 — 장부 / 인과앵커 / 미래참조앵커 셋을 "
                        "나란히 낸다. imp_tp_grid 의 +0.517%%/일 이 어디서 "
                        "오는지 가린다")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    r = Run(since=a.since, hold_min=a.hold_min, slots=a.slots,
            stop_pct=a.stop_pct, unit=a.unit)
    tps = [float(x) for x in a.tps.split(",")]
    log.info("인자 도달 — 익절 %s (%s 단위) · 보유 %d분 · 슬롯 %d · 손절 %.1f%% · 거울 %s",
             tps, a.unit, r.hold_min, r.slots, r.stop_pct, a.mirror)
    log.info("설정 전문 %s", r.dump())

    t0 = time.time()
    grid, C, H, I, OK, names = load(r, a.smoke)
    days = (grid[-1] - grid[0]).total_seconds() / 86400
    log.info("적재 완료 %.1f분 · %.0f일", (time.time() - t0) / 60, days)

    if a.diag:
        base = Run(since=a.since, hold_min=a.hold_min, slots=a.slots,
                   stop_pct=a.stop_pct)
        tr, _ = simulate(grid, C, H, I, OK, base, 0.0)
        net = np.array([x[0] for x in tr])
        bk = net.sum() / base.slots / days
        la = anchor_sweep(grid, C, H, I, OK, base, lookahead=True)
        ca = anchor_sweep(grid, C, H, I, OK, base, lookahead=False)
        f = lambda x: (x.mean(), x.mean() / (x.std(ddof=1) / np.sqrt(len(x))), len(x))
        print(f"\n■ 기준선 진단 (익절 없음 · 종목 {len(names)} · {days:.0f}일)")
        print(f"  {'방식':>22}{'일평균%':>10}{'t':>8}{'날':>7}")
        print(f"  {'① 장부(슬롯 3·실거래와 같음)':>22}{bk:>+10.4f}{'—':>8}{days:>7.0f}")
        m, t_, k = f(ca)
        print(f"  {'② 인과 앵커(슬롯 없음)':>22}{m:>+10.4f}{t_:>+8.2f}{k:>7}")
        m, t_, k = f(la)
        print(f"  {'③ 미래참조 앵커(imp_tp_grid)':>22}{m:>+10.4f}{t_:>+8.2f}{k:>7}")
        print("\n  ③ 은 하루치 앵커를 **전부 모은 뒤** imp 최저 3을 고른다 —")
        print("     01시에는 그날 최저가 14시에 나올 것을 알 수 없다. 선택에 미래가 들어간다.")
        print("     ③ 이 크고 ②·① 이 작으면, 교체 근거는 그 미래참조가 만든 것이다.")
        log.info("완료 %.1f분", (time.time() - t0) / 60)
        return 0

    rows = []
    for tp in tps:
        for mir in ((False, True) if a.mirror else (False,)):
            rr = Run(since=a.since, hold_min=a.hold_min, slots=a.slots,
                     stop_pct=a.stop_pct, unit=a.unit, mirror=mir)
            tr, ntp = simulate(grid, C, H, I, OK, rr, tp)
            lab = ("익절 없음" if tp <= 0 else f"통합 {tp:.0f}%") + (" · 거울" if mir else "")
            rows.append(report(lab, tr, ntp, rr, days))
            log.info("%s — 거래 %d · %.1f분", lab, len(tr), (time.time() - t0) / 60)

    print(f"\n■ 통합 익절 ({a.unit} 단위) — 종목 {len(names)} · "
          f"{grid[0].date()}~{grid[-1].date()} ({days:.0f}일) · "
          f"슬롯 {r.slots} · 보유 {r.hold_min}분 · 손절 {r.stop_pct:.0f}%")
    print(f"  {'설정':>14}{'거래':>8}{'거래당%':>10}{'t':>7}{'승률':>7}"
          f"{'손절':>7}{'익절':>7}{'발동':>6}{'일평균%':>9}{'복리%':>11}{'낙폭%':>9}")
    for x in rows:
        if not x["n"]:
            continue
        print(f"  {x['tag']:>14}{x['n']:>8,}{x['mean']:>+10.4f}{x['t']:>+7.2f}"
              f"{x['win']:>6.0f}%{x['stop']:>7,}{x['tp']:>7,}{x['ntp']:>6,}"
              f"{x['daily']:>+9.4f}{x['compound']:>+11.2f}{x['mdd']:>9.2f}")
    print("\n  ※ '발동' 은 통합 익절이 책을 걷은 횟수. '익절' 은 그때 닫힌 다리 수.")
    print("     거울은 imp **최고** 3종목을 숏 친 대조군이다 — 양쪽에서 같은 방향으로")
    print("     움직이면 엣지가 아니라 규칙 효과다(교훈#91).")
    log.info("완료 %.1f분", (time.time() - t0) / 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
