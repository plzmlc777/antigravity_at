"""1분봉을 바이낸스 공식 아카이브와 대조하고, 어긋난 행을 고친다.

⚠ 왜 필요한가 (2026-08-15 발견)
    `ohlcv_hourly` 를 아카이브에서 받아 `ohlcv_daily` 와 대조하다 드러났다.
    아카이브 1h 집계 == 아카이브 1d 원본(완전 일치)인데, 우리 일봉은
    **280종목 중 13종목**에서 어긋났고 **그 13종목이 전부 신상저격수 세션
    종목**이었다. 일반 수집 경로는 멀쩡하고 라이브 세션 백필만 틀렸다.

    실측 (REUSDT 2026-06-20 UTC):
        우리      1,440봉 · 시가 0.8885 · 고가 1.0680 · 저가 0.7421 · 종가 1.0013
        아카이브             시가 0.8885 · 고가 **1.0970** · 저가 **0.7817** · 종가 1.0025

    봉 개수도 1440 이고 타임스탬프도 정확하다. **아무것도 고장 나 보이지 않는다.**
    그래서 대조 없이는 영원히 안 잡힌다.

⚠ 안전 장치
    · 기본은 **점검만** 한다. 쓰려면 `--commit` 을 명시해야 한다.
    · 쓰기 전에 현재 값을 **백업 파일**로 남긴다(복구 가능).
    · DELETE 하지 않는다 — 어긋난 행을 **UPDATE** 하고 없는 행만 INSERT 한다.
      (`.claude/references/protocols.md`: DROP/RESET 금지)
    · 실거래 중인 종목이 포함될 수 있다. 과거 봉을 고치면 다음 사이클의 정본
      판단이 바뀔 수 있다 — 그게 **의도**다(틀린 가격으로 판단하던 것을 멈춤).

⚠ `volume` 도 고친다 (2026-08-15 2차)
    1차에서는 "BIGINT 라 어차피 잘린다"며 가격만 고쳤다. **그건 틀렸다.**
    근본 원인이 **KST 9시간 밀림**이라 거래량도 9시간 전 것이 붙어 있었다.
    가격만 고치면 **가격은 맞고 거래량은 틀린** 더 나쁜 상태가 된다.
    조기청산(`vol_cliff`)이 거래량으로 판정하므로 반드시 같이 고쳐야 한다.
    비교는 정수로 반올림해서 한다(스키마가 BIGINT).

사용:
  python3 -m scripts.repair_ohlcv_1m_from_archive --symbols REUSDT          # 점검만
  python3 -m scripts.repair_ohlcv_1m_from_archive --lifecycle --commit      # 적용
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("repair_1m")

BASE = "https://data.binance.vision/data/futures/um"
BACKUP_DIR = ROOT / "runs" / "research_track" / "ohlcv_repair"
WORKERS = 6
REL_TOL = 1e-6          # 부동소수 표현 차이는 불일치가 아니다

LIFECYCLE_SYMS = [
    "DATAIPUSDT", "REUSDT", "OUSDT", "CAPUSDT", "GRVTUSDT", "ARXUSDT",
    "BTWUSDT", "GRAMUSDT", "SLXUSDT", "ZESTUSDT", "CTRUSDT", "DOSUSDT",
    "PHAROSUSDT", "STARUSDT", "AIGENSYNUSDT",
]


def _fetch(url: str) -> list[list] | None:
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            blob = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except Exception as exc:
        log.warning("%s: %s", url.rsplit("/", 1)[-1], exc)
        return None
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        text = z.read(z.namelist()[0]).decode("utf-8", errors="replace")
    out = []
    for r in csv.reader(io.StringIO(text)):
        if not r or not r[0].strip().isdigit():
            continue
        try:
            ts = int(r[0])
            if ts > 10 ** 14:
                ts //= 1000
            out.append((ts, float(r[1]), float(r[2]), float(r[3]),
                        float(r[4]), float(r[5])))
        except (ValueError, IndexError):
            continue
    return out


def archive_1m(sym: str, d0: date, d1: date) -> dict[int, tuple]:
    """{ts_ms: (o,h,l,c)}. 완결된 달은 월별, 당월은 일별."""
    today = date.today()
    jobs = []
    y, m = d0.year, d0.month
    while (y, m) <= (d1.year, d1.month):
        if (y, m) == (today.year, today.month):
            cur = max(d0, date(y, m, 1))
            while cur <= min(d1, today):
                jobs.append(f"{BASE}/daily/klines/{sym}/1m/{sym}-1m-{cur.isoformat()}.zip")
                cur += timedelta(days=1)
        else:
            jobs.append(f"{BASE}/monthly/klines/{sym}/1m/{sym}-1m-{y}-{m:02d}.zip")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        chunks = list(ex.map(_fetch, jobs))
    out = {}
    for c in chunks:
        for ts, o, h, l, cl, v in (c or []):
            out[ts] = (o, h, l, cl, v)
    return out


def close_enough(a: float, b: float) -> bool:
    if a == b:
        return True
    d = abs(a - b)
    return d <= REL_TOL * max(abs(a), abs(b), 1e-12)


def main() -> int:
    p = argparse.ArgumentParser(description="1분봉 아카이브 대조·복구")
    p.add_argument("--symbols", default="")
    p.add_argument("--lifecycle", action="store_true",
                   help="신상저격수 세션 종목 전체")
    p.add_argument("--commit", action="store_true",
                   help="실제로 쓴다. 없으면 점검만")
    p.add_argument("--limit-days", type=int, default=0,
                   help="종목당 최근 N일만 (0=전체)")
    a = p.parse_args()

    from sqlalchemy import text

    from app.db.session import engine

    syms = ([s.strip().upper() for s in a.symbols.split(",") if s.strip()]
            or (LIFECYCLE_SYMS if a.lifecycle else []))
    if not syms:
        raise SystemExit("--symbols 또는 --lifecycle 이 필요하다")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode = "적용" if a.commit else "**점검만**"
    print("=" * 96)
    print(f"1분봉 아카이브 대조 — 종목 {len(syms)} · 모드 {mode}")
    if not a.commit:
        print("  쓰려면 --commit 을 붙여라. 지금은 아무것도 바꾸지 않는다.")
    print("=" * 96)
    print(f"  {'종목':<14}{'DB행':>9}{'아카이브':>10}{'일치':>9}{'불일치':>9}"
          f"{'DB없음':>9}{'아카없음':>10}{'불일치%':>9}")
    print("  " + "-" * 82)

    summary, t0 = {}, time.time()
    with engine.connect() as conn:
        for sym in syms:
            rows = conn.execute(text(
                "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
                "WHERE symbol = :s AND time_frame = '1m' ORDER BY timestamp"),
                {"s": sym}).fetchall()
            if not rows:
                print(f"  {sym:<14}      DB 에 1분봉 없음 — 건너뜀")
                continue
            d0, d1 = rows[0][0].date(), rows[-1][0].date()
            if a.limit_days:
                d0 = max(d0, d1 - timedelta(days=a.limit_days))
                rows = [r for r in rows if r[0].date() >= d0]
            arch = archive_1m(sym, d0, d1)
            if not arch:
                print(f"  {sym:<14}      아카이브 없음 — 건너뜀")
                continue

            same = diff = 0
            fixes, backup = [], []
            db_ts = set()
            for ts_dt, o, h, l, c, v in rows:
                ms = int(ts_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
                db_ts.add(ms)
                ref = arch.get(ms)
                if ref is None:
                    continue
                if (all(close_enough(x, y) for x, y in
                        zip((o, h, l, c), ref[:4]))
                        and int(v) == int(round(ref[4]))):
                    same += 1
                    continue
                diff += 1
                backup.append({"symbol": sym, "ts": ts_dt.isoformat(),
                               "old": [o, h, l, c, v], "new": list(ref)})
                fixes.append({"s": sym, "t": ts_dt, "o": ref[0], "h": ref[1],
                              "l": ref[2], "c": ref[3],
                              "v": int(round(ref[4]))})
            missing_db = len(set(arch) - db_ts)      # 아카이브엔 있고 DB엔 없음
            missing_ar = len(db_ts - set(arch))      # DB엔 있고 아카이브엔 없음
            tot = same + diff
            summary[sym] = {"db": len(rows), "arch": len(arch), "same": same,
                            "diff": diff, "missing_db": missing_db,
                            "missing_arch": missing_ar,
                            "diff_pct": 100 * diff / max(tot, 1)}
            print(f"  {sym:<14}{len(rows):>9,}{len(arch):>10,}{same:>9,}"
                  f"{diff:>9,}{missing_db:>9,}{missing_ar:>10,}"
                  f"{100*diff/max(tot,1):>8.1f}%")

            if a.commit and fixes:
                bp = BACKUP_DIR / f"{sym}_{stamp}.jsonl"
                with open(bp, "w") as f:
                    for b in backup:
                        f.write(json.dumps(b, ensure_ascii=False) + "\n")
                for fx in fixes:
                    conn.execute(text(
                        "UPDATE ohlcv SET open=:o, high=:h, low=:l, close=:c, "
                        "volume=:v "
                        "WHERE symbol=:s AND time_frame='1m' AND timestamp=:t"),
                        fx)
                conn.commit()
                log.info("  %s — %d행 수정 · 백업 %s", sym, len(fixes), bp.name)

    tot_diff = sum(v["diff"] for v in summary.values())
    tot_same = sum(v["same"] for v in summary.values())
    print("  " + "-" * 82)
    print(f"  합계 — 일치 {tot_same:,} · **불일치 {tot_diff:,}** "
          f"({100*tot_diff/max(tot_same+tot_diff,1):.2f}%) · {time.time()-t0:.0f}초")
    if a.commit:
        print(f"  백업 → {BACKUP_DIR}")
        print(f"  ⚠ `ohlcv_daily` 를 이 종목들에 대해 **재생성**해야 한다:")
        print(f"     python3 -m scripts.build_ohlcv_daily --symbols {','.join(syms[:3])},...")
    else:
        print("  → 적용하려면 --commit")
    print("=" * 96)
    return 0


if __name__ == "__main__":
    sys.exit(main())
