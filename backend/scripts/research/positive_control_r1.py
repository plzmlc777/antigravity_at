#!/usr/bin/env python3
"""양성 대조 — 검증된 알파를 현재 R-1 3-gate 에 태운다.

왜 필요한가 (2026-08-08):
  마지막 R-4 PASS 가 2026-05-21 이고 그 뒤 79일간 0건이다. 최근 29건 사유는
  "zero directional information" 이 지배적인데, 이것만으로는 세 가설이 구분되지
  않는다.
    A. 검증 파이프라인 결함 — 진짜 알파도 falsify 한다
    B. 시장에 알파가 없다 (era-universal decay)
    C. 탐색 공간 소진 (131 graveyard, DNA 중복 반복)

  구분법은 양성 대조다. **실재가 확인된 알파**를 같은 게이트에 넣어
  통과하면 A 배제, falsify 되면 A 확정이다.

대조 대상: lifecycle pump-decay (신규 상장 Day-1 숏, 30일 보유)
  - R-4 PASS 이력
  - 실계좌 3개월 +240.17 USDT 실현 (2026-06~08)
  - lookahead 없음 (일봉·Day-30 이라 실행 지연에 둔감)
  즉 "이 시스템에서 유일하게 실전 수익이 확인된 알파" 다.

R-1 과 동일 도구를 쓴다: _perm_utils.fee_aware_perm_test / bootstrap_ci,
동일 임계값 (signal_t_excess>=2.0, ci_lower>0, perm_p_above<=0.10).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("positive_control")

LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT = ROOT / "runs" / "research_track" / "positive_control_r1__metrics.json"

FEE_RT = 0.0008
SL_LEVEL = 0.50
HOLD_DAYS = 30
# R-1 게이트 임계값 (paradigm126_r1.py 와 동일)
T_EXCESS_MIN = 2.0
PERM_P_MAX = 0.10
EDGE_PCT_MIN = 2.0


def load_daily(db, sym):
    rows = db.execute(text(
        "SELECT timestamp, open, high, low, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    ), {"s": sym}).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return pd.DataFrame({
        "open": df["open"].resample("1D").first(),
        "high": df["high"].resample("1D").max(),
        "low": df["low"].resample("1D").min(),
        "close": df["close"].resample("1D").last(),
    }).dropna()


def short_ret(daily, entry_idx, sl_level=SL_LEVEL, hold=HOLD_DAYS):
    """R-3 lifecycle_phase_r3.simulate_short 과 동일 (SL + 시간청산)."""
    if entry_idx >= len(daily):
        return None
    ep = float(daily.iloc[entry_idx]["close"])
    if ep <= 0:
        return None
    sl = ep * (1.0 + sl_level)
    mx = min(entry_idx + hold, len(daily) - 1)
    exit_px = float(daily.iloc[mx]["close"])
    for i in range(entry_idx + 1, mx + 1):
        if float(daily.iloc[i]["high"]) >= sl:
            exit_px = sl
            break
    return (ep - exit_px) / ep  # gross (숏)


def main() -> int:
    db = SessionLocal()
    try:
        listings = json.loads(LISTINGS.read_text())
        today = date.today()
        syms = sorted({r[0] for r in db.execute(text(
            "SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m'")).fetchall()})

        trig_gross, pool_gross = [], []
        cohort = 0
        for sym in syms:
            meta = listings.get(sym)
            daily = load_daily(db, sym)
            if daily.empty or len(daily) < HOLD_DAYS + 5:
                continue

            # ── candidate pool: 같은 심볼의 **모든** 30일 숏 윈도우 (트리거 무관)
            #    R-1 이 fwd_ret 전체를 풀로 쓰는 것과 동일한 구성.
            for i in range(0, len(daily) - HOLD_DAYS - 1, 3):  # stride 3d (부하 완화)
                r = short_ret(daily, i)
                if r is not None and np.isfinite(r):
                    pool_gross.append(r)

            # ── 트리거: 상장일 Day-1
            if not isinstance(meta, dict) or not meta.get("onboard_date"):
                continue
            ld = datetime.strptime(meta["onboard_date"], "%Y-%m-%d").date()
            if not (HOLD_DAYS <= (today - ld).days <= 365):
                continue
            try:
                pos = daily.index.get_indexer([pd.Timestamp(ld)], method="nearest")[0]
            except Exception:
                continue
            if abs((daily.index[pos].date() - ld).days) > 2 or pos >= len(daily) - HOLD_DAYS:
                continue
            r = short_ret(daily, pos)
            if r is not None and np.isfinite(r):
                trig_gross.append(r)
                cohort += 1
    finally:
        db.close()

    if cohort < 20:
        log.error("코호트 부족: %d", cohort)
        return 1

    trig_gross = np.array(trig_gross)
    pool_gross = np.array(pool_gross)
    trig_net = trig_gross - FEE_RT

    log.info("트리거 %d건 / 후보풀 %d건", len(trig_net), len(pool_gross))

    perm = fee_aware_perm_test(
        observed_net_returns=trig_net,
        candidate_pool_returns=pool_gross,
        fee_per_trade=FEE_RT, n_perms=1000, rng_seed=42)
    ci = bootstrap_ci(trig_net, n_boot=2000, block_size=1, alpha=0.05, rng_seed=42)

    t_excess = float(perm.get("signal_t_excess", float("nan")))
    perm_p_above = float(perm.get("perm_p_one_sided_above", float("nan")))
    ci_lower_bp = float(ci["ci_lower"]) * 10000
    edge_pct = float(trig_net.mean()) * 100

    gate_excess = bool(t_excess >= T_EXCESS_MIN)
    gate_ci = bool(ci_lower_bp > 0)
    gate_perm = bool(perm_p_above <= PERM_P_MAX)
    three_gate = gate_excess and gate_ci and gate_perm
    edge_gate = bool(edge_pct >= EDGE_PCT_MIN)

    print()
    print("=" * 72)
    print("양성 대조 — lifecycle pump-decay (실계좌 3개월 +240.17 USDT 실현)")
    print("=" * 72)
    print(f"  트리거 n            {len(trig_net)}")
    print(f"  후보풀 n            {len(pool_gross):,}")
    print(f"  거래당 net          {edge_pct:+.3f}%  ({edge_pct*100:+.1f}bp)")
    print(f"  중앙값 net          {float(np.median(trig_net))*100:+.3f}%")
    print()
    print(f"  {'게이트':<22}{'값':>14}{'기준':>14}  판정")
    print(f"  {'signal_t_excess':<22}{t_excess:>14.3f}{'>= 2.0':>14}  {'PASS' if gate_excess else 'FAIL'}")
    print(f"  {'ci_lower_bp':<22}{ci_lower_bp:>14.2f}{'> 0':>14}  {'PASS' if gate_ci else 'FAIL'}")
    print(f"  {'perm_p_one_above':<22}{perm_p_above:>14.4f}{'<= 0.10':>14}  {'PASS' if gate_perm else 'FAIL'}")
    print(f"  {'-'*22}{'-'*14}{'-'*14}")
    print(f"  {'3-gate':<22}{'':>28}  {'PASS' if three_gate else 'FAIL'}")
    print(f"  {'edge >= 2% (L#41)':<22}{edge_pct:>14.3f}{'>= 2.0':>14}  {'PASS' if edge_gate else 'FAIL'}")
    print()
    # 해석은 게이트 조합으로 갈린다. "3-gate FAIL = 파이프라인 결함" 은 성급하다 —
    # 이 대조군은 고분산 저빈도라 평균 CI 하한이 음수인 것이 **정상**이고,
    # R-2 원본(n=167)도 mean_ci_lo -0.30% 로 같은 성질을 보였다. 당시 통과 근거는
    # 평균 CI 가 아니라 중앙값 CI(+3.27%)와 순열검정(median +21.61% vs null -0.60%,
    # sigma 6.8, p=0.000) 이었다.
    if three_gate:
        print("  → 파이프라인이 검증된 알파를 통과시킨다. 가설 A(파이프라인 결함) 배제.")
    elif gate_excess and gate_perm and not gate_ci:
        print("  → t_excess/perm 은 통과하고 ci_lower 만 FAIL 이다.")
        print("    이 대조군은 승률 50%대 + SL -50% 좌측꼬리라 분산이 크고,")
        print("    R-2 원본(n=167)도 mean_ci_lo -0.30% 로 동일한 성질을 보였다.")
        print("    → 파이프라인이 '틀린' 게 아니라, **평균 CI 게이트가 고분산 전략에")
        print("      구조적으로 불리**하다. 가설 A 는 배제하되 게이트 설계 편향은 실재한다.")
    else:
        print("  → 파이프라인이 실전 수익이 확인된 알파를 다차원으로 falsify 한다.")
        print("    가설 A 유력 — 판정 로직 재검토 필요.")
    print("=" * 72)

    OUT.write_text(json.dumps({
        "generated_at": datetime.utcnow().isoformat(),
        "control": "lifecycle pump-decay (신규 상장 Day-1 숏, 30일 보유, SL 50%)",
        "evidence": "R-4 PASS + 실계좌 2026-06~08 실현손익 +240.17 USDT",
        "n_trigger": int(len(trig_net)), "n_pool": int(len(pool_gross)),
        "edge_pct": edge_pct, "signal_t_excess": t_excess,
        "ci_lower_bp": ci_lower_bp, "perm_p_one_sided_above": perm_p_above,
        "gates": {"excess": gate_excess, "ci": gate_ci, "perm": gate_perm,
                  "three_gate": three_gate, "edge_2pct": edge_gate},
        "thresholds": {"t_excess": T_EXCESS_MIN, "perm_p": PERM_P_MAX, "edge_pct": EDGE_PCT_MIN},
    }, indent=2, ensure_ascii=False))
    log.info("wrote %s", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
