"""초단기 트랙 실시간 수집기 — Binance Futures WebSocket 상주 프로세스.

왜 필요한가 (2026-08-09, 초단기 트랙 설계):
  1. **호가는 오늘부터 쌓는 수밖에 없다.** `data.binance.vision` 의 bookTicker
     아카이브가 **2026-03-30 을 끝으로 중단**됐다(실측: 이후 전 날짜 404).
     최근 구간의 실제 스프레드는 과거로 소급해 얻을 방법이 없다. aggTrades 로
     추정치를 만들어 두었으나(`backfill_aggtrades_1m.py`) 그건 추정이고,
     초단기는 마찰이 엣지와 같은 자릿수라 추정으로는 판정이 안 선다.
  2. **2군 paper 가 성립하려면 실시간 피드가 있어야 한다.** 현행 1분봉은
     일 아카이브 배치라 T+1 지연이다. 그 위에서 forward 를 돌리면 3군 백테스트와
     같은 데이터를 같은 방식으로 재생하는 것이라 "재현되는가"를 잴 수 없다.
  3. **1군 실거래와 같은 경로**를 쓰기 위해서다. 2군과 1군이 같은 피드·같은
     코드로 돌고 마지막 "주문을 실제로 보내는가" 한 줄만 갈려야, 2군에서 잰
     성과가 1군에서 재현된다 (메모리 `project_two_paper_systems` 의 미해결 간극).

수집 대상
  · `<sym>@kline_1m`   전 유니버스 → 봉 마감분만 DB `ohlcv` upsert (T+1일 → T+1분)
  · `<sym>@bookTicker` 초단기 후보만 → 1분 집계(스프레드 bp 통계)를 파일로 적재
    전 유니버스 bookTicker 는 초당 수천~수만 건이라 낭비다. 후보만 받는다.

거래소 제약 (2026-08-09 공식 문서 확인)
  · 연결당 최대 **1024 스트림** — 288종목 kline + 24종목 bookTicker = 312, 여유 있음
  · 수신 명령 **초당 10건** — SUBSCRIBE 를 나눠 보내고 사이를 띄운다
  · 연결은 **24시간 후 강제 종료** — 매일 한 번은 반드시 끊긴다
  · 서버가 3분마다 ping, 10분 내 pong 없으면 절단
  → 재연결은 예외가 아니라 **정상 동작**이다. 그 사이 공백을 REST 로 메우고
    메운 양을 **세어서 보고**한다 (조용한 결손 금지).

저장
  · kline → 기존 `ohlcv` 테이블 (symbol, time_frame='1m', timestamp) ON CONFLICT DO NOTHING.
    아카이브 백필과 같은 테이블·같은 멱등 규칙이라 마이그레이션이 필요 없다.
  · bookTicker → `runs/ws_quotes/{SYMBOL}/{YYYY-MM-DD}.jsonl` 1분 1행.
    DB 스키마 변경을 피했다 — 프로덕션 DB 에 새 테이블을 만드는 건 별도 승인 사안이다.

사용
  python3 scripts/binance/ultra_ws_collector.py \\
      --kline-symbols configs/ultra_universe_full.txt \\
      --quote-symbols configs/ultra_quote_symbols.txt
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ultra_ws_collector")

WS_BASE = "wss://fstream.binance.com/ws"
REST_KLINES = "https://fapi.binance.com/fapi/v1/klines"

MAX_STREAMS_PER_CONN = 1024
SUB_BATCH = 100                 # SUBSCRIBE 한 건에 담는 스트림 수
SUB_INTERVAL_SEC = 0.4          # 초당 10건 제한 대비 (여유 2.5배)
RECONNECT_MAX_SEC = 120
QUOTE_FLUSH_SEC = 20            # 완료된 분(minute) 플러시 주기
STATS_SEC = 300                 # 상태 보고 주기


def live_symbols() -> set:
    """현재 거래 가능한 종목만. 유니버스 파일(719종목)에는 창 구간에 거래됐다가
    상장폐지된 종목이 섞여 있고, 없는 스트림을 구독하면 24/7 프로세스가 조용히
    불완전해진다. 실패 시 빈 집합을 반환해 필터를 건너뛴다(차단하지 않는다)."""
    try:
        import requests
        info = requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo",
                            timeout=60).json()
        return {x["symbol"] for x in info.get("symbols", [])
                if x.get("status") == "TRADING"}
    except Exception as e:
        log.warning("exchangeInfo 실패: %s — 종목 필터 생략", e)
        return set()


def _read_symbols(path: str) -> list[str]:
    out = []
    for ln in Path(path).read_text().splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            out.append(ln.upper())
    return out


class QuoteAggregator:
    """bookTicker 틱 → 1분 스프레드 통계. 완료된 분만 파일로 내린다."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.buf: dict[tuple, list] = defaultdict(list)   # (sym, minute) → [bp,...]
        self.mid: dict[tuple, list] = defaultdict(list)
        self.qty: dict[tuple, list] = defaultdict(list)   # 최우선 호가 잔량 (USD)
        self.chg: dict[tuple, list] = defaultdict(lambda: [0, None])  # 가격변경수, 직전가
        self.written = 0

    def add(self, sym: str, bid: float, ask: float, ts_ms: int,
            bq: float = 0.0, aq: float = 0.0) -> None:
        if not (bid > 0 and ask > 0 and ask >= bid):
            return
        mid = (bid + ask) / 2.0
        key = (sym, ts_ms // 60_000)
        self.buf[key].append((ask - bid) / mid * 10_000.0)
        self.mid[key].append(mid)
        # 큐 잔량은 메이커 체결 가능성의 핵심 재료다 — 스프레드만으로는 판단 못 한다.
        self.qty[key].append((bq * bid, aq * ask))
        c = self.chg[key]
        if c[1] is not None and (bid, ask) != c[1]:
            c[0] += 1
        c[1] = (bid, ask)

    def flush(self, keep_current: bool = True) -> int:
        """현재 분은 아직 진행 중이므로 남긴다."""
        now_min = int(time.time()) // 60
        done = [k for k in self.buf if (not keep_current) or k[1] < now_min]
        n = 0
        for key in done:
            sym, minute = key
            bps = sorted(self.buf.pop(key))
            mids = self.mid.pop(key, [])
            qs = self.qty.pop(key, [])
            n_chg, _ = self.chg.pop(key, [0, None])
            if not bps:
                continue
            ts = datetime.fromtimestamp(minute * 60, tz=timezone.utc)
            row = {
                "ts": ts.strftime("%Y-%m-%dT%H:%M:00Z"),
                "n": len(bps),
                "spread_bp_med": round(bps[len(bps) // 2], 5),
                "spread_bp_mean": round(sum(bps) / len(bps), 5),
                "spread_bp_min": round(bps[0], 5),
                "spread_bp_p90": round(bps[int(len(bps) * 0.9)], 5),
                "mid_last": mids[-1] if mids else None,
                # 최우선 호가 잔량(USD) 중앙값 — 메이커 큐 깊이
                "bid_usd_med": round(sorted(q[0] for q in qs)[len(qs) // 2], 1) if qs else None,
                "ask_usd_med": round(sorted(q[1] for q in qs)[len(qs) // 2], 1) if qs else None,
                # 최우선 호가가 실제로 바뀐 횟수 / 전체 갱신 수 = 큐 회전 대리지표.
                # 낮으면 잔량만 바뀌는 안정된 호가(지정가가 살아남기 쉬움).
                "price_changes": n_chg,
            }
            d = self.out_dir / sym
            d.mkdir(parents=True, exist_ok=True)
            with open(d / f"{ts.strftime('%Y-%m-%d')}.jsonl", "a") as fh:
                fh.write(json.dumps(row) + "\n")
            n += 1
        self.written += n
        return n


class KlineWriter:
    """봉 마감분만 DB `ohlcv` 에 넣는다. 아카이브 백필과 동일한 멱등 규칙."""

    def __init__(self, batch: int = 500):
        from app.db.session import SessionLocal   # noqa: WPS433 (지연 임포트)
        self._Session = SessionLocal
        self.pending: list[tuple] = []
        self.batch = batch
        self.written = 0

    def add(self, sym: str, k: dict) -> None:
        if not k.get("x"):        # 봉이 닫히지 않았으면 버린다 (미확정 봉 금지)
            return
        self.pending.append((
            sym, "1m",
            datetime.fromtimestamp(k["t"] / 1000, tz=timezone.utc).replace(tzinfo=None),
            float(k["o"]), float(k["h"]), float(k["l"]), float(k["c"]), float(k["v"]),
        ))
        if len(self.pending) >= self.batch:
            self.flush()

    def flush(self) -> int:
        if not self.pending:
            return 0
        from sqlalchemy import text
        rows, self.pending = self.pending, []
        db = self._Session()
        try:
            db.execute(text(
                "INSERT INTO ohlcv (symbol, time_frame, timestamp, open, high, low, close, volume)"
                " VALUES (:s, :tf, :ts, :o, :h, :l, :c, :v)"
                " ON CONFLICT (symbol, time_frame, timestamp) DO NOTHING"
            ), [{"s": r[0], "tf": r[1], "ts": r[2], "o": r[3], "h": r[4],
                 "l": r[5], "c": r[6], "v": r[7]} for r in rows])
            db.commit()
            self.written += len(rows)
            return len(rows)
        except Exception as e:
            db.rollback()
            log.error("kline DB 기록 실패 %d행: %s", len(rows), e)
            return 0
        finally:
            db.close()


async def backfill_gap(symbols: list[str], since_ms: int, writer: KlineWriter) -> int:
    """재연결 공백을 REST 로 메운다. 24시간 강제 절단이 매일 오므로 정상 경로다."""
    import aiohttp
    filled = 0
    async with aiohttp.ClientSession() as sess:
        for sym in symbols:
            try:
                async with sess.get(REST_KLINES, params={
                    "symbol": sym, "interval": "1m",
                    "startTime": since_ms, "limit": 1000,
                }, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    if r.status != 200:
                        continue
                    for a in await r.json():
                        # 마지막 봉은 진행 중일 수 있으므로 닫힌 것만
                        if a[6] > int(time.time() * 1000):
                            continue
                        writer.add(sym, {"x": True, "t": a[0], "o": a[1], "h": a[2],
                                         "l": a[3], "c": a[4], "v": a[5]})
                        filled += 1
            except Exception as e:
                log.warning("[%s] REST 보정 실패: %s", sym, e)
            await asyncio.sleep(0.05)      # REST 가중치 보호
    writer.flush()
    return filled


async def run_stream(streams: list[str], on_msg, name: str, stop: asyncio.Event) -> None:
    """한 연결이 담당하는 스트림 묶음. 24시간 절단·오류를 정상 경로로 처리한다."""
    import websockets
    delay = 1.0
    while not stop.is_set():
        opened = time.time()
        try:
            async with websockets.connect(WS_BASE, ping_interval=180,
                                          ping_timeout=600, max_size=2 ** 22) as ws:
                for i in range(0, len(streams), SUB_BATCH):
                    await ws.send(json.dumps({
                        "method": "SUBSCRIBE",
                        "params": streams[i:i + SUB_BATCH],
                        "id": i // SUB_BATCH + 1,
                    }))
                    await asyncio.sleep(SUB_INTERVAL_SEC)
                log.info("[%s] 연결 — 스트림 %d개", name, len(streams))
                delay = 1.0
                while not stop.is_set():
                    raw = await asyncio.wait_for(ws.recv(), timeout=120)
                    d = json.loads(raw)
                    if "result" in d:          # SUBSCRIBE 응답
                        continue
                    on_msg(d)
        except asyncio.CancelledError:
            return
        except Exception as e:
            if stop.is_set():
                return
            up = time.time() - opened
            # 24시간 근처 절단은 사고가 아니라 규격이다.
            lvl = log.info if up > 23 * 3600 else log.warning
            lvl("[%s] 연결 종료 (%.1f시간) — %s. %.0f초 후 재연결", name, up / 3600, e, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_SEC)


async def amain(args) -> int:
    kline_syms = _read_symbols(args.kline_symbols) if args.kline_symbols else []
    quote_syms = _read_symbols(args.quote_symbols) if args.quote_symbols else []
    live = live_symbols()
    if live:
        drop_k = [s for s in kline_syms if s not in live]
        drop_q = [s for s in quote_syms if s not in live]
        kline_syms = [s for s in kline_syms if s in live]
        quote_syms = [s for s in quote_syms if s in live]
        if drop_k or drop_q:
            log.info("상장폐지·미거래 제외 — kline %d종목%s, 호가 %d종목%s",
                     len(drop_k), (" " + ",".join(drop_k[:6])) if drop_k else "",
                     len(drop_q), (" " + ",".join(drop_q[:6])) if drop_q else "")
    if not kline_syms and not quote_syms:
        log.error("수집 대상이 없다")
        return 1

    out_dir = Path(args.quote_dir)
    agg = QuoteAggregator(out_dir)
    writer = KlineWriter()
    counts = {"kline": 0, "quote": 0, "closed": 0}
    last_msg = {"t": time.time()}

    def on_msg(d: dict) -> None:
        last_msg["t"] = time.time()
        e = d.get("e")
        if e == "kline":
            counts["kline"] += 1
            if d["k"].get("x"):
                counts["closed"] += 1
            writer.add(d["s"], d["k"])
        elif e == "bookTicker":
            counts["quote"] += 1
            agg.add(d["s"], float(d["b"]), float(d["a"]),
                    int(d.get("E") or d.get("T") or time.time() * 1000),
                    float(d.get("B") or 0.0), float(d.get("A") or 0.0))

    streams = [f"{s.lower()}@kline_1m" for s in kline_syms] + \
              [f"{s.lower()}@bookTicker" for s in quote_syms]
    chunks = [streams[i:i + MAX_STREAMS_PER_CONN]
              for i in range(0, len(streams), MAX_STREAMS_PER_CONN)]
    log.info("kline %d종목 / bookTicker %d종목 → 스트림 %d개, 연결 %d개",
             len(kline_syms), len(quote_syms), len(streams), len(chunks))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    tasks = [asyncio.create_task(run_stream(c, on_msg, f"conn{i}", stop))
             for i, c in enumerate(chunks)]

    async def housekeeping():
        t0 = time.time()
        last_stats = time.time()
        while not stop.is_set():
            await asyncio.sleep(QUOTE_FLUSH_SEC)
            agg.flush()
            writer.flush()
            if time.time() - last_stats >= STATS_SEC:
                last_stats = time.time()
                silent = time.time() - last_msg["t"]
                log.info("가동 %.1f시간 | kline %s(마감 %s) DB %s행 | 호가 %s틱 분 %s개"
                         " | 최근 수신 %.0f초 전",
                         (time.time() - t0) / 3600, f"{counts['kline']:,}",
                         f"{counts['closed']:,}", f"{writer.written:,}",
                         f"{counts['quote']:,}", f"{agg.written:,}", silent)
                if silent > 300:
                    log.error("5분간 수신 없음 — 연결 이상 의심")
    tasks.append(asyncio.create_task(housekeeping()))

    await stop.wait()
    log.info("종료 신호 — 잔여 플러시")
    for t in tasks:
        t.cancel()
    agg.flush(keep_current=False)
    writer.flush()
    log.info("종료. DB %s행 / 호가 분 %s개", f"{writer.written:,}", f"{agg.written:,}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="초단기 트랙 WS 수집기")
    p.add_argument("--kline-symbols", default=str(ROOT / "configs" / "ultra_universe_full.txt"))
    p.add_argument("--quote-symbols", default=str(ROOT / "configs" / "ultra_quote_symbols.txt"))
    p.add_argument("--quote-dir", default=str(ROOT / "runs" / "ws_quotes"))
    p.add_argument("--no-kline", action="store_true", help="호가만 수집")
    args = p.parse_args()
    if args.no_kline:
        args.kline_symbols = ""
    try:
        return asyncio.run(amain(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
