"""신상저격수 파라미터 최적화 — 범용 축 스윕, 표본 밖 분할 **필수**.

설계 근거 `.claude/plans/param_sweep_heatmap_component.md`
표준 형식 `scripts/research/sweep_format.py`

무엇이 MT5 에서 왔나
    MT5 Strategy Tester 는 최적화 UI 에 **Forward 기간을 내장**한다. 표본 밖을
    떼어놓지 않고는 최적화를 시작할 수 없다. 그게 이 스크립트가 `--split` 을
    필수 인자로 두는 이유다.

    2026-08-14 실측이 그 필요를 증명했다. 익절 20칸 격자에서 IS 최고였던
    `d7@tp50/w3`(1338%p, t 2.19)이 표본 밖에서 **-11.4%p** 로 뒤집혔고,
    IS 중위였던 `d14@tp50/w7` 이 표본 밖 1위였다. 분할이 선택 사항이었으면
    그대로 채택했을 것이다.

    반대로 **유전 알고리즘은 들이지 않는다.** 우리 격자는 수십~수백 칸이라
    전수로 충분하고, 확률적 탐색은 교훈 #87(LGBM 세션 재현 불가)과 같은 병을
    새로 들인다. 재현 가능한 전수 탐색이 낫다.

축
    sl       손절 %. **2026-08-14 에 처음 열렸다.** 그전까지 0.50 고정이라
             익절 격자에서 최악 거래가 전 칸 -50.1% 였다 — 축을 안 열면
             위험 쪽은 탐색 자체가 안 된다.
    tp       익절 %. `none` = 없음(현행)
    window   재진입 창(상장 후 일수). 개정된 패러다임 정의가 여는 자유도
    variant  base / h21 / earlyexit_d7 / earlyexit_d14 / bearskip

사용:
  python3 -m scripts.research.lifecycle_optimize \\
      --split 2026-05-13 \\
      --axis variant=base,earlyexit_d7,bearskip \\
      --axis sl=0.3,0.5,0.7 \\
      --axis tp=none,30,50 \\
      --axis window=3,7
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lc_optimize")

OUT = ROOT / "runs" / "research_track" / "lifecycle_optimize.json"

VARIANT_SPEC = {                       # 이름 → (보유일, 조기청산일, 정책)
    "base": (30, None, "baseline"),
    "h21": (21, None, "baseline"),
    "earlyexit_d7": (30, 7, "early_exit"),
    "earlyexit_d14": (30, 14, "early_exit"),
    "bearskip": (30, None, "bear_skip"),
}

DEFAULT_AXES = {
    "variant": ["base", "earlyexit_d7", "bearskip"],
    "sl": [0.3, 0.5, 0.7],
    "tp": ["none", 30, 50],
    "window": [3, 7],
}


def parse_axis(spec: str) -> tuple[str, list]:
    """`sl=0.3,0.5,0.7` → ("sl", [0.3, 0.5, 0.7]). 숫자로 읽히면 숫자로."""
    if "=" not in spec:
        raise SystemExit(f"--axis 형식은 이름=값,값 이다: {spec!r}")
    name, raw = spec.split("=", 1)
    vals = []
    for x in raw.split(","):
        x = x.strip()
        if not x:
            continue
        try:
            vals.append(int(x) if "." not in x else float(x))
        except ValueError:
            vals.append(x)
    if not vals:
        raise SystemExit(f"--axis 값이 비었다: {spec!r}")
    return name.strip(), vals


def stats(a: np.ndarray) -> dict:
    if len(a) == 0:
        return {"n_trades": 0}
    if len(a) < 2:
        return {"n_trades": int(len(a)), "total_ret": float(a.sum()),
                "mean": float(a[0]), "worst": float(a[0])}
    se = a.std(ddof=1) / np.sqrt(len(a))
    return {
        "n_trades": int(len(a)),
        "total_ret": float(a.sum()),
        "mean": float(a.mean()),
        "med": float(np.median(a)),
        "win": float(100 * (a > 0).mean()),
        "t": float(a.mean() / se) if se else None,
        "worst": float(a.min()),
        "std": float(a.std(ddof=1)),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="신상저격수 파라미터 최적화")
    p.add_argument("--split", required=True,
                   help="표본 안/밖 분할 상장일 (필수). 이 날 **이후** 상장이 표본 밖")
    p.add_argument("--axis", action="append", default=[],
                   help="축 선언. 예 sl=0.3,0.5,0.7 · 반복 가능")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--limit", type=int, default=0, help="앞에서 N 사건만")
    a = p.parse_args()

    from research.lifecycle_canon_backtest import (  # noqa: E402
        LISTINGS, MIN_DAILY_BARS, WINDOW_DAYS, daily_bars, run_one,
    )
    from research.sweep_format import SweepWriter  # noqa: E402

    axes = dict(DEFAULT_AXES)
    for spec in a.axis:
        k, v = parse_axis(spec)
        axes[k] = v
    for k in list(axes):
        if k not in ("variant", "sl", "tp", "window"):
            raise SystemExit(f"모르는 축: {k}. 가능: variant/sl/tp/window")
    for v in axes.get("variant", []):
        if v not in VARIANT_SPEC:
            raise SystemExit(f"모르는 변형: {v}. 가능: {sorted(VARIANT_SPEC)}")

    names = list(axes)
    combos = list(product(*(axes[k] for k in names)))
    log.info("축 %s · 조합 %d칸 · 분할 %s", {k: len(v) for k, v in axes.items()},
             len(combos), a.split)

    listings = json.load(open(LISTINGS))
    from app.db.session import engine

    # (조합 키) → {"IS": [수익률...], "OOS": [...]}
    bucket: dict[tuple, dict[str, list]] = {c: {"IS": [], "OOS": []} for c in combos}
    n_events = {"IS": 0, "OOS": 0}
    win_lo, win_hi = None, None

    with engine.connect() as conn:
        items = sorted(listings.items())
        used = 0
        for i, (sym, meta) in enumerate(items, 1):
            od = meta.get("onboard_date")
            if not od:
                continue
            ld = datetime.strptime(od, "%Y-%m-%d").date()
            dl = daily_bars(conn, sym, ld, ld + timedelta(days=WINDOW_DAYS))
            if len(dl) < MIN_DAILY_BARS:
                continue
            used += 1
            side = "OOS" if od >= a.split else "IS"
            n_events[side] += 1
            win_lo = od if win_lo is None or od < win_lo else win_lo
            win_hi = od if win_hi is None or od > win_hi else win_hi

            for combo in combos:
                kw = dict(zip(names, combo))
                hold, early, pv = VARIANT_SPEC[kw["variant"]]
                try:
                    trades = run_one(sym, ld, kw["variant"], hold, early, pv,
                                     None, dl, kw.get("tp", "none"),
                                     kw.get("window"), kw.get("sl"))
                except Exception as exc:
                    log.warning("%s %s 실패: %s", sym, kw, exc)
                    continue
                if not trades:          # bearskip 억제 또는 진입 없음 = 표본 밖
                    continue
                bucket[combo][side].extend(float(t.return_pct) * 100
                                           for t in trades)
            if a.limit and used >= a.limit:
                break
            if i % 100 == 0:
                log.info("%d/%d (사용 %d)", i, len(items), used)

    w = SweepWriter(
        script="scripts/research/lifecycle_optimize.py",
        engine="canon_kernel", root=ROOT, split_date=a.split, axes=axes,
        data_window={"start": win_lo, "end": win_hi,
                     "is_events": n_events["IS"], "oos_events": n_events["OOS"]},
        notes=("표본 밖 = 분할일 이후 상장. 지표는 **거래 기준**(재진입 포함). "
               "total_ret 은 거래별 수익률의 합(%p, 복리 아님)."))
    for combo in combos:
        kw = dict(zip(names, combo))
        for side in ("IS", "OOS"):
            w.add(axis_values=kw, metrics=stats(np.array(bucket[combo][side])),
                  split=side)
    d = w.write(a.out)

    # ── 요약 ──
    print("=" * 92)
    print(f"신상저격수 최적화 — {len(combos)}칸 · 분할 {a.split} "
          f"(IS 사건 {n_events['IS']} / OOS 사건 {n_events['OOS']})")
    print("=" * 92)
    hdr = "".join(f"{k:>10}" for k in names)
    print(f"  {hdr}{'IS 거래':>8}{'IS 총%p':>10}{'IS t':>7}"
          f"{'OOS 거래':>9}{'OOS 총%p':>10}{'OOS 평균':>9}{'OOS t':>7}")
    rows = {(r["split"], tuple(r[k] for k in names)): r for r in d["results"]}
    for combo in sorted(combos, key=lambda c: -(rows.get(("IS", c), {}).get("total_ret") or 0)):
        i_, o_ = rows.get(("IS", combo), {}), rows.get(("OOS", combo), {})
        vals = "".join(f"{str(v):>10}" for v in combo)
        print(f"  {vals}{i_.get('n_trades', 0):>8}{i_.get('total_ret', 0):>10.0f}"
              f"{(i_.get('t') or 0):>7.2f}{o_.get('n_trades', 0):>9}"
              f"{o_.get('total_ret', 0):>10.1f}{(o_.get('mean') or 0):>9.2f}"
              f"{(o_.get('t') or 0):>7.2f}")
    print("-" * 92)
    print("  IS 총%p 내림차순. **IS 최고를 채택하지 마라** — 고원 판정을 거쳐라:")
    print("    python3 -m scripts.research.plateau_select --file", a.out)
    print("=" * 92)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
