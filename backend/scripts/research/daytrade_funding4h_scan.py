"""단기 — **4시간 주기 펀딩 정산**이 8시간 정산과 같은 효과를 내는가.

배경 (2026-08-11)
  초단기(초~분) 마켓메이킹 8가설이 전부 닫혔다. 라이브 원장으로 보면 **수수료를
  0 으로 해도** 열 가설 모두 적자다 — 역선택(-3.1~-5.4bp)이 스프레드 획득을
  언제나 넘는다. 이건 수수료 문제가 아니라 **취소 속도** 문제이고, 유료
  코로케이션 없이는 못 푼다.

  그래서 "속도 경쟁이 필요 없는 가장 짧은 것" 을 찾는다. 속도가 필요한 이유는
  둘뿐이다 — (1) 패시브로 서 있다 낡은 호가를 밟히거나 (2) 사라지는 가격을
  남보다 먼저 잡아야 하거나. **사건 시각이 미리 확정돼 있으면 둘 다 없다.**
  아무도 정해진 시각보다 먼저 도착할 수 없다.

발견
  바이낸스 `/fapi/v1/fundingInfo` 실측 (2026-08-11):
      1시간 주기    2종목  (COTIUSDT, PROMUSDT)  → 하루 24 사건
      **4시간 주기 431종목**                     → 하루  6 사건
      8시간 주기  136종목                        → 하루  3 사건
  그런데 우리 페이퍼 러너는 **00/08/16 UTC 만** 본다. 431종목이 04/12/20 UTC
  에도 정산하는데 그 사건을 통째로 버리고 있었다.

무엇을 묻는가
  "추가 경계(04/12/20 UTC)의 정산이 기존 경계(00/08/16)와 같은 효과를 내는가."
  같다면 사건 빈도가 3회/일 → 6회/일 로 두 배가 된다. 통계 판정까지 걸리는
  시간이 절반이 된다.

무엇을 조심하는가
  · **2겹 대조 필수.** 정산 시각 근처의 수익이 정산 때문인지 그냥 그 시간대가
    원래 그런지 갈라야 한다. 같은 종목·같은 시각대의 **비정산일** 을 대조군으로
    쓴다. (1겹 대조는 통과했으나 2겹에서 모멘텀 교란이 드러난 전례가 있다.)
  · **8시간 종목을 위약군으로 쓴다.** 8h 종목은 04/12/20 에 정산하지 않으므로,
    같은 시각에 같은 크기 효과가 나오면 그건 정산 효과가 아니라 시간대 효과다.
    이게 가장 강한 통제다.
  · 표본 단위는 **사건**이지 체결이 아니다. 한 사건 안 수백 종목은 서로 독립이
    아니다 (2026-08-11 교훈). 종목별로 재고 사건 평균을 낸 뒤 사건 단위로 센다.
  · 마찰: 지정가 진입 + 시장가 청산 가정. 메이커 2bp + 테이커 5bp + 스프레드.

사용:
  python3 scripts/research/daytrade_funding4h_scan.py --days 60
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("daytrade_funding4h_scan")

FAPI = "https://fapi.binance.com"
MAKER_BP, TAKER_BP = 2.0, 5.0
BASE_HOURS = (0, 8, 16)        # 모든 무기한이 공유하는 경계
EXTRA_HOURS = (4, 12, 20)      # 4시간 주기 종목만 추가로 정산하는 경계
# 진입/청산 (정산 T 기준 분). 라이브 페이퍼의 early / base 와 맞춘다.
WINDOWS = ((-30, 30), (-15, 15), (-45, 15), (-30, 0), (-30, 60))


def funding_interval_map() -> dict:
    fi = requests.get(f"{FAPI}/fapi/v1/fundingInfo", timeout=30).json()
    ex = requests.get(f"{FAPI}/fapi/v1/exchangeInfo", timeout=30).json()
    per = {s["symbol"] for s in ex["symbols"]
           if s["contractType"] == "PERPETUAL" and s["status"] == "TRADING"}
    out = {s: 8 for s in per}          # fundingInfo 에 없으면 기본 8시간
    for x in fi:
        if x["symbol"] in per and x.get("fundingIntervalHours"):
            out[x["symbol"]] = int(x["fundingIntervalHours"])
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="4시간 주기 펀딩 정산 효과")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--min-dvol-usd", type=float, default=3_000_000)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "daytrade_funding4h_scan.json"))
    args = p.parse_args()

    iv = funding_interval_map()
    n4 = sum(1 for v in iv.values() if v == 4)
    log.info("펀딩 주기: 4시간 %d종목 / 8시간 %d종목",
             n4, sum(1 for v in iv.values() if v == 8))

    files = sorted(glob.glob(os.path.join(args.data_dir, "*_agg1m.joblib")))
    if args.limit:
        files = files[:args.limit]

    # 종목별 · 창별 · 경계군별 수익 (bp). 사건 단위로 모은다.
    #   key = (창, "4h종목/추가경계" 등) → {사건시각: [종목별 bp]}
    acc: dict = {}
    used4 = used8 = 0
    for i, f in enumerate(files, 1):
        sym = os.path.basename(f).replace("_agg1m.joblib", "")
        h = iv.get(sym)
        if h not in (4, 8):
            continue
        try:
            d = joblib.load(f)
        except Exception:
            continue
        d = d[~d.index.duplicated(keep="last")].sort_index()
        d = d.loc[d.index >= d.index.max() - pd.Timedelta(days=args.days)]
        if len(d) < 20000:
            continue
        if d["quote_volume"].resample("1D").sum().median() < args.min_dvol_usd:
            continue
        px = d["px_open"].astype(float)
        sp = float(d["eff_spread_bp_adj"].median())
        fric = MAKER_BP + TAKER_BP + sp          # 지정가 진입 + 시장가 청산
        if h == 4:
            used4 += 1
        else:
            used8 += 1

        idx = px.index
        for hh in BASE_HOURS + EXTRA_HOURS:
            grp = "추가경계" if hh in EXTRA_HOURS else "기존경계"
            tag = f"{h}h종목/{grp}"
            marks = idx[(idx.hour == hh) & (idx.minute == 0)]
            for m in marks:
                for (e0, e1) in WINDOWS:
                    t0, t1 = m + pd.Timedelta(minutes=e0), m + pd.Timedelta(minutes=e1)
                    if t0 not in px.index or t1 not in px.index:
                        continue
                    bp = (px[t1] / px[t0] - 1.0) * 1e4 - fric
                    acc.setdefault(((e0, e1), tag), {}).setdefault(m, []).append(bp)

    log.info("사용 종목: 4시간 %d / 8시간 %d", used4, used8)
    if used4 < 20 or used8 < 10:
        log.error("종목 부족")
        return 1

    rows = []
    for (win, tag), evs in acc.items():
        # 사건 단위: 한 사건 = 그 시각 전 종목의 평균. 종목 간 상관을 접는다.
        ev_means = np.array([float(np.mean(v)) for v in evs.values() if v])
        if len(ev_means) < 30:
            continue
        se = ev_means.std(ddof=1) / np.sqrt(len(ev_means))
        rows.append({"win": f"T{win[0]:+d}/T{win[1]:+d}", "group": tag,
                     "n_events": len(ev_means), "net_bp": float(ev_means.mean()),
                     "se_bp": float(se), "t": float(ev_means.mean() / se) if se else np.nan})

    df = pd.DataFrame(rows)
    print("\n" + "=" * 100)
    print(f"4시간 주기 펀딩 정산 — 사건 단위 / 최근 {args.days}일 / "
          f"마찰(메이커2+테이커5+스프레드) 차감 후")
    print("=" * 100)
    print(f"{'창':<14}{'집단':<20}{'사건':>7}{'net bp':>11}{'오차':>9}{'t':>8}")
    print("-" * 100)
    for w in [f"T{a:+d}/T{b:+d}" for a, b in WINDOWS]:
        sub = df[df.win == w]
        if sub.empty:
            continue
        for _, r in sub.sort_values("group").iterrows():
            print(f"{r.win:<14}{r.group:<20}{r.n_events:>7,}{r.net_bp:>+11.2f}"
                  f"{r.se_bp:>9.2f}{r.t:>+8.2f}")
        print("-" * 100)

    print("\n  ** 결정적 대조 — 추가경계(04/12/20 UTC)에서 두 집단 비교 **")
    print("     4h 종목은 그때 정산하고, 8h 종목은 정산하지 않는다.")
    print("     차이가 나면 정산 효과. 같으면 그냥 시간대 효과다.\n")
    print(f"  {'창':<14}{'4h종목':>12}{'8h종목(위약)':>15}{'차이':>11}{'차이 t':>10}")
    print("  " + "-" * 62)
    for w in [f"T{a:+d}/T{b:+d}" for a, b in WINDOWS]:
        a = df[(df.win == w) & (df.group == "4h종목/추가경계")]
        b = df[(df.win == w) & (df.group == "8h종목/추가경계")]
        if a.empty or b.empty:
            continue
        a, b = a.iloc[0], b.iloc[0]
        diff = a.net_bp - b.net_bp
        se = float(np.hypot(a.se_bp, b.se_bp))
        print(f"  {w:<14}{a.net_bp:>+12.2f}{b.net_bp:>+15.2f}{diff:>+11.2f}"
              f"{diff / se if se else np.nan:>+10.2f}")
    print()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"days": args.days, "n_sym_4h": used4, "n_sym_8h": used8,
                   "rows": rows}, fh, indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
