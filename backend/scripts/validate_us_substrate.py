#!/usr/bin/env python3
"""
미국 ETF 일봉 substrate 무결성 점검 + 유효 시작일 산출.

왜 필요한가:
    키움 미국 일봉에는 상장 이전 구간이 섞여 들어오는 종목이 있다.
    실측: IBIT(iShares Bitcoin Trust, 2024-01 상장)에 2022-09-09부터 데이터가
    있고 974봉 중 188봉(19.3%)이 거래량 0. 그대로 백테스트에 넣으면 존재하지도
    않던 기간의 가짜 시그널이 생긴다.

판정:
    first_valid_date = 마지막 거래량 0 봉의 다음 거래일.
    (거래량 0 이 전혀 없으면 최초 봉 날짜)
    zero_ratio 가 임계 이상이면 suspect 로 표시.

결과는 us_universe.json 의 각 레코드에 first_valid_date / zero_bars /
data_suspect 로 기록된다. 백테스트는 first_valid_date 이후만 쓸 것.

실행: cd backend && python -m scripts.validate_us_substrate
"""

import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR.parent / ".env")

from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402

UNIVERSE_PATH = BACKEND_DIR / "configs" / "us_universe.json"
SUSPECT_ZERO_RATIO = 0.02      # 거래량 0 봉 2% 초과 → suspect
MIN_BARS_FOR_BACKTEST = 500    # 일봉 500봉(약 2년) 미만이면 장기 백테스트 부적합


def main() -> int:
    if not UNIVERSE_PATH.exists():
        print(f"실패: {UNIVERSE_PATH} 없음")
        return 1

    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    groups = [g for g in ("core", "leveraged") if g in universe]
    symbols = [r["symbol"] for g in groups for r in universe[g]]

    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT symbol,
                   COUNT(*)                                        AS n,
                   SUM(CASE WHEN volume = 0 THEN 1 ELSE 0 END)     AS zeros,
                   MIN(timestamp)::date                            AS first_dt,
                   MAX(timestamp)::date                            AS last_dt,
                   MAX(CASE WHEN volume = 0 THEN timestamp END)::date AS last_zero_dt
            FROM ohlcv
            WHERE time_frame = '1d' AND symbol = ANY(:s)
            GROUP BY symbol
        """), {"s": symbols}).all()

        stats = {r[0]: r for r in rows}

        first_valid = {}
        for sym, r in stats.items():
            if r[5] is None:
                first_valid[sym] = r[3]
                continue
            nxt = db.execute(text("""
                SELECT MIN(timestamp)::date FROM ohlcv
                WHERE symbol = :s AND time_frame = '1d' AND timestamp::date > :z
            """), {"s": sym, "z": r[5]}).scalar()
            first_valid[sym] = nxt or r[4]
    finally:
        db.close()

    missing, suspect, thin = [], [], []
    for group in groups:
        for rec in universe[group]:
            sym = rec["symbol"]
            st = stats.get(sym)
            if st is None:
                rec["bars_1d"] = 0
                rec["data_suspect"] = True
                missing.append(sym)
                continue
            n, zeros = st[1], int(st[2] or 0)
            ratio = zeros / n if n else 1.0
            rec["bars_1d"] = n
            rec["zero_bars"] = zeros
            rec["first_date"] = str(st[3])
            rec["last_date"] = str(st[4])
            rec["first_valid_date"] = str(first_valid[sym])
            rec["data_suspect"] = ratio > SUSPECT_ZERO_RATIO
            if rec["data_suspect"]:
                suspect.append((sym, n, zeros, ratio, rec["first_valid_date"]))
            if n < MIN_BARS_FOR_BACKTEST:
                thin.append((sym, n))

    universe["validated_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    universe["validation"] = {
        "suspect_zero_ratio": SUSPECT_ZERO_RATIO,
        "min_bars_for_backtest": MIN_BARS_FOR_BACKTEST,
        "missing": missing,
        "suspect": [s[0] for s in suspect],
        "thin": [t[0] for t in thin],
        "rule": "백테스트는 first_valid_date 이후 구간만 사용할 것",
    }
    UNIVERSE_PATH.write_text(
        json.dumps(universe, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"점검 대상 {len(symbols)}종목 (일봉 적재 {len(stats)}종목)")
    print(f"  미적재  : {len(missing)} {missing if missing else ''}")
    print(f"  suspect : {len(suspect)}")
    for sym, n, z, ratio, fv in suspect:
        print(f"    {sym:6} {n:5}봉 중 거래량0 {z:4} ({ratio * 100:.1f}%) → first_valid {fv}")
    print(f"  데이터 부족(<{MIN_BARS_FOR_BACKTEST}봉): {len(thin)}")
    for sym, n in thin:
        print(f"    {sym:6} {n}봉")
    print(f"\n갱신: {UNIVERSE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
