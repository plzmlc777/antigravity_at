#!/usr/bin/env python3
"""RSI≤문턱 신호의 **발생 구조**를 주 단위로 남긴다.

왜 만들었나 (2026-09-02)
    1군이 48시간 무신호였다. 원본 대조로 「엔진이 놓친 게 아니라 시장에
    자리가 없었다」는 건 확인했지만, 그 과정에서 **주간 신호 빈도가 3주 전
    42회 → 최근 8~9회로 꺾인 것**이 드러났다. 이게 국면인지 알파 감쇠인지는
    한 번의 관측으로 못 가른다 — **매주 같은 자로 재서 쌓아야** 가른다.

⚠ 유니버스는 **지금 것 하나로 고정**해 전 구간을 훑는다. 그래야 주간 차이가
  유니버스 변경 탓이 아니라는 게 설계로 보장된다(2026-08-22 85→379 확장).

⚠ 국면과 감쇠를 가르는 대조 지표를 같이 남긴다.
  · 실현변동성(|로그수익률|) — **2026-09-02 실측에서 관계가 거꾸로 나왔다.**
    신호 42회 주의 변동성이 24bp 로 최저, 8회 주가 43bp 로 최고였다.
    RSI 극단은 흔들림의 **크기**가 아니라 한 방향으로 눌리는 **지속성**에서
    나온다 — 변동성만 보면 틀린 결론에 이른다.
  · 그래서 방향 지표를 함께 잰다: 주간 누적수익률(중앙) · 하락봉 비율.
    눌린 주에 신호가 많으면 국면, 눌렸는데도 신호가 없으면 감쇠다.

⚠ 봉 한도 999. 1000 이상은 가중치가 5→10 이라 유니버스 전체에서 한도를 넘는다.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "binance"))

from rsi_extreme_paper import fetch_klines, wilder_rsi   # noqa: E402

OUT = ROOT / "runs" / "paper_sessions" / "rsi_extreme" / "signal_profile"


def profile(universe: Path, tf: str, period: int, thresh: float,
            limit: int = 999, cap: int = 0) -> dict:
    syms = [s.strip().upper() for s in universe.read_text().split() if s.strip()]
    if cap:
        syms = syms[:cap]
    per_cycle: collections.Counter = collections.Counter()
    vol_by_sym: dict = {}
    bars: set = set()
    fail = 0
    for i, s in enumerate(syms):
        d = fetch_klines(s, limit, tf)
        if d is None or len(d) < period + 1:
            fail += 1
            continue
        c = d["close"].astype(float)
        r = wilder_rsi(c, period).dropna()
        bars.update(r.index)
        for ts in r[r <= thresh].index:
            per_cycle[ts] += 1
        # 대조 지표 — 봉당 로그수익률. 크기(|r|)와 방향(r)을 둘 다 쓴다.
        vol_by_sym[s] = c.pipe(np.log).diff()
        if (i + 1) % 60 == 0:
            print(f"  … {i+1}/{len(syms)}", flush=True)

    idx = sorted(bars)
    sig = sorted(per_cycle)
    span_h = (idx[-1] - idx[0]).total_seconds() / 3600 if len(idx) > 1 else 0.0

    # 주 단위 묶음 — 최신 봉 기준 7일씩 거슬러
    def wk_of(ts):
        return int((idx[-1] - ts).total_seconds() // (7 * 86400))

    wk_sig: collections.Counter = collections.Counter()
    for ts in sig:
        wk_sig[wk_of(ts)] += 1
    wk_vol: dict = collections.defaultdict(list)      # 크기 |r|
    wk_ret: dict = collections.defaultdict(list)      # 종목별 주간 누적수익률
    wk_down: dict = collections.defaultdict(list)     # 종목별 하락봉 비율
    for s, v in vol_by_sym.items():
        v = v.dropna()
        by_wk: dict = collections.defaultdict(list)
        for ts, x in v.items():
            k = wk_of(ts)
            wk_vol[k].append(abs(float(x)))
            by_wk[k].append(float(x))
        for k, xs in by_wk.items():
            arr = np.array(xs)
            wk_ret[k].append(float(arr.sum()))
            wk_down[k].append(float((arr < 0).mean()))

    gaps = [(sig[i + 1] - sig[i]).total_seconds() / 3600
            for i in range(len(sig) - 1)]
    now_gap = ((pd.Timestamp.now(tz="UTC") - sig[-1]).total_seconds() / 3600
               if sig else None)
    g = np.array(gaps) if gaps else np.array([])

    weeks = []
    for k in sorted(wk_sig | collections.Counter(wk_vol.keys())):
        vs = wk_vol.get(k) or []
        rs = wk_ret.get(k) or []
        ds = wk_down.get(k) or []
        weeks.append({
            "week_ago": k,
            "signal_cycles": int(wk_sig.get(k, 0)),
            "median_bar_vol_bp": round(1e4 * float(np.median(vs)), 2) if vs else None,
            # 방향 — 눌린 주인가
            "median_week_ret_pct": round(100 * float(np.median(rs)), 2) if rs else None,
            "p10_week_ret_pct": round(100 * float(np.percentile(rs, 10)), 2) if rs else None,
            "median_down_bar_pct": round(100 * float(np.median(ds)), 2) if ds else None,
            "n_vol_obs": len(vs)})

    return {
        "asof": datetime.now(timezone.utc).isoformat(),
        "universe": str(universe), "n_symbols": len(syms) - fail,
        "tf": tf, "period": period, "thresh": thresh,
        "span_days": round(span_h / 24, 2),
        "from": str(idx[0]) if idx else None, "to": str(idx[-1]) if idx else None,
        "bars": len(idx),
        "signal_cycles": len(sig),
        "signal_cycle_pct": round(100 * len(sig) / max(len(idx), 1), 2),
        "signal_bars": int(sum(per_cycle.values())),
        "per_signal_cycle_symbols": round(
            sum(per_cycle.values()) / max(len(sig), 1), 2),
        "cycles_per_day": round(len(sig) / max(span_h / 24, 1e-9), 2),
        "cluster_hist": {str(k): v for k, v
                         in sorted(collections.Counter(per_cycle.values()).items())},
        "gap_h": {"median": round(float(np.median(g)), 2) if len(g) else None,
                  "mean": round(float(g.mean()), 2) if len(g) else None,
                  "p90": round(float(np.percentile(g, 90)), 2) if len(g) else None,
                  "max": round(float(g.max()), 2) if len(g) else None,
                  "now": round(now_gap, 2) if now_gap is not None else None,
                  "pct_longer": round(100 * float((g >= now_gap).mean()), 1)
                  if len(g) and now_gap is not None else None},
        "weeks": weeks,
        "recent_signal_cycles": [str(t) for t in sig[-10:]],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe",
                    default=str(ROOT / "configs" / "rsi_live_universe.txt"))
    ap.add_argument("--tf", default="30m")
    ap.add_argument("--period", type=int, default=14)
    ap.add_argument("--thresh", type=float, default=12.0)
    ap.add_argument("--cap", type=int, default=0, help="예비비행용 종목 수 제한")
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args()

    d = profile(Path(a.universe), a.tf, a.period, a.thresh, cap=a.cap)
    print(f"\n표본 {d['n_symbols']}종목 · 봉 {d['bars']}개 · {d['span_days']}일")
    print(f"신호 사이클 {d['signal_cycles']}/{d['bars']} = "
          f"{d['signal_cycle_pct']}% · 하루 {d['cycles_per_day']}회 · "
          f"사이클당 {d['per_signal_cycle_symbols']}종목")
    gp = d["gap_h"]
    print(f"공백(h) 중앙 {gp['median']} · 상위10% {gp['p90']} · 최대 {gp['max']} "
          f"· 지금 {gp['now']} (더 긴 과거 {gp['pct_longer']}%)")
    print("\n주        신호   변동성   주간수익(중앙)  하위10%   하락봉비율")
    for w in d["weeks"]:
        lab = "최근 7일" if w["week_ago"] == 0 else f"{w['week_ago']+1}주 전"
        def f(x, suf=""):
            return f"{x}{suf}" if x is not None else "—"
        print(f"  {lab:<8} {w['signal_cycles']:>4}회 "
              f"{f(w['median_bar_vol_bp']):>7}bp "
              f"{f(w['median_week_ret_pct']):>10}% "
              f"{f(w['p10_week_ret_pct']):>8}% "
              f"{f(w['median_down_bar_pct']):>9}%")
    if not a.no_save:
        OUT.mkdir(parents=True, exist_ok=True)
        f = OUT / f"{datetime.now(timezone.utc):%Y%m%d}.json"
        f.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        print(f"\n기록 → {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
