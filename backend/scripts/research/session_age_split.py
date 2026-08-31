"""세션 이월 — **상장 나이**로 갈라 잰다. 신규상장 현상인가.

## 왜 (2026-08-31, 대표님 질문에서)

"현재 쓰는 종목들은 최소 1년 이상 차트가 있나" → 유니버스는 99.4%가 1년 이상
(6개월 미만 2종목뿐)이라 괜찮았는데, **오늘 첫 진입 10종목 중 4개가 이력
1.0~1.2년**이었다(ZORA 1.10 · LA 1.23 · SCR 1.04 · PROM 1.04).

우연이 아닐 수 있다 — 아시아 세션에서 ±10~29% 움직이는 종목은 대개 시총이
작고 최근 상장한 쪽이다. 이 트랙엔 신규상장이 별개 현상이라는 교훈이 여러 건
있다([[교훈#78]] 이벤트 코호트 유동성 게이트, [[교훈#99]] 같은 기질에서 분류하라).

**4년 격자에서 상장 나이로 나눠 잰 적이 한 번도 없다.** 결함이다.

    1년 이상 종목에서만 효과가 있으면      세션 이월이 맞다
    최근 상장 종목에서만 있으면            신규상장 현상을 다시 발견한 것

## 규약

⚠ 나이는 **거래 시점 기준**으로 계산한다. 오늘 나이로 과거를 자르면 미래참조다
  — 2023년에 거래할 땐 그 종목이 1년짜리였을 수 있다.
⚠ 상장일은 `ohlcv_1m` 의 종목별 최소 ts. 거래는 5분봉에서 하지만 분류는 같은
  1분봉 기질에서 뽑는다([[교훈#99]] — 다른 기질로 분류하면 커버리지 결손을
  신규상장으로 오독한다).
⚠ 칸은 고정 — 아시아→미주 · 추세스프레드3 · 미주 13-17. 여기서 다시 안 뒤진다.

사용:
  python3 -m scripts.research.session_age_split
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import text                                      # noqa: E402

from app.db.session import engine                                # noqa: E402
from scripts.research.session_combined import (Cfg, SESS_B,      # noqa: E402
                                               sess_returns)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "research_track" / "session_2026_08_31"
log = logging.getLogger("sessage")
BANDS = [(0.0, 1.0, "1년 미만"), (1.0, 2.0, "1~2년"),
         (2.0, 3.0, "2~3년"), (3.0, 99.0, "3년 이상")]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--picks", type=int, default=3)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg()
    t0 = time.time()
    RET, dates, syms = sess_returns(["runs/bars5m_oos", "runs/bars5m"], SESS_B, cfg)
    di = pd.DatetimeIndex(dates)
    log.info("판 날짜 %d · 종목 %d · %.1f분", len(dates), len(syms),
             (time.time()-t0)/60)

    first = {}
    with engine.connect() as c:
        c.execute(text("SET statement_timeout='8s'"))
        for s in syms:
            try:
                r = c.execute(text("SELECT min(ts) FROM ohlcv_1m WHERE symbol=:s"),
                              {"s": s}).scalar()
            except Exception:                                    # noqa: BLE001
                c.rollback(); continue
            if r is not None:
                first[s] = pd.Timestamp(r, tz="UTC")
    log.info("상장일 %d/%d · %.1f분", len(first), len(syms), (time.time()-t0)/60)

    # ⚠ **거래 시점 기준** 나이 (날짜 × 종목). 오늘 나이로 자르면 미래참조다.
    # ⚠⚠ 단위 — pandas 2.x 의 DatetimeIndex 는 **마이크로초**(datetime64[us])로
    #   나올 수 있는데 `Timestamp.value` 는 **언제나 나노초**다. 둘을 int64 로
    #   바꿔 빼면 1,000배 어긋나 나이가 -55년이 된다(2026-08-31 실측).
    #   numpy 날짜 뺄셈은 단위를 자동 승격하므로 그쪽을 쓴다.
    f0 = np.array([first.get(s, pd.Timestamp("2100-01-01", tz="UTC")).to_datetime64()
                   for s in syms])
    AGE = ((di.values[:, None] - f0[None, :])
           / np.timedelta64(1, "D") / 365.25)
    log.info("나이 범위 %.2f ~ %.2f년 · 유한 %.1f%%", np.nanmin(AGE),
             np.nanmax(AGE[np.isfinite(AGE) & (AGE < 50)]),
             100*np.isfinite(AGE).mean())
    A = RET["아시아"].to_numpy(np.float32)
    U = RET["미주"].to_numpy(np.float32)
    N = a.picks
    rows = []
    for lo, hi, lab in BANDS:
        gate = (AGE >= lo) & (AGE < hi)
        sig = np.where(gate, A, np.nan)
        nd = len(di)
        out = np.full(nd, np.nan)
        cnt = np.zeros(nd)
        for i in range(nd):
            ok = np.where(np.isfinite(sig[i]) & np.isfinite(U[i]))[0]
            cnt[i] = len(ok)
            if len(ok) < max(2*N, 20):
                continue
            o = ok[np.argsort(-sig[i][ok])]
            h = float(U[i][o[:N]].mean()); l = float(U[i][o[-N:]].mean())
            out[i] = (h - l)/2.0 - cfg.fee_rt
        v = out[np.isfinite(out)]
        if len(v) < 100:
            log.info("  %-8s 거래 가능일 %d — 표본 부족", lab, len(v))
            rows.append({"나이대": lab, "거래일": len(v), "종목중앙": np.median(cnt),
                         "일평균": np.nan, "날짜t": np.nan, "샤프": np.nan})
            continue
        m, sd = float(v.mean()), float(v.std(ddof=1))
        rows.append({"나이대": lab, "거래일": len(v),
                     "종목중앙": float(np.median(cnt)),
                     "일평균": m, "일중앙": float(np.median(v)),
                     "날짜t": m/(sd/np.sqrt(len(v))),
                     "샤프": m/sd*np.sqrt(365.25),
                     "양수일%": float(100*(v > 0).mean()),
                     "연환산%": m*365.25})
        log.info("  %-8s 거래일 %4d · 종목중앙 %3d → %+.4f · t %+.2f · 샤프 %.2f",
                 lab, len(v), int(np.median(cnt)), m,
                 m/(sd/np.sqrt(len(v))), m/sd*np.sqrt(365.25))
    T = pd.DataFrame(rows)
    print(f"\n■ 세션 이월 — 상장 나이별 (아시아→미주 · 추세스프레드{N} · "
          f"미주 13-17 · 4년 · **거래 시점 기준 나이**)")
    print(T.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    ok = T.dropna(subset=["일평균"])
    if len(ok) > 1:
        print(f"\n  양수인 나이대 {int((ok.일평균 > 0).sum())}/{len(ok)}")
        print("  판정: " + (
            "**모든 나이대에서 양수** — 신규상장 현상이 아니다"
            if (ok.일평균 > 0).all() else
            "**젊은 종목에만 있다** — 신규상장 현상 의심"
            if float(ok.iloc[0].일평균 if len(ok) else 0) > 0
            and (ok.일평균.iloc[1:] <= 0).all() else
            "혼재 — 표를 직접 읽을 것"))
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_csv(OUT / "age_split.csv", index=False)
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
