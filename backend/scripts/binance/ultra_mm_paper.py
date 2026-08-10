"""2군 페이퍼 마켓메이킹 — WS 실시간 피드 위에서 큐 위치까지 모사한다.

왜 이게 필요한가 (2026-08-09, 대표님 지시 "ws 자료가 모일 때까지 기다릴 수 없다"):
  체결 데이터(aggTrades)로 잰 메이킹 손익은 **상한**이다. "항상 최우선 호가에 있고
  흐름에 비례해 체결된다"고 가정하기 때문이다. 실제 메이킹의 성패는 **큐 위치**가
  가른다 — 내 앞에 $260k 가 쌓여 있으면 그 물량이 다 소진돼야 내 차례다.
  그 질문은 백테스트로 답이 안 나오고, 호가·체결 스트림을 동시에 받아 모사해야
  답이 나온다. 수집만 하며 기다릴 이유가 없다 — 모사가 곧 수집이다.

무엇을 모사하는가
  · `@bookTicker` 최우선 호가·잔량 → 내 주문의 **큐 앞 물량**
  · `@trade`      체결 하나하나 → 그 물량이 **얼마나 소진됐는지**

  ※ `@aggTrade` 를 쓰지 않는다. fstream.binance.com/ws 에서 구독은 수락(result:null)
    되는데 **데이터가 오지 않는다**(2026-08-09 실측: 40초간 0건, 같은 창에서
    `@trade` 는 343건). 개별 체결이라 큐 모사에는 오히려 더 정밀하다.
  체결 조건: 내 가격에서 반대편 테이커 체결이 누적으로 큐 앞 물량을 넘어설 때.
  이게 실제 체결 규칙(가격-시간 우선)과 같은 구조다.

정직하게 남기는 낙관 요소
  1. 취소·재게시 지연 0 (실제로는 왕복 수십 ms, 그 사이 당한다)
  2. 내 주문이 시장에 주는 영향 없음 (소액이면 타당)
  3. 부분체결을 전량체결로 근사
  → 그래도 큐를 무시한 상한보다는 훨씬 보수적이다.

손익 분해 (bp)
  스프레드 획득 : 체결가 − 체결 시점 중간가
  역선택       : 체결 시점 중간가 − Δ분 뒤 중간가 (내 포지션 방향 기준)
  수수료       : 메이커 2bp/체결, 재고 청산 시 테이커 5bp
  재고 청산     : |재고| 가 한도 초과 시 시장가로 평탄화 (실제 운영 제약)
  **펀딩비**    : 정산 시각에 보유 재고 명목 x 펀딩률. 롱이면 rate>0 일 때 지불.

펀딩을 왜 넣는가 (2026-08-09 대표님 지적)
  perp 은 정산 시각마다 **포지션 명목금액** 기준으로 펀딩을 주고받는다. 메이킹은
  평균 재고가 0 에 가까우면 대체로 상쇄되지만, 재고가 한쪽으로 오래 쏠리면 실비용이다.
  크기가 작지도 않다 — 실측 AKEUSDT +6.59bp/8h = **일 환산 +19.77bp** 로, 거래
  손익(-8bp 대)보다 크다. 빼놓으면 양수 후보를 과대평가하게 된다.

  출처는 REST `/fapi/v1/premiumIndex` 다(857종목 1회 호출). WS `@markPrice` 는
  `@kline_1m`·`@aggTrade` 와 마찬가지로 **데이터가 오지 않는다**(2026-08-09 실측).
  정산 주기는 종목마다 다르므로(8h 가 대부분이나 NFPUSDT 는 4h) 고정하지 않고
  응답의 `nextFundingTime` 을 따른다.

출력: runs/ultra_mm_paper/{날짜}/{SYMBOL}.jsonl (체결·상태) + 주기적 요약 로그

사용:
  python3 scripts/binance/ultra_mm_paper.py --symbols configs/ultra_mm_paper_symbols.txt
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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ultra_mm_paper")

WS_BASE = "wss://fstream.binance.com/ws"
MAKER_FEE_BP = 2.0
TAKER_FEE_BP = 5.0
PREMIUM_INDEX = "https://fapi.binance.com/fapi/v1/premiumIndex"
FUNDING_POLL_SEC = 300
# 정산 판정 주기. 폴러(5분)보다 **촘촘해야 한다** — 정산 시각이 지나면 API 가
# nextFundingTime 을 다음 시각으로 바꾸므로, 판정이 그 전에 그 순간을 잡아야 한다.
# 초판은 판정이 10분 주기라 폴러가 먼저 덮어써서 **정산이 영영 0회**였다(2026-08-10 발견).
# 15초면 정산 시각과 재고 측정 시점의 어긋남도 그 안으로 묶인다.
FUNDING_SETTLE_SEC = 15

# ── 가설 5: 물러선 호가 (2026-08-10 신설) ──────────────────────────────
# 가설 1~4 는 전부 **최우선 호가에 선다**는 같은 전제 위에 있었고, "언제 뺄까"만
# 달리했다. 11.67시간 실측의 결론은 그 전제 안에서는 답이 없다는 것이었다 —
# 이론 반스프레드를 **완벽히** 다 받아내도 5종목 전부 적자였다(수수료 2bp 때문).
#
#   AKE +2.80 − 1.22 − 2.00 = −0.42   BANK +1.52 − 0.98 − 2.00 = −1.46
#   SOL +0.68 − 0.76 − 2.00 = −2.08   TST +4.53 − 5.24 − 2.00 = −2.71
#
# 그 계산이 깨지는 유일한 축이 **호가 거리**다. 중간가에서 멀수록 체결당 획득이
# 커진다. SOL 기준 최우선 +0.68bp / 3틱 물러서면 +4.60bp — 수수료를 넘긴다.
# 대가는 빈도다. 3틱을 쓸어야 체결되므로 훨씬 드물다.
#
# ※ 폐기한 가설: "물러서면 큐 앞에 선다". 실측이 반증했다 —
#   SOL 매수 최우선 $86k / 1틱 아래 $200k / 2틱 아래 $254k 로 **깊을수록 더 쌓인다.**
#   따라서 이 가설의 근거는 큐 위치가 아니라 오직 **획득 크기**다.
#
# 큐를 정확히 알아야 하므로 `@depth20@100ms`(20단계 스냅샷, 초당 약 9회)를 쓴다.
# `@bookTicker` 는 1단계뿐이라 물러선 가격의 대기 물량을 모른다.
# 주의: 이 값은 **호가창의 몇 번째 단계**이지 가격 기준 몇 틱이 아니다.
# 최우선 근처는 단계가 촘촘해 둘이 거의 같지만, 깊어질수록 빈 가격대가 생겨
# 어긋난다(7~10단계에서 특히). 단계 기준이 오히려 실전에 맞다 — 주문이 실제로
# 쌓여 있는 가격에 서는 것이고, 비어 있는 가격에 혼자 서면 체결이 안 온다.
DEPTH_TICKS = 3             # 최우선에서 몇 **단계** 물러설까

# ── 가설 6: 호가창 불균형 조건부 (2026-08-10 신설) ──────────────────────
# 타이밍 축(가설 2~4)과 거리 축(가설 5)이 둘 다 닫혔다. 거리 축은 U자가 나왔고
# 최적점(3~5단계)에서도 CYS -7.03 / AKE -5.67bp 로 적자였다 — 물러설수록 획득은
# 커지지만 역선택이 더 빨리 늘었다(5→7단계에서 획득 +1.85 vs 역선택 -9.68).
#
# 아직 안 쓴 데이터가 있다. 가설 5 때문에 호가창 20단계를 받기 시작했는데
# 지금까지 "얼마나 물러설까" 에만 썼다. **쌓여 있는 물량의 좌우 비대칭**은
# 초단기 가격 방향의 강한 예측자다. 매수 쪽이 두꺼우면 가격은 위로 간다.
#
# 메이커에겐 이게 결정적이다:
#   매수 두꺼움 → 상승 압력 → 매수호가에 서면 사고 나서 오른다 (유리)
#                          → 매도호가에 서면 팔고 나서 오른다 (당함)
#
# 가설 2 와 다른 점: 가설 2 는 이미 일어난 **체결 흐름**(60초 과거)을 봤다.
# 가설 6 은 **대기 중인 물량**(현재 상태)을 본다. 후행 대 선행이다.
IMB_LEVELS = 5              # 불균형 계산에 쓸 호가 단계 수
IMB_TH = 0.20               # |불균형| 이 이보다 크면 불리한 쪽을 걷는다

# ── 가설 7: 깊이 + 불균형 결합 (2026-08-10) ────────────────────────────
# 가설 5 와 6 은 **서로 다른 성분**을 공격한다. 결합한 적이 없는 유일한 조합이고,
# 산술상 유일하게 양수로 닫힌다 (CYSUSDT 3.7시간 실측):
#     가설5 깊이5   스프레드 획득 +6.42  역선택 -11.08  → net -6.66
#     가설6 불균형  스프레드 획득 +0.37  역선택  -4.34  → net -5.97
#     결합 (가정)   획득 +6.4 · 역선택 -4.3 · 수수료 -2.0 → **+0.1bp**
#
# 각 성분의 신뢰도가 다르다. **깊이의 획득은 단단하다** — 세 번 측정에
# +6.35/+6.38/+6.42 로 흔들리지 않았다(체결마다 즉시 확정되는 값이라 표본 문제가
# 없다). 불확실한 건 역선택 쪽뿐이다.
#
# 낙관하지는 않는다. 깊이에서 역선택이 나쁜 이유는 **물러선 호가가 "가격이 쓸고
# 갈 때만" 체결되기 때문**이다. 불균형 필터는 방향을 거를 뿐 그 성질을 없애지
# 못할 수 있다. 그러면 역선택이 -11 에서 -8 쯤으로만 줄고 여전히 적자다.
# 어느 쪽이든 **초단타 메이킹의 마지막 축이 닫히거나 열린다.**
MARKOUT_SEC = 300           # 주 역선택 지평 (net 계산에 쓰는 값)
# 역선택이 **얼마나 빨리** 쌓이는지 모르면 "빨리 털면 피할 수 있는가" 에 답할 수
# 없다. 여러 지평에서 같이 재서 곡선을 본다 (2026-08-10 추가).
MARKOUT_HORIZONS = (1, 5, 30, 60, 300)

# ── 가설 2: 흐름 회피형 편향 호가 (2026-08-09 신설) ──────────────────────
# 가설 1(양방향 최우선 고정)의 실측 실패 지점은 **스프레드 획득이 음수**라는 것이다
# (라이브 -0.16 ~ -3.29bp). 최우선에 대고도 체결되는 순간엔 중간가가 이미 내 가격을
# 지나쳐 있다 = 매번 당하는 쪽에 서 있다.
#   그런데 어느 쪽에서 당할지는 미리 보인다. 공격적 매수가 몰리는 국면에선 내
#   **매도호가**가 정보 있는 매수자에게 쓸린다. 그 순간 매도호가를 걷으면 그 손실이
#   사라진다. 방향을 맞히는 게 아니라 **노출을 피하는** 것이다.
#   OFI 는 수익률 예측엔 쓸모없었으나(ultra_signal_scan 283종목 실측) 여기서는
#   예측이 아니라 "지금 어느 쪽이 맞고 있나"를 보는 용도라 성격이 다르다.
FLOW_WIN_SEC = 60.0         # 주문흐름 관측 창
FLOW_SKEW_TH = 0.30         # |OFI| 가 이보다 크면 노출된 쪽을 걷는다

# ── 가설 3: 큐 소진 임박 회피 (2026-08-09 신설) ────────────────────────
# 역선택이 어디서 생기는지는 실측에 이미 나와 있다 — **체결 순간에 이미 밀려 있다**
# (스프레드 획득이 음수). 메커니즘은 큐다. 내 주문은 큐 뒤에 서고, 앞 물량이 다
# 소진돼야 차례가 온다. 그런데 앞이 다 소진된다는 건 한 방향으로 체결이 몰렸다는
# 뜻이고, 곧 가격이 그 방향으로 가고 있다는 뜻이다.
#   **나를 체결시켜 주는 조건이 곧 나를 당하게 하는 조건이다.**
#
# 가설 2 는 60초 평균 흐름을 봤다 — 느린 신호라 개선이 0.6~2.6bp 에 그쳤다.
# 가설 3 은 **그 순간의 큐 소진 속도**를 본다. 빠르게 비면 쓸림, 느리게 비면 정상
# 양방향 거래다. 소진 속도로 도달 시각(ETA)을 추정해 임박하면 호가를 뺀다.
# "내 차례가 임박했다"를 기회가 아니라 **위험 신호로 읽는 것**이다.
#
# 되물을 지점: 늘 도망가면 체결이 0 이 되어 사업이 없다. 그래서 절대 잔량이 아니라
# **속도** 로 판단한다 — 천천히 줄어드는 큐는 그대로 두고 급소진만 피한다.
FLEE_ETA_SEC = 3.0          # 이 시간 안에 내 차례가 올 속도면 뺀다
FLEE_MIN_CONSUMED = 0.20    # 속도 추정이 신뢰될 만큼 소진된 뒤에만 판단

# ── 가설 4: 가설 2 + 가설 3 결합 (2026-08-09) ──────────────────────────
# 둘은 직교한다. 가설 2 는 **어느 쪽**에 설지(방향, 60초 흐름), 가설 3 은
# **언제 뺄지**(타이밍, 그 순간 큐 소진 속도)를 정한다. 서로 다른 실패 모드다.
#
# 1.67시간 실측이 합칠 근거를 준다 — 효과가 나타난 종목이 갈렸다:
#   가설 2 : SOLUSDT (스프레드 좁은 대형) net -2.90 → -1.81
#   가설 3 : BANKUSDT net -5.96 → -2.74 / TSTUSDT -11.88 → +1.85
#   그리고 가설 3 의 스프레드 획득 개선은 4종목 전부에서 나타났다(예외 없음).
#
# 위험: 둘 다 체결을 줄이는 규칙이라 합치면 체결이 거의 사라질 수 있다. 가설 3
# 단독으로도 이미 90~95% 가 줄었다. **"남은 체결로 사업이 되는가"** 가 이 가설의
# 주 검증 지점이고, 체결이 0 에 수렴하면 그 자체가 반증이다.
SUB_BATCH = 50
SUB_INTERVAL = 0.4
STATS_SEC = 600


@dataclass
class Order:
    side: str                # "buy" | "sell"
    price: float
    notional: float
    queue_ahead: float       # 내 앞 물량 + **내 주문 자신**. 0 이하가 되면 전량 체결.
                             # 앞 큐만 비우고 즉시 체결시키면 내 물량을 소진하는
                             # 거래량이 공짜가 된다 — CYSUSDT 가 하루 거래대금의
                             # 1.8배를 한 시간에 체결하는 값이 나왔다 (2026-08-09).
    posted_at: float
    queue0: float = 0.0      # 게시 시점 큐 (소진 속도 계산용, 가설 3)


@dataclass
class SymState:
    symbol: str
    quote_usd: float
    inv_cap_usd: float
    bid: float = 0.0
    ask: float = 0.0
    bid_qty_usd: float = 0.0
    ask_qty_usd: float = 0.0
    book_bids: list = field(default_factory=list)   # [(가격, USD), ...] 가설5
    book_asks: list = field(default_factory=list)
    tick: float = 0.0
    buy_order: Order | None = None
    sell_order: Order | None = None
    inv_usd: float = 0.0            # 양수 = 롱
    inv_cost: float = 0.0           # 재고의 평균 진입가 가중합
    realized_bp: float = 0.0        # 누적 스프레드 획득 (bp·USD)
    fee_usd: float = 0.0
    flat_cost_usd: float = 0.0
    n_fills: int = 0
    n_flat: int = 0
    flow: deque = field(default_factory=deque)   # (ts, +buy_usd, -sell_usd) 최근 흐름
    flow_buy: float = 0.0
    flow_sell: float = 0.0
    funding_rate: float = 0.0
    next_funding_ms: int = 0
    applied_funding_ms: int = 0
    funding_usd: float = 0.0        # 양수 = 지불
    n_funding: int = 0
    n_skip_bid: int = 0
    n_skip_ask: int = 0
    n_flee: int = 0
    pending_markout: deque = field(default_factory=deque)   # (t_due, side, mid_at_fill, notional)
    markout_bp_sum: float = 0.0
    markout_n: int = 0
    mk_sum: dict = field(default_factory=dict)   # 지평별 누적 (bp·USD)
    mk_n: dict = field(default_factory=dict)
    fills_log: list = field(default_factory=list)
    pending_rec: dict = field(default_factory=dict)   # 체결ID → 기록(markout 대기)
    fill_seq: int = 0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0 if (self.bid > 0 and self.ask > 0) else 0.0


class PaperMM:
    def __init__(self, symbols: list[str], quote_usd: float, inv_cap_usd: float,
                 out_dir: Path, strategy: str = "touch"):
        self.st = {s: SymState(s, quote_usd, inv_cap_usd) for s in symbols}
        self.out_dir = out_dir
        self.strategy = strategy          # "touch" = 가설1 / "flow_skew" = 가설2
        self.t0 = time.time()

    def book_imbalance(self, s: SymState) -> float:
        """호가창 상위 IMB_LEVELS 단계의 좌우 비대칭. +1=매수 일방, -1=매도 일방.
        가설 2 의 체결흐름(후행)과 달리 **대기 물량**(현재 상태)을 본다."""
        if not s.book_bids or not s.book_asks:
            return 0.0
        b = sum(u for _, u in s.book_bids[:IMB_LEVELS])
        a = sum(u for _, u in s.book_asks[:IMB_LEVELS])
        return (b - a) / (b + a) if (b + a) > 0 else 0.0

    def _sides_allowed(self, s: SymState) -> tuple:
        """(매수호가를 댈까, 매도호가를 댈까). 가설 1 은 항상 양방향."""
        if self.strategy in ("book_imb", "depth_imb"):
            imb = self.book_imbalance(s)
            if imb > IMB_TH:      # 매수 두꺼움 → 상승 압력 → 매도호가가 당한다
                return True, False
            if imb < -IMB_TH:     # 매도 두꺼움 → 하락 압력 → 매수호가가 당한다
                return False, True
            return True, True
        if self.strategy not in ("flow_skew", "combo"):
            return True, True
        tot = s.flow_buy + s.flow_sell
        if tot <= 0:
            return True, True
        ofi = (s.flow_buy - s.flow_sell) / tot
        if ofi > FLOW_SKEW_TH:            # 공격적 매수 우위 → 내 매도호가가 쓸린다
            return True, False
        if ofi < -FLOW_SKEW_TH:           # 공격적 매도 우위 → 내 매수호가가 쓸린다
            return False, True
        return True, True

    # ── 호가 갱신 ──────────────────────────────────────────────
    def on_book(self, sym: str, bid: float, ask: float, bq: float, aq: float) -> None:
        s = self.st.get(sym)
        if s is None or not (bid > 0 and ask > bid):
            return
        s.bid, s.ask = bid, ask
        s.bid_qty_usd, s.ask_qty_usd = bq * bid, aq * ask

        # **호가 이동만으로는 체결시키지 않는다.**
        # 체결은 내 가격에서 실제 거래가 일어나 큐를 소진해야 성립한다(가격-시간 우선).
        # 초판에서 "최우선가가 내려가면 쓸고 간 것"으로 보고 체결시켰더니 CYSUSDT 가
        # 시간당 $3.5M 체결 = 그 종목 하루 거래대금의 28배라는 불가능한 값이 나왔다.
        # 호가 갱신은 취소/재게시로도 일어나므로 거래의 증거가 아니다.
        # 거래 기반 체결은 on_trade 가 전담한다.
        #
        # 시장이 **나에게서 멀어지면**(매수호가가 내 가격 위로) 더는 최우선이 아니므로
        # 취소하고 새 최우선에 다시 선다 — 큐는 처음부터다.
        if self.strategy in ("depth", "depth_imb"):
            # 물러선 호가는 중간가를 따라 움직여야 한다 — 목표 가격이 바뀌면 재게시.
            tb, _ = self._depth_target(s, "buy")
            ta, _ = self._depth_target(s, "sell")
            if s.buy_order and tb > 0 and s.buy_order.price != tb:
                s.buy_order = None
            if s.sell_order and ta > 0 and s.sell_order.price != ta:
                s.sell_order = None
        else:
            if s.buy_order and bid > s.buy_order.price:
                s.buy_order = None
            if s.sell_order and ask < s.sell_order.price:
                s.sell_order = None
        self._repost(s)

    def _depth_target(self, s: SymState, side: str) -> tuple:
        """가설 5 — 최우선에서 DEPTH_TICKS 만큼 물러선 가격과 그 단계의 대기 물량.
        호가창 스냅샷에서 직접 읽는다. 해당 단계가 없으면 (0,0) 을 돌려 게시하지 않는다."""
        book = s.book_bids if side == "buy" else s.book_asks
        if len(book) <= DEPTH_TICKS or s.tick <= 0:
            return 0.0, 0.0
        px, usd = book[DEPTH_TICKS]
        return px, usd

    def _repost(self, s: SymState) -> None:
        """호가를 댄다. 재고 한도에 걸린 쪽은 대지 않는다."""
        if s.bid <= 0 or s.ask <= 0:
            return
        if self.strategy in ("depth", "depth_imb"):
            ok_bid, ok_ask = self._sides_allowed(s)
            # 불균형이 불리하다고 한 쪽은 걷는다 (가설 7)
            if not ok_bid and s.buy_order is not None:
                s.buy_order = None
                s.n_skip_bid += 1
            if not ok_ask and s.sell_order is not None:
                s.sell_order = None
                s.n_skip_ask += 1
            if ok_bid and s.buy_order is None and s.inv_usd < s.inv_cap_usd:
                px, q = self._depth_target(s, "buy")
                if px > 0:
                    s.buy_order = Order("buy", px, s.quote_usd, q + s.quote_usd,
                                        time.time(), q + s.quote_usd)
            if ok_ask and s.sell_order is None and s.inv_usd > -s.inv_cap_usd:
                px, q = self._depth_target(s, "sell")
                if px > 0:
                    s.sell_order = Order("sell", px, s.quote_usd, q + s.quote_usd,
                                         time.time(), q + s.quote_usd)
            return
        ok_bid, ok_ask = self._sides_allowed(s)
        if not ok_bid and s.buy_order is not None:
            s.buy_order = None
            s.n_skip_bid += 1
        if not ok_ask and s.sell_order is not None:
            s.sell_order = None
            s.n_skip_ask += 1
        if ok_bid and s.buy_order is None and s.inv_usd < s.inv_cap_usd:
            q = s.bid_qty_usd + s.quote_usd
            s.buy_order = Order("buy", s.bid, s.quote_usd, q, time.time(), q)
        if ok_ask and s.sell_order is None and s.inv_usd > -s.inv_cap_usd:
            q = s.ask_qty_usd + s.quote_usd
            s.sell_order = Order("sell", s.ask, s.quote_usd, q, time.time(), q)

    def on_depth(self, sym: str, bids: list, asks: list) -> None:
        """20단계 스냅샷 (가설 5). 최우선도 여기서 갱신하므로 bookTicker 없이 돈다."""
        s = self.st.get(sym)
        if s is None or not bids or not asks:
            return
        try:
            bb = [(float(p), float(p) * float(q)) for p, q in bids if float(q) > 0]
            aa = [(float(p), float(p) * float(q)) for p, q in asks if float(q) > 0]
        except (TypeError, ValueError):
            return
        if not bb or not aa:
            return
        s.book_bids, s.book_asks = bb, aa
        if s.tick <= 0 and len(bb) > 1:
            s.tick = round(abs(bb[0][0] - bb[1][0]), 12)
        self.on_book(sym, bb[0][0], aa[0][0],
                     bb[0][1] / bb[0][0], aa[0][1] / aa[0][0])

    # ── 체결 스트림 ────────────────────────────────────────────
    def on_trade(self, sym: str, price: float, qty: float, buyer_maker: bool) -> None:
        """buyer_maker=True → 테이커 **매도** (내 매수호가를 소진)."""
        s = self.st.get(sym)
        if s is None:
            return
        notional = price * qty
        # 흐름 창 갱신 (가설 2 의 입력). 가설 1 에서도 계산은 하되 쓰지 않는다.
        now = time.time()
        if buyer_maker:
            s.flow.append((now, 0.0, notional)); s.flow_sell += notional
        else:
            s.flow.append((now, notional, 0.0)); s.flow_buy += notional
        cut = now - FLOW_WIN_SEC
        while s.flow and s.flow[0][0] < cut:
            _, b, sl = s.flow.popleft()
            s.flow_buy -= b; s.flow_sell -= sl
        if buyer_maker:                      # 테이커 매도 → 매수 큐 소진
            o = s.buy_order
            if o and price <= o.price:
                o.queue_ahead -= notional
                if o.queue_ahead > 0 and self._should_flee(o):
                    s.buy_order = None        # 급소진 감지 → 체결 전에 뺀다
                    s.n_flee += 1
                elif o.queue_ahead <= 0:
                    self._fill(s, o, adverse=False)
                    s.buy_order = None
        else:                                # 테이커 매수 → 매도 큐 소진
            o = s.sell_order
            if o and price >= o.price:
                o.queue_ahead -= notional
                if o.queue_ahead > 0 and self._should_flee(o):
                    s.sell_order = None
                    s.n_flee += 1
                elif o.queue_ahead <= 0:
                    self._fill(s, o, adverse=False)
                    s.sell_order = None
        self._settle_markouts(s)

    def _should_flee(self, o: Order) -> bool:
        """큐가 급소진 중이면 체결 직전에 뺀다 (가설 3). 상세는 상단 상수 주석."""
        if self.strategy not in ("queue_flee", "combo") or o.queue0 <= 0:
            return False
        consumed = o.queue0 - o.queue_ahead
        if consumed / o.queue0 < FLEE_MIN_CONSUMED:
            return False                      # 속도 추정이 아직 못 미덥다
        elapsed = max(time.time() - o.posted_at, 1e-3)
        rate = consumed / elapsed             # USD/초
        if rate <= 0:
            return False
        return (o.queue_ahead / rate) < FLEE_ETA_SEC

    def _fill(self, s: SymState, o: Order, adverse: bool = False) -> None:
        mid = s.mid or o.price
        sign = 1.0 if o.side == "buy" else -1.0
        # 스프레드 획득: 매수는 중간가보다 싸게, 매도는 비싸게 산 만큼
        edge_bp = (mid - o.price) / mid * 1e4 * sign
        s.realized_bp += edge_bp * o.notional
        s.fee_usd += o.notional * MAKER_FEE_BP / 1e4
        s.inv_usd += sign * o.notional
        s.inv_cost += sign * o.notional * o.price
        s.n_fills += 1
        now = time.time()
        # 기록은 **markout 이 확정될 때까지 미룬다.** 초판은 체결 시점에 써버려서
        # 역선택이 기록에 안 남았고, 그 때문에 net 의 신뢰구간을 계산할 수 없었다
        # (2026-08-10: 획득 표준오차는 0.01bp 로 쟀는데 역선택 쪽은 못 쟀다).
        # 지평별 markout 을 다 채운 뒤에 한 줄로 내린다.
        s.fill_seq += 1
        rid = s.fill_seq
        s.pending_rec[rid] = {
            "t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "side": o.side, "price": o.price, "mid": mid,
            "edge_bp": round(edge_bp, 4), "notional": o.notional,
            "adverse_sweep": adverse, "inv_usd": round(s.inv_usd, 1),
            "queue_wait_sec": round(time.time() - o.posted_at, 2),
            "markout": {},
        }
        for h in MARKOUT_HORIZONS:
            s.pending_markout.append((now + h, o.side, mid, o.notional, h, rid))
        self._enforce_inventory(s)

    def _enforce_inventory(self, s: SymState) -> None:
        """재고 한도 초과분은 시장가로 턴다 — 실제 운영 제약이자 비용이다."""
        if abs(s.inv_usd) <= s.inv_cap_usd or s.mid <= 0:
            return
        excess = abs(s.inv_usd) - s.inv_cap_usd
        # 시장가는 스프레드 절반 + 테이커 수수료를 낸다
        half_spread_bp = (s.ask - s.bid) / 2 / s.mid * 1e4
        cost = excess * (half_spread_bp + TAKER_FEE_BP) / 1e4
        s.flat_cost_usd += cost
        s.inv_usd -= (1 if s.inv_usd > 0 else -1) * excess
        s.n_flat += 1

    def settle_funding(self) -> int:
        """정산 시각을 지난 종목에 보유 재고 기준 펀딩을 적용한다.
        rate>0 이면 롱이 지불하므로 cost = 재고 x rate 로 부호가 자연히 맞는다."""
        now_ms = int(time.time() * 1000)
        n = 0
        for s in self.st.values():
            if (s.next_funding_ms and now_ms >= s.next_funding_ms
                    and s.next_funding_ms > s.applied_funding_ms):
                cost = s.inv_usd * s.funding_rate
                s.funding_usd += cost
                s.applied_funding_ms = s.next_funding_ms
                s.n_funding += 1
                n += 1
                if abs(cost) > 0.001:
                    log.info("  [펀딩] %s 재고 $%.0f x %+.4f%% → %+.4f USD",
                             s.symbol, s.inv_usd, s.funding_rate * 100, -cost)
        return n

    def _settle_markouts(self, s: SymState) -> None:
        now = time.time()
        while s.pending_markout and s.pending_markout[0][0] <= now:
            _, side, mid_at, notional, h, rid = s.pending_markout.popleft()
            if s.mid <= 0 or mid_at <= 0:
                s.pending_rec.pop(rid, None) if h == MARKOUT_SEC else None
                continue
            sign = 1.0 if side == "buy" else -1.0
            bp = (s.mid - mid_at) / mid_at * 1e4 * sign
            v = bp * notional
            s.mk_sum[h] = s.mk_sum.get(h, 0.0) + v
            s.mk_n[h] = s.mk_n.get(h, 0) + 1
            rec = s.pending_rec.get(rid)
            if rec is not None:
                rec["markout"][h] = round(bp, 4)
            if h == MARKOUT_SEC:            # net 계산은 주 지평만 쓴다
                s.markout_bp_sum += v
                s.markout_n += 1
                if rec is not None:
                    # 이제 체결당 net 이 완성된다 — 이게 신뢰구간의 재료다
                    rec["net_bp"] = round(rec["edge_bp"] + bp - MAKER_FEE_BP, 4)
                    s.fills_log.append(rec)
                    s.pending_rec.pop(rid, None)

    # ── 보고 ──────────────────────────────────────────────────
    def summary(self) -> list[dict]:
        out = []
        for s in self.st.values():
            vol = s.n_fills * s.quote_usd
            if vol <= 0:
                out.append({"symbol": s.symbol, "fills": 0})
                continue
            spread_bp = s.realized_bp / vol
            mk_vol = s.markout_n * s.quote_usd
            adverse_bp = (s.markout_bp_sum / mk_vol) if mk_vol > 0 else float("nan")
            fee_bp = s.fee_usd / vol * 1e4
            flat_bp = s.flat_cost_usd / vol * 1e4
            fund_bp = s.funding_usd / vol * 1e4
            # markout 은 체결 후 5분이 지나야 확정된다. 미확정을 0 으로 취급하면
            # net 이 실제보다 좋아 보인다 — 미정이면 net 도 미정으로 둔다.
            has_mk = adverse_bp == adverse_bp
            net = (spread_bp + adverse_bp - fee_bp - flat_bp - fund_bp) if has_mk else float("nan")
            out.append({
                "symbol": s.symbol, "fills": s.n_fills,
                "spread_bp": round(spread_bp, 3),
                "markout_bp": round(adverse_bp, 3) if adverse_bp == adverse_bp else None,
                "fee_bp": round(fee_bp, 3), "flatten_bp": round(flat_bp, 3),
                "markout_curve": {h: (round(s.mk_sum[h] / (s.mk_n[h] * s.quote_usd), 2)
                                      if s.mk_n.get(h) else None)
                                  for h in MARKOUT_HORIZONS},
                "funding_bp": round(fund_bp, 3), "n_funding": s.n_funding,
                "funding_rate_bp": round(s.funding_rate * 1e4, 3),
                "net_bp": round(net, 3) if net == net else None,
                "markout_settled": s.markout_n,
                "inv_usd": round(s.inv_usd, 1), "n_flat": s.n_flat,
                "skip_bid": s.n_skip_bid, "skip_ask": s.n_skip_ask, "flee": s.n_flee,
                "fills_per_hour": round(s.n_fills / max((time.time() - self.t0) / 3600, 1e-6), 1),
            })
        return out

    def persist(self) -> None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        d = self.out_dir / day
        d.mkdir(parents=True, exist_ok=True)
        for s in self.st.values():
            if not s.fills_log:
                continue
            with open(d / f"{s.symbol}.jsonl", "a") as fh:
                for r in s.fills_log:
                    fh.write(json.dumps(r) + "\n")
            s.fills_log.clear()
        with open(d / "_summary.jsonl", "a") as fh:
            fh.write(json.dumps({
                "t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "uptime_h": round((time.time() - self.t0) / 3600, 3),
                "rows": self.summary()}) + "\n")


async def funding_poller(mm: PaperMM, stop: asyncio.Event) -> None:
    """펀딩률·다음 정산시각을 주기적으로 갱신한다. 857종목이 1회 호출로 온다.
    WS `@markPrice` 는 데이터가 오지 않아 REST 를 쓴다 (모듈 docstring 참조)."""
    import aiohttp
    first = True
    while not stop.is_set():
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(PREMIUM_INDEX,
                                    timeout=aiohttp.ClientTimeout(total=45)) as r:
                    data = await r.json()
            # 갱신 **전에** 먼저 정산한다. 여기서 next 를 덮어쓰면 지나간 정산 시각을
            # 잃어버린다 — 초판 버그의 직접 원인이다.
            mm.settle_funding()
            got = 0
            for x in data:
                st = mm.st.get(x.get("symbol"))
                if st is None:
                    continue
                st.funding_rate = float(x.get("lastFundingRate") or 0.0)
                nxt = int(x.get("nextFundingTime") or 0)
                if nxt and st.applied_funding_ms == 0:
                    st.applied_funding_ms = nxt - 1   # 기동 직후 과거분 소급 금지
                st.next_funding_ms = nxt
                got += 1
            if first:
                log.info("펀딩률 수신 %d/%d종목 — 예: %s", got, len(mm.st),
                         ", ".join(f"{k} {v.funding_rate*1e4:+.2f}bp"
                                   for k, v in list(mm.st.items())[:3]))
                first = False
        except Exception as e:
            log.warning("펀딩률 폴링 실패: %s", e)
        for _ in range(FUNDING_POLL_SEC):
            if stop.is_set():
                return
            await asyncio.sleep(1)


async def run(mm: PaperMM, symbols: list[str], stop: asyncio.Event) -> None:
    import websockets
    if mm.strategy in ("depth", "book_imb", "depth_imb"):
        # 물러선 가격의 대기 물량을 알아야 하므로 20단계 스냅샷을 받는다.
        streams = [f"{s.lower()}@depth20@100ms" for s in symbols] + \
                  [f"{s.lower()}@trade" for s in symbols]
    else:
        streams = [f"{s.lower()}@bookTicker" for s in symbols] + \
                  [f"{s.lower()}@trade" for s in symbols]
    delay = 1.0
    while not stop.is_set():
        opened = time.time()
        try:
            async with websockets.connect(WS_BASE, ping_interval=180,
                                          ping_timeout=600, max_size=2 ** 22) as ws:
                for i in range(0, len(streams), SUB_BATCH):
                    await ws.send(json.dumps({"method": "SUBSCRIBE",
                                              "params": streams[i:i + SUB_BATCH],
                                              "id": i + 1}))
                    await asyncio.sleep(SUB_INTERVAL)
                log.info("연결 — %d종목 / 스트림 %d개", len(symbols), len(streams))
                delay = 1.0
                while not stop.is_set():
                    d = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
                    e = d.get("e")
                    if e == "depthUpdate":
                        mm.on_depth(d["s"], d.get("b") or [], d.get("a") or [])
                    elif e == "bookTicker":
                        mm.on_book(d["s"], float(d["b"]), float(d["a"]),
                                   float(d["B"]), float(d["A"]))
                    elif e == "trade":
                        mm.on_trade(d["s"], float(d["p"]), float(d["q"]), bool(d["m"]))
        except asyncio.CancelledError:
            return
        except Exception as ex:
            if stop.is_set():
                return
            up = time.time() - opened
            (log.info if up > 23 * 3600 else log.warning)(
                "연결 종료 (%.1f시간) — %s. %.0f초 후 재연결", up / 3600, ex, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 120)


async def amain(args) -> int:
    syms = [ln.strip().upper() for ln in Path(args.symbols).read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    if not syms:
        log.error("종목 없음")
        return 1
    global DEPTH_TICKS
    DEPTH_TICKS = args.depth_ticks
    mm = PaperMM(syms, args.quote_usd, args.inv_cap_usd, Path(args.out_dir),
                 strategy=args.strategy)
    log.info("페이퍼 MM 시작 [%s] — %d종목 | 호가 $%.0f | 재고한도 $%.0f | 메이커 %.1fbp%s",
             args.strategy, len(syms), args.quote_usd, args.inv_cap_usd, MAKER_FEE_BP,
             (f" | 흐름창 {FLOW_WIN_SEC:.0f}초 임계 {FLOW_SKEW_TH}" if args.strategy == "flow_skew"
              else f" | 회피 ETA {FLEE_ETA_SEC:.0f}초, 최소소진 {FLEE_MIN_CONSUMED:.0%}"
              if args.strategy == "queue_flee"
              else f" | 흐름 {FLOW_WIN_SEC:.0f}초/{FLOW_SKEW_TH} + 회피 ETA {FLEE_ETA_SEC:.0f}초"
              if args.strategy == "combo"
              else f" | 최우선에서 {DEPTH_TICKS}단계 물러섬"
              if args.strategy == "depth"
              else f" | 호가 {IMB_LEVELS}단계 불균형 임계 {IMB_TH}"
              if args.strategy == "book_imb"
              else f" | {DEPTH_TICKS}단계 물러섬 + 불균형 임계 {IMB_TH}"
              if args.strategy == "depth_imb" else ""))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sg in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sg, stop.set)

    task = asyncio.create_task(run(mm, syms, stop))

    async def reporter():
        while not stop.is_set():
            await asyncio.sleep(args.stats_sec)
            mm.settle_funding()
            mm.persist()
            rows = [r for r in mm.summary() if r.get("fills", 0) > 0]
            if not rows:
                log.info("아직 체결 없음 (가동 %.2f시간)", (time.time() - mm.t0) / 3600)
                continue
            log.info("── 가동 %.2f시간 ──", (time.time() - mm.t0) / 3600)
            for r in sorted(rows, key=lambda x: -(x["net_bp"] if x["net_bp"] is not None else -99)):
                mk = "  미정" if r["markout_bp"] is None else f"{r['markout_bp']:+6.2f}"
                nt = "  미정" if r["net_bp"] is None else f"{r['net_bp']:+6.2f}"
                log.info("  %-13s 체결 %4d(%.1f/h) 스프 %+6.2f 역선택 %s(%d건) "
                         "수수료 %.2f 청산 %.2f 펀딩 %+.2f(%d회,%+.2fbp) → net %sbp (재고 $%.0f)",
                         r["symbol"], r["fills"], r["fills_per_hour"], r["spread_bp"],
                         mk, r["markout_settled"], r["fee_bp"], r["flatten_bp"],
                         r["funding_bp"], r["n_funding"], r["funding_rate_bp"],
                         nt, r["inv_usd"])
                cv = r.get("markout_curve") or {}
                if any(v is not None for v in cv.values()):
                    log.info("      역선택 곡선  " + "  ".join(
                        f"{h}s {cv[h]:+.2f}" if cv.get(h) is not None else f"{h}s --"
                        for h in MARKOUT_HORIZONS))
    async def settler():
        """정산 시각 감시. 폴러보다 촘촘해야 한다 (FUNDING_SETTLE_SEC 주석 참조)."""
        while not stop.is_set():
            await asyncio.sleep(FUNDING_SETTLE_SEC)
            try:
                mm.settle_funding()
            except Exception as e:
                log.warning("펀딩 정산 실패: %s", e)

    rep = asyncio.create_task(reporter())
    fund = asyncio.create_task(funding_poller(mm, stop))
    setl = asyncio.create_task(settler())

    await stop.wait()
    for t in (task, rep, fund, setl):
        t.cancel()
    mm.persist()
    log.info("종료 — 최종 요약")
    for r in mm.summary():
        log.info("  %s", json.dumps(r, ensure_ascii=False))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="2군 페이퍼 마켓메이킹 (WS, 큐 모사)")
    p.add_argument("--symbols", default=str(ROOT / "configs" / "ultra_mm_paper_symbols.txt"))
    p.add_argument("--quote-usd", type=float, default=200.0, help="한쪽 호가 명목금액")
    p.add_argument("--inv-cap-usd", type=float, default=1000.0, help="종목별 재고 한도")
    p.add_argument("--out-dir", default=str(ROOT / "runs" / "ultra_mm_paper"))
    p.add_argument("--strategy",
                   choices=["touch", "flow_skew", "queue_flee", "combo", "depth",
                            "book_imb", "depth_imb"],
                   default="touch",
                   help="touch=가설1 / flow_skew=가설2 / queue_flee=가설3 / "
                        "combo=가설4(2+3) / depth=가설5 물러선 호가 / "
                        "book_imb=가설6 호가창 불균형 조건부 / "
                        "depth_imb=가설7 깊이+불균형 결합")
    p.add_argument("--depth-ticks", type=int, default=DEPTH_TICKS,
                   help="가설5 — 최우선에서 몇 틱 물러설까")
    p.add_argument("--stats-sec", type=int, default=STATS_SEC, help="요약 보고 주기(초)")
    args = p.parse_args()
    try:
        return asyncio.run(amain(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
