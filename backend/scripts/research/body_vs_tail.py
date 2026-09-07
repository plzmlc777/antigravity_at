"""몸통도 이기는 설정이 있나 — 거래별 중앙값·상5제외를 격자로 잰다.

## 왜

페이퍼 8갈래 중 **중앙값과 상5제외가 둘 다 양수인 것은 UTC01 하나**인데, 그것은
아카이브 2,156일 검정에서 48칸 전부 음수로 부정됐다. 나머지는 전부 **몸통은 지고
꼬리로 버는** 구조다(탄성저울 중앙 +0.47% / 상5제외 -0.108%).

기존 하네스(`kine_band_hold` · `imp_tp_grid`)는 **날별 묶음 수익**만 낸다. 그래서
"거래 절반이 이기나"를 못 묻는다. 여기서는 **거래 단위 분포**를 같이 낸다.

    거래당    평균
    중앙      절반이 이 값을 넘는다 → **몸통**
    상5제외   상위 5% 를 뺀 평균 → **꼬리를 뺀 몸통**
    일별 t    유의성은 여전히 날 단위로 (겹친 앵커 때문 · 교훈#92)

## 판정

    중앙 > 실거래 수수료(0.1003%)  →  몸통이 통행료를 넘는다
    상5제외 > 0                    →  꼬리 없이도 남는다
    둘 다 만족하는 칸이 있는가?

## 기질

두 앵커 표를 재사용한다(적재 안 함).
    kine  runs/research_track/kine_band_hold/panel_all.parquet
    imp   runs/research_track/imp_tp_grid/panel_all.parquet

사용:
    python3 -m scripts.research.body_vs_tail
    python3 -m scripts.research.body_vs_tail --holds 480 --nsides 1,3
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("body_tail")

STOP = 0.05
FEE_PAPER = 0.072
FEE_LIVE = 0.1003
Z_LO, Z_HI, ACC_MAX = -1.25, -0.25, 0.5


def stats(trades: np.ndarray, daily: np.ndarray, fee: float) -> dict:
    n = len(trades)
    k = max(1, int(np.ceil(n * 0.05)))
    ex5 = np.sort(trades)[::-1][k:].mean() if n > k else np.nan
    dt = (daily.mean() / (daily.std(ddof=1) / np.sqrt(len(daily)))
          if len(daily) > 2 and daily.std(ddof=1) > 0 else np.nan)
    return {"거래": n, "거래당": trades.mean(), "중앙": np.median(trades),
            "상5제외": ex5, "승률%": 100 * (trades > 0).mean(),
            "손절%": 100 * (trades <= -STOP * 100 - fee + 1e-9).mean(),
            "일평균%": daily.mean(), "일별t": dt, "날": len(daily)}


def run_kine(p, holds, nsides, fee) -> list[dict]:
    zv, za, day = p.z_vel.to_numpy(), p.z_acc.to_numpy(), p.day.to_numpy()
    okL = (zv >= Z_LO) & (zv <= Z_HI) & (za < ACC_MAX)
    okS = (zv >= -Z_HI) & (zv <= -Z_LO) & (za > -ACC_MAX)
    order = np.lexsort((zv, day))
    day_s = day[order]
    bnd = np.flatnonzero(np.r_[True, day_s[1:] != day_s[:-1], True])
    out = []
    for H in holds:
        fwd = p[f"fwd{H}"].to_numpy(); lor = p[f"lo{H}"].to_numpy(); hir = p[f"hi{H}"].to_numpy()
        for terc in ("하", "중", "상", "전체"):
            def bmask(ok, e0, e1, flip):
                if terc == "전체":
                    return ok
                pos = (zv - e0) / (e1 - e0)
                if flip:
                    pos = 1.0 - pos
                a, b = {"하": (0, 1 / 3), "중": (1 / 3, 2 / 3), "상": (2 / 3, 1)}[terc]
                return ok & (pos >= a) & (pos <= b)
            mL, mS = bmask(okL, Z_LO, Z_HI, False), bmask(okS, -Z_HI, -Z_LO, True)
            for ns in nsides:
                tr, dl = [], []
                for a, b in zip(bnd[:-1], bnd[1:]):
                    sl = order[a:b]
                    L = sl[mL[sl]]; S = sl[mS[sl]]
                    if len(L) < ns or len(S) < ns:
                        continue
                    L = L[np.argsort(zv[L])][:ns]
                    S = S[np.argsort(-zv[S])][:ns]
                    rl = np.where(lor[L] <= -STOP, -STOP, fwd[L])
                    rs = np.where(hir[S] >= STOP, -STOP, -fwd[S])
                    net = np.r_[rl, rs] * 100.0 - fee
                    tr.append(net); dl.append(net.mean())
                if len(dl) < 30:
                    continue
                out.append({"신호": "kine", "보유": H, "구분": terc, "다리": ns,
                            **stats(np.concatenate(tr), np.asarray(dl), fee)})
    return out


def run_imp(p, holds, nsides, fee) -> list[dict]:
    imp, day = p.imp.to_numpy(), p.day.to_numpy()
    order = np.lexsort((imp, day))
    day_s = day[order]
    bnd = np.flatnonzero(np.r_[True, day_s[1:] != day_s[:-1], True])
    out = []
    for H in holds:
        fwd = p[f"fwd{H}"].to_numpy(); lor = p[f"lo{H}"].to_numpy(); hir = p[f"hi{H}"].to_numpy()
        for mode in ("short", "both"):
            for ns in nsides:
                tr, dl = [], []
                for a, b in zip(bnd[:-1], bnd[1:]):
                    sl = order[a:b]
                    if len(sl) < 2 * ns:
                        continue
                    S = sl[:ns]; L = sl[-ns:]
                    rs = np.where(hir[S] >= STOP, -STOP, -fwd[S])
                    if mode == "short":
                        net = rs * 100.0 - fee
                    else:
                        rl = np.where(lor[L] <= -STOP, -STOP, fwd[L])
                        net = np.r_[rl, rs] * 100.0 - fee
                    tr.append(net); dl.append(net.mean())
                if len(dl) < 30:
                    continue
                out.append({"신호": "imp", "보유": H, "구분": mode, "다리": ns,
                            **stats(np.concatenate(tr), np.asarray(dl), fee)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--holds", default="120,240,480")
    ap.add_argument("--nsides", default="1,3,5")
    ap.add_argument("--fee", type=float, default=FEE_PAPER)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    holds = [int(x) for x in a.holds.split(",")]
    nsides = [int(x) for x in a.nsides.split(",")]

    rows = []
    for name, path, fn in (
            ("kine", "runs/research_track/kine_band_hold/panel_all.parquet", run_kine),
            ("imp", "runs/research_track/imp_tp_grid/panel_all.parquet", run_imp)):
        f = ROOT / path
        if not f.exists():
            log.warning("%s 앵커 표 없음 — 건너뜀 (%s)", name, f)
            continue
        p = pd.read_parquet(f)
        log.info("%s 앵커 %s행", name, f"{len(p):,}")
        rows += fn(p, holds, nsides, a.fee)

    r = pd.DataFrame(rows).sort_values("중앙", ascending=False)
    pd.set_option("display.width", 240)
    print("\n■ 거래 단위 분포 — 수수료 %.3f%% 반영 · 정렬: 중앙값" % a.fee)
    print(r.to_string(index=False, float_format=lambda x: f"{x:9.3f}"))

    print("\n■ 판정")
    body = r[r["중앙"] > 0]
    both = r[(r["중앙"] > 0) & (r["상5제외"] > 0)]
    live = r[(r["중앙"] > FEE_LIVE - a.fee) & (r["상5제외"] > 0)]
    print("  중앙 > 0            %d / %d 칸" % (len(body), len(r)))
    print("  중앙 > 0 **및** 상5제외 > 0   **%d 칸**" % len(both))
    if len(both):
        print(both.to_string(index=False, float_format=lambda x: f"{x:9.3f}"))
    print("  실거래 수수료(%.4f%%)까지 물려도 둘 다 양수  **%d 칸**" % (FEE_LIVE, len(live)))
    d = ROOT / "runs/research_track/body_vs_tail"
    d.mkdir(parents=True, exist_ok=True)
    r.to_csv(d / "observed.csv", index=False)
    log.info("기록 — %s", d / "observed.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
