"""단타 트랙 페이퍼 — 펀딩 정산 사건. **지정가 체결률을 실측한다.**

왜 이게 필요한가 (2026-08-10):
  `ultra_event_scan.py` 가 279종목 60일에서 정산 고유 효과 **+9.6~15.3bp** 를 찾았다
  (2겹 대조 검증: 정산 없는 정각 0bp, 같은 펀딩률 구간의 다른 시각 대비 차이 일정).

  그런데 마찰이 갈림길이다.
      시장가로 쫓아가면   11 − 12.2 = −1.2bp   미달
      지정가를 미리 걸면  11 −  2.0 = +9.0bp   넘음
  **예정된 시각이라 쫓아갈 이유가 없다** — 15분 전에 지정가를 건다. 이게 이 전략의
  전부이자 유일한 전제다. 그러니 **그 지정가가 실제로 체결되는지가 생사를 가른다.**
  백테스트로는 절대 답이 안 나온다. 그래서 페이퍼로 실측한다.

무엇을 재는가 (순서대로 중요)
  1. **체결률** — T-15분에 최우선 매수호가에 건 지정가가 T 까지 체결되는가
  2. 체결 시점 — 얼마나 기다렸나 (큐 대기)
  3. 진입가 대비 중간가 — 지정가 이점이 실제로 얼마인가
  4. 청산 — T+15분에 지정가 매도, 미체결 시 시장가 (그 비용도 기록)
  5. 순손익 분해 — 지정가 이점 / 가격 이동 / 수수료 / 시장가 청산 비용

설계
  · 사건 시각: 00/08/16 UTC (종목별 예외는 REST nextFundingTime 으로 확인)
  · T-20분에 구독 시작 → T-15분 진입 → T+15분 청산 → T+20분 구독 해제
    상시 구독하지 않는다. 261종목 bookTicker 를 24시간 받을 이유가 없고,
    사건 창은 하루 3회 x 40분 = 2시간뿐이다.
  · 큐 모사는 `ultra_mm_paper.py` 와 같은 규칙 — 내 앞 물량 + 내 주문이
    실제 체결로 소진돼야 체결. 호가 이동만으로는 체결시키지 않는다.

방어 조건
  · 미확정 데이터 금지 — 봉 마감/체결 스트림만 신뢰
  · 조용한 0 금지 — 미체결도 미체결로 기록한다. 그게 핵심 측정값이다.
  · 표본 1,000건 미만은 판정하지 않는다 (2026-08-10 소표본에 세 번 속았다)

사용:
  python3 scripts/binance/daytrade_funding_paper.py \\
      --symbols configs/daytrade_funding_symbols.txt
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("daytrade_funding_paper")

WS_BASE = "wss://fstream.binance.com/ws"
PREMIUM_INDEX = "https://fapi.binance.com/fapi/v1/premiumIndex"

MAKER_FEE_BP = 2.0
TAKER_FEE_BP = 5.0
SUB_BATCH = 100
SUB_INTERVAL = 0.4

# 사건 창 (분). 기본값은 백테스트 최적점(진입 T-15 / 청산 T+15 = 보유 30분).
# 아래는 런타임에 덮어쓴다 — 같은 사건에서 여러 가설을 나란히 돌리기 위해서다.
#
# 백테스트가 짚어준 후보들 (ultra_event_scan, 279종목 60일):
#   기본  진입 -15 / 청산 +15 (보유 30) 롱   → 정산 고유 +12.56bp
#   되돌림 진입 +15 / 청산 +75 (보유 60) 숏   → -5.4 ~ -19.1bp (부호 반대, 메커니즘 대칭)
#   조기  진입 -30 / 청산 +30 (보유 60) 롱   → +5.39bp
#   지연  진입  -5 / 청산 +10 (보유 15) 롱   → +7.02bp
PRE_SUBSCRIBE_MIN = 20      # 사건 시각 기준 구독 시작 (진입보다 5분 이상 앞서야)
ENTRY_MIN = -15             # 진입 시점 (사건 대비 분. 음수=이전)
EXIT_MIN = 15               # 청산 시점 (사건 대비 분)
POST_MIN = 20               # 구독 해제 (청산보다 뒤여야)
EXIT_GRACE_MIN = 3          # 청산 지정가를 이만큼 기다린 뒤 시장가
SIDE = "long"               # long | short
MIN_FUNDING_BP = 0.0        # |펀딩률| 이 이보다 작은 종목은 건너뛴다


@dataclass
class Pos:
    symbol: str
    entry_px: float = 0.0
    entry_mid: float = 0.0
    entry_ts: float = 0.0
    queue_ahead: float = 0.0
    queue0: float = 0.0
    posted_at: float = 0.0
    filled: bool = False
    exit_px: float = 0.0
    exit_mid: float = 0.0
    exit_taker: bool = False
    exit_queue: float = 0.0
    exit_posted: float = 0.0
    closed: bool = False


@dataclass
class Book:
    bid: float = 0.0
    ask: float = 0.0
    bid_usd: float = 0.0
    ask_usd: float = 0.0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0 if self.bid > 0 and self.ask > 0 else 0.0


class FundingPaper:
    def __init__(self, symbols: list[str], notional: float, out_dir: Path):
        self.symbols = symbols
        self.notional = notional
        self.out_dir = out_dir
        self.book: dict[str, Book] = {s: Book() for s in symbols}
        self.pos: dict[str, Pos] = {}
        self.funding: dict[str, float] = {}     # 종목 → 펀딩률 (MIN_FUNDING_BP 용)
        self.phase = "idle"          # idle | armed | holding | closing
        self.records: list = []
        self.stats = {"events": 0, "armed": 0, "filled": 0, "closed": 0,
                      "exit_taker": 0}

    # ── 스트림 ────────────────────────────────────────────────
    def on_book(self, sym: str, bid: float, ask: float, bq: float, aq: float) -> None:
        b = self.book.get(sym)
        if b is None or not (bid > 0 and ask > bid):
            return
        b.bid, b.ask = bid, ask
        b.bid_usd, b.ask_usd = bq * bid, aq * ask

    def on_trade(self, sym: str, price: float, qty: float, buyer_maker: bool) -> None:
        p = self.pos.get(sym)
        if p is None:
            return
        n = price * qty
        if not p.filled:
            # 진입 체결: 롱(매수 지정가)은 테이커 **매도**가, 숏(매도 지정가)은
            # 테이커 **매수**가 큐를 소진해야 한다.
            hit = ((buyer_maker and price <= p.entry_px) if SIDE == "long"
                   else ((not buyer_maker) and price >= p.entry_px))
            if hit:
                p.queue_ahead -= n
                if p.queue_ahead <= 0:
                    b = self.book[sym]
                    p.filled = True
                    p.entry_mid = b.mid or p.entry_px
                    p.entry_ts = time.time()
                    self.stats["filled"] += 1
        elif p.exit_px > 0 and not p.closed:
            # 청산은 진입의 반대편이다.
            hit = (((not buyer_maker) and price >= p.exit_px) if SIDE == "long"
                   else (buyer_maker and price <= p.exit_px))
            if hit:
                p.exit_queue -= n
                if p.exit_queue <= 0:
                    self._close(sym, p, taker=False)

    def _close(self, sym: str, p: Pos, taker: bool) -> None:
        b = self.book[sym]
        if taker:
            # 시장가 청산은 반대편 호가를 친다 (롱→매수호가, 숏→매도호가)
            p.exit_px = (b.bid if SIDE == "long" else b.ask) or p.entry_px
            p.exit_taker = True
            self.stats["exit_taker"] += 1
        p.exit_mid = b.mid or p.exit_px
        p.closed = True
        self.stats["closed"] += 1
        sign = 1.0 if SIDE == "long" else -1.0
        gross = ((p.exit_px / p.entry_px - 1.0) * sign) if p.entry_px > 0 else 0.0
        fee = (MAKER_FEE_BP + (TAKER_FEE_BP if taker else MAKER_FEE_BP)) / 1e4
        # 지정가 이점 = 중간가 대비 얼마나 유리하게 샀나
        edge_in = (((p.entry_mid - p.entry_px) / p.entry_mid * 1e4 * sign)
                   if p.entry_mid else 0.0)
        edge_out = (((p.exit_px - p.exit_mid) / p.exit_mid * 1e4 * sign)
                    if p.exit_mid else 0.0)
        self.records.append({
            "t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "symbol": sym, "entry_px": p.entry_px, "exit_px": p.exit_px,
            "gross_bp": round(gross * 1e4, 3), "fee_bp": round(fee * 1e4, 3),
            "net_bp": round((gross - fee) * 1e4, 3),
            "edge_in_bp": round(edge_in, 3), "edge_out_bp": round(edge_out, 3),
            "exit_taker": taker, "side": SIDE,
            "queue_wait_sec": round(p.entry_ts - p.posted_at, 1) if p.entry_ts else None,
        })

    async def refresh_funding(self) -> None:
        """펀딩률 갱신. MIN_FUNDING_BP 필터의 입력이다."""
        if MIN_FUNDING_BP <= 0:
            return
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.get(PREMIUM_INDEX,
                                 timeout=aiohttp.ClientTimeout(total=45)) as r:
                    data = await r.json()
            self.funding = {x["symbol"]: float(x.get("lastFundingRate") or 0.0)
                            for x in data}
            hi = sum(1 for v in self.funding.values()
                     if abs(v) * 1e4 >= MIN_FUNDING_BP)
            log.info("펀딩률 갱신 %d종목 — |rate| >= %.1fbp 인 종목 %d개",
                     len(self.funding), MIN_FUNDING_BP, hi)
        except Exception as e:
            log.warning("펀딩률 갱신 실패: %s — 필터를 적용하지 않는다", e)
            self.funding = {}

    # ── 사건 진행 ─────────────────────────────────────────────
    def arm(self) -> None:
        """진입 시점: 롱이면 매수호가에, 숏이면 매도호가에 지정가를 건다."""
        self.pos.clear()
        n = skipped = 0
        for s in self.symbols:
            if MIN_FUNDING_BP > 0:
                fr = abs(self.funding.get(s, 0.0)) * 1e4
                if fr < MIN_FUNDING_BP:
                    skipped += 1
                    continue
            b = self.book[s]
            px = b.bid if SIDE == "long" else b.ask
            q0 = b.bid_usd if SIDE == "long" else b.ask_usd
            if px <= 0:
                continue
            q = q0 + self.notional             # 내 앞 물량 + 내 주문
            self.pos[s] = Pos(symbol=s, entry_px=px, queue_ahead=q, queue0=q,
                              posted_at=time.time())
            n += 1
        self.stats["armed"] += n
        self.phase = "holding"
        log.info("[진입] %s 지정가 게시 %d종목%s", "매수" if SIDE == "long" else "매도",
                 n, f" (펀딩률 미달 {skipped}종목 제외)" if skipped else "")

    def start_exit(self) -> None:
        """청산 시점: 진입의 반대편 호가에 지정가."""
        n = 0
        for s, p in self.pos.items():
            if p.filled and not p.closed:
                b = self.book[s]
                px = b.ask if SIDE == "long" else b.bid
                q0 = b.ask_usd if SIDE == "long" else b.bid_usd
                if px <= 0:
                    continue
                p.exit_px = px
                p.exit_queue = q0 + self.notional
                p.exit_posted = time.time()
                n += 1
        self.phase = "closing"
        log.info("[청산] 지정가 매도 %d종목", n)

    def force_exit(self) -> None:
        """유예 후에도 미체결이면 시장가. 그 비용도 기록한다."""
        n = 0
        for s, p in self.pos.items():
            if p.filled and not p.closed:
                self._close(s, p, taker=True)
                n += 1
        if n:
            log.info("[강제청산] 시장가 %d종목", n)

    def finish(self) -> dict:
        armed = sum(1 for p in self.pos.values())
        filled = sum(1 for p in self.pos.values() if p.filled)
        rec = [r for r in self.records]
        fill_rate = filled / armed if armed else 0.0
        summ = {"armed": armed, "filled": filled, "fill_rate": round(fill_rate, 4),
                "closed": len(rec)}
        if rec:
            import statistics as st
            summ.update({
                "net_bp_mean": round(st.mean(r["net_bp"] for r in rec), 3),
                "gross_bp_mean": round(st.mean(r["gross_bp"] for r in rec), 3),
                "edge_in_bp_mean": round(st.mean(r["edge_in_bp"] for r in rec), 3),
                "taker_exit_frac": round(
                    sum(1 for r in rec if r["exit_taker"]) / len(rec), 3),
                "queue_wait_med": round(st.median(
                    [r["queue_wait_sec"] for r in rec
                     if r["queue_wait_sec"] is not None] or [0]), 1),
            })
        return summ

    def persist(self, tag: str) -> None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        d = self.out_dir / day
        d.mkdir(parents=True, exist_ok=True)
        if self.records:
            with open(d / "fills.jsonl", "a") as fh:
                for r in self.records:
                    fh.write(json.dumps(r) + "\n")
        with open(d / "_events.jsonl", "a") as fh:
            fh.write(json.dumps({"event": tag, **self.finish()}) + "\n")
        self.records.clear()


async def next_funding_time() -> datetime:
    """다음 정산 시각. 기본 8h 주기이나 API 값을 우선한다."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(PREMIUM_INDEX, params={"symbol": "BTCUSDT"},
                             timeout=aiohttp.ClientTimeout(total=30)) as r:
                d = await r.json()
        return datetime.fromtimestamp(int(d["nextFundingTime"]) / 1000, tz=timezone.utc)
    except Exception as e:
        log.warning("nextFundingTime 조회 실패: %s — 00/08/16 UTC 로 계산", e)
        now = datetime.now(timezone.utc)
        h = ((now.hour // 8) + 1) * 8
        base = now.replace(minute=0, second=0, microsecond=0)
        return (base.replace(hour=0) + timedelta(hours=h)) if h < 24 else \
            (base.replace(hour=0) + timedelta(days=1))


async def event_cycle(fp: FundingPaper, T: datetime, stop: asyncio.Event) -> None:
    """한 사건 창을 처리한다. 구독은 창 안에서만 유지한다."""
    import websockets
    streams = [f"{s.lower()}@bookTicker" for s in fp.symbols] + \
              [f"{s.lower()}@trade" for s in fp.symbols]
    await fp.refresh_funding()
    try:
        async with websockets.connect(WS_BASE, ping_interval=180,
                                      ping_timeout=600, max_size=2 ** 22) as ws:
            for i in range(0, len(streams), SUB_BATCH):
                await ws.send(json.dumps({"method": "SUBSCRIBE",
                                          "params": streams[i:i + SUB_BATCH],
                                          "id": i + 1}))
                await asyncio.sleep(SUB_INTERVAL)
            log.info("구독 %d스트림 — 사건 %s UTC", len(streams),
                     T.strftime("%m-%d %H:%M"))
            done_arm = done_exit = done_force = False
            while not stop.is_set():
                now = datetime.now(timezone.utc)
                if now >= T + timedelta(minutes=EXIT_MIN + EXIT_GRACE_MIN + 2):
                    break
                if not done_arm and now >= T + timedelta(minutes=ENTRY_MIN):
                    fp.arm(); done_arm = True
                if not done_exit and now >= T + timedelta(minutes=EXIT_MIN):
                    fp.start_exit(); done_exit = True
                if (not done_force and done_exit
                        and now >= T + timedelta(minutes=EXIT_MIN + EXIT_GRACE_MIN)):
                    fp.force_exit(); done_force = True
                try:
                    d = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                except asyncio.TimeoutError:
                    continue
                e = d.get("e")
                if e == "bookTicker":
                    fp.on_book(d["s"], float(d["b"]), float(d["a"]),
                               float(d["B"]), float(d["A"]))
                elif e == "trade":
                    fp.on_trade(d["s"], float(d["p"]), float(d["q"]), bool(d["m"]))
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.warning("사건 창 오류: %s", e)
    finally:
        fp.force_exit()
        s = fp.finish()
        log.info("[사건 종료 %s] 게시 %d / 체결 %d (체결률 %.1f%%) | "
                 "net %s bp | 지정가이점 %s bp | 큐대기 %s초 | 시장가청산 %s",
                 T.strftime("%m-%d %H:%M"), s.get("armed", 0), s.get("filled", 0),
                 s.get("fill_rate", 0) * 100, s.get("net_bp_mean", "--"),
                 s.get("edge_in_bp_mean", "--"), s.get("queue_wait_med", "--"),
                 f"{s.get('taker_exit_frac', 0) * 100:.0f}%")
        fp.persist(T.strftime("%Y-%m-%dT%H:%MZ"))
        fp.stats["events"] += 1


async def amain(args) -> int:
    syms = [ln.strip().upper() for ln in Path(args.symbols).read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    if not syms:
        log.error("종목 없음")
        return 1
    fp = FundingPaper(syms, args.notional, Path(args.out_dir))
    log.info("단타 페이퍼 [펀딩 정산 · %s] — %d종목 | 주문 $%.0f | %s | "
             "진입 T%+d분 / 청산 T%+d분 (보유 %d분)%s",
             args.tag, len(syms), args.notional,
             "롱" if SIDE == "long" else "숏", ENTRY_MIN, EXIT_MIN,
             EXIT_MIN - ENTRY_MIN,
             f" | 펀딩 >= {MIN_FUNDING_BP:.1f}bp" if MIN_FUNDING_BP > 0 else "")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sg in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sg, stop.set)

    while not stop.is_set():
        T = await next_funding_time()
        wake = T + timedelta(minutes=ENTRY_MIN - 5)
        wait = (wake - datetime.now(timezone.utc)).total_seconds()
        if wait > 0:
            log.info("다음 사건 %s UTC — %.1f분 대기 (그동안 구독 없음)",
                     T.strftime("%m-%d %H:%M"), wait / 60)
            try:
                await asyncio.wait_for(stop.wait(), timeout=wait)
                break
            except asyncio.TimeoutError:
                pass
        await event_cycle(fp, T, stop)
        await asyncio.sleep(60)      # 같은 사건 재진입 방지
    log.info("종료 — 사건 %d회 / 게시 %d / 체결 %d",
             fp.stats["events"], fp.stats["armed"], fp.stats["filled"])
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="단타 페이퍼 — 펀딩 정산 사건")
    p.add_argument("--symbols",
                   default=str(ROOT / "configs" / "daytrade_funding_symbols.txt"))
    p.add_argument("--notional", type=float, default=200.0)
    p.add_argument("--out-dir", default=str(ROOT / "runs" / "daytrade_funding_paper"))
    p.add_argument("--entry-min", type=int, default=-15,
                   help="진입 시점 (사건 대비 분, 음수=이전)")
    p.add_argument("--exit-min", type=int, default=15,
                   help="청산 시점 (사건 대비 분)")
    p.add_argument("--side", choices=["long", "short"], default="long")
    p.add_argument("--min-funding-bp", type=float, default=0.0,
                   help="|펀딩률| 이 이보다 작은 종목 제외. 백테스트에서 양 3~10bp "
                        "구간이 +24.39bp 로 전체 평균의 2.4배였다")
    p.add_argument("--tag", default="base", help="출력 구분용")
    args = p.parse_args()

    global ENTRY_MIN, EXIT_MIN, SIDE, MIN_FUNDING_BP
    ENTRY_MIN, EXIT_MIN = args.entry_min, args.exit_min
    SIDE, MIN_FUNDING_BP = args.side, args.min_funding_bp
    if ENTRY_MIN >= EXIT_MIN:
        log.error("진입(%d)이 청산(%d)보다 뒤다", ENTRY_MIN, EXIT_MIN)
        return 1
    try:
        return asyncio.run(amain(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
