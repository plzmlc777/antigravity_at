"""온체인 지표 수집 — CoinMetrics Community API.

출처는 **완전 무료·키 불필요**다(`community-api.coinmetrics.io`). 등록도 결제도
없다. 대표님 원칙(완전무료 + 공개데이터 + 자체수집, freemium 금지)에 맞는다.

⚠ 커버리지가 우리 유니버스와 어긋난다
    실측(2026-08-15): 지원 17종. **SOL/AVAX/MATIC/ATOM/NEAR/FIL/SHIB/PEPE/WIF
    없음**. 일부는 갱신 정지(DOT 2022-06, BNB 2019-04).
    우리 유동성 유니버스가 190종이니 교집합이 작다. 이 스크립트는 **어느 자산이
    빠졌고 어느 것이 멈췄는지 반드시 보고**한다 — 모르고 쓰면 표본이 조용히 준다.

⚠ 자산 코드 ≠ 거래소 심볼
    CoinMetrics 는 `btc`, 바이낸스는 `BTCUSDT` 다. 매핑을 여기 한 곳에 두고
    DB 에는 원본 코드를 저장한다. 매핑이 두 곳에 있으면 갈린다.

사용:
  python3 -m scripts.collect_onchain --discover        # 지원 자산·이력 조사
  python3 -m scripts.collect_onchain --all             # 전체 이력 수집
  python3 -m scripts.collect_onchain --incremental     # 매일 (크론)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("onchain")

BASE = "https://community-api.coinmetrics.io/v4"

# CoinMetrics 지표 → 우리 컬럼
METRIC_MAP = {
    "AdrActCnt": "active_addresses",
    "TxCnt": "tx_count",
    "CapMrktCurUSD": "market_cap",
    "SplyCur": "supply",
    "FeeTotNtv": "fee_total",
    "HashRate": "hash_rate",
    "IssTotUSD": "issuance_usd",
}

# 자산 코드 ↔ 바이낸스 심볼. **여기가 유일한 매핑처다.**
ASSET_TO_SYMBOL = {
    "btc": "BTCUSDT", "eth": "ETHUSDT", "ada": "ADAUSDT", "xrp": "XRPUSDT",
    "doge": "DOGEUSDT", "ltc": "LTCUSDT", "link": "LINKUSDT", "dot": "DOTUSDT",
    "uni": "UNIUSDT", "aave": "AAVEUSDT", "algo": "ALGOUSDT", "icp": "ICPUSDT",
    "bch": "BCHUSDT", "etc": "ETCUSDT", "xlm": "XLMUSDT", "trx": "TRXUSDT",
    "bnb": "BNBUSDT",
}
DEFAULT_ASSETS = sorted(ASSET_TO_SYMBOL)

START = "2015-01-01"
STALE_DAYS = 30          # 이보다 오래 갱신이 없으면 '정지'로 본다


def fetch(assets: str, metrics: str, start: str, end: str,
          retries: int = 3) -> list[dict]:
    q = (f"assets={assets}&metrics={metrics}&frequency=1d"
         f"&start_time={start}&end_time={end}&page_size=10000")
    url = f"{BASE}/timeseries/asset-metrics?{q}"
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r).get("data", [])
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []              # 그 자산에 그 지표가 없다
            if i == retries - 1:
                raise
        except Exception:
            if i == retries - 1:
                raise
        time.sleep(2 * (i + 1))
    return []


def discover(assets: list[str]) -> list[dict]:
    """자산별 지원 여부·이력 범위. **무엇이 빠졌는지 먼저 알아야 한다.**"""
    today = date.today().isoformat()
    out = []
    for a in assets:
        try:
            rows = fetch(a, "AdrActCnt,CapMrktCurUSD", START, today)
        except Exception as exc:
            out.append({"asset": a, "ok": False, "why": type(exc).__name__})
            continue
        if not rows:
            out.append({"asset": a, "ok": False, "why": "데이터 없음"})
            continue
        first, last = rows[0]["time"][:10], rows[-1]["time"][:10]
        stale = (date.today() - date.fromisoformat(last)).days
        out.append({"asset": a, "ok": True, "n": len(rows),
                    "first": first, "last": last, "stale_days": stale,
                    "has_cap": any(r.get("CapMrktCurUSD") for r in rows[-5:]),
                    "symbol": ASSET_TO_SYMBOL.get(a)})
    return out


def upsert(conn, asset: str, rows: list[dict]) -> int:
    from sqlalchemy import text
    if not rows:
        return 0
    cols = list(METRIC_MAP.values())
    sql = text(f"""
        INSERT INTO onchain_metric (asset, date, {', '.join(cols)}, fetched_at)
        VALUES (:asset, :date, {', '.join(':' + c for c in cols)}, now())
        ON CONFLICT (asset, date) DO UPDATE SET
            {', '.join(f'{c} = EXCLUDED.{c}' for c in cols)},
            fetched_at = now()
    """)
    n = 0
    for r in rows:
        p = {"asset": asset, "date": r["time"][:10]}
        for cm, col in METRIC_MAP.items():
            v = r.get(cm)
            try:
                p[col] = float(v) if v not in (None, "") else None
            except (TypeError, ValueError):
                p[col] = None
        conn.execute(sql, p)
        n += 1
    conn.commit()
    return n


def main() -> int:
    p = argparse.ArgumentParser(description="온체인 지표 수집 (CoinMetrics 무료)")
    p.add_argument("--discover", action="store_true",
                   help="지원 자산·이력 범위만 조사하고 종료")
    p.add_argument("--all", action="store_true", help="전체 이력")
    p.add_argument("--incremental", action="store_true",
                   help="자산별 마지막 날짜 이후만")
    p.add_argument("--assets", default="", help="쉼표 구분. 기본은 매핑 전체")
    a = p.parse_args()
    if not (a.discover or a.all or a.incremental):
        raise SystemExit("--discover / --all / --incremental 중 하나")

    assets = ([x.strip().lower() for x in a.assets.split(",") if x.strip()]
              or DEFAULT_ASSETS)

    if a.discover:
        rows = discover(assets)
        print("=" * 84)
        print(f"CoinMetrics Community — 후보 {len(assets)}종 조사")
        print("=" * 84)
        print(f"  {'자산':<7}{'심볼':<12}{'행':>7}{'시작':>12}{'최신':>12}"
              f"{'지연일':>7}  시총")
        for r in sorted(rows, key=lambda x: (not x["ok"], x["asset"])):
            if not r["ok"]:
                print(f"  {r['asset']:<7}{'':<12}  — {r['why']}")
                continue
            flag = " ⚠정지" if r["stale_days"] > STALE_DAYS else ""
            print(f"  {r['asset']:<7}{str(r['symbol']):<12}{r['n']:>7}"
                  f"{r['first']:>12}{r['last']:>12}{r['stale_days']:>7}"
                  f"  {'있음' if r['has_cap'] else '없음'}{flag}")
        live = [r for r in rows if r["ok"] and r["stale_days"] <= STALE_DAYS]
        print("-" * 84)
        print(f"  살아 있는 자산 **{len(live)}/{len(assets)}**")
        print(f"  ⚠ 우리 유동성 유니버스는 190종이다 — 교집합이 작다는 것을")
        print(f"     알고 써야 한다. 빠진 종목은 표본에서 조용히 사라진다.")
        print("=" * 84)
        return 0

    from app.db.session import engine

    metrics = ",".join(METRIC_MAP)
    today = date.today().isoformat()
    total, done, skipped = 0, 0, []
    t0 = time.time()
    with engine.connect() as conn:
        last_by: dict[str, date] = {}
        if a.incremental:
            from sqlalchemy import text
            for asset, d in conn.execute(text(
                    "SELECT asset, max(date) FROM onchain_metric GROUP BY asset")):
                last_by[asset] = d
        for asset in assets:
            start = (last_by[asset].isoformat() if asset in last_by else START)
            try:
                rows = fetch(asset, metrics, start, today)
            except Exception as exc:
                skipped.append(f"{asset}: {type(exc).__name__}")
                log.warning("%s 실패: %s", asset, exc)
                continue
            if not rows:
                skipped.append(f"{asset}: 데이터 없음")
                continue
            n = upsert(conn, asset, rows)
            total += n
            done += 1
            log.info("%s +%d행 (%s ~ %s)", asset, n,
                     rows[0]["time"][:10], rows[-1]["time"][:10])

    print("=" * 76)
    print(f"온체인 수집 — {done}/{len(assets)}자산 · {total:,}행 · "
          f"{time.time()-t0:.0f}초")
    if skipped:
        print(f"제외 {len(skipped)}: {', '.join(skipped[:10])}")
    from sqlalchemy import text
    with engine.connect() as c:
        n, s, d0, d1 = c.execute(text(
            "SELECT count(*), count(distinct asset), min(date), max(date) "
            "FROM onchain_metric")).one()
        print(f"테이블: {n:,}행 · 자산 {s} · {d0} ~ {d1}")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
