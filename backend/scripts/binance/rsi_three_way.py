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

BT_TRADES = "runs/research_track/rsi_tp_sl/cbtrades_sl0_cross_back.csv"
BT_SLIP = "runs/research_track/rsi_tp_sl/cbslip_sl0_cross_back.csv"
SESS = Path("runs/paper_sessions/rsi_extreme")
SHADOW = "5m_rsi10_cb_nosl_SHADOW"
LIVE = "5m_rsi10_cb_nosl_LIVE"



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


def _bt_period() -> dict:
    """백테스트 자본 수익률 — **슬롯 제약을 건 값**을 쓴다.

    제약 없는 총손익(+2,167%p)은 종목마다 자본 100% 를 쓴 합이라 자본
    수익률이 아니다. 실거래는 슬롯 80 이므로 같은 조건의 값을 기준선으로
    둔다 — `rsi_slot_sim` 실측(실측 슬리피지 낙관 적용):
        슬롯 80 · 복리 +14.2% · 최대낙폭 -8.3% · 샤프 0.97 · 365일
    """
    return {"ret": 0.142, "days": 365.0, "projected": False, "n": 2556}


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
    ap.add_argument("--cap", type=int, default=0,
                    help="비교를 **앞에서 N거래**로 자른다. 0이면 전부. "
                         "표본 수가 다르면 자르고 비교하는 게 정직하다")
    a = ap.parse_args()

    out = {}

    # ── 백테스트 ──
    bt = pd.read_csv(BT_TRADES)
    bt = bt[bt.placebo == "real"]
    try:
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

    cols = ["거래", "총손익%p", "거래당%", "익절비중%", "청산slip_bp",
            "종목", "보유중", "누적$", "구간"]
    D = pd.DataFrame(out).T.reindex(columns=cols)
    print(f"\n=== 3자 비교{f' · 앞 {a.cap}거래로 절단' if a.cap else ''} ===")
    print(D.to_string(na_rep="—", float_format=lambda x: f"{x:,.2f}"))

    # ── 기간 손익 ──────────────────────────────────────
    print("\n=== 기간 손익 (자본 대비) ===")
    print(f"{'':<8}{'실현':>11}{'경과':>9}{'주간':>11}{'월간':>11}{'연간':>11}"
          f"{'표본':>7}   비고")
    for label, info in (("백테스트", _bt_period()),
                        ("그림자", _sess_period(SHADOW)),
                        ("실거래", _sess_period(LIVE))):
        if not info:
            print(f"{label:<8}{'—':>11}{'—':>9}{'—':>11}{'—':>11}{'—':>11}"
                  f"{0:>7}   거래 없음")
            continue
        pr = period_returns(info["ret"], info["days"], info["projected"])
        tag = "**예측치**" if info["projected"] else "실측"
        # ⚠ 경과가 짧으면 복리 환산이 폭주한다(0.3일 → 365제곱). 숫자를
        #   지우진 않되 **믿을 수 없다는 사실**을 같이 찍는다. 조용히
        #   내보내면 +6,191% 같은 값이 성과로 읽힌다.
        bad = []
        if info["projected"] and info["days"] < 7:
            bad.append(f"경과 {info['days']:.1f}일")
        if info["n"] < 30:
            bad.append(f"표본 {info['n']}건")
        warn = ("  ⚠ 무의미 — " + " · ".join(bad)) if bad else ""
        print(f"{label:<8}{_fmt_pct(info['ret']):>11}{info['days']:>8.1f}일"
              f"{_fmt_pct(pr.get('주간')):>11}{_fmt_pct(pr.get('월간')):>11}"
              f"{_fmt_pct(pr.get('연간')):>11}{info['n']:>7}   {tag}{warn}")
    print("  ※ 예측치는 복리 환산이다. 경과 7일 미만 또는 표본 30건 미만이면")
    print("     `무의미` 로 표시한다 — 하루치를 연으로 늘리면 365제곱이 된다.")
    print("     주간 예측은 7일, 월간은 30일, 연간은 90일 경과 후부터 읽어라.")

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
