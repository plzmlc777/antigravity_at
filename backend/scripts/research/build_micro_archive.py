"""아카이브 → **미시구조 1분봉**. 틱을 저장하지 않고 접어서만 남긴다.

## 왜 (2026-09-02)

`bump`(방향 반전율)·`irr`(도착 불규칙성)·`rmax` 같은 미시구조 지표는 틱에서만
나오는데, 우리 수집본은 **7일치뿐**이다. 그래서 잡음 계열과 H1~H5 판정이
전부 7일 위에 서 있었다.

data.binance.vision 에 **상장일부터 전부** 있고 **월간 파일**이라 종목당
14~15개면 된다. 실측(ZORAUSDT 403일): 다운로드+접기 **4분 · 28.5 MB**.

⚠ **틱을 저장하지 않는다.** 한 달씩 받아 1분봉으로 접고 버린다.
⚠ 접는 규칙은 `tickbars.fold_raw` 그대로 — 수집기 경로와 같은 값이어야
  최근 7일과 이어 붙는다.
⚠ 종목 선택은 **성과와 무관한 기준**으로 하라. 전략이 잘 잡은 종목을
  고르면 그 자체가 선택 편향이다(2026-09-02: ZORA 만 보고 p 0.021 로
  통과했는데 56종목 전부 보니 우연 수준이었다).

사용:
  python3 -m scripts.research.build_micro_archive --symbols A,B --workers 4
  python3 -m scripts.research.build_micro_archive --stride 10 --workers 4
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

log = logging.getLogger("micro_arch")
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "micro1m"
BM = "https://data.binance.vision/data/futures/um/monthly/trades"
COLS = ["id", "price", "qty", "quote_qty", "time", "is_buyer_maker"]


def _chunks(fh, hdr):
    """월간 CSV 를 **청크로 흘려** 읽는다. 통째로 안 든다.

    ⚠ 한 달치를 `pd.read_csv` 로 통째로 올렸다가 워커가 죽었다
      (BrokenProcessPool · 2026-09-02). 대형 종목은 한 달에 수천만 건이다.
      오늘 아침 `tick_features` 와 **같은 병**이다.
    ⚠ 아카이브는 거래 id 순 = 시간순이다. 청크 경계를 넘어도 순서가 유지되므로
      `fold_raw` 의 이월 상태가 그대로 맞는다. 어긋나면 fold_raw 가 소리낸다.
    """
    for d in pd.read_csv(fh, header=hdr, names=None if hdr == 0 else COLS,
                         chunksize=2_000_000):
        d.columns = [c.strip().lower().lstrip("\ufeff") for c in d.columns]
        ts = d["time"].to_numpy(np.int64)
        if ts.size and ts.max() > 10 ** 15:
            ts = ts // 1000          # ⚠ 어떤 달은 마이크로초다
        pr = d["price"].to_numpy(np.float64)
        qy = d["qty"].to_numpy(np.float64)
        bm = d["is_buyer_maker"].to_numpy()
        if bm.dtype == object or bm.dtype.kind in "US":
            bm = np.isin(bm, ["true", "True", "TRUE", True])
        del d
        k = (pr > 0) & (qy > 0)
        ts, pr, qy, bm = ts[k], pr[k], qy[k], bm.astype(bool)[k]
        if ts.size == 0:
            continue
        o = np.argsort(ts, kind="stable")      # ⚠ **안정** 정렬
        ts, pr, qy, bm = ts[o], pr[o], qy[o], bm[o]
        yield ts, pr, pr * qy, (~bm).astype(np.int8)


def one(job):
    sym, months, force = job
    out = OUT / f"{sym}.parquet"
    if out.exists() and not force:
        return sym, 0, "건너뜀"
    parts = []
    for m in months:
        try:
            raw = urllib.request.urlopen(f"{BM}/{sym}/{sym}-trades-{m}.zip",
                                         timeout=900).read()
        except urllib.error.HTTPError:
            continue                       # 그달 상장 전 — 정상
        except Exception:                                      # noqa: BLE001
            continue
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
            nm = z.namelist()[0]
            with z.open(nm) as fh:
                first = fh.readline().decode("utf-8", "ignore")
            hdr = 0 if first.split(",")[0].strip().lstrip("\ufeff") == "id" else None
            with z.open(nm) as fh:
                b = tickbars.fold_raw(_chunks(fh, hdr), min_ticks=1)
        except Exception:                                      # noqa: BLE001
            b = None
        finally:
            raw = None
        if b is not None:
            parts.append(b.reset_index().rename(columns={"index": "ts"}))
    if not parts:
        return sym, 0, "빈 결과"
    B = pd.concat(parts, ignore_index=True).drop_duplicates("ts").sort_values("ts")
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".parquet.tmp")
    B.to_parquet(tmp, compression="zstd", index=False)
    tmp.replace(out)
    return sym, len(B), "완성"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols", default="")
    p.add_argument("--stride", type=int, default=0,
                   help="유동성 순서에서 N번째마다 — **성과와 무관한** 표본 추출")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--from-month", default="2025-07")
    p.add_argument("--workers", type=int, default=4,
                   help="⚠ 실계좌·페이퍼와 같은 서버다. 4를 넘기지 마라")
    p.add_argument("--force", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if a.symbols:
        syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    else:
        # ⚠ 오늘 틱 파일 크기 = 유동성 대리. **성과와 무관**하다.
        cand = sorted((d.name for d in tickbars.TICKS.iterdir() if d.is_dir()),
                      key=lambda s: -sum(f.stat().st_size
                                         for f in (tickbars.TICKS/s).glob("*.parquet")))
        syms = cand[::max(a.stride, 1)][:a.limit]
    # ⚠ 시작을 tz-aware 로 맞춘다 — 한쪽만 aware 면 pandas 가 죽는다
    months = pd.date_range(pd.Timestamp(f"{a.from_month}-01", tz="UTC"),
                           pd.Timestamp.now(tz="UTC"),
                           freq="MS").strftime("%Y-%m").tolist()
    log.info("미시구조 적재 — 종목 %d · 월 %d(%s~%s) · 워커 %d",
             len(syms), len(months), months[0], months[-1], a.workers)
    log.info("대상: %s", " ".join(syms[:12]) + (" …" if len(syms) > 12 else ""))

    t0, done, rows = time.time(), 0, 0
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, (s, k, how) in enumerate(
                ex.map(one, [(s, months, a.force) for s in syms]), 1):
            done += (how == "완성"); rows += k
            el = time.time() - t0
            log.info("[%d/%d] %s %s %s봉 · %.0f분 · 남은 %.0f분",
                     i, len(syms), s, how, f"{k:,}", el/60,
                     (len(syms)-i)*el/i/60)
    sz = sum(f.stat().st_size for f in OUT.glob("*.parquet"))/1048576
    log.info("완료 — 완성 %d · 봉 %s · %.0f MB · %.1f분",
             done, f"{rows:,}", sz, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
