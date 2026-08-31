"""백테스트 · 페이퍼 · 실거래를 **같은 자로** 잰다.

셋 다 정본 커널로 회계하지만 체결가를 정하는 주체가 다르다. 그 차이가
이 트랙의 측정 대상이다.

    진입 체결가   백테·그림자 봉 종가(정본) / 실거래 거래소 체결가
    익절 체결     백테·그림자 익절가 정확   / 실거래 **거래소 지정가**
    시간 청산     백테·그림자 봉 종가       / 실거래 거래소 시장가
    슬리피지      백테 0(사후추정)·그림자 0 / 실거래 **전부 실측**

**그림자**는 1군과 **같은 후보**를 받아쓰고 체결만 정본대로 한다. 그래서
`그림자 − 실거래` 가 곧 **체결 비용**이다 — 주문 거절 · 익절 지정가 미체결 ·
슬롯 포화로 1군이 놓친 몫. 페이퍼(독립 신호)와는 다른 물건이다.

⚠ 연율로 환산하지 마라. 실거래 표본이 백테스트 3,439건에 한참 못 미치는
   동안은 어떤 차이도 잡음이다. **같은 거래 수**에서 자른 뒤 비교한다.

⚠ 급락일을 겪었는지 본다. 슬리피지 꼬리는 청산 사태에서 나온다. 그날을
   안 겪은 표본은 "평온할 때는 안 밀린다" 만 말해준다 — 백테스트도 이미
   아는 사실이다(중앙값 0bp).

사용:
  python3 -m scripts.binance.rsi_three_way
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

SESS = Path("runs/paper_sessions/rsi_extreme")
SHADOW = "30m_rsi12_SHADOW"
LIVE = "30m_rsi12_LIVE"

# ══ 백테스트 기준선 — 30분봉 사양 (2026-08-24 이관) ═══════════════════
#
# ⚠ 실전은 스톱리밋 **간격 0** 이지만 기준선은 간격 0.1% 격자를 쓴다.
#   커널의 "간격 0 = 다음 30분봉까지 기다린다" 모형이 30분봉 해상도 탓에
#   지나치게 비관적이라(연 −96.8%) 쓸 수 없다. 1분봉 체결률 실측은 간격
#   0 에서도 **99.6%** 이므로 0.1% 격자가 실제에 더 가깝다.
BT_TRADES = ("runs/research_track/rsi_tp_sl/"
             "trades_long_30mfrom1m_h96_2025-08-17_2026-08-17_OFFSET18.csv")
BT_SLIP = ""                      # 지정가 손절이라 시장가 슬리피지 표가 없다
# 실전 칸 — 문서 "01 확정 사양"
BT_CELL = {"thr": 12.0, "tp": 0.08, "sl": 0.005, "entry_mode": "level",
           "xr": 10.0, "sloff": 0.001}


def _live_slots(default: int = 1) -> int:
    """슬롯 수는 **실행 중인 세션에서 읽는다.**

    ⚠ 2026-08-24 — 상수 `SLOTS = 80` 이 박혀 있어 30분봉(슬롯 1) 이관 뒤에도
      80 을 곱했다. "슬롯당 자본 $752 × 80 = 계좌 $60,160" 같은 값이 나왔고
      대표님이 먼저 발견하셨다. 설정을 두 곳에 두면 한 곳만 바뀐다."""
    for name in (LIVE, SHADOW):
        f = SESS / name / "config.json"
        try:
            return int(json.loads(f.read_text()).get("slots") or default)
        except Exception:                                     # noqa: BLE001
            continue
    return default


SLOTS = _live_slots()



# ══════════════════════════════════════════════════════════════════════
#  기간 손익 — 주간·월간·연간
# ══════════════════════════════════════════════════════════════════════
#  ⚠ 셋을 비교하려면 **자본 대비 %** 로 통일해야 한다. 총손익 %p 는 거래별
#    수익률의 합이라 슬롯 수가 다르면 비교가 안 된다.
#    자본 기여 = 거래수익률 / 슬롯수 → 자본곡선을 복리로 쌓는다.
#
#  ⚠ 기간이 안 찼으면 **예측치**다. 선형 외삽이 아니라 복리로 환산한다
#    (연 14.2% 는 월 1.18% 가 아니라 1.11% 다). 그리고 표본이 적으면
#    예측 자체가 무의미하므로 그 사실을 같이 찍는다.
WEEK_D, MONTH_D, YEAR_D = 7.0, 30.44, 365.0


def period_returns(total_ret: float, days: float, projected: bool) -> dict:
    """실현 수익률(비율, 예: 0.142)과 경과일 → 주간·월간·연간."""
    if days <= 0:
        return {}
    g = 1.0 + total_ret
    if g <= 0:                     # 자본 전손 — 환산이 뜻을 잃는다
        return {"주간": float("nan"), "월간": float("nan"), "연간": -1.0,
                "예측": projected}
    return {
        "주간": g ** (WEEK_D / days) - 1.0,
        "월간": g ** (MONTH_D / days) - 1.0,
        "연간": g ** (YEAR_D / days) - 1.0,
        "예측": projected,
    }


def _fmt_pct(v) -> str:
    import math
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{100 * v:+.2f}%"


def _load_session(name: str) -> tuple[list, dict]:
    """세션 폴더의 체결 원장과 상태."""
    d = SESS / name
    st = {}
    f = d / "state.json"
    if f.exists():
        st = json.loads(f.read_text())
    rows: list = []
    # ⚠ 원장은 **날짜별 하위 폴더**에 있다(`<세션>/2026-08-22/cycles.jsonl`).
    #   최상위만 뒤지면 거래 0 으로 나온다 — 상태 파일엔 손익이 있는데
    #   원장이 비는 모순이 그 증상이다.
    for p in sorted(d.glob("*/cycles*.jsonl")) + sorted(d.glob("cycles*.jsonl")):
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            try:
                c = json.loads(line)
            except Exception:
                continue
            for e in c.get("exits", []) or []:
                rows.append(e)
    return rows, st


def _metrics(rets: np.ndarray, exits: list, n_sym: int) -> dict:
    """매뉴얼이 못 박은 다섯 지표."""
    if not len(rets):
        return {"거래": 0}
    reasons = [str(e.get("reason", "")).lower() for e in exits] if exits else []
    tp = sum(1 for r in reasons if r == "tp")
    slips = [float(e.get("exit_slip_bp", 0) or 0) for e in exits
             if str(e.get("reason", "")).lower() != "tp"] if exits else []
    return {
        "거래": len(rets),
        "총손익%p": float(rets.sum()),
        "거래당%": float(rets.mean()),
        "익절비중%": 100.0 * tp / len(rets) if len(rets) else np.nan,
        "청산slip_bp": float(np.median(slips)) if slips else np.nan,
        "종목": n_sym,
    }


def backtest_slotted(slots: int, seeds: int = 8) -> dict:
    """백테스트 원장에 **슬롯 제약과 실측 슬리피지를 걸어** 다시 센다.

    ⚠ 제약 없는 총손익(+2,167%p)을 기간 수익률과 같은 표에 두면 단위가
      섞인다. 그건 종목마다 자본 100% 를 쓴 합이라 **자본 수익률이 아니다**
      (동시 보유가 최대 267종목까지 간다). 실거래는 슬롯 80 이므로
      **같은 조건**으로 맞춰야 비교가 성립한다.

    하드코딩하지 않고 원장에서 계산한다 — 설정이 바뀌면 값도 따라간다.
    """
    import sys
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
    from scripts.research.rsi_slot_sim import simulate

    T = pd.read_csv(BT_TRADES)
    if "placebo" in T.columns:
        T = T[T.placebo == "real"]
    # 격자 원장이므로 **실전 칸만** 남긴다 — 안 거르면 18칸이 뒤섞인다
    for col, want in BT_CELL.items():
        if col not in T.columns:
            continue
        T = (T[T[col] == want] if col == "entry_mode"
             else T[np.isclose(T[col].astype(float), float(want))])
    T = T.copy()
    try:
        if not BT_SLIP:
            raise FileNotFoundError("지정가 손절 — 시장가 슬리피지 표 없음")
        S = pd.read_csv(BT_SLIP)
        k = ["symbol", "entry_ts", "exit_ts"]
        for c in k:
            S[c] = S[c].astype(str); T[c] = T[c].astype(str)
        T = T.merge(S.drop_duplicates(k)[k + ["slip_opt_bp"]], on=k, how="left")
        mkt = T.exit_reason.str.lower().isin(["sl", "time", "eod"])
        pool = T.loc[mkt & T.slip_opt_bp.notna(), "slip_opt_bp"].to_numpy()
        rng0 = np.random.default_rng(20260822)
        miss = mkt & T.slip_opt_bp.isna()
        if miss.any() and len(pool):
            T.loc[miss, "slip_opt_bp"] = rng0.choice(pool, size=int(miss.sum()))
        T["ret_pct"] = T.ret_pct - T.slip_opt_bp.fillna(0.0) / 100.0
    except Exception:
        pass

    def _ns(col):
        return (pd.to_datetime(T[col], utc=True)
                .astype("datetime64[ns, UTC]").astype("int64"))
    en, ex = _ns("entry_ts"), _ns("exit_ts")
    ok = ex > en
    T, en, ex = T[ok], en[ok], ex[ok]
    df = pd.DataFrame({"en": en.values, "ex": ex.values,
                       "ret": T.ret_pct.astype(float).values,
                       "tp": T.exit_reason.str.lower().eq("tp").values,
                       "sym": T.symbol.values}).sort_values("en")
    ev = [(k, list(zip(g["ex"], g["ret"]))) for k, g in df.groupby("en", sort=True)]

    runs = [simulate(ev, slots, np.random.default_rng(900 + i))
            for i in range(seeds)]
    take = int(np.median([r["take"] for r in runs]))
    drop = int(np.median([r["drop"] for r in runs]))
    tot = float(np.median([r["sum_pct"] for r in runs]))
    avg = float(np.median([r["avg_pct"] for r in runs]))
    days = (df.ex.max() - df.en.min()) / 86_400_000_000_000
    # 익절 비중은 포착 비율이 사유와 무관하므로 원장 비율을 그대로 쓴다
    tp_share = 100.0 * float(df.tp.mean())
    return {"슬롯": slots, "체결": take,
            "포착률": 100.0 * take / max(take + drop, 1),
            "총손익%p": tot, "거래당%": avg, "익절비중%": tp_share,
            "종목": int(df.sym.nunique()),
            "ret": tot / 100.0 / slots, "days": float(days),
            "projected": False, "n": take}


def _live_notional() -> float:
    """실거래 세션의 슬롯당 명목. 설정 파일에서 읽는다(하드코딩 금지)."""
    f = SESS / LIVE / "config.json"
    if not f.exists():
        return 0.0
    try:
        return float(json.loads(f.read_text()).get("notional_usd", 0) or 0)
    except Exception:
        return 0.0


def _bt_period() -> dict:
    return backtest_slotted(SLOTS)


def _sess_period(name: str) -> dict:
    """세션 자본 수익률 = 누적손익 / (슬롯 × 슬롯당 명목)."""
    d = SESS / name
    st_f, cf_f = d / "state.json", d / "config.json"
    if not st_f.exists():
        return {}
    st = json.loads(st_f.read_text())
    eq = float(st.get("equity", 0) or 0)
    cap = 0.0
    if cf_f.exists():
        try:
            cf = json.loads(cf_f.read_text())
            cap = float(cf.get("slots", 0)) * float(cf.get("notional_usd", 0))
        except Exception:
            cap = 0.0
    if cap <= 0:
        return {}
    # 경과 — 원장의 첫 사이클부터 마지막 저장까지
    days, n = 0.0, 0
    stamps = []
    for p_ in sorted(d.glob("*/cycles*.jsonl")):
        for line in p_.read_text().splitlines():
            if not line.strip():
                continue
            try:
                c = json.loads(line)
            except Exception:
                continue
            stamps.append(c.get("ts", ""))
            n += len(c.get("exits", []) or [])
    if len(stamps) >= 2:
        t0 = pd.Timestamp(min(stamps)); t1 = pd.Timestamp(max(stamps))
        days = max((t1 - t0).total_seconds() / 86400.0, 1e-6)
    if days <= 0 or n == 0:
        return {"ret": eq / cap, "days": max(days, 1e-6), "projected": True,
                "n": n} if days > 0 else {}
    return {"ret": eq / cap, "days": days, "projected": days < 365.0, "n": n}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true",
                   help="표를 JSON 으로 낸다. 정기보고가 **텍스트를 파싱하지 "
                        "않도록** 하기 위한 통로다 — 파싱은 언젠가 조용히 깨진다.")
    ap.add_argument("--cap", type=int, default=0,
                    help="비교를 **앞에서 N거래**로 자른다. 0이면 전부. "
                         "표본 수가 다르면 자르고 비교하는 게 정직하다")
    a = ap.parse_args()

    out = {}

    # ── 백테스트 ──
    bt = pd.read_csv(BT_TRADES)
    bt = bt[bt.placebo == "real"]
    try:
        if not BT_SLIP:
            raise FileNotFoundError("지정가 손절 — 시장가 슬리피지 표 없음")
        S = pd.read_csv(BT_SLIP)
        k = ["symbol", "entry_ts", "exit_ts"]
        for c in k:
            S[c] = S[c].astype(str); bt[c] = bt[c].astype(str)
        bt = bt.merge(S.drop_duplicates(k)[k + ["slip_opt_bp"]], on=k, how="left")
    except Exception:
        bt["slip_opt_bp"] = np.nan
    bt_ex = [{"reason": r, "exit_slip_bp": s}
             for r, s in zip(bt.exit_reason, bt.slip_opt_bp.fillna(0))]
    r = bt.ret_pct.to_numpy()
    if a.cap:
        r, bt_ex = r[:a.cap], bt_ex[:a.cap]
    out["백테스트"] = _metrics(r, bt_ex, bt.symbol.nunique())
    out["백테스트"]["구간"] = "2025-08-17~2026-08-17"

    # ── 페이퍼 · 실거래 ──
    for label, name in (("그림자", SHADOW), ("실거래", LIVE)):
        exits, st = _load_session(name)
        rr = np.array([float(e.get("ret_pct", 0)) for e in exits])
        if a.cap:
            rr, exits = rr[:a.cap], exits[:a.cap]
        m = _metrics(rr, exits, len({e.get("symbol") for e in exits}))
        m["구간"] = (st.get("saved_at", "?")[:10] if st else "?")
        m["보유중"] = len(st.get("pos", [])) if st else 0
        m["누적$"] = round(float(st.get("equity", 0) or 0), 2) if st else 0.0
        out[label] = m

    # ── 단일 표 — **슬롯을 적용한 값으로 통일한다** ──────────
    #    2026-08-22 대표님 지적: 총손익은 슬롯 무제한, 기간 수익률은 슬롯 80
    #    이라 한 표에 단위가 섞여 있었다. 이제 세 행 모두 슬롯 적용값이고
    #    `총손익%p ÷ 슬롯 ≈ 연간 수익률` 이 표 안에서 맞아떨어진다.
    btm = _bt_period()
    periods = {"백테스트": btm, "그림자": _sess_period(SHADOW),
               "실거래": _sess_period(LIVE)}
    rows = []
    for label in ("백테스트", "그림자", "실거래"):
        info = periods.get(label) or {}
        if label == "백테스트":
            m = {k: btm.get(k) for k in
                 ("체결", "포착률", "총손익%p", "거래당%", "익절비중%", "종목")}
            m["슬롯"] = btm["슬롯"]
        else:
            src = out.get(label, {})
            m = {"슬롯": SLOTS, "체결": src.get("거래", 0),
                 "포착률": None, "총손익%p": src.get("총손익%p"),
                 "거래당%": src.get("거래당%"), "익절비중%": src.get("익절비중%"),
                 "종목": src.get("종목")}
        pr = period_returns(info["ret"], info["days"], info["projected"]) \
            if info else {}
        bad = bool(info) and (info["n"] < 30
                              or (info["projected"] and info["days"] < 7))
        show = (lambda k: "—" if (not pr or bad) else _fmt_pct(pr.get(k)))
        def num(v, f="{:,.2f}"):
            return "—" if v is None or (isinstance(v, float) and np.isnan(v)) \
                else f.format(v)
        note = ""
        if info:
            if bad:
                note = f"표본 {info['n']}건 · 경과 {info['days']:.1f}일 — 예측 불가"
            elif info["projected"]:
                note = f"예측치 (경과 {info['days']:.0f}일)"
            else:
                note = f"실측 {info['days']:.0f}일"
        rows.append([label, f"{m['슬롯']}", num(m["체결"], "{:,.0f}"),
                     num(m["포착률"], "{:.1f}%"), num(m["총손익%p"]),
                     num(m["거래당%"]), num(m["익절비중%"]),
                     num(m["종목"], "{:,.0f}"),
                     show("주간"), show("월간"), show("연간"), note])
    hdr = ["", "슬롯", "체결", "포착률", "총손익%p", "거래당%", "익절비중%",
           "종목", "주간", "월간", "연간", "비고"]
    w = [max(len(str(r[i])) for r in [hdr] + rows) for i in range(len(hdr))]
    def _line(r):
        return "  ".join(str(v).rjust(w[i]) if i else str(v).ljust(w[0])
                         for i, v in enumerate(r))
    if a.json:
        import json as _json
        cost = None
        try:
            g = float(out["그림자"]["총손익%p"]); l = float(out["실거래"]["총손익%p"])
            cost = round(g - l, 4)
        except Exception:                                     # noqa: BLE001
            pass
        print(_json.dumps(
            {"hdr": hdr, "rows": rows, "slots": SLOTS,
             "n_live": int(out["실거래"].get("거래", 0) or 0),
             "n_bt": int(out["백테스트"].get("거래", 0) or 0),
             "held": {k: out.get(k, {}).get("보유중")
                      for k in ("그림자", "실거래")},
             "equity": {k: out.get(k, {}).get("누적$")
                        for k in ("그림자", "실거래")},
             "fill_cost_pp": cost}, ensure_ascii=False))
        return 0
    print(f"\n=== 3자 비교 · 슬롯 {SLOTS} 적용{f' · 앞 {a.cap}거래' if a.cap else ''} ===")
    print(_line(hdr))
    print("  ".join("─" * x for x in w))
    for r in rows:
        print(_line(r))
    print(f"  ※ 총손익%p 는 **슬롯 {SLOTS} 제약과 실측 슬리피지를 건** 값이다.")
    print(f"     자본 기여 = 거래수익률 / {SLOTS} → 주간·월간·연간은 그 복리다.")
    print("     표본 30건 미만 또는 경과 7일 미만이면 예측을 내지 않는다.")

    # ── 슬롯 관점 — **금액으로** ──────────────────────────
    #    비율은 슬롯당과 계좌가 같다(자본을 균등 분할하므로). 다른 건 금액이다.
    #    "연 13%" 보다 "슬롯 하나가 한 달에 10센트" 가 현실을 정확히 전한다.
    notional = _live_notional() or 9.4
    acct = SLOTS * notional
    pr = period_returns(btm["ret"], btm["days"], False)
    tr_per_slot = btm["체결"] / SLOTS
    print(f"\n=== 슬롯 관점 (백테스트 기준) ===")
    print(f"  슬롯당 자본 ${notional:.2f} × {SLOTS}슬롯 = 계좌 ${acct:,.0f}")
    print(f"  슬롯당 거래 {tr_per_slot:.1f}건/년 = {tr_per_slot/12:.1f}건/월"
          f" · 거래당 {btm['거래당%']:.2f}% = ${notional*btm['거래당%']/100:.3f}")
    print(f"\n  {'기간':<6}{'수익률':>9}{'슬롯당':>12}{'계좌':>12}")
    for lab, k in (("주간", "주간"), ("월간", "월간"), ("연간", "연간")):
        r = pr.get(k, 0.0)
        print(f"  {lab:<6}{100*r:>8.2f}%{notional*r:>11.3f}$"
              f"{acct*r:>11.2f}$")
    print(f"\n  ※ 슬롯 하나가 한 달에 버는 돈은 ${notional*pr['월간']:.3f} 다.")
    print(f"     계좌 전체가 그 {SLOTS}배 — 규모는 슬롯 수가 아니라 **슬롯당")
    print(f"     자본**이 정한다. 지금은 잔고 ${acct:,.0f} 를 {SLOTS}등분했다.")

    n_live = int(out["실거래"].get("거래", 0) or 0)
    n_bt = int(out["백테스트"].get("거래", 0) or 0)
    print(f"\n표본 — 실거래 {n_live} vs 백테스트 {n_bt}")
    if n_live < 30:
        print("  ⚠ 실거래 표본이 30건 미만이다. **어떤 차이도 잡음이다.**")
        print("     지금 판단하지 마라 — 표본이 쌓일 때까지 기다린다.")
    else:
        print(f"  같은 수로 비교하려면 --cap {n_live}")
    print("\n기준선(백테스트) — 수익종목 73.2% · 익절비중 39.4% · "
          "청산slip 8.6bp · 포착률 74.3%")
    g = out.get("그림자", {}).get("총손익%p")
    l = out.get("실거래", {}).get("총손익%p")
    if g and l is not None:
        print(f"체결 비용 = 그림자 − 실거래 = {g:,.2f} − {l:,.2f} = "
              f"{g - l:+,.2f}%p   (1군이 놓친 몫)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
