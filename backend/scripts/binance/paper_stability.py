"""운동학 페이퍼 갈래별 **안정성** 표 — 총손익만 보면 순위가 뒤집힌다.

## 왜 필요한가

정기 보고의 `자본%` 는 총손익 순위다. 그런데 41거래짜리 갈래가 1위인데
그 +20.74% 중 **91%가 하루**에서 나온 적이 있다(충격숏3, 2026-09-05).
총손익과 함께 **집중도·낙폭·일별 안정성**을 봐야 승격 판단이 선다.

## 여기서 재는 것

    총손익       Σ stake × net_pct   (복리 아님 — 합산 가능한 자본 기여)
    거래당       net_pct 평균
    상5제외      상위 5% 거래를 뺀 거래당. **꼬리로 버는가**를 가른다
                 ⚠ 올림(ceil)을 쓴다. 보고서는 int(round())라 41건에서 2 vs 3 차이
    양수일       일별 자본기여가 양수인 날 / 전체 날
    최고일제외   총손익 - 최고일 기여. **하루에 몰렸는지** 본다
    일별 t       일별 기여의 t 통계. 겹치지 않는 관측이라 거래 단위 t 보다 정직하다
    MDD          자본곡선 최대 낙폭
    최악         최악 단일 거래 (손절이 걸려 있으면 -STOP_PCT 근처여야 한다)

## 한계

일수가 5 안팎이면 `일별 t` 는 참고값이다. 표본이 얇다는 사실 자체를
`일수` 열로 같이 낸다 — 숫자만 보고 t 를 믿지 마라.

사용:
    python3 -m scripts.binance.paper_stability
    python3 -m scripts.binance.paper_stability --dir runs/kinematics_paper
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

# ⚠ 갈래를 늘리면 **여기도** 고쳐라. 빠지면 표에서 조용히 사라진다.
TAG = {
    "s1": "롱1", "s2both": "속도저울", "s6both": "롱숏3", "s6both_h240": "롱숏3h4",
    "s3short_imp": "충격숏3", "s6both_imp": "충격스프3",
    "s3short_skew": "쏠림숏3", "s6both_skew": "쏠림스프3",
    "s3short_ac1": "뭉침숏3", "s6both_ac1": "뭉침스프3",
    "s3short_rmz": "연속숏3", "s6both_rmz": "연속스프3",
    "s10": "롱10", "s20": "롱20", "s10short": "숏10", "s10both": "롱숏10",
    "s10both_d30": "롱숏d30", "s6both_d5_noise": "잡음6",
    "s10both_d5_utc01": "UTC01", "s6both_sess240": "세션240",
    "s6both_sess480": "세션480", "s10both_sess240n5": "세션240n5",
}


def one(f: Path, name: str) -> dict | None:
    t = pd.read_csv(f)
    if len(t) == 0:
        return None
    t["closed"] = pd.to_datetime(t.closed_ts, utc=True, errors="coerce")
    t = t.dropna(subset=["closed"]).sort_values("closed")
    if len(t) == 0:
        return None
    # 자본 기여 — 복리가 아니라 합산 가능한 양으로 본다
    t["contrib"] = t.stake * t.net_pct
    n = len(t)
    # ⚠ 올림. 20거래 미만에서 int(round()) 는 0 을 내 아무것도 안 뺀다
    k = max(1, int(np.ceil(n * 0.05)))
    day = t.groupby(t.closed.dt.date).contrib.sum()
    nd = len(day)
    sd = day.std(ddof=1) if nd > 1 else np.nan
    eq = (1 + t.contrib / 100).cumprod()
    return {
        "갈래": name, "거래": n,
        "총손익": t.contrib.sum(),
        "거래당": t.net_pct.mean(),
        "상5제외": t.net_pct.sort_values(ascending=False).iloc[k:].mean(),
        "일수": nd, "양수일": int((day > 0).sum()),
        "최고일제외": t.contrib.sum() - day.max(),
        "일별t": (day.mean() / (sd / np.sqrt(nd))
                  if nd > 2 and np.isfinite(sd) and sd > 0 else np.nan),
        "MDD": ((eq / eq.cummax()) - 1).min() * 100,
        "최악": t.net_pct.min(),
    }


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", default="runs/kinematics_paper")
    a = p.parse_args()
    d = ROOT / a.dir
    rows = [r for k, name in TAG.items()
            if (d / k / "trades.csv").exists()
            and (r := one(d / k / "trades.csv", name)) is not None]
    if not rows:
        print(f"원장 없음: {d}")
        return 1
    r = pd.DataFrame(rows).sort_values("총손익", ascending=False)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    print(r.to_string(index=False, float_format=lambda x: f"{x:8.3f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
