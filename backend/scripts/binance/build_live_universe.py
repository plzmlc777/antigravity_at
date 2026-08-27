"""실거래 유니버스 — 연구 유니버스에서 **거래 불가 종목만** 걷어낸다.

## 왜 (2026-08-27)

틱 수집기가 377종목 중 360개만 받았다. 빠진 17개를 확인하니 전부 거래소에서
죽은 것이었다 — SETTLING(정산 중) 15개 · 목록에서 삭제 2개(AERGO·BTCST).
수집기 결함이 아니라 **유니버스 파일이 낡은 것**이다.

실거래도 같은 파일을 쓴다. 삭제된 2종목은 매 사이클 `HTTP 400` 을 내고(시세
실패로 걸러져 주문은 안 나간다), SETTLING 15종목은 신호가 나면 **주문 단계에서
거부**된다. 아직 안 걸렸을 뿐이다.

## 두 유니버스를 가른다

    configs/rsi_paper_universe.txt   **연구용 — 얼리지 않는다**
        백테스트 결과가 이 목록에 묶여 있다. 종목을 빼면 과거 격자와
        비교가 안 된다. 죽은 종목이 섞여 있어도 그대로 둔다.

    configs/rsi_live_universe.txt    **실거래·수집용 — 매일 다시 만든다**
        위 목록에서 `status=TRADING` 인 것만 남긴다.

⚠ **부분집합만 만든다.** 거래소에 새로 상장한 종목을 넣지 않는다 — 배포된
  전략은 그 377종목에서 검증됐다. 유니버스 확대는 별도 판단 사안이다.

⚠ 빠지는 종목을 **세어서 남긴다**. 조용히 줄어들면 나중에 "원래 그 종목은
  없었다"로 오독된다. 감소가 크면(기본 15%) 쓰지 않고 죽는다.

사용:
  python3 -m scripts.binance.build_live_universe            # 점검만
  python3 -m scripts.binance.build_live_universe --write
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAPI = "https://fapi.binance.com/fapi/v1/exchangeInfo"

log = logging.getLogger("live_uni")


def exchange_status() -> dict[str, dict]:
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
    p.add_argument("--max-drop-pct", type=float, default=15.0,
                   help="이보다 많이 빠지면 쓰지 않고 죽는다 — 거래소 응답 이상 방어")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    src = ROOT / a.source
    syms = [s.strip().upper() for s in src.read_text().split() if s.strip()]
    info = exchange_status()
    if len(info) < 100:
        raise SystemExit(f"거래소 목록이 {len(info)}개뿐이다 — 응답이 이상하다")

    keep, dead = [], []
    for s in syms:
        x = info.get(s)
        if x is None:
            dead.append((s, "목록에 없음", ""))
        elif x.get("status") != "TRADING":
            ob = datetime.datetime.fromtimestamp(
                x["onboardDate"] / 1000, datetime.UTC).date()
            dead.append((s, x["status"], str(ob)))
        else:
            keep.append(s)

    drop_pct = 100.0 * len(dead) / max(len(syms), 1)
    log.info("연구 %d종목 → 거래 가능 %d · 제외 %d (%.1f%%)",
             len(syms), len(keep), len(dead), drop_pct)
    for s, st, ob in dead:
        log.info("  제외 %-16s %-14s %s", s, st, ob)

    if drop_pct > a.max_drop_pct:
        raise SystemExit(
            f"제외가 {drop_pct:.1f}% 로 상한 {a.max_drop_pct}% 를 넘는다 — "
            f"거래소 응답이나 원본 목록을 확인하라. 쓰지 않았다.")

    out = ROOT / a.out
    if not a.write:
        prev = (len([x for x in out.read_text().split() if x.strip()])
                if out.exists() else 0)
        log.info("점검만 — 쓰려면 --write (현재 파일 %d종목)", prev)
        return 0

    prev = set()
    if out.exists():
        prev = {x.strip().upper() for x in out.read_text().split() if x.strip()}
    out.write_text("\n".join(keep) + "\n")
    added = sorted(set(keep) - prev)
    removed = sorted(prev - set(keep))
    log.info("저장 %s — %d종목%s%s", out, len(keep),
             f" · 추가 {added}" if added and prev else "",
             f" · 제거 {removed}" if removed else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
