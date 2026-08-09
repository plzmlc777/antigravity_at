"""Binance Futures aggTrades 일 아카이브 → 1분 마이크로구조 피처.

URL: data.binance.vision/data/futures/um/daily/aggTrades/{SYM}/{SYM}-aggTrades-YYYY-MM-DD.zip
원본 컬럼: agg_trade_id, price, quantity, first_trade_id, last_trade_id,
           transact_time(ms), is_buyer_maker
  `is_buyer_maker=true`  → 매수자가 메이커 → **테이커가 매도**(공격적 매도)
  `is_buyer_maker=false` → 매도자가 메이커 → **테이커가 매수**(공격적 매수)

왜 이 substrate 인가 (2026-08-09, 초단기 트랙 설계):
  1분봉 OHLCV 에는 **주문 흐름 방향**이 없다. aggTrades 에는 체결마다 테이커
  방향이 붙어 있어 CVD·주문흐름 불균형·대형체결 편향을 과거로 소급 계산할 수 있다.
  캠페인 graveyard 에 "aggTrades backfill 후 재시도 가치 있음"(wick_reversal)이
  적혀 있으나 레포가 한 번도 손대지 않은 축이다.

  그리고 결정적으로 **유효 스프레드(effective spread)를 과거로 추정**할 수 있다.
  초단기 판정의 마찰 관문(U2 `spread_headroom`)은 분모가 실제 스프레드여야 하는데,
  Binance 의 bookTicker 아카이브는 **2024-03-30 에 중단**됐다(2026-08-09 실측:
  이후 전 날짜 404). 즉 최근 구간의 실제 호가는 과거로 소급해 얻을 방법이 없고,
  WS 로 오늘부터 모으는 수밖에 없다. 그 공백을 이 추정치가 메운다.

추정 원리:
  같은 1분 안에서 테이커 매수는 ask 에, 테이커 매도는 bid 에 체결된다. 따라서
      eff_spread ≈ VWAP(테이커 매수) - VWAP(테이커 매도)
  가 스프레드 한 폭에 대응한다. 분(分) 안에서 가격이 추세를 타면 오염되므로
  **추정치를 그대로 저장하지 않고 `vwap_buy`/`vwap_sell` 원재료를 함께 남긴다** —
  나중에 WS 실측이 쌓이면 편향을 교정하고 추정식을 갈아끼울 수 있어야 한다.

  실측 검증 (WIFUSDT 2026-08-03~05, 4320분):
    틱사이즈 0.0001 @ 가격 0.1403 = 7.13bp/틱
    추정 스프레드  중앙값 4.75bp(0.67틱) / 75분위 7.12bp(1.00틱) / 95분위 7.70bp
  1틱 근처에서 상한이 걸린다 — 유동성 좋은 perp 가 대부분 최소 스프레드에 붙어
  있는 실제 모습과 일치한다. 다만 분 단위 표준편차가 3.4bp 이고 5% 는 음수다
  (분 안 추세 오염). **분 단위로 거칠고 창 단위로 정밀한** 지표이므로 U2 처럼
  K일 창에서 집계해 쓴다 — 14일 창이면 표준오차 0.02bp 로 무의미해진다.
  분 단위 값을 단독 조건으로 쓰지 말 것.

  **추정기의 하한 (2026-08-09 13종목 180일 실측에서 드러난 결함)**:
    FIL 3.78 / NEAR 3.09 / WIF 2.27 / ADA 2.10  (중앙값 bp — 정상)
    BNB -0.14 / ETH -0.12 / BCH -0.09           (음수 — 붕괴)
  ETH 는 가격이 높아 1틱이 0.03bp 라 **진짜 스프레드가 분 안 가격흐름 노이즈보다
  훨씬 작다.** 그러면 추정치가 0 근처 노이즈가 되고 중앙값이 음수로 내려간다.
  즉 이 추정기는 틱이 노이즈보다 클 때만 작동한다. 음수를 그대로 두면 U2 의
  `spread_headroom = 순엣지 ÷ 스프레드` 가 음수로 나눠져 깨진다.

  → **물리적 하한을 씌운다. 스프레드는 1틱 미만일 수 없다.**
     `eff_spread_bp_adj = max(eff_spread_bp, tick_bp)`
  틱사이즈는 추정하지 않고 `/fapi/v1/exchangeInfo` PRICE_FILTER 에서 받는다.
  원본 `eff_spread_bp` 도 함께 남긴다 — 나중에 WS 실측으로 교정할 때 필요하다.

처리: 다운로드 → 1분 집계 → 저장 → **원본 폐기**. 원본을 남기면 전 유니버스
1년치가 수백 GB 라 유지 불가능하다(backfill_book_depth 와 같은 전략).

출력: backend/runs/aggtrade_1m/{SYMBOL}_agg1m.joblib  (UTC 1분 인덱스 DataFrame)
      레포의 다른 파생 substrate(book_depth / microstructure / premium_index)와 같은
      형식이다. 프로덕션 venv 에 새 의존성(pyarrow)을 넣지 않으려고 parquet 대신 택했다.

사용:
  python3 scripts/backfill_aggtrades_1m.py --symbols WIFUSDT,DOGEUSDT --days 180
  python3 scripts/backfill_aggtrades_1m.py --symbols-file configs/ultra_universe.txt --days 365
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_aggtrades_1m")

ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/daily/aggTrades"
USECOLS = ["price", "quantity", "transact_time", "is_buyer_maker"]
DTYPES = {"price": "float64", "quantity": "float64",
          "transact_time": "int64", "is_buyer_maker": "bool"}

# 대형 체결 기준 — 당일 체결 금액 분포의 상위 분위. 종목·시기마다 절대 금액이
# 크게 다르므로 고정 USD 임계가 아니라 분위로 잡는다.
LARGE_TRADE_Q = 0.95

EXCHANGE_INFO = "https://fapi.binance.com/fapi/v1/exchangeInfo"
_TICK_CACHE: dict[str, float] = {}


def tick_size(sym: str) -> float | None:
    """PRICE_FILTER 틱사이즈. 추정하지 않고 거래소에서 받는다 (한 번만 호출)."""
    if not _TICK_CACHE:
        try:
            info = requests.get(EXCHANGE_INFO, timeout=60).json()
            for s in info.get("symbols", []):
                for f in s.get("filters", []):
                    if f.get("filterType") == "PRICE_FILTER":
                        _TICK_CACHE[s["symbol"]] = float(f["tickSize"])
            log.info("exchangeInfo 틱사이즈 %d종목 수신", len(_TICK_CACHE))
        except Exception as e:
            log.warning("exchangeInfo 실패: %s — 스프레드 하한 미적용", e)
            _TICK_CACHE["__failed__"] = 0.0
    return _TICK_CACHE.get(sym)


def infer_tick(df: pd.DataFrame) -> float | None:
    """관측 가격에서 틱을 역산한다 — 상장폐지 종목은 exchangeInfo 에 없다.

    719종목 유니버스 중 2종목(AERGO/BDXN)이 여기 해당한다. 폴백이 없으면 하한이
    안 씌워져 음수 스프레드가 조용히 흘러간다."""
    px = pd.concat([df["px_open"], df["px_high"], df["px_low"], df["px_close"]]).dropna()
    if len(px) < 100:
        return None
    d = np.diff(np.unique(np.round(px.values, 12)))
    d = d[d > 0]
    return float(np.min(d)) if len(d) else None


def apply_tick_floor(df: pd.DataFrame, tick: float | None) -> pd.DataFrame:
    """스프레드 추정치에 물리적 하한(1틱)을 씌운다. 상세는 모듈 docstring 참조."""
    if tick is None or tick <= 0:
        tick = infer_tick(df)
        if tick:
            log.info("  틱 역산 %s (exchangeInfo 미등재 — 폐지 종목)", tick)
    if tick is None or tick <= 0:
        log.warning("  틱 확보 실패 — 스프레드 하한 미적용 (음수 가능, 하류에서 걸러라)")
        df["tick_bp"] = np.nan
        df["eff_spread_bp_adj"] = df["eff_spread_bp"]
        return df
    df["tick_bp"] = tick / df["vwap"].replace(0, np.nan) * 10_000.0
    df["eff_spread_bp_adj"] = df[["eff_spread_bp", "tick_bp"]].max(axis=1)
    # 한쪽 방향 체결만 있어 추정 불가한 분은 하한값으로 채운다 (조용한 NaN 금지).
    df["eff_spread_bp_adj"] = df["eff_spread_bp_adj"].fillna(df["tick_bp"])
    return df


def aggregate_1m(df: pd.DataFrame) -> pd.DataFrame:
    """하루치 원본 체결 → 1분 피처. 원본은 호출자가 버린다."""
    if df is None or df.empty:
        return pd.DataFrame()

    df["quote"] = df["price"] * df["quantity"]
    df["ts"] = pd.to_datetime(df["transact_time"], unit="ms")
    df["minute"] = df["ts"].dt.floor("min")
    # is_buyer_maker=True → 테이커 매도. 부호를 여기서 한 번만 뒤집는다.
    df["taker_buy"] = ~df["is_buyer_maker"]

    large_thr = float(df["quote"].quantile(LARGE_TRADE_Q)) if len(df) > 20 else np.inf
    df["is_large"] = df["quote"] >= large_thr

    g = df.groupby("minute", sort=True)
    out = pd.DataFrame({
        "n_trades": g.size(),
        "volume": g["quantity"].sum(),
        "quote_volume": g["quote"].sum(),
        "px_open": g["price"].first(),
        "px_high": g["price"].max(),
        "px_low": g["price"].min(),
        "px_close": g["price"].last(),
    })

    buy = df[df["taker_buy"]].groupby("minute", sort=True)
    sell = df[~df["taker_buy"]].groupby("minute", sort=True)
    out["taker_buy_quote"] = buy["quote"].sum()
    out["taker_sell_quote"] = sell["quote"].sum()
    out["n_buy"] = buy.size()
    out["n_sell"] = sell.size()
    # 유효 스프레드 추정의 원재료. 파생값이 아니라 이것을 저장한다.
    out["vwap_buy"] = buy["quote"].sum() / buy["quantity"].sum()
    out["vwap_sell"] = sell["quote"].sum() / sell["quantity"].sum()

    lg = df[df["is_large"]]
    out["large_buy_quote"] = lg[lg["taker_buy"]].groupby("minute", sort=True)["quote"].sum()
    out["large_sell_quote"] = lg[~lg["taker_buy"]].groupby("minute", sort=True)["quote"].sum()
    out["large_thr_quote"] = large_thr

    q = df.groupby("minute", sort=True)["quote"]
    out["trade_q50"] = q.median()
    out["trade_q90"] = q.quantile(0.90)
    out["trade_max"] = q.max()

    for c in ("taker_buy_quote", "taker_sell_quote", "n_buy", "n_sell",
              "large_buy_quote", "large_sell_quote"):
        out[c] = out[c].fillna(0.0)

    out["vwap"] = out["quote_volume"] / out["volume"].replace(0, np.nan)
    denom = (out["taker_buy_quote"] + out["taker_sell_quote"]).replace(0, np.nan)
    # 주문흐름 불균형: +1 = 전량 공격적 매수, -1 = 전량 공격적 매도
    out["ofi"] = (out["taker_buy_quote"] - out["taker_sell_quote"]) / denom
    # 유효 스프레드 추정 (bp). 양쪽 체결이 다 있어야 정의된다 — 한쪽만 있으면 NaN.
    mid = (out["vwap_buy"] + out["vwap_sell"]) / 2.0
    out["eff_spread_bp"] = (out["vwap_buy"] - out["vwap_sell"]) / mid * 10_000.0

    out.index.name = "timestamp"
    return out


def _fetch_day(sym: str, date, session: requests.Session, retries: int = 2):
    url = f"{ARCHIVE_BASE}/{sym}/{sym}-aggTrades-{date.isoformat()}.zip"
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=180)
            if r.status_code == 404:
                return date, None, "missing"
            r.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                names = [n for n in z.namelist() if n.endswith(".csv")]
                if not names:
                    return date, None, "empty_zip"
                with z.open(names[0]) as fh:
                    raw = pd.read_csv(fh, usecols=USECOLS, dtype=DTYPES)
            agg = aggregate_1m(raw)
            del raw
            if agg.empty:
                return date, None, "empty_csv"
            return date, agg, "ok"
        except Exception as e:
            if attempt == retries:
                log.warning("[%s] %s 실패: %s", sym, date, e)
                return date, None, f"error: {type(e).__name__}"
            time.sleep(1.5 * (attempt + 1))
    return date, None, "exhausted"


def load_existing(path: Path):
    if not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception as e:
        log.warning("기존 파일 읽기 실패 %s: %s — 전량 재수집", path, e)
        return None


def postprocess_symbol(sym: str, out_dir: Path) -> dict:
    """다운로드 없이 파생 컬럼(틱 하한)만 기존 파일에 소급 적용한다."""
    out_path = out_dir / f"{sym}_agg1m.joblib"
    prev = load_existing(out_path)
    if prev is None:
        log.warning("[%s] 파일 없음 — 건너뜀", sym)
        return {"symbol": sym, "added": 0}
    tick = tick_size(sym)
    prev = apply_tick_floor(prev, tick)
    tmp = out_path.with_suffix(".joblib.tmp")
    joblib.dump(prev, tmp, compress=3)
    tmp.replace(out_path)
    log.info("[%s] 틱 %s | 스프레드 중앙 %.2f → 보정 %.2f bp", sym, tick,
             prev["eff_spread_bp"].median(), prev["eff_spread_bp_adj"].median())
    return {"symbol": sym, "added": 0, "have": len(prev), "missing": 0}


def backfill_symbol(sym: str, days: list, out_dir: Path, parallel: int) -> dict:
    out_path = out_dir / f"{sym}_agg1m.joblib"
    prev = load_existing(out_path)
    have = set() if prev is None else set(pd.DatetimeIndex(prev.index).normalize().date)
    todo = [d for d in days if d not in have]
    if not todo:
        log.info("[%s] 최신 — 신규 없음 (보유 %d일)", sym, len(have))
        return {"symbol": sym, "added": 0, "have": len(have), "missing": 0}

    t0 = time.time()
    frames, reasons = [], {}
    session = requests.Session()
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futs = [ex.submit(_fetch_day, sym, d, session) for d in todo]
        for i, f in enumerate(as_completed(futs), 1):
            d, agg, why = f.result()
            if agg is not None:
                frames.append(agg)
            else:
                reasons[why] = reasons.get(why, 0) + 1
            if i % 60 == 0:
                log.info("[%s] %d/%d", sym, i, len(todo))

    if not frames:
        log.warning("[%s] 수집 0일 — 사유 %s", sym, reasons)
        return {"symbol": sym, "added": 0, "have": len(have), "missing": len(todo),
                "reasons": reasons}

    new = pd.concat(frames).sort_index()
    if prev is not None:
        new = pd.concat([prev, new]).sort_index()
        new = new[~new.index.duplicated(keep="last")]
    new = apply_tick_floor(new, tick_size(sym))
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".joblib.tmp")
    joblib.dump(new, tmp, compress=3)
    tmp.replace(out_path)

    # 조용한 결손 금지 — 못 받은 날은 세어서 보고한다.
    got = len(frames)
    miss = len(todo) - got
    log.info("[%s] +%d일 (총 %d분봉, %s ~ %s) %.1fs%s",
             sym, got, len(new), new.index[0].date(), new.index[-1].date(),
             time.time() - t0, f" | 결손 {miss}일 {reasons}" if miss else "")
    return {"symbol": sym, "added": got, "have": len(have) + got,
            "missing": miss, "reasons": reasons}


def main() -> int:
    p = argparse.ArgumentParser(description="aggTrades 아카이브 → 1분 마이크로구조 피처")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--symbols", help="쉼표 구분")
    g.add_argument("--symbols-file", help="줄바꿈 구분 파일")
    p.add_argument("--days", type=int, default=180)
    p.add_argument("--end-date", default=None, help="YYYY-MM-DD (기본: 어제)")
    p.add_argument("--parallel", type=int, default=6,
                   help="일 단위 동시 다운로드. 대형 종목은 하루 CSV 가 크므로 과하게 올리지 말 것")
    p.add_argument("--out-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--postprocess", action="store_true",
                   help="다운로드 없이 기존 파일의 파생 컬럼(틱 하한)만 재계산")
    args = p.parse_args()

    if args.symbols_file:
        syms = [ln.strip().upper() for ln in Path(args.symbols_file).read_text().splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    else:
        syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    end_date = (datetime.utcnow() - timedelta(days=1)).date() if args.end_date is None \
        else datetime.strptime(args.end_date, "%Y-%m-%d").date()
    start_date = end_date - timedelta(days=args.days - 1)
    days = [start_date + timedelta(days=i) for i in range(args.days)]
    out_dir = Path(args.out_dir)

    log.info("종목 %d개 | %s ~ %s (%d일) | 출력 %s",
             len(syms), start_date, end_date, args.days, out_dir)

    t0, results = time.time(), []
    for n, sym in enumerate(syms, 1):
        log.info("── [%d/%d] %s ──", n, len(syms), sym)
        try:
            if args.postprocess:
                results.append(postprocess_symbol(sym, out_dir))
                continue
            results.append(backfill_symbol(sym, days, out_dir, args.parallel))
        except Exception as e:
            log.error("[%s] 중단: %s", sym, e)
            results.append({"symbol": sym, "added": 0, "error": str(e)})

    ok = [r for r in results if r.get("added", 0) > 0 or r.get("have", 0) > 0]
    total_missing = sum(r.get("missing", 0) for r in results)
    log.info("완료 — 종목 %d/%d, 신규 %d일, 결손 %d일, %.1f분",
             len(ok), len(syms), sum(r.get("added", 0) for r in results),
             total_missing, (time.time() - t0) / 60)
    for r in results:
        if r.get("missing"):
            log.info("  결손 %s: %d일 %s", r["symbol"], r["missing"], r.get("reasons"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
