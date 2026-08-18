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
    진입 : RSI(14) <= 12 → 롱. 신호 봉의 **다음 봉 시가** 체결 (정본 규약)
    청산 : 익절 +8% / 손절 -3% / 보유 48봉 만료 중 먼저 오는 것
    배분 : 슬롯 3~5. 경쟁 신호 중 **무작위** 선택
           ⚠ rv_high·rsi_low 선택 규칙은 **넣지 않는다.** 증명 안 됐고,
             넣었다가 안 되면 신호 탓인지 규칙 탓인지 못 가른다.

⚠ 체결 안 된 신호도 **전부 기록한다**
    슬롯이 없어 못 잡은 신호까지 남겨야, 나중에 어떤 선택 규칙이 나았는지를
    **재실행 없이** 판정할 수 있다. 조용히 버리면 그 질문이 영영 닫힌다.

⚠ 이것은 System-2 forward-sim 이다 — 실계좌가 아니다
    슬리피지 0, 지정가 완전체결 가정. System-1(실계좌 paper)과 섞어 읽지 마라.
    백테스트와 **같은 규약**으로 두어야 백테스트 대 전진의 차이가 순수하게
    "미래 데이터"에서만 오게 된다.

⚠ 봉 마감 후에만 판단한다
    진행 중인 봉의 고가·저가는 확정값이 아니다. 마감된 봉만 쓴다.

사용:
  python3 scripts/binance/rsi_extreme_paper.py --selftest
  python3 scripts/binance/rsi_extreme_paper.py --slots 5
"""
from __future__ import annotations

import argparse
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

REST = "https://fapi.binance.com/fapi/v1/klines"
UNIVERSE = ROOT / "configs" / "rsi_paper_universe.txt"
OUT_DIR = ROOT / "runs" / "paper_sessions" / "rsi_extreme"


# ══════════════════════════════════════════════════════════════════════
#  설정은 한 곳에만
# ══════════════════════════════════════════════════════════════════════
@dataclass
class PaperConfig:
    rsi_period: int = 14
    entry_rsi: float = 12.0      # RSI <= 이 값이면 롱 후보
    tp_pct: float = 0.08
    sl_pct: float = 0.03
    max_hold_bars: int = 48
    slots: int = 5
    notional_usd: float = 200.0  # 슬롯당 명목
    warmup_bars: int = 200       # RSI 안정화
    seed: int = 20260817         # 무작위 선택의 재현성

    def __post_init__(self):
        if not (0 < self.entry_rsi < 100):
            raise SystemExit(f"entry_rsi 는 (0,100) — {self.entry_rsi}")
        if self.tp_pct <= 0 or self.sl_pct <= 0 or self.slots < 1:
            raise SystemExit("익절·손절·슬롯은 양수여야 한다")


@dataclass
class Position:
    symbol: str
    entry_ts: str
    entry_price: float
    bars_held: int = 0
    tp_price: float = 0.0
    sl_price: float = 0.0
    signal_rsi: float = 0.0


def wilder_rsi(close: pd.Series, period: int) -> pd.Series:
    """정본 소스와 **같은 구현**을 쓴다. 여기서 다르게 계산하면 백테스트와
    비교가 성립하지 않는다."""
    from app.composer_framework.sources.rsi_threshold_source import (
        wilder_rsi as _r)
    return _r(close, period)


def fetch_klines(symbol: str, limit: int = 300) -> pd.DataFrame | None:
    """마감된 1h 봉만. 진행 중인 마지막 봉은 **버린다**."""
    q = urllib.parse.urlencode({"symbol": symbol, "interval": "1h",
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
        if ot + 3_600_000 > now_ms:      # 진행 중인 봉
            continue
        rows.append((ot, float(k[1]), float(k[2]), float(k[3]), float(k[4])))
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ot", "open", "high", "low", "close"])
    df["ts"] = pd.to_datetime(df.ot, unit="ms", utc=True)
    return df.set_index("ts")


class RsiPaper:
    def __init__(self, cfg: PaperConfig, symbols: list, out_dir: Path):
        self.cfg = cfg
        self.symbols = symbols
        self.out = out_dir
        self.pos: dict[str, Position] = {}
        self.rng = np.random.default_rng(cfg.seed)
        self.equity = 0.0            # 누적 실현손익 (USD)
        self.n_fill = 0
        self.n_signal = 0
        self.n_skip = 0

    # ── 한 사이클: 마감 봉 기준으로 청산 먼저, 그 다음 진입 ──────
    def step(self, bars: dict) -> dict:
        cyc = {"ts": datetime.now(timezone.utc).isoformat(),
               "signals": [], "fills": [], "exits": []}

        # ① 청산 — 보유분부터. 슬롯을 먼저 비워야 그 자리에 새로 들어간다
        for sym in list(self.pos):
            b = bars.get(sym)
            if b is None or b.empty:
                continue
            last = b.iloc[-1]
            p = self.pos[sym]
            p.bars_held += 1
            reason, px = None, None
            # ⚠ 불리한 쪽(손절)을 먼저 본다 — 한 봉 안의 순서를 모른다
            if last.low <= p.sl_price:
                reason, px = "sl", p.sl_price
            elif last.high >= p.tp_price:
                reason, px = "tp", p.tp_price
            elif p.bars_held >= self.cfg.max_hold_bars:
                reason, px = "time", float(last.close)
            if reason:
                ret = (px / p.entry_price - 1.0)
                pnl = ret * self.cfg.notional_usd
                self.equity += pnl
                cyc["exits"].append({
                    "symbol": sym, "reason": reason, "exit_price": px,
                    "entry_price": p.entry_price, "entry_ts": p.entry_ts,
                    "bars_held": p.bars_held, "ret_pct": 100 * ret,
                    "pnl_usd": pnl, "signal_rsi": p.signal_rsi})
                del self.pos[sym]

        # ② 신호 — **전부 기록한다**. 못 잡은 것까지 남겨야 나중에 선택
        #    규칙을 재실행 없이 판정할 수 있다
        cands = []
        for sym, b in bars.items():
            if sym in self.pos or b is None or len(b) < self.cfg.warmup_bars:
                continue
            r = wilder_rsi(b["close"].astype(float), self.cfg.rsi_period)
            v = float(r.iloc[-1])
            if np.isnan(v) or v > self.cfg.entry_rsi:
                continue
            cands.append({"symbol": sym, "rsi": v,
                          "close": float(b["close"].iloc[-1]),
                          "rv7": float(np.log(b["close"].astype(float)).diff()
                                       .rolling(24 * 7).std().iloc[-1]
                                       * math.sqrt(24 * 365))})
        self.n_signal += len(cands)
        cyc["signals"] = cands

        # ③ 진입 — 빈 슬롯만큼 **무작위** 선택 (선택 규칙은 넣지 않는다)
        free = self.cfg.slots - len(self.pos)
        if cands and free > 0:
            idx = self.rng.permutation(len(cands))[:free]
            picked = {cands[i]["symbol"] for i in idx}
        else:
            picked = set()
        self.n_skip += max(0, len(cands) - len(picked))
        for c in cands:
            if c["symbol"] not in picked:
                continue
            # 체결가 = **다음 봉 시가**. 지금은 그 값을 모르므로 마감 종가로
            # 근사하지 않는다 — 다음 사이클에 시가로 채운다.
            cyc["fills"].append(c)

        return cyc

    def open_pending(self, pending: list, bars: dict) -> list:
        """직전 사이클에서 고른 신호를 **이번 봉 시가**로 체결한다."""
        opened = []
        for c in pending:
            b = bars.get(c["symbol"])
            if b is None or b.empty or c["symbol"] in self.pos:
                continue
            if len(self.pos) >= self.cfg.slots:
                break
            px = float(b["open"].iloc[-1])
            p = Position(symbol=c["symbol"],
                         entry_ts=str(b.index[-1]), entry_price=px,
                         tp_price=px * (1 + self.cfg.tp_pct),
                         sl_price=px * (1 - self.cfg.sl_pct),
                         signal_rsi=c["rsi"])
            self.pos[c["symbol"]] = p
            self.n_fill += 1
            opened.append(asdict(p))
        return opened

    def persist(self, cyc: dict, opened: list) -> None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        d = self.out / day
        d.mkdir(parents=True, exist_ok=True)
        cyc["opened"] = opened
        cyc["state"] = {"open_positions": len(self.pos),
                        "equity_usd": round(self.equity, 2),
                        "n_signal": self.n_signal, "n_fill": self.n_fill,
                        "n_skip": self.n_skip}
        with open(d / "cycles.jsonl", "a") as fh:
            fh.write(json.dumps(cyc, ensure_ascii=False) + "\n")


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
    cyc = pp.step(bars)
    syms = {c["symbol"] for c in cyc["signals"]}
    if syms != {"A", "B"}:
        raise SystemExit(f"신호가 틀렸다 — 기대 A,B / 실제 {syms}")
    if len(cyc["fills"]) != 2:
        raise SystemExit(f"슬롯 2인데 체결 후보 {len(cyc['fills'])}건")
    log.info("✔ 신호·슬롯 확인 — 하락 2종목 신호, 상승 1종목 무시, 슬롯만큼 선택")

    opened = pp.open_pending(cyc["fills"], bars)
    if len(opened) != 2 or len(pp.pos) != 2:
        raise SystemExit("체결이 안 잡혔다")
    p = pp.pos["A"]
    if abs(p.tp_price / p.entry_price - 1.08) > 1e-9:
        raise SystemExit(f"익절가 틀림 {p.tp_price/p.entry_price:.4f}")
    if abs(p.sl_price / p.entry_price - 0.97) > 1e-9:
        raise SystemExit(f"손절가 틀림 {p.sl_price/p.entry_price:.4f}")
    log.info("✔ 체결 확인 — 다음 봉 시가 진입 · 익절 +8%% / 손절 -3%% 정확")

    # 손절 발동 — 불리한 쪽을 먼저 본다
    crash = bars["A"].copy()
    crash.iloc[-1, crash.columns.get_loc("low")] = p.sl_price * 0.99
    crash.iloc[-1, crash.columns.get_loc("high")] = p.tp_price * 1.01
    c2 = pp.step({"A": crash})
    ex = [e for e in c2["exits"] if e["symbol"] == "A"]
    if not ex or ex[0]["reason"] != "sl":
        raise SystemExit(f"같은 봉에서 손절·익절이 겹쳤는데 손절이 안 났다: {ex}")
    log.info("✔ 청산 규약 확인 — 한 봉에 손절·익절 동시면 **손절** (보수적)")

    if pp.n_signal < 2 or pp.n_skip < 0:
        raise SystemExit("신호 집계가 안 된다")
    log.info("✔ 자기검사 통과 — 신호 %d · 체결 %d · 미체결 %d",
             pp.n_signal, pp.n_fill, pp.n_skip)


def main() -> int:
    p = argparse.ArgumentParser(description="RSI 극단 전진 페이퍼")
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

    cfg = PaperConfig(slots=a.slots, entry_rsi=a.entry_rsi,
                      tp_pct=a.tp, sl_pct=a.sl, notional_usd=a.notional)
    syms = [s.strip().upper() for s in Path(a.universe).read_text().split()
            if s.strip()]
    log.info("유니버스 %d종목 · 슬롯 %d · RSI<=%g · 익절 %.0f%% / 손절 %.0f%% "
             "· 슬롯당 $%.0f", len(syms), cfg.slots, cfg.entry_rsi,
             100 * cfg.tp_pct, 100 * cfg.sl_pct, cfg.notional_usd)
    pp = RsiPaper(cfg, syms, OUT_DIR)
    pending: list = []

    while True:
        # 봉 마감 직후로 맞춘다 (+40초 여유 — 아카이브가 아니라 REST 라 빠르다)
        now = time.time()
        nxt = (int(now // 3600) + 1) * 3600 + 40
        if not a.once:
            time.sleep(max(5, nxt - now))
        t0 = time.time()
        bars = {}
        for s in syms:
            b = fetch_klines(s, limit=max(300, cfg.warmup_bars + 50))
            if b is not None:
                bars[s] = b
            time.sleep(0.05)          # 레이트리밋 여유
        if len(bars) < len(syms) * 0.8:
            log.warning("시세 %d/%d — 이번 사이클 건너뜀", len(bars), len(syms))
            if a.once:
                return 1
            continue

        opened = pp.open_pending(pending, bars)
        cyc = pp.step(bars)
        pending = cyc["fills"]
        pp.persist(cyc, opened)
        log.info("사이클 %.0fs · 신호 %d · 진입 %d · 청산 %d · 보유 %d/%d · "
                 "누적 $%.2f", time.time() - t0, len(cyc["signals"]),
                 len(opened), len(cyc["exits"]), len(pp.pos), cfg.slots,
                 pp.equity)
        if a.once:
            return 0


if __name__ == "__main__":
    sys.exit(main())
