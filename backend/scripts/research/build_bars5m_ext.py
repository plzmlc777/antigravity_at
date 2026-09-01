"""확장 5분봉 캐시 — **아카이브에서 바로** 파케이로. DB를 거치지 않는다.

## 왜 (2026-09-01, 대표님 지시)

유니버스에 신규 상장 162종목을 편입했다([[유니버스 정책 개정]]). 그 종목들이
백테스트에도 들어가려면 과거 봉이 필요한데, `ohlcv_1m` 으로 받으면 **+20GB**
(71GB → 91GB)다. 세션 연구 하네스는 전부 5분봉 파케이만 읽으므로 그 길로 간다.

    ① DB ohlcv_1m 적재      +20.0 GB   전 구간 스캔이 이미 막혀 있다
    ② 5분봉 파케이만 생성    **+0.57 GB**  ← 이쪽

⚠ **`runs/bars5m` 을 덮지 않는다.** 지금까지의 모든 격자(세션 이월 4년 판정
  포함)가 그 240종목에 묶여 있다. 종목을 늘리면 과거 결과와 비교가 안 된다 —
  특히 신규 편입 114종목이 상장 90일~1년이라 **뽑히는 종목의 나이가 통째로
  젊어진다**(2026-08-31 실측: 나이는 조절 변수다). 새 디렉터리에 만든다.

## 어디서 받나

data.binance.vision 공개 아카이브. 무료·인증 불필요·속도 제한 없음.

    완결된 달  monthly/klines/<SYM>/1m/<SYM>-1m-YYYY-MM.zip
    당월       daily/klines/<SYM>/1m/<SYM>-1m-YYYY-MM-DD.zip

⚠ 달마다 형식이 다르다 — 헤더가 있는 달, 타임스탬프를 **마이크로초**로 주는
  달이 있다. `backfill_ohlcv_1m_archive.py` 의 규약을 그대로 따른다.

## 무엇을 만드나

`runs/bars5m_ext/<SYM>.parquet` — `runs/bars5m` 과 **같은 스키마**여야 한다.

    ts  h  l  c  v  n

⚠ `n` 은 5분 칸에 든 **1분봉 개수**(최대 5)다. 유동성 게이트가
  `n.rolling(12).median().shift(1) >= 3` 으로 쓴다. 5분봉 아카이브를 바로 받아
  `n=5` 로 채우면 거래 없는 구간이 살아 있는 것으로 잡힌다 — 그래서 **1분봉을
  받아 접는다**. DB 경로와 정의가 같아야 옛 종목과 새 종목이 섞이지 않는다.

사용:
  python3 -m scripts.research.build_bars5m_ext --smoke 3
  python3 -m scripts.research.build_bars5m_ext --workers 6
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

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "bars5m_ext"
SRC = ROOT / "runs" / "bars5m"           # 이미 있는 240종목 — 그대로 복사
MONTHLY = "https://data.binance.vision/data/futures/um/monthly/klines"
DAILY = "https://data.binance.vision/data/futures/um/daily/klines"
FAPI = "https://fapi.binance.com/fapi/v1/exchangeInfo"
log = logging.getLogger("bars5m_ext")


def parse(blob: bytes) -> list[tuple]:
    """아카이브 zip → (ts, o, h, l, c, v). 달마다 형식이 다르다."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        txt = z.read(z.namelist()[0]).decode("utf-8", errors="replace")
    out = []
    for r in csv.reader(io.StringIO(txt)):
        if not r or not r[0].strip().isdigit():
            continue                       # 헤더가 있는 달이 있다
        try:
            ts = int(r[0])
            if ts > 10**14:                # 마이크로초로 주는 달이 있다
                ts //= 1000
            out.append((ts, float(r[1]), float(r[2]), float(r[3]),
                        float(r[4]), float(r[5])))
        except (ValueError, IndexError):
            continue
    return out


def fetch(url: str) -> list[tuple]:
    try:
        with urllib.request.urlopen(url, timeout=180) as r:
            return parse(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []                      # 그 달에 상장 전이면 없다
        log.warning("%s HTTP %s", url.rsplit("/", 1)[-1], e.code)
        return []
    except Exception as exc:               # noqa: BLE001
        log.warning("%s: %s", url.rsplit("/", 1)[-1], exc)
        return []


def months(a: date, b: date):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def one(job) -> tuple[str, int, str]:
    sym, start, end = job
    p = OUT / f"{sym}.parquet"
    if p.exists():
        return sym, -1, "이미 있음"
    rows: list[tuple] = []
    # 완결된 달은 월별, 이번 달은 일별
    cur = date(end.year, end.month, 1)
    for y, m in months(start, end):
        if date(y, m, 1) >= cur:
            continue
        rows += fetch(f"{MONTHLY}/{sym}/1m/{sym}-1m-{y}-{m:02d}.zip")
    d = cur
    while d <= end:
        rows += fetch(f"{DAILY}/{sym}/1m/{sym}-1m-{d.isoformat()}.zip")
        d += timedelta(days=1)
    if len(rows) < 5_000:
        return sym, 0, f"1분봉 {len(rows)}개 — 건너뜀"
    t = pd.DataFrame(rows, columns=["ts_ms", "o", "h", "l", "c", "v"])
    t = t.drop_duplicates("ts_ms").sort_values("ts_ms")
    # ⚠ 5분 칸으로 접는다. `n` 은 칸에 든 1분봉 개수 — DB 경로와 같은 정의다.
    t["b"] = (t.ts_ms // 300_000) * 300_000
    g = t.groupby("b")
    b = pd.DataFrame({
        "h": g.h.max(), "l": g.l.min(), "c": g.c.last(),
        "v": g.v.sum(), "n": g.size(),
    }).reset_index()
    b["ts"] = pd.to_datetime(b.b, unit="ms", utc=True)
    b = b[["ts", "h", "l", "c", "v", "n"]]
    for col, dt in (("h", np.float32), ("l", np.float32), ("c", np.float32),
                    ("v", np.float32), ("n", np.int16)):
        b[col] = b[col].astype(dt)
    OUT.mkdir(parents=True, exist_ok=True)
    b.to_parquet(p, index=False)
    return sym, len(b), f"{b.ts.min().date()} ~ {b.ts.max().date()}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/binance_collect_universe.txt")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--smoke", type=int, default=0,
                   help="N종목만 — 본실행과 같은 경로로 먼저 확인한다")
    p.add_argument("--no-copy", action="store_true",
                   help="기존 bars5m 복사를 건너뛴다")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    syms = [s.strip().upper() for s in (ROOT/a.universe).read_text().split()
            if s.strip()]

    # ① 이미 만들어 둔 240종목은 그대로 복사 — 다시 받을 이유가 없다
    copied = 0
    if not a.no_copy:
        import shutil
        for f in SRC.glob("*.parquet"):
            if f.stem in syms and not (OUT / f.name).exists():
                shutil.copy2(f, OUT / f.name)
                copied += 1
    log.info("기존 캐시 복사 %d개 · %.1f분", copied, (time.time()-t0)/60)

    # ② 나머지는 아카이브에서 받는다. 상장일부터.
    with urllib.request.urlopen(FAPI, timeout=30) as r:
        info = {x["symbol"]: x for x in json.load(r)["symbols"]}
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    todo = []
    for s in syms:
        if (OUT / f"{s}.parquet").exists():
            continue
        x = info.get(s)
        if not x or not x.get("onboardDate"):
            log.warning("  %s 상장일 없음 — 건너뜀", s)
            continue
        ob = datetime.fromtimestamp(x["onboardDate"]/1000, timezone.utc).date()
        todo.append((s, ob, end))
    if a.smoke:
        todo = todo[:a.smoke]
    if not todo:
        log.info("받을 것이 없다 — %d개 완비", len(list(OUT.glob("*.parquet"))))
        return 0
    log.info("아카이브에서 받을 종목 %d · 워커 %d · %s 까지",
             len(todo), a.workers, end)

    done = bars = skip = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for sym, n, msg in ex.map(one, todo):
            done += 1
            if n > 0:
                bars += n
            elif n == 0:
                skip += 1
                log.info("  %-16s %s", sym, msg)
            if done % 10 == 0 or done == len(todo):
                el = time.time() - t0
                log.info("[%d/%d] 봉 %s · 건너뜀 %d · %.1f분 · 남은 %.1f분",
                         done, len(todo), f"{bars:,}", skip, el/60,
                         (len(todo)-done)*el/max(done, 1)/60)
    fs = sorted(OUT.glob("*.parquet"))
    tot = sum(f.stat().st_size for f in fs)
    log.info("완료 — %d종목 · 새 봉 %s · %.2f GB · %.1f분",
             len(fs), f"{bars:,}", tot/1e9, (time.time()-t0)/60)

    # ③ 검증 — 스키마와 겹침 구간이 기존 캐시와 같은지
    import random
    same = [f.stem for f in fs if (SRC / f.name).exists()]
    if same:
        s = random.Random(0).choice(same)
        a_ = pd.read_parquet(SRC / f"{s}.parquet")
        b_ = pd.read_parquet(OUT / f"{s}.parquet")
        log.info("검증 %s — 열 %s / %s · 행 %d / %d",
                 s, list(a_.columns), list(b_.columns), len(a_), len(b_))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
