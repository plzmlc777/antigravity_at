"""국면 지속성 — **탐지기를 만들기 전에 반드시 먼저 재야 하는 것**.

왜 이걸 먼저 재나
    "신상저격수의 수익이 국면 덕이라면 국면이 돌 때 감지할 수 없나"에
    답하려면 순서가 있다.

        예측 — 국면이 돌 것을 **미리** 안다  → 열 번 실패한 그 문제다
        탐지 — 국면이 돌았다는 걸 **빨리** 안다 → 다른 문제다

    탐지는 예측보다 쉽지만 **공짜가 아니다.** 탐지기는 늘 한 발 늦는다.
    국면이 오래 가면 늦어도 남는 게 있고, 주 단위로 뒤집히면 아무 소용 없다.

    **그러니 지속성부터 재고, 없으면 거기서 멈춘다.** 탐지기를 먼저 만들면
    표본 안에서는 반드시 좋아 보인다(문턱을 관측된 손실에 맞추므로).

무엇을 재나
    1. 자기상관 — 이번 기간이 좋았으면 다음도 좋은가
    2. 부호 런 길이 — 좋은 국면이 몇 기간 연속되나 (무작위 대비)
    3. **결정적**: 직전 성과가 다음 성과를 가르는가 (이게 곧 탐지기의 상한이다)

⚠ 규칙은 실거래 그대로다
    `universe_rule_strategy.run_side` 를 재사용한다. 손절 50% · 익절 없음 ·
    보유 30일 — 민트 실거래 세션 spec 의 `sl_pct=0.5 / tp_pct=1.0` 과 같다.
    여기서 규칙이 어긋나면 잰 것이 실거래의 국면이 아니게 된다.

⚠ 겹치면 안 된다
    앵커 간격 = 보유기간. 겹치면 인접 기간이 같은 봉을 공유해서
    자기상관이 **가짜로** 생긴다. 그게 바로 [[feedback-overlapping-window-persistence-artifact]]
    에서 r +0.470 → +0.001 로 무너진 그 함정이다.

사용:
  python3 -m scripts.research.regime_persistence_scan --split 2026-02-01
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
log = logging.getLogger("regime")

OUT = ROOT / "runs" / "research_track" / "regime_persistence_scan.json"
# --side 별로 파일을 나눈다

MIN_SYMS_PER_ANCHOR = 8     # 이보다 적으면 그 기간은 대표성이 없다


def acf(x: np.ndarray, lag: int) -> float:
    if len(x) <= lag + 2:
        return float("nan")
    a, b = x[:-lag], x[lag:]
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def runs(sign: np.ndarray) -> tuple[float, int]:
    """평균 런 길이와 런 개수."""
    if len(sign) < 2:
        return float("nan"), 0
    n_runs = 1 + int((sign[1:] != sign[:-1]).sum())
    return len(sign) / n_runs, n_runs


def main() -> int:
    p = argparse.ArgumentParser(description="국면 지속성")
    p.add_argument("--split", required=True)
    p.add_argument("--sl", type=float, default=0.5)      # 실거래 값
    p.add_argument("--tp", type=float, default=1.0)      # 1.0 = 익절 없음
    p.add_argument("--hold", type=int, default=30)
    # ⚠ 방향 대조(교훈 #91) — 롱에서도 같은 갈림이 나오면 그건 숏
    #   전략의 국면이 아니라 **시장 전체의 자기상관**이다.
    p.add_argument("--side", choices=["short", "long"],
                   default="short")
    p.add_argument("--min-dollar-vol", type=float, default=1_000_000)
    p.add_argument("--min-days", type=int, default=120)
    p.add_argument("--reps", type=int, default=2000, help="뒤섞기 반복")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default="")
    a = p.parse_args()

    if not a.out:
        a.out = str(OUT).replace(".json", f"_{a.side}.json")
    from app.db.session import engine
    from research.short_universe_scan import full_daily, universe
    from research.universe_rule_strategy import run_side

    split = pd.Timestamp(datetime.fromisoformat(a.split))
    tp = None if a.tp >= 1.0 else a.tp

    with engine.connect() as conn:
        syms = universe(conn, a.min_dollar_vol, a.min_days)
        if a.limit:
            syms = syms[:a.limit]
        log.info("유동성 통과 %d종목 · 손절 %.0f%% · 익절 %s · 보유 %d일",
                 len(syms), a.sl * 100, "없음" if tp is None else f"{tp:.0%}",
                 a.hold)
        bars_by = {}
        for s in syms:
            sym = s["symbol"] if isinstance(s, dict) else s
            try:
                b = full_daily(conn, sym)
            except Exception:
                continue
            if b is not None and len(b) > a.hold + 5:
                bars_by[sym] = b

    log.info("일봉 확보 %d종목", len(bars_by))
    if not bars_by:
        raise SystemExit("일봉이 없다")

    # ⚠ `run_side` 는 **앵커 구간만** 받아야 한다. 전체 일봉을 넘기면 소스의
    #   `max_age_days` 가 걸러 거래가 **0건**이 된다(첫 실행에서 그랬다).
    #   그리고 거래는 dict 가 아니라 **객체**다 — `t.return_pct`(비율).
    #   `universe_rule_strategy.main` 의 루프 구조를 그대로 따른다.
    raw = []
    for i, (sym, bars) in enumerate(bars_by.items(), 1):
        if len(bars) < a.hold + 40:
            continue
        d0, d1 = bars.index[0].date(), bars.index[-1].date()
        anchor = d0 + timedelta(days=30)
        while anchor <= d1 - timedelta(days=a.hold + 2):
            seg = bars[(bars.index.date >= anchor)
                       & (bars.index.date <= anchor + timedelta(days=a.hold + 5))]
            if len(seg) >= a.hold - 2:
                try:
                    trades = run_side(sym, anchor, seg, a.sl, tp, a.hold, a.side)
                except Exception:
                    trades = []
                for t in (trades or []):
                    raw.append({"anchor": pd.Timestamp(anchor), "symbol": sym,
                                "ret": float(t.return_pct) * 100})
            anchor += timedelta(days=a.hold)      # 겹치지 않는 앵커
        if i % 40 == 0:
            log.info("  %d/%d 종목 · 거래 %d", i, len(bars_by), len(raw))

    if not raw:
        raise SystemExit("거래가 0건이다 — 구간/규칙을 확인하라")
    rw = pd.DataFrame(raw)
    # ⚠ 종목마다 상장일이 달라 앵커 날짜가 흩어진다. **월 단위로 묶어야**
    #   같은 기간의 종목들이 한 관측이 된다(그러지 않으면 기간마다 1종목).
    rw["period"] = rw["anchor"].dt.to_period("M").dt.to_timestamp()
    g = rw.groupby("period")["ret"]
    d = pd.DataFrame({"anchor": g.mean().index, "n": g.size().values,
                      "mean": g.mean().values, "med": g.median().values,
                      "win": g.apply(lambda x: 100 * (x > 0).mean()).values})
    d = d[d["n"] >= MIN_SYMS_PER_ANCHOR].reset_index(drop=True)
    log.info("거래 %d건 → 유효 기간 %d개", len(rw), len(d))

    if len(d) < 12:
        raise SystemExit(f"유효 기간이 {len(d)}개뿐이다 — 지속성을 못 잰다")
    d["split"] = np.where(d["anchor"] >= split, "OOS", "IS")
    r = d["mean"].to_numpy()

    print("=" * 92)
    print(f"국면 지속성 — 비겹침 기간 {len(d)}개 · 종목/기간 중앙값 "
          f"{int(d['n'].median())} · {d['anchor'].min().date()} ~ "
          f"{d['anchor'].max().date()}")
    print(f"규칙 = **실거래 그대로** 손절 {a.sl:.0%} · "
          f"익절 {'없음' if tp is None else f'{tp:.0%}'} · 보유 {a.hold}일 "
          f"({'숏' if a.side == 'short' else '롱 — 방향 대조'})")
    print("=" * 92)

    print(f"\n  기간별 숏 수익 — 평균 {r.mean():+.3f}% · 표준편차 {r.std(ddof=1):.3f}"
          f" · 양수 {int((r>0).sum())}/{len(r)}")

    # ── 1. 자기상관 ───────────────────────────────────────────────────
    print("\n【1】 자기상관 — 이번 기간이 좋았으면 다음도 좋은가")
    rng = np.random.default_rng(a.seed)
    res: dict = {"n_periods": len(d), "mean": float(r.mean())}
    print(f"  {'시차':>4}{'상관':>9}{'위약 p95':>11}{'경험 p':>9}")
    for lag in (1, 2, 3):
        obs = acf(r, lag)
        null = np.array([acf(rng.permutation(r), lag) for _ in range(a.reps)])
        pv = float(np.mean(np.abs(null) >= abs(obs)))
        res[f"acf{lag}"] = {"obs": obs, "p": pv}
        print(f"  {lag:>4}{obs:>+9.3f}{np.percentile(np.abs(null),95):>11.3f}"
              f"{pv:>9.3f}" + ("   **없다**" if pv > 0.05 else "   ★ 있다"))

    # ── 2. 런 길이 ────────────────────────────────────────────────────
    sign = (r > 0).astype(int)
    obs_run, n_runs = runs(sign)
    null_runs = np.array([runs(rng.permutation(sign))[0] for _ in range(a.reps)])
    pv_run = float(np.mean(null_runs >= obs_run))
    res["run_len"] = {"obs": obs_run, "null_mean": float(null_runs.mean()),
                      "p": pv_run}
    print(f"\n【2】 부호 런 — 좋은 국면이 몇 기간 연속되나")
    print(f"  관측 평균 런 {obs_run:.2f}기간 ({n_runs}런) · "
          f"무작위 {null_runs.mean():.2f} · 경험 p {pv_run:.3f}"
          + ("   **무작위와 같다**" if pv_run > 0.05 else "   ★ 뭉쳐 있다"))

    # ── 3. 결정적 — 직전 성과가 다음을 가르는가 ───────────────────────
    #
    # ⚠ 이것이 **탐지기 성능의 상한**이다. 여기서 안 갈리면 어떤 탐지기도
    #   작동할 수 없다 — 탐지기가 볼 수 있는 것이 직전 성과뿐이기 때문이다.
    print("\n【3】 직전 성과로 다음 기간이 갈리는가 — **탐지기의 상한**")
    print(f"  {'조건':<22}{'기간':>6}{'다음기간 평균%':>14}{'승률%':>8}{'t':>8}")
    print("  " + "-" * 60)
    prev, nxt = r[:-1], r[1:]
    detect = {}
    for lab, m in (("직전 > 0 (계속)", prev > 0),
                   ("직전 ≤ 0 (쉼)", prev <= 0),
                   ("직전 2기간 합 > 0", None),
                   ("직전 2기간 합 ≤ 0", None)):
        if m is None:
            if len(r) < 4:
                continue
            s2 = r[:-2] + r[1:-1]
            m2 = (s2 > 0) if "> 0" in lab else (s2 <= 0)
            v = r[2:][m2]
        else:
            v = nxt[m]
        if len(v) < 5:
            print(f"  {lab:<22}{len(v):>6}   표본 부족")
            continue
        se = v.std(ddof=1) / np.sqrt(len(v))
        t = float(v.mean() / se) if se > 0 else 0.0
        detect[lab] = {"n": len(v), "mean": float(v.mean()),
                       "win": float(100 * (v > 0).mean()), "t": t}
        print(f"  {lab:<22}{len(v):>6}{v.mean():>14.3f}"
              f"{100*(v>0).mean():>8.1f}{t:>8.2f}")
    res["detector_ceiling"] = detect

    # ── 갈림 폭 — **세 겹으로** 검정한다 ──────────────────────────────
    #
    # ⚠ 1회차에서 1기간 갈림이 p 0.026 으로 나왔다. 그대로 채택하면 안 되는
    #   이유가 셋이었고, 셋 다 여기서 막는다:
    #     ① 표본 안/밖을 안 갈랐다        → IS·OOS 따로 낸다
    #     ② 2기간 판본은 갈림이 없었다     → 내적 일관성으로 함께 본다
    #     ③ 통계를 9개 재고 하나를 골랐다  → **최대통계량**(교훈 #95)
    def gap_of(x: np.ndarray, k: int) -> float | None:
        """직전 k기간 합의 부호로 가른 다음 기간 평균의 차이."""
        if len(x) < k + 6:
            return None
        prev_k = x[:-1] if k == 1 else np.convolve(x, np.ones(k), "valid")[:-1]
        nxt_k = x[1:] if k == 1 else x[k:]
        hi, lo = prev_k > 0, prev_k <= 0
        if hi.sum() < 5 or lo.sum() < 5:
            return None
        return float(nxt_k[hi].mean() - nxt_k[lo].mean())

    KS = (1, 2, 3)
    obs_gaps = {k: gap_of(r, k) for k in KS}
    best_k = max((k for k in KS if obs_gaps[k] is not None),
                 key=lambda k: abs(obs_gaps[k]), default=None)
    print(f"\n【4】 갈림 폭 — 직전 k기간 합의 부호로 가른다")
    print(f"  {'k':>3}{'갈림 폭%p':>12}")
    for k in KS:
        g = obs_gaps[k]
        print(f"  {k:>3}{(f'{g:+.3f}' if g is not None else '—'):>12}")

    # 최대통계량 귀무 — 위약도 **세 k 를 다 재고 최고를 고른다**
    null_best, null_1 = [], []
    for _ in range(a.reps):
        pr = rng.permutation(r)
        gs = [gap_of(pr, k) for k in KS]
        gs = [g for g in gs if g is not None]
        if not gs:
            continue
        null_best.append(max(abs(g) for g in gs))
        g1 = gap_of(pr, 1)
        if g1 is not None:
            null_1.append(abs(g1))
    null_best, null_1 = np.array(null_best), np.array(null_1)
    obs_best_gap = abs(obs_gaps[best_k]) if best_k else 0.0
    p_naive = float(np.mean(null_1 >= abs(obs_gaps[1]))) if obs_gaps[1] is not None else 1.0
    p_max = float(np.mean(null_best >= obs_best_gap)) if len(null_best) else 1.0
    res["gap"] = {"obs": obs_gaps, "best_k": best_k,
                  "p_naive_k1": p_naive, "p_max_stat": p_max}
    print(f"\n  k=1 단독 위약 p        {p_naive:.3f}   ← 이것만 보면 통과처럼 보인다")
    print(f"  **최대통계량 p        {p_max:.3f}**   ← 세 k 를 다 재고 최고를 골랐음을 반영")

    # ── 표본 안/밖 ────────────────────────────────────────────────────
    print(f"\n【5】 표본 안/밖 — 분할 {a.split}")
    r_is = d.loc[d["split"] == "IS", "mean"].to_numpy()
    r_oos = d.loc[d["split"] == "OOS", "mean"].to_numpy()
    split_ok = True
    for lab, x in (("IS", r_is), ("OOS", r_oos)):
        g = gap_of(x, 1)
        if g is None:
            print(f"  {lab:<4} 기간 {len(x):>3} — **표본 부족으로 판정 불가**")
            split_ok = False
            continue
        res[f"gap/{lab}"] = {"n": len(x), "gap": g}
        print(f"  {lab:<4} 기간 {len(x):>3} · 갈림 폭 {g:+.3f}%p")
    if split_ok and res.get("gap/IS") and res.get("gap/OOS"):
        same = res["gap/IS"]["gap"] * res["gap/OOS"]["gap"] > 0
        print(f"  → 부호 {'일치 ✓' if same else '반전 ✗'}")
    else:
        same = False

    if p_max > 0.05:
        verdict = "탐지 불가 — 최대통계량 위약을 못 넘는다"
    elif not (split_ok and same):
        verdict = "보류 — 위약은 넘었으나 표본 밖 확인 실패"
    else:
        verdict = "탐지 여지 있음 — 다음 단계로"

    print("\n" + "=" * 92)
    print(f"  판정: **{verdict}**")
    if "탐지 불가" in verdict:
        print("     → 국면이 뭉쳐 있지 않다. 탐지기를 만들어도 늘 한 발 늦는다.")
        print("        여기서 멈춘다 — 탐지기는 표본 안에서 반드시 좋아 보인다.")
    print("=" * 92)

    res["verdict"] = verdict
    res["periods"] = d.assign(anchor=d["anchor"].astype(str)).to_dict("records")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"params": vars(a), "results": res},
                                      ensure_ascii=False, indent=2, default=str))
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
