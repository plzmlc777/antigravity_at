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
SUB_BATCH = 50      # 정산 순간 밀림 대비해 낮춤
SUB_INTERVAL = 0.5

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
SIDE = "long"               # long | short (단일 팔 모드 기본값)
MIN_FUNDING_BP = 0.0        # |펀딩률| 이 이보다 작은 종목은 건너뛴다

# ── 다중 팔 (2026-08-10) ──────────────────────────────────────────────
# 사건은 하루 세 번뿐이라 팔을 늘려도 추가 비용이 없다 — 시간을 놀릴 이유가 없다.
# 다만 팔마다 별도 프로세스로 522스트림씩 구독하면 자원이 배로 든다. 첫 사건에서
# **한 팔만으로도 연결이 두 번 끊겼다.** 팔들이 같은 종목·같은 데이터를 보므로
# **한 프로세스가 여러 팔을 함께 돌린다** — 팔이 몇 개든 스트림은 522개 그대로다.
#
# 각 팔은 ultra_event_scan 이 짚어준 지점이다 (279종목 60일, 정산−대조 차이):
ARMS_DEFAULT = [
    # (태그,        진입, 청산, 방향,    펀딩필터, 백테스트 차이)
    ("base",        -15,  15,  "long",   0.0,  "+10.56bp 최대"),
    ("early",       -30,  30,  "long",   0.0,  "+5.39bp, 지정가 걸 시간 2배"),
    ("hifr",        -15,  15,  "long",   3.0,  "+24.39bp (모멘텀 성분 포함)"),
    ("reversal",     15,  75,  "short",  0.0,  "-7.77bp 되돌림"),
    ("late5",        -5,  10,  "long",   0.0,  "+7.02bp, 노출 15분으로 최소"),
    ("late1",        -1,  14,  "long",   0.0,  "+7.25bp, 정산 직전 진입"),
    ("pre60",       -60,   0,  "long",   0.0,  "+4.44bp, 정산 전 구간만 (관통 안 함)"),
    ("post1",         1,  16,  "long",   0.0,  "+4.77bp, 정산 직후 롱"),
    ("rev30",        15,  45,  "short",  0.0,  "-5.39bp 되돌림 짧은 버전"),
    ("wide",        -15,  45,  "long",   0.0,  "+5.44bp, 되돌림까지 관통"),
]


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


@dataclass
class Arm:
    """팔 하나. 같은 호가·체결 스트림을 공유하되 포지션과 기록은 독립이다."""
    tag: str
    entry_min: int
    exit_min: int
    side: str
    min_fr: float
    note: str = ""
    pos: dict = field(default_factory=dict)
    records: list = field(default_factory=list)
    done_arm: bool = False
    done_exit: bool = False
    done_force: bool = False


class FundingPaper:
    def __init__(self, symbols: list[str], notional: float, out_dir: Path,
                 arms: list | None = None):
        self.symbols = symbols
        self.notional = notional
        self.out_dir = out_dir
        self.book: dict[str, Book] = {s: Book() for s in symbols}
        self.funding: dict[str, float] = {}     # 종목 → 펀딩률 (팔별 필터용)
        self.arms: list[Arm] = arms or [Arm("base", ENTRY_MIN, EXIT_MIN, SIDE,
                                            MIN_FUNDING_BP)]
        self.stats = {"events": 0}

    # ── 스트림 (모든 팔이 공유) ──────────────────────────────
    def on_book(self, sym: str, bid: float, ask: float, bq: float, aq: float) -> None:
        b = self.book.get(sym)
        if b is None or not (bid > 0 and ask > bid):
            return
        b.bid, b.ask = bid, ask
        b.bid_usd, b.ask_usd = bq * bid, aq * ask

    def on_trade(self, sym: str, price: float, qty: float, buyer_maker: bool) -> None:
        n = price * qty
        for arm in self.arms:
            p = arm.pos.get(sym)
            if p is None:
                continue
            if not p.filled:
                # 롱(매수 지정가)은 테이커 **매도**가, 숏(매도 지정가)은 테이커
                # **매수**가 큐를 소진해야 체결된다.
                hit = ((buyer_maker and price <= p.entry_px) if arm.side == "long"
                       else ((not buyer_maker) and price >= p.entry_px))
                if hit:
                    p.queue_ahead -= n
                    if p.queue_ahead <= 0:
                        b = self.book[sym]
                        p.filled = True
                        p.entry_mid = b.mid or p.entry_px
                        p.entry_ts = time.time()
            elif p.exit_px > 0 and not p.closed:
                hit = (((not buyer_maker) and price >= p.exit_px) if arm.side == "long"
                       else (buyer_maker and price <= p.exit_px))
                if hit:
                    p.exit_queue -= n
                    if p.exit_queue <= 0:
                        self._close(arm, sym, p, taker=False)

    def _close(self, arm: Arm, sym: str, p: Pos, taker: bool) -> None:
        b = self.book[sym]
        sign = 1.0 if arm.side == "long" else -1.0
        if taker:
            # 시장가 청산은 반대편 호가를 친다 (롱→매수호가, 숏→매도호가)
            p.exit_px = (b.bid if arm.side == "long" else b.ask) or p.entry_px
            p.exit_taker = True
        p.exit_mid = b.mid or p.exit_px
        p.closed = True
        gross = ((p.exit_px / p.entry_px - 1.0) * sign) if p.entry_px > 0 else 0.0
        fee = (MAKER_FEE_BP + (TAKER_FEE_BP if taker else MAKER_FEE_BP)) / 1e4
        edge_in = (((p.entry_mid - p.entry_px) / p.entry_mid * 1e4 * sign)
                   if p.entry_mid else 0.0)
        arm.records.append({
            "t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "arm": arm.tag, "symbol": sym, "side": arm.side,
            "entry_px": p.entry_px, "exit_px": p.exit_px,
            "gross_bp": round(gross * 1e4, 3), "fee_bp": round(fee * 1e4, 3),
            "net_bp": round((gross - fee) * 1e4, 3),
            "edge_in_bp": round(edge_in, 3), "exit_taker": taker,
            "queue_wait_sec": round(p.entry_ts - p.posted_at, 1) if p.entry_ts else None,
        })

    async def refresh_funding(self) -> None:
        """펀딩률 갱신. 팔별 필터의 입력이다."""
        if not any(a.min_fr > 0 for a in self.arms):
            return
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.get(PREMIUM_INDEX,
                                 timeout=aiohttp.ClientTimeout(total=45)) as r:
                    data = await r.json()
            self.funding = {x["symbol"]: float(x.get("lastFundingRate") or 0.0)
                            for x in data}
            log.info("펀딩률 갱신 %d종목", len(self.funding))
        except Exception as e:
            log.warning("펀딩률 갱신 실패: %s — 필터 미적용", e)
            self.funding = {}

    # ── 팔별 진행 ─────────────────────────────────────────────
    def arm_open(self, arm: Arm) -> None:
        arm.pos.clear()
        n = skipped = 0
        for s in self.symbols:
            if arm.min_fr > 0 and abs(self.funding.get(s, 0.0)) * 1e4 < arm.min_fr:
                skipped += 1
                continue
            b = self.book[s]
            px = b.bid if arm.side == "long" else b.ask
            q0 = b.bid_usd if arm.side == "long" else b.ask_usd
            if px <= 0:
                continue
            q = q0 + self.notional          # 내 앞 물량 + 내 주문
            arm.pos[s] = Pos(symbol=s, entry_px=px, queue_ahead=q, queue0=q,
                             posted_at=time.time())
            n += 1
        arm.done_arm = True
        log.info("  [%s] %s 지정가 %d종목%s", arm.tag,
                 "매수" if arm.side == "long" else "매도", n,
                 f" (펀딩 미달 {skipped} 제외)" if skipped else "")

    def arm_exit(self, arm: Arm) -> None:
        n = 0
        for s, p in arm.pos.items():
            if p.filled and not p.closed:
                b = self.book[s]
                px = b.ask if arm.side == "long" else b.bid
                q0 = b.ask_usd if arm.side == "long" else b.bid_usd
                if px <= 0:
                    continue
                p.exit_px, p.exit_queue = px, q0 + self.notional
                n += 1
        arm.done_exit = True
        log.info("  [%s] 청산 지정가 %d종목", arm.tag, n)

    def arm_force(self, arm: Arm) -> None:
        n = 0
        for s, p in arm.pos.items():
            if p.filled and not p.closed:
                self._close(arm, s, p, taker=True)
                n += 1
        arm.done_force = True
        if n:
            log.info("  [%s] 강제청산 시장가 %d종목", arm.tag, n)

    def arm_summary(self, arm: Arm) -> dict:
        armed = len(arm.pos)
        filled = sum(1 for p in arm.pos.values() if p.filled)
        rec = arm.records
        out = {"arm": arm.tag, "side": arm.side,
               "entry_min": arm.entry_min, "exit_min": arm.exit_min,
               "armed": armed, "filled": filled,
               "fill_rate": round(filled / armed, 4) if armed else 0.0,
               "closed": len(rec)}
        if rec:
            import statistics as st
            out.update({
                "net_bp": round(st.mean(r["net_bp"] for r in rec), 3),
                "gross_bp": round(st.mean(r["gross_bp"] for r in rec), 3),
                "edge_in_bp": round(st.mean(r["edge_in_bp"] for r in rec), 3),
                "taker_exit_frac": round(
                    sum(1 for r in rec if r["exit_taker"]) / len(rec), 3),
                "queue_wait_med": round(st.median(
                    [r["queue_wait_sec"] for r in rec
                     if r["queue_wait_sec"] is not None] or [0]), 1),
            })
        return out

    def persist(self, tag: str, gaps: list) -> None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        d = self.out_dir / day
        d.mkdir(parents=True, exist_ok=True)
        rows = []
        for arm in self.arms:
            if arm.records:
                with open(d / f"fills_{arm.tag}.jsonl", "a") as fh:
                    for r in arm.records:
                        fh.write(json.dumps(r) + "\n")
            rows.append(self.arm_summary(arm))
            arm.records.clear()
        with open(d / "_events.jsonl", "a") as fh:
            fh.write(json.dumps({"event": tag, "conn_gaps": len(gaps),
                                 "arms": rows}, ensure_ascii=False) + "\n")

    def reset(self) -> None:
        for a in self.arms:
            a.pos.clear(); a.records.clear()
            a.done_arm = a.done_exit = a.done_force = False


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


async def _conn(fp: "FundingPaper", streams: list, name: str,
                until: datetime, stop: asyncio.Event, gaps: list) -> None:
    """연결 하나를 창이 끝날 때까지 유지한다. **끊기면 재연결한다.**

    초판은 연결이 끊기면 사건을 통째로 포기하고 finally 에서 강제청산했다.
    2026-08-10 첫 사건에서 두 번 끊겼고(16:46, 정산 직후 17:00:00.8) 그 때문에
    청산 시각도 아닌데 시장가로 전부 털렸다 — net 수치가 통째로 무효가 됐다.
    연결 문제와 전략 타임라인은 **분리돼야 한다.**"""
    import websockets
    delay = 1.0
    while not stop.is_set() and datetime.now(timezone.utc) < until:
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
                while not stop.is_set() and datetime.now(timezone.utc) < until:
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
            return
        except Exception as ex:
            if stop.is_set() or datetime.now(timezone.utc) >= until:
                return
            up = time.time() - t0
            gaps.append({"conn": name, "uptime_sec": round(up, 1), "err": str(ex)[:80]})
            log.warning("  [%s] 끊김 (%.0f초 유지) — %s. %.0f초 후 재연결",
                        name, up, str(ex)[:60], delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def event_cycle(fp: FundingPaper, T: datetime, stop: asyncio.Event) -> None:
    """한 사건 창. **타임라인은 연결 상태와 무관하게 흐르고, 모든 팔이 한 스트림을
    공유한다.** 팔이 몇 개든 구독은 그대로다 — 팔마다 프로세스를 띄우면 첫 사건에서
    겪은 연결 끊김이 배로 늘어난다."""
    fp.reset()
    t_start = min(T + timedelta(minutes=a.entry_min) for a in fp.arms)
    t_end = max(T + timedelta(minutes=a.exit_min + EXIT_GRACE_MIN)
                for a in fp.arms) + timedelta(minutes=2)

    half = (len(fp.symbols) + 1) // 2
    groups = [fp.symbols[:half], fp.symbols[half:]]
    gaps: list = []
    tasks = [asyncio.create_task(_conn(
        fp, [f"{s.lower()}@bookTicker" for s in g] + [f"{s.lower()}@trade" for s in g],
        f"conn{i}", t_end, stop, gaps)) for i, g in enumerate(groups) if g]

    await fp.refresh_funding()
    log.info("사건 %s UTC — 팔 %d개 / 창 %s ~ %s", T.strftime("%m-%d %H:%M"),
             len(fp.arms), t_start.strftime("%H:%M"), t_end.strftime("%H:%M"))
    while not stop.is_set():
        now = datetime.now(timezone.utc)
        if now >= t_end:
            break
        for arm in fp.arms:
            if not arm.done_arm and now >= T + timedelta(minutes=arm.entry_min):
                fp.arm_open(arm)
            if (not arm.done_exit and arm.done_arm
                    and now >= T + timedelta(minutes=arm.exit_min)):
                fp.arm_exit(arm)
            if (not arm.done_force and arm.done_exit
                    and now >= T + timedelta(minutes=arm.exit_min + EXIT_GRACE_MIN)):
                fp.arm_force(arm)
        await asyncio.sleep(0.5)

    for t in tasks:
        t.cancel()
    # 창이 실제로 끝난 뒤에만 정리한다
    for arm in fp.arms:
        if not arm.done_force:
            fp.arm_force(arm)

    log.info("[사건 종료 %s] 연결끊김 %d회", T.strftime("%m-%d %H:%M"), len(gaps))
    log.info("  %-9s %-6s %7s %7s %8s %9s %9s %8s %7s",
             "팔", "방향", "게시", "체결", "체결률", "net bp", "지정가이점",
             "큐대기", "시장가")
    for arm in fp.arms:
        r = fp.arm_summary(arm)
        log.info("  %-9s %-6s %7d %7d %7.1f%% %+9s %+9s %8s %6s%%",
                 r["arm"], "롱" if r["side"] == "long" else "숏",
                 r["armed"], r["filled"], r["fill_rate"] * 100,
                 r.get("net_bp", "--"), r.get("edge_in_bp", "--"),
                 r.get("queue_wait_med", "--"),
                 f"{r.get('taker_exit_frac', 0) * 100:.0f}")
    if gaps:
        log.warning("  연결 끊김 상세: %s", json.dumps(gaps[:4], ensure_ascii=False))
    fp.persist(T.strftime("%Y-%m-%dT%H:%MZ"), gaps)
    fp.stats["events"] += 1


async def amain(args) -> int:
    syms = [ln.strip().upper() for ln in Path(args.symbols).read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    if not syms:
        log.error("종목 없음")
        return 1
    arms = [Arm(t, e, x, sd, fr, note) for t, e, x, sd, fr, note in ARMS_DEFAULT]
    fp = FundingPaper(syms, args.notional, Path(args.out_dir), arms)
    log.info("단타 페이퍼 [펀딩 정산] — %d종목 | 주문 $%.0f | 팔 %d개",
             len(syms), args.notional, len(arms))
    for a in arms:
        log.info("  %-9s %-4s T%+d → T%+d (보유 %d분)%s  — %s", a.tag,
                 "롱" if a.side == "long" else "숏", a.entry_min, a.exit_min,
                 a.exit_min - a.entry_min,
                 f" 펀딩>={a.min_fr:.0f}bp" if a.min_fr > 0 else "", a.note)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sg in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sg, stop.set)

    last_T = None
    while not stop.is_set():
        T = await next_funding_time()
        if last_T is not None and T <= last_T:
            await asyncio.sleep(60)
            continue
        wake = T + timedelta(minutes=min(a.entry_min for a in fp.arms) - 5)
        wait = (wake - datetime.now(timezone.utc)).total_seconds()
        if wait > 0:
            log.info("다음 사건 %s UTC — %.1f분 대기 (구독 없음)",
                     T.strftime("%m-%d %H:%M"), wait / 60)
            try:
                await asyncio.wait_for(stop.wait(), timeout=wait)
                break
            except asyncio.TimeoutError:
                pass
        await event_cycle(fp, T, stop)
        last_T = T
    log.info("종료 — 사건 %d회", fp.stats["events"])
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
