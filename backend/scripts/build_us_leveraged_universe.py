#!/usr/bin/env python3
"""
미국 레버리지·인버스 ETF 전수 유니버스 + 일봉 백필.

왜 전수인가:
    us_universe.json 은 "현재 유동성 상위" 랭킹에서 뽑은 것이라 생존편향이 있다.
    상장 이벤트를 연구하려면 상장 후 사라졌거나 유동성이 낮은 종목까지 포함한
    전수 코호트가 필요하다.

수집:
    usa10099 (거래소별 종목 목록) → isEtf='Y' 필터 → 영문·한글명에서 레버리지·
    인버스 패턴 매칭. 상장일은 일봉 최초 거래일로 근사한다(IBIT 2024-01-11 실측
    검증 완료).

출력: backend/configs/us_leveraged_universe.json
실행: cd backend && PYTHONPATH=. python3 -m scripts.build_us_leveraged_universe [--no-backfill]
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR.parent / ".env")

import logging  # noqa: E402

from app.adapters.kiwoom_us import KiwoomUSAdapter  # noqa: E402
from app.core import security  # noqa: E402
from app.core.http_client import HttpClientManager  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.account import ExchangeAccount  # noqa: E402
from app.models.user import User  # noqa: E402,F401
from app.services.us_market_data_service import USMarketDataService  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

OUT_PATH = BACKEND_DIR / "configs" / "us_leveraged_universe.json"
EXCHANGES = ("ND", "NY", "AM")

LEV_RE = re.compile(
    r"(\b-?[23]X\b|DAILY\s*-?[23]X|BULL|BEAR|INVERSE|ULTRA(?:PRO|SHORT)?|레버리지|인버스|[23]배)",
    re.IGNORECASE,
)
# 방향 판별 — 인버스/숏 상품인지
SHORT_RE = re.compile(r"(-[23]X|BEAR|INVERSE|SHORT|인버스|숏)", re.IGNORECASE)


async def build_adapter() -> KiwoomUSAdapter:
    db = SessionLocal()
    try:
        acc = (db.query(ExchangeAccount)
               .filter(ExchangeAccount.exchange_name == "KiwoomUS").first()
               or db.query(ExchangeAccount)
               .filter(ExchangeAccount.exchange_name == "Kiwoom",
                       ExchangeAccount.environment == "real").first())
        if acc is None:
            raise RuntimeError("키움 자격증명 계정 없음")
        return KiwoomUSAdapter(
            app_key=security.decrypt_key(acc.encrypted_access_key or ""),
            secret_key=security.decrypt_key(acc.encrypted_secret_key or ""),
        )
    finally:
        db.close()


async def collect_symbols(adapter: KiwoomUSAdapter) -> list:
    out = []
    for stex in EXCHANGES:
        data = await adapter._request("usa10099", "/api/us/stkinfo", {"stex_tp": stex})
        rows = data.get("list") or []
        for r in rows:
            if r.get("isEtf") != "Y":
                continue
            blob = f"{r.get('stk_enm') or ''} {r.get('stk_nm') or ''}"
            if not LEV_RE.search(blob):
                continue
            out.append({
                "symbol": (r.get("stk_cd") or "").strip().upper(),
                "name_kr": r.get("stk_nm"),
                "name_en": r.get("stk_enm"),
                "stex_tp": r.get("stex_tp"),
                "exchange": r.get("mkgb"),
                "direction": "short" if SHORT_RE.search(blob) else "long",
            })
        print(f"  {stex}: 전체 {len(rows)} → 레버리지·인버스 누적 {len(out)}")
        await asyncio.sleep(0.2)
    # 중복 제거
    seen, uniq = set(), []
    for r in out:
        if r["symbol"] and r["symbol"] not in seen:
            seen.add(r["symbol"])
            uniq.append(r)
    return uniq


async def backfill(symbols: list, years: float = 6.0) -> dict:
    svc = USMarketDataService()
    stats = {"ok": 0, "empty": 0, "error": 0}
    t0 = time.time()
    for i, rec in enumerate(symbols, 1):
        try:
            n = await svc.fetch_daily_history(rec["symbol"], years=years)
            stats["ok" if n else "empty"] += 1
        except Exception as e:
            stats["error"] += 1
            if stats["error"] <= 5:
                print(f"    실패 {rec['symbol']}: {str(e)[:80]}")
        if i % 50 == 0:
            el = time.time() - t0
            print(f"  {i}/{len(symbols)} ({el:.0f}s, 잔여 ~{el / i * (len(symbols) - i):.0f}s)")
    print(f"  백필 완료 {time.time() - t0:.0f}s — {stats}")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-backfill", action="store_true")
    ap.add_argument("--years", type=float, default=6.0)
    args = ap.parse_args()

    async def run():
        await HttpClientManager.get_instance().start()
        try:
            adapter = await build_adapter()
            print("레버리지·인버스 ETF 전수 수집...")
            syms = await collect_symbols(adapter)
            print(f"→ {len(syms)}종 (롱 {sum(1 for s in syms if s['direction'] == 'long')} / "
                  f"숏 {sum(1 for s in syms if s['direction'] == 'short')})")

            payload = {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "source": "usa10099 (거래소별 종목목록) + 명칭 패턴 매칭",
                "note": ("상장일은 일봉 최초 거래일로 근사. 전수 코호트라 "
                         "us_universe.json(유동성 상위)과 달리 생존편향이 없다."),
                "n": len(syms),
                "symbols": syms,
            }
            OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                encoding="utf-8")
            print(f"저장: {OUT_PATH}")

            if not args.no_backfill:
                print(f"\n일봉 백필 {len(syms)}종 × {args.years}년...")
                await backfill(syms, args.years)
        finally:
            await HttpClientManager.get_instance().stop()

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
