"""소수 급등·급락 종목을 **미리 알 수 있는가** — 꼬리 사건 예측 가능성.

왜 이 질문인가
    동일가중 알트 바스켓은 5.4년 누적 -8% 인데 상하위 5% 를 절사하면 **-100%**
    다. 즉 **바스켓의 운명 전부가 소수 극단 종목에 달려 있다.** 그것들을 미리
    가릴 수 있으면 알트 숏은 전혀 다른 물건이 된다.

⚠ "어느 종목이 오를까"는 이미 닫혔다
    [[project-short-selection-closed-2026-08-15]] — 종목 선별(IS→OOS rho
    **-0.058** p 0.574) · 성질 선별(6종 전부 IS 비단조 or OOS 부호반전) ·
    횡단면 모멘텀(HAC 후 OOS -1.999%) · SMB(뒤섞기 p 0.150).
    **그래서 이 스크립트는 수익률 평균을 예측하지 않는다.** 묻는 건 다르다:

        ① 크게 움직일 것인가 (**크기**)     — 쉽다. 문제는 기준선이다.
        ② 그 극단이 위인가 아래인가 (**방향**) — 이게 미해결이고 이게 돈이다.

⚠ 크기 예측은 과거 변동성을 이겨야 한다 (교훈 #94)
    미래 변동성은 **뭐든** 맞힌다 — 과거 실현변동성 단독으로 2.2~3.2배가 나온다.
    그래서 모든 신호를 **과거 변동성 오분위 안에서** 이중정렬해 증분만 본다.
    증분이 없으면 그 신호는 과거 변동성의 재포장이다.

⚠ 새 기질이라 처음 보는 축이다
    `binance_funding_rate` 는 2026-08-15 까지 **26종목**뿐이었다. 어제 354종목 ·
    116만 행 · 2021-01~ 으로 늘렸다. 펀딩으로 **꼬리 방향**을 묻는 건 이 기질이
    없어 못 하던 질문이다.
    기전 가설: 극단 음수 펀딩 = 숏 과밀 = **위쪽 꼬리(스퀴즈) 연료**,
              극단 양수 펀딩 = 롱 과밀 = **아래쪽 꼬리(청산 연쇄) 연료**.

⚠ 교차자산 위약이 필수다 (교훈 #93)
    종목별 신호는 **다른 종목의 신호로 이 종목을 예측**해 보면 무너지는 일이
    흔하다. 온چ인 축이 정확히 거기서 죽었다.

정의
    꼬리 = 그 날의 **횡단면 상위 5% / 하위 5%** (앞으로 5일 수익률 기준).
    날마다 기저율이 5% 로 고정되므로 국면에 휘둘리지 않는다.

사용:
  python3 -m scripts.research.tail_event_predictability --fwd 5
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tail")

OUT = ROOT / "runs" / "research_track" / "tail_event_predictability.json"

MIN_ADV = 3e6
MIN_HIST = 60
TAIL_Q = 0.05
SPLIT = "2025-06-01"
NQ = 5                       # 오분위


def load(conn):
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT symbol, date, close, volume FROM ohlcv_daily ORDER BY date, symbol"
    )).fetchall()
    d = pd.DataFrame(r, columns=["symbol", "ts", "close", "volume"])
    d["ts"] = pd.to_datetime(d["ts"])
    for c in ("close", "volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    close = d.pivot(index="ts", columns="symbol", values="close").sort_index()
    dv = (d.assign(x=d["close"] * d["volume"])
           .pivot(index="ts", columns="symbol", values="x").sort_index())
    f = conn.execute(text(
        "SELECT symbol, date_trunc('day', funding_time) d, sum(funding_rate) fr "
        "FROM binance_funding_rate GROUP BY symbol, d")).fetchall()
    fu = pd.DataFrame(f, columns=["symbol", "ts", "fr"])
    fu["ts"] = pd.to_datetime(fu["ts"])
    fu["fr"] = pd.to_numeric(fu["fr"], errors="coerce")
    fund = fu.pivot(index="ts", columns="symbol", values="fr").sort_index()
    return close, dv, fund


def qcut_rows(df: pd.DataFrame, nq: int) -> pd.DataFrame:
    """날짜별 횡단면 오분위(0..nq-1). 국면 드리프트를 자동으로 제거한다."""
    return df.rank(axis=1, pct=True).apply(
        lambda r: np.minimum((r * nq).astype(float).fillna(-1) // 1, nq - 1),
        axis=0)


def table(flag_up, flag_dn, q, elig, lab, out, split_ts):
    """오분위별 상·하 꼬리 확률과 **비대칭**(상 − 하)."""
    print(f"\n  ── {lab} " + "─" * 66)
    print(f"     {'오분위':>7}{'표본':>9}{'상위꼬리%':>10}{'하위꼬리%':>10}"
          f"{'비대칭%p':>10}{'OOS 비대칭%p':>13}")
    rec = {}
    m = elig & q.notna() & (flag_up.notna() | flag_dn.notna())
    is_m = pd.Series(q.index < split_ts, index=q.index)
    for k in range(NQ):
        sel = m & (q == k)
        n = int(sel.values.sum())
        if n < 200:
            continue
        u = float(flag_up.where(sel).sum().sum() / n * 100)
        d = float(flag_dn.where(sel).sum().sum() / n * 100)
        so = sel & ~is_m.values[:, None]
        no = int(so.values.sum())
        uo = float(flag_up.where(so).sum().sum() / no * 100) if no > 200 else np.nan
        do = float(flag_dn.where(so).sum().sum() / no * 100) if no > 200 else np.nan
        rec[k] = {"n": n, "up_pct": u, "dn_pct": d, "asym": u - d,
                  "oos_asym": (uo - do) if no > 200 else None}
        print(f"     {k:>7}{n:>9,}{u:>10.2f}{d:>10.2f}{u-d:>+10.2f}"
              f"{(uo-do if no>200 else np.nan):>+13.2f}")
    if len(rec) >= 2:
        ks = sorted(rec)
        spread = rec[ks[-1]]["asym"] - rec[ks[0]]["asym"]
        mono = all(rec[ks[i]]["asym"] <= rec[ks[i+1]]["asym"]
                   for i in range(len(ks)-1)) or \
               all(rec[ks[i]]["asym"] >= rec[ks[i+1]]["asym"]
                   for i in range(len(ks)-1))
        print(f"     상단−하단 비대칭 갈림 **{spread:+.2f}%p** · 단조 "
              f"{'○' if mono else '✗'}")
        rec["_spread"] = spread
        rec["_monotone"] = bool(mono)
    out[lab] = rec
    return rec


def main() -> int:
    p = argparse.ArgumentParser(description="꼬리 사건 예측 가능성")
    p.add_argument("--fwd", type=int, default=5, help="앞으로 며칠")
    p.add_argument("--since", default="2022-01-01")
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from app.db.session import engine
    with engine.connect() as conn:
        close, dv, fund = load(conn)

    adv = dv.rolling(30, min_periods=20).mean().shift(1)
    hist = close.notna().rolling(MIN_HIST, min_periods=1).sum().shift(1)
    elig = (adv >= MIN_ADV) & (hist >= MIN_HIST) & close.notna()
    ret = close.pct_change()

    # ── 목표: 앞으로 fwd 일 수익률의 **횡단면** 상·하위 5% ──────────────
    fwd = close.shift(-a.fwd) / close - 1
    fwd = fwd.where(elig)
    r_pct = fwd.rank(axis=1, pct=True)
    up = (r_pct >= 1 - TAIL_Q)
    dn = (r_pct <= TAIL_Q)

    # ── 예측자 (전부 t 시점까지의 정보) ────────────────────────────────
    rv30 = ret.rolling(30, min_periods=20).std().shift(1)         # 과거 실현변동성
    f3 = fund.reindex(index=close.index, columns=close.columns).fillna(0.0)
    f_sum3 = f3.rolling(3, min_periods=1).sum().shift(1)          # 직전 3일 펀딩
    f_mu = f3.rolling(30, min_periods=10).mean().shift(1)
    f_sd = f3.rolling(30, min_periods=10).std().shift(1)
    f_z = ((f3.shift(1) - f_mu) / f_sd).replace([np.inf, -np.inf], np.nan)
    dd30 = (close / close.rolling(30, min_periods=20).max() - 1).shift(1)
    turn = (dv / dv.rolling(30, min_periods=20).mean()).shift(1)

    split_ts = pd.Timestamp(SPLIT)
    base = elig & (close.index >= a.since)[:, None] if False else \
        elig & pd.Series(close.index >= a.since, index=close.index).values[:, None]
    log.info("표본 %d일 × %d종목 · 자격 셀 %s",
             len(close), close.shape[1], f"{int(base.values.sum()):,}")

    print("=" * 100)
    print(f"  **꼬리 사건 예측 가능성** — 앞으로 {a.fwd}일 · 꼬리 = 그 날 횡단면 "
          f"상·하위 {TAIL_Q:.0%} · 기저율 각 {TAIL_Q:.0%}")
    print(f"  ⚠ 묻는 건 '크게 움직이나'가 아니라 **'위인가 아래인가'** 다. "
          f"비대칭(상−하)이 0 이면 방향을 모르는 것이다")
    print(f"  ⚠ 표본 밖 분할 {SPLIT}")
    print("=" * 100)

    res: dict = {}
    preds = [("과거 변동성 rv30 (기준선)", rv30),
             ("펀딩 z (30일)", f_z),
             ("펀딩 3일 누적", f_sum3),
             ("30일 고점 대비 낙폭", dd30),
             ("거래대금 회전 turn", turn)]
    for lab, sig in preds:
        q = qcut_rows(sig.where(base), NQ)
        table(up, dn, q, base, lab, res, split_ts)

    # ── 이중정렬 — 과거 변동성 안에서 펀딩이 증분을 주는가 (교훈 #94) ──
    print("\n" + "=" * 100)
    print("  **이중정렬** — 과거 변동성 오분위 **안에서** 펀딩 z 의 증분")
    print("  (증분이 없으면 펀딩은 과거 변동성의 재포장이다)")
    qv = qcut_rows(rv30.where(base), NQ)
    qf = qcut_rows(f_z.where(base), NQ)
    print(f"\n     {'rv30':>7}" + "".join(f"{'펀딩Q'+str(k):>11}" for k in range(NQ))
          + f"{'갈림':>10}")
    dbl = {}
    for v in range(NQ):
        row, cells_ = [], {}
        for k in range(NQ):
            sel = base & (qv == v) & (qf == k)
            n = int(sel.values.sum())
            if n < 200:
                row.append(np.nan)
                continue
            asym = float((up.where(sel).sum().sum()
                          - dn.where(sel).sum().sum()) / n * 100)
            row.append(asym)
            cells_[k] = {"n": n, "asym": asym}
        good = [x for x in row if x == x]
        spread = (good[-1] - good[0]) if len(good) >= 2 else np.nan
        dbl[v] = {"cells": cells_, "spread": spread}
        print(f"     {v:>7}" + "".join(f"{x:>+11.2f}" if x == x else f"{'—':>11}"
                                       for x in row) + f"{spread:>+10.2f}")
    res["double_sort_rv_x_funding"] = dbl
    sp = [d["spread"] for d in dbl.values() if d["spread"] == d["spread"]]
    print(f"\n     변동성 오분위별 갈림 — 중앙 {np.median(sp):+.2f}%p · "
          f"부호 일치 {sum(1 for x in sp if x*np.median(sp) > 0)}/{len(sp)}")

    # ── 교차자산 위약 (교훈 #93) ──────────────────────────────────────
    print("\n" + "=" * 100)
    print("  **교차자산 위약** — 종목 신호를 한 칸 밀어 **다른 종목**을 예측")
    cols = list(f_z.columns)
    f_shift = f_z.copy()
    f_shift.columns = cols[1:] + cols[:1]
    f_shift = f_shift.reindex(columns=cols)
    qp = qcut_rows(f_shift.where(base), NQ)
    pl = table(up, dn, qp, base, "펀딩 z (교차자산 위약)", res, split_ts)
    obs = res.get("펀딩 z (30일)", {}).get("_spread")
    if obs is not None and "_spread" in pl:
        print(f"\n     관측 갈림 {obs:+.2f}%p vs 위약 {pl['_spread']:+.2f}%p")
        print(f"     ⚠ 위약이 관측만큼 크면 그건 종목 신호가 아니라 **시장 전체 효과**다")

    print("\n" + "=" * 100)
    print("  읽는 법")
    print("    · 비대칭이 오분위에 걸쳐 **단조**여야 신호다. 들쭉날쭉하면 잡음이다.")
    print("    · IS 에서 갈리고 **OOS 에서 부호가 뒤집히면** 그 축은 죽은 것이다.")
    print("    · 이중정렬에서 증분이 사라지면 과거 변동성만 있으면 되는 것이다.")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"params": vars(a), "results": res}, ensure_ascii=False,
        indent=2, default=str))
    print(f"  → {a.out}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
