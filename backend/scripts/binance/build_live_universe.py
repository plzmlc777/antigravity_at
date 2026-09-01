"""실거래 유니버스 — 죽은 종목을 걷어내고 **여문 신규 상장을 편입한다**.

## 왜 (2026-08-27 최초 · 2026-08-31 정책 개정)

처음엔 **부분집합만** 만들었다. 틱 수집기가 377종목 중 360개만 받았고 빠진 17개가
전부 거래소에서 죽은 것이어서(SETTLING 15 · 목록 삭제 2), 죽은 것만 걷어내면
됐다. 새로 상장한 종목은 넣지 않았다 — 배포된 전략이 그 377종목에서 검증됐기
때문이다.

**2026-08-31 대표님 지시로 자동 편입으로 바꾼다.** 근거는 실측이다.

세션 이월 전략(아시아→미주)에서 확인된 것:

    유니버스 359종목 중 357개가 1년 이상인데
    **전략이 뽑는 6종목의 중앙 나이는 0.95년** (유니버스 중앙 1.49년)
    뽑힌 종목의 60.8% 가 1년 미만

    뽑힌 종목 중 1년 미만 **비율**로 날짜를 가르면
      33%  →  일평균 **-0.097%**
      67%  →  +0.077%
      83%  →  **+0.270%**  (t 2.22)

신규 상장을 안 넣으면 종목이 계속 늙어 위 표의 -0.097 구간으로 이동한다.
**유니버스 갱신이 이 전략의 전제 조건이다.**

## 왜 7일인가 (문턱도 실측으로 정했다)

문턱 미만을 후보에서 빼고 4년(1,473일) 전략을 돌린 결과:

    문턱     후보중앙   일평균     t     샤프   연환산
      0일      125    +0.0835  +1.41  +0.70  +30.5%
      7일      125    +0.0628  +1.08  +0.54  +22.9%
     14일      125    +0.0623  +1.07  +0.54  +22.8%
     30일      123    +0.0514  +0.88  +0.44  +18.8%
     60일      123    +0.0071  +0.13  +0.07   +2.6%
     90일      120    -0.0297  -0.56  -0.29  -10.9%
    365일       85    -0.0512  -0.95  -0.55  -18.7%

**문턱을 올릴수록 단조롭게 나빠지고 90일에서 부호가 뒤집힌다.** 데이터만 보면
0일이 최선이다. 그럼에도 7일을 두는 이유는 **백테스트가 못 재는 비용** 때문이다 —
상장 당일 코인의 호가 스프레드·체결 깊이는 왕복 0.072% 가정을 못 지킨다
(교훈#82: 괴리는 제 통행료만큼 벌어진다). 7일이면 세션을 일곱 번 돌아 호가가
자리를 잡고 엣지는 75% 가 남는다.

⚠ 상장 첫 주 변동성은 실제로 크다 — 미주 세션 |수익| 중앙 1.92%(1년 이상은
  1.18%) · 99분위 **19.5%**(1년 이상 8.5%). 다만 **문턱을 올려도 최악의 날은
  -13.62% 로 그대로**였다. 꼬리 위험은 신규 상장에서 오지 않는다.
⚠ **30일 이상은 쓰지 마라.** 엣지의 38% 를 잃고 60일이면 사실상 0 이 된다.

## 두 유니버스를 가른다

    configs/rsi_paper_universe.txt   **연구용 — 얼리지 않는다**
        백테스트 결과가 이 목록에 묶여 있다. 여기에는 아무것도 더하지 않는다.

    configs/rsi_live_universe.txt    **실계좌 전용 — 부분집합만**
        `rsi-30m-LIVE`(계좌 8 · 레버리지 2)가 이 파일을 읽는다. 여기에 신규를
        넣으면 **실거래가 검증한 적 없는 종목을 거래한다**. 편입은 대표님이
        따로 결정할 사안이라 `--no-add` 로 옛 정책을 유지한다.

    configs/binance_collect_universe.txt  **틱 수집·페이퍼 — 신규 편입 적용**
        (연구 목록 ∪ 여문 신규 상장) ∩ status=TRADING · PERPETUAL · USDT
        → 연구 목록의 **부분집합이 아니다**

⚠ 빠지는 종목도 **들어오는 종목도** 세어서 남긴다. 조용히 변하면 나중에 성과
  차이를 종목 탓으로 못 돌린다. 감소·증가가 크면 쓰지 않고 죽는다.
⚠ 새로 들어온 종목은 틱 수집기가 붙고 **약 14시간** 뒤부터 신호가 나온다
  (운동학 신호가 790분을 되돌아본다). 편입 당일에는 안 뽑힌다.

사용:
  python3 -m scripts.binance.build_live_universe            # 점검만
  python3 -m scripts.binance.build_live_universe --write
  python3 -m scripts.binance.build_live_universe --min-age-days 14 --write
                                              # ⚠ **기본값은 7일**이다.
                                              #   위는 문턱을 바꿔 쓰는 예시
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAPI = "https://fapi.binance.com/fapi/v1/exchangeInfo"

log = logging.getLogger("live_uni")


def exchange_info() -> dict[str, dict]:
    with urllib.request.urlopen(FAPI, timeout=30) as r:
        d = json.load(r)
    return {x["symbol"]: x for x in d["symbols"]}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", default="configs/rsi_paper_universe.txt",
                   help="연구 유니버스 — 이 파일은 **건드리지 않는다**")
    p.add_argument("--out", default="configs/rsi_live_universe.txt")
    p.add_argument("--write", action="store_true", help="없으면 점검만")
    p.add_argument("--min-age-days", type=int, default=7,
                   help="신규 상장은 이만큼 여문 뒤 편입한다. 4년 실측에서 "
                        "0일이 최선이고 30일 이상은 엣지의 38%%를 잃는다 — "
                        "7일은 호가가 자리잡을 시간만 준 값이다")
    p.add_argument("--no-add", action="store_true",
                   help="옛 정책(부분집합만). 편입을 끄고 죽은 종목만 걷어낸다")
    p.add_argument("--max-drop-pct", type=float, default=15.0,
                   help="이보다 많이 빠지면 쓰지 않고 죽는다 — 거래소 응답 이상 방어")
    p.add_argument("--max-add-pct", type=float, default=20.0,
                   help="이보다 많이 들어오면 쓰지 않고 죽는다 — 같은 방어")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    src = ROOT / a.source
    research = [s.strip().upper() for s in src.read_text().split() if s.strip()]
    info = exchange_info()
    if len(info) < 100:
        raise SystemExit(f"거래소 목록이 {len(info)}개뿐이다 — 응답이 이상하다")

    now = datetime.datetime.now(datetime.UTC)
    cutoff = now - datetime.timedelta(days=a.min_age_days)

    def onboard(x) -> datetime.datetime | None:
        v = x.get("onboardDate")
        return (datetime.datetime.fromtimestamp(v/1000, datetime.UTC)
                if v else None)

    # ── ① 연구 목록에서 살아 있는 것 ─────────────────────
    keep, dead = [], []
    for s in research:
        x = info.get(s)
        if x is None:
            dead.append((s, "목록에 없음", ""))
        elif x.get("status") != "TRADING":
            ob = onboard(x)
            dead.append((s, x["status"], str(ob.date()) if ob else ""))
        else:
            keep.append(s)

    # ── ② 여문 신규 상장 ────────────────────────────────
    #   ⚠ 무기한(PERPETUAL) · USDT 정산만. 분기물·코인마진이 섞이면 전략이
    #     본 적 없는 상품을 거래하게 된다.
    added, skipped = [], []
    if not a.no_add:
        known = set(research)
        for s, x in info.items():
            if s in known or x.get("status") != "TRADING":
                continue
            if x.get("contractType") != "PERPETUAL":
                continue
            if x.get("quoteAsset") != "USDT" or x.get("marginAsset") != "USDT":
                continue
            ob = onboard(x)
            if ob is None or ob > cutoff:
                continue
            # ⚠ 종목명이 디렉터리·파일명·CSV 열로 쓰인다. 비ASCII 티커가 실제로
            #   상장돼 있다(币安人生·我踏马来了·龙虾). **조용히 빼지 말고** 남긴다.
            if not re.fullmatch(r"[A-Z0-9]+USDT", s):
                skipped.append((s, ob))
                continue
            added.append((s, ob, (now - ob).days))

    drop_pct = 100.0 * len(dead) / max(len(research), 1)
    add_pct = 100.0 * len(added) / max(len(keep), 1)
    log.info("연구 %d종목 → 살아있음 %d · 제외 %d (%.1f%%) · "
             "신규 편입 %d (%.1f%%) · 나이 문턱 %d일",
             len(research), len(keep), len(dead), drop_pct, len(added),
             add_pct, a.min_age_days)
    for s, st, ob in dead:
        log.info("  제외 %-16s %-14s %s", s, st, ob)
    for s, ob, age in sorted(added, key=lambda z: z[1]):
        log.info("  편입 %-16s 상장 %s · %d일", s, ob.date(), age)
    for s, ob in sorted(skipped, key=lambda z: z[1]):
        log.info("  건너뜀 %-14s 상장 %s · **비ASCII 티커** — 경로·열 이름으로 "
                 "쓰이므로 자동 편입에서 제외한다", s, ob.date())
    # 문턱에 걸려 대기 중인 것도 남긴다 — 조용히 사라지면 안 보인다
    if not a.no_add:
        waiting = [(s, onboard(x)) for s, x in info.items()
                   if s not in set(research) and x.get("status") == "TRADING"
                   and x.get("contractType") == "PERPETUAL"
                   and x.get("quoteAsset") == "USDT"
                   and onboard(x) is not None and onboard(x) > cutoff]
        for s, ob in sorted(waiting, key=lambda z: z[1]):
            log.info("  대기 %-16s 상장 %s · %d일 (문턱 %d일)", s, ob.date(),
                     (now - ob).days, a.min_age_days)

    if drop_pct > a.max_drop_pct:
        raise SystemExit(
            f"제외가 {drop_pct:.1f}% 로 상한 {a.max_drop_pct}% 를 넘는다 — "
            f"거래소 응답이나 원본 목록을 확인하라. 쓰지 않았다.")
    if add_pct > a.max_add_pct:
        raise SystemExit(
            f"편입이 {add_pct:.1f}% 로 상한 {a.max_add_pct}% 를 넘는다 — "
            f"한 번에 이만큼 상장될 리 없다. 응답을 확인하라. 쓰지 않았다.")

    final = sorted(keep + [s for s, _, _ in added])
    out = ROOT / a.out
    prev = set()
    if out.exists():
        prev = {x.strip().upper() for x in out.read_text().split() if x.strip()}
    if not a.write:
        log.info("점검만 — 쓰려면 --write (현재 파일 %d종목 → 새로 %d종목)",
                 len(prev), len(final))
        return 0
    out.write_text("\n".join(final) + "\n")
    new_in = sorted(set(final) - prev)
    gone = sorted(prev - set(final))
    log.info("저장 %s — %d종목%s%s", out, len(final),
             f" · 추가 {new_in}" if new_in and prev else "",
             f" · 제거 {gone}" if gone else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
