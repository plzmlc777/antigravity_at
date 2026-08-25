"""미국 주식 일봉: 구 `ohlcv`(time_frame='1d') → `ohlcv_daily`.

## 왜 (2026-08-25)

구 `ohlcv` 를 걷어내는 중인데 그 안에 **미국 주식 일봉**이 섞여 있었다.
바이낸스 1분봉만 있는 줄 알고 60종목을 표본했는데, 그 표본이 바이낸스
유니버스 파일에서만 뽑혀 미국 종목을 한 번도 안 봤다.

실사(core 60 + leveraged 46 = 106종목):
    1d  106종목 · 144,875행 · 2019-10-23 ~ 2026-08-21
    1m  **없음** — 서비스에 1분봉 경로가 있지만 쓰인 적이 없다

2.67억 행 중 0.05% 다. 이것만 옮기면 구 테이블을 통째로 버릴 수 있다.

## 대상 테이블

`ohlcv_daily (symbol, date, open, high, low, close, volume, n_minutes,
is_partial, built_at)` · 유니크 `uq_ohlcv_daily_symbol_date (symbol, date)`.

⚠ `n_minutes` 는 "그 날 몇 분봉으로 만들었나"다. 미국 일봉은 분봉에서
  만든 게 아니라 **거래소가 준 일봉**이므로 0 을 넣고 `is_partial=false`
  로 둔다. 0 이 "분봉에서 유도하지 않았다"는 표시가 된다.

⚠ 절대 삭제하지 않는다 — `ON CONFLICT (symbol, date) DO NOTHING`.
  다시 돌려도 무해하다.

사용:
  python3 -m scripts.migrate_us_daily_to_ohlcv_daily --dry-run
  python3 -m scripts.migrate_us_daily_to_ohlcv_daily --commit
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text                                    # noqa: E402

from app.db.session import engine                              # noqa: E402

log = logging.getLogger("mig_us")
UNI = Path(__file__).resolve().parents[1] / "configs" / "us_universe.json"

CNT = text("SELECT count(*) FROM ohlcv WHERE symbol=:s AND time_frame='1d'")
HAVE = text("SELECT count(*) FROM ohlcv_daily WHERE symbol=:s")
COPY = text("""
INSERT INTO ohlcv_daily (symbol, date, open, high, low, close, volume,
                         n_minutes, is_partial, built_at)
SELECT symbol, timestamp::date, open, high, low, close, volume,
       0, false, now()
FROM ohlcv
WHERE symbol=:s AND time_frame='1d'
ON CONFLICT (symbol, date) DO NOTHING
""")


def us_symbols() -> list[str]:
    d = json.loads(UNI.read_text())
    out = []
    for k in ("core", "leveraged"):
        for x in d.get(k, []):
            s = x.get("symbol") if isinstance(x, dict) else x
            if s:
                out.append(s)
    return sorted(set(out))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--commit", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--symbols", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    commit = a.commit and not a.dry_run

    syms = ([s.strip().upper() for s in a.symbols.split(",") if s.strip()]
            if a.symbols else us_symbols())
    log.info("미국 종목 %d · 모드 %s", len(syms), "이관" if commit else "점검만")

    t0 = time.time()
    n_src = n_ins = n_sym = 0
    with engine.connect() as c:
        c.execute(text("SET statement_timeout='300s'"))
        for s in syms:
            try:
                src = c.execute(CNT, {"s": s}).scalar() or 0
            except Exception as e:                             # noqa: BLE001
                c.rollback(); log.warning("  ✗ %s 계수 실패: %s", s, e); continue
            if not src:
                continue
            n_sym += 1; n_src += src
            if not commit:
                continue
            try:
                r = c.execute(COPY, {"s": s}); c.commit()
                n_ins += r.rowcount or 0
            except Exception as e:                             # noqa: BLE001
                c.rollback(); log.warning("  ✗ %s 이관 실패: %s", s, e)
    log.info("완료 — 종목 %d · 원본 %s행 · 삽입 %s행 · %.0f초",
             n_sym, f"{n_src:,}", f"{n_ins:,}", time.time() - t0)
    if not commit:
        log.info("점검만 했다. 실제 이관은 --commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
