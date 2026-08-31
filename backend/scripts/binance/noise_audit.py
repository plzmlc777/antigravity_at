"""잡음 필터 페이퍼 — **사이클마다** 무작위 선별과 대어 쌓는다.

## 왜 (2026-08-31)

첫 사이클이 거래당 +2.459% · 승률 67% 로 나왔다. 그런데 여섯 자리가 전부
**같은 시각**이라 사건은 하나였고, 좋게 나온 걸 보고 나서 무작위 검정을 돌렸다.
그렇게 얻은 p 0.0001 은 고르고 난 뒤의 값이라 못 쓴다.

고칠 것은 값이 아니라 절차다. **모든 사이클에 같은 검정을 자동으로 붙인다.**
사건 하나하나의 p 를 쌓으면 편향이 안 들어간 기록이 된다.

## 무엇을 재나

사이클(같은 entry_ts)마다 그 보유 창 동안:

    유니버스     틱에서 살아있는 종목 전부의 수익률
    실측 벌림    고른 롱 평균 - 고른 숏 평균
    무작위 벌림  같은 수의 종목을 무작위로 뽑아 같은 계산을 1만 번
    p            무작위가 실측 이상인 비율

⚠ 첫 사이클 실측: **롱 다리 초과 +0.07%p · 숏 다리 -5.23%p**. 롱은 유니버스
  중앙과 같았고 숏이 전부였다. 다리별로 갈라서 봐야 이게 보인다.
⚠ 종목 수익은 **거래 손익과 다르다** — 숏은 (진입-청산)/진입 이고 펀딩이 붙는다
  (교훈#89). 여기서는 선별을 재는 것이라 **종목 수익**으로 계산한다.

사용:
  python3 -m scripts.binance.noise_audit
  python3 -m scripts.binance.noise_audit --tag s10both --reps 20000
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TICKS = ROOT / "runs" / "ticks"
LEDGERS = ROOT / "runs" / "kinematics_paper"
log = logging.getLogger("noise_audit")


def universe_ret(a: pd.Timestamp, b: pd.Timestamp, min_ticks: int = 50
                 ) -> pd.Series:
    """보유 창 동안 살아있던 종목 전부의 수익률(%)."""
    a_ms, b_ms = int(a.timestamp()*1000), int(b.timestamp()*1000)
    out = {}
    for d in sorted(TICKS.iterdir()):
        if not d.is_dir():
            continue
        fs = sorted(d.glob("*.parquet"))
        if not fs:
            continue
        try:
            t = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price"])
                           for f in fs[-3:]], ignore_index=True)
        except Exception:                                       # noqa: BLE001
            continue
        t = t[(t.ts_ms >= a_ms - 60_000) & (t.ts_ms <= b_ms + 60_000)]
        if len(t) < min_ticks:
            continue
        p0 = t.price[t.ts_ms <= a_ms]
        p1 = t.price[t.ts_ms <= b_ms]
        if p0.empty or p1.empty:
            continue
        out[d.name] = 100.0*(p1.iloc[-1]/p0.iloc[-1] - 1.0)
    return pd.Series(out, dtype=float)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tag", default="s6both_d5_noise")
    p.add_argument("--reps", type=int, default=10_000)
    p.add_argument("--seed", type=int, default=20260831)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    led = LEDGERS / a.tag / "trades.csv"
    if not led.exists():
        raise SystemExit(f"원장이 없다: {led}")
    T = pd.read_csv(led)
    T["entry_ts"] = pd.to_datetime(T.entry_ts, utc=True)
    T["exit_ts"] = pd.to_datetime(T.exit_ts, utc=True)
    rng = np.random.default_rng(a.seed)

    rows = []
    for ts, g in T.groupby("entry_ts"):
        b = g.exit_ts.max()
        U = universe_ret(ts, b)
        if len(U) < 50:
            log.warning("%s 유니버스 %d종목 — 건너뜀(틱 없음)", ts, len(U))
            continue
        L = g.symbol[~g.short].tolist(); S = g.symbol[g.short].tolist()
        lr = U.reindex(L).dropna(); sr = U.reindex(S).dropna()
        if lr.empty or sr.empty:
            continue
        obs = lr.mean() - sr.mean()
        v = U.to_numpy(); k = len(lr) + len(sr)
        d = np.empty(a.reps)
        for i in range(a.reps):
            ix = rng.choice(len(v), k, replace=False)
            d[i] = v[ix[:len(lr)]].mean() - v[ix[len(lr):]].mean()
        rows.append({
            "진입": ts.tz_convert("Asia/Seoul").strftime("%m-%d %H:%M"),
            "보유분": int((b - ts).total_seconds()//60),
            "종목": len(U), "롱": len(lr), "숏": len(sr),
            "중앙": float(U.median()),
            "롱초과": float(lr.mean() - U.median()),
            "숏초과": float(U.median() - sr.mean()),
            "벌림": float(obs), "무작위중앙": float(np.median(d)),
            "p": float((d >= obs).mean()),
            "실현": float(g.net_pct.mean())})
    if not rows:
        raise SystemExit("잴 사이클이 없다 — 틱 보관이 원장 구간을 덮는지 확인하라")
    R = pd.DataFrame(rows)
    print(f"\n■ 사이클별 선별 감사 — {a.tag} · 무작위 {a.reps:,}회")
    print(R.to_string(index=False, float_format=lambda z: f"{z:+.3f}"))
    n = len(R)
    print(f"\n  사이클 {n}건 · 벌림 중앙 {R.벌림.median():+.3f}%p "
          f"· 양수 {int((R.벌림>0).sum())}/{n}")
    print(f"  롱초과 중앙 {R.롱초과.median():+.3f}%p "
          f"· 숏초과 중앙 {R.숏초과.median():+.3f}%p")
    # 사이클 p 를 합친다 — 균등이면 우연, 0 쪽으로 쏠리면 선별에 값어치가 있다
    print(f"  p 중앙 {R.p.median():.4f} · p<0.05 인 사이클 "
          f"{int((R.p<0.05).sum())}/{n} (우연이면 기대 {0.05*n:.1f})")
    if n < 10:
        print(f"\n  ⚠ 사이클 {n}건이다. 방향을 말할 표본이 아니다 — 쌓는 중.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
