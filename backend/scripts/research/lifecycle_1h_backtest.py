"""신상저격수 **1시간봉** 백테스트 — 정본 커널 그대로, 해상도만 바꾼다.

왜 1h 인가 (사전 측정 `lifecycle_resolution_study` 결과)
    커널은 미래참조를 피하려고 **진입 바에서 손절을 보지 않는다**(옳다).
    그런데 그 바의 상승폭이 손절보다 크면 **그 손절은 존재하지 않는다.**

        진입 바 상승폭   일봉 p50 **32.7%**  /  1h p50 **3.8%**
        손절 20% 무력화  일봉 **60.0%**      /  1h **3.3%**

    즉 지금 실거래 손절 20% 조차 일봉 harness 에서는 60% 가 기록되지 않는다.
    일봉 격자가 "조일수록 좋다"(손절 50%→2%: 2.63%→7.64%)고 말한 이유가
    여기 있을 수 있다. **1h 로 내려야 그 구간을 처음으로 측정할 수 있다.**

⚠ 새 백테스터를 만들지 않는다
    `GenericBacktester.run_rule_based` 를 그대로 쓴다. 손익 구현체를 하나 더
    만드는 순간 정본 밖으로 나간다 — 그게 [[project-canon-backtest-unification]]
    에서 **6개 중 4개가 오염됐던** 이유다.

⚠ 진입 시점을 일봉판과 **똑같이** 맞춘다
    안 맞추면 해상도가 아니라 **다른 전략**을 비교하게 된다.

        일봉  bar[0]=상장일 → 신호 지연 1봉 → bar[1] 시가 체결 = 상장+24h
        1h    bar[0]=상장+23시 → 신호 지연 1봉 → bar[1] 시가 체결 = **상장+24h**

    그래서 1h 봉을 **상장+23시부터** 잘라 넣는다. 두 판본의 체결 시각이
    같아지고 남는 차이는 손절·익절 판정 해상도뿐이다.

⚠ 소스는 그대로 쓴다
    `bn_lifecycle_decay` 는 진입창을 **시각**(`pd.Timedelta(days=...)`)으로
    닫는다 — 봉 개수가 아니다. 그래서 1h 에서도 수정 없이 작동한다.
    (`bn_lifecycle_decay_early_exit` 는 `Day N = iloc[N-1]` 이라 1h 에서
     7시간/14시간이 된다 — 이 스크립트는 **base 변형만** 다룬다.)

사용:
  python3 -m scripts.research.lifecycle_1h_backtest --split 2026-05-13 \
      --axis sl=0.02,0.05,0.10,0.20,0.50
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lc_1h")

LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT = ROOT / "runs" / "research_track" / "lifecycle_1h_backtest.json"

ENTRY_OFFSET_H = 23        # 상장+23시부터 자른다 → 체결이 상장+24h

# 손절 무력화율 — **체결 바**(상장+24h 의 1시간봉) 기준 실측 (544상장, 2026-08-15)
#   1h 체결 바 상승폭  p50 2.09% · p75 4.69% · p90 9.23%
#
#     손절     1h      일봉      ← 일봉에서 못 보던 구간이 열린다
#       2%   51.3%    79.9%
#       5%   23.9%    58.5%
#      10%    8.8%    35.6%   ← 여기부터 1h 전용 구간
#      15%    2.9%       —
#      20%    1.3%    16.9%
#      30%    0.6%     9.6%
#
# 그래서 1h harness 의 정직한 하한은 **0.08~0.10** 이다(일봉은 0.20).
# 5% 이하는 1h 에서도 24~51% 가 기록되지 않으므로 쓰지 마라.
SL_FLOOR_1H = 0.08
SL_NULLIFY_1H = {0.02: 51.3, 0.05: 23.9, 0.08: 11.9, 0.10: 8.8,
                 0.15: 2.9, 0.20: 1.3, 0.30: 0.6, 0.50: 0.0}
HOLD_DAYS = 30
MIN_BARS = 24 * 5          # 최소 5일치는 있어야 판정


def load_cohort(conn, since: str) -> list[dict]:
    from sqlalchemy import text
    listings = json.loads(LISTINGS.read_text())
    h = pd.DataFrame(conn.execute(text(
        "SELECT symbol, ts, open, high, low, close, volume FROM ohlcv_hourly "
        "ORDER BY symbol, ts")).fetchall(),
        columns=["symbol", "ts", "open", "high", "low", "close", "volume"])
    h["ts"] = pd.to_datetime(h["ts"])
    for c in ("open", "high", "low", "close", "volume"):
        h[c] = pd.to_numeric(h[c], errors="coerce")
    out = []
    for sym, g in h.groupby("symbol"):
        meta = listings.get(sym)
        if not isinstance(meta, dict) or not meta.get("onboard_date"):
            continue
        d = meta["onboard_date"]
        if d < since:
            continue
        ld = pd.Timestamp(datetime.strptime(d, "%Y-%m-%d"))
        bars = g.set_index("ts").sort_index()[["open", "high", "low", "close",
                                               "volume"]]
        # ⚠ 상장+23시부터 — 체결이 상장+24h 가 되도록 (일봉판과 동일)
        start = ld + pd.Timedelta(hours=ENTRY_OFFSET_H)
        end = ld + pd.Timedelta(days=HOLD_DAYS + 2)
        seg = bars.loc[(bars.index >= start) & (bars.index <= end)]
        if len(seg) < MIN_BARS:
            continue
        out.append({"symbol": sym, "listing": d, "bars": seg,
                    "anchor": seg.index[0]})
    return out


def run_one(item: dict, sl: float, tp: float | None, hold_h: int) -> list:
    """정본 커널로 한 상장을 돌린다. 새 손익 구현을 만들지 않는다."""
    from app.composer_framework.backtester import GenericBacktester
    from app.composer_framework.pipeline_spec import build_pipeline
    from app.composer_framework.signal_source import SourceContext

    ps = {
        "sources": [{"type": "bn_lifecycle_decay",
                     "kwargs": {
                         # 진입창은 **시각** 기준이라 1h 에서도 그대로 동작한다.
                         # 자른 구간의 첫 봉을 기준일로 준다.
                         "listing_date": str(item["anchor"]),
                         "max_age_days": HOLD_DAYS,
                         # ⚠ **0** 이다 — 소스가 `int(entry_window_days)` 로
                         #   캐스팅하므로 0 이면 창이 `anchor` 에서 닫힌다.
                         #   즉 **첫 봉만** 진입 신호를 갖는다 = 상장당 1회.
                         #   1 로 두면 24시간 창이 되어 손절 후 재진입한다
                         #   (실측: 상장 8건에서 거래 12건). 일봉판은 상장당
                         #   1회이므로 그대로 두면 **다른 전략**을 비교하게 된다.
                         "entry_window_days": 0}}],
        "composer": {"type": "passthrough",
                     "kwargs": {"feature_col": "bnld_signal", "scale": 1.0}},
        "policy": {"type": "long_short_threshold",
                   "kwargs": {"entry_threshold": 0.5,
                              "sl_pct": sl,
                              "tp_pct": (1.0 if tp is None else tp),
                              "max_hold_bars": hold_h}},
        "config": {"eval_freq_minutes": 60, "forward_bars": hold_h},
    }
    ctx = SourceContext(symbol=item["symbol"], eval_freq_minutes=60,
                        ohlcv_1m=None, ohlcv_eval=item["bars"])
    bt = GenericBacktester(initial_capital=1_000_000.0, fee_rate=0.0005,
                           apply_fee_to_short=True)
    return bt.run_rule_based(pipeline=build_pipeline(ps, {}), ctx=ctx,
                             signal_lag_bars=1).trades


def stats(a: np.ndarray) -> dict:
    if len(a) < 2:
        return {"n": int(len(a))}
    se = a.std(ddof=1) / np.sqrt(len(a))
    return {"n": int(len(a)), "mean": float(a.mean()), "med": float(np.median(a)),
            "win": float(100 * (a > 0).mean()), "t": float(a.mean() / se) if se else None,
            "worst": float(a.min()), "total": float(a.sum())}


def main() -> int:
    p = argparse.ArgumentParser(description="신상저격수 1시간봉 백테스트")
    p.add_argument("--split", required=True, help="표본 밖 시작 상장일")
    p.add_argument("--since", default="2025-01-01")
    p.add_argument("--sl", default="0.08,0.10,0.15,0.20,0.30,0.50")
    p.add_argument("--tp", default="none,0.50")
    p.add_argument("--hold-days", type=int, default=30)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from app.db.session import engine
    with engine.connect() as conn:
        cohort = load_cohort(conn, a.since)
    if a.limit:
        cohort = cohort[:a.limit]
    if not cohort:
        raise SystemExit("코호트가 비었다 — ohlcv_hourly 적재를 확인하라")
    hold_h = a.hold_days * 24
    log.info("코호트 %d상장 · 봉/상장 중앙값 %d · 보유 %d시간",
             len(cohort), int(np.median([len(c["bars"]) for c in cohort])), hold_h)

    sls = [float(x) for x in a.sl.split(",")]
    tps = [None if x.strip().lower() == "none" else float(x)
           for x in a.tp.split(",")]
    split = a.split

    print("=" * 100)
    print(f"신상저격수 **1시간봉** — 상장 {len(cohort)}건 · 보유 {a.hold_days}일"
          f"({hold_h}봉) · 분할 {split} · 수수료 5bp")
    print("⚠ 진입 체결을 일봉판과 **동일 시각**(상장+24h)으로 맞췄다 — "
          "남는 차이는 손절·익절 판정 해상도뿐이다")
    print("=" * 100)
    print(f"  {'손절':>6}{'익절':>7} | {'IS거래':>7}{'IS평균%':>9}{'IS t':>7}"
          f"{'IS승률':>7}{'IS최악%':>9} | {'OOS거래':>8}{'OOS평균%':>10}{'OOS t':>7}"
          f" | {'손절체결':>9}{'익절체결':>9}{'시간':>6}")
    print("  " + "-" * 96)

    res = {}
    for sl in sls:
        for tp in tps:
            recs = []
            for c in cohort:
                try:
                    trades = run_one(c, sl, tp, hold_h)
                except Exception as exc:
                    log.warning("%s 실패: %s", c["symbol"], exc)
                    continue
                for t in (trades or []):
                    recs.append({"listing": c["listing"],
                                 "ret": float(t.return_pct) * 100,
                                 "reason": t.exit_reason,
                                 "split": "OOS" if c["listing"] >= split else "IS"})
            if not recs:
                continue
            d = pd.DataFrame(recs)
            si = stats(d.loc[d["split"] == "IS", "ret"].values)
            so = stats(d.loc[d["split"] == "OOS", "ret"].values)
            rc = d["reason"].value_counts().to_dict()
            key = f"sl{sl}/tp{tp}"
            res[key] = {"IS": si, "OOS": so, "reasons": rc}
            tpl = "없음" if tp is None else f"{tp:.0%}"
            print(f"  {sl:>6.0%}{tpl:>7} | {si.get('n',0):>7}"
                  f"{si.get('mean',float('nan')):>9.2f}{(si.get('t') or 0):>7.2f}"
                  f"{si.get('win',float('nan')):>7.1f}{si.get('worst',float('nan')):>9.1f}"
                  f" | {so.get('n',0):>8}{so.get('mean',float('nan')):>10.2f}"
                  f"{(so.get('t') or 0):>7.2f}"
                  f" | {rc.get('sl',0):>9}{rc.get('tp',0):>9}{rc.get('time',0):>6}")

    print("\n  " + "-" * 96)
    print("  읽는 법 — 일봉 격자는 손절을 조일수록 수익이 **단조 증가**했다")
    print("            (50%→2%: 2.63%→7.64%, t 0.96→7.28). 그게 인공물이었다면")
    print("            1h 에서는 **그 비탈이 사라지거나 뒤집혀야** 한다.")
    print("            손절체결 수가 손절폭에 따라 제대로 늘어나는지도 함께 보라 —")
    print("            일봉에서는 진입 바 무력화 때문에 그게 안 늘었다.")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"params": vars(a), "n_listings": len(cohort), "results": res},
        ensure_ascii=False, indent=2, default=str))
    print("=" * 100)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
