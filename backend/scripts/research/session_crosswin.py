"""세션 격자 두 창 **맞대기** — 같은 칸이 양쪽에서 이기는가.

## 왜 (2026-08-31)

각 창의 최고값끼리 비교하면 안 된다. 창마다 108칸 중 최고를 고른 뒤라 서로 다른
칸을 비교하게 된다 — 실제로 그랬다:

    본표본 2024-2026   아시아→미주 · **상위롱** · 5   +0.2935  t 1.76
    표본밖 2022-2024   아시아→유럽 · **하위롱** · 3   +0.2035  t 2.17

쌍도 다리도 다르고 **방향이 반대**다(추세 대 반전). 판정은 칸을 짝지어야 나온다.

## 재는 것

    ① 108칸 짝지은 상관 — 한 창에서 좋았던 칸이 다른 창에서도 좋은가
    ② 각 창 상위 10칸이 반대 창에서 몇 등인가
    ③ 부호 일치율 — 우연이면 50%
    ④ 창별 최고칸을 **반대 창에서** 읽은 값 (이게 진짜 표본밖 성적)

⚠ `초과`(방향맞춤 위약 대비)로도 같이 본다. 야간 세션은 그 자체로 상승 편향이
  있어(위약 +0.050) 일평균만 보면 야간 칸이 전부 위로 올라온다.

사용:
  python3 -m scripts.research.session_crosswin
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "runs" / "research_track" / "session_2026_08_31"
KEY = ["신호", "거래", "종목", "다리"]
log = logging.getLogger("crosswin")


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    A = pd.read_csv(D / "xsec_is.csv")      # 2024-2026 · 240종목
    B = pd.read_csv(D / "xsec_oos.csv")     # 2022-2024 · 125종목
    M = A.merge(B, on=KEY, suffixes=("_본", "_밖"))
    n = len(M)
    print(f"■ 두 창 맞대기 — 짝지은 칸 {n} "
          f"(본 {len(A)} · 밖 {len(B)})")

    for col in ("일평균", "초과", "날짜t"):
        a, b = M[f"{col}_본"], M[f"{col}_밖"]
        rp = float(a.corr(b))
        rs = float(a.corr(b, method="spearman"))
        agree = float(((a > 0) == (b > 0)).mean())
        print(f"\n  [{col}]  피어슨 {rp:+.3f} · 스피어만 {rs:+.3f} "
              f"· 부호일치 {100*agree:.1f}% (우연 50%)")
        both = int(((a > 0) & (b > 0)).sum())
        print(f"    양쪽 양수 {both}/{n} · 본만 {int(((a>0)&(b<=0)).sum())} "
              f"· 밖만 {int(((a<=0)&(b>0)).sum())} "
              f"· 양쪽 음수 {int(((a<=0)&(b<=0)).sum())}")

    for src, dst, lab in (("본", "밖", "본표본"), ("밖", "본", "표본밖")):
        M2 = M.sort_values(f"초과_{src}", ascending=False).head(10)
        rank = M[f"초과_{dst}"].rank(ascending=False)
        print(f"\n■ {lab} 상위 10칸이 반대 창에서 (초과 기준 · {n}칸 중 등수)")
        for r in M2.itertuples():
            k = (M[KEY[0]] == getattr(r, "신호")) & (M[KEY[1]] == getattr(r, "거래")) \
                & (M[KEY[2]] == getattr(r, "종목")) & (M[KEY[3]] == getattr(r, "다리"))
            print(f"  {r.신호}→{r.거래} {r.다리}{r.종목:<3d} "
                  f"{src} {getattr(r, f'초과_{src}'):+.4f} → "
                  f"{dst} {getattr(r, f'초과_{dst}'):+.4f} "
                  f"(일평균 {getattr(r, f'일평균_{dst}'):+.4f} · "
                  f"t {getattr(r, f'날짜t_{dst}'):+.2f} · "
                  f"등수 {int(rank[k].iloc[0])})")

    print("\n■ 양쪽 모두 초과 양수이면서 합이 큰 칸 (교집합)")
    both = M[(M.초과_본 > 0) & (M.초과_밖 > 0)].copy()
    both["합"] = both.초과_본 + both.초과_밖
    both = both.sort_values("합", ascending=False).head(12)
    cols = KEY + ["일평균_본", "날짜t_본", "초과_본",
                  "일평균_밖", "날짜t_밖", "초과_밖", "합"]
    print(both[cols].to_string(index=False, float_format=lambda z: f"{z:+.4f}")
          if len(both) else "  없음")
    M.to_csv(D / "crosswin.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
