"""신상저격수 백테스트 — **정본(Canon) 커널로** 실행.

왜 새로 만드나
    같은 전략의 손익을 계산하는 코드가 연구 스크립트에 **6개** 따로 있었고 그중
    4개가 숏 수익률 규약을 틀리게 썼다(`진입/청산−1` 은 상한이 없어 이익 거래가
    부풀려진다). 2026-08-14 에 251 코호트 평균이 43.41% → 5.15%, t 5.73 → 1.74
    로 무너졌다.

    CANON·PA·REAL 은 커널 한 곳을 지나므로 서로 어긋나지 않는다. **BT 만 정본
    밖에 있어서 BT 만 계속 틀렸다.** 이 스크립트는 그 예외를 없앤다.

무엇이 달라지나
    · 공식이 한 곳 — 진입·청산·손절·수수료·수익률 전부 `kernel.step/close`
    · 골든 재생이 백테스트를 덮는다 — 규약 결함이 관문에서 걸린다
    · **BT↔CANON 격차가 구조적으로 0** 이 된다. 지금까지는 두 코드가 우연히
      같은 값을 낼 때만 0 이었다(DOSUSDT +0.04%p 는 운이었다)

정본과 같은 코드만 쓴다
    스펙   `lifecycle_session_spawner.build_session_spec`  ← CANON 세션과 동일
    조립   `pipeline_spec.build_pipeline`                  ← 동일
    실행   `backtester.GenericBacktester` (커널)           ← 동일

    스펙을 여기서 다시 쓰지 않는 것이 핵심이다. 교훈 #88 — 클래스만 고치고
    팩토리를 안 보면 인자가 조용히 버려진다.

코호트
    `lifecycle_variant_backtest.py` 와 같은 규칙 — `listing_dates.json` 의
    onboard_date 가 있고 상장 후 35일 창에 일봉 31개 이상. 비교가 목적이므로
    선별을 바꾸지 않는다.

사용:
  python3 -m scripts.research.lifecycle_canon_backtest --limit 20   # 빠른 확인
  python3 -m scripts.research.lifecycle_canon_backtest              # 전체
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
log = logging.getLogger("canon_bt")

LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT = ROOT / "runs" / "research_track" / "lifecycle_canon_backtest.json"

# (이름, baseline_hold_days, early_exit_check_day)
VARIANTS = [("base", 30, None), ("h21", 21, None),
            ("earlyexit_d7", 30, 7), ("earlyexit_d14", 30, 14)]

WINDOW_DAYS = 35
MIN_DAILY_BARS = 31


def daily_bars(conn, sym: str, a, b) -> pd.DataFrame:
    """1분봉 → 일봉. CANON 오케스트레이터와 같은 리샘플."""
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' AND timestamp >= :a AND timestamp < :b "
        "ORDER BY timestamp"), {"s": sym, "a": a, "b": b}).fetchall()
    if not r:
        return pd.DataFrame()
    df = pd.DataFrame(r, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    d = df.set_index("ts").astype(float)
    return pd.DataFrame({
        "open": d["open"].resample("1D").first(),
        "high": d["high"].resample("1D").max(),
        "low": d["low"].resample("1D").min(),
        "close": d["close"].resample("1D").last(),
        "volume": d["volume"].resample("1D").sum(),
    }).dropna()


def run_one(sym: str, ld, variant: str, hold: int, early, bars_1m, bars_daily):
    """한 상장 사건 × 한 변형 — 정본 커널로 실행. 거래 목록을 돌려준다."""
    from app.composer_framework.backtester import GenericBacktester
    from app.composer_framework.pipeline_spec import build_pipeline
    from app.composer_framework.signal_source import SourceContext
    from research.lifecycle_session_spawner import build_session_spec

    spec = build_session_spec(
        sym, str(ld),
        policy_variant=("baseline" if early is None else "early_exit"),
        early_exit_check_day=(early or 14),
        early_exit_vc_threshold=0.40,
        baseline_hold_days=hold,
    )
    ps = spec["pipeline_spec"]
    ctx = SourceContext(symbol=sym,
                        eval_freq_minutes=ps["config"]["eval_freq_minutes"],
                        ohlcv_1m=bars_1m, ohlcv_eval=bars_daily)
    pipeline = build_pipeline(ps, {})
    bt = GenericBacktester(
        initial_capital=float(spec["initial_capital"]),
        fee_rate=float(spec["fee_rate"]),
        apply_fee_to_short=True,          # 숏 수수료 — 2026-08-12 수정분
    )
    # 규칙 기반 전용 경로. `run_static` 은 학습/시험 분할이 상장일 진입을 잘라
    # 거래 0건을 만든다 — CANON 의 no-fit 경로와 같은 `run_rule_based` 를 쓴다.
    kpis = bt.run_rule_based(pipeline=pipeline, ctx=ctx)
    return kpis.trades


def stats(a: np.ndarray) -> dict:
    if len(a) < 2:
        return {"n": int(len(a))}
    se = a.std(ddof=1) / np.sqrt(len(a))
    return {"n": int(len(a)), "mean": float(a.mean()), "med": float(np.median(a)),
            "win": float(100 * (a > 0).mean()),
            "t": float(a.mean() / se) if se else float("nan")}


def main() -> int:
    p = argparse.ArgumentParser(description="신상저격수 백테스트 (정본 커널)")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--limit", type=int, default=0, help="앞에서 N 사건만 (빠른 확인)")
    a = p.parse_args()

    listings = json.load(open(LISTINGS))
    from app.db.session import engine

    rows, skipped, failed = [], 0, []
    with engine.connect() as conn:
        items = sorted(listings.items())
        for i, (sym, meta) in enumerate(items, 1):
            od = meta.get("onboard_date")
            if not od:
                continue
            ld = datetime.strptime(od, "%Y-%m-%d").date()
            dl = daily_bars(conn, sym, ld, ld + timedelta(days=WINDOW_DAYS))
            if len(dl) < MIN_DAILY_BARS:
                skipped += 1
                continue

            rec = {"symbol": sym, "listing": str(ld)}
            ok = True
            for name, hold, early in VARIANTS:
                try:
                    trades = run_one(sym, ld, name, hold, early, None, dl)
                except Exception as exc:
                    failed.append(f"{sym}/{name}: {type(exc).__name__}: {exc}")
                    ok = False
                    break
                # 진입 1회가 패러다임이다. 2회 이상이면 재진입 — 기록해 둔다.
                rec[f"{name}_n"] = len(trades)
                rec[f"{name}"] = (float(trades[0].return_pct) * 100
                                  if trades else None)
                rec[f"{name}_reason"] = trades[0].exit_reason if trades else None
            if ok:
                rows.append(rec)
            if a.limit and len(rows) >= a.limit:
                break
            if i % 50 == 0:
                log.info("%d/%d (사용 %d)", i, len(items), len(rows))

    out = {"cohort": len(rows), "skipped": skipped,
           "engine": "canon_kernel", "variants": {}}
    for name, _, _ in VARIANTS:
        v = np.array([r[name] for r in rows if r.get(name) is not None])
        out["variants"][name] = stats(v)
        reent = sum(1 for r in rows if (r.get(f"{name}_n") or 0) > 1)
        out["variants"][name]["reentry_events"] = reent
    out["rows"] = rows
    out["failed"] = failed[:20]

    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print("=" * 78)
    print(f"정본 커널 백테스트 — 코호트 {len(rows)} (제외 {skipped}, 실패 {len(failed)})")
    print("=" * 78)
    print(f"  {'변형':<15}{'n':>6}{'평균%':>10}{'중앙%':>10}{'승률%':>8}{'t':>8}{'재진입':>8}")
    for name, _, _ in VARIANTS:
        s = out["variants"][name]
        if "mean" not in s:
            print(f"  {name:<15}{s.get('n', 0):>6}   (표본 부족)")
            continue
        print(f"  {name:<15}{s['n']:>6}{s['mean']:>10.2f}{s['med']:>10.2f}"
              f"{s['win']:>8.1f}{s['t']:>8.2f}{s['reentry_events']:>8}")
    if failed:
        print("-" * 78)
        for f in failed[:5]:
            print(f"  실패: {f}")
    print("=" * 78)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
