"""RSI 극단 되돌림 — **전진 페이퍼** (System-2 forward-sim).

무엇을 검증하려고 도는가 (2026-08-17 착수)
    백테스트에서 통과한 것과 못 한 것이 갈렸다:

      통과 — 회전 위약(포트폴리오 47/48) · 상위거래 절삭(23/24) ·
             종목집중도(상위3 = 11%) · 문턱 고원(12·15·18 단조) ·
             표본밖 기간(상관 +0.839) · 포트폴리오 수준(교훈 #81 회피)
      미증명 — **배분 규칙(슬롯·선택)의 우위.** 전진 검정 p 0.120.

    미증명의 원인은 표본이다. 5.6년에 625건 · 연 단위 5개 관측이라 백테스트를
    더 해도 p 0.05 에 못 간다. **표본을 늘리는 길은 앞으로 쌓는 것뿐이다.**

전략 (백테스트 최선 조합 그대로)
    진입 : RSI(14) <= 12 → 롱. 마감 봉으로 판단하고 **결정 즉시 현재가** 체결
    청산 : 익절 +8% / 손절 -3% / 보유 48봉 만료 중 먼저 오는 것
    배분 : 슬롯 3~5. 경쟁 신호 중 **무작위** 선택
           ⚠ rv_high·rsi_low 선택 규칙은 **넣지 않는다.** 증명 안 됐고,
             넣었다가 안 되면 신호 탓인지 규칙 탓인지 못 가른다.

⚠ 체결 안 된 신호도 **전부 기록한다**
    슬롯이 없어 못 잡은 신호까지 남겨야, 나중에 어떤 선택 규칙이 나았는지를
    **재실행 없이** 판정할 수 있다. 조용히 버리면 그 질문이 영영 닫힌다.

⚠ 체결 시점 — 백테스트와 **일부러 다르게** 둔다 (2026-08-19 수정)
    정본은 신호 봉이 닫히는 순간의 시가에 들어간다. 봉 N 종가 시각 = 봉 N+1
    시가 시각이라 실질 즉시 체결이고, 백테스트에선 옳다.

    페이퍼는 그 순간에 결정을 못 한다. 봉 마감 +40초에 깨어나 379종목을
    훑는 데 50초가 넘는다(실측 사이클 51s). 그런데 예전 구현은 다음 사이클에
    **그 지나간 시가로** 채웠다 — 못 잡는 가격에 샀다고 기록한 것이다.

    이제 결정 직후의 **현재가**로 채우고, 정본 값과의 차이를 slip_bp 로
    남긴다. 백테스트 대비 성적 차이 중 얼마가 지연 탓인지 분리해 읽을 수 있다.

⚠ 이것은 System-2 forward-sim 이다 — 실계좌가 아니다
    수수료·호가 스프레드는 여전히 0 이다. System-1(실계좌 paper)과 섞어 읽지
    마라. slip_bp 는 **지연**만 재지 스프레드·수수료는 안 잰다.

⚠ 봉 마감 후에만 판단한다
    진행 중인 봉의 고가·저가는 확정값이 아니다. 마감된 봉만 쓴다.

사용:
  python3 scripts/binance/rsi_extreme_paper.py --selftest
  python3 scripts/binance/rsi_extreme_paper.py --slots 5
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import logging
import math
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ⚠ parents[2] 는 저장소 루트가 아니라 **backend** 다
#   (backend/scripts/binance/x.py → [0]binance [1]scripts [2]backend).
#   다른 research 스크립트와 같은 규약이므로 여기 맞춘다.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rsi_paper")

from app.composer_framework.kernel import (FEE_MAKER_BINANCE_FUTURES,
                                           FEE_TAKER_BINANCE_FUTURES,
                                           KernelConfig, KernelState,
                                           _forced_exit)
from app.composer_framework.kernel import close as kernel_close
from app.composer_framework.kernel import open_position as kernel_open
from app.composer_framework.policy import Action
from app.composer_framework.rules import MarketOpenFill, NotionalSizing

# ⚠ 손익 회계는 **정본 커널**이 한다 — 여기서 다시 구현하지 않는다.
#   이 저장소는 손익 구현체가 6개까지 늘었고 그중 4개가 오염됐다. 2026-08-14
#   에 커널로 통합했고 그 뒤로 "커널 1곳"이 원칙이다. 그런데 이 스크립트는
#   2026-08-19 까지 자체 계산을 썼고, 그 결과 **수수료가 0이었다**.
#
#   정본은 종목 하나 단위(orchestrator: "on one symbol")라 377종목 스캔과
#   슬롯 배분 계층이 없다. 그 계층만 여기서 맡고, 포지션 회계는 커널에 준다:
#       탐지(손절 우선) = _forced_exit   회계 = open_position / close
#   체결 **가격**만 우리가 정한다(실측한 현재가). 커널은 받은 값으로 계산만 한다.
KCFG = KernelConfig(size_pct=1.0,
                    fee_rate=FEE_TAKER_BINANCE_FUTURES,      # 5bp 편도
                    fee_rate_maker=FEE_MAKER_BINANCE_FUTURES)  # 2bp 편도

REST = "https://fapi.binance.com/fapi/v1/klines"
REST_TICKER = "https://fapi.binance.com/fapi/v1/ticker/price"
TF_MS = {"1h": 3_600_000, "30m": 1_800_000, "15m": 900_000,
         "5m": 300_000, "1m": 60_000}
UNIVERSE = ROOT / "configs" / "rsi_paper_universe.txt"
OUT_DIR = ROOT / "runs" / "paper_sessions" / "rsi_extreme"


# ══════════════════════════════════════════════════════════════════════
#  설정은 한 곳에만
# ══════════════════════════════════════════════════════════════════════
@dataclass
class SourceSpec:
    """한 시간대의 진입·청산 규약.

    결합 세션은 이걸 여러 개 들고 **슬롯 하나를 공유**한다. 측정상 1시간+15분
    공유풀이 독립 2세션보다 같은 총자본에서 +5.25%p 낫다 — 신호가 뭉쳐 오는데
    한쪽 풀이 비어 있어도 못 쓰기 때문이다."""
    tf: str = "1h"                # 1h | 30m | 15m | 5m
    entry_rsi: float = 12.0       # RSI <= 이 값이면 롱 후보
    tp_pct: float = 0.08
    sl_pct: float = 0.03
    max_hold_bars: int = 48       # **자기 시간대의** 봉 수. 48h 면 1h=48/15m=192
    rsi_period: int = 14
    warmup_bars: int = 200        # RSI 안정화
    # ⚠ 죽은 종목 게이트 (2026-08-19 HFTUSDT 사고)
    #   거래가 멈춘 종목은 봉이 전부 같은 값이고 거래대금이 0 이다. 그러면
    #   Wilder RSI 가 0/0 에 가까워져 **RSI 0.28** 같은 값이 나오고 문턱을
    #   그냥 통과한다. 실제로 한 주도 안 거래된 종목에서 +7.92% 익절이 났다.
    min_active_bars: int = 10     # RSI 창에서 거래대금>0 인 봉의 최소 개수
    min_distinct_closes: int = 5  # RSI 창의 서로 다른 종가 최소 개수

    def __post_init__(self):
        if self.tf not in TF_MS:
            raise SystemExit(f"tf 는 {list(TF_MS)} — 받은 값 {self.tf!r}")
        if not (0 < self.entry_rsi < 100):
            raise SystemExit(f"entry_rsi 는 (0,100) — {self.entry_rsi}")
        if self.tp_pct <= 0 or self.sl_pct <= 0 or self.max_hold_bars < 1:
            raise SystemExit("익절·손절·보유상한은 양수여야 한다")

    @property
    def key(self) -> str:
        return f"{self.tf}r{self.entry_rsi:g}"


@dataclass
class PaperConfig:
    # 단일 소스 인자 — 기존 세션과의 호환을 위해 남긴다
    rsi_period: int = 14
    entry_rsi: float = 12.0
    tp_pct: float = 0.08
    sl_pct: float = 0.03
    max_hold_bars: int = 48
    tf: str = "1h"
    warmup_bars: int = 200
    # 세션 공용
    slots: int = 5
    notional_usd: float = 200.0  # 슬롯당 명목
    # ⚠ 정본 대비 괴리 상한 (2026-08-19 HFTUSDT 사고)
    #   정상 지연(수십 초)으로는 100bp 를 못 넘는다. 넘으면 시세가 이상한
    #   것이다 — 거래 없는 종목의 마지막 체결가와 현재 호가가 따로 노는 등.
    #   그런 값으로 채우면 익절가가 이미 봉 안에 들어와 다음 사이클에 즉시
    #   "익절"이 나고, 한 주도 안 거래된 종목에서 이익이 생긴다.
    max_slip_bp: float = 100.0
    # ⚠ 봉 마감 후 대기 (2026-08-20 실측으로 40초 → 2초)
    #   40초는 "REST 봉이 확정되길 기다린다"는 근거로 있었는데, 실측하니
    #   마감 후 **0.1~0.3초**에 확정된다. 40초는 통째로 낭비였다.
    #   이 전략의 수익은 진입 봉 안에서 끝난다(익절가 도달까지 중앙 2개
    #   1분봉). 대기 1초가 곧 손실이다.
    bar_wait_s: float = 2.0
    # 시세 조회 병렬도. 순차면 377종목에 43초(실측) — 그동안 급등이 지나간다.
    fetch_workers: int = 16
    seed: int = 20260817         # 무작위 선택의 재현성
    sources: list = field(default_factory=list)   # 비면 위 인자로 1개 구성

    def __post_init__(self):
        if self.slots < 1:
            raise SystemExit("슬롯은 1 이상")
        if not self.sources:
            self.sources = [SourceSpec(
                tf=self.tf, entry_rsi=self.entry_rsi, tp_pct=self.tp_pct,
                sl_pct=self.sl_pct, max_hold_bars=self.max_hold_bars,
                rsi_period=self.rsi_period, warmup_bars=self.warmup_bars)]
        tfs = [x.tf for x in self.sources]
        if len(set(tfs)) != len(tfs):
            raise SystemExit(f"같은 시간대를 두 번 넣을 수 없다 — {tfs}")

    @property
    def base_tf(self) -> str:
        """가장 짧은 시간대 — 사이클 주기를 여기에 맞춘다."""
        return min((x.tf for x in self.sources), key=lambda t: TF_MS[t])

    @property
    def session_name(self) -> str:
        # 단일 소스는 **기존 경로 그대로** 둔다. 바꾸면 가동 중인 세션의
        # 보유 포지션과 누적 표본이 통째로 고아가 된다.
        if len(self.sources) == 1:
            x = self.sources[0]
            return f"{x.tf}_rsi{x.entry_rsi:g}"
        return "combo_" + "_".join(x.key for x in self.sources)


@dataclass
class Position:
    """커널 상태 + 이 계층만 아는 기록.

    앞쪽 필드는 KernelState 를 그대로 담는다 — 직렬화·복원을 위해 펼쳐 둘 뿐,
    회계는 커널이 한다. 여기서 값을 손으로 고치지 말 것."""
    symbol: str
    entry_ts: str
    entry_price: float
    bars_held: int = 0
    tp_price: float = 0.0
    sl_price: float = 0.0
    signal_rsi: float = 0.0
    src: str = ""                # 어느 시간대가 낸 신호인가 (결합 세션용)
    # ── 커널 상태 (KernelState 로 왕복한다)
    cash: float = 0.0
    qty: float = 0.0
    entry_maker: bool = False
    # 지연의 대가 — 정본(신호 봉 종가) 대비 실제 체결가가 얼마나 불리했나.
    # 기본값을 둬야 새 필드가 없는 **기존 상태 파일**도 그대로 복원된다.
    ref_price: float = 0.0       # 정본 체결가 = 신호 봉 종가
    slip_bp: float = 0.0         # 1e4 * (체결가/정본 - 1). 롱이므로 +가 손해
    lag_s: float = 0.0           # 봉 마감 → 체결까지 실제 경과 초

    def to_kernel(self) -> KernelState:
        return KernelState(cash=self.cash, side="long", qty=self.qty,
                           entry_price=self.entry_price, entry_ts=self.entry_ts,
                           bars_held=self.bars_held, sl_price=self.sl_price,
                           tp_price=self.tp_price, entry_maker=self.entry_maker)

    def sync(self, st: KernelState) -> None:
        self.cash, self.qty = st.cash, st.qty
        self.entry_price, self.bars_held = st.entry_price, st.bars_held
        self.sl_price, self.tp_price = st.sl_price, st.tp_price
        self.entry_maker = st.entry_maker


def wilder_rsi(close: pd.Series, period: int) -> pd.Series:
    """정본 소스와 **같은 구현**을 쓴다. 여기서 다르게 계산하면 백테스트와
    비교가 성립하지 않는다."""
    from app.composer_framework.sources.rsi_threshold_source import (
        wilder_rsi as _r)
    return _r(close, period)


def fetch_klines(symbol: str, limit: int = 300,
                 tf: str = "1h") -> pd.DataFrame | None:
    """마감된 봉만. 진행 중인 마지막 봉은 **버린다**."""
    q = urllib.parse.urlencode({"symbol": symbol, "interval": tf,
                                "limit": min(limit, 1500)})
    try:
        with urllib.request.urlopen(f"{REST}?{q}", timeout=20) as r:
            data = json.load(r)
    except Exception as exc:
        log.warning("%s 시세 실패: %s", symbol, exc)
        return None
    if not data:
        return None
    rows = []
    now_ms = int(time.time() * 1000)
    for k in data:
        ot = int(k[0])
        if ot + TF_MS[tf] > now_ms:      # 진행 중인 봉
            continue
        # k[5]=거래량(코인) k[7]=거래대금(USDT). 죽은 종목 판정에 쓴다.
        rows.append((ot, float(k[1]), float(k[2]), float(k[3]), float(k[4]),
                     float(k[7])))
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ot", "open", "high", "low", "close",
                                     "quote_vol"])
    df["ts"] = pd.to_datetime(df.ot, unit="ms", utc=True)
    return df.set_index("ts")


def scan_list(syms: list, dead: set, held) -> list:
    """이번 사이클에 시세를 받을 종목.

    유니버스에서 빠졌거나 시세가 죽은 종목이라도 **보유 중이면 반드시 본다**.
    안 그러면 청산 조건을 영영 못 봐서 슬롯이 묶인 채로 남는다 — 유니버스를
    고칠 때마다 조용히 발생하는 결함이다."""
    out = [s for s in syms if s not in dead or s in held]
    out += [s for s in held if s not in syms]
    return out


def fetch_mark_price(symbol: str) -> float | None:
    """**지금** 잡을 수 있는 값. 지나간 봉 시가가 아니라 현재 체결가다."""
    q = urllib.parse.urlencode({"symbol": symbol})
    try:
        with urllib.request.urlopen(f"{REST_TICKER}?{q}", timeout=10) as r:
            return float(json.load(r)["price"])
    except Exception as exc:
        log.warning("%s 현재가 실패: %s", symbol, exc)
        return None


class RsiPaper:
    def __init__(self, cfg: PaperConfig, symbols: list, out_dir: Path):
        self.cfg = cfg
        self.symbols = symbols
        self.out = out_dir
        self.state_path = out_dir / "state.json"
        self.pos: dict[str, Position] = {}
        self.rng = np.random.default_rng(cfg.seed)
        self.equity = 0.0            # 누적 실현손익 (USD)
        self.n_fill = 0
        self.n_signal = 0
        self.n_skip = 0
        self.n_pricefail = 0
        self.slip_sum = 0.0          # 진입 slip_bp 합 (평균 산출용)
        self.exit_slip_sum = 0.0     # 청산 slip_bp 합 (손절·시간만료만)
        self.n_exit_mkt = 0          # 시장가로 나간 청산 건수
        self.n_dead = 0              # 거래 멈춘 종목이라 거른 신호
        self.n_slipreject = 0        # 괴리 상한 초과로 거부한 체결
        # 자기검사가 시세를 안 건드리고 체결 경로를 확인할 수 있도록 주입 가능
        self.price_fn = fetch_mark_price
        self.spec = {x.tf: x for x in cfg.sources}   # 시간대 → 규약

    # ── 한 사이클: 마감 봉 기준으로 청산 먼저, 그 다음 진입 ──────
    def step(self, bars_by_tf: dict, closed: set | None = None) -> dict:
        """한 사이클.

        `bars_by_tf` = {시간대: {종목: 마감봉 DataFrame}}.
        `closed` = 이번 사이클에 **봉이 마감된** 시간대. 생략하면 받은 전부.

        결합 세션에서 15분봉은 매 사이클, 1시간봉은 :00 에만 마감된다.
        마감 안 된 시간대의 포지션을 평가하면 **같은 봉을 여러 번 세어**
        보유상한이 4배 빨리 차고, 신호도 같은 봉으로 중복 발생한다."""
        closed = set(bars_by_tf) if closed is None else set(closed)
        cyc = {"ts": datetime.now(timezone.utc).isoformat(),
               "closed_tf": sorted(closed),
               "signals": [], "fills": [], "exits": []}

        # ① 청산 — 보유분부터. 슬롯을 먼저 비워야 그 자리에 새로 들어간다
        for sym in list(self.pos):
            p = self.pos[sym]
            src = p.src or self.cfg.base_tf     # 구형 상태엔 src 가 없다
            if src not in closed:
                continue                        # 이 시간대는 아직 안 닫혔다
            b = bars_by_tf.get(src, {}).get(sym)
            if b is None or b.empty:
                continue
            last = b.iloc[-1]
            p.bars_held += 1
            st = p.to_kernel()
            # ⚠ 손절 우선 판정은 **커널의 _forced_exit** 이 한다. 여기서 다시
            #   쓰면 백테스트와 갈린다 — 실제로 그래 왔다.
            hit = _forced_exit(st, float(last.high), float(last.low))
            reason, ref = (hit[1], hit[0]) if hit else (None, None)
            if reason is None and p.bars_held >= self.spec[src].max_hold_bars:
                reason, ref = "time", float(last.close)
            if reason:
                # 익절은 **지정가**가 호가에 걸려 있다 — 그 값에 체결된다.
                # 손절은 스탑마켓, 시간만료는 시장가라 **지금 값**으로 나간다.
                #
                # ⚠ 백테스트는 손절가에 정확히 체결된다고 가정한다. 실제로는
                #   미끄러지고, 이 세션은 봉 마감 뒤에야 알아채니 더 미끄러진다.
                #   정본값(ref)과 실제값을 **둘 다** 남겨야 그 대가를 잰다.
                #   손절 비중이 80%를 넘는 설정에서는 이 한 숫자가 판정을 가른다.
                if reason == "tp":
                    px, slip = ref, 0.0
                else:
                    now = self.price_fn(sym)
                    px = now if (now and now > 0) else ref
                    slip = 1e4 * (1.0 - px / ref) if ref else 0.0  # +가 손해
                self.exit_slip_sum += slip
                self.n_exit_mkt += 0 if reason == "tp" else 1
                # 회계는 커널이 한다 — 수수료(진입 테이커 5bp / 익절 메이커
                # 2bp)도 여기서 함께 계상된다. 우리가 정하는 건 체결가뿐이다.
                _, tr = kernel_close(st, px, cyc["ts"], reason, KCFG,
                                     exit_maker=(reason == "tp"))
                ret, pnl = tr.return_pct, tr.pnl_cash
                self.equity += pnl
                cyc["exits"].append({
                    "symbol": sym, "reason": reason, "exit_price": px,
                    "entry_price": p.entry_price, "entry_ts": p.entry_ts,
                    "bars_held": p.bars_held, "ret_pct": 100 * ret,
                    "pnl_usd": pnl, "signal_rsi": p.signal_rsi,
                    "src": src, "slip_bp": p.slip_bp,
                    "ref_exit_price": ref, "exit_slip_bp": slip})
                del self.pos[sym]

        # ② 신호 — **전부 기록한다**. 못 잡은 것까지 남겨야 나중에 선택
        #    규칙을 재실행 없이 판정할 수 있다
        cands = []
        for tf in sorted(closed, key=lambda t: TF_MS[t]):
            spec = self.spec.get(tf)
            if spec is None:
                continue
            for sym, b in bars_by_tf.get(tf, {}).items():
                if sym in self.pos or b is None or len(b) < spec.warmup_bars:
                    continue
                c = b["close"].astype(float)
                # 거래가 멈춘 종목은 RSI 가 의미 없다 — 계산 전에 거른다
                w = c.iloc[-(spec.rsi_period + 1):]
                qv = (b["quote_vol"].astype(float).iloc[-(spec.rsi_period + 1):]
                      if "quote_vol" in b.columns else None)
                if (qv is not None and int((qv > 0).sum()) < spec.min_active_bars) \
                        or w.nunique() < spec.min_distinct_closes:
                    self.n_dead += 1
                    continue
                v = float(wilder_rsi(c, spec.rsi_period).iloc[-1])
                if np.isnan(v) or v > spec.entry_rsi:
                    continue
                cands.append({"symbol": sym, "rsi": v, "src": tf,
                              "close": float(c.iloc[-1]),
                              "bar_close_ms": int(b.index[-1].timestamp()
                                                  * 1000) + TF_MS[tf],
                              "rv7": float(c.pipe(np.log).diff()
                                           .rolling(24 * 7).std().iloc[-1]
                                           * math.sqrt(24 * 365))})
        self.n_signal += len(cands)
        cyc["signals"] = cands

        # ③ 선택 — 빈 슬롯만큼 **무작위**. 결합 세션은 두 시간대 후보를
        #    **한 통에 합쳐서** 뽑는다 (시간대 우선순위를 두지 않는다).
        #    측정: 같은 시각·같은 종목 충돌이 1년에 15건뿐이라 우선순위
        #    설계는 결과를 못 바꾼다. 순서 6가지 전부 재봤다.
        free = self.cfg.slots - len(self.pos)
        if cands and free > 0:
            idx = self.rng.permutation(len(cands))[:free]
            picked = [cands[i] for i in idx]
        else:
            picked = []
        self.n_skip += max(0, len(cands) - len(picked))

        # ④ 체결 — **지금 잡을 수 있는 값**으로 채운다
        #
        #   백테스트(정본)는 신호 봉이 닫히는 순간의 시가에 들어간다. 봉 N 의
        #   종가 시각 = 봉 N+1 의 시가 시각이라 실질 즉시 체결이다.
        #
        #   페이퍼는 그럴 수 없다. 봉 마감 +40초에 깨어나 379종목을 훑는 데
        #   50초 넘게 걸린다(실측 사이클 51s). 결정이 끝난 시점엔 마감 순간의
        #   가격이 이미 지나갔다. 그런데 예전 구현은 **다음 사이클에 그 지나간
        #   시가로** 채웠다 — 못 잡는 가격에 샀다고 기록한 것이다.
        #
        #   그래서 지금 호가로 채우고, 정본 값(ref_price)과의 차이를 slip_bp 로
        #   남긴다. 지연의 대가가 얼마인지 영구히 측정된다.
        #
        #   ⚠ 진입 봉(체결 시점에 진행 중인 봉)은 다음 사이클에 마감된 채로
        #     ①에서 평가된다. 그 봉의 고·저에는 체결 **전** 구간이 섞여 있어
        #     불리하게 잡힐 수 있다 — 정본과 같은 방향(보수적)이라 둔다.
        # 체결가는 **동시에** 받는다 — 순차면 20종목에 2초, 그만큼 더 밀린다
        px_map: dict = {}
        if picked:
            with cf.ThreadPoolExecutor(max_workers=min(20, len(picked))) as ex:
                fut = {ex.submit(self.price_fn, c["symbol"]): c["symbol"]
                       for c in picked}
                for f in cf.as_completed(fut):
                    try:
                        px_map[fut[f]] = f.result()
                    except Exception:
                        px_map[fut[f]] = None
        for c in picked:
            # 같은 종목이 두 시간대에서 동시에 뽑힐 수 있다 — 한 번만 채운다
            if c["symbol"] in self.pos:
                continue
            spec = self.spec[c["src"]]
            px = px_map.get(c["symbol"])
            if px is None or px <= 0:
                self.n_pricefail += 1
                continue
            ref = c["close"]                       # 정본 체결가 = 신호 봉 종가
            slip = 1e4 * (px / ref - 1.0) if ref > 0 else 0.0
            if abs(slip) > self.cfg.max_slip_bp:
                # 정상 지연으로는 안 나오는 값 — 시세가 이상하다. 안 채운다.
                self.n_slipreject += 1
                log.warning("%s 괴리 %+.0fbp — 체결 거부 (정본 %.8g / 현재 %.8g)",
                            c["symbol"], slip, ref, px)
                continue
            # 진입 회계도 커널이 한다. 체결가는 우리가 실측한 현재가를
            # MarketOpenFill 로 그대로 넘긴다(바 네 값을 같은 값으로 준다).
            ts_now = datetime.now(timezone.utc).isoformat()
            act = Action(kind="enter_long",
                         sl_price=px * (1 - spec.sl_pct),
                         tp_price=px * (1 + spec.tp_pct),
                         sizing=NotionalSizing(self.cfg.notional_usd),
                         fill=MarketOpenFill())
            st = kernel_open(
                KernelState(cash=self.cfg.notional_usd * 2.0), "enter_long",
                dict(open_price=px, high_price=px, low_price=px,
                     close_price=px), ts_now, act, KCFG)
            if st.side != "long" or st.qty <= 0:
                self.n_pricefail += 1
                continue
            p = Position(
                symbol=c["symbol"], entry_ts=ts_now, entry_price=st.entry_price,
                tp_price=st.tp_price, sl_price=st.sl_price,
                signal_rsi=c["rsi"], src=c["src"], ref_price=ref, slip_bp=slip,
                lag_s=max(0.0, (time.time() * 1000 - c["bar_close_ms"]) / 1000))
            p.sync(st)
            self.pos[c["symbol"]] = p
            self.n_fill += 1
            self.slip_sum += slip
            cyc["fills"].append(asdict(p))

        return cyc

    # ⚠ 재시작하면 보유 포지션과 누적손익이 **증발한다**. 2026-08-18 강제
    #   재부팅 때 실제로 그랬다 — 누적 -$1.50 이 $0.00 으로 초기화됐고
    #   들고 있던 포지션이 사라졌다. 실계좌면 심각한 결함이고, 페이퍼라도
    #   표본이 조용히 없어진다. 매 사이클 상태를 파일로 남기고 기동 시 읽는다.
    def write_config(self, extra: dict) -> None:
        """설정 전문을 산출물 옆에 남긴다.

        안 남기면 몇 달 뒤 이 표본이 어떤 파라미터로 쌓인 건지 알 수 없다.
        이미 다른 설정으로 쌓인 폴더면 **크게 경고한다** — 조용히 섞이면
        표본 전체가 못 쓰게 된다."""
        cur = {"sources": [asdict(x) for x in self.cfg.sources],
               "slots": self.cfg.slots, "notional_usd": self.cfg.notional_usd,
               "seed": self.cfg.seed, **extra}
        f = self.out / "config.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists():
            old = json.loads(f.read_text())
            drift = {k: (old.get(k), cur[k]) for k in cur
                     if k != "started_at" and old.get(k) != cur[k]}
            if drift:
                log.warning("⚠ 설정이 바뀐 폴더에 이어 쌓는다 — 표본이 섞인다: %s",
                            drift)
        f.write_text(json.dumps(cur, ensure_ascii=False, indent=1))

    def save_state(self) -> None:
        st = {"pos": [asdict(p) for p in self.pos.values()],
              "equity": self.equity, "n_fill": self.n_fill,
              "n_signal": self.n_signal, "n_skip": self.n_skip,
              "n_pricefail": self.n_pricefail, "slip_sum": self.slip_sum,
              "exit_slip_sum": self.exit_slip_sum, "n_exit_mkt": self.n_exit_mkt,
              "n_dead": self.n_dead, "n_slipreject": self.n_slipreject,
              "saved_at": datetime.now(timezone.utc).isoformat()}
        tmp = self.state_path.with_suffix(".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(st, ensure_ascii=False))
        tmp.replace(self.state_path)      # 원자적 교체 — 중간에 죽어도 안 깨진다

    def load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            st = json.loads(self.state_path.read_text())
        except Exception as exc:
            log.warning("상태 파일 손상 — 새로 시작: %s", exc)
            return
        self.pos = {d["symbol"]: Position(**d) for d in st.get("pos", [])}
        self.equity = float(st.get("equity", 0.0))
        self.n_fill = int(st.get("n_fill", 0))
        self.n_signal = int(st.get("n_signal", 0))
        self.n_skip = int(st.get("n_skip", 0))
        # 새 필드 — 예전 상태 파일엔 없다. 기본값으로 이어받는다
        self.n_pricefail = int(st.get("n_pricefail", 0))
        self.slip_sum = float(st.get("slip_sum", 0.0))
        self.exit_slip_sum = float(st.get("exit_slip_sum", 0.0))
        self.n_exit_mkt = int(st.get("n_exit_mkt", 0))
        self.n_dead = int(st.get("n_dead", 0))
        self.n_slipreject = int(st.get("n_slipreject", 0))
        log.info("상태 복원 — 보유 %d · 누적 $%.2f · 신호 %d · 체결 %d (저장 %s)",
                 len(self.pos), self.equity, self.n_signal, self.n_fill,
                 st.get("saved_at", "?")[:19])

    def persist(self, cyc: dict) -> None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        d = self.out / day
        d.mkdir(parents=True, exist_ok=True)
        cyc["state"] = {"open_positions": len(self.pos),
                        "equity_usd": round(self.equity, 2),
                        "n_signal": self.n_signal, "n_fill": self.n_fill,
                        "n_skip": self.n_skip,
                        "n_pricefail": self.n_pricefail,
                        "slip_bp_mean": round(self.slip_sum / self.n_fill, 2)
                                        if self.n_fill else 0.0,
                        "n_exit_mkt": self.n_exit_mkt,
                        "n_dead": self.n_dead,
                        "n_slipreject": self.n_slipreject,
                        "exit_slip_bp_mean":
                            round(self.exit_slip_sum / self.n_exit_mkt, 2)
                            if self.n_exit_mkt else 0.0}
        with open(d / "cycles.jsonl", "a") as fh:
            fh.write(json.dumps(cyc, ensure_ascii=False) + "\n")
        self.save_state()


def selftest() -> None:
    """합성 경로로 규약을 확인한다 — 시세를 안 건드린다."""
    cfg = PaperConfig(slots=2, warmup_bars=50)
    pp = RsiPaper(cfg, ["A", "B", "C"], OUT_DIR)
    idx = pd.date_range("2026-01-01", periods=120, freq="h", tz="UTC")
    dn = pd.Series(np.linspace(100, 60, 120), index=idx)   # 단조 하락 → RSI 0
    up = pd.Series(np.linspace(60, 100, 120), index=idx)
    mk = lambda c: pd.DataFrame({"open": c, "high": c * 1.001,
                                 "low": c * 0.999, "close": c}, index=idx)
    bars = {"A": mk(dn), "B": mk(dn * 1.01), "C": mk(up)}
    # 시세를 안 건드리고 체결 경로를 확인한다 — 현재가를 정본 대비 +1% 로 준다
    ref_close = {"A": float(dn.iloc[-1]), "B": float((dn * 1.01).iloc[-1])}
    pp.price_fn = lambda sym: ref_close[sym] * 1.005   # +50bp (상한 100 미만)
    cyc = pp.step({"1h": bars})
    syms = {c["symbol"] for c in cyc["signals"]}
    if syms != {"A", "B"}:
        raise SystemExit(f"신호가 틀렸다 — 기대 A,B / 실제 {syms}")
    if len(cyc["fills"]) != 2 or len(pp.pos) != 2:
        raise SystemExit(f"슬롯 2인데 체결 {len(cyc['fills'])}건")
    log.info("✔ 신호·슬롯 확인 — 하락 2종목 신호, 상승 1종목 무시, 슬롯만큼 선택")

    p = pp.pos["A"]
    # 체결가가 **주입한 현재가**인지 — 지나간 봉 시가로 채우면 여기서 걸린다
    if abs(p.entry_price - ref_close["A"] * 1.005) > 1e-9:
        raise SystemExit(f"체결가가 현재가가 아니다 {p.entry_price}")
    if abs(p.ref_price - ref_close["A"]) > 1e-9:
        raise SystemExit(f"정본 기준가 틀림 {p.ref_price}")
    if abs(p.slip_bp - 50.0) > 1e-6:
        raise SystemExit(f"지연 대가 계산 틀림 {p.slip_bp}")
    # 익절·손절은 **실제 체결가** 기준이어야 한다 (정본 기준가가 아니라)
    if abs(p.tp_price / p.entry_price - 1.08) > 1e-9:
        raise SystemExit(f"익절가 틀림 {p.tp_price/p.entry_price:.4f}")
    if abs(p.sl_price / p.entry_price - 0.97) > 1e-9:
        raise SystemExit(f"손절가 틀림 {p.sl_price/p.entry_price:.4f}")
    log.info("✔ 체결 확인 — **현재가** 즉시 진입 · 정본 대비 +%.1fbp 기록 · "
             "익절 +8%% / 손절 -3%% 는 체결가 기준", p.slip_bp)

    # 결합 세션 — 슬롯 공유 · 시간대별 규약 · 마감된 시간대만 평가
    ccfg = PaperConfig(slots=2, notional_usd=100.0, sources=[
        SourceSpec(tf="15m", entry_rsi=99, tp_pct=0.05, sl_pct=0.02,
                   max_hold_bars=3, warmup_bars=50),
        SourceSpec(tf="1h", entry_rsi=99, tp_pct=0.08, sl_pct=0.03,
                   max_hold_bars=99, warmup_bars=50)])
    if ccfg.base_tf != "15m" or ccfg.session_name != "combo_15mr99_1hr99":
        raise SystemExit(f"결합 설정이 안 잡힌다 — {ccfg.base_tf} {ccfg.session_name}")
    cp = RsiPaper(ccfg, ["A", "B"], OUT_DIR)
    # 체결가를 합성 봉의 마지막 종가 근처로 둔다 — 안 그러면 진입 즉시
    # 손절이 나고 같은 사이클에 재진입해서 보유봉 검사가 무의미해진다
    PX = float(dn.iloc[-1]) * 0.995      # -50bp (괴리 상한 100bp 미만)
    cp.price_fn = lambda sym: PX
    # 1h 봉은 **안 닫혔다** — B 는 1h 로만 후보가 되므로 잡히면 안 된다
    c1 = cp.step({"15m": {"A": mk(dn)}, "1h": {"A": mk(dn), "B": mk(dn)}},
                 closed={"15m"})
    if {f["symbol"] for f in c1["fills"]} != {"A"}:
        raise SystemExit(f"마감 안 된 시간대 후보가 섞였다 — {c1['fills']}")
    if cp.pos["A"].src != "15m":
        raise SystemExit(f"출처 기록 안 됨 — {cp.pos['A'].src!r}")
    if abs(cp.pos["A"].tp_price / PX - 1.05) > 1e-9 or \
       abs(cp.pos["A"].sl_price / PX - 0.98) > 1e-9:
        raise SystemExit("시간대별 익절·손절이 안 먹었다")
    held0 = cp.pos["A"].bars_held
    cp.step({"1h": {"A": mk(dn)}}, closed={"1h"})
    if cp.pos["A"].bars_held != held0:
        raise SystemExit("15m 포지션이 1h 마감에 보유봉이 늘었다")
    cp.step({"15m": {"A": mk(dn)}}, closed={"15m"})
    if cp.pos["A"].bars_held != held0 + 1:
        raise SystemExit("자기 시간대 마감인데 보유봉이 안 늘었다")
    log.info("✔ 결합 확인 — 슬롯 공유 · 시간대별 익절/손절 · "
             "**마감된 시간대만** 평가")

    # ── 죽은 종목 게이트 — 2026-08-19 HFTUSDT 재현
    #   봉이 전부 같은 값이고 거래대금 0. RSI 가 0/0 에 가까워 0.28 이 나오고
    #   문턱을 통과했다. 한 주도 안 거래된 종목에서 +7.92% 익절이 났다.
    dead = pd.DataFrame({"open": 0.0238, "high": 0.0238, "low": 0.0238,
                         "close": 0.0238, "quote_vol": 0.0}, index=idx)
    pd_ = RsiPaper(PaperConfig(slots=2, warmup_bars=50), ["D"], OUT_DIR)
    pd_.price_fn = lambda sym: 0.0209654          # 마지막 체결가와 따로 노는 호가
    cd = pd_.step({"1h": {"D": dead}})
    if cd["signals"] or cd["fills"] or pd_.n_dead != 1:
        raise SystemExit(f"죽은 종목이 안 걸러졌다 — 신호 {cd['signals']} "
                         f"체결 {cd['fills']} n_dead {pd_.n_dead}")
    log.info("✔ 죽은 종목 확인 — 평평한 봉·거래대금 0 은 RSI 계산 전에 제외")

    # ── 괴리 상한 — 시세가 정본과 크게 어긋나면 안 채운다
    ps_ = RsiPaper(PaperConfig(slots=2, warmup_bars=50, max_slip_bp=100.0),
                   ["A"], OUT_DIR)
    ps_.price_fn = lambda sym: float(dn.iloc[-1]) * 0.85    # -1500bp
    cs_ = ps_.step({"1h": {"A": mk(dn)}})
    if cs_["fills"] or ps_.pos or ps_.n_slipreject != 1:
        raise SystemExit(f"괴리 상한이 안 걸렸다 — {cs_['fills']} "
                         f"n_slipreject {ps_.n_slipreject}")
    ps_.price_fn = lambda sym: float(dn.iloc[-1]) * 1.005   # +50bp = 허용
    cs2 = ps_.step({"1h": {"A": mk(dn)}})
    if not cs2["fills"]:
        raise SystemExit("허용 범위인데 체결이 안 됐다")
    log.info("✔ 괴리 상한 확인 — %+.0fbp 거부 / %+.0fbp 체결 (상한 %gbp)",
             -1500, 50, ps_.cfg.max_slip_bp)

    # 유니버스에서 빠진 보유 종목도 계속 봐야 한다 — 안 보면 슬롯이 묶인다
    sl_ = scan_list(["A", "B"], {"B"}, {"B", "Z"})
    if set(sl_) != {"A", "B", "Z"} or len(sl_) != 3:
        raise SystemExit(f"보유 종목이 스캔에서 빠졌다 — {sl_}")
    if scan_list(["A", "B"], {"B"}, set()) != ["A"]:
        raise SystemExit("죽은 종목이 안 빠졌다")
    log.info("✔ 스캔 목록 확인 — 유니버스 이탈·시세 실패라도 **보유분은** 본다")

    # 현재가를 못 받으면 **채우지 않는다** — 지나간 값으로 때우면 안 된다
    p3 = RsiPaper(PaperConfig(slots=2, warmup_bars=50), ["A"], OUT_DIR)
    p3.price_fn = lambda sym: None
    c3 = p3.step({"1h": {"A": mk(dn)}})
    if c3["fills"] or p3.pos or p3.n_pricefail != 1:
        raise SystemExit(f"현재가 실패인데 체결됐다 — {c3['fills']} {p3.n_pricefail}")
    log.info("✔ 시세 실패 확인 — 현재가 없으면 체결 안 함 (n_pricefail 집계)")

    # 손절 발동 — 불리한 쪽을 먼저 본다
    crash = bars["A"].copy()
    crash.iloc[-1, crash.columns.get_loc("low")] = p.sl_price * 0.99
    crash.iloc[-1, crash.columns.get_loc("high")] = p.tp_price * 1.01
    c2 = pp.step({"1h": {"A": crash}})
    ex = [e for e in c2["exits"] if e["symbol"] == "A"]
    if not ex or ex[0]["reason"] != "sl":
        raise SystemExit(f"같은 봉에서 손절·익절이 겹쳤는데 손절이 안 났다: {ex}")
    log.info("✔ 청산 규약 확인 — 한 봉에 손절·익절 동시면 **손절** (보수적)")

    # 손절은 **현재가**로 나가고 정본(손절가) 대비 차이를 남겨야 한다.
    # 이걸 안 재면 손절 비중 80% 설정의 실전 성적을 영영 모른다.
    e = ex[0]
    if abs(e["ref_exit_price"] - p.sl_price) > 1e-9:
        raise SystemExit(f'정본 손절가 기록 안 됨 — {e["ref_exit_price"]}')
    px_now = ref_close["A"] * 1.005
    if abs(e["exit_price"] - px_now) > 1e-9:
        raise SystemExit(f'손절이 현재가로 안 나갔다 — {e["exit_price"]}')
    want = 1e4 * (1.0 - px_now / p.sl_price)
    if abs(e["exit_slip_bp"] - want) > 1e-6:
        raise SystemExit(f'청산 지연대가 계산 틀림 {e["exit_slip_bp"]} vs {want}')
    log.info("✔ 손절 체결 확인 — **현재가**로 청산 · 정본 대비 %+.1fbp 기록",
             e["exit_slip_bp"])

    # 익절은 지정가라 그 값에 체결된다 — 미끄러지지 않아야 한다
    p4 = RsiPaper(PaperConfig(slots=1, warmup_bars=50), ["A"], OUT_DIR)
    # 진입은 허용 범위로 하고, **청산 직전에** 현재가를 크게 어긋나게 만든다.
    # (진입까지 어긋나게 두면 괴리 상한에 걸려 포지션이 안 생긴다)
    p4.price_fn = lambda sym: ref_close["A"]
    c4 = p4.step({"1h": {"A": mk(dn)}})
    pos4 = p4.pos["A"]
    p4.price_fn = lambda sym: ref_close["A"] * 0.5      # 익절이 이걸 쓰면 안 된다
    win = mk(dn).copy()
    win.iloc[-1, win.columns.get_loc("high")] = pos4.tp_price * 1.01
    win.iloc[-1, win.columns.get_loc("low")] = pos4.sl_price * 1.01
    c5 = p4.step({"1h": {"A": win}})
    e5 = [x for x in c5["exits"] if x["symbol"] == "A"]
    if not e5 or e5[0]["reason"] != "tp":
        raise SystemExit(f"익절이 안 났다 — {c5['exits']}")
    if abs(e5[0]["exit_price"] - pos4.tp_price) > 1e-9 or e5[0]["exit_slip_bp"] != 0.0:
        raise SystemExit(f"익절이 지정가로 안 나갔다 — {e5[0]}")
    log.info("✔ 익절 체결 확인 — 지정가라 익절가 그대로 (미끄러짐 0)")

    # ⓔ 상태 저장·복원 — 이게 안 되면 재시작 때 **조용히** 표본을 잃는다
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pp.state_path = Path(td) / "state.json"
        pp.equity = -1.5
        pp.save_state()
        if not pp.state_path.exists():
            raise SystemExit("상태 파일이 안 만들어졌다")
        pos_before = {k: v.entry_price for k, v in pp.pos.items()}
        eq_before, nf, ns = pp.equity, pp.n_fill, pp.n_signal
        p2 = RsiPaper(cfg, ["A", "B", "C"], Path(td))
        p2.load_state()
        if {k: v.entry_price for k, v in p2.pos.items()} != pos_before:
            raise SystemExit(f"포지션 복원 실패 — {p2.pos} vs {pos_before}")
        if (p2.equity, p2.n_fill, p2.n_signal) != (eq_before, nf, ns):
            raise SystemExit(
                f"집계 복원 실패 — {(p2.equity,p2.n_fill,p2.n_signal)} "
                f"vs {(eq_before,nf,ns)}")
        log.info("✔ 상태 영속 확인 — 포지션 %d · 누적 $%.2f · 신호 %d 복원",
                 len(p2.pos), p2.equity, p2.n_signal)

        # 새 필드가 없는 **예전 상태 파일**도 읽혀야 한다. 안 그러면 이번
        # 배포로 가동 중인 세션의 보유 포지션이 조용히 증발한다.
        old = {"pos": [{"symbol": "Z", "entry_ts": "2026-01-01T00:00:00+00:00",
                        "entry_price": 10.0, "bars_held": 3, "tp_price": 10.8,
                        "sl_price": 9.7, "signal_rsi": 5.0}],
               "equity": -2.5, "n_fill": 1, "n_signal": 4, "n_skip": 2}
        (Path(td) / "state.json").write_text(json.dumps(old))
        p3 = RsiPaper(cfg, ["Z"], Path(td))
        p3.load_state()
        if "Z" not in p3.pos or p3.pos["Z"].ref_price != 0.0 or p3.equity != -2.5:
            raise SystemExit(f"구형 상태 복원 실패 — {p3.pos}")
        log.info("✔ 구형 상태 호환 확인 — 새 필드 없는 파일도 그대로 복원")

    if pp.n_signal < 2 or pp.n_skip < 0:
        raise SystemExit("신호 집계가 안 된다")
    # ⓖ **정본 대조** — 같은 진입·청산을 백테스트 경로(GenericBacktester 가
    #   쓰는 커널)에 넣어 손익이 일치하는지 본다.
    #
    #   이게 없어서 2026-08-19 까지 수수료 0 으로 돌았다. 스크립트가 제
    #   규약대로 도는지만 검사했지, **정본과 같은 답을 내는지**는 한 번도
    #   묻지 않았다. 클래스 검증도 경로 검증도 통과했는데 기준점이 없었다.
    from app.composer_framework.kernel import KernelConfig as _KC
    from app.composer_framework.kernel import KernelState as _KS
    from app.composer_framework.kernel import close as _kclose
    from app.composer_framework.kernel import open_position as _kopen

    ENTRY, EXIT, NOTIONAL = 100.0, 105.0, 50.0
    ref_act = Action(kind="enter_long", sl_price=ENTRY * 0.97,
                     tp_price=ENTRY * 1.08,
                     sizing=NotionalSizing(NOTIONAL), fill=MarketOpenFill())
    ref_st = _kopen(_KS(cash=NOTIONAL * 2.0), "enter_long",
                    dict(open_price=ENTRY, high_price=ENTRY, low_price=ENTRY,
                         close_price=ENTRY), "t0", ref_act, KCFG)
    _, ref_tr = _kclose(ref_st, EXIT, "t1", "tp", KCFG, exit_maker=True)

    pp5 = RsiPaper(PaperConfig(slots=1, warmup_bars=50, notional_usd=NOTIONAL,
                               tp_pct=0.08, sl_pct=0.03), ["A"], OUT_DIR)
    pp5.price_fn = lambda sym: ENTRY
    flat = pd.Series(np.linspace(140, 100, 120), index=idx)   # 하락 → RSI 0
    pp5.step({"1h": {"A": mk(flat)}})
    if "A" not in pp5.pos:
        raise SystemExit("대조용 진입이 안 됐다")
    win2 = mk(flat).copy()
    win2.iloc[-1, win2.columns.get_loc("high")] = pp5.pos["A"].tp_price * 1.01
    win2.iloc[-1, win2.columns.get_loc("low")] = pp5.pos["A"].sl_price * 1.01
    pp5.price_fn = lambda sym: EXIT
    cx = pp5.step({"1h": {"A": win2}})
    ex2 = [x for x in cx["exits"] if x["symbol"] == "A"]
    if not ex2:
        raise SystemExit(f"대조용 청산이 안 났다 — {cx['exits']}")
    # 익절가는 진입가의 1.08 배이므로 청산가가 다르다. 수익률 공식만 대조한다.
    got = ex2[0]["ret_pct"] / 100.0
    st_ref = _KS(cash=ref_st.cash, side="long", qty=ref_st.qty,
                 entry_price=ref_st.entry_price, entry_ts="t0",
                 sl_price=ref_st.sl_price, tp_price=ref_st.tp_price,
                 entry_maker=ref_st.entry_maker)
    _, want_tr = _kclose(st_ref, ex2[0]["exit_price"], "t1", "tp", KCFG,
                         exit_maker=True)
    if abs(got - want_tr.return_pct) > 1e-9:
        raise SystemExit(f"정본과 손익이 다르다 — 페이퍼 {got:.8f} vs "
                         f"정본 {want_tr.return_pct:.8f}")
    # 수수료가 실제로 물리는지 — 안 물면 +8%% 가 그대로 나온다
    gross = ex2[0]["exit_price"] / ex2[0]["entry_price"] - 1.0
    if got >= gross:
        raise SystemExit(f"수수료가 안 빠졌다 — 순 {got:.6f} >= 총 {gross:.6f}")
    log.info("✔ 정본 대조 확인 — 손익이 커널과 일치 · 수수료 %.1fbp 반영 "
             "(총 %.4f%% → 순 %.4f%%)", 1e4 * (gross - got), 100 * gross,
             100 * got)

    log.info("✔ 자기검사 통과 — 신호 %d · 체결 %d · 미체결 %d",
             pp.n_signal, pp.n_fill, pp.n_skip)


def main() -> int:
    p = argparse.ArgumentParser(description="RSI 극단 전진 페이퍼")
    p.add_argument("--tf", default="1h", choices=list(TF_MS),
                   help="봉 주기. 보유상한(--hold-bars)도 같이 맞춰라")
    p.add_argument("--sources", default="",
                   help="결합 세션. 'tf:rsi:익절:손절:보유봉' 을 쉼표로. "
                        "예 '15m:8:0.08:0.015:192,1h:12:0.08:0.03:48'. "
                        "주면 --tf/--entry-rsi/--tp/--sl/--hold-bars 는 무시")
    p.add_argument("--hold-bars", type=int, default=48,
                   help="보유상한(봉). 물리 48시간이면 1h=48 · 15m=192 · 5m=576")
    p.add_argument("--slots", type=int, default=5)
    p.add_argument("--entry-rsi", type=float, default=12.0)
    p.add_argument("--tp", type=float, default=0.08)
    p.add_argument("--sl", type=float, default=0.03)
    p.add_argument("--notional", type=float, default=200.0)
    p.add_argument("--universe", default=str(UNIVERSE))
    p.add_argument("--once", action="store_true", help="한 사이클만 (점검용)")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()

    selftest()
    if a.selftest:
        return 0

    if a.sources:
        specs = []
        for chunk in a.sources.split(","):
            f = chunk.strip().split(":")
            if len(f) != 5:
                raise SystemExit(f"--sources 항목은 tf:rsi:익절:손절:보유봉 — {chunk!r}")
            specs.append(SourceSpec(tf=f[0], entry_rsi=float(f[1]),
                                    tp_pct=float(f[2]), sl_pct=float(f[3]),
                                    max_hold_bars=int(f[4])))
        cfg = PaperConfig(slots=a.slots, notional_usd=a.notional,
                          sources=specs)
    else:
        cfg = PaperConfig(slots=a.slots, entry_rsi=a.entry_rsi, tf=a.tf,
                          max_hold_bars=a.hold_bars,
                          tp_pct=a.tp, sl_pct=a.sl, notional_usd=a.notional)
    syms = [s.strip().upper() for s in Path(a.universe).read_text().split()
            if s.strip()]
    log.info("유니버스 %d종목 · 슬롯 %d **공유** · 슬롯당 $%.0f · 세션 %s",
             len(syms), cfg.slots, cfg.notional_usd, cfg.session_name)
    for x in cfg.sources:
        log.info("  · %s봉 RSI<=%g · 익절 %g%% / 손절 %g%% · 보유상한 %d봉",
                 x.tf, x.entry_rsi, 100 * x.tp_pct, 100 * x.sl_pct,
                 x.max_hold_bars)
    pp = RsiPaper(cfg, syms, OUT_DIR / cfg.session_name)
    pp.load_state()
    pp.write_config({"universe": str(a.universe), "n_symbols": len(syms),
                     "started_at": datetime.now(timezone.utc).isoformat()})
    dead: set = set()      # 시세가 계속 실패하는 종목 (상장폐지·심볼변경)
    fail: dict = {}        # 종목별 **연속** 실패 횟수

    while True:
        # 봉 마감 직후로 맞춘다 (+40초 여유 — 아카이브가 아니라 REST 라 빠르다)
        now = time.time()
        base = TF_MS[cfg.base_tf] / 1000
        nxt = (int(now // base) + 1) * base + cfg.bar_wait_s
        if not a.once:
            time.sleep(max(5, nxt - now))
        t0 = time.time()
        # 방금 마감된 봉의 경계. 바이낸스 봉은 UTC epoch 에 정렬돼 있으므로
        # 경계가 그 시간대의 길이로 나누어떨어지면 그 시간대도 방금 마감됐다.
        edge_ms = int(time.time() // base) * int(base) * 1000
        closed = {x.tf for x in cfg.sources if edge_ms % TF_MS[x.tf] == 0}
        if not closed:                       # 이론상 base 는 항상 들어온다
            closed = {cfg.base_tf}
        targets = scan_list(syms, dead, set(pp.pos))
        bars_by_tf: dict = {}
        miss: list = []
        # ⚠ 순차 조회는 377종목에 43초(실측). 그 사이에 급등이 끝난다.
        #   스레드풀로 병렬화한다 — 조회는 I/O 대기라 GIL 이 문제되지 않는다.
        for tf in sorted(closed, key=lambda t: TF_MS[t]):
            spec = pp.spec[tf]
            lim = max(300, spec.warmup_bars + 50)
            d: dict = {}
            with cf.ThreadPoolExecutor(max_workers=cfg.fetch_workers) as ex:
                fut = {ex.submit(fetch_klines, s, lim, tf): s for s in targets}
                for f in cf.as_completed(fut):
                    sym_ = fut[f]
                    try:
                        b = f.result()
                    except Exception:
                        b = None
                    if b is not None:
                        d[sym_] = b
                    elif tf == cfg.base_tf:   # 건강 판정은 기준 시간대로만
                        miss.append(sym_)
            bars_by_tf[tf] = d
        bars = bars_by_tf.get(cfg.base_tf, {})          # 레이트리밋 여유
        # ⚠ 상장폐지·심볼변경 종목은 매 사이클 HTTP 400 을 낸다(실측 BTCSTUSDT·
        #   AERGOUSDT). 로그만 더럽히고 사이클 시간을 늘리므로 3회 연속 실패하면
        #   뺀다. 일시적 장애로 영구 제외하지 않도록 **연속** 실패만 센다.
        for s in miss:
            fail[s] = fail.get(s, 0) + 1
            if fail[s] >= 3 and s not in pp.pos:
                dead.add(s)
                log.warning("%s — 3회 연속 시세 실패, 유니버스에서 제외", s)
        for s in bars:
            fail.pop(s, None)
        if len(bars) < (len(syms) - len(dead)) * 0.8:
            log.warning("시세 %d/%d — 이번 사이클 건너뜀", len(bars), len(syms))
            if a.once:
                return 1
            continue

        cyc = pp.step(bars_by_tf, closed)
        pp.persist(cyc)
        log.info("사이클 %.0fs · 마감 %s · 신호 %d · 진입 %d · 청산 %d · "
                 "보유 %d/%d · 누적 $%.2f · 지연대가 %+.1fbp",
                 time.time() - t0, ",".join(sorted(closed)),
                 len(cyc["signals"]), len(cyc["fills"]), len(cyc["exits"]),
                 len(pp.pos), cfg.slots, pp.equity,
                 pp.slip_sum / pp.n_fill if pp.n_fill else 0.0)
        if a.once:
            return 0


if __name__ == "__main__":
    sys.exit(main())
