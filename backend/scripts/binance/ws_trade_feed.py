"""체결(@trade)로 봉을 조립하는 피드 — REST 레이트리밋을 근본적으로 없앤다.

⚠ 왜 kline 이 아니라 trade 인가 (2026-08-20 실측)
    `@kline_*` 은 연결은 되는데 **데이터가 한 건도 안 온다.** 단일 `/ws/` 도
    결합 `/stream` 도 같고, 75초(봉 마감 1회 이상) 관찰해도 0건이다. 같은
    연결·같은 시각에 `@trade` 는 초당 65건씩 온다. IP 차단과도 무관하다
    (해제 후 재검증에서 동일). 이 저장소의 `@aggTrade` 미작동과 같은 계열이다.

⚠ 왜 필요한가
    REST 폴링은 IP weight 를 먹는다. 5세션 × 377종목이 정각에 겹쳐
    `-1003 IP banned` 로 12분 차단됐고, **같은 IP 인 실거래 세션까지 막혔다.**
    웹소켓 시장 데이터는 REST weight 를 **전혀 쓰지 않는다.**

⚠ 이 방식의 진짜 위험 — 봉이 공식 봉과 달라질 수 있다
    백테스트는 바이낸스 공식 klines 로 돌았다. 우리가 조립한 봉이 조금이라도
    다르면 RSI 가 달라지고 신호가 갈린다. 그래서 `validate()` 를 내장한다 —
    조립한 봉을 REST klines 와 **한 봉씩 대조**한다. 통과 못 하면 쓰지 마라.

    특히 조심할 것:
      · **체결이 없는 봉** — 바이낸스는 그래도 봉을 낸다(직전 종가로 평평하게).
        체결만 모으면 그 봉이 통째로 빠져 RSI 창이 어긋난다.
      · 경계 처리 — 봉 시작은 `(체결ms // tf_ms) * tf_ms` 로 바닥을 맞춘다.
      · 재연결 구멍 — 끊긴 동안의 체결은 영영 못 받는다. 감지해서 REST 로 메운다.
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

log = logging.getLogger("trade_feed")

WS_BASE = "wss://fstream.binance.com/stream?streams="
SYMS_PER_CONN = 120          # 종목/연결. 메시지량이 초당 ~770건이라 여유롭다
TF_MS = {"1h": 3_600_000, "30m": 1_800_000, "15m": 900_000,
         "5m": 300_000, "1m": 60_000}


class _Bar:
    __slots__ = ("ot", "o", "h", "l", "c", "qv")

    def __init__(self, ot: int, px: float, qv: float):
        self.ot, self.o, self.h, self.l, self.c, self.qv = ot, px, px, px, px, qv

    def add(self, px: float, qv: float) -> None:
        if px > self.h:
            self.h = px
        if px < self.l:
            self.l = px
        self.c = px
        self.qv += qv

    def row(self):
        return (self.ot, self.o, self.h, self.l, self.c, self.qv)


class TradeFeed:
    """종목×시간대별 마감 봉을 메모리에 유지한다. REST 형태로 내준다."""

    def __init__(self, symbols: list[str], tfs: list[str], maxlen: int = 400):
        self.symbols = [s.upper() for s in symbols]
        self.tfs = list(tfs)
        self.maxlen = maxlen
        self.closed: dict[tuple[str, str], deque] = {}   # 마감된 봉
        self.cur: dict[tuple[str, str], _Bar] = {}       # 진행 중인 봉
        self.lock = threading.Lock()
        self.n_msg = 0
        self.n_zero_px = 0          # 체결가 0 이벤트 — 버린 건수
        self.last_msg_ts = 0.0
        self.n_reconnect = 0
        self.gap_since: Optional[float] = None
        # ⚠ 연결 시점에 **이미 진행 중이던 봉**은 앞부분 체결을 놓쳤다.
        #   그걸 마감 봉으로 채택하면 시가가 틀린다 — 2026-08-20 검증에서
        #   실제로 그랬다(일치율 80.3%, 불일치 5건 전부 첫 봉의 시가).
        #   고·저·종가는 맞고 **시가만** 틀리므로 눈에 잘 안 띈다.
        #   종목별로 "경계부터 온전히 본 첫 봉"의 시작 시각을 기억해 그 이전은 버린다.
        self.first_full: dict[tuple[str, str], int] = {}
        # 시계로 마감한 지점. 이 시각까지는 **빠짐없이** 마감돼 있다.
        # 이후 첫 체결로 시작하는 봉은 처음부터 온전하다 — 그 봉을
        # 부분 관측으로 버리면 한산한 종목이 영영 안 보인다.
        # 듣기 시작한 시각. **이 전의 봉은 '거래가 없었다'고 말할 수 없다.**
        # 안 듣고 있었을 뿐이다 — 모르는 것과 없는 것은 다르다(교훈 #106).
        self.started_ms: int = 0
        # 마지막 체결가·시각. 체결을 이미 받고 있으므로 REST ticker 가 필요 없다.
        self.last_px: dict[str, tuple[float, float]] = {}
        self._stop = threading.Event()

    # ── 워밍업 (REST 1회) ────────────────────────────────────────
    def seed(self, fetch: Callable[[str, int, str], Optional[pd.DataFrame]],
             limit_by_tf: dict[str, int]) -> int:
        n = 0
        for tf in self.tfs:
            for s in self.symbols:
                df = fetch(s, limit_by_tf.get(tf, 300), tf)
                if df is None or df.empty:
                    continue
                rows = [(int(ts.timestamp() * 1000), float(r.open), float(r.high),
                         float(r.low), float(r.close),
                         float(getattr(r, "quote_vol", 0.0)))
                        for ts, r in df.iterrows()]
                with self.lock:
                    self.closed[(s, tf)] = deque(rows, maxlen=self.maxlen)
                n += 1
        log.info("워밍업 %d (종목×시간대)", n)
        return n

    # ── 체결 수신 ───────────────────────────────────────────────
    def _on_trade(self, sym: str, ts_ms: int, px: float, qty: float) -> None:
        qv = px * qty
        with self.lock:
            for tf in self.tfs:
                span = TF_MS[tf]
                ot = (ts_ms // span) * span
                key = (sym, tf)
                b = self.cur.get(key)
                if b is None:
                    # ⚠ **이미 정해진 first_full 을 덮어쓰지 않는다.**
                    #   seal 이 진행 봉을 닫고 cur 를 비우면 이 분기가 다시
                    #   온다. 그때 새로 잡으면 온전한 봉까지 부분 관측으로
                    #   버려진다 — 고치려던 것보다 나빠진다.
                    if key not in self.first_full:
                        # 이 종목·시간대의 첫 관측. 이 봉은 앞부분을 놓쳤을 수
                        # 있으므로 **다음 봉부터** 온전하다고 본다.
                        self.first_full[key] = ot + span
                    self.cur[key] = _Bar(ot, px, qv)
                elif b.ot == ot:
                    b.add(px, qv)
                elif ot > b.ot:
                    self._close_bar(key, b, ot, span)
                    self.cur[key] = _Bar(ot, px, qv)
                # ot < b.ot 는 지연 도착 — 버린다(이미 마감된 봉)

    def _close_bar(self, key, b: _Bar, new_ot: int, span: int) -> None:  # noqa: D401
        """진행 봉을 마감하고, 그 사이 **체결이 없던 봉**을 평평하게 메운다.

        바이낸스 klines 는 거래가 없어도 봉을 낸다(직전 종가로 O=H=L=C).
        안 메우면 RSI 창의 봉 수가 어긋나 신호가 갈린다."""
        q = self.closed.get(key)
        if q is None:
            q = self.closed[key] = deque(maxlen=self.maxlen)
        # 부분 관측 봉은 버린다 (시가가 틀린다)
        if b.ot < self.first_full.get(key, 0):
            log.debug("부분 관측 봉 폐기 %s ot=%d", key, b.ot)
        elif q and q[-1][0] == b.ot:
            q[-1] = b.row()                 # 워밍업 REST 봉을 덮어쓰는 경우
        else:
            q.append(b.row())
        gap_ot = b.ot + span
        while gap_ot < new_ot:
            q.append((gap_ot, b.c, b.c, b.c, b.c, 0.0))
            gap_ot += span

    def _safe_from(self, span: int) -> int:
        """처음부터 온전히 들은 **첫 봉**의 시작 시각.

        듣기 시작한 순간 진행 중이던 봉은 앞부분을 놓쳤다 — 그 봉을
        "거래가 없었다"고 평평하게 메우면 거짓을 만든다."""
        if not self.started_ms:
            return 0
        return ((self.started_ms // span) + 1) * span

    def seal(self, edge_ms: int, tf: str, grace_ms: int = 2_000) -> int:
        """경계가 지난 봉을 **체결을 기다리지 않고** 시계로 마감한다.

        ⚠ 왜 필요한가 (2026-08-31 실측)
            봉은 `_close_bar` 에서 **다음 봉의 첫 체결**이 와야 닫힌다.
            사이클은 경계 +20초에 도는데, 한산한 종목은 첫 체결이 중앙값
            **46.6초** 뒤에 붙는다. 그 종목들은 사이클 시점에 봉이 한 칸
            뒤처져 있고(묵은봉), 관문이 걸러 그 사이클에서 사라진다.
            실측: 걸린 34종목은 +20초 체결 **0/34**, 대조군은 **34/34**.
            :30 경계는 :00 보다 한산해(체결 3건 미만 경계분 3.32배)
            묵은봉이 :00 평균 2.3건 vs :30 평균 19.7건으로 몰렸다.

        ⚠ 왜 이래도 되는가 — **정본이 그렇게 한다.**
            바이낸스 klines 는 거래가 없어도 봉을 낸다(직전 종가로 평평하게).
            백테스트가 쓰는 값이 바로 그것이다. 시계로 닫는 건 정본에서
            벗어나는 게 아니라 **정본에 맞추는** 것이다.

        ⚠ 유예 — `grace_ms` 만큼 지나야 마감한다. 경계 직전 체결이 늦게
            배달될 수 있다. 기본 2초는 `bar_wait_s` 기본값과 같다.

        반환: 이번에 마감·보충한 봉 수.
        """
        span = TF_MS[tf]
        if edge_ms % span:
            return 0                       # 이 시간대의 경계가 아니다
        now_ms = int(time.time() * 1000)
        if now_ms < edge_ms + grace_ms:
            log.warning("seal 유예 미달 — %dms 남음. 이번엔 건너뛴다",
                        edge_ms + grace_ms - now_ms)
            return 0
        n = 0
        with self.lock:
            for sym in self.symbols:
                key = (sym, tf)
                b = self.cur.get(key)
                # ① 창이 완전히 지난 진행 봉을 닫는다
                if b is not None and b.ot + span <= edge_ms:
                    self._close_bar(key, b, b.ot + span, span)
                    self.cur.pop(key, None)
                    n += 1
                q = self.closed.get(key)
                if not q:
                    continue
                # ② 마지막 마감 봉과 경계 사이를 평평한 봉으로 메운다.
                #
                # ⚠ **처음부터 듣지 못한 봉은 지어내지 않는다.**
                #   2026-08-31 시험에서 20/20 이 정본과 불일치했다. 피드가
                #   19:33 에 붙어 19:30 봉을 앞부분부터 못 봤고(그래서 폐기),
                #   그 빈자리를 직전 종가로 평평하게 메웠는데 **실제로는 거래가
                #   있던 봉**이었다. 평평한 봉은 "거래가 없었다"는 주장인데,
                #   안 듣고 있었던 것과 거래가 없던 것은 다르다(교훈 #106).
                floor = max(self._safe_from(span), self.first_full.get(key, 0))
                last_ot, last_c = q[-1][0], q[-1][4]
                gap_ot = last_ot + span
                if gap_ot < floor:
                    # 못 본 구간이 남아 있다 — 이 종목은 이번 사이클에서
                    # 뒤처진 채 둔다(오늘까지의 동작과 같다). 관문이 거른다.
                    continue
                while gap_ot < edge_ms:
                    q.append((gap_ot, last_c, last_c, last_c, last_c, 0.0))
                    gap_ot += span
                    n += 1
        return n

    def _handle(self, raw: str) -> None:
        try:
            d = json.loads(raw).get("data") or {}
        except Exception:
            return
        if d.get("e") != "trade":
            return
        self.n_msg += 1
        self.last_msg_ts = time.time()
        try:
            px, qty = float(d["p"]), float(d["q"])
        except (KeyError, ValueError):
            return
        # ⚠ 바이낸스는 **체결가 0** 이벤트를 섞어 보낸다 (2026-08-20 실측)
        #     {"e":"trade","s":"BTCUSDT","p":"0","q":"0","X":"NA","st":1}
        #   BTC 1,195건 중 2건. X="NA" 이고 일반 체결에 없는 `st` 필드가 붙는다
        #   — 실제 체결이 아니라 상태성 이벤트로 보인다.
        #
        #   이걸 봉에 넣으면 `px < low` 에서 **저가가 0 으로 내려앉는다.**
        #   시가·고가·종가는 멀쩡해서(0 은 고가를 못 올리고 종가는 다음 체결이
        #   덮는다) **저가만 틀리고**, 육안으로는 잘 안 보인다.
        #
        #   ⚠ 이 저장소의 라이브 엔진에도 같은 증상이 있다:
        #       "Skip corrupt candles (e.g., low=0 from WebSocket reconnection gaps)"
        #     원인을 **재연결 구멍으로 적어놨는데 틀렸다.** 재연결과 무관하고
        #     이 이벤트가 원인이다. 그래서 멀쩡한 봉까지 통째로 버려 왔다.
        if px <= 0 or qty < 0:
            self.n_zero_px += 1
            return
        sym = d.get("s")
        if sym:
            self.last_px[sym] = (px, time.time())
        try:
            self._on_trade(d["s"], int(d["T"]), px, qty)
        except (KeyError, ValueError):
            pass

    # ── 연결 ────────────────────────────────────────────────────
    async def _conn(self, syms: list[str]) -> None:
        url = WS_BASE + "/".join(f"{s.lower()}@trade" for s in syms)
        while not self._stop.is_set():
            try:
                async with websockets.connect(url, ping_interval=180,
                                              ping_timeout=60,
                                              max_queue=8192) as ws:
                    self.gap_since = None
                    log.info("연결 — %d종목", len(syms))
                    async for raw in ws:
                        self._handle(raw)
                        if self._stop.is_set():
                            break
            except Exception as exc:
                if self._stop.is_set():
                    return
                self.n_reconnect += 1
                if self.gap_since is None:
                    self.gap_since = time.time()
                log.warning("재연결 #%d — %s", self.n_reconnect, exc)
                await asyncio.sleep(3)

    def start(self) -> None:
        # 이 순간부터 듣는다. 이 전 봉은 '거래가 없었다'고 말할 수 없다.
        self.started_ms = int(time.time() * 1000)
        chunks = [self.symbols[i:i + SYMS_PER_CONN]
                  for i in range(0, len(self.symbols), SYMS_PER_CONN)]

        def _loop():
            asyncio.set_event_loop(asyncio.new_event_loop())
            asyncio.get_event_loop().run_until_complete(
                asyncio.gather(*[self._conn(c) for c in chunks]))

        threading.Thread(target=_loop, daemon=True, name="tradefeed").start()
        log.info("체결 피드 시작 — 연결 %d · 종목 %d · 시간대 %s",
                 len(chunks), len(self.symbols), self.tfs)

    def stop(self) -> None:
        self._stop.set()

    # ── 읽기 ────────────────────────────────────────────────────
    def snapshot(self, tf: str, min_bars: int) -> dict[str, pd.DataFrame]:
        """REST 경로와 **같은 형태**. 진행 중인 봉은 넣지 않는다."""
        out: dict[str, pd.DataFrame] = {}
        with self.lock:
            items = [(k[0], list(v)) for k, v in self.closed.items() if k[1] == tf]
        for sym, rows in items:
            if len(rows) < min_bars:
                continue
            df = pd.DataFrame(rows, columns=["ot", "open", "high", "low",
                                             "close", "quote_vol"])
            df["ts"] = pd.to_datetime(df.ot, unit="ms", utc=True)
            out[sym] = df.set_index("ts")
        return out

    def last_price(self, symbol: str, max_age_s: float = 30.0):
        """마지막 체결가. **너무 오래되면 None** 을 준다.

        오래된 값으로 체결하면 정지 종목에서 엉뚱한 가격에 진입한다 —
        2026-08-19 HFTUSDT 사고가 그 형태였다(마지막 체결가와 현재 호가가
        12% 벌어져 있었다). 신선도 판정을 여기서 강제한다."""
        v = self.last_px.get(symbol.upper())
        if v is None:
            return None
        px, ts = v
        return px if (time.time() - ts) <= max_age_s else None

    def health(self) -> dict:
        with self.lock:
            keys = len(self.closed)
        return {"keys": keys, "msg": self.n_msg, "zero_px": self.n_zero_px,
                "silent_s": round(time.time() - self.last_msg_ts, 1)
                if self.last_msg_ts else None,
                "reconnect": self.n_reconnect,
                "gap": self.gap_since is not None}

    # ── 정확성 검증 ─────────────────────────────────────────────
    def validate(self, fetch: Callable[[str, int, str], Optional[pd.DataFrame]],
                 tf: str, n_syms: int = 12, tol: float = 1e-9) -> dict:
        """조립한 봉을 REST klines 와 **한 봉씩** 대조한다.

        통과 못 하면 이 피드를 쓰면 안 된다 — 백테스트와 신호가 갈린다."""
        snap = self.snapshot(tf, 2)
        checked = ok = 0
        bad: list = []
        for sym in list(snap)[:n_syms]:
            ref = fetch(sym, 100, tf)
            if ref is None or ref.empty:
                continue
            mine = snap[sym]
            common = mine.index.intersection(ref.index)
            # 마지막 봉은 경합 가능 — 뺀다
            common = common[:-1] if len(common) else common
            for ts in common:
                checked += 1
                a, b = mine.loc[ts], ref.loc[ts]
                d = max(abs(float(a[c]) - float(b[c]))
                        for c in ("open", "high", "low", "close"))
                rel = d / max(abs(float(b["close"])), 1e-12)
                if rel <= tol:
                    ok += 1
                elif len(bad) < 5:
                    bad.append((sym, str(ts), round(rel, 10),
                                {c: (float(a[c]), float(b[c]))
                                 for c in ("open", "high", "low", "close")}))
        return {"checked": checked, "match": ok,
                "rate": round(100 * ok / checked, 3) if checked else None,
                "bad": bad}
