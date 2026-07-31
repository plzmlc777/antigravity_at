#!/usr/bin/env python3
"""
미국 신규 상장 ETF 코호트 구축 (비레버리지 포함 전수).

왜 필요한가:
    앞선 R-0(us_leveraged_etf_listing_cohort)은 레버리지·인버스 567종만 봤다.
    미국 ETF 전체는 4,000종 규모이고, 비레버리지 신규 상장은 완전히 다른
    모집단이다 — 일간 리밸런싱 감쇠가 없으므로 레버리지에서 관측된 하락
    편향이 그대로 적용된다는 보장이 없다.

상장일을 싸게 얻는 법:
    키움 API 에 상장일 필드가 없다(usa10100 확인). 대신 일봉 조회의 strt_dt 가
    "조회 종료일"이라는 성질을 이용한다 — strt_dt=CUTOFF 로 1페이지만 요청해
    **0행이면 그 날짜 이전에 거래 이력이 없다** = CUTOFF 이후 상장.
    심볼당 1요청이면 되므로 4,000종을 ~13분에 판별한다.

단계:
    1) usa10099 로 거래소별 전 종목 → isEtf='Y' 필터
    2) strt_dt=CUTOFF 프로브로 신규 상장 후보 선별
    3) 후보만 일봉 백필 (신규라 페이지 수가 적어 빠름)

출력: backend/configs/us_new_etf_cohort.json
실행: cd backend && PYTHONPATH=. python3 -m scripts.build_us_new_etf_cohort [--cutoff 20231231]
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

from app.adapters.kiwoom_us import KiwoomUSAdapter, KiwoomUSError  # noqa: E402
from app.core import security  # noqa: E402
from app.core.http_client import HttpClientManager  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.account import ExchangeAccount  # noqa: E402
from app.models.user import User  # noqa: E402,F401
from app.services.us_market_data_service import USMarketDataService  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

OUT_PATH = BACKEND_DIR / "configs" / "us_new_etf_cohort.json"
LEV_UNIVERSE = BACKEND_DIR / "configs" / "us_leveraged_universe.json"
EXCHANGES = ("ND", "NY", "AM")

LEV_RE = re.compile(
    r"(\b-?[23]X\b|DAILY\s*-?[23]X|BULL|BEAR|INVERSE|ULTRA(?:PRO|SHORT)?|레버리지|인버스|[23]배)",
    re.IGNORECASE,
)


def log(msg: str) -> None:
    print(msg, flush=True)


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


async def all_etfs(adapter: KiwoomUSAdapter) -> list:
    out = []
    for stex in EXCHANGES:
        data = await adapter._request("usa10099", "/api/us/stkinfo", {"stex_tp": stex})
        rows = data.get("list") or []
        etfs = [r for r in rows if r.get("isEtf") == "Y"]
        for r in etfs:
            blob = f"{r.get('stk_enm') or ''} {r.get('stk_nm') or ''}"
            out.append({
                "symbol": (r.get("stk_cd") or "").strip().upper(),
                "name_kr": r.get("stk_nm"),
                "name_en": r.get("stk_enm"),
                "stex_tp": r.get("stex_tp"),
                "exchange": r.get("mkgb"),
                "leveraged": bool(LEV_RE.search(blob)),
            })
        log(f"  {stex}: 전체 {len(rows)} / ETF {len(etfs)}")
        await asyncio.sleep(0.2)
    seen, uniq = set(), []
    for r in out:
        if r["symbol"] and r["symbol"] not in seen:
            seen.add(r["symbol"])
            uniq.append(r)
    return uniq


async def probe_new(adapter: KiwoomUSAdapter, cands: list, cutoff: str) -> list:
    """strt_dt=cutoff 로 1페이지 조회 → 0행이면 cutoff 이후 상장."""
    new_ones, t0 = [], time.time()
    for i, rec in enumerate(cands, 1):
        stex = rec.get("stex_tp") or "ND"
        body = {"stex_tp": stex, "stk_cd": rec["symbol"], "strt_dt": cutoff,
                "upd_stkpc_tp": "1", "exrt_appl_tp": "0"}
        try:
            data = await adapter._request("usa06012", "/api/us/chart", body)
            if not (data.get("result_list") or []):
                new_ones.append(rec)
        except KiwoomUSError:
            pass  # 조회 불가 종목은 후보에서 제외
        except Exception:
            pass
        if i % 250 == 0:
            el = time.time() - t0
            log(f"  프로브 {i}/{len(cands)} — 신규 {len(new_ones)}종 "
                f"({el:.0f}s, 잔여 ~{el / i * (len(cands) - i):.0f}s)")
    return new_ones


async def backfill(symbols: list, years: float) -> dict:
    svc = USMarketDataService()
    stats = {"ok": 0, "empty": 0, "error": 0}
    t0 = time.time()
    for i, rec in enumerate(symbols, 1):
        try:
            n = await svc.fetch_daily_history(rec["symbol"], years=years)
            stats["ok" if n else "empty"] += 1
        except Exception:
            stats["error"] += 1
        if i % 100 == 0:
            el = time.time() - t0
            log(f"  백필 {i}/{len(symbols)} ({el:.0f}s, 잔여 ~{el / i * (len(symbols) - i):.0f}s)")
    log(f"  백필 완료 {time.time() - t0:.0f}s — {stats}")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", default="20231231",
                    help="이 날짜 이전 거래이력이 없으면 신규 상장으로 판정")
    ap.add_argument("--years", type=float, default=3.0)
    args = ap.parse_args()

    async def run():
        await HttpClientManager.get_instance().start()
        try:
            adapter = await build_adapter()
            log("전체 ETF 목록 수집...")
            etfs = await all_etfs(adapter)
            log(f"→ ETF {len(etfs)}종 (레버리지 {sum(1 for e in etfs if e['leveraged'])})")

            # 이미 백필된 레버리지 유니버스는 프로브 생략 (일봉으로 상장일 확보됨)
            done = set()
            if LEV_UNIVERSE.exists():
                done = {s["symbol"] for s in
                        json.loads(LEV_UNIVERSE.read_text(encoding="utf-8"))["symbols"]}
            cands = [e for e in etfs if e["symbol"] not in done]
            log(f"\n프로브 대상 {len(cands)}종 (기적재 {len(done)}종 제외), "
                f"기준일 {args.cutoff}")
            new_ones = await probe_new(adapter, cands, args.cutoff)
            log(f"→ 신규 상장 후보 {len(new_ones)}종 "
                f"(비레버리지 {sum(1 for e in new_ones if not e['leveraged'])})")

            payload = {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "cutoff": args.cutoff,
                "method": ("일봉 strt_dt=cutoff 1페이지 조회에서 0행 → "
                           "해당 일자 이전 거래이력 없음 = 신규 상장"),
                "n_etf_total": len(etfs),
                "n_probed": len(cands),
                "n_new": len(new_ones),
                "symbols": new_ones,
            }
            OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                encoding="utf-8")
            log(f"저장: {OUT_PATH}")

            log(f"\n신규 코호트 일봉 백필 {len(new_ones)}종...")
            await backfill(new_ones, args.years)
        finally:
            await HttpClientManager.get_instance().stop()

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
