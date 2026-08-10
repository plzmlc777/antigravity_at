"""단기 페이퍼 — 시간 단위 **횡단면** 되돌림. 지정가 체결률을 실측한다.

배경 (2026-08-10):
  단기 트랙 10팔이 전부 **펀딩 정산 하나**의 변형이었다. 정보 구조가 다른 축을 연다.

    검증한 것              정보 구조
    자기 종목 주문흐름      종목 하나의 시계열      — 닫힘
    BTC 대비 잔차           종목 하나 대 선도       — 닫힘
    펀딩 정산 사건          종목 하나 + 일정        — 진행 중
    **횡단면 되돌림**       **그 시점 전 종목의 상대 위치**  ← 새 축

  몇 시간 동안 가장 많이 떨어진 종목은 되돌아오고 오른 종목은 되밀린다.
  하위 K 롱 + 상위 K 숏으로 **롱숏 동수**라 시장 방향과 무관하다.

백테스트 (daytrade_xsection_scan, 279종목 60일)
  과거 2h / 보유 8h / K=10 이 최선 — net -0.13bp, 마찰 약 12bp → **gross 약 +12bp**.
  과거 구간이 짧을수록 낫고(1~2h 되돌림) 길수록 모멘텀으로 뒤집힌다(8h -48bp).
  또 같은 벽이다 — 신호는 있는데 시장가 마찰이 정확히 그만큼이다.

**그런데 이 부류엔 빠져나갈 길이 있다 — 리밸런싱 시각을 우리가 정한다.**
  연속 신호 : 언제 올지 모름         → 시장가로 쫓아야   → 12bp
  펀딩 사건 : 시각을 앎              → 지정가 미리       →  2bp
  횡단면    : **시각을 우리가 정함**  → 지정가 걸고 대기  →  2bp
  종목은 그 순간에야 알지만 시각은 고른다. 정시에 순위를 매겨 지정가를 걸고
  보유 기간 동안 체결을 기다린다. 펀딩 페이퍼에서 15분 대기 체결률이 84% 였으니
  8시간이면 훨씬 높을 것이다 — **그 가정이 이 전략의 전부이므로 실측한다.**

방어 조건
  · lookahead: 순위는 리밸런싱 시각까지의 정보로만
  · 큐 모사: 내 앞 물량 + 내 주문이 **실제 체결로** 소진돼야 체결
  · 미체결도 미체결로 기록 (조용한 0 금지) — 체결률이 핵심 측정값이다
  · 롱숏 동수를 유지하되 **한쪽만 체결되는 경우를 별도 기록** — 실제 운영에서
    가장 위험한 상태다(시장 노출이 생긴다)

사용:
  python3 scripts/binance/daytrade_xsection_paper.py --lookback-h 2 --hold-h 8 --top-k 10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("daytrade_xsection_paper")

WS_BASE = "wss://fstream.binance.com/ws"
MAKER_FEE_BP = 2.0
TAKER_FEE_BP = 5.0
SUB_BATCH = 50
SUB_INTERVAL = 0.5


@dataclass
class Book:
    bid: float = 0.0
    ask: float = 0.0
    bid_usd: float = 0.0
    ask_usd: float = 0.0
    hist: deque = field(default_factory=lambda: deque(maxlen=64))  # (시각, 중간가)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0 if self.bid > 0 and self.ask > 0 else 0.0


@dataclass
class Leg:
    symbol: str
    side: str            # long | short
    entry_px: float
    queue_ahead: float
    posted_at: float
    entry_mid: float = 0.0
    filled: bool = False
    entry_ts: float = 0.0
    exit_px: float = 0.0
    exit_queue: float = 0.0
    exit_mid: float = 0.0
    exit_taker: bool = False
    closed: bool = False


class XSectionPaper:
    def __init__(self, symbols: list[str], notional: float, top_k: int,
                 lookback_h: int, hold_h: int, out_dir: Path):
        self.symbols = symbols
        self.notional = notional
        self.top_k = top_k
        self.lookback_h = lookback_h
        self.hold_h = hold_h
        self.out_dir = out_dir
        self.book = {s: Book() for s in symbols}
        self.legs: dict[str, Leg] = {}
        self.records: list = []
        self.rounds = 0

    def on_book(self, sym: str, bid: float, ask: float, bq: float, aq: float) -> None:
        b = self.book.get(sym)
        if b is None or not (bid > 0 and ask > bid):
            return
        b.bid, b.ask = bid, ask
        b.bid_usd, b.ask_usd = bq * bid, aq * ask

    def snapshot(self) -> None:
        """정시마다 중간가를 남긴다 — 순위의 재료."""
        now = time.time()
        for s, b in self.book.items():
            if b.mid > 0:
                b.hist.append((now, b.mid))

    def on_trade(self, sym: str, price: float, qty: float, buyer_maker: bool) -> None:
        lg = self.legs.get(sym)
        if lg is None:
            return
        n = price * qty
        if not lg.filled:
            hit = ((buyer_maker and price <= lg.entry_px) if lg.side == "long"
                   else ((not buyer_maker) and price >= lg.entry_px))
            if hit:
                lg.queue_ahead -= n
                if lg.queue_ahead <= 0:
                    b = self.book[sym]
                    lg.filled = True
                    lg.entry_mid = b.mid or lg.entry_px
                    lg.entry_ts = time.time()
        elif lg.exit_px > 0 and not lg.closed:
            hit = (((not buyer_maker) and price >= lg.exit_px) if lg.side == "long"
                   else (buyer_maker and price <= lg.exit_px))
            if hit:
                lg.exit_queue -= n
                if lg.exit_queue <= 0:
                    self._close(sym, lg, taker=False)

    def _close(self, sym: str, lg: Leg, taker: bool) -> None:
        b = self.book[sym]
        sign = 1.0 if lg.side == "long" else -1.0
        if taker:
            lg.exit_px = (b.bid if lg.side == "long" else b.ask) or lg.entry_px
            lg.exit_taker = True
        lg.exit_mid = b.mid or lg.exit_px
        lg.closed = True
        gross = ((lg.exit_px / lg.entry_px - 1.0) * sign) if lg.entry_px > 0 else 0.0
        fee = (MAKER_FEE_BP + (TAKER_FEE_BP if taker else MAKER_FEE_BP)) / 1e4
        edge_in = (((lg.entry_mid - lg.entry_px) / lg.entry_mid * 1e4 * sign)
                   if lg.entry_mid else 0.0)
        self.records.append({
            "t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "round": self.rounds, "symbol": sym, "side": lg.side,
            "gross_bp": round(gross * 1e4, 3), "fee_bp": round(fee * 1e4, 3),
            "net_bp": round((gross - fee) * 1e4, 3),
            "edge_in_bp": round(edge_in, 3), "exit_taker": taker,
            "queue_wait_sec": (round(lg.entry_ts - lg.posted_at, 1)
                               if lg.entry_ts else None),
        })

    # ── 리밸런싱 ─────────────────────────────────────────────
    def rebalance(self) -> dict:
        """정시: 과거 L시간 수익률로 줄 세워 하위 K 롱 / 상위 K 숏에 지정가."""
        cutoff = time.time() - self.lookback_h * 3600
        rets = {}
        for s, b in self.book.items():
            past = [m for (t, m) in b.hist if t <= cutoff]
            if not past or b.mid <= 0:
                continue
            rets[s] = b.mid / past[-1] - 1.0
        if len(rets) < self.top_k * 2 + 10:
            log.warning("순위 대상 부족 %d — 리밸런싱 건너뜀", len(rets))
            return {"skipped": True, "n_rank": len(rets)}
        order = sorted(rets, key=lambda k: rets[k])
        longs, shorts = order[:self.top_k], order[-self.top_k:]
        self.legs.clear()
        for s, side in [(x, "long") for x in longs] + [(x, "short") for x in shorts]:
            b = self.book[s]
            px = b.bid if side == "long" else b.ask
            q0 = b.bid_usd if side == "long" else b.ask_usd
            if px <= 0:
                continue
            self.legs[s] = Leg(s, side, px, q0 + self.notional, time.time())
        self.rounds += 1
        log.info("[리밸런싱 %d] 순위 %d종목 → 롱 %d / 숏 %d 지정가 게시",
                 self.rounds, len(rets), len(longs), len(shorts))
        return {"skipped": False, "n_rank": len(rets), "posted": len(self.legs)}

    def start_exit(self) -> None:
        for s, lg in self.legs.items():
            if lg.filled and not lg.closed:
                b = self.book[s]
                px = b.ask if lg.side == "long" else b.bid
                q0 = b.ask_usd if lg.side == "long" else b.bid_usd
                if px > 0:
                    lg.exit_px, lg.exit_queue = px, q0 + self.notional

    def force_close(self) -> None:
        for s, lg in list(self.legs.items()):
            if lg.filled and not lg.closed:
                self._close(s, lg, taker=True)

    def summary(self) -> dict:
        posted = len(self.legs)
        filled = sum(1 for l in self.legs.values() if l.filled)
        nl = sum(1 for l in self.legs.values() if l.filled and l.side == "long")
        ns = filled - nl
        out = {"round": self.rounds, "posted": posted, "filled": filled,
               "fill_rate": round(filled / posted, 4) if posted else 0.0,
               "long_filled": nl, "short_filled": ns,
               # 한쪽만 체결되면 시장 노출이 생긴다 — 운영상 가장 위험한 상태다
               "imbalance": abs(nl - ns)}
        rec = [r for r in self.records if r["round"] == self.rounds]
        if rec:
            import statistics as st
            out.update({
                "net_bp": round(st.mean(r["net_bp"] for r in rec), 3),
                "edge_in_bp": round(st.mean(r["edge_in_bp"] for r in rec), 3),
                "taker_exit_frac": round(
                    sum(1 for r in rec if r["exit_taker"]) / len(rec), 3),
                "queue_wait_med": round(st.median(
                    [r["queue_wait_sec"] for r in rec
                     if r["queue_wait_sec"] is not None] or [0]), 1),
            })
        return out

    def persist(self) -> None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        d = self.out_dir / day
        d.mkdir(parents=True, exist_ok=True)
        if self.records:
            with open(d / "fills.jsonl", "a") as fh:
                for r in self.records:
                    fh.write(json.dumps(r) + "\n")
            self.records.clear()
        with open(d / "_rounds.jsonl", "a") as fh:
            fh.write(json.dumps(self.summary(), ensure_ascii=False) + "\n")


async def _conn(xp: XSectionPaper, streams: list, name: str,
                stop: asyncio.Event, gaps: list) -> None:
    """상시 연결. 끊기면 재연결한다 — 연결 문제가 전략 타임라인을 망가뜨리면 안 된다."""
    import websockets
    delay = 1.0
    while not stop.is_set():
        t0 = time.time()
        try:
            async with websockets.connect(WS_BASE, ping_interval=180,
                                          ping_timeout=600, max_size=2 ** 22) as ws:
                for i in range(0, len(streams), SUB_BATCH):
                    await ws.send(json.dumps({"method": "SUBSCRIBE",
                                              "params": streams[i:i + SUB_BATCH],
                                              "id": i + 1}))
                    await asyncio.sleep(SUB_INTERVAL)
                log.info("  [%s] 연결 — %d스트림", name, len(streams))
                delay = 1.0
                while not stop.is_set():
                    try:
                        d = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                    except asyncio.TimeoutError:
                        continue
                    e = d.get("e")
                    if e == "bookTicker":
                        xp.on_book(d["s"], float(d["b"]), float(d["a"]),
                                   float(d["B"]), float(d["A"]))
                    elif e == "trade":
                        xp.on_trade(d["s"], float(d["p"]), float(d["q"]), bool(d["m"]))
        except asyncio.CancelledError:
            return
        except Exception as ex:
            if stop.is_set():
                return
            gaps.append({"conn": name, "uptime_sec": round(time.time() - t0, 1)})
            log.warning("  [%s] 끊김 — %s. %.0f초 후 재연결", name, str(ex)[:60], delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def amain(args) -> int:
    syms = [ln.strip().upper() for ln in Path(args.symbols).read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    xp = XSectionPaper(syms, args.notional, args.top_k, args.lookback_h,
                       args.hold_h, Path(args.out_dir))
    log.info("단기 페이퍼 [횡단면 되돌림] — %d종목 | 주문 $%.0f | "
             "과거 %dh 로 순위 → 하위/상위 %d종목 롱숏 | 보유 %dh",
             len(syms), args.notional, args.lookback_h, args.top_k, args.hold_h)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sg in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sg, stop.set)

    half = (len(syms) + 1) // 2
    gaps: list = []
    tasks = [asyncio.create_task(_conn(
        xp, [f"{s.lower()}@bookTicker" for s in g] + [f"{s.lower()}@trade" for s in g],
        f"conn{i}", stop, gaps))
        for i, g in enumerate([syms[:half], syms[half:]]) if g]

    async def clock():
        """정시마다 중간가 스냅샷. 순위의 재료이고, lookback 만큼 쌓여야 시작한다."""
        while not stop.is_set():
            now = datetime.now(timezone.utc)
            nxt = (now.replace(minute=0, second=0, microsecond=0)
                   + timedelta(hours=1))
            try:
                await asyncio.wait_for(stop.wait(),
                                       timeout=(nxt - now).total_seconds())
                return
            except asyncio.TimeoutError:
                pass
            xp.snapshot()
    tasks.append(asyncio.create_task(clock()))

    # 과거 구간이 쌓일 때까지 기다린 뒤 시작한다 (조용한 오판 금지)
    warm = args.lookback_h + 1
    log.info("과거 %d시간 관측이 쌓일 때까지 대기 (약 %d시간)", args.lookback_h, warm)
    try:
        await asyncio.wait_for(stop.wait(), timeout=warm * 3600)
        stop.set()
    except asyncio.TimeoutError:
        pass

    while not stop.is_set():
        r = xp.rebalance()
        if not r.get("skipped"):
            try:
                await asyncio.wait_for(stop.wait(), timeout=args.hold_h * 3600)
                break
            except asyncio.TimeoutError:
                pass
            xp.start_exit()
            try:
                await asyncio.wait_for(stop.wait(), timeout=300)   # 5분 유예
                break
            except asyncio.TimeoutError:
                pass
            xp.force_close()
            s = xp.summary()
            log.info("[라운드 %d] 게시 %d / 체결 %d (%.1f%%) | net %s bp | "
                     "지정가이점 %s bp | 큐대기 %s초 | 롱숏 불균형 %d | 연결끊김 %d",
                     s["round"], s["posted"], s["filled"], s["fill_rate"] * 100,
                     s.get("net_bp", "--"), s.get("edge_in_bp", "--"),
                     s.get("queue_wait_med", "--"), s["imbalance"], len(gaps))
            xp.persist()
        else:
            await asyncio.sleep(600)
    for t in tasks:
        t.cancel()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="단기 페이퍼 — 횡단면 되돌림")
    p.add_argument("--symbols",
                   default=str(ROOT / "configs" / "daytrade_funding_symbols.txt"))
    p.add_argument("--notional", type=float, default=200.0)
    p.add_argument("--lookback-h", type=int, default=2, help="순위 매길 과거 구간")
    p.add_argument("--hold-h", type=int, default=8)
    p.add_argument("--top-k", type=int, default=10, help="한쪽 종목 수")
    p.add_argument("--out-dir", default=str(ROOT / "runs" / "daytrade_xsection_paper"))
    args = p.parse_args()
    try:
        return asyncio.run(amain(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
