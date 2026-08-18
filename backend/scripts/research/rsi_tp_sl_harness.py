"""RSI 진입 × 익절 × 손절 — **승률이 문턱에 따라 어떻게 변하나**.

무엇을 묻는가
    대표님 질문: "RSI 진입 조건이 달라짐에 따른 승률 변화."
    그래서 판독의 주축은 **문턱별 승률**이다. 다만 승률만 내면 거짓말이 된다 —
    익절 1% / 손절 5% 면 승률 80% 에 기대값은 음수다. 그래서 승률 옆에
    **거래당 평균**과 **손익비**를 항상 같이 낸다.

⚠ 손익 커널은 **정본 하나**만 쓴다
    `GenericBacktester.run_rule_based`. 새 백테스터를 만들지 않는다 — 그게
    이 저장소에서 손익 구현체 6개 중 4개가 오염된 경로다.

⚠ 방향은 파라미터
    롱(과매도 진입)만 돌리면 국면 효과를 규칙 효과로 읽는다. **같은 문턱의
    거울(숏, 과매수 진입)**을 항상 같이 돌린다 (교훈 #91).

⚠ 파라미터 도달을 증명한다
    `spec_sink` 로 조립된 스펙을 꺼내 설정과 대조한다. 이 저장소에서 "플래그는
    있는데 판정은 하드코딩" 이 세 번 났다 (교훈 #88).

사용:
  python3 -m scripts.research.rsi_tp_sl_harness --selftest
  python3 -m scripts.research.rsi_tp_sl_harness --side both
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rsi_grid")

OUT_DIR = ROOT / "runs" / "research_track" / "rsi_tp_sl"


# ══════════════════════════════════════════════════════════════════════
#  ① 설정은 여기 한 곳에만
# ══════════════════════════════════════════════════════════════════════
@dataclass
class RsiConfig:
    side: str = "long"           # long = 과매도 진입 / short = 과매수 진입
    period: int = 14
    entry_threshold: float = 30.0   # 롱이면 RSI<=이 값, 숏이면 RSI>=100-이 값
    tp_pct: float = 0.03
    sl_pct: float = 0.02
    max_hold_bars: int = 48      # 1h 봉 기준 2일
    placebo: str = ""            # "" | rotate | random  (진입 대조군)
    placebo_seed: int = 0
    signal_lag_bars: int = 1     # 정본 장부 규약 — 신호 봉의 **다음 봉 시가** 체결
    eval_freq_minutes: int = 60

    def __post_init__(self):
        if self.side not in ("long", "short"):
            raise SystemExit(f"side 는 long|short — {self.side!r}")
        if not (0.0 < self.entry_threshold < 100.0):
            raise SystemExit(f"문턱은 (0,100) — {self.entry_threshold!r}")
        if self.tp_pct <= 0 or self.sl_pct <= 0:
            raise SystemExit("익절·손절은 양수여야 한다")

    def pipeline_spec(self) -> dict:
        return {
            "sources": [{"type": "rsi_threshold",
                         "kwargs": {"period": self.period,
                                    "entry_threshold": self.entry_threshold,
                                    "side": self.side,
                                    "placebo": self.placebo,
                                    "placebo_seed": self.placebo_seed}}],
            "composer": {"type": "passthrough",
                         "kwargs": {"feature_col": "rsi_signal"}},
            "policy": {"type": "long_short_threshold",
                       "kwargs": {"entry_threshold": 0.5,
                                  "sl_pct": self.sl_pct,
                                  "tp_pct": self.tp_pct,
                                  "max_hold_bars": self.max_hold_bars}},
        }

    def key(self) -> str:
        pl = self.placebo or "real"
        return (f"{self.side}_p{self.period}_t{self.entry_threshold:g}"
                f"_tp{self.tp_pct:g}_sl{self.sl_pct:g}_h{self.max_hold_bars}_{pl}")


# ══════════════════════════════════════════════════════════════════════
#  ② 파라미터 도달 증명
# ══════════════════════════════════════════════════════════════════════
def verify_reaches(cfg: RsiConfig) -> None:
    from app.composer_framework.pipeline_spec import build_pipeline
    pipe = build_pipeline(cfg.pipeline_spec())
    src = pipe.sources[0]
    checks = [("period", src.period, cfg.period),
              ("entry_threshold", src.entry_threshold, cfg.entry_threshold)]
    bad = [(k, g, w) for k, g, w in checks if abs(float(g) - float(w)) > 1e-9]
    if src.side != cfg.side:
        bad.append(("side", src.side, cfg.side))
    if src.placebo != cfg.placebo:
        bad.append(("placebo", src.placebo, cfg.placebo))
    pol = pipe.policy
    for k, want in (("sl_pct", cfg.sl_pct), ("tp_pct", cfg.tp_pct),
                    ("max_hold_bars", cfg.max_hold_bars)):
        got = getattr(pol, k, None)
        if got is None or abs(float(got) - float(want)) > 1e-9:
            bad.append((k, got, want))
    if bad:
        raise SystemExit(
            "**설정이 스펙에 도달하지 않았다** — 값을 바꿔도 판정이 안 바뀐다:\n"
            + "\n".join(f"  {k}: 스펙={g!r} 설정={w!r}" for k, g, w in bad))
    log.info("✔ 도달 확인 — RSI %d / 문턱 %g / %s / 익절 %.1f%% / 손절 %.1f%% / "
             "보유 %d봉", cfg.period, cfg.entry_threshold, cfg.side,
             100 * cfg.tp_pct, 100 * cfg.sl_pct, cfg.max_hold_bars)


def selftest() -> None:
    """RSI 계산과 문턱·방향이 실제로 신호를 바꾸는지 합성 경로로 확인."""
    from app.composer_framework.signal_source import SourceContext
    from app.composer_framework.sources.rsi_threshold_source import (
        RsiThresholdSource, wilder_rsi)

    # ⓐ 단조 상승이면 RSI 100, 단조 하락이면 0 에 붙어야 한다
    idx = pd.date_range("2024-01-01", periods=400, freq="h")
    up = pd.Series(np.linspace(100, 200, 400), index=idx)
    dn = pd.Series(np.linspace(200, 100, 400), index=idx)
    if not (wilder_rsi(up, 14).iloc[-1] > 99.9):
        raise SystemExit(f"단조 상승 RSI 가 {wilder_rsi(up,14).iloc[-1]:.2f}")
    if not (wilder_rsi(dn, 14).iloc[-1] < 0.1):
        raise SystemExit(f"단조 하락 RSI 가 {wilder_rsi(dn,14).iloc[-1]:.2f}")
    log.info("✔ RSI 계산 확인 — 단조상승 100.0 / 단조하락 0.0")

    # ⓑ 문턱을 낮추면 신호가 **줄어야** 한다 (같은 방향)
    rng = np.random.default_rng(5)
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.006, 3000)))
    ix = pd.date_range("2024-01-01", periods=3000, freq="h")
    bars = pd.DataFrame({"open": px, "high": px * 1.002,
                         "low": px * 0.998, "close": px}, index=ix)
    ctx = SourceContext(symbol="TEST", eval_freq_minutes=60, ohlcv_eval=bars)
    cnt = {}
    for thr in (20.0, 30.0, 40.0):
        f = RsiThresholdSource(14, thr, "long").build_features(ctx)
        cnt[thr] = int((f["rsi_signal"] > 0).sum())
    if not (cnt[20.0] <= cnt[30.0] <= cnt[40.0]) or cnt[20.0] == cnt[40.0]:
        raise SystemExit(f"**문턱이 신호를 안 바꾼다** — {cnt}")
    log.info("✔ 문턱 감응 확인 — 롱 신호 봉수 20:%d ≤ 30:%d ≤ 40:%d",
             cnt[20.0], cnt[30.0], cnt[40.0])

    # ⓒ 방향 — 숏은 부호가 반대여야 하고 롱과 같은 봉에서 켜지면 안 된다
    fl = RsiThresholdSource(14, 30.0, "long").build_features(ctx)["rsi_signal"]
    fs = RsiThresholdSource(14, 30.0, "short").build_features(ctx)["rsi_signal"]
    if fs.max() > 0 or fs.min() >= 0:
        raise SystemExit("숏 신호가 음수가 아니다")
    if int(((fl != 0) & (fs != 0)).sum()) > 0:
        raise SystemExit("롱·숏 신호가 같은 봉에서 동시에 켜졌다")
    log.info("✔ 방향 확인 — 롱 %d봉 / 숏 %d봉 · 겹침 0",
             int((fl != 0).sum()), int((fs != 0).sum()))

    # ⓓ 데이터 결손은 조용한 0 이 아니라 예외여야 한다
    from app.composer_framework.signal_source import InsufficientSourceDataError
    short_ctx = SourceContext(symbol="TEST", eval_freq_minutes=60,
                              ohlcv_eval=bars.iloc[:30])
    try:
        RsiThresholdSource(14, 30.0, "long").build_features(short_ctx)
    except InsufficientSourceDataError:
        log.info("✔ 결손 처리 확인 — 봉 부족 시 조용한 0 대신 예외")
    else:
        raise SystemExit("**봉이 모자란데 예외가 안 났다** — 조용한 0 신호 위험")

    # ⓔ 위약 — **진입 횟수가 보존되고, 시점은 달라져야** 한다.
    #   횟수가 달라지면 "거래를 덜 해서 좋아진 것"과 구별이 안 된다.
    base = RsiThresholdSource(14, 30.0, "long").build_features(ctx)["rsi_signal"]
    n_base = int((base != 0).sum())
    for pl in ("rotate", "random"):
        f = RsiThresholdSource(14, 30.0, "long", placebo=pl,
                               placebo_seed=7).build_features(ctx)["rsi_signal"]
        n_pl = int((f != 0).sum())
        same = int(((base != 0) & (f != 0)).sum())
        if pl == "random" and n_pl != n_base:
            raise SystemExit(f"random 위약이 횟수를 안 지켰다 {n_base}→{n_pl}")
        if pl == "rotate" and not (0.5 * n_base <= n_pl <= n_base):
            # 앞쪽 k 개를 지우므로 조금 줄어드는 것은 정상이다
            raise SystemExit(f"rotate 위약 횟수가 이상하다 {n_base}→{n_pl}")
        if n_base and same / n_base > 0.5:
            raise SystemExit(
                f"**{pl} 위약이 실측과 {100*same/n_base:.0f}% 겹친다** — "
                f"시점이 안 흔들렸다")
        log.info("✔ 위약 %s 확인 — 진입 %d→%d봉 · 실측과 겹침 %d (%.1f%%)",
                 pl, n_base, n_pl, same, 100 * same / max(n_base, 1))

    verify_reaches(RsiConfig(side="short", period=7, entry_threshold=25,
                             tp_pct=0.05, sl_pct=0.01, max_hold_bars=12))
    verify_reaches(RsiConfig(side="long", entry_threshold=20, placebo="rotate"))
    log.info("✔ 자기검사 통과")


# ══════════════════════════════════════════════════════════════════════
#  기질
# ══════════════════════════════════════════════════════════════════════
TF_TABLE = {"1h": "ohlcv_hourly", "15m": "ohlcv_15m", "5m": "ohlcv_5m"}
TF_MIN = {"1h": 60, "15m": 15, "5m": 5}


def load_panel(min_bars: int, limit: int = 0, symbols: str = "",
               start: str = "", end: str = "", tf: str = "1h") -> dict:
    from sqlalchemy import text
    from app.db.session import engine
    table = TF_TABLE[tf]
    log.info("%s 적재 …", table)
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT symbol, ts, open, high, low, close, volume FROM "
            f"{table} ORDER BY symbol, ts")).fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "ts", "open", "high", "low",
                                     "close", "volume"])
    want = {s.strip().upper() for s in symbols.split(",") if s.strip()}
    out = {}
    for sym, g in df.groupby("symbol", sort=True):
        if want and sym not in want:
            continue
        g = g.drop_duplicates("ts").sort_values("ts")
        if len(g) < min_bars:
            continue
        b = g[["ts", "open", "high", "low", "close", "volume"]].copy()
        b["ts"] = pd.to_datetime(b["ts"])
        # ⚠ 구간을 자른 뒤 RSI 워밍업이 다시 필요하다. 소스가 `period*5` 봉을
        #   요구하므로 시작 **이전** 여유분을 남겨 자르고, 진입은 커널이 알아서
        #   워밍업 이후부터 낸다. 구간을 칼같이 자르면 앞 70봉이 죽는다.
        if start:
            lo = pd.Timestamp(start) - pd.Timedelta(minutes=200 * TF_MIN[tf])
            b = b[b["ts"] >= lo]
        if end:
            b = b[b["ts"] < pd.Timestamp(end)]
        if len(b) < min_bars:
            continue
        out[sym] = b.set_index("ts")
    if limit:
        out = {k: out[k] for k in sorted(out)[:limit]}
    log.info("적재 완료 — %d종목 · 총 %s봉", len(out),
             f"{sum(len(v) for v in out.values()):,}")
    return out


def run_symbol(cfgs: list, sym: str, bars: pd.DataFrame,
               dump_trades: bool = False) -> list:
    """한 종목을 워커로 **한 번만** 보내고 그 안에서 설정을 전부 돈다."""
    return [run_one(c, sym, bars, dump_trades) for c in cfgs]


def run_one(cfg: RsiConfig, sym: str, bars: pd.DataFrame,
            dump_trades: bool = False) -> dict:
    """⑤ 정본 커널 **단일 경로**."""
    from app.composer_framework.backtester import GenericBacktester
    from app.composer_framework.pipeline_spec import build_pipeline
    from app.composer_framework.signal_source import (
        InsufficientSourceDataError, SourceContext)

    pipe = build_pipeline(cfg.pipeline_spec())
    ctx = SourceContext(symbol=sym, eval_freq_minutes=cfg.eval_freq_minutes,
                        ohlcv_eval=bars)
    try:
        kpi = GenericBacktester().run_rule_based(
            pipeline=pipe, ctx=ctx, signal_lag_bars=cfg.signal_lag_bars)
    except InsufficientSourceDataError as e:
        return {"symbol": sym, "error": str(e)}
    tr = getattr(kpi, "trades", None)
    d = {"symbol": sym}
    for f in ("total_trades", "win_rate", "total_return_pct", "sharpe",
              "max_drawdown_pct", "avg_trade_pct", "profit_factor"):
        d[f] = getattr(kpi, f, np.nan)
    if tr is not None and len(tr):
        t = pd.DataFrame(tr) if not isinstance(tr, pd.DataFrame) else tr
        col = next((c for c in ("pnl_pct", "return_pct", "pct", "ret")
                    if c in t.columns), None)
        if col:
            r = t[col].astype(float)
            # 정책이 % 로 주는지 소수로 주는지 판본마다 다르다 — 크기로 가른다
            if r.abs().median() > 1.0:
                r = r / 100.0
            w, l = r[r > 0], r[r < 0]
            d.update({
                "n_trades": int(len(r)),
                "win_rate_calc": 100.0 * float((r > 0).mean()),
                "avg_pct": 100.0 * float(r.mean()),
                "med_pct": 100.0 * float(r.median()),
                "avg_win": 100.0 * float(w.mean()) if len(w) else np.nan,
                "avg_loss": 100.0 * float(l.mean()) if len(l) else np.nan,
                "payoff": float(w.mean() / abs(l.mean()))
                          if len(w) and len(l) and l.mean() != 0 else np.nan,
                "sum_pct": 100.0 * float(r.sum()),
            })
            # ⚠ 상위 거래 절삭 검정(교훈 #81)은 **거래별** 손익이 있어야 한다.
            #   집계만 저장하면 "상위 10건이 전부였는가"를 영영 못 묻는다.
            if dump_trades:
                d["trades_pct"] = ",".join(f"{x:.6f}" for x in (100.0 * r))
                # ⚠ 포트폴리오는 **언제** 자본이 묶이는지를 알아야 한다.
                #   손익만 있으면 동시 포지션 수도 유휴 자본도 못 센다.
                keep = [c for c in ("entry_ts", "exit_ts", "entry_price",
                                    "exit_price", "exit_reason") if c in t.columns]
                tt = t[keep].copy()
                tt["ret_pct"] = 100.0 * r.to_numpy()
                tt["symbol"] = sym
                d["_trades"] = tt.to_dict("records")
    return d


def _partial(rows, a) -> None:
    """부분 저장. 끝에 한 번에 쓰면 중간에 죽을 때 전부 잃는다 (실측 5시간)."""
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(
            OUT_DIR / f"partial_{a.tag or 'run'}.csv", index=False)
    except Exception as e:                       # 저장 실패가 실행을 죽이면 안 된다
        log.warning("부분 저장 실패: %s", e)


def main() -> int:
    p = argparse.ArgumentParser(description="RSI × 익절 × 손절 격자")
    p.add_argument("--side", default="both", choices=["long", "short", "both"])
    p.add_argument("--periods", default="14")
    p.add_argument("--thresholds", default="15,20,25,30,35,40,45,50")
    p.add_argument("--tps", default="0.01,0.02,0.03,0.05")
    p.add_argument("--sls", default="0.01,0.02,0.03,0.05")
    p.add_argument("--hold", type=int, default=48)
    p.add_argument("--min-bars", type=int, default=8760)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--symbols", default="")
    p.add_argument("--tf", default="1h", choices=["1h", "15m", "5m"],
                   help="시간대. 보유상한(--hold)은 **봉 수**이니 같이 바꿔라")
    p.add_argument("--start", default="", help="구간 시작 YYYY-MM-DD (포함)")
    p.add_argument("--end", default="", help="구간 끝 YYYY-MM-DD (미포함)")
    p.add_argument("--placebos", default="real",
                   help="real,rotate,random — 진입 대조군 축")
    p.add_argument("--seed", type=int, default=20260816)
    p.add_argument("--dump-trades", action="store_true",
                   help="거래별 손익을 실어 저장 (상위 절삭 검정용)")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--tag", default="")
    a = p.parse_args()

    selftest()
    if a.selftest:
        return 0

    sides = ["long", "short"] if a.side == "both" else [a.side]
    placebos = [x.strip() for x in a.placebos.split(",")]
    placebos = ["" if x in ("real", "none", "") else x for x in placebos]
    grid = [RsiConfig(side=s, period=int(pp), entry_threshold=float(t),
                      tp_pct=float(tp), sl_pct=float(sl), max_hold_bars=a.hold,
                      placebo=pl, placebo_seed=a.seed,
                      eval_freq_minutes=TF_MIN[a.tf])
            for s in sides
            for pp in a.periods.split(",")
            for t in a.thresholds.split(",")
            for tp in a.tps.split(",")
            for sl in a.sls.split(",")
            for pl in placebos]
    verify_reaches(grid[0])
    log.info("격자 %d칸", len(grid))

    panel = load_panel(a.min_bars, a.limit, a.symbols, a.start, a.end, a.tf)
    if not panel:
        log.error("종목이 없다")
        return 1

    # 한 실행이 3.5초라 격자 전체는 순차로 몇 시간이다. 코어로 나눈다.
    # ⚠ 병렬화가 결과를 바꾸면 안 된다 — 각 작업은 완전히 독립이고 공유 상태가
    #   없다. 순차판과 대조하는 `--check-parallel` 을 둔다.
    jobs = sorted(panel)                      # 작업 = 종목
    log.info("작업 %d종목 × 설정 %d = %d실행 · 워커 %d",
             len(jobs), len(grid), len(jobs) * len(grid), a.workers)
    rows, t0 = [], datetime.now()

    trade_rows: list = []

    def tag(cfg, r):
        for tr in r.pop("_trades", []):
            tr.update({"key": cfg.key(), "side": cfg.side, "thr": cfg.entry_threshold,
                       "tp": cfg.tp_pct, "sl": cfg.sl_pct,
                       "placebo": cfg.placebo or "real"})
            trade_rows.append(tr)
        r.update({"side": cfg.side, "period": cfg.period,
                  "thr": cfg.entry_threshold, "tp": cfg.tp_pct,
                  "sl": cfg.sl_pct, "hold": cfg.max_hold_bars,
                  "key": cfg.key()})
        return r

    def _collect(res):
        for cfg, r in zip(grid, res):
            rows.append(tag(cfg, r))

    if a.workers <= 1:
        for i, sym in enumerate(jobs, 1):
            _collect(run_symbol(grid, sym, panel[sym], a.dump_trades))
            if i % 5 == 0:
                log.info("[%d/%d종목] %.0f초", i, len(jobs),
                         (datetime.now() - t0).total_seconds())
                _partial(rows, a)
    else:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            fut = {ex.submit(run_symbol, grid, s_, panel[s_], a.dump_trades): s_
                   for s_ in jobs}
            for i, f in enumerate(as_completed(fut), 1):
                _collect(f.result())
                if i % 5 == 0:
                    log.info("[%d/%d종목] %.0f초", i, len(jobs),
                             (datetime.now() - t0).total_seconds())
                    _partial(rows, a)

    P = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    span = f"_{a.start or 'beg'}_{a.end or 'end'}" if (a.start or a.end) else ""
    stem = f"{'_'.join(sides)}_{a.tf}_h{a.hold}{span}" + (f"_{a.tag}" if a.tag else "")
    P.to_csv(OUT_DIR / f"persym_{stem}.csv", index=False)
    if trade_rows:
        pd.DataFrame(trade_rows).to_csv(OUT_DIR / f"trades_{stem}.csv", index=False)
        log.info("거래 덤프 %s행 저장", f"{len(trade_rows):,}")

    G = ["side", "period", "thr", "tp", "sl"]
    agg = (P[P.n_trades.notna()].groupby(G)
           .agg(n_sym=("symbol", "nunique"), trades=("n_trades", "sum"),
                win_rate=("win_rate_calc", "median"),
                avg_pct=("avg_pct", "median"), payoff=("payoff", "median"),
                sum_pct=("sum_pct", "median"),
                pos_sym=("sum_pct", lambda x: 100.0 * float((x > 0).mean())))
           .reset_index())
    agg.to_csv(OUT_DIR / f"agg_{stem}.csv", index=False)
    with open(OUT_DIR / f"meta_{stem}.json", "w") as fh:
        json.dump({"args": vars(a), "n_symbols": len(panel),
                   "grid": len(grid), "config_template": asdict(grid[0]),
                   "generated": datetime.now().isoformat()},
                  fh, indent=2, ensure_ascii=False)
    log.info("저장: %s", OUT_DIR / f"agg_{stem}.csv")
    print(f"\n격자 {len(agg)}칸 · 종목 {len(panel)} · 총 거래 "
          f"{int(agg.trades.sum()):,} — 판독은 rsi_tp_sl_report 로")
    return 0


if __name__ == "__main__":
    sys.exit(main())
