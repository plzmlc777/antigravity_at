#!/usr/bin/env python3
"""
미국 ETF 유니버스 빌더 — 키움 순위정보 API 기반.

왜 ETF 우선인가 (2026-07-31 확정):
    - 협의수수료 문턱이 개별주 10억 vs 미국ETF 1억 (10배 낮음)
    - 개별주 이벤트 리스크(실적/소송/PTP 10% 원천징수) 없음
    - 키움 API 에 ETF 전용 순위 계열이 완비돼 있어 US 고유 substrate 확보 가능

소스 (전부 /api/us/rkinfo, 실측 검증):
    usa20541  당일 거래대금 상위(ETF)   — trde_prica 로 유동성 랭킹
    usa20551  시가총액 상위(ETF)        — mac, mac_wght

레버리지/인버스 분리:
    2X/3X·불/베어 ETF 는 일간 리밸런싱 구조상 경로의존 감쇠가 있어 스윙
    백테스트 결과가 왜곡된다. 유니버스에서 제외하지 않고 `leveraged` 플래그로
    분리 태깅해, 코어 트랙은 non-leveraged 만 쓰고 레버리지는 별도 실험군으로 둔다.

출력: backend/configs/us_universe.json

실행: cd backend && python -m scripts.build_us_universe [--pages 10] [--top 60]
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR.parent / ".env")

from app.adapters.kiwoom_us import KiwoomUSAdapter, KiwoomUSError, _f  # noqa: E402
from app.core import security  # noqa: E402
from app.core.http_client import HttpClientManager  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.account import ExchangeAccount  # noqa: E402
from app.models.user import User  # noqa: E402,F401

OUT_PATH = BACKEND_DIR / "configs" / "us_universe.json"

TRADE_VALUE_TOP = "usa20541"   # 당일 거래대금 상위(ETF)
MARKET_CAP_TOP = "usa20551"    # 시가총액 상위(ETF)
RK_URL = "/api/us/rkinfo"

# 레버리지/인버스 판별 — 영문명·한글명 양쪽을 본다
_LEV_PATTERNS = re.compile(
    r"(\b[23]X\b|\b[23]-?X\b|BULL|BEAR|INVERSE|ULTRA(?:PRO|SHORT)|레버리지|인버스|[23]배)",
    re.IGNORECASE,
)


def is_leveraged(*names: str) -> bool:
    return any(_LEV_PATTERNS.search(n or "") for n in names)


async def build_adapter() -> KiwoomUSAdapter:
    db = SessionLocal()
    try:
        account = (
            db.query(ExchangeAccount)
            .filter(ExchangeAccount.exchange_name == "KiwoomUS")
            .first()
        ) or (
            db.query(ExchangeAccount)
            .filter(
                ExchangeAccount.exchange_name == "Kiwoom",
                ExchangeAccount.environment == "real",
            )
            .first()
        )
        if account is None:
            raise RuntimeError("키움 자격증명 계정을 찾을 수 없습니다")
        return KiwoomUSAdapter(
            app_key=security.decrypt_key(account.encrypted_access_key or ""),
            secret_key=security.decrypt_key(account.encrypted_secret_key or ""),
        )
    finally:
        db.close()


async def fetch_ranked(adapter: KiwoomUSAdapter, api_id: str, pages: int) -> list:
    """순위 API 를 연속조회로 긁는다."""
    rows = []
    cont_yn, next_key = "N", ""
    for page in range(pages):
        try:
            data = await adapter._request(api_id, RK_URL, {}, cont_yn=cont_yn, next_key=next_key)
        except KiwoomUSError as e:
            print(f"  [{api_id}] page {page} 실패: {e}")
            break
        key = next((k for k, v in data.items() if isinstance(v, list)), None)
        page_rows = data.get(key) or [] if key else []
        rows.extend(page_rows)
        cont_yn, next_key = data.get("_cont_yn", "N"), data.get("_next_key", "")
        if cont_yn != "Y" or not page_rows:
            break
        await asyncio.sleep(0.15)
    return rows


def merge(trade_rows: list, cap_rows: list) -> dict:
    """티커 기준 병합. 거래대금·시총을 한 레코드로 합친다."""
    out: dict[str, dict] = {}

    for r in trade_rows:
        code = (r.get("stk_cd") or "").strip().upper()
        if not code:
            continue
        out[code] = {
            "symbol": code,
            "name_kr": r.get("stk_nm"),
            "name_en": r.get("stk_enm"),
            "stex_tp": r.get("stex_tp"),
            "price": abs(_f(r.get("cur_prc"))),
            "trade_value": _f(r.get("trde_prica")),
            "volume": _f(r.get("acc_trde_qty")),
            "market_cap": None,
            "trade_value_rank": int(r.get("rank") or 0) or None,
            "market_cap_rank": None,
        }

    for r in cap_rows:
        code = (r.get("stk_cd") or "").strip().upper()
        if not code:
            continue
        rec = out.setdefault(code, {
            "symbol": code,
            "name_kr": r.get("stk_nm"),
            "name_en": r.get("stk_enm"),
            "stex_tp": r.get("stex_tp"),
            "price": abs(_f(r.get("cur_prc"))),
            "trade_value": None,
            "volume": _f(r.get("acc_trde_qty")),
            "market_cap": None,
            "trade_value_rank": None,
            "market_cap_rank": None,
        })
        rec["market_cap"] = _f(r.get("mac"))
        rec["market_cap_rank"] = int(r.get("rank") or 0) or None

    for code, rec in out.items():
        rec["leveraged"] = is_leveraged(rec.get("name_en"), rec.get("name_kr"))

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=10, help="순위 API 연속조회 페이지 수")
    ap.add_argument("--top", type=int, default=60, help="코어 유니버스 크기 (non-leveraged)")
    args = ap.parse_args()

    async def run():
        await HttpClientManager.get_instance().start()
        try:
            adapter = await build_adapter()
            print(f"거래대금 상위 ETF 수집 ({args.pages}페이지)...")
            trade_rows = await fetch_ranked(adapter, TRADE_VALUE_TOP, args.pages)
            print(f"  -> {len(trade_rows)}건")
            print(f"시가총액 상위 ETF 수집 ({args.pages}페이지)...")
            cap_rows = await fetch_ranked(adapter, MARKET_CAP_TOP, args.pages)
            print(f"  -> {len(cap_rows)}건")
            return merge(trade_rows, cap_rows)
        finally:
            await HttpClientManager.get_instance().stop()

    merged = asyncio.run(run())
    if not merged:
        print("실패: 수집 결과 없음")
        return 1

    core = [r for r in merged.values() if not r["leveraged"]]
    lev = [r for r in merged.values() if r["leveraged"]]

    # 코어 정렬: 거래대금 우선, 없으면 시총
    core.sort(key=lambda r: (-(r["trade_value"] or 0), -(r["market_cap"] or 0)))
    lev.sort(key=lambda r: -(r["trade_value"] or 0))
    core = core[: args.top]

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "trade_value_top": TRADE_VALUE_TOP,
            "market_cap_top": MARKET_CAP_TOP,
            "url": RK_URL,
        },
        "note": (
            "키움 미국 ETF 순위 API 기반. leveraged=2X/3X·불베어·인버스 (일간 리밸런싱 "
            "경로의존 감쇠 때문에 코어 트랙에서 분리). 거래대금은 조회 시점 당일 값이라 "
            "일간 변동이 크다 — 랭킹은 참고용이고 유니버스는 주기적으로 재생성할 것."
        ),
        "counts": {"total": len(merged), "core": len(core), "leveraged": len(lev)},
        "core": core,
        "leveraged": lev,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"\n저장: {OUT_PATH}")
    print(f"  전체 {len(merged)} / 코어 {len(core)} / 레버리지 {len(lev)}")
    print("\n코어 상위 15:")
    for r in core[:15]:
        tv = r["trade_value"]
        mc = r["market_cap"]
        print(f"  {r['symbol']:6} {r['stex_tp']:3} "
              f"거래대금 {tv:>14,.0f}" if tv else f"  {r['symbol']:6} {r['stex_tp']:3} 거래대금 —",
              end="")
        print(f"  시총 {mc:>12,.0f}" if mc else "  시총 —", f" {r['name_kr']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
