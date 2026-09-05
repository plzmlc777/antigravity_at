"""틱 수집기 — Binance Futures `@trade` 상주 프로세스. Parquet 로 쌓고 예산으로 자른다.

## 왜 (2026-08-26)

1분봉은 그 분 안의 체결 순서를 모른다. 그래서 손절 슬리피지를 **분 단위
상한**으로만 낸다(`rsi_sl_slippage.py`). 틱이 있으면 진짜 체결 순서를 본다.

## 저장 형식이 자릿수를 바꾼다 (실측)

    CSV(비압축)            40.6 B/행   → 20GB 에 42일
    Postgres(추정)        150   B/행   → 20GB 에 11일
    **Parquet zstd(정렬)   4.5 B/행**  → 20GB 에 **286일**

처음엔 Postgres 기준으로 "10종목 11일"이라 셈했다. 형식을 바꾸니 **전 종목
9.5개월**이 됐다 — 33배다. 추정하지 말고 재라.

## 유량 (2026-08-26 실측, 60종목 61초 표본)

    상위 10종목      622만건/일  (전체의 37%)
    무작위 50종목 중앙  7,091건/일
    전 유니버스 377종목 추정 1,669만건/일 = **0.070 GB/일**

꼬리가 싸다 — 상위 10개가 3분의 1을 만든다. 그래서 종목을 줄일 이유가 없다.

## 거래소 제약 (2026-08-09 실측·공식문서)

  · `@aggTrade` 와 `@kline_1m` 은 **데이터가 안 온다**(세 형태 모두 0건).
    구독은 수락되므로 **조용히 아무것도 안 하는 상태**가 된다. `@trade` 만 쓴다.
  · 연결당 최대 **1024 스트림** — 377개는 한 연결로 충분
  · 수신 명령 **초당 10건** — 구독을 나눠 보내고 사이를 띄운다
  · 연결은 **24시간 후 강제 종료** — 재연결은 예외가 아니라 정상 동작
  · 서버 ping 3분, 10분 내 pong 없으면 절단

⚠ 재연결 사이의 공백은 **세어서 보고한다**. 조용한 결손은 나중에 "데이터가
  원래 그랬다"로 오독된다.

## 가짜 체결 — 버려야 한다 (2026-08-27 전선 실측)

바이낸스가 **가격 0 · 수량 0** 인 체결을 섞어 보낸다. 표식은 `X:"NA"` · `st:1`
이고 정상 체결은 `X:"MARKET"` 이다. 우리 결함이 아니라 원본이 그렇다 —
전선 60초 표본과 저장분의 비율이 일치했다(BNB 1.11% vs 1.14%).

    전 유니버스  1억 1,948만 건 중 **13만 1,362건**(0.110%) · 238/359 종목
    유동성이 클수록 많다 — BNB 1.14% · XRP 0.76% · SOL 0.73% · BTC 0.64%

⚠ 이게 왜 위험한가: 최저가·로그수익률·변동성을 **조용히** 망친다. 실측에서
  1000BONKUSDT 의 24시간 변동폭이 105% 로 나왔는데 실제는 4% 였다. 0 이 하나
  섞이면 min 이 0 이 되고 log(0) 이 -inf 가 된다. 봉수·타임스탬프는 멀쩡해서
  **대조 없이는 안 보인다**.

  그래서 **받는 자리에서 버린다**. 읽는 쪽 필터에 맡기면 다음 사람이 놓친다.

사용:
  python3 scripts/binance/tick_collector.py --universe configs/rsi_paper_universe.txt
  python3 scripts/binance/tick_collector.py --smoke 60      # 60초만 돌려보고 끝
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import signal
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import websockets

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "ticks"
WS = "wss://fstream.binance.com/stream?streams="
MAX_STREAMS = 1024          # 연결당 상한(공식)
SUB_CHUNK = 100             # 한 번에 보낼 스트림 수
SUB_GAP = 0.4               # 수신 명령 초당 10건 — 여유 있게 띄운다

log = logging.getLogger("tick")
_stop = False


def _sig(*_):
    global _stop
    _stop = True
    log.info("정지 신호 — 버퍼를 비우고 끝낸다")


class Buffer:
    """종목·날짜별 메모리 버퍼. 임계에 닿으면 Parquet 로 붙인다."""

    def __init__(self, flush_rows: int, flush_secs: float):
        self.rows: dict[tuple[str, str], list] = defaultdict(list)
        self.n = 0
        self.flush_rows = flush_rows
        self.flush_secs = flush_secs
        self.last = time.time()
        self.written = 0
        self.dropped = 0          # 가격·수량 0 인 가짜 체결(바이낸스 원본)

    def add(self, sym: str, ts_ms: int, price: float, qty: float, maker: bool):
        # ⚠ 가짜 체결은 **여기서** 버린다. 읽는 쪽에 맡기면 다음 사람이 놓친다.
        if price <= 0.0 or qty <= 0.0:
            self.dropped += 1
            return
        day = datetime.fromtimestamp(ts_ms / 1000, timezone.utc).strftime("%Y-%m-%d")
        self.rows[(sym, day)].append((ts_ms, price, qty, maker))
        self.n += 1

    def due(self) -> bool:
        return (self.n >= self.flush_rows
                or (self.n and time.time() - self.last >= self.flush_secs))

    def flush(self) -> int:
        if not self.n:
            return 0
        wrote = 0
        for (sym, day), rows in self.rows.items():
            if not rows:
                continue
            d = pd.DataFrame(rows, columns=["ts_ms", "price", "qty", "is_buyer_maker"])
            d["ts_ms"] = d.ts_ms.astype("int64")
            d["price"] = d.price.astype("float64")
            d["qty"] = d.qty.astype("float32")
            # ⚠ 정렬해야 델타 인코딩이 먹는다 — 실측 4.7 → 4.5 B/행
            # ⚠⚠ **안정 정렬이어야 한다.** pandas 기본 quicksort 는 같은 ms
            #   안의 체결 순서를 흩뜨린다(실측 BTRUSDT 중복 78.8%). 하루치를
            #   flush 마다 다시 정렬하므로 **저장된 순서가 매번 뒤바뀌었고**,
            #   순서에 의존하는 값이 재현되지 않았다 — 같은 구간을 다시 접으면
            #   flip 이 최대 16.9% · rmax 가 26.9% 달랐다(2026-09-01 실측).
            #   잡음 계열과 H5 연속이 그 위에 서 있다.
            d = d.sort_values("ts_ms", kind="stable")
            p = OUT / sym / f"{day}.parquet"
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.exists():
                # Parquet 는 붙여쓰기가 없다. 읽어서 합치고 다시 쓴다.
                # 하루 파일이라 크기가 제한적이고, flush 주기가 길어 드물다.
                try:
                    d = pd.concat([pd.read_parquet(p), d], ignore_index=True)
                    # ⚠⚠ **`drop_duplicates()` 를 다시 넣지 마라.**
                    #   같은 (시각·가격·수량·방향) 은 흔한 정상 상황이다 — 한
                    #   주문이 같은 값의 대기주문 여럿을 같은 수량으로 체결시키면
                    #   거래 id 만 다른 행이 여러 개 나온다. 그걸 지우고 있었다.
                    #
                    #   2026-08-31 아카이브 대조 실측 (삭제 비율):
                    #       ETHUSDT 28.04% · ZECUSDT 14.35% · BNTUSDT 12.99%
                    #       COMPUSDT 11.65% · ONGUSDT 4.97% · ARBUSDT 3.17%
                    #   종목마다 **열 배 차이**라 균일한 축소가 아니라 종목별
                    #   왜곡이었다. 활동량 횡단면 선별이 이 위에 서 있었다.
                    #   float32 반올림 탓도 아니다(원본 정밀도와 겹침 수 동일).
                    #
                    #   막던 것도 없다. 버퍼는 flush 직후 비워지고, 중간에
                    #   죽으면 버퍼째 사라진다 — 같은 행이 두 번 들어올 경로가
                    #   없다.
                    d = d.sort_values("ts_ms", kind="stable")
                except Exception as e:                     # noqa: BLE001
                    log.warning("%s %s 재적재 실패(새로 쓴다): %s", sym, day, e)
            # ⚠ **원자적으로** 쓴다. 그냥 쓰면 읽는 쪽이 반쯤 쓴 파일을 만나
            #   `Parquet magic bytes not found` 로 실패하고, 그 종목이 그
            #   주기에서 **조용히 사라진다**(로그엔 후보 수만 하나 준다).
            tmp = p.with_suffix(".parquet.tmp")
            d.to_parquet(tmp, compression="zstd", index=False)
            tmp.replace(p)
            wrote += len(rows)
        self.rows.clear()
        self.n = 0
        self.last = time.time()
        self.written += wrote
        return wrote


def disk_bytes() -> int:
    return sum(f.stat().st_size for f in OUT.rglob("*.parquet"))


def prune(budget_gb: float) -> int:
    """예산을 넘으면 **가장 오래된 날부터** 지운다. 지운 양을 돌려준다.

    ⚠ 날짜 단위로 지운다 — 한 종목만 잘라내면 그 날의 단면이 깨져 비교가 안 된다.
    """
    budget = int(budget_gb * 1024 ** 3)
    total = disk_bytes()
    if total <= budget:
        return 0
    by_day: dict[str, list[Path]] = defaultdict(list)
    for f in OUT.rglob("*.parquet"):
        by_day[f.stem].append(f)
    freed = 0
    for day in sorted(by_day):                    # 오래된 날부터
        if total - freed <= budget:
            break
        for f in by_day[day]:
            freed += f.stat().st_size
            f.unlink(missing_ok=True)
        log.info("예산 초과 — %s 삭제 (누적 %.2f GB)", day, freed / 1024 ** 3)
    return freed


async def run(syms: list[str], buf: Buffer, budget_gb: float,
              smoke: int = 0) -> None:
    if len(syms) > MAX_STREAMS:
        raise SystemExit(f"스트림 {len(syms)} > 연결당 상한 {MAX_STREAMS} — "
                         f"연결을 나눠야 한다")
    url = WS + "/".join(f"{s.lower()}@trade" for s in syms)
    t_start = time.time()
    gaps: list[float] = []
    last_seen = time.time()
    n_conn = 0
    while not _stop:
        if smoke and time.time() - t_start >= smoke:
            break
        try:
            async with websockets.connect(url, ping_interval=20,
                                          ping_timeout=60, max_queue=None) as ws:
                n_conn += 1
                gap = time.time() - last_seen
                if n_conn > 1:
                    gaps.append(gap)
                    log.info("재연결 #%d — 공백 %.1f초", n_conn, gap)
                else:
                    log.info("연결 — %d 스트림", len(syms))
                while not _stop:
                    if smoke and time.time() - t_start >= smoke:
                        break
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=120)
                    except asyncio.TimeoutError:
                        log.warning("120초간 수신 없음 — 재연결한다")
                        break
                    last_seen = time.time()
                    d = (json.loads(raw).get("data") or {})
                    s = d.get("s")
                    if not s:
                        continue
                    buf.add(s, int(d["T"]), float(d["p"]), float(d["q"]),
                            bool(d["m"]))
                    if buf.due():
                        w = buf.flush()
                        f = prune(budget_gb)
                        log.info("적재 %s행 · 누적 %s행 · 가짜폐기 %s(%.3f%%) · "
                                 "디스크 %.2f GB%s",
                                 f"{w:,}", f"{buf.written:,}",
                                 f"{buf.dropped:,}",
                                 100.0 * buf.dropped / max(buf.written + buf.dropped, 1),
                                 disk_bytes() / 1024 ** 3,
                                 f" · 삭제 {f/1024**3:.2f} GB" if f else "")
        except Exception as e:                             # noqa: BLE001
            if _stop:
                break
            log.warning("연결 예외: %s — 5초 뒤 재시도", str(e)[:120])
            await asyncio.sleep(5)
    buf.flush()
    prune(budget_gb)
    el = time.time() - t_start
    log.info("종료 — %.1f분 · 적재 %s행 · 가짜폐기 %s · 연결 %d회 · "
             "공백 %d회(합 %.0f초) · 디스크 %.2f GB", el / 60,
             f"{buf.written:,}", f"{buf.dropped:,}", n_conn,
             len(gaps), sum(gaps), disk_bytes() / 1024 ** 3)
    if gaps:
        log.info("  공백 상세 — 최대 %.0f초 · 중앙 %.0f초", max(gaps),
                 sorted(gaps)[len(gaps) // 2])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_paper_universe.txt")
    p.add_argument("--symbols", default="")
    p.add_argument("--budget-gb", type=float, default=20.0,
                   help="디스크 예산. 넘으면 가장 오래된 **날**부터 지운다")
    p.add_argument("--flush-rows", type=int, default=300_000)
    p.add_argument("--flush-secs", type=float, default=900.0)
    p.add_argument("--smoke", type=int, default=0, help="N초만 돌리고 끝(점검용)")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    if a.symbols:
        syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    else:
        syms = [s.strip().upper() for s in
                (ROOT / a.universe).read_text().split() if s.strip()]
    OUT.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(OUT).free / 1024 ** 3
    log.info("틱 수집 — %d종목 · 예산 %.0f GB · 디스크 여유 %.0f GB · "
             "flush %s행/%.0f초", len(syms), a.budget_gb, free,
             f"{a.flush_rows:,}", a.flush_secs)
    if free < a.budget_gb * 1.5:
        raise SystemExit(f"디스크 여유 {free:.0f} GB 가 예산 {a.budget_gb} GB 의 "
                         f"1.5배에 못 미친다 — 예산을 줄여라")
    buf = Buffer(a.flush_rows, a.flush_secs)
    asyncio.run(run(syms, buf, a.budget_gb, a.smoke))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
