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
# A/B 개시 — 무손숏3·방향숏3·확인숏3 를 띄워 기준과 나란히 세운 시각
AB_START = pd.Timestamp("2026-09-09 11:00", tz=KST)

# (경로, 이름, 슬롯) — 늘릴 땐 여기만 고친다
TRACKS = [
    # ── 보유 240분 무리 — **실거래와 같은 보유**. 하나씩만 다르다
    ("s3short_h4",    "충격240  imp·240 (구 기준·만기냉각 없음)", 3),
    # 2026-09-12 대표님 지시 — 만기 청산에도 240분 냉각. **라이브가 이쪽으로 옮겨졌다.**
    ("s3short_h4ec",  "충격240냉 imp·240·만기냉각 (기준=실거래)", 3),
    # 2026-09-12 대표님 지시 — 신선도 창 0,3-5. **라이브가 이쪽으로 옮겨졌다.**
    #   위 h4ec 와 창 하나만 다른 쌍둥이다 — 둘을 나란히 봐야 창을 판별한다.
    ("s3short_h4st",  "충격240신선 imp·240·냉각·창0,3-5 (기준=실거래)", 3),
    # 2026-09-13 대표님 지시 — 가격 신선도(이미 먹힌 몫 5% 초과 배제).
    #   **라이브가 이쪽으로 옮겨졌다.** h4ec 와 이 필터 하나만 다르다.
    ("s3short_h4sp",  "충격240가격 imp·240·냉각·먹힌몫≤5% (기준=실거래)", 3),
    ("s3short_impns", "무손숏3  imp·240·무손절",        3),
    ("s3short_dir",   "방향숏3  dir k=15·240",          3),
    ("s3short_conf",  "확인숏3  impconf k=15·240 (꺾임)", 3),
    ("s3short_anti",  "역확인3  impanti k=15·240 (상승)", 3),
    # ── 보유 대조군 — 보유가 정체성이라 240 으로 안 바꾼다
    # 2026-09-13 대표님 지시 — **계좌 8 실거래로 승격.** RSI 극단(30m)을
    #   내리고 이 갈래를 올렸다. 페이퍼는 대조군으로 계속 돈다.
    ("s3short_imp",   "충격숏3  imp·480 (보유대조)",    3),
    ("s3short_h1",    "충격60   imp·60  (보유대조)",    3),
    # ── 양다리 대조 — 슬롯 6(롱3+숏3). 숏만 vs 롱숏 헤지를 본다.
    #   6년 검정: 숏↔롱 상관 −0.389(헤지는 진짜)이나 롱 기대수익이 −0.030%/일
    #   이라 반반 혼합 시 샤프 0.0526 → 0.0442 로 떨어진다.
    ("s6both_imp",    "충격스프3 imp·480·롱3숏3",       6),
    # ── 2026-09-15 대표님 승인 — 교체 후보 풀에 넣으면서 **이름을 여기 등재**한다.
    #   `_rotate.py` 의 BR 과 **같은 짧은 이름**을 쓴다. 두 곳이 갈리면
    #   보고가 엉뚱한 갈래를 가리킨다(인계문 §6 함정).
    ("s6both_h240",   "s6양다리 kine·240·롱3숏3",      6),
    ("s2both",        "s2양다리 kine·120·롱1숏1",      2),
    ("s10both",       "s10양다리 kine·120·롱5숏5",     10),
    ("s6both_ac1",    "체결자기여기 ac1·480·롱3숏3",    6),
    ("s3short_rmz",   "최장연속숏 rmz·480",            3),
    ("s10both_d5_utc01",   "되돌림UTC1 rev·120·UTC1시·지연5",   10),
    # 2026-09-15 롱 축 발굴 — utc01 에서 `--entry-hour` 하나만 뺐다.
    ("s10both_d5_revcont", "되돌림연속 rev·120·연속진입·지연5", 10),
]


def w(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def pad(s: str, n: int) -> str:
    return s + " " * max(n - w(s), 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="")
    a = ap.parse_args()
    # ⚠ 기본값은 **A/B 개시 시각 고정**이다. "오늘 11:00" 으로 두면 날이 바뀌는
    #   순간 전 갈래가 0건으로 나와 보고가 통째로 빈다(2026-09-10 아침 실제 발생).
    #   비교의 출발선은 달력이 아니라 실험이 시작된 날이다.
    since = pd.Timestamp(a.since, tz=KST) if a.since else AB_START
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
    # ── 충격스프3 다리별 — 숏만(충격240) 대비 헤지가 실제로 먹는지 본다
    #   6년 검정: 상관 −0.389 · 숏 손해일에 롱 +1.575%(63%가 이익).
    f = PAPER / "s6both_imp" / "trades.csv"
    if f.exists():
        t = pd.read_csv(f)
        if len(t):
            t["e"] = pd.to_datetime(t.entry_ts, utc=True,
                                    errors="coerce").dt.tz_convert(KST)
            t = t[t.e >= since]
            if len(t):
                sh = t["short"].astype(bool)
                print(f"\n  충격스프3 다리별 — 숏 {int(sh.sum())}건 "
                      f"{t[sh].net_pct.sum():+.2f}% · 롱 {int((~sh).sum())}건 "
                      f"{t[~sh].net_pct.sum():+.2f}%")

    # ── 승격 후보 대조 (2026-09-09 대표님 지시)
    #
    # 아카이브가 아무리 좋아도 **페이퍼 전진 성적 없이는 승격하지 않는다.**
    # 6년 검정에서 확인숏의 방향 성분이 1위(+0.257)였지만 그것은 근거가
    # 아니다 — 여기 숫자가 근거다. 기준은 **현행 실거래 규칙**이다.
    print("\n■ 승격 후보 대조 — 기준(충격240 = 현행 실거래 규칙) 대비")
    base = None
    for tag, name, slots in TRACKS:
        if tag not in ("s3short_h4", "s3short_conf", "s3short_anti"):
            continue
        f = PAPER / tag / "trades.csv"
        n_tr, cap = 0, 0.0
        if f.exists():
            t = pd.read_csv(f)
            if len(t):
                t["e"] = pd.to_datetime(t.entry_ts, utc=True,
                                        errors="coerce").dt.tz_convert(KST)
                t = t[t.e >= since]
                n_tr = len(t)
                cap = float(t.net_pct.sum()) / slots if n_tr else 0.0
        if base is None:
            base = cap
            gap = "  (기준)"
        else:
            gap = f"  기준대비 {cap - base:+7.2f}%p"
        short = name.split()[0]
        print(f"  {pad(short, 10)}{n_tr:>4}건   자본 {cap:>+7.2f}%{gap}")
    print("  ⚠ 표본이 찰 때까지(실측 SD 기준 약 30일) 순위를 읽지 마라.")

    print("\n※ 자본% = 실현합 ÷ 슬롯. 총손익이 판정 주축이다 — 거래당만 보면 뒤집힌다.")
    print("※ 진입 기준이다. 청산 기준으로 보면 8시간 보유만큼 시점이 밀린다(교훈#110).")


if __name__ == "__main__":
    main()
