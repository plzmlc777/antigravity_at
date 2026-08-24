"""지정가 손절이 **실제로 채워지는가** — 1분봉으로 되짚어 잰다.

배경 — 커널 모형은 띠(`sl_limit_offset`)가 있으면 **항상 체결**로 본다.
  간격 0.1/0.3/0.5% 의 청산 사유·체결수가 소수점까지 같은 이유다.
  가격만 하한으로 막힐 뿐 미체결 위험이 모형에 없다. 그래서 그 결과는
  **낙관 상한**이고, 간격 0(되돌아와야 체결)이 **비관 하한**이다.
  진짜 값은 둘 사이이고, 그 위치를 정하는 건 **체결률** 하나다.

측정 방법
  ① 원장의 손절 거래에서 방아쇠가 `T = exit_price`
  ② 하한 `F = T − 진입가 × 간격`
  ③ 진입~보유상한 구간의 1분봉을 읽어 `low <= T` 인 **첫 봉** = 방아쇠 순간
  ④ 체결 판정 — 매도 지정가 F 는 시장이 **F 이상**일 때 채워진다
       · 방아쇠 봉의 `low >= F` → 그 1분 내내 띠 안 → **즉시 체결**
       · 아니면 이후 봉에서 `high >= F` 인 첫 봉 → **지연 체결** (지연 기록)
       · 끝까지 없으면 → **미체결**

⚠ 1분봉도 그 안의 체결 순서는 모른다. 이건 상한·하한이지 실측이 아니다.
   다만 "띠를 지나갔다"와 "한 틱에 건너뛰었다"를 **분 단위로는** 가른다.
"""
from __future__ import annotations
import argparse, logging, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
from sqlalchemy import text
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.db.session import engine                       # noqa: E402

log = logging.getLogger("sl_fill")
Q = text("SELECT ts, high, low FROM ohlcv_1m "
         "WHERE symbol=:s AND ts >= :a AND ts <= :b ORDER BY ts")


def one(row):
    """(상태, 지연분, 방아쇠_저가_대비_하한초과bp) — 상태: hit0/hitN/miss/nodata."""
    sym, en, hz, trig, entry, off = row
    F = trig - entry * off
    if F <= 0:
        return ("nodata", np.nan, np.nan)
    with engine.connect() as c:
        r = c.execute(Q, {"s": sym, "a": en, "b": hz}).fetchall()
    if not r:
        return ("nodata", np.nan, np.nan)
    ts = [x[0] for x in r]
    hi = np.array([float(x[1]) for x in r])
    lo = np.array([float(x[2]) for x in r])
    t = int(np.argmax(lo <= trig)) if (lo <= trig).any() else -1
    if t < 0:
        return ("nodata", np.nan, np.nan)          # 원장의 손절을 1분봉이 확인 못 함
    if lo[t] >= F:
        return ("hit0", 0.0, 1e4 * (lo[t] - F) / F)
    later = np.nonzero(hi[t + 1:] >= F)[0]
    if len(later):
        j = int(later[0]) + t + 1
        return ("hitN", (ts[j] - ts[t]).total_seconds() / 60.0,
                1e4 * (lo[t] - F) / F)
    return ("miss", np.nan, 1e4 * (lo[t] - F) / F)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--trades", required=True, help="시장가 손절 원장 (exit_reason=sl)")
    p.add_argument("--offsets", default="0,0.001,0.003,0.005")
    p.add_argument("--hold-hours", type=float, default=48.0)
    p.add_argument("--sample", type=int, default=1200)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--seed", type=int, default=20260824)
    p.add_argument("--out", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    T = pd.read_csv(a.trades)
    if "placebo" in T.columns:
        T = T[T["placebo"] == "real"]
    T = T[T["exit_reason"].astype(str).str.lower() == "sl"].copy()
    log.info("손절 거래 %s건", f"{len(T):,}")
    if len(T) > a.sample:
        T = T.sample(a.sample, random_state=a.seed)
        log.info("표본 %s건", f"{len(T):,}")
    en = pd.to_datetime(T["entry_ts"])
    hz = en + pd.Timedelta(hours=a.hold_hours)
    offs = [float(x) for x in a.offsets.split(",") if x.strip()]

    rec = []
    for off in offs:
        rows = list(zip(T["symbol"], en, hz, T["exit_price"].astype(float),
                        T["entry_price"].astype(float), [off] * len(T)))
        out = []
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            for i, r in enumerate(ex.map(one, rows), 1):
                out.append(r)
                if i % 400 == 0:
                    log.info("간격 %g%% [%s/%s]", 100 * off, f"{i:,}", f"{len(rows):,}")
        st = pd.Series([o[0] for o in out])
        dl = pd.Series([o[1] for o in out], dtype=float)
        ok = st.isin(["hit0", "hitN"])
        n = int((st != "nodata").sum())
        rec.append(dict(간격=f"{100*off:g}%", 측정=n,
                        즉시=round(100 * (st == "hit0").sum() / max(n, 1), 1),
                        지연=round(100 * (st == "hitN").sum() / max(n, 1), 1),
                        미체결=round(100 * (st == "miss").sum() / max(n, 1), 1),
                        체결률=round(100 * ok.sum() / max(n, 1), 1),
                        지연중앙분=round(float(dl[st == "hitN"].median()), 1)
                        if (st == "hitN").any() else np.nan,
                        지연90분=round(float(dl[st == "hitN"].quantile(.9)), 1)
                        if (st == "hitN").any() else np.nan))
        log.info("간격 %g%% → 체결률 %.1f%% (즉시 %.1f / 지연 %.1f / 미체결 %.1f)",
                 100 * off, rec[-1]["체결률"], rec[-1]["즉시"],
                 rec[-1]["지연"], rec[-1]["미체결"])
    R = pd.DataFrame(rec)
    print("\n■ 지정가 손절 체결률 — 1분봉 되짚기 (단위 %)")
    print(R.to_string(index=False))
    print("\n  즉시  = 방아쇠 1분봉이 띠 안에서 멈춤 → 그 자리에서 채워짐")
    print("  지연  = 띠를 지났다가 되돌아와 채워짐 (지연중앙분 = 걸린 시간)")
    print("  미체결 = 보유상한까지 되돌아오지 않음 → RSI청산·만료로 넘어감")
    print("\n※ 1분봉도 그 안의 체결 순서는 모른다. 분 단위 상한·하한이다.")
    if a.out:
        R.to_csv(a.out, index=False)
        log.info("저장 %s", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
