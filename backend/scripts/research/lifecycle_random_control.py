"""신상저격수 **랜덤 종목 대조군** — "신규 상장이라는 조건"이 실제로 기여하는가.

묻는 것
    같은 규칙(진입 24h 뒤 숏 · 보유 30일 · 손절/익절)을 **신규 상장이 아닌
    기성 종목**에 적용하면 어떻게 되는가. 대조군이 관측을 이기면 수익원은
    상장 사건이 아니라 그 시기 알트코인 전반의 드리프트다.

⚠ 이미 한 번 답이 나왔던 질문이다 (2026-08-14 `lifecycle_placebo2.json`)
    실거래 설정(일봉 · 손절50 · 익절없음)에서 신규 2.44 vs 기성 **4.82**
    = **197%**. 대조군이 두 배 가까이 이겼다.
    그런데 그 판정에는 두 가지 한계가 있었다:

      ① **대조 종목을 한 벌만** 뽑았다 (`sum(ord(c))` 로 결정적 선택).
         한 벌은 점 추정이다. "기성 종목을 랜덤으로 뽑으면 보통 얼마인가"라는
         **분포**를 모르면 197% 가 흔한 일인지 극단인지 알 수 없다.
      ② **일봉 · 옛 실거래 설정**이었다. 지금 실거래는 **1h 손절50/익절50**
         이다. 설정이 바뀌었으면 대조도 다시 재야 한다.

    이 스크립트는 둘 다 고친다 — 랜덤 추출을 **R벌 반복**해 귀무 분포를
    만들고, 일봉/1h 두 해상도를 같은 코드로 돌린다.

⚠ 랜덤은 두 가지가 있고 **결론이 갈린다**
    `matched`  같은 **날짜**에 기성 종목을 랜덤 추출. 시장 국면이 고정되므로
               남는 차이는 "신규 상장인가"뿐이다. ← **이게 대조군이다**
    `free`     날짜도 랜덤. 국면이 섞여 "상장이 몰린 시기"와 비교가 깨진다.
               참고용으로만 낸다 — 이걸 근거로 판정하면 안 된다.

⚠ 새 손익 구현을 만들지 않는다
    `GenericBacktester.run_rule_based` 를 그대로 쓴다. 손익 구현체를 하나 더
    만드는 순간 정본 밖으로 나간다 — 그게 [[project-canon-backtest-unification]]
    에서 6개 중 4개가 오염됐던 이유다. 관측·대조가 **같은 함수**를 탄다.

⚠ 진입 바 손절 무력화는 두 팔에서 **비대칭**이다
    커널은 미래참조를 피하려고 진입 바에서 손절을 보지 않는다(옳다). 그런데
    상장 첫날 바의 진폭은 일봉 p50 **32.7%** 이고 기성 종목은 그 근처도 안 된다.
    즉 **일봉 대조는 관측 쪽 손절만 더 자주 지운다.** 그래서 두 팔의 무력화율을
    같이 낸다 — 벌어져 있으면 그 해상도의 비교는 그만큼 못 믿는다.
    1h 로 내리면 이 비대칭이 크게 줄어든다(손절50 기준 무력화 ~0%).

사용:
  python3 -m scripts.research.lifecycle_random_control --res 1d --draws 30
  python3 -m scripts.research.lifecycle_random_control --res 1h --draws 30 \
      --specs "0.50/0.50"
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lc_rand")

LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT = ROOT / "runs" / "research_track" / "lifecycle_random_control.json"

HOLD_DAYS = 30
# 1h 는 상장+23시부터 자른다 → 신호지연 1봉 뒤 체결이 상장+24h 가 되어
# 일봉판(bar[0]=상장일 → bar[1] 시가)과 **같은 시각**에 들어간다.
# 이걸 안 맞추면 해상도가 아니라 다른 전략을 비교하게 된다.
ENTRY_OFFSET_H = 23

# 대조 종목 자격 — 관측 코호트 시작(2025-01-01)보다 최소 180일 앞서 상장.
# `lifecycle_optimize.CONTROL_MIN_AGE_DAYS` 와 같은 기준이다.
CONTROL_LISTED_BEFORE = "2024-07-01"
# 유동성 게이트 — 교훈 #78. 자동 구성 코호트는 이 필터 없이는 부호가 뒤집힌다.
# ⚠ 다만 이건 **대조군에만** 걸린다. 신규 상장은 유동성이 낮은 게 정상이므로
#   같은 기준을 관측에 걸면 코호트가 사라진다. 비대칭을 알고 쓴다.
CONTROL_MIN_ADV = 3e6
CONTROL_MIN_DAYS = 500


def load_daily(conn, syms: list[str]) -> dict[str, pd.DataFrame]:
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT symbol, date, open, high, low, close, volume FROM ohlcv_daily "
        "WHERE symbol = ANY(:s) ORDER BY symbol, date"), {"s": syms}).fetchall()
    df = pd.DataFrame(r, columns=["symbol", "ts", "open", "high", "low",
                                  "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return {s: g.set_index("ts")[["open", "high", "low", "close", "volume"]]
            for s, g in df.groupby("symbol")}


def load_hourly(conn, syms: list[str]) -> dict[str, pd.DataFrame]:
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT symbol, ts, open, high, low, close, volume FROM ohlcv_hourly "
        "WHERE symbol = ANY(:s) ORDER BY symbol, ts"), {"s": syms}).fetchall()
    df = pd.DataFrame(r, columns=["symbol", "ts", "open", "high", "low",
                                  "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return {s: g.set_index("ts")[["open", "high", "low", "close", "volume"]]
            for s, g in df.groupby("symbol")}


def segment(bars: pd.DataFrame, anchor: pd.Timestamp, res: str,
            min_bars: int) -> pd.DataFrame | None:
    """앵커부터 보유기간+여유만큼 자른다. 부족하면 None."""
    end = anchor + pd.Timedelta(days=HOLD_DAYS + 2)
    seg = bars.loc[(bars.index >= anchor) & (bars.index <= end)]
    if len(seg) < min_bars:
        return None
    # ⚠ 앵커 바가 실제로 그 시각이어야 한다. 결손으로 며칠 뒤 바가 첫 봉이
    #   되면 "상장 24h 뒤 진입"이 아닌 다른 시점을 재게 된다.
    gap = (seg.index[0] - anchor).total_seconds()
    if gap > (26 * 3600 if res == "1d" else 2 * 3600):
        return None
    return seg


def run_event(symbol: str, seg: pd.DataFrame, sl: float, tp: float | None,
              res: str, lag: int):
    """정본 커널 한 번. 관측·대조가 **같은 이 함수**를 탄다."""
    from app.composer_framework.backtester import GenericBacktester
    from app.composer_framework.pipeline_spec import build_pipeline
    from app.composer_framework.signal_source import SourceContext

    freq = 1440 if res == "1d" else 60
    hold_bars = HOLD_DAYS if res == "1d" else HOLD_DAYS * 24
    ps = {
        "sources": [{"type": "bn_lifecycle_decay",
                     "kwargs": {"listing_date": str(seg.index[0]),
                                "max_age_days": HOLD_DAYS,
                                # 0 = 진입창이 첫 봉에서 닫힌다 → **사건당 1거래**.
                                # 1 로 두면 손절 후 재진입해 사건당 거래 수가
                                # 팔마다 달라지고 평균 비교가 깨진다.
                                "entry_window_days": 0}}],
        "composer": {"type": "passthrough",
                     "kwargs": {"feature_col": "bnld_signal", "scale": 1.0}},
        "policy": {"type": "long_short_threshold",
                   "kwargs": {"entry_threshold": 0.5, "sl_pct": sl,
                              "tp_pct": (1.0 if tp is None else tp),
                              "max_hold_bars": hold_bars}},
        "config": {"eval_freq_minutes": freq, "forward_bars": hold_bars},
    }
    ctx = SourceContext(symbol=symbol, eval_freq_minutes=freq,
                        ohlcv_1m=None, ohlcv_eval=seg)
    bt = GenericBacktester(initial_capital=1_000_000.0, fee_rate=0.0005,
                           apply_fee_to_short=True)
    return bt.run_rule_based(pipeline=build_pipeline(ps, {}), ctx=ctx,
                             signal_lag_bars=lag).trades


def fill_bar_range(seg: pd.DataFrame, lag: int) -> float | None:
    """체결 바의 저가→고가 상승폭. 이 값이 손절폭보다 크면 그 손절은 기록되지
    않는다(커널이 진입 바에서 손절을 안 보기 때문). 팔별로 이걸 비교해야
    "무력화 비대칭"을 알 수 있다."""
    if len(seg) <= lag:
        return None
    b = seg.iloc[lag]
    if not (b["low"] > 0):
        return None
    return float(b["high"] / b["low"] - 1.0)


def agg(rets: list[float]) -> dict:
    a = np.asarray(rets, dtype=float)
    if len(a) < 2:
        return {"n": int(len(a))}
    se = a.std(ddof=1) / np.sqrt(len(a))
    return {"n": int(len(a)), "mean": float(a.mean()),
            "med": float(np.median(a)), "win": float(100 * (a > 0).mean()),
            "t": float(a.mean() / se) if se else None,
            "worst": float(a.min()), "best": float(a.max()),
            "total": float(a.sum())}


def main() -> int:
    p = argparse.ArgumentParser(description="신상저격수 랜덤 종목 대조군")
    p.add_argument("--res", choices=["1d", "1h"], default="1d")
    p.add_argument("--since", default="2025-01-01", help="관측 코호트 상장일 하한")
    p.add_argument("--draws", type=int, default=30, help="랜덤 추출 반복 횟수")
    p.add_argument("--specs", default="0.50/0.50,0.50/none,0.20/none",
                   help="손절/익절 쉼표 구분. 익절 none = 없음")
    p.add_argument("--seed", type=int, default=20260815)
    p.add_argument("--exec-lag", type=int, default=1,
                   help="신호지연 봉수. 두 팔에 **동일 적용**되므로 비교에는 "
                        "영향이 없다. 1 = 정본 장부 규약")
    p.add_argument("--free", action="store_true",
                   help="날짜까지 랜덤인 변형도 함께 낸다(참고용)")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default="")
    a = p.parse_args()

    min_bars = 20 if a.res == "1d" else 24 * 5
    listings = json.loads(LISTINGS.read_text())

    # ── 관측 코호트 · 대조 풀 ─────────────────────────────────────────
    cohort_syms = sorted(k for k, m in listings.items()
                         if isinstance(m, dict) and m.get("onboard_date")
                         and m["onboard_date"] >= a.since)
    pool_cand = sorted(k for k, m in listings.items()
                       if isinstance(m, dict) and m.get("onboard_date")
                       and m["onboard_date"] <= CONTROL_LISTED_BEFORE)

    from sqlalchemy import text

    from app.db.session import engine
    with engine.connect() as conn:
        liq = {r[0]: (r[1], float(r[2] or 0)) for r in conn.execute(text(
            "SELECT symbol, count(*), avg(close*volume) FROM ohlcv_daily "
            "WHERE date >= :d GROUP BY symbol"), {"d": a.since}).fetchall()}
        pool = [s for s in pool_cand
                if liq.get(s, (0, 0))[0] >= CONTROL_MIN_DAYS
                and liq.get(s, (0, 0))[1] >= CONTROL_MIN_ADV]
        log.info("관측 후보 %d상장 · 대조 풀 %d종목 (유동성 게이트 통과)",
                 len(cohort_syms), len(pool))
        loader = load_daily if a.res == "1d" else load_hourly
        t0 = time.time()
        bars = loader(conn, cohort_syms + pool)
        log.info("봉 적재 %d종목 · %.0f초", len(bars), time.time() - t0)

    # ── 사건 목록 (관측) ──────────────────────────────────────────────
    events = []
    for s in cohort_syms:
        b = bars.get(s)
        if b is None:
            continue
        ld = pd.Timestamp(datetime.strptime(listings[s]["onboard_date"],
                                            "%Y-%m-%d"))
        anchor = ld if a.res == "1d" else ld + pd.Timedelta(hours=ENTRY_OFFSET_H)
        seg = segment(b, anchor, a.res, min_bars)
        if seg is None:
            continue
        events.append({"symbol": s, "listing": listings[s]["onboard_date"],
                       "anchor": anchor, "seg": seg})
    if a.limit:
        events = events[:a.limit]
    if not events:
        raise SystemExit("코호트가 비었다 — 봉 적재를 확인하라")
    log.info("관측 사건 %d건 (봉 부족 %d건 탈락)",
             len(events), len(cohort_syms) - len(events))

    # 사건별로 그 날짜에 쓸 수 있는 대조 종목을 미리 가려낸다.
    # ⚠ 잘라낸 **구간은 캐시하지 않는다** — 1h 에서 사건 327 × 풀 85 × 720봉이면
    #   수백 MB 다. 자격만 기억하고 추출 때 그때그때 자른다(슬라이싱은 싸다).
    t0 = time.time()
    avail: list[list[str]] = []
    for e in events:
        avail.append([s for s in pool
                      if bars.get(s) is not None
                      and segment(bars[s], e["anchor"], a.res, min_bars) is not None])
    log.info("대조 구간 사전 계산 %.0f초 · 사건당 사용가능 중앙값 %d종목",
             time.time() - t0, int(np.median([len(x) for x in avail])))

    specs = []
    for sp in a.specs.split(","):
        s_, t_ = sp.strip().split("/")
        specs.append((float(s_), None if t_.lower() == "none" else float(t_)))

    rng = np.random.default_rng(a.seed)
    # free 변형용 — 코호트 달력 범위 안에서 앵커를 랜덤 추출
    anchors_all = sorted({e["anchor"] for e in events})

    res_out: dict = {}
    print("=" * 104)
    print(f"신상저격수 **랜덤 종목 대조군** — 해상도 {a.res} · 관측 {len(events)}사건"
          f" · 대조 풀 {len(pool)}종목 · 랜덤 {a.draws}벌 · 신호지연 {a.exec_lag}봉")
    print("  대조 = **같은 날짜**에 기성 종목(2024-07-01 이전 상장·ADV≥$3M)을 "
          "랜덤 추출 → 같은 규칙·같은 커널")
    print("=" * 104)

    for sl, tp in specs:
        tag = f"sl{sl:.2f}/tp{'none' if tp is None else f'{tp:.2f}'}"
        # ── 관측 ──────────────────────────────────────────────────────
        obs, obs_null = [], 0
        for e in events:
            try:
                tr = run_event(e["symbol"], e["seg"], sl, tp, a.res, a.exec_lag)
            except Exception as exc:
                log.warning("%s 관측 실패: %s", e["symbol"], exc)
                continue
            for t in (tr or []):
                obs.append(float(t.return_pct) * 100)
            r = fill_bar_range(e["seg"], a.exec_lag)
            if r is not None and r > sl:
                obs_null += 1
        o = agg(obs)

        # ── 대조 랜덤 R벌 ─────────────────────────────────────────────
        draw_stats, ctl_all, ctl_null, ctl_n = [], [], 0, 0
        for d in range(a.draws):
            rets = []
            for e, ok in zip(events, avail):
                if not ok:
                    continue
                s = ok[int(rng.integers(len(ok)))]
                sg = segment(bars[s], e["anchor"], a.res, min_bars)
                if sg is None:
                    continue
                try:
                    tr = run_event(s, sg, sl, tp, a.res, a.exec_lag)
                except Exception:
                    continue
                for t in (tr or []):
                    rets.append(float(t.return_pct) * 100)
                r = fill_bar_range(sg, a.exec_lag)
                if r is not None and r > sl:
                    ctl_null += 1
                ctl_n += 1
            if len(rets) >= 2:
                draw_stats.append(agg(rets))
                ctl_all.extend(rets)
        means = np.array([d["mean"] for d in draw_stats])
        # 관측이 대조 분포 어디에 있나. 숏 전략이므로 "관측이 더 크면 좋다".
        p_ge = float((means >= o.get("mean", -1e9)).mean()) if len(means) else None

        res_out[tag] = {"obs": o, "control_pooled": agg(ctl_all),
                        "draw_means": means.tolist(),
                        "p_control_ge_obs": p_ge,
                        "obs_sl_nullified_pct": 100 * obs_null / max(1, len(events)),
                        "ctl_sl_nullified_pct": 100 * ctl_null / max(1, ctl_n)}

        tpl = "없음" if tp is None else f"{tp:.0%}"
        print(f"\n  ── 손절 {sl:.0%} · 익절 {tpl} " + "─" * 60)
        print(f"     {'':10}{'거래':>7}{'평균%':>9}{'중앙%':>9}{'승률%':>8}"
              f"{'t':>7}{'최악%':>9}{'합계%':>10}")
        print(f"     {'관측(신규)':10}{o.get('n',0):>7}{o.get('mean',np.nan):>9.2f}"
              f"{o.get('med',np.nan):>9.2f}{o.get('win',np.nan):>8.1f}"
              f"{(o.get('t') or 0):>7.2f}{o.get('worst',np.nan):>9.1f}"
              f"{o.get('total',np.nan):>10.0f}")
        if len(means):
            cp = agg(ctl_all)
            print(f"     {'대조(랜덤)':10}{cp.get('n',0):>7}{cp.get('mean',np.nan):>9.2f}"
                  f"{cp.get('med',np.nan):>9.2f}{cp.get('win',np.nan):>8.1f}"
                  f"{(cp.get('t') or 0):>7.2f}{cp.get('worst',np.nan):>9.1f}"
                  f"{cp.get('total',np.nan):>10.0f}   ← {a.draws}벌 합산")
            q = np.percentile(means, [5, 25, 50, 75, 95])
            print(f"     대조 {a.draws}벌 평균 분포  p5 {q[0]:+.2f} · p25 {q[1]:+.2f}"
                  f" · **중앙 {q[2]:+.2f}** · p75 {q[3]:+.2f} · p95 {q[4]:+.2f}")
            print(f"     관측이 대조 분포에서 차지하는 위치 — 대조가 관측 이상일 확률"
                  f" **p {p_ge:.3f}**")
            ratio = (q[2] / o["mean"] * 100) if o.get("mean") else float("nan")
            print(f"     대조 중앙 / 관측 = **{ratio:.0f}%**")
        print(f"     손절 무력화(체결 바 진폭 > 손절폭) — 관측 "
              f"{res_out[tag]['obs_sl_nullified_pct']:.1f}% vs 대조 "
              f"{res_out[tag]['ctl_sl_nullified_pct']:.1f}%")

    print("\n" + "=" * 104)
    print("  읽는 법")
    print("    · **p 가 크면 대조가 관측을 자주 이긴다** = 신규 상장이라는 조건이")
    print("      기여하지 않는다는 뜻이다. p 0.5 근처면 동전던지기다.")
    print("    · 무력화율이 두 팔에서 크게 벌어지면 그 해상도의 비교는 그만큼")
    print("      못 믿는다 — 관측 쪽 손절만 더 자주 지워지기 때문이다.")
    out = a.out or str(OUT).replace(".json", f"_{a.res}.json")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(
        {"params": vars(a), "n_events": len(events), "pool": pool,
         "results": res_out}, ensure_ascii=False, indent=2, default=str))
    print(f"  → {out}")
    print("=" * 104)
    return 0


if __name__ == "__main__":
    sys.exit(main())
