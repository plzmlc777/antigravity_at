"""바이낸스 선물 봉 마감 피드 — 웹소켓.

⚠ 왜 만들었나 (2026-08-20)
    REST 폴링은 봉 마감 +40초에 깨어나 377종목을 순차 조회하느라 50초를 더
    쓴다. 결정 시점이 봉 마감 **+90초**다.

    그런데 이 전략의 수익은 그 안에서 끝난다 — 1봉 익절 거래의 익절가 도달까지
    **중앙 2개 1분봉**이었다. 90초면 급등의 상당 부분이 지나간 뒤다.
    백테스트는 신호 봉 종가에 산다고 가정하므로 그 차이가 통째로 허수가 된다.

    웹소켓은 봉 마감 이벤트(k.x=true)를 밀리초 안에 준다. 전 종목이 동시에
    밀려오므로 순차 조회도 없다. 결정 시점이 **봉 마감 +수 초**로 줄어든다.

⚠ 왜 즉시 처리하지 않고 몇 초 모으나
    슬롯 배분이 **후보 전체**를 보고 무작위로 뽑는다. 먼저 도착한 종목부터
    처리하면 네트워크 도착 순서가 곧 선택 편향이 된다. 짧은 수집창을 둬야
    REST 때와 같은 규약이 유지된다.

⚠ 워밍업은 REST 로 채운다
    RSI 는 200봉이 필요한데 웹소켓은 구독 이후만 준다. 기동 시 한 번 REST 로
    채우고, 그 뒤로는 마감 이벤트로 갱신한다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import deque
from typing import Callable, Optional

import pandas as pd
import websockets

log = logging.getLogger("ws_feed")

WS_BASE = "wss://fstream.binance.com/stream?streams="
MAX_STREAMS_PER_CONN = 200      # 바이낸스 상한은 1024. 여유를 크게 둔다
SUB_CHUNK = 100                 # SUBSCRIBE 한 번에 보낼 스트림 수


class KlineFeed:
    """종목×시간대별 **마감된 봉**을 메모리에 유지한다.

    스레드에서 asyncio 루프를 돌리고, 본 루프는 `snapshot()` 으로 읽는다.
    """

    def __init__(self, symbols: list[str], tfs: list[str], maxlen: int = 400):
        self.symbols = [s.lower() for s in symbols]
        self.tfs = list(tfs)
        self.maxlen = maxlen
        # (SYMBOL, tf) -> deque[(open_ms, o, h, l, c, quote_vol)]
        self.buf: dict[tuple[str, str], deque] = {}
        self.lock = threading.Lock()
        self.n_msg = 0
        self.n_closed = 0
        self.last_msg_ts = 0.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── 워밍업 (REST) ─────────────────────────────────────────────
    def seed(self, fetch: Callable[[str, int, str], Optional[pd.DataFrame]],
             limit_by_tf: dict[str, int]) -> int:
        """기동 시 한 번. `fetch` 는 페이퍼 스크립트의 fetch_klines 를 받는다."""
        n = 0
        for tf in self.tfs:
            for s in self.symbols:
                df = fetch(s.upper(), limit_by_tf.get(tf, 300), tf)
                if df is None or df.empty:
                    continue
                rows = [(int(ts.timestamp() * 1000), float(r.open), float(r.high),
                         float(r.low), float(r.close),
                         float(getattr(r, "quote_vol", 0.0)))
                        for ts, r in df.iterrows()]
                with self.lock:
                    self.buf[(s.upper(), tf)] = deque(rows, maxlen=self.maxlen)
                n += 1
                time.sleep(0.05)
        log.info("워밍업 완료 — %d (종목×시간대) 적재", n)
        return n

    # ── 웹소켓 ───────────────────────────────────────────────────
    def _streams(self) -> list[str]:
        return [f"{s}@kline_{tf}" for tf in self.tfs for s in self.symbols]

    async def _run_conn(self, streams: list[str]) -> None:
        url = WS_BASE + "/".join(streams[:1])      # 최소 1개로 연결 후 나머지 구독
        while not self._stop.is_set():
            try:
                async with websockets.connect(url, ping_interval=180,
                                              ping_timeout=60,
                                              max_queue=4096) as ws:
                    rest = streams[1:]
                    for i in range(0, len(rest), SUB_CHUNK):
                        await ws.send(json.dumps({
                            "method": "SUBSCRIBE",
                            "params": rest[i:i + SUB_CHUNK], "id": i + 1}))
                        await asyncio.sleep(0.3)   # 초당 10건 제한 회피
                    log.info("웹소켓 연결 — 스트림 %d", len(streams))
                    async for raw in ws:
                        self._on_msg(raw)
                        if self._stop.is_set():
                            break
            except Exception as exc:            # 끊기면 다시 붙는다
                if self._stop.is_set():
                    return
                log.warning("웹소켓 재연결 — %s", exc)
                await asyncio.sleep(3)

    def _on_msg(self, raw: str) -> None:
        try:
            m = json.loads(raw)
        except Exception:
            return
        d = m.get("data") or m
        k = d.get("k")
        if not k:
            return
        self.n_msg += 1
        self.last_msg_ts = time.time()
        if not k.get("x"):                      # 마감된 봉만
            return
        key = (d["s"], k["i"])
        row = (int(k["t"]), float(k["o"]), float(k["h"]), float(k["l"]),
               float(k["c"]), float(k["q"]))
        with self.lock:
            q = self.buf.get(key)
            if q is None:
                q = self.buf[key] = deque(maxlen=self.maxlen)
            if q and q[-1][0] == row[0]:        # 같은 봉 재수신
                q[-1] = row
            else:
                q.append(row)
        self.n_closed += 1

    def start(self) -> None:
        chunks = [self._streams()[i:i + MAX_STREAMS_PER_CONN]
                  for i in range(0, len(self._streams()), MAX_STREAMS_PER_CONN)]

        def _loop() -> None:
            asyncio.set_event_loop(asyncio.new_event_loop())
            loop = asyncio.get_event_loop()
            loop.run_until_complete(asyncio.gather(
                *[self._run_conn(c) for c in chunks]))

        self._thread = threading.Thread(target=_loop, daemon=True, name="klinefeed")
        self._thread.start()
        log.info("웹소켓 시작 — 연결 %d · 스트림 %d", len(chunks),
                 len(self._streams()))

    def stop(self) -> None:
        self._stop.set()

    # ── 본 루프가 읽는 창 ────────────────────────────────────────
    def snapshot(self, tf: str, min_bars: int) -> dict[str, pd.DataFrame]:
        """시간대별 {종목: 마감봉 DataFrame}. REST 경로와 **같은 형태**로 준다."""
        out: dict[str, pd.DataFrame] = {}
        with self.lock:
            items = [(k[0], list(v)) for k, v in self.buf.items() if k[1] == tf]
        for sym, rows in items:
            if len(rows) < min_bars:
                continue
            df = pd.DataFrame(rows, columns=["ot", "open", "high", "low",
                                             "close", "quote_vol"])
            df["ts"] = pd.to_datetime(df.ot, unit="ms", utc=True)
            out[sym] = df.set_index("ts")
        return out

    def health(self) -> dict:
        with self.lock:
            n_key = len(self.buf)
        return {"keys": n_key, "msg": self.n_msg, "closed": self.n_closed,
                "silent_s": round(time.time() - self.last_msg_ts, 1)
                if self.last_msg_ts else None}
