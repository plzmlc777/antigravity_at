"""1분봉 — 틱을 **한 번만** 접어 두고 모두가 그것을 읽는다.

## 왜 (2026-09-01 · 민트 정지 사고)

페이퍼 갈래 24개가 각자 521종목의 틱을 5분마다 통째로 압축 해제했다.
메모리가 20 GB 를 요구해 **서버가 통째로 멈췄고** 실계좌가 54분 무방비였다.

흘려읽기로 갈래당 최고점을 1,129 → 258 MB 로 줄였지만, **같은 일을 14번
하는 구조**는 그대로였다(부하 12~17). 여기서 그것을 끊는다.

    지금    수집기 → 틱 → 갈래 14개가 각자 640만 틱을 5분마다 푼다
    바꾸면  수집기 → 틱 + **1분봉** → 갈래는 1분봉만 읽는다

⚠ **틱은 계속 남긴다.** 이번 세션에서만 틱에서 새 신호를 다섯 개 뽑았다
  (imp · skew · ac1 · rmz · 잡음). 전부 기존 아홉 열에 없던 것이고, 만들
  때마다 과거 틱에서 다시 계산했다. 틱을 버리면 **새 가설을 세워도 과거를
  못 잰다**. 1분봉은 틱의 5% 남짓(하루 54 MB)이라 붙여도 티가 안 난다.

## 열을 한 곳에 둔다

열 목록이 `tick_features.py` · `tick_synergy.build_all` · `kinematics_paper.
bars()` 세 곳에 흩어져 있어 `KeyError` 를 세 번 냈다(qmax · nrun ·
is_buyer_maker). 여기가 **유일한 정의**다. 늘릴 땐 여기만 고치고, 과거
봉은 `build_bars1m.py --rebuild` 로 다시 만든다.

## 접기와 마무리를 가른다

    fold_raw()   자료가 있는 분만. **저장은 이 형태로.**
    finalize()   빈 분을 채우고 종가를 ffill. **읽는 쪽에서 창에 맞춰.**

가르지 않으면 하루 전체로 채운 봉을 창으로 자를 때 앞쪽에 빈 분이 남아
옛 판본과 달라진다(옛 판본은 자료가 있는 첫 분에서 시작했다).
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

log = logging.getLogger("tickbars")

ROOT = Path(__file__).resolve().parents[2]
TICKS = ROOT / "runs" / "ticks"
BARS = ROOT / "runs" / "bars1m"

# ⚠ 틱에서 읽는 열 — 이걸 줄이면 신호가 조용히 결측이 된다
TICK_COLS = ["ts_ms", "price", "qty", "is_buyer_maker"]
# ⚠ 1분봉이 담는 열 — **유일한 정의**
BAR_FIELDS = ["cl", "ntr", "flip", "dtm", "dts", "qv", "q90", "qmed", "rmax"]
BATCH = 50_000          # 배치 하나 ≈ 1.3 MB. 최고점을 이 값이 묶는다.


class Unsorted(Exception):
    """파일이 시간순이 아니다 — 흘려읽기를 포기하고 통째로 읽어 정렬한다."""


def read_chunks(fs, since_ms: int):
    """구간에 드는 틱을 **배치 단위**로 흘려보낸다. 통째로 안 든다."""
    for f in fs:
        for rb in pq.ParquetFile(f).iter_batches(batch_size=BATCH,
                                                 columns=TICK_COLS):
            m = pc.greater_equal(rb.column("ts_ms"), since_ms)
            if not pc.sum(m).as_py():
                continue
            rb = rb.filter(m)
            yield _arrays(rb)


def _arrays(rb):
    ts = rb.column("ts_ms").to_numpy(zero_copy_only=False
                                     ).astype(np.int64, copy=False)
    pr = rb.column("price").to_numpy(zero_copy_only=False
                                     ).astype(np.float64, copy=False)
    qy = rb.column("qty").to_numpy(zero_copy_only=False
                                   ).astype(np.float64, copy=False)
    bm = rb.column("is_buyer_maker").to_numpy(zero_copy_only=False)
    k = (pr > 0) & (qy > 0)
    if not k.all():
        ts, pr, qy, bm = ts[k], pr[k], qy[k], bm[k]
    return ts, pr, pr * qy, (~bm).astype(np.int8)


def fold_raw(chunks, min_ticks: int = 500) -> pd.DataFrame | None:
    """배치들을 **분당 아홉 값**으로 접는다. 배치는 접고 나서 버린다.

    이월하는 상태는 넷뿐이다 — 직전 가격 · 직전 시각 · 직전 부호 · 진행 중인
    같은 방향 연속. 이것만 있으면 통째로 든 것과 **같은 값**이 나온다
    (실측: 36건 대조에서 8열 비트 일치, `qv` 만 상대 2~4e-16).

    ⚠ 빈 분을 안 채운다. 그건 `finalize()` 몫이다.
    """
    acc: dict[int, list[float]] = {}     # 분 → [n, s1, s2, flip, qsum, cl, rmax]
    qres: dict[int, tuple[float, float]] = {}
    qbuf: list[np.ndarray] = []
    qmin: int | None = None
    prev_px = prev_ts = None
    prv_last = np.nan
    run_min, run_val, run_len = None, -1, 0.0
    total = 0

    for ts, pr, qv, tb in chunks:
        if ts.size == 0:
            continue
        if prev_ts is not None and int(ts[0]) < prev_ts:
            raise Unsorted
        if ts.size > 1 and not bool((np.diff(ts) >= 0).all()):
            raise Unsorted
        total += ts.size
        # ⚠ 첫 배치는 `prepend=pr[0]` 이라 sg[0]=0 · dt[0]=0 이 된다.
        sg = np.sign(np.diff(pr, prepend=(prev_px if prev_px is not None
                                          else pr[0])))
        dt_ = np.diff(ts, prepend=(prev_ts if prev_ts is not None
                                   else int(ts[0]))).astype(np.float64)
        v = np.where(sg == 0, np.nan, sg)
        prv = pd.Series(np.concatenate([[prv_last], v])).ffill().to_numpy()[1:]
        pshift = np.empty_like(prv)
        pshift[0] = prv_last
        pshift[1:] = prv[:-1]
        fl = ((sg != 0) & (pshift != 0) & (sg != pshift)).astype(np.float64)
        del sg, v, pshift

        key = ts // 60_000
        u, idx = np.unique(key, return_index=True)
        bounds = np.append(idx, key.size)
        for j in range(u.size):
            a, z = int(bounds[j]), int(bounds[j + 1])
            mk = int(u[j])
            e = acc.get(mk)
            if e is None:
                e = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                acc[mk] = e
            d = dt_[a:z]
            e[0] += float(z - a)
            e[1] += float(d.sum())
            e[2] += float((d * d).sum())
            e[3] += float(fl[a:z].sum())
            e[4] += float(qv[a:z].sum())
            e[5] = float(pr[z - 1])          # 그 분의 마지막 종가
            # 같은 방향 연속 — 분이 바뀌면 끊긴다
            seg = tb[a:z]
            carry = run_len if (run_min == mk and run_val == int(seg[0])) else 0.0
            ch = np.flatnonzero(seg[1:] != seg[:-1]) + 1
            st = np.concatenate([[0], ch])
            ln = np.diff(np.concatenate([st, [seg.size]])).astype(np.float64)
            ln[0] += carry
            e[6] = max(e[6], float(ln.max()))
            run_min, run_val, run_len = mk, int(seg[-1]), float(ln[-1])
            # 분위수만은 누적이 안 된다 — **그 한 분치**만 들고 있는다
            #   (실측 최대 76,967틱 ≈ 0.6 MB)
            if qmin is not None and mk != qmin:
                arr = np.concatenate(qbuf)
                qres[qmin] = (float(np.quantile(arr, 0.9)), float(np.median(arr)))
                qbuf = []
            qmin = mk
            qbuf.append(qv[a:z])
        prev_px, prev_ts, prv_last = float(pr[-1]), int(ts[-1]), prv[-1]
        del ts, pr, qv, tb, dt_, fl, prv, key, u, idx, bounds

    if qmin is not None and qbuf:
        arr = np.concatenate(qbuf)
        qres[qmin] = (float(np.quantile(arr, 0.9)), float(np.median(arr)))
    if total < min_ticks or not acc:
        return None

    ks = np.array(sorted(acc), dtype=np.int64)
    a = np.array([acc[int(k)] for k in ks], dtype=np.float64)
    n = a[:, 0]
    with np.errstate(invalid="ignore", divide="ignore"):
        var = (a[:, 2] - a[:, 1] * a[:, 1] / n) / (n - 1.0)
    q = np.array([qres[int(k)] for k in ks], dtype=np.float64)
    return pd.DataFrame(
        {"cl": a[:, 5], "ntr": n, "flip": a[:, 3], "dtm": a[:, 1] / n,
         # ⚠ pandas `.std()` 기본은 표본표준편차(ddof=1). 모표준편차로 쓰면
         #   값이 조용히 작아진다.
         "dts": np.where(n > 1.0, np.sqrt(np.maximum(var, 0.0)), np.nan),
         "qv": a[:, 4], "q90": q[:, 0], "qmed": q[:, 1], "rmax": a[:, 6]},
        index=pd.to_datetime(ks * 60_000, unit="ms", utc=True))


def finalize(b: pd.DataFrame | None) -> pd.DataFrame | None:
    """빈 분을 채우고 종가를 ffill. **읽는 쪽에서 창에 맞춰** 부른다."""
    if b is None or b.empty:
        return None
    b = b.reindex(pd.date_range(b.index.min(), b.index.max(), freq="1min",
                                tz="UTC"))
    b["cl"] = b.cl.ffill()
    b["ntr"] = b.ntr.fillna(0.0)
    b["flip"] = b.flip.fillna(0.0)
    b["qv"] = b.qv.fillna(0.0)
    return b


def fold_frame(d: pd.DataFrame) -> pd.DataFrame | None:
    """이미 메모리에 있는 틱 표를 접는다 — **수집기 flush 경로**용.

    수집기는 flush 때 하루치를 이미 들고 있다. 여기서 접으면 파일을 다시
    읽는 비용이 0이다. 별도 프로세스를 두면 방금 쓴 파일을 다시 읽어야
    하므로 그보다 나쁘다.
    """
    if d is None or d.empty:
        return None
    ts = d.ts_ms.to_numpy(np.int64)
    pr = d.price.to_numpy(np.float64)
    qy = d.qty.to_numpy(np.float64)
    bm = d.is_buyer_maker.to_numpy(bool)
    k = (pr > 0) & (qy > 0)
    if not k.all():
        ts, pr, qy, bm = ts[k], pr[k], qy[k], bm[k]
    if ts.size == 0:
        return None
    return fold_raw([(ts, pr, pr * qy, (~bm).astype(np.int8))], min_ticks=1)


def fold_ticks(fs, since_ms: int) -> pd.DataFrame | None:
    """틱 파일에서 직접 접는다 — 봉이 없을 때의 되돌아갈 길.

    ⚠ `since_ms` 를 **분 경계로 내린다**. 안 그러면 창의 첫 분이 반쪽이
      되어 저장된 봉(온전한 분)과 달라지고, 그 한 분이 후행 중앙값을 타고
      `bump`·`imp` 를 중앙 1% · 최대 8% 움직였다(2026-09-01 실측).
      기준은 `read_bars` 와 같아야 한다 — 거기도 내린다.
    """
    since_ms = (since_ms // 60_000) * 60_000
    try:
        return fold_raw(read_chunks(fs, since_ms))
    except Unsorted:
        return _fold_buffered(fs, since_ms)


def _fold_buffered(fs, since_ms: int) -> pd.DataFrame | None:
    """통째로 읽고 **안정 정렬** — 파일이 시간순이 아닐 때만."""
    parts = []
    for f in fs:
        for rb in pq.ParquetFile(f).iter_batches(batch_size=BATCH,
                                                 columns=TICK_COLS):
            m = pc.greater_equal(rb.column("ts_ms"), since_ms)
            if pc.sum(m).as_py():
                parts.append(rb.filter(m))
    if not parts:
        return None
    t = pa.Table.from_batches(parts).to_pandas()
    del parts
    t = t[(t.price > 0) & (t.qty > 0)]
    if len(t) < 500:
        return None
    # ⚠ **안정** 정렬이어야 한다. pandas 기본 quicksort 는 같은 ms 안의 체결
    #   순서를 흩뜨린다(실측 BTRUSDT 중복 78.8%) — 종가·반전·연속이 바뀐다.
    t = t.sort_values("ts_ms", kind="stable")
    ts = t.ts_ms.to_numpy(np.int64)
    pr = t.price.to_numpy(np.float64)
    qv = pr * t.qty.to_numpy(np.float64)
    tb = (~t.is_buyer_maker.to_numpy(bool)).astype(np.int8)
    del t
    return fold_raw([(ts, pr, qv, tb)])


# ── 저장·적재 ────────────────────────────────────────────────
def bar_path(sym: str, day: str) -> Path:
    return BARS / sym / f"{day}.parquet"


def write_bars(sym: str, day: str, b: pd.DataFrame) -> int:
    """하루치 봉을 원자적으로 쓴다 — 읽는 쪽이 반쯤 쓴 파일을 보면 안 된다.

    ⚠ 틱 수집기는 이걸 안 지켜서 읽는 쪽이 `Parquet magic bytes not found`
      를 만난다. 그러면 그 종목이 그 주기에서 **조용히 사라진다**.

    ⚠⚠ `index.view("int64")` 를 쓰지 마라. pandas 3.0 의 DatetimeIndex 는
      **자기 단위**(여기선 ms)로 정수를 준다. ns 로 믿고 1e6 으로 나눴다가
      1788220 처럼 뭉개졌고 **서로 다른 분이 같은 ts_ms** 가 됐다. 조용히
      틀린 파일이 나오고 읽는 쪽은 그냥 빈 결과를 봤다.
      `to_numpy(dtype="datetime64[ms]")` 는 단위를 **명시**하므로 안전하다.
    """
    p = bar_path(sym, day)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = b.copy()
    ts = b.index.to_numpy(dtype="datetime64[ms]").astype(np.int64)
    # ⚠ 쓰기 직전에 확인한다. 위 실수는 **읽는 쪽에서야** 드러났다.
    if ts.size and (ts.min() < 1_000_000_000_000 or ts.max() > 4_000_000_000_000):
        raise ValueError(f"{sym} {day} ts_ms 가 시대를 벗어났다: "
                         f"{ts.min()}~{ts.max()} — 단위 환산을 확인하라")
    if ts.size > 1 and not bool((np.diff(ts) > 0).all()):
        raise ValueError(f"{sym} {day} ts_ms 가 증가하지 않는다 — 정밀도가 "
                         f"뭉개졌는지 확인하라(중복 {ts.size - np.unique(ts).size}건)")
    out.insert(0, "ts_ms", ts)
    tmp = p.with_suffix(".parquet.tmp")
    out.to_parquet(tmp, compression="zstd", index=False)
    tmp.replace(p)
    return len(out)


def read_bars(sym: str, since_ms: int, days: int = 2) -> pd.DataFrame | None:
    """저장된 봉에서 창을 잘라 온다. 없으면 None(부르는 쪽이 되돌아간다)."""
    fs = sorted((BARS / sym).glob("*.parquet"))[-days:]
    if not fs:
        return None
    try:
        d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    except Exception:                                          # noqa: BLE001
        return None
    if d.empty:
        return None
    d = d[d.ts_ms >= (since_ms // 60_000) * 60_000]
    if d.empty:
        return None
    d = d.drop_duplicates(subset=["ts_ms"], keep="last").sort_values("ts_ms")
    b = d[BAR_FIELDS].set_index(
        pd.to_datetime(d.ts_ms.to_numpy(), unit="ms", utc=True))
    b.index.name = None
    return b
