"""cvd_divergence 정련 — 조건부 엣지 지형을 그린 뒤 조건을 고른다.

배경 (2026-08-09):
  `ultra_signal_scan.py` 가 8신호 x 3z x 6보유 = 180칸을 283종목에 돌린 결과,
  표본이 크면서(1만건) breadth>0.55 이고 net>0 인 칸은 **cvd_divergence 240분**
  하나뿐이었다. gross +12.23bp / 테이커 마찰 10.83bp → net +1.40bp (t 0.43).
  메이커 마찰 4bp 를 가정하면 +8.23bp (t 2.52) 가 되지만, 이 신호의 메커니즘이
  곧 유동성 공급이라 지정가는 **내가 틀렸을 때 우선 체결된다**(역선택).
  하필 엣지가 사는 지점에서 낙관적인 가정이므로 검증된 값이 아니다.

  그래서 gross 를 키워 **시장가로도 넘기는** 쪽을 먼저 시도한다. 성공하면
  체결 가정 자체가 의사결정에서 빠진다.

  ※ 범위 한정 (대표님 지시 2026-08-09): "테이커 마찰을 넘어야 한다"는
    **이 신호에만 적용하는 실험 조건**이다. U1/U2 의 일반 관문으로 승격시키지
    않는다. 다른 전략은 각자의 실행 방식에 맞게 따로 판정한다.

방법 — 임계값을 쓸어보지 않는다
  느슨한 트리거(ofi_z > 1.5)로 거래를 전부 만들고, 각 거래의 **진입 시점 상태**를
  같이 기록한다. 그 다음 상태 변수별 십분위로 gross 엣지를 갈라 본다. 어디에
  엣지가 몰리는지 지형이 먼저 보이고, 조건은 거기서 고른다. 임계값을 성과에
  맞춰 직접 최적화하면 그 값이 표본에 붙는다.

과적합 통제
  종목을 개발/검증 둘로 가른다(해시 기반, 시점은 동일). 지형은 **개발 집합에서만**
  그리고, 고른 조건은 **검증 집합에서만** 평가한다. 시간 분할도 함께 본다
  (앞 절반에서 고르고 뒤 절반에서 확인).

사용:
  python3 scripts/research/ultra_cvd_refine.py --min-dvol-usd 3000000 --days 60
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
import zlib
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ultra_cvd_refine")

BAR_MIN = 5
Z_WIN = 288                  # 24시간
TAKER_FEE_BP = 4.0
LOOSE_Z = 1.5                # 지형을 그리기 위한 느슨한 트리거
HOLDS = (24, 36, 48, 72, 96)  # 120 / 180 / 240 / 360 / 480분


def to_bars(df1m: pd.DataFrame) -> pd.DataFrame:
    r = df1m.resample(f"{BAR_MIN}min")
    b = pd.DataFrame({
        "open": r["px_open"].first(),
        "close": r["px_close"].last(),
        "qvol": r["quote_volume"].sum(),
        "buy": r["taker_buy_quote"].sum(),
        "sell": r["taker_sell_quote"].sum(),
        "lbuy": r["large_buy_quote"].sum(),
        "lsell": r["large_sell_quote"].sum(),
        "ntr": r["n_trades"].sum(),
        "tq50": r["trade_q50"].median(),
        "spread": r["eff_spread_bp_adj"].median(),
    }).dropna(subset=["open", "close"])
    return b[b["qvol"] > 0]


def _z(s: pd.Series, win: int = Z_WIN) -> pd.Series:
    m = s.rolling(win, min_periods=win // 4).mean()
    sd = s.rolling(win, min_periods=win // 4).std()
    return (s - m) / sd.replace(0, np.nan)


def build(sym: str, b: pd.DataFrame, hold: int) -> pd.DataFrame:
    """느슨한 cvd_divergence 트리거 → 비겹침 거래 + 진입 시점 상태 기록."""
    tot = (b["buy"] + b["sell"]).replace(0, np.nan)
    ofi = (b["buy"] - b["sell"]) / tot
    ltot = (b["lbuy"] + b["lsell"]).replace(0, np.nan)
    wimb = (b["lbuy"] - b["lsell"]) / ltot
    ret = b["close"].pct_change()
    rv = ret.rolling(Z_WIN, min_periods=Z_WIN // 4).std()   # 실현변동성

    ofi_z = _z(ofi)
    ret_z = ret / rv.replace(0, np.nan)                     # 변동성 정규화 수익률
    vol_z, spr_z, ntr_z, sz_z, wm_z = (_z(rv), _z(b["spread"]), _z(b["ntr"]),
                                       _z(b["tq50"]), _z(wimb))

    # 흡수: 가격이 내렸는데 공격적 매수가 몰림(→ 롱), 또는 반대(→ 숏)
    d = pd.Series(0.0, index=b.index)
    d[((ofi_z > LOOSE_Z) & (ret < 0)).fillna(False)] = 1.0
    d[((ofi_z < -LOOSE_Z) & (ret > 0)).fillna(False)] = -1.0

    idx, o, sp = b.index, b["open"].values, b["spread"].values
    cols = {"ofi_z": ofi_z.values, "ret_z": ret_z.values, "vol_z": vol_z.values,
            "spr_z": spr_z.values, "ntr_z": ntr_z.values, "sz_z": sz_z.values,
            "wm_z": wm_z.values, "spread_bp": sp}
    fired = np.flatnonzero(d.values != 0)
    rows, last_exit = [], -1
    for i in fired:
        ei, xi = i + 1, i + 1 + hold          # lookahead 방어: 다음 봉 시가 진입
        if ei <= last_exit or xi >= len(idx):
            continue                          # 겹침 방어
        e, x = o[ei], o[xi]
        if not (np.isfinite(e) and np.isfinite(x)) or e <= 0:
            continue
        dirv = d.values[i]
        rec = {"symbol": sym, "ts": idx[ei], "dir": dirv,
               "gross": (x / e - 1.0) * dirv}
        for k, v in cols.items():
            val = v[i]
            rec[k] = float(val) if np.isfinite(val) else np.nan
        # 방향 부호를 제거한 절대 강도 — 롱/숏을 한 지형에서 보기 위해
        rec["ofi_mag"] = abs(rec["ofi_z"]) if np.isfinite(rec["ofi_z"]) else np.nan
        rec["ret_mag"] = abs(rec["ret_z"]) if np.isfinite(rec["ret_z"]) else np.nan
        rec["wm_align"] = (rec["wm_z"] * dirv) if np.isfinite(rec["wm_z"]) else np.nan
        rows.append(rec)
        last_exit = xi
    return pd.DataFrame(rows)


def net_bp(df: pd.DataFrame) -> tuple:
    fric = (df["spread_bp"] + 2.0 * TAKER_FEE_BP) / 1e4
    net = df["gross"] - fric
    n = len(net)
    sd = net.std(ddof=1) if n > 1 else 0.0
    t = float(net.mean() / (sd / np.sqrt(n))) if n > 2 and sd > 0 else float("nan")
    return (float(df["gross"].mean() * 1e4), float(fric.mean() * 1e4),
            float(net.mean() * 1e4), t, n)


def terrain(df: pd.DataFrame, var: str, q: int = 10) -> pd.DataFrame:
    """상태 변수 십분위별 gross/net. 지형만 본다 — 임계는 여기서 고르지 않는다."""
    d = df[np.isfinite(df[var])].copy()
    if len(d) < q * 30:
        return pd.DataFrame()
    d["bucket"] = pd.qcut(d[var], q, labels=False, duplicates="drop")
    rows = []
    for bk, g in d.groupby("bucket"):
        gr, fr, nt, t, n = net_bp(g)
        rows.append({"bucket": int(bk), "lo": float(g[var].min()),
                     "hi": float(g[var].max()), "n": n,
                     "gross_bp": gr, "net_bp": nt, "t": t})
    return pd.DataFrame(rows)


def dev_set(sym: str) -> bool:
    """종목 해시 분할. 시점은 동일하게 두고 종목만 가른다."""
    return zlib.crc32(sym.encode()) % 2 == 0


def main() -> int:
    p = argparse.ArgumentParser(description="cvd_divergence 조건부 엣지 지형 + 정련")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--min-dvol-usd", type=float, default=3_000_000)
    p.add_argument("--hold", type=int, default=48, help="지형용 기준 보유(봉)")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "ultra_cvd_refine.json"))
    args = p.parse_args()

    files = sorted(glob.glob(os.path.join(args.data_dir, "*_agg1m.joblib")))
    if args.limit:
        files = files[:args.limit]

    frames = {h: [] for h in HOLDS}
    n_used = 0
    for i, f in enumerate(files, 1):
        sym = os.path.basename(f).replace("_agg1m.joblib", "")
        try:
            df = joblib.load(f)
        except Exception:
            continue
        df = df[~df.index.duplicated(keep="last")].sort_index()
        df = df.loc[df.index >= df.index.max() - pd.Timedelta(days=args.days)]
        dv = df["quote_volume"].resample("1D").sum().median() if len(df) else np.nan
        if not np.isfinite(dv) or dv < args.min_dvol_usd:
            continue
        b = to_bars(df)
        if len(b) < Z_WIN * 2:
            continue
        n_used += 1
        for h in HOLDS:
            t = build(sym, b, h)
            if len(t):
                frames[h].append(t)
        if i % 100 == 0:
            log.info("%d/%d (사용 %d)", i, len(files), n_used)

    if not frames[args.hold]:
        log.error("거래 0건")
        return 1

    all_h = {h: pd.concat(v, ignore_index=True) for h, v in frames.items() if v}
    base = all_h[args.hold]
    base["dev"] = base["symbol"].map(dev_set)
    dev, hold_out = base[base["dev"]], base[~base["dev"]]

    print("\n" + "=" * 92)
    print(f"cvd_divergence 정련 — {n_used}종목 / 최근 {args.days}일 / "
          f"느슨한 트리거 |ofi_z|>{LOOSE_Z}")
    print("=" * 92)
    gr, fr, nt, t, n = net_bp(base)
    print(f"  기준선(보유 {args.hold * BAR_MIN}분, 조건 없음)  "
          f"n={n:,}  gross {gr:+.2f}bp  마찰 {fr:.2f}  net {nt:+.2f}bp  t={t:+.2f}")
    print(f"  개발 {len(dev):,}거래 / {dev['symbol'].nunique()}종목  |  "
          f"검증 {len(hold_out):,}거래 / {hold_out['symbol'].nunique()}종목")

    print("\n  ── 보유 기간 (조건 없음, 전체) ──")
    print(f"      {'보유':>7}{'거래수':>10}{'gross':>10}{'마찰':>8}{'net':>10}{'t':>8}")
    for h in HOLDS:
        if h not in all_h:
            continue
        gr, fr, nt, t, n = net_bp(all_h[h])
        print(f"      {h * BAR_MIN:>6}분{n:>10,}{gr:>+10.2f}{fr:>8.2f}{nt:>+10.2f}{t:>+8.2f}")

    print("\n  ── 조건부 엣지 지형 (개발 집합만, 십분위) ──")
    for var, label in [("ofi_mag", "흡수 강도 |ofi_z|"),
                       ("ret_mag", "가격 이동 |ret/rv|"),
                       ("vol_z", "변동성 레짐"),
                       ("spr_z", "스프레드 상태"),
                       ("ntr_z", "체결 도착률"),
                       ("sz_z", "체결 크기"),
                       ("wm_align", "대형체결 방향 일치")]:
        tf = terrain(dev, var)
        if tf.empty:
            print(f"    {label}: 표본 부족")
            continue
        cells = "  ".join(f"{r.gross_bp:+.0f}" for r in tf.itertuples())
        best = tf.loc[tf["gross_bp"].idxmax()]
        print(f"    {label:<20} gross/십분위: {cells}")
        print(f"    {'':<20}   최고 십분위 {int(best.bucket)} "
              f"[{best.lo:+.2f}~{best.hi:+.2f}] gross {best.gross_bp:+.2f}bp "
              f"net {best.net_bp:+.2f}bp (n={int(best.n):,})")
    print("=" * 92 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    payload = {"n_symbols": n_used, "days": args.days, "hold_bars": args.hold,
               "loose_z": LOOSE_Z,
               "baseline": dict(zip(["gross_bp", "fric_bp", "net_bp", "t", "n"],
                                    net_bp(base))),
               "holds": {h * BAR_MIN: dict(zip(["gross_bp", "fric_bp", "net_bp", "t", "n"],
                                               net_bp(v))) for h, v in all_h.items()},
               "terrain": {v: terrain(dev, v).to_dict("records")
                           for v in ("ofi_mag", "ret_mag", "vol_z", "spr_z",
                                     "ntr_z", "sz_z", "wm_align")}}
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    joblib.dump(all_h, args.out.replace(".json", "_trades.joblib"), compress=3)
    log.info("저장: %s (+거래 캐시)", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
