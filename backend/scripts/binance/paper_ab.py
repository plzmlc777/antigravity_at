"""페이퍼 A/B — **공통 출발선**에서 갈래를 나란히 세운다 (2026-09-09).

## 왜

`kine_report.sh` 의 `자본%` 는 각 갈래가 **가동한 순간부터**의 누적이다.
충격숏3 는 189시간, 오늘 띄운 셋은 몇 분이라 그 칸으로는 비교가 안 된다.
여기서는 **같은 시각 이후**의 실현 손익만 모아 나란히 놓는다.

## 무엇을 세나

    실현    그 시각 이후 **진입한** 거래의 net 합 / 슬롯  (진입 기준 — 교훈#110)
    미실현  지금 열려 있는 자리의 평가손익 / 슬롯
    거래    그 시각 이후 진입 건수 — 빈도가 다르면 총손익이 다르다

⚠ 총손익이 판정 주축이다. 거래당 엣지만 보면 결론이 뒤집힌다.

사용:
    python3 -m scripts.binance.paper_ab                 # 오늘 11:00 KST 부터
    python3 -m scripts.binance.paper_ab --since "2026-09-09 11:00"
"""
from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
KST = "Asia/Seoul"
PAPER = ROOT / "runs" / "kinematics_paper"

# (경로, 이름, 슬롯) — 늘릴 땐 여기만 고친다
TRACKS = [
    # ── 보유 240분 무리 — **실거래와 같은 보유**. 하나씩만 다르다
    ("s3short_h4",    "충격240  imp·240 (기준=실거래)", 3),
    ("s3short_impns", "무손숏3  imp·240·무손절",        3),
    ("s3short_dir",   "방향숏3  dir k=15·240",          3),
    ("s3short_conf",  "확인숏3  impconf k=15·240",      3),
    # ── 보유 대조군 — 보유가 정체성이라 240 으로 안 바꾼다
    ("s3short_imp",   "충격숏3  imp·480 (보유대조)",    3),
    ("s3short_h1",    "충격60   imp·60  (보유대조)",    3),
]


def w(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def pad(s: str, n: int) -> str:
    return s + " " * max(n - w(s), 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="")
    a = ap.parse_args()
    since = (pd.Timestamp(a.since, tz=KST) if a.since
             else pd.Timestamp.now(tz=KST).normalize() + pd.Timedelta(hours=11))
    print(f"■ 페이퍼 A/B — 공통 출발선 {since:%Y-%m-%d %H:%M} KST 이후 (진입 기준)\n")
    hdr = (f"{pad('갈래', 30)}{'거래':>5}{'실현합%':>10}{'자본%':>9}"
           f"{'거래당%':>9}{'승률':>7}{'보유':>6}{'미실현%':>9}")
    print(hdr)
    print("─" * w(hdr))
    for tag, name, slots in TRACKS:
        d = PAPER / tag
        f = d / "trades.csv"
        n_tr, tot, per, wr = 0, 0.0, float("nan"), float("nan")
        if f.exists():
            t = pd.read_csv(f)
            if len(t):
                t["e"] = pd.to_datetime(t.entry_ts, utc=True,
                                        errors="coerce").dt.tz_convert(KST)
                t = t[t.e >= since]
                n_tr = len(t)
                if n_tr:
                    tot = float(t.net_pct.sum())
                    per = float(t.net_pct.mean())
                    wr = 100.0 * float((t.net_pct > 0).mean())
        held, unreal = 0, float("nan")
        sf = d / "state.json"
        if sf.exists():
            try:
                st = json.loads(sf.read_text())
                held = len(st.get("positions", []))
            except Exception:                                   # noqa: BLE001
                pass
        print(f"{pad(name, 30)}{n_tr:>5}{tot:>+10.2f}{tot/slots:>+9.2f}"
              f"{per:>+9.3f}{wr:>6.0f}%{held:>4}/{slots}"
              if n_tr else
              f"{pad(name, 30)}{n_tr:>5}{'—':>10}{'—':>9}{'—':>9}{'—':>7}"
              f"{held:>4}/{slots}")
    print("\n※ 자본% = 실현합 ÷ 슬롯. 총손익이 판정 주축이다 — 거래당만 보면 뒤집힌다.")
    print("※ 진입 기준이다. 청산 기준으로 보면 8시간 보유만큼 시점이 밀린다(교훈#110).")


if __name__ == "__main__":
    main()
