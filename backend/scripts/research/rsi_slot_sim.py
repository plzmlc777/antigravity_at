"""슬롯 제약을 걸고 원장을 다시 훑는다 — **실제로 체결 가능한 총손익**.

⚠ 왜 필요한가 (2026-08-20 실측)
    5분봉 격자가 총손익 +2,034%p 를 냈다. 그런데 그 값은 종목 377개를
    **각각 독립적으로 자본 100%** 로 돌린 수익률의 합이다. 동시 보유가
    중앙 21 · 90% 135 · **최대 280** 이었다 — 슬롯 20개로는 잡을 수 없다.
    거래의 절반이 10일에 몰려 있다. 그날 수백 신호 중 20개만 잡는다.

    즉 원래 수치는 "슬롯이 무한하다면" 의 값이다.

배분 규칙은 페이퍼와 같게 둔다 — 같은 시각에 후보가 슬롯보다 많으면
**무작위**. 한 번 뽑고 끝내면 그건 한 번의 추첨 결과일 뿐이라
`--seeds` 번 반복해서 분포를 낸다.

종목 하나 안에서는 이미 보유 중이면 새 신호를 무시한다(정책이 그렇다).
원장에 그 규칙이 이미 반영돼 있으므로 여기서는 **종목 간 경합**만 푼다.

사용:
  python3 -m scripts.research.rsi_slot_sim --trades <trades.csv> \
      --slots 5,10,20,40,80 --seeds 40
"""
from __future__ import annotations

import argparse
import heapq
import numpy as np
import pandas as pd


def simulate(ev: list[tuple], slots: int, rng: np.random.Generator) -> dict:
    """시각순으로 훑으며 빈 슬롯만큼만 잡는다.

    ev: (entry_ns, exit_ns, ret_pct) 를 진입 시각으로 묶은 리스트
    """
    live: list[int] = []          # 보유 중인 거래의 청산 시각(min-heap)
    taken_ret, n_take, n_drop = [], 0, 0
    # ⚠ 자본곡선 없이 "연 +209%" 를 말하면 안 된다 (교훈 #81 — 거래당 엣지가
    #   좋아도 포트폴리오는 죽을 수 있다). 청산 시각에 손익을 꽂아
    #   **시간순 자본곡선**을 만들고 최대낙폭을 잰다.
    closes: list[tuple[int, float]] = []
    for entry_ns, group in ev:
        while live and live[0] <= entry_ns:      # 먼저 청산부터
            heapq.heappop(live)
        free = slots - len(live)
        if free <= 0:
            n_drop += len(group)
            continue
        if len(group) <= free:
            pick = group
        else:
            idx = rng.choice(len(group), size=free, replace=False)
            pick = [group[i] for i in idx]
            n_drop += len(group) - free
        for exit_ns, ret in pick:
            heapq.heappush(live, exit_ns)
            taken_ret.append(ret)
            closes.append((exit_ns, ret))
            n_take += 1
    r = np.array(taken_ret) if taken_ret else np.zeros(0)
    out = {"slots": slots, "take": n_take, "drop": n_drop,
           "sum_pct": float(r.sum()),
           "avg_pct": float(r.mean()) if len(r) else np.nan,
           "win_rate": float(100.0 * (r > 0).mean()) if len(r) else np.nan}
    if closes:
        closes.sort()
        ts = np.array([c[0] for c in closes], dtype="int64")
        # 슬롯당 명목 = 자본/슬롯 → 한 거래의 자본 기여 = ret_pct / slots.
        # ⚠ 복리로 잰다. 비복리 누적합으로 낙폭을 재면 자본이 커질수록
        #   같은 손실이 작아 보인다 — 슬롯별 최대낙폭이 전부 -3.0% 로
        #   똑같이 나왔던 게 그 왜곡이었다.
        step = np.array([c[1] for c in closes]) / 100.0 / slots
        eq = np.cumprod(1.0 + step)
        peak = np.maximum.accumulate(eq)
        out["mdd_pct"] = float(100.0 * ((eq - peak) / peak).min())
        out["final"] = float(eq[-1])
        out["cagr_pct"] = float(100.0 * (eq[-1] - 1.0))
        # 일별 수익률로 샤프 — 거래별로 재면 보유기간이 섞여 뜻이 없다
        day = ts // 86_400_000_000_000
        daily = pd.Series(step).groupby(day).sum()
        span_d = int(day.max() - day.min()) + 1
        full = daily.reindex(range(int(day.min()), int(day.max()) + 1),
                             fill_value=0.0)
        sd = float(full.std())
        out["sharpe"] = float(full.mean() / sd * np.sqrt(365)) if sd > 0 else np.nan
        out["worst_day_pct"] = float(100.0 * full.min())
        out["span_d"] = span_d
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--trades", required=True)
    p.add_argument("--slots", default="5,10,20,40,80")
    p.add_argument("--seeds", type=int, default=40)
    p.add_argument("--placebo", default="real")
    p.add_argument("--tp-maker-bp", type=float, default=0.0)
    p.add_argument("--sl-slip-bp", type=float, default=0.0,
                   help="손절 체결에 매길 슬리피지(bp). 하네스는 손절가에 "
                        "**정확히** 체결된다고 본다 — 30bp 스톱에서 이건 "
                        "낙관적이다. 스톱은 시장가로 나가고, 하필 여러 종목의 "
                        "스톱이 동시에 터지는 날 가장 크게 밀린다")
    a = p.parse_args()

    T = pd.read_csv(a.trades)
    T = T[T["placebo"] == a.placebo].copy()
    reason = T["exit_reason"].astype(str).str.lower()
    if a.tp_maker_bp:
        istp = reason.eq("tp")
        T.loc[istp, "ret_pct"] += a.tp_maker_bp / 100.0
        print(f"익절 {int(istp.sum()):,}건 +{a.tp_maker_bp:.1f}bp 되돌림")
    if a.sl_slip_bp:
        issl = reason.eq("sl")
        T.loc[issl, "ret_pct"] -= a.sl_slip_bp / 100.0
        print(f"손절 {int(issl.sum()):,}건 -{a.sl_slip_bp:.1f}bp 슬리피지 부과")

    # ⚠ pandas 2.x 는 CSV 시각을 **datetime64[us]** 로 읽는다. 그대로
    #   `.astype("int64")` 하면 마이크로초가 나오는데, 나노초 상수로 나누면
    #   1년이 **2일**이 된다(실측: 일 인덱스 19~20, 샤프 13.3).
    #   단위를 못 박고, 못 박혔는지 검사한다.
    def _ns(col: str) -> pd.Series:
        v = pd.to_datetime(T[col], utc=True).astype("datetime64[ns, UTC]")
        return v.astype("int64")

    en, ex = _ns("entry_ts"), _ns("exit_ts")
    span_days = (ex.max() - en.min()) / 86_400_000_000_000
    if not (1 <= span_days <= 5000):
        raise SystemExit(f"시각 단위가 이상하다 — 구간이 {span_days:.1f}일로 "
                         f"나온다. 나노초가 아닐 수 있다.")
    # 청산 시각이 없거나 진입보다 이르면 버린다 — 조용히 통과시키면 슬롯이
    # 즉시 비어 제약이 없는 것과 같아진다.
    ok = ex > en
    if (~ok).sum():
        print(f"⚠ 청산시각 이상 {int((~ok).sum())}건 제외")
    T, en, ex = T[ok], en[ok], ex[ok]

    df = pd.DataFrame({"en": en.values, "ex": ex.values,
                       "ret": T["ret_pct"].astype(float).values}).sort_values("en")
    ev = [(k, list(zip(g["ex"], g["ret"])))
          for k, g in df.groupby("en", sort=True)]
    uncon = df["ret"].sum()
    print(f"원장 {len(df):,}거래 · 진입시각 {len(ev):,}개 · "
          f"제약 없음 총손익 {uncon:,.1f}%p\n")

    print(f"{'슬롯':>5}{'체결':>8}{'버림':>8}{'포착률':>8}"
          f"{'총손익%p 중앙':>15}{'(5~95%)':>20}{'거래당%':>9}{'승률%':>7}"
          f"{'제약없음대비':>12}")
    for sl in [int(x) for x in a.slots.split(",")]:
        runs = [simulate(ev, sl, np.random.default_rng(1000 + s))
                for s in range(a.seeds)]
        S = np.array([r["sum_pct"] for r in runs])
        med = float(np.median(S))
        lo, hi = np.percentile(S, [5, 95])
        tk = int(np.median([r["take"] for r in runs]))
        dr = int(np.median([r["drop"] for r in runs]))
        av = float(np.median([r["avg_pct"] for r in runs]))
        wr = float(np.median([r["win_rate"] for r in runs]))
        print(f"{sl:>5}{tk:>8,}{dr:>8,}{100*tk/(tk+dr):>7.1f}%"
              f"{med:>15,.1f}{f'({lo:,.0f}~{hi:,.0f})':>20}"
              f"{av:>9.3f}{wr:>7.1f}{100*med/uncon:>11.1f}%")

    print(f"\n{'슬롯':>5}{'슬롯당자본':>10}{'복리수익':>10}{'단리수익':>10}"
          f"{'최대낙폭':>10}{'최악의날':>10}{'샤프':>8}{'구간일':>8}")
    for sl in [int(x) for x in a.slots.split(",")]:
        runs = [simulate(ev, sl, np.random.default_rng(1000 + s))
                for s in range(min(a.seeds, 20))]
        ret = float(np.median([r.get("cagr_pct", np.nan) for r in runs]))
        simple = float(np.median([r["sum_pct"] for r in runs])) / sl
        mdd = float(np.median([r.get("mdd_pct", np.nan) for r in runs]))
        wd = float(np.median([r.get("worst_day_pct", np.nan) for r in runs]))
        sh = float(np.median([r.get("sharpe", np.nan) for r in runs]))
        sp = int(np.median([r.get("span_d", 0) for r in runs]))
        print(f"{sl:>5}{100.0/sl:>9.1f}%{ret:>9.1f}%{simple:>9.1f}%"
              f"{mdd:>9.1f}%{wd:>9.2f}%{sh:>8.2f}{sp:>8}")
    print("\n※ 슬롯당 명목 = 자본/슬롯 → 한 거래의 자본 기여 = 거래수익률/슬롯수.")
    print("   복리수익은 자본곡선의 최종값, 단리수익은 총손익%p/슬롯수.")
    print("   슬롯이 적을수록 한 방이 크다 — 수익률과 최대낙폭을 **같이**")
    print("   봐야 한다 (교훈 #81: 거래당 엣지 ≠ 포트폴리오 생존).")
    print("   ⚠ 구간일이 기대와 다르면 원장의 창부터 확인하라.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
