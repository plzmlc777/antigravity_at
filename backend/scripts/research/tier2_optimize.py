"""2군 계열 파라미터 최적화 — 좌석/은퇴 세션의 스펙을 축으로 스윕.

1군(`lifecycle_optimize.py`)과 **같은 엔진·같은 표준**을 쓰되 대상이 다르다.

    1군   상장 사건 코호트를 훑는다 (사건마다 다른 종목·다른 창)
    2군   한 종목을 연속 구간에서 돌린다 (좌석 = 종목 × 전략)

    그래서 표본 안/밖 분할의 뜻도 다르다 — 1군은 **상장일 기준**, 2군은
    **시각 기준**이다.

스펙은 세션 파일에서 그대로 읽는다
    `session.json` 의 `pipeline_spec` 이 라이브가 쓰던 바로 그것이다. 여기서
    다시 조립하면 교훈 #88 — 인자가 조용히 버려져도 모른다.

⚠ `signal_lag_bars = 0`
    volume_burst 계열 소스는 **이미** 트리거를 다음 eval 봉에 부착한다
    (cd0ca27f). 여기서 또 밀면 두 번 밀린다. 1군은 반대로 1 이다(교훈 #90).

사용:
  python3 -m scripts.research.tier2_optimize --session 947cb3a0 --list-axes
  python3 -m scripts.research.tier2_optimize --session 947cb3a0 \\
      --split 2026-06-15 --days 150 \\
      --axis 'source.volume_percentile=98,99,99.5' \\
      --axis 'policy.long_threshold=0.3,0.5'
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tier2_optimize")

OUT_DIR = ROOT / "runs" / "research_track"
SIGNAL_LAG_BARS = 0        # 소스가 이미 부착한다 — 위 주석 참조
WARMUP_DAYS = 31           # 30일 롤링 기준선 (교훈 #90)


def find_session(prefix: str) -> dict:
    """세션 id 접두사로 찾는다. **은퇴 세션도 포함** — 리그에서 내려갔다고
    근거가 사라지는 것은 아니다."""
    from tier_governor import SESS_DIR  # type: ignore
    hits = []
    for d in sorted(glob.glob(os.path.join(SESS_DIR, "*"))):
        sj = os.path.join(d, "session.json")
        if not os.path.exists(sj):
            continue
        try:
            m = json.load(open(sj))
        except Exception:
            continue
        if str(m.get("session_id", "")).startswith(prefix):
            hits.append(m)
    if not hits:
        raise SystemExit(f"세션을 찾지 못했다: {prefix!r}")
    if len(hits) > 1:
        raise SystemExit(f"접두사가 모호하다 ({len(hits)}건): "
                         + ", ".join(h["session_id"] for h in hits[:5]))
    return hits[0]


def main() -> int:
    p = argparse.ArgumentParser(description="2군 계열 파라미터 최적화")
    p.add_argument("--session", required=True, help="세션 id 접두사")
    p.add_argument("--split", default="", help="표본 안/밖 분할 **날짜** (필수, --list-axes 제외)")
    p.add_argument("--days", type=int, default=150, help="평가 구간(오늘 기준 소급)")
    p.add_argument("--axis", action="append", default=[])
    p.add_argument("--out", default="")
    p.add_argument("--list-axes", action="store_true")
    a = p.parse_args()

    from research.sweep_engine import apply_all, describe, parse_axis
    from research.tier2_canon_backtest import load_ohlcv, resample

    meta = find_session(a.session)
    ps0 = meta["pipeline_spec"]
    sym = meta["symbol"]
    src = (ps0.get("sources") or [{}])[0].get("type", "?")
    log.info("좌석 %s · %s · %s · 상태 %s", meta["session_id"], sym, src,
             meta.get("status"))

    if a.list_axes:
        print(json.dumps(describe(ps0), ensure_ascii=False, indent=2))
        return 0
    if not a.split:
        raise SystemExit(
            "--split 은 필수다. 표본 밖 선언 없는 최적화는 과최적화 기계다 "
            "(설계 §9). 형식: --split 2026-06-15")

    axes: dict[str, list] = {}
    for spec in a.axis:
        k, v = parse_axis(spec)
        axes[k] = v
    if not axes:
        raise SystemExit("--axis 를 최소 하나 선언하라. 후보: --list-axes")

    names = list(axes)
    combos = list(product(*(axes[k] for k in names)))
    log.info("축 %s · 조합 %d칸 · 분할 %s", {k: len(v) for k, v in axes.items()},
             len(combos), a.split)

    # 사전 점검 — 오타 난 축이 거래 0건짜리 결과를 만들면 안 된다(교훈 #88)
    from app.composer_framework.pipeline_spec import build_pipeline
    for combo in combos:
        kw = dict(zip(names, combo))
        try:
            build_pipeline(apply_all(ps0, kw), {})
        except Exception as exc:
            raise SystemExit(f"사전 점검 실패 — {kw}\n  {type(exc).__name__}: {exc}\n"
                             f"  축 확인: --list-axes")
    log.info("사전 점검 통과 — %d칸 전부 조립됨", len(combos))

    from app.composer_framework.backtester import GenericBacktester
    from app.composer_framework.signal_source import SourceContext
    from app.db.session import engine
    from research.sweep_format import SweepWriter

    end = datetime.utcnow()
    start = end - timedelta(days=a.days)
    split_dt = datetime.fromisoformat(a.split)
    if not (start < split_dt < end):
        raise SystemExit(f"분할일 {a.split} 이 평가 구간 "
                         f"{start.date()}~{end.date()} 밖이다")

    ev = ps0.get("config", {}).get("eval_freq_minutes", 5)
    with engine.connect() as conn:
        df_1m = load_ohlcv(conn, sym, start - timedelta(days=WARMUP_DAYS), end)
    if df_1m.empty:
        raise SystemExit(f"{sym} 1분봉이 없다")
    df_eval = resample(df_1m, ev)
    df_eval = df_eval[df_eval.index >= start]

    w = SweepWriter(script="scripts/research/tier2_optimize.py",
                    engine="canon_kernel", root=ROOT, split_date=a.split,
                    axes=axes,
                    data_window={"start": str(start.date()), "end": str(end.date()),
                                 "symbol": sym, "source": src,
                                 "session_id": meta["session_id"]},
                    notes=(f"2군 좌석 스윕. signal_lag_bars={SIGNAL_LAG_BARS} "
                           f"(소스가 이미 다음 봉에 부착). 워밍업 {WARMUP_DAYS}일."))

    for combo in combos:
        kw = dict(zip(names, combo))
        ps = apply_all(ps0, kw)
        ctx = SourceContext(symbol=sym, eval_freq_minutes=ev,
                            ohlcv_1m=df_1m, ohlcv_eval=df_eval)
        bt = GenericBacktester(
            initial_capital=float(meta.get("initial_capital") or 1_000_000),
            fee_rate=float(meta.get("fee_rate") or 0.0004),
            apply_fee_to_short=True)
        try:
            trades = bt.run_rule_based(pipeline=build_pipeline(ps, {}), ctx=ctx,
                                       signal_lag_bars=SIGNAL_LAG_BARS).trades
        except Exception as exc:
            log.warning("%s 실패: %s", kw, exc)
            trades = []
        for side in ("IS", "OOS"):
            sel = [t for t in trades
                   if (t.exit_ts < split_dt) == (side == "IS")]
            arr = np.array([float(t.return_pct) * 100 for t in sel])
            w.add(axis_values=kw, metrics=_stats(arr), split=side)
        log.info("%s → 거래 %d", kw, len(trades))

    out = a.out or str(OUT_DIR / f"tier2_optimize_{meta['session_id'][:12]}.json")
    d = w.write(out)

    print("=" * 92)
    print(f"2군 최적화 — {sym} · {src} · {len(combos)}칸 · 분할 {a.split}")
    print("=" * 92)
    hdr = "".join(f"{k.split('.')[-1]:>16}" for k in names)
    print(f"  {hdr}{'IS 거래':>8}{'IS 총%p':>10}{'IS t':>7}"
          f"{'OOS 거래':>9}{'OOS 총%p':>10}{'OOS t':>7}")
    rows = {(r["split"], tuple(r[k] for k in names)): r for r in d["results"]}
    for combo in sorted(combos, key=lambda c: -(rows.get(("IS", c), {}).get("total_ret") or 0)):
        i_, o_ = rows.get(("IS", combo), {}), rows.get(("OOS", combo), {})
        print(f"  {''.join(f'{str(v):>16}' for v in combo)}"
              f"{i_.get('n_trades', 0):>8}{i_.get('total_ret', 0):>10.1f}"
              f"{(i_.get('t') or 0):>7.2f}{o_.get('n_trades', 0):>9}"
              f"{o_.get('total_ret', 0):>10.1f}{(o_.get('t') or 0):>7.2f}")
    print("-" * 92)
    print(f"  고원 판정: python3 -m scripts.research.plateau_select --file {out}")
    print("=" * 92)
    return 0


def _stats(a: np.ndarray) -> dict:
    if len(a) == 0:
        return {"n_trades": 0}
    if len(a) < 2:
        return {"n_trades": 1, "total_ret": float(a.sum()), "mean": float(a[0]),
                "worst": float(a[0])}
    se = a.std(ddof=1) / np.sqrt(len(a))
    return {"n_trades": int(len(a)), "total_ret": float(a.sum()),
            "mean": float(a.mean()), "med": float(np.median(a)),
            "win": float(100 * (a > 0).mean()),
            "t": float(a.mean() / se) if se else None,
            "worst": float(a.min()), "std": float(a.std(ddof=1))}


if __name__ == "__main__":
    sys.exit(main())
