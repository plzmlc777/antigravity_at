"""신규 상장 코호트의 BTC 베타 — 실거래 장부가 실제로 지는 노출.

왜
    어제 잰 비대칭 베타(β⁺ 1.032 / β⁻ 1.396)는 **기성 유동 알트 60종목
    동일가중 바스켓 · 2021~2026** 이다. 실거래 장부는 **신규 상장 1~3종목
    집중 · 2025~2026** 이다. 모집단도 기간도 다르므로 그 숫자를 장부에
    적용할 근거가 없었다. 여기서 그걸 직접 잰다.

⚠ 기간을 맞추지 않으면 코호트 효과와 기간 효과가 섞인다
    그래서 **같은 날짜 · 같은 데이터원**으로 세 계열을 동시에 만든다:
        ① 코호트 바스켓 — 그 날 **보유창 안에 있는** 상장 종목 동일가중
        ② 기성 바스켓   — 같은 날 대조 풀(85종목) 동일가중
        ③ BTC
    ①과 ②의 차이만이 "신규 상장이라서" 생긴 차이다.

⚠ 바스켓 구성이 곧 장부 구성이다
    실거래는 여러 상장을 동시에 보유한다(종목당 상한 20%). 그러므로 **그 날
    활성인 상장들의 동일가중 평균**이 장부의 하루 수익률에 해당한다. 개별
    종목 수익률을 그냥 풀링하면 동시 보유 구조가 사라진다.

⚠ 시간봉을 일봉으로 되접는다
    `ohlcv_daily` 는 최근 상장 다수가 비어 205건까지만 잡힌다. `ohlcv_hourly`
    는 같은 코호트가 322건이고 BTC 도 같은 표에 있다 — 한 데이터원에서
    양쪽을 만들어야 기준이 어긋나지 않는다.

⚠ 부호 규약 — 숏 관점으로 읽어라
    장부는 **숏**이다. β⁻(하락일 베타)가 크면 숏에게 **유리**하고, β⁺(상승일)
    가 크면 **불리**하다. α 는 보합일 캐리이고 숏에게는 부호가 뒤집힌다.

사용:
  python3 -m scripts.research.lifecycle_cohort_beta --hold-days 30
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("cohort_beta")

LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT = ROOT / "runs" / "research_track" / "lifecycle_cohort_beta.json"

BENCH = "BTCUSDT"
CONTROL_LISTED_BEFORE = "2024-07-01"
CONTROL_MIN_ADV = 3e6
CONTROL_MIN_DAYS = 500
ENTRY_LAG_DAYS = 1        # 상장 다음날부터 보유 (실거래 = 상장+24h 진입)


def to_daily(h: pd.DataFrame) -> pd.DataFrame:
    """시간봉 → 일봉(UTC). 종가만 쓰므로 마지막 값."""
    return h.pivot(index="ts", columns="symbol", values="close").sort_index() \
            .resample("1D").last()


def fit(alt: pd.Series, btc: pd.Series) -> dict:
    """alt = α + β⁺·max(btc,0) + β⁻·min(btc,0)"""
    d = pd.concat([alt.rename("a"), btc.rename("b")], axis=1).dropna()
    if len(d) < 60:
        return {"n": int(len(d))}
    up = np.maximum(d["b"].values, 0.0)
    dn = np.minimum(d["b"].values, 0.0)
    X = np.column_stack([np.ones(len(d)), up, dn])
    y = d["a"].values
    c, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ c
    # 계수 표준오차 (등분산 가정) — 갈림이 잡음인지 보려면 필요하다
    dof = max(1, len(d) - 3)
    s2 = float(resid @ resid) / dof
    cov = s2 * np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    # β⁻ − β⁺ 의 표준오차
    v = cov[2, 2] + cov[1, 1] - 2 * cov[1, 2]
    gap = float(c[2] - c[1])
    return {"n": int(len(d)), "alpha_pct": float(c[0] * 100),
            "alpha_t": float(c[0] / se[0]) if se[0] else None,
            "beta_up": float(c[1]), "beta_down": float(c[2]),
            "gap": gap, "gap_t": float(gap / np.sqrt(v)) if v > 0 else None,
            "mean_pct": float(y.mean() * 100)}


def main() -> int:
    p = argparse.ArgumentParser(description="신규 상장 코호트 BTC 베타")
    p.add_argument("--since", default="2025-01-01")
    p.add_argument("--hold-days", type=int, default=30)
    p.add_argument("--rot", type=int, default=200)
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from sqlalchemy import text

    from app.db.session import engine
    listings = json.loads(LISTINGS.read_text())
    cohort = {k: m["onboard_date"] for k, m in listings.items()
              if isinstance(m, dict) and m.get("onboard_date")
              and m["onboard_date"] >= a.since}
    pool_cand = sorted(k for k, m in listings.items()
                       if isinstance(m, dict) and m.get("onboard_date")
                       and m["onboard_date"] <= CONTROL_LISTED_BEFORE)

    with engine.connect() as conn:
        liq = {r[0]: (r[1], float(r[2] or 0)) for r in conn.execute(text(
            "SELECT symbol, count(*), avg(close*volume) FROM ohlcv_daily "
            "WHERE date >= :d GROUP BY symbol"), {"d": a.since}).fetchall()}
        pool = [s for s in pool_cand
                if liq.get(s, (0, 0))[0] >= CONTROL_MIN_DAYS
                and liq.get(s, (0, 0))[1] >= CONTROL_MIN_ADV]
        syms = sorted(set(cohort) | set(pool) | {BENCH})
        r = conn.execute(text(
            "SELECT symbol, ts, close FROM ohlcv_hourly WHERE symbol = ANY(:s) "
            "ORDER BY symbol, ts"), {"s": syms}).fetchall()
    h = pd.DataFrame(r, columns=["symbol", "ts", "close"])
    h["ts"] = pd.to_datetime(h["ts"])
    h["close"] = pd.to_numeric(h["close"], errors="coerce")
    close = to_daily(h)
    ret = close.pct_change()
    ret = ret[ret.index >= a.since]
    log.info("코호트 %d상장 · 대조 풀 %d종목 · 일봉 %d일",
             len(cohort), len(pool), len(ret))

    # ── ① 코호트 바스켓 — 그 날 보유창 안에 있는 상장만 ────────────────
    mask = pd.DataFrame(False, index=ret.index, columns=ret.columns)
    for s, d0 in cohort.items():
        if s not in mask.columns:
            continue
        ld = pd.Timestamp(datetime.strptime(d0, "%Y-%m-%d"))
        lo = ld + pd.Timedelta(days=ENTRY_LAG_DAYS)
        hi = ld + pd.Timedelta(days=ENTRY_LAG_DAYS + a.hold_days)
        mask.loc[(mask.index >= lo) & (mask.index <= hi), s] = True
    mask &= ret.notna()
    coh_ret = ret.where(mask).mean(axis=1, skipna=True)
    n_active = mask.sum(axis=1)

    # ── ② 기성 바스켓 — 같은 날짜 ─────────────────────────────────────
    pm = pd.DataFrame(False, index=ret.index, columns=ret.columns)
    for s in pool:
        if s in pm.columns:
            pm[s] = True
    pm &= ret.notna()
    est_ret = ret.where(pm).mean(axis=1, skipna=True)

    btc = ret[BENCH] if BENCH in ret.columns else pd.Series(dtype=float)
    # 두 바스켓이 다 살아 있는 날만 — 같은 표본에서 비교해야 한다
    ok = coh_ret.notna() & est_ret.notna() & btc.notna() & (n_active >= 3)
    coh_ret, est_ret, btc_r, n_active = (coh_ret[ok], est_ret[ok], btc[ok],
                                         n_active[ok])
    log.info("공통 표본 %d일 · 동시 활성 상장 중앙 %d개 (최대 %d)",
             len(coh_ret), int(n_active.median()), int(n_active.max()))

    print("=" * 100)
    print(f"  **신규 상장 코호트 BTC 베타** — {coh_ret.index[0].date()} ~ "
          f"{coh_ret.index[-1].date()} · {len(coh_ret)}일 · 동시 활성 상장 중앙 "
          f"{int(n_active.median())}개")
    print(f"  알트 = α + β⁺·max(BTC,0) + β⁻·min(BTC,0)   ⚠ 장부는 **숏**이다 — "
          f"β⁻ 큰 건 유리, β⁺ 큰 건 불리")
    print("=" * 100)

    res = {}
    rows = [("① 신규 상장 코호트", coh_ret), ("② 기성 대조 풀", est_ret)]
    print(f"\n  {'':>18}{'일수':>6}{'α %/일':>9}{'α t':>7}{'β⁺ 상승':>9}"
          f"{'β⁻ 하락':>9}{'갈림':>8}{'갈림 t':>8}{'일평균%':>9}")
    for lab, s in rows:
        f = fit(s, btc_r)
        res[lab] = f
        print(f"  {lab:>18}{f['n']:>6}{f['alpha_pct']:>9.4f}"
              f"{(f['alpha_t'] or 0):>7.2f}{f['beta_up']:>9.3f}"
              f"{f['beta_down']:>9.3f}{f['gap']:>8.3f}{(f['gap_t'] or 0):>8.2f}"
              f"{f['mean_pct']:>9.4f}")

    # ── 보유 구간별 — 초반과 후반이 다른가 ────────────────────────────
    print(f"\n  보유 구간별 (코호트만)")
    for lo, hi, lab in ((1, 7, "Day 1-7"), (8, 30, "Day 8-30")):
        m2 = pd.DataFrame(False, index=ret.index, columns=ret.columns)
        for s, d0 in cohort.items():
            if s not in m2.columns:
                continue
            ld = pd.Timestamp(datetime.strptime(d0, "%Y-%m-%d"))
            m2.loc[(m2.index >= ld + pd.Timedelta(days=lo))
                   & (m2.index <= ld + pd.Timedelta(days=hi)), s] = True
        m2 &= ret.notna()
        sr = ret.where(m2).mean(axis=1, skipna=True)
        sr = sr[m2.sum(axis=1) >= 3]
        f = fit(sr, btc_r)
        if f.get("n", 0) < 60:
            print(f"  {lab:>18}  표본 부족 (n={f.get('n',0)})")
            continue
        res[lab] = f
        print(f"  {lab:>18}{f['n']:>6}{f['alpha_pct']:>9.4f}"
              f"{(f['alpha_t'] or 0):>7.2f}{f['beta_up']:>9.3f}"
              f"{f['beta_down']:>9.3f}{f['gap']:>8.3f}{(f['gap_t'] or 0):>8.2f}"
              f"{f['mean_pct']:>9.4f}")

    # ── 원형회전 위약 — 코호트 갈림이 진짜인가 ────────────────────────
    rng = np.random.default_rng(20260816)
    bv = btc_r.values
    obs = res["① 신규 상장 코호트"]["gap"]
    null = []
    y = coh_ret.values
    for _ in range(a.rot):
        k = int(rng.integers(30, len(bv) - 30))
        r_ = np.roll(bv, k)
        X = np.column_stack([np.ones(len(y)), np.maximum(r_, 0), np.minimum(r_, 0)])
        c, *_ = np.linalg.lstsq(X, y, rcond=None)
        null.append(c[2] - c[1])
    null = np.array(null)
    p_rot = float((np.abs(null) >= abs(obs)).mean())
    print(f"\n  원형회전 위약 {a.rot}회 (코호트 갈림) — |귀무| 중앙 "
          f"{np.median(np.abs(null)):.3f} · p95 {np.percentile(np.abs(null),95):.3f}"
          f" · **p {p_rot:.3f}**")
    res["p_rotation_cohort"] = p_rot

    # ── 숏 관점 요약 ──────────────────────────────────────────────────
    c_, e_ = res["① 신규 상장 코호트"], res["② 기성 대조 풀"]
    print("\n" + "=" * 100)
    print("  **숏 관점으로 다시 읽기** (장부는 숏이므로 부호를 뒤집는다)")
    for lab, f in (("신규 코호트 숏", c_), ("기성 풀 숏", e_)):
        print(f"     {lab:>14}  BTC 하락일 **{f['beta_down']:.2f}배로 번다** · "
              f"상승일 **{f['beta_up']:.2f}배로 잃는다** · "
              f"보합일 캐리 {-f['alpha_pct']:+.4f}%/일 "
              f"(연 {-f['alpha_pct']*365:+.0f}%)")
    print(f"\n     ⚠ 위험 관리에 쓸 숫자는 **β⁺**(불리한 쪽)이다. β⁻ 가 크다는 건")
    print(f"        이익 쪽 증폭이라 사이징을 줄일 근거가 못 된다.")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"params": vars(a), "n_days": int(len(coh_ret)),
         "n_active_median": int(n_active.median()), "results": res},
        ensure_ascii=False, indent=2, default=str))
    print("\n" + "=" * 100)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
