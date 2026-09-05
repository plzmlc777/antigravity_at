"""틱 복구 — 완결된 하루를 **무료 공개 아카이브**로 다시 채운다.

## 왜 (2026-09-01)

우리 수집본은 두 가지로 새고 있었다. 2026-08-31 아카이브 대조 실측:

    종목        아카이브      우리 저장   빠진 것   그중 삭제분
    ETHUSDT    5,365,953   3,736,251   30.4%    **28.04%**
    ZECUSDT    5,077,153   4,233,041   16.6%    **14.35%**
    COMPUSDT      84,345      73,132   13.3%      11.65%
    ONGUSDT    1,108,057   1,034,446    6.6%       4.97%
    ARBUSDT    1,036,854     969,214    6.5%       3.17%

  ① `drop_duplicates()` 가 **같은 (시각·가격·수량·방향)** 을 지웠다. 한
     주문이 같은 값의 대기주문 여럿을 같은 수량으로 체결시키면 거래 id 만
     다른 행이 여러 개 나온다 — 정상이고 흔하다. 종목마다 2.87~28.04% 로
     **열 배 차이**라 균일한 축소가 아니라 종목별 왜곡이었다.
  ② 재연결 공백이 1.6~3.3%p 더 먹었다("재연결 #79 — 공백 5.2초").

①은 수집기에서 제거했다. 이 도구는 **이미 새어 나간 과거**를 메운다.
아카이브는 삭제도 공백도 없으므로 우리 수집본보다 완전하다.

⚠ **오늘 날짜는 못 받는다.** 아카이브는 하루가 끝난 뒤 올라온다.
⚠ 복구한 파일은 `.archive` 표시를 남긴다. 다시 받지 않기 위해서다.
⚠ 복구 뒤 **1분봉을 다시 만들어야 한다** — `build_bars1m --days N`.
  틱 파일이 봉보다 새로우면 자동으로 다시 접는다.

사용:
  python3 -m scripts.binance.repair_ticks_archive --smoke 3
  python3 -m scripts.binance.repair_ticks_archive --days 2026-08-31
  python3 -m scripts.binance.repair_ticks_archive --workers 3
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.binance import tickbars                          # noqa: E402

log = logging.getLogger("tick_repair")
BASE = "https://data.binance.vision/data/futures/um/daily/trades"
COLS = ["id", "price", "qty", "quote_qty", "time", "is_buyer_maker"]


def fetch(sym: str, day: str, tries: int = 3) -> bytes | None:
    url = f"{BASE}/{sym}/{sym}-trades-{day}.zip"
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None                # 그날 상장 전 — 정상
            if k == tries - 1:
                raise
        except Exception:                                      # noqa: BLE001
            if k == tries - 1:
                raise
        time.sleep(2 * (k + 1))
    return None


def one(job):
    sym, day, force = job
    out = tickbars.TICKS / sym / f"{day}.parquet"
    mark = out.with_suffix(".archive")
    if mark.exists() and not force:
        return sym, day, 0, 0, "건너뜀"
    before = 0
    try:
        import pyarrow.parquet as pq
        if out.exists():
            before = pq.ParquetFile(out).metadata.num_rows
    except Exception:                                          # noqa: BLE001
        before = 0
    try:
        raw = fetch(sym, day)
    except Exception as e:                                     # noqa: BLE001
        return sym, day, before, 0, f"받기실패 {type(e).__name__}"
    if raw is None:
        return sym, day, before, 0, "아카이브없음"
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        name = z.namelist()[0]
        with z.open(name) as fh:
            first = fh.readline().decode("utf-8", "ignore")
        # ⚠ 달에 따라 머리글이 있기도 없기도 하다. 첫 칸으로 판별한다.
        has_hdr = first.split(",")[0].strip().lstrip("﻿") == "id"
        with z.open(name) as fh:
            d = pd.read_csv(fh, header=0 if has_hdr else None,
                            names=None if has_hdr else COLS)
        del raw, z
    except Exception as e:                                     # noqa: BLE001
        return sym, day, before, 0, f"해석실패 {type(e).__name__}"

    d.columns = [c.strip().lower().lstrip("﻿") for c in d.columns]
    t = d["time"].to_numpy(np.int64)
    # ⚠ 어떤 달은 **마이크로초**로 온다. 자릿수로 판별한다.
    if t.size and t.max() > 10 ** 15:
        t = t // 1000
    pr = d["price"].to_numpy(np.float64)
    qy = d["qty"].to_numpy(np.float64)
    bm = d["is_buyer_maker"].to_numpy()
    if bm.dtype == object or bm.dtype.kind in "US":
        bm = np.isin(bm, ["true", "True", "TRUE", True])
    bm = bm.astype(bool)
    del d
    # ⚠ 가짜 체결(가격·수량 0)은 여기서도 버린다 — 수집기와 같은 기준.
    k = (pr > 0) & (qy > 0)
    t, pr, qy, bm = t[k], pr[k], qy[k], bm[k]
    if t.size == 0:
        return sym, day, before, 0, "빈파일"
    o = np.argsort(t, kind="stable")       # ⚠ **안정** — 동률 순서를 지킨다
    n = pd.DataFrame({"ts_ms": t[o], "price": pr[o],
                      "qty": qy[o].astype(np.float32),
                      "is_buyer_maker": bm[o]})
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".parquet.tmp")
    n.to_parquet(tmp, compression="zstd", index=False)
    tmp.replace(out)
    mark.write_text(f"{day} {len(n)}\n")
    return sym, day, before, len(n), "복구"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--days", default="",
                   help="쉼표로. 비우면 틱 디렉터리의 **완결된** 날 전부")
    p.add_argument("--symbols", default="", help="쉼표로. 비우면 있는 것 전부")
    p.add_argument("--fill-missing", action="store_true",
                   help="그날 수집 안 한 종목도 받는다(유니버스 확장 이전 구멍)")
    p.add_argument("--universe", default="configs/binance_collect_universe.txt")
    p.add_argument("--workers", type=int, default=3,
                   help="⚠ 실계좌·페이퍼와 같은 서버다. 4를 넘기지 마라")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--force", action="store_true", help="이미 복구한 것도 다시")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    today = time.strftime("%Y-%m-%d", time.gmtime())
    have = sorted(d.name for d in tickbars.TICKS.iterdir() if d.is_dir())
    syms = ([s.strip().upper() for s in a.symbols.split(",") if s.strip()]
            or have)
    if a.fill_missing:
        uni = [s.strip().upper() for s in
               Path(a.universe).read_text().split() if s.strip()]
        syms = sorted(set(syms) | set(uni))
    if a.days:
        days = [x.strip() for x in a.days.split(",") if x.strip()]
    else:
        days = sorted({f.stem for s in have
                       for f in (tickbars.TICKS / s).glob("*.parquet")})
    # ⚠ 오늘은 아카이브에 없다. 넣으면 전 종목이 404 로 실패한다.
    days = [d for d in days if d < today]
    if a.smoke:
        syms = sorted(syms, key=lambda s: -sum(
            f.stat().st_size for f in (tickbars.TICKS / s).glob("*.parquet")
        ))[:a.smoke]
        days = days[-1:]

    jobs = [(s, d, a.force) for s in syms for d in days
            if a.fill_missing or (tickbars.TICKS / s / f"{d}.parquet").exists()]
    log.info("틱 복구 — 종목 %d · 날짜 %d(%s ~ %s) · 작업 %d · 워커 %d",
             len(syms), len(days), days[0] if days else "-",
             days[-1] if days else "-", len(jobs), a.workers)

    t0 = time.time()
    add = old = 0
    stat: dict[str, int] = {}
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, (sym, day, b, n, how) in enumerate(ex.map(one, jobs), 1):
            stat[how] = stat.get(how, 0) + 1
            if how == "복구":
                old += b
                add += n
            if i % 50 == 0 or i == len(jobs):
                el = time.time() - t0
                log.info("[%d/%d] 복구 %s → %s (+%.1f%%) · %s · %.1f분 · 남은 %.1f분",
                         i, len(jobs), f"{old:,}", f"{add:,}",
                         100 * (add - old) / max(old, 1),
                         " ".join(f"{k}{v}" for k, v in sorted(stat.items())),
                         el / 60, (len(jobs) - i) * el / i / 60)
    log.info("완료 — 이전 %s행 → 복구 %s행 (**+%.1f%%**) · %.1f분 · %s",
             f"{old:,}", f"{add:,}", 100 * (add - old) / max(old, 1),
             (time.time() - t0) / 60,
             " ".join(f"{k}{v}" for k, v in sorted(stat.items())))
    log.info("⚠ 1분봉을 다시 만들어라: "
             "python3 -m scripts.binance.build_bars1m --days %d", len(days) + 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
