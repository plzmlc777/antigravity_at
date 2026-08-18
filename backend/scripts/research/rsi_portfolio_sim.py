"""포트폴리오 시뮬레이션 — 거래당 엣지가 **계좌 수익**이 되는가.

왜 필요한가 (교훈 #81)
    지금까지 낸 것은 전부 "거래당 평균"이다. R-1 에서 거래당 엣지 9/9 PASS
    였는데 R-2 에서 샤프 0.75 · MDD -36% 였던 전례가 있다. 계좌는 거래를
    **동시에·자본 한도 안에서** 하므로 거래당 수치와 다른 답이 나온다.

⚠ 드물게 거래하면 샤프가 **공짜로** 높아진다
    자본이 놀면 그 기간 수익률이 0 이라 변동성이 낮다. 그래서 회전 위약
    포트폴리오를 **같은 배선으로** 돌려 나란히 놓는다. 위약도 샤프가 높으면
    그건 신호가 아니라 게으름이다.

⚠ 자본 유휴를 반드시 출력한다
    문턱 12 는 종목당 연 1.3 건이다. 85종목을 붙여도 동시 포지션이 한 자릿수면
    거래당 +1.5% 가 연 수익률로는 미미해진다. **그게 이 검정의 핵심 질문이다.**

배선
    · 거래는 시각순으로 처리. 진입 시 빈 슬롯이 있으면 잡고, 없으면 **버린다**
      (실계좌에서 자본이 없으면 그 신호는 못 먹는다 — 소급해 끼워넣지 않는다)
    · 슬롯당 자본 = 총자본 / max_slots (고정 분할, 복리 아님)
    · 청산 시 슬롯 반납, 손익을 자본에 더한다
    · 일별 자본 곡선으로 샤프·MDD 를 낸다
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "runs" / "research_track" / "rsi_tp_sl"
KEY = ["side", "thr", "tp", "sl", "placebo"]


def sec(t):
    print("\n" + "=" * 112)
    print(t)
    print("=" * 112)


def simulate(tr: pd.DataFrame, slots: int, fee_bp: float) -> dict:
    """슬롯 제약 하의 계좌. 자본은 슬롯으로 균등 분할한다.

    반환: 연수익·샤프·MDD·거래수·체결률·평균 동시포지션·유휴비율
    """
    t = tr.sort_values("entry_ts").reset_index(drop=True)
    ent = pd.to_datetime(t.entry_ts).to_numpy()
    exi = pd.to_datetime(t.exit_ts).to_numpy()
    ret = (t.ret_pct.to_numpy(float) - fee_bp / 100.0) / 100.0

    free = np.full(slots, np.datetime64("1970-01-01"))   # 슬롯별 해제 시각
    taken = np.zeros(len(t), dtype=bool)
    slot_of = np.full(len(t), -1)
    for i in range(len(t)):
        j = int(np.argmin(free))
        if free[j] <= ent[i]:
            free[j] = exi[i]
            taken[i] = True
            slot_of[i] = j
    if not taken.any():
        return {"n": 0}

    # 일별 실현손익 → 자본 곡선 (슬롯당 1/slots 자본, 복리 아님)
    d_exit = pd.to_datetime(t.exit_ts[taken]).dt.floor("D")
    pnl = pd.Series(ret[taken] / slots, index=d_exit).groupby(level=0).sum()
    days = pd.date_range(pd.to_datetime(t.entry_ts).min().floor("D"),
                         pd.to_datetime(t.exit_ts).max().ceil("D"), freq="D")
    daily = pnl.reindex(days).fillna(0.0)
    eq = 1.0 + daily.cumsum()
    yrs = len(days) / 365.25
    sd = daily.std(ddof=1)
    mdd = float((eq - eq.cummax()).min())

    # 자본 점유 — 슬롯·시간 기준
    occ = float(np.sum((exi[taken] - ent[taken]) / np.timedelta64(1, "D"))
                / (slots * len(days)))
    return {
        "n": int(taken.sum()), "n_signal": int(len(t)),
        "fill_pct": 100.0 * float(taken.mean()),
        "ret_total": 100.0 * float(eq.iloc[-1] - 1.0),
        "ret_yr": 100.0 * float(eq.iloc[-1] - 1.0) / yrs,
        "sharpe": float(daily.mean() / sd * np.sqrt(365.25)) if sd > 0 else np.nan,
        "mdd": 100.0 * mdd,
        "trades_yr": float(taken.sum() / yrs),
        "occ_pct": 100.0 * occ,
        "idle_pct": 100.0 * (1.0 - occ),
        "yrs": yrs,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="trades_long_short_h48_PF.csv")
    ap.add_argument("--slots", default="5,10,20,40")
    ap.add_argument("--fee-bp", type=float, default=10.0)
    a = ap.parse_args()

    f = D / a.file
    if not f.exists():
        print(f"거래 파일이 없다: {f}")
        return 1
    T = pd.read_csv(f)
    sec("포트폴리오 시뮬레이션 — 거래당 엣지가 계좌 수익이 되는가")
    print(f"  거래 {len(T):,} · 설정 {T.groupby(KEY).ngroups} · "
          f"종목 {T.symbol.nunique()} · 왕복 마찰 {a.fee_bp:.0f}bp")
    print("  슬롯 = 동시 보유 가능 종목 수. 자본은 슬롯으로 균등 분할(복리 아님)")
    print("  ⚠ 신호가 왔는데 슬롯이 없으면 **버린다** — 실계좌와 같게")

    slots = [int(x) for x in a.slots.split(",")]
    rows = []
    for k, g in T.groupby(KEY):
        for s in slots:
            r = simulate(g, s, a.fee_bp)
            if r.get("n", 0) < 30:
                continue
            rows.append({**dict(zip(KEY, k)), "slots": s, **r})
    R = pd.DataFrame(rows)
    if R.empty:
        print("판정 가능한 설정이 없다 (거래 30건 미만)")
        return 0

    # ── ① 실측 vs 위약 ─────────────────────────────────────────
    sec("① 실측 포트폴리오 (마찰 반영)")
    print(f"{'방향':<6}{'문턱':>5}{'익절%':>6}{'손절%':>6}{'슬롯':>5}"
          f"{'연거래':>8}{'체결률%':>8}{'연수익%':>9}{'샤프':>7}{'MDD%':>8}"
          f"{'자본점유%':>11}")
    print("-" * 112)
    for _, r in R[R.placebo == "real"].sort_values(
            ["side", "thr", "sl", "slots"]).iterrows():
        print(f"{r.side:<6}{r.thr:>5.0f}{100*r.tp:>6.0f}{100*r.sl:>6.0f}"
              f"{r.slots:>5}{r.trades_yr:>8.1f}{r.fill_pct:>8.1f}"
              f"{r.ret_yr:>+9.2f}{r.sharpe:>7.2f}{r.mdd:>+8.1f}{r.occ_pct:>11.1f}")

    # ── ② 위약 대비 ────────────────────────────────────────────
    sec("② 회전 위약 대비 — 샤프가 신호 덕인가 게으름 덕인가")
    M = (R[R.placebo == "real"].merge(
        R[R.placebo == "rotate"], on=["side", "thr", "tp", "sl", "slots"],
        suffixes=("_r", "_n")))
    print(f"{'방향':<6}{'문턱':>5}{'손절%':>6}{'슬롯':>5}"
          f"{'실측 연수익%':>13}{'위약 연수익%':>13}{'실측 샤프':>10}{'위약 샤프':>10}"
          f"{'실측 MDD%':>11}{'위약 MDD%':>11}")
    print("-" * 112)
    for _, r in M.sort_values(["side", "thr", "sl", "slots"]).iterrows():
        print(f"{r.side:<6}{r.thr:>5.0f}{100*r.sl:>6.0f}{r.slots:>5}"
              f"{r.ret_yr_r:>+13.2f}{r.ret_yr_n:>+13.2f}"
              f"{r.sharpe_r:>10.2f}{r.sharpe_n:>10.2f}"
              f"{r.mdd_r:>+11.1f}{r.mdd_n:>+11.1f}")
    print(f"\n  실측이 위약보다 연수익 높은 칸 "
          f"**{int((M.ret_yr_r > M.ret_yr_n).sum())}/{len(M)}**")
    print(f"  실측이 위약보다 샤프 높은 칸   "
          f"**{int((M.sharpe_r > M.sharpe_n).sum())}/{len(M)}**")

    # ── ③ 자본 유휴 ────────────────────────────────────────────
    sec("③ 자본 유휴 — 기회가 없어서 못 버는가")
    q = R[R.placebo == "real"]
    print(f"{'문턱':>5}{'슬롯':>5}{'자본점유 중앙%':>16}{'체결률 중앙%':>14}"
          f"{'연거래 중앙':>13}{'연수익 중앙%':>14}")
    print("-" * 112)
    for (t, s), g in q.groupby(["thr", "slots"]):
        print(f"{t:>5.0f}{s:>5}{g.occ_pct.median():>16.1f}"
              f"{g.fill_pct.median():>14.1f}{g.trades_yr.median():>13.1f}"
              f"{g.ret_yr.median():>+14.2f}")
    print("\n  → 점유가 낮으면 거래당 엣지가 커도 연 수익은 작다. 그게 이 계열의 한계다")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
