"""국면 기질 — **신호와 무관한** 시장 눈금을 한 번 만들어 두고 계속 쓴다.

## 왜 (2026-08-25)

"어떤 장에서 되고 안 되는가"를 세 번 물어 세 번 다 닫혔다.
    · 전략 자신의 과거 성과로 스위치      위약 p 0.112 (항상거래보다 낮음)
    · 외부 시장 지표 6종 (BTC 수익·변동성) 위약 p 0.438
    · 거래 단위 특성 12종                 하루가 익절의 68% 라 전부 그 날의 대리변수

네 번째로 **위약(rotate)** 을 눈금으로 써봤더니 해석이 명확했다 — 단위·종목·
마찰이 전략과 완벽히 짝지어지기 때문이다. 그런데 두 가지가 막았다.

  ① rotate 는 **신호를 시간축에서 민 것**이라 위약도 신호 근처에만 생긴다.
     실측: 2025-10월 실측 367거래인데 위약 **12건**. 가장 중요한 달의 국면을
     못 쟀다. 어떤 달은 아예 0건이라 "위약 0.000 = 횡보"로 처리됐는데 그건
     측정이 아니라 **결측**이다.
  ② 저장된 위약 24만 건은 설정이 제각각이다(5m/15m/30m · 익절 5~8% ·
     손절 0.3~1.5% · 보유 24~48h). 같은 순간이라도 **규칙이 다르면 수익률이
     다르다** — 국면이 아니라 규칙 차이를 재게 된다.

그래서 **격자 진입**으로 다시 만든다. 신호를 안 본다. 모든 종목·모든 봉에서
앞으로 얼마를 주는지 재서 (종목, 날짜) 로 접는다.

## 무엇을 담나

    symbol, date, n_bars, ret_day, vol_day, fwd_6h, fwd_24h, fwd_48h,
    up_6h, up_24h, up_48h          (선도수익률이 양수인 봉의 비율)

⚠ **익절·손절·보유를 쓰지 않는다.** 그래서 전략 설정과 무관하다. 어떤 전략이든
  자기가 거래한 (종목, 날짜) 를 골라 평균 내면 그 전략에 맞는 눈금이 된다.
  규칙을 넣으면 이 기질도 설정에 묶여 재사용이 안 된다.

⚠ 미래참조 아님 — 이건 **진단용 기질**이지 신호가 아니다. 선도수익률은 정의상
  미래를 본다. 거래 규칙에 쓰면 안 되고, "그때 시장이 뭘 줬나"를 사후에
  읽는 용도다.

사용:
  python3 -m scripts.research.build_regime_baseline \
      --universe configs/rsi_paper_universe.txt --from 2022-08-01 --to 2026-08-26
  python3 -m scripts.research.build_regime_baseline --smoke 3      # 예비비행
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research.rsi_tp_sl_harness import load_1m_resampled  # noqa: E402

log = logging.getLogger("regime_base")
OUT = Path(__file__).resolve().parents[2] / "runs" / "research_track" / "regime"
# 30분봉 기준 앞으로 몇 봉인가
HORIZONS = {"6h": 12, "24h": 48, "48h": 96}
# 가장 긴 지평(96봉=48h) + 하루(48봉). 이보다 짧으면 선도가 하나도 안 여문다.
MIN_BARS = max(HORIZONS.values()) + 48


def one(args) -> pd.DataFrame | None:
    sym, tf, a, b = args
    try:
        bars = load_1m_resampled(sym, tf, 100, a, b)
    except Exception as e:                                     # noqa: BLE001
        log.debug("%s 적재 실패: %s", sym, e)
        return None
    # ⚠ 최소 봉수는 **선도 지평에서 유도한다**. 200 을 박아뒀다가 일일 갱신
    #   (4일 = 192봉)이 통째로 걸러졌다(2026-08-25). 가장 긴 지평 + 하루면
    #   최소한 하루치는 여문 선도값이 나온다.
    if bars is None or len(bars) < MIN_BARS:
        return None
    c = bars["close"].astype(float)
    d = pd.DataFrame(index=bars.index)
    d["date"] = bars.index.normalize()
    d["ret"] = c.pct_change()
    for lab, k in HORIZONS.items():
        # 앞으로 k봉 뒤 종가 대비 — **진단용**이라 미래를 본다(신호 아님)
        d[f"fwd_{lab}"] = (c.shift(-k) / c - 1.0) * 100.0
    g = d.groupby("date")
    out = pd.DataFrame({
        "n_bars": g.size(),
        "ret_day": g["ret"].apply(lambda s: 100.0 * ((1 + s.fillna(0)).prod() - 1)),
        "vol_day": g["ret"].std() * 100.0 * np.sqrt(48),
    })
    for lab in HORIZONS:
        out[f"fwd_{lab}"] = g[f"fwd_{lab}"].mean()
        out[f"up_{lab}"] = g[f"fwd_{lab}"].apply(lambda s: 100.0 * (s > 0).mean())
    out = out.reset_index()
    out.insert(0, "symbol", sym)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_paper_universe.txt")
    p.add_argument("--symbols", default="")
    p.add_argument("--tf", default="30m")
    p.add_argument("--from", dest="d_from", default="2022-08-01")
    p.add_argument("--to", dest="d_to", default="")
    p.add_argument("--workers", type=int, default=5)
    p.add_argument("--smoke", type=int, default=0,
                   help="N종목만 돌려 경로를 먼저 확인한다(2026-08-21 교훈)")
    p.add_argument("--out", default="")
    p.add_argument("--merge", action="store_true",
                   help="기존 표에 이어 붙인다(일일 갱신). (symbol,date) 중복은 "
                        "**새 값 우선** — 선도수익률이 여물면서 바뀌기 때문이다")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if a.symbols:
        syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    else:
        syms = [s.strip().upper() for s in Path(a.universe).read_text().split()
                if s.strip()]
    if a.smoke:
        syms = syms[:a.smoke]
    to = a.d_to or time.strftime("%Y-%m-%d")
    log.info("국면 기질 — %d종목 · %s · %s ~ %s · 워커 %d",
             len(syms), a.tf, a.d_from, to, a.workers)

    t0 = time.time()
    parts, empty = [], 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, r in enumerate(ex.map(one, [(s, a.tf, a.d_from, to) for s in syms]), 1):
            if r is None:
                empty += 1
            else:
                parts.append(r)
            if i % 25 == 0 or i == len(syms):
                el = time.time() - t0
                log.info("[%d/%d] 행 %s · %.0f분 · 남은 %.0f분", i, len(syms),
                         f"{sum(len(x) for x in parts):,}", el / 60,
                         (len(syms) - i) * el / i / 60)
    if not parts:
        raise SystemExit(
            f"한 종목도 못 만들었다 — 구간 {a.d_from} ~ {to} 가 "
            f"최소 {MIN_BARS}봉({MIN_BARS/48:.1f}일)보다 짧은지 확인하라. "
            f"일일 갱신은 최소 {MIN_BARS/48+1:.0f}일 이상으로 잡아야 한다.")
    R = pd.concat(parts, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / f"regime_baseline_{a.tf}.csv"
    if a.merge and path.exists():
        # 일일 갱신 — 기존 표에 이어 붙이고 (symbol, date) 로 **새 값 우선**.
        # ⚠ 선도수익률은 시간이 지나야 여문다. 최근 며칠은 다시 계산해서
        #   덮어야 NaN 이 진짜 값으로 바뀐다 — 그래서 `keep="last"` 다.
        old_df = pd.read_csv(path)
        old_df["date"] = pd.to_datetime(old_df["date"])
        R["date"] = pd.to_datetime(R["date"])
        before = len(old_df)
        R = (pd.concat([old_df, R], ignore_index=True)
               .drop_duplicates(subset=["symbol", "date"], keep="last")
               .sort_values(["symbol", "date"]))
        log.info("병합 — 기존 %s행 + 새 %s행 → %s행",
                 f"{before:,}", f"{len(parts)}묶음", f"{len(R):,}")
    R.to_csv(path, index=False)
    log.info("저장 %s — %s행 · 종목 %d · 날짜 %d · 데이터없음 %d · %.0f분",
             path, f"{len(R):,}", R.symbol.nunique(), R.date.nunique(), empty,
             (time.time() - t0) / 60)

    # 요약 — 만들자마자 눈으로 확인한다
    R["date"] = pd.to_datetime(R.date)
    m = R.assign(ym=R.date.dt.to_period("M")).groupby("ym").agg(
        종목=("symbol", "nunique"), 종목일=("symbol", "size"),
        fwd48=("fwd_48h", "mean"), up48=("up_48h", "mean"),
        일변동성=("vol_day", "median"))
    print("\n■ 월별 국면 눈금 (마지막 14개월)")
    print(m.tail(14).round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
