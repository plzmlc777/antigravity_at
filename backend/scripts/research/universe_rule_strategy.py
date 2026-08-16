"""**분산 무차별 숏** — 새 전략 후보의 첫 검정.

신상저격수와 무관하다
    신상저격수는 신규 상장 전용으로 그대로 둔다(실계좌가 그 위에 있다).
    이건 **별개 전략**이다 — 유동성 통과 종목 전체에 손절·익절·보유 규칙을
    무차별로 걸고 분산으로 먹는다.

왜 이 방향인가
    2026-08-15 에 대상 선택이 두 번 기각됐다 — 종목 선별(rho -0.058) ·
    성질 선별(6종 전부 실패). 그런데 **규칙 자체는 살아 있다.** 위약 대조 실측:

        규칙 없이 30일 숏   신규 -8.80%  기성 -0.17%
        규칙 얹으면         신규 +2.24%  기성 **+6.13%**

    손절이 왼쪽 꼬리를 자르고 익절이 이익을 확정한다. 그게 변동성 큰 알트
    전반에 통한다면, 고를 필요 없이 **전부 걸고 분산**하면 된다.

첫 질문 — 방향성 베팅인가 규칙 효과인가
    ⚠ 이게 갈림길이다. 숏이 벌었다면 두 가지 설명이 있다:
      (a) 알트가 내려갔다 → **방향성 베팅**. 시장이 돌면 죽는다
      (b) 규칙의 비대칭이 벌었다 → **규칙 효과**. 방향과 무관할 수 있다

    가르는 법: **같은 규칙을 롱으로 뒤집어** 돌린다.
      숏만 벌고 롱이 지면      → (a) 방향성
      숏도 롱도 벌면            → (b) 규칙 (또는 측정 오류)
      숏이 벌고 롱이 덜 지면   → 둘의 혼합

    교훈 #85 의 위약 정신과 같다 — 사건이 아니라 **방향**에 대한 대조군이다.

사용:
  python3 -m scripts.research.universe_rule_strategy --split 2026-02-01
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
log = logging.getLogger("uni_rule")

OUT = ROOT / "runs" / "research_track" / "universe_rule_strategy.json"


def run_side(sym: str, anchor, bars, sl: float, tp: float, hold: int, side: str,
             spec_sink: dict | None = None):
    """한 앵커 — `side` 방향으로 규칙 적용. 정본 커널.

    롱 대조군은 `long_short_threshold` 정책으로 만든다. 신상저격수 정책은
    숏 전용이라(`policy_no_long`) 롱을 못 낸다.
    """
    from app.composer_framework.backtester import GenericBacktester
    from app.composer_framework.pipeline_spec import build_pipeline
    from app.composer_framework.signal_source import SourceContext
    from research.lifecycle_session_spawner import build_session_spec
    from research.sweep_engine import apply_all

    spec = build_session_spec(sym, str(anchor), policy_variant="baseline",
                              baseline_hold_days=hold)
    ps = apply_all(spec["pipeline_spec"], {
        "policy.sl_pct": sl,
        "policy.tp_pct": (1.0 if tp is None else tp),
        "policy.max_hold_bars": hold,
        "source.entry_window_days": 1,
        "source.max_age_days": hold + 5,
    })
    if side == "long":
        # 소스는 -1.0(숏)을 내므로 컴포저 scale 을 뒤집어 +1.0(롱)으로 만든다.
        # **같은 봉·같은 규칙·반대 방향** 이어야 대조가 성립한다.
        ps = dict(ps)
        ps["composer"] = {**ps.get("composer", {}),
                          "kwargs": {**(ps.get("composer", {}).get("kwargs") or {}),
                                     "scale": -1.0}}
        # LongShortThresholdPolicy 는  하나만 받는다
        # (long_threshold/short_threshold 가 아니다 — 2026-08-15 에 그걸로 롱
        #  대조군이 0건 나왔다. 사전 점검이 없는 경로라 조용히 지나갔다)
        ps["policy"] = {"type": "long_short_threshold",
                        "kwargs": {"entry_threshold": 0.5,
                                   "sl_pct": sl,
                                   "tp_pct": (1.0 if tp is None else tp),
                                   "max_hold_bars": hold}}
    # ⚠ 조립된 스펙을 **밖으로 내보낸다** — 호출자가 "내가 넣은 값이 정말
    #   들어갔는가"를 확인할 수 있어야 한다. 교훈 #88 은 정확히 이걸 안 해서
    #   생겼다(설정에 넣은 값이 팩토리에서 사라져 한 번도 안 걸림).
    if spec_sink is not None:
        spec_sink.clear()
        spec_sink.update(ps)
    ctx = SourceContext(symbol=sym, eval_freq_minutes=1440,
                        ohlcv_1m=None, ohlcv_eval=bars)
    bt = GenericBacktester(initial_capital=1_000_000.0,
                           fee_rate=float(spec["fee_rate"]),
                           apply_fee_to_short=True)
    return bt.run_rule_based(pipeline=build_pipeline(ps, {}), ctx=ctx,
                             signal_lag_bars=1).trades


def stats(a: np.ndarray) -> dict:
    if len(a) < 2:
        return {"n": int(len(a))}
    se = a.std(ddof=1) / np.sqrt(len(a))
    t = float(a.mean() / se) if se else None
    return {"n": int(len(a)), "total": float(a.sum()), "mean": float(a.mean()),
            "med": float(np.median(a)), "win": float(100 * (a > 0).mean()),
            "t": t, "worst": float(a.min()), "std": float(a.std(ddof=1))}


def main() -> int:
    p = argparse.ArgumentParser(description="분산 무차별 규칙 전략 검정")
    p.add_argument("--split", required=True)
    p.add_argument("--sl", type=float, default=0.2)
    p.add_argument("--tp", type=float, default=0.3)
    p.add_argument("--hold", type=int, default=30)
    p.add_argument("--sides", default="short,long",
                   help="short 만 재면 방향성/규칙을 못 가른다 — 기본은 둘 다")
    p.add_argument("--min-dollar-vol", type=float, default=1_000_000)
    p.add_argument("--min-days", type=int, default=120)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from app.db.session import engine
    from research.short_universe_scan import full_daily, universe

    split_date = datetime.fromisoformat(a.split).date()
    sides = [x.strip() for x in a.sides.split(",") if x.strip()]
    with engine.connect() as c0:
        uni = universe(c0, a.min_dollar_vol, a.min_days)
    if a.limit:
        uni = uni[:a.limit]
    log.info("유동성 통과 %d종목 · 방향 %s · 손절 %.0f%% · 익절 %.0f%% · 보유 %d일",
             len(uni), sides, a.sl * 100, a.tp * 100, a.hold)

    recs = []
    with engine.connect() as conn:
        for i, u in enumerate(uni, 1):
            sym = u["symbol"]
            bars = full_daily(conn, sym)
            if len(bars) < a.hold + 40:
                continue
            d0, d1 = bars.index[0].date(), bars.index[-1].date()
            anchor = d0 + timedelta(days=30)
            while anchor <= d1 - timedelta(days=a.hold + 2):
                seg = bars[(bars.index.date >= anchor)
                           & (bars.index.date <= anchor + timedelta(days=a.hold + 5))]
                if len(seg) >= a.hold - 2:
                    for side in sides:
                        try:
                            trades = run_side(sym, anchor, seg, a.sl, a.tp,
                                              a.hold, side)
                        except Exception:
                            trades = []
                        for t in trades:
                            recs.append({
                                "symbol": sym, "anchor": anchor, "side": side,
                                "actual_side": t.side,
                                "ret": float(t.return_pct) * 100,
                                "reason": t.exit_reason,
                                "split": "OOS" if anchor >= split_date else "IS"})
                anchor += timedelta(days=a.hold)     # 겹치지 않는 앵커
            if i % 40 == 0:
                log.info("%d/%d · 표본 %d", i, len(uni), len(recs))

    if not recs:
        raise SystemExit("표본이 없다")
    df = pd.DataFrame(recs)

    res = {}
    for side in sides:
        for sp in ("IS", "OOS"):
            m = (df["side"] == side) & (df["split"] == sp)
            res[f"{side}/{sp}"] = stats(df.loc[m, "ret"].values)
        m = df["side"] == side
        rc = df.loc[m, "reason"].value_counts().to_dict()
        res[f"{side}/reasons"] = {k: int(v) for k, v in rc.items()}
        res[f"{side}/actual_sides"] = {
            k: int(v) for k, v in df.loc[m, "actual_side"].value_counts().items()}

    out = {"params": {"sl": a.sl, "tp": a.tp, "hold": a.hold, "split": a.split,
                      "sides": sides, "min_dollar_vol": a.min_dollar_vol},
           "n_samples": len(df), "results": res}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))

    print("=" * 88)
    print(f"분산 무차별 규칙 전략 — 표본 {len(df)} · 손절 {a.sl:.0%} · "
          f"익절 {a.tp:.0%} · 보유 {a.hold}일 · 분할 {a.split}")
    print("=" * 88)
    print(f"  {'방향':<8}{'구간':<6}{'n':>7}{'총%p':>10}{'평균%':>9}"
          f"{'중앙%':>9}{'승률%':>8}{'t':>8}{'최악%':>9}")
    for side in sides:
        for sp in ("IS", "OOS"):
            s = res[f"{side}/{sp}"]
            if "mean" not in s:
                print(f"  {side:<8}{sp:<6}{s.get('n',0):>7}   (표본 부족)")
                continue
            print(f"  {side:<8}{sp:<6}{s['n']:>7}{s['total']:>10.0f}{s['mean']:>9.2f}"
                  f"{s['med']:>9.2f}{s['win']:>8.1f}{(s['t'] or 0):>8.2f}"
                  f"{s['worst']:>9.1f}")
    print("-" * 88)
    for side in sides:
        print(f"  {side} 청산 사유: {res[f'{side}/reasons']} · "
              f"실제 방향: {res[f'{side}/actual_sides']}")
    print("-" * 88)

    # ── 판정 ──
    sm = res.get("short/IS", {}).get("mean")
    lm = res.get("long/IS", {}).get("mean")
    so = res.get("short/OOS", {}).get("mean")
    lo = res.get("long/OOS", {}).get("mean")
    if sm is not None and lm is not None:
        print("  **방향성인가 규칙인가**")
        print(f"     표본 안  숏 {sm:+.2f}% · 롱 {lm:+.2f}%  → 합 {sm+lm:+.2f}%")
        if so is not None and lo is not None:
            print(f"     표본 밖  숏 {so:+.2f}% · 롱 {lo:+.2f}%  → 합 {so+lo:+.2f}%")
        if sm > 0 and lm < 0:
            print("     → 숏만 번다. **방향성 베팅**이다 — 시장이 돌면 죽는다")
        elif sm > 0 and lm > 0:
            print("     → 양쪽 다 번다. 같은 봉에서 둘 다 이길 수는 없으므로")
            print("        **규칙의 비대칭**이거나 **측정 오류**다. 반드시 확인하라")
        else:
            print("     → 숏이 못 번다. 이 방향은 닫힌다")
    print("=" * 88)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
