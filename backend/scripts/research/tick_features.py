"""틱 → 5분 특징봉. 한 번 만들고 계속 읽는다.

## 왜 (2026-08-31)

운동학 z_vel 밴드를 닫으면서(총엣지 +0.040~0.084% 대 통행료 0.072%) 값어치가
**밴드가 아니라 틱 미시구조**에 있다는 쪽으로 옮겼다. 실측 근거:

    잡음6 첫 사이클  롱 다리 초과 +0.071%p (유니버스 중앙과 같음 = 0)
                     숏 다리 초과 +5.226%p (358종목 중 최하위 2개)

틱을 매번 다시 읽으면 격자 한 번에 수십 분이 든다. 특징을 미리 접어 둔다.

## 담는 것 (5분 봉 · 종목별)

    cl    마지막 체결가
    ntr   체결 수
    qsum  체결 수량 합
    flip  가격 방향이 **뒤집힌** 횟수 (0 은 직전 방향 유지로 처리)
    dtm   체결 간격 평균(ms)      dts  체결 간격 표준편차(ms)
    tkb   테이커 매수 비율 = 1 - mean(is_buyer_maker)
    tkq   테이커 매수 수량 비율

⚠ 가짜 체결 — 바이낸스 @trade 가 price 0 · qty 0 을 섞어 보낸다(0.110%,
  유동성 클수록 많음). 최저가·로그수익률을 조용히 파괴한다. **여기서 거른다**.
⚠ flip 은 부호가 0 인 체결(같은 가격)을 직전 부호로 채운 뒤 센다. 안 그러면
  같은 가격 연속 체결이 전부 '뒤집힘 아님'으로 세어져 유동성 대리변수가 된다.

사용:
  python3 -m scripts.research.tick_features            # 없는 것만
  python3 -m scripts.research.tick_features --refresh
"""
from __future__ import annotations

import argparse
import logging
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
TICKS = ROOT / "runs" / "ticks"
OUT = ROOT / "runs" / "tickbars5m"
BAR_MS = 5 * 60 * 1000
BATCH = 50_000       # 배치 하나 ≈ 1.3 MB. 최고점을 이 값이 묶는다.
TCOLS = ["ts_ms", "price", "qty", "is_buyer_maker"]
log = logging.getLogger("tickfeat")


def _maxrun(v: np.ndarray) -> int:
    """가장 긴 동일값 연속 구간 길이."""
    if len(v) == 0:
        return 0
    b = np.flatnonzero(np.diff(v) != 0)
    edges = np.concatenate([[-1], b, [len(v)-1]])
    return int(np.diff(edges).max())


def _chunks(fs):
    """틱을 **배치 단위**로 흘려보낸다. 통째로 안 든다.

    ⚠ 파일이 시간순·안정정렬이라는 전제 위에 선다. 수집기와 아카이브 복구가
      둘 다 `kind="stable"` 로 쓰므로 참이다. 아니면 부르는 쪽이 소리내어
      멈춘다 — 조용히 틀린 값을 내면 안 된다.
    """
    for f in fs:
        for rb in pq.ParquetFile(f).iter_batches(batch_size=BATCH,
                                                 columns=TCOLS):
            ts = rb.column("ts_ms").to_numpy(zero_copy_only=False
                                             ).astype(np.int64, copy=False)
            pr = rb.column("price").to_numpy(zero_copy_only=False
                                             ).astype(np.float64, copy=False)
            qy = rb.column("qty").to_numpy(zero_copy_only=False
                                           ).astype(np.float64, copy=False)
            bm = rb.column("is_buyer_maker").to_numpy(zero_copy_only=False)
            # ⚠ 가짜 체결 제거 — price 0 · qty 0 (2026-08-27 규명)
            k = (pr > 0) & (qy > 0)
            if not k.all():
                ts, pr, qy, bm = ts[k], pr[k], qy[k], bm[k]
            if ts.size:
                yield ts, pr, qy, (~bm).astype(np.float32)


def one(sym: str) -> tuple[str, int]:
    """한 종목의 5분 특징봉. **틱을 통째로 들지 않는다.**

    ## 왜 (2026-09-01 · 민트 정지 사고)

    예전 판본은 7일치를 `pd.concat` 으로 통째로 펼친 뒤 `assign` 을 여섯 번
    이었다. 실측 최고 RSS **BTRUSDT 7,053 MB · ETHUSDT 4,535 MB** 다.
    기본 워커가 6이었으니 40 GB 를 요구했다 — 이 서버는 15 GB 다.
    같은 결함으로 오늘 서버가 통째로 멈췄고 실계좌가 54분 무방비였다.

    여기서는 배치마다 접고 버린다. 이월하는 상태는 다섯뿐이다 —
    직전 가격 · 직전 시각 · 직전 부호 · 직전 테이커방향 · 진행 중인 연속.

    ⚠ **분위수(q90·qmed)만은 누적이 안 된다.** 그래서 **열려 있는 구간
      하나치**의 체결대금만 들고 있는다. 5분 구간 하나는 가장 붐빌 때도
      수십만 건이라 몇 MB 다.

    ⚠ 산출물은 옛 판본과 **같아야 한다**. `_maxrun` 을 남겨둔 것은 아래
      벡터화를 검증하기 위해서다.
    """
    d = TICKS / sym
    fs = sorted(d.glob("*.parquet"))
    if not fs:
        return sym, 0
    # 구간 → [n, s_dt, s_dt2, flip, qsum, tkb, tkq_num, op, hi, lo, cl,
    #         qmax, qmax_tb, sw, run_max]
    acc: dict[int, list[float]] = {}
    qres: dict[int, tuple[float, float]] = {}
    qbuf: list[np.ndarray] = []
    qbin: int | None = None
    prev_px = prev_ts = None
    prev_tb = None
    prv_last = np.nan
    run_bin, run_val, run_len = None, -1.0, 0.0
    total = 0
    try:
        for ts, pr, qy, tb in _chunks(fs):
            if prev_ts is not None and int(ts[0]) < prev_ts:
                raise ValueError("시간순 아님")
            if ts.size > 1 and not bool((np.diff(ts) >= 0).all()):
                raise ValueError("시간순 아님")
            total += ts.size
            sg = np.sign(np.diff(pr, prepend=(prev_px if prev_px is not None
                                              else pr[0])))
            dt_ = np.diff(ts, prepend=(prev_ts if prev_ts is not None
                                       else int(ts[0]))).astype(np.float64)
            v = np.where(sg == 0, np.nan, sg)
            prv = pd.Series(np.concatenate([[prv_last], v])).ffill().to_numpy()[1:]
            psh = np.empty_like(prv)
            psh[0] = prv_last
            psh[1:] = prv[:-1]
            fl = ((sg != 0) & (psh != 0) & (sg != psh)).astype(np.float64)
            # 테이커 방향 전환 — 전역으로 세되 첫 원소는 0(옛 판본과 같다)
            sw = np.empty(tb.size, dtype=np.float64)
            sw[0] = 0.0 if prev_tb is None else float(tb[0] != prev_tb)
            sw[1:] = (tb[1:] != tb[:-1]).astype(np.float64)
            nv = pr * qy
            del sg, v, psh

            key = (ts // BAR_MS) * BAR_MS
            u, idx = np.unique(key, return_index=True)
            bounds = np.append(idx, key.size)
            for j in range(u.size):
                a, z = int(bounds[j]), int(bounds[j + 1])
                bk = int(u[j])
                e = acc.get(bk)
                if e is None:
                    e = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                         float(pr[a]), -np.inf, np.inf, 0.0,
                         -np.inf, np.nan, 0.0, 0.0]
                    acc[bk] = e
                dd = dt_[a:z]
                pp = pr[a:z]
                qq = qy[a:z]
                bb = tb[a:z]
                vv = nv[a:z]
                e[0] += float(z - a)
                e[1] += float(dd.sum())
                e[2] += float((dd * dd).sum())
                e[3] += float(fl[a:z].sum())
                e[4] += float(qq.sum())
                e[5] += float(bb.sum())
                e[6] += float((qq * bb).sum())
                e[8] = max(e[8], float(pp.max()))
                e[9] = min(e[9], float(pp.min()))
                e[10] = float(pp[-1])
                m = int(np.argmax(vv))
                if float(vv[m]) > e[11]:
                    e[11] = float(vv[m])
                    e[12] = float(bb[m])
                e[13] += float(sw[a:z].sum())
                # 최장 연속 — 구간이 바뀌면 끊긴다(옛 판본도 그랬다)
                carry = run_len if (run_bin == bk and run_val == float(bb[0])) else 0.0
                ch = np.flatnonzero(bb[1:] != bb[:-1]) + 1
                st = np.concatenate([[0], ch])
                ln = np.diff(np.concatenate([st, [bb.size]])).astype(np.float64)
                ln[0] += carry
                e[14] = max(e[14], float(ln.max()))
                run_bin, run_val, run_len = bk, float(bb[-1]), float(ln[-1])
                # ⚠ 분위수만 값을 들고 있어야 한다 — **열린 구간 하나치**
                if qbin is not None and bk != qbin:
                    arr = np.concatenate(qbuf)
                    qres[qbin] = (float(np.quantile(arr, 0.9)),
                                  float(np.median(arr)))
                    qbuf = []
                qbin = bk
                qbuf.append(vv)
            prev_px, prev_ts = float(pr[-1]), int(ts[-1])
            prev_tb, prv_last = float(tb[-1]), prv[-1]
            del ts, pr, qy, tb, dt_, fl, sw, nv, prv, key, u, idx, bounds
    except Exception as e:                                      # noqa: BLE001
        log.warning("%s 접기 실패: %s", sym, e)
        return sym, 0
    if qbin is not None and qbuf:
        arr = np.concatenate(qbuf)
        qres[qbin] = (float(np.quantile(arr, 0.9)), float(np.median(arr)))
    if total < 2_000 or not acc:
        return sym, 0

    ks = np.array(sorted(acc), dtype=np.int64)
    A = np.array([acc[int(k)] for k in ks], dtype=np.float64)
    n = A[:, 0]
    with np.errstate(invalid="ignore", divide="ignore"):
        var = (A[:, 2] - A[:, 1] * A[:, 1] / n) / (n - 1.0)
    q = np.array([qres[int(k)] for k in ks], dtype=np.float64)
    b = pd.DataFrame({
        "ts_ms": ks,
        # ⚠ OHLC 를 넣는다 — RSI·볼린저·ADX·스토캐스틱이 고가·저가를 쓴다.
        "op": A[:, 7], "hi": A[:, 8], "lo": A[:, 9], "cl": A[:, 10],
        "ntr": n, "qsum": A[:, 4], "flip": A[:, 3],
        "dtm": A[:, 1] / n,
        # ⚠ pandas `.std()` 기본은 표본표준편차(ddof=1)
        "dts": np.where(n > 1.0, np.sqrt(np.maximum(var, 0.0)), np.nan),
        "tkb": A[:, 5] / n,
        "tkq": A[:, 6] / np.maximum(A[:, 4], 1e-9),
        # ⚠ qty 의 **분포** — 합계만으로는 고래 한 건과 잔거래 천 건이
        #   구분이 안 된다. H1(고래 각인)에 필요하다.
        "qmax": A[:, 11], "q90": q[:, 0], "qmed": q[:, 1],
        "qmax_buy": A[:, 12],
        # ⚠ H5(테이커 연속) — `flip` 은 **가격** 방향 반전이고 이건
        #   **테이커** 방향 연속이다. 다른 것이다.
        "nrun": A[:, 13] + 1.0, "run_max": A[:, 14],
    })
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / f"{sym}.parquet.tmp"
    b.to_parquet(tmp, index=False)
    tmp.replace(OUT / f"{sym}.parquet")
    return sym, len(b)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--smoke", type=int, default=0)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    syms = [d.name for d in sorted(TICKS.iterdir()) if d.is_dir()]
    if not a.refresh:
        syms = [s for s in syms if not (OUT / f"{s}.parquet").exists()]
    if a.smoke:
        syms = syms[:a.smoke]
    if not syms:
        log.info("만들 것이 없다 — %d개 이미 있음", len(list(OUT.glob("*.parquet"))))
        return 0
    log.info("특징봉 — %d종목 · 워커 %d", len(syms), a.workers)
    t0, done, empty = time.time(), 0, 0
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, (s, n) in enumerate(ex.map(one, syms), 1):
            done += n
            empty += (n == 0)
            if i % 40 == 0 or i == len(syms):
                el = time.time()-t0
                log.info("[%d/%d] 봉 %s · 빈 %d · %.1f분 · 남은 %.1f분",
                         i, len(syms), f"{done:,}", empty, el/60,
                         (len(syms)-i)*el/i/60)
    log.info("완료 — %d종목 · 봉 %s · 빈 %d · %.1f분",
             len(syms), f"{done:,}", empty, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
