"""백테스트 · 페이퍼 · 실거래를 **같은 자로** 잰다.

셋 다 정본 커널로 회계하지만 체결가를 정하는 주체가 다르다. 그 차이가
이 트랙의 측정 대상이다.

    진입 체결가   백테 다음 봉 시가 / 페이퍼 봉마감 직후 현재가 / 실거래 거래소
    익절 체결     백테·페이퍼 익절가 정확 / 실거래 **거래소 지정가**
    시간 청산     백테 봉 종가 / 페이퍼 현재가 / 실거래 거래소 시장가
    슬리피지      백테 0(사후추정) / 페이퍼 진입만 / 실거래 **전부 실측**

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
PAPER = "5m_rsi10_cb_nosl"
LIVE = "5m_rsi10_cb_nosl_LIVE"


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
    for label, name in (("페이퍼", PAPER), ("실거래", LIVE)):
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
