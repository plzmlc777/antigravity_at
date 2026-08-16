"""R-5 시드 `premium_index_zscore` 재검정 — 4종목 17거래를 322종목으로.

## 원본 판정 (2026-05-06 R-4 gate)

    DOGE  alpha **+348.17%** · Sharpe 3.15 · PF 11.76 · 승률 76.5% ·
          perm_p 0.0000 · **9.0σ**
    LDO   alpha +290.07 · SOL +166.52 · AVAX +141.81
    **거래 17 / 17 / 13건** — 하드 컷오프 30건 **미달(전부 FAIL)**

    5/5 strict PASS 로 R-5 시드가 됐다. 거래 수만 빼고.

## 규칙 (소스 `BinancePremiumIndexZScoreSource` 그대로)

    프리미엄 = (mark_close − index_close) / index_close   (1일봉)
    z = (프리미엄 − 30일 평균) / 30일 표준편차
    z > +2.0 → **롱** (지속 프리미엄 = 롱 압력, 모멘텀 추종)
    z < -2.0 → **숏**
    보유 5일 · 손절 5% · 수수료 4bp

## 무엇을 다르게 하나

  · 종목 **4개 → 322개** (2026-08-16 수집, 22.5만 행 · 2021-01~)
  · 관측 단위 — 신호가 시간에 뭉치므로 **월별**로 묶어 t 를 낸다(교훈 #92)
  · **방향 대조**(교훈 #91) — 같은 규칙을 뒤집는다. 둘 다 벌면 국면이다
  · **원형회전 위약** — 프리미엄 계열만 밀어 가격과의 짝을 깬다
  · IS/OOS 분할

⚠ 진입은 신호 **다음날 시가**. 같은 날 종가로 넣으면 그 날을 보고 들어간다.

사용:
  python3 -m scripts.research.premium_index_revalidate
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("prem_rv")

OUT_DIR = ROOT / "runs" / "research_track" / "premium_index_zscore"


@dataclass
class PIConfig:
    zwin: int = 30
    entry_z: float = 2.0
    hold_days: int = 5
    sl: float = 0.05
    fee: float = 0.0004         # 편도
    min_adv: float = 3e6
    since: str = "2021-01-01"
    split: str = "2025-01-01"
    rot: int = 200
    invert: bool = False

    def __post_init__(self):
        if self.hold_days < 1:
            raise SystemExit("hold_days >= 1")
        if self.entry_z <= 0:
            raise SystemExit("entry_z > 0")

    @property
    def out_path(self) -> Path:
        return OUT_DIR / (f"revalidate_z{self.entry_z}_h{self.hold_days}"
                          f"{'_inv' if self.invert else ''}.json")


def simulate(g: pd.DataFrame, cfg: PIConfig) -> list[dict]:
    """한 종목. 진입은 신호 **다음날 시가**, 청산은 보유일 뒤 시가 또는 손절."""
    prem = g["premium"].values
    op, hi, lo = g["open"].values, g["high"].values, g["low"].values
    ts = g["ts"].values
    s = pd.Series(prem)
    z = ((s - s.rolling(cfg.zwin).mean())
         / s.rolling(cfg.zwin).std().replace(0, np.nan)).values
    out, i, n = [], cfg.zwin, len(g)
    while i < n - 1:
        zi = z[i]
        if not np.isfinite(zi) or abs(zi) < cfg.entry_z:
            i += 1
            continue
        side = 1 if zi > 0 else -1          # z>0 → 롱 (추종)
        if cfg.invert:
            side = -side
        j = i + 1
        entry = op[j]
        if not (entry > 0):
            i += 1
            continue
        k_end = min(j + cfg.hold_days, n - 1)
        reason, ex = "time", op[k_end]
        for k in range(j, k_end):
            adverse = hi[k] if side < 0 else lo[k]
            if adverse > 0 and side * (adverse / entry - 1.0) <= -cfg.sl:
                reason, ex = "sl", entry * (1 - side * cfg.sl)
                break
        ret = side * (ex / entry - 1.0) - 2 * cfg.fee
        out.append({"symbol": g["symbol"].iloc[0], "ts": pd.Timestamp(ts[j]),
                    "side": "long" if side > 0 else "short", "z": float(zi),
                    "ret": float(ret) * 100, "reason": reason})
        i = k_end                            # 겹치지 않게
    return out


def stats(d: pd.DataFrame, cfg: PIConfig, label: str) -> dict:
    if d.empty:
        print(f"  {label:<20} 거래 0건")
        return {"n": 0}
    sp = pd.Timestamp(cfg.split)
    out = {"n": int(len(d)), "mean": float(d["ret"].mean()),
           "med": float(d["ret"].median()),
           "win": float(100 * (d["ret"] > 0).mean())}
    for name, m in (("IS", d["ts"] < sp), ("OOS", d["ts"] >= sp)):
        g = d[m]
        if g.empty:
            continue
        mon = g.set_index("ts")["ret"].resample("MS").mean().dropna()
        se = mon.std(ddof=1) / np.sqrt(len(mon)) if len(mon) > 1 else np.nan
        out[name] = {"n": int(len(g)), "mean": float(g["ret"].mean()),
                     "n_months": int(len(mon)),
                     "t_monthly": float(mon.mean() / se) if se and se == se else None}
    i_, o_ = out.get("IS", {}), out.get("OOS", {})
    print(f"  {label:<20} 거래 {out['n']:>5} · 평균 {out['mean']:+6.3f}% · "
          f"승률 {out['win']:4.1f}% | IS {i_.get('n',0):>4}건 "
          f"{i_.get('mean',np.nan):+6.3f}% t {(i_.get('t_monthly') or 0):+5.2f} | "
          f"OOS {o_.get('n',0):>4}건 {o_.get('mean',np.nan):+6.3f}% "
          f"t {(o_.get('t_monthly') or 0):+5.2f}")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="premium_index_zscore 재검정")
    for f_ in PIConfig.__dataclass_fields__.values():
        if f_.type is bool:
            p.add_argument("--" + f_.name.replace("_", "-"), action="store_true")
        else:
            p.add_argument("--" + f_.name.replace("_", "-"),
                           type=type(f_.default), default=f_.default)
    a = p.parse_args()
    cfg = PIConfig(**{k: getattr(a, k) for k in PIConfig.__dataclass_fields__})

    from sqlalchemy import text

    from app.db.session import engine
    with engine.connect() as conn:
        pr = conn.execute(text(
            "SELECT symbol, date, premium FROM binance_premium_index "
            "WHERE date >= :d ORDER BY symbol, date"), {"d": cfg.since}).fetchall()
        px = conn.execute(text(
            "SELECT symbol, date, open, high, low, close FROM ohlcv_daily "
            "WHERE date >= :d AND is_partial = false ORDER BY symbol, date"),
            {"d": cfg.since}).fetchall()
        liq = {r[0]: float(r[1] or 0) for r in conn.execute(text(
            "SELECT symbol, avg(close*volume) FROM ohlcv_daily "
            "WHERE date >= :d GROUP BY symbol"), {"d": cfg.since})}
    P = pd.DataFrame(pr, columns=["symbol", "ts", "premium"])
    X = pd.DataFrame(px, columns=["symbol", "ts", "open", "high", "low", "close"])
    for D in (P, X):
        D["ts"] = pd.to_datetime(D["ts"])
    for c in ("premium",):
        P[c] = pd.to_numeric(P[c], errors="coerce")
    for c in ("open", "high", "low", "close"):
        X[c] = pd.to_numeric(X[c], errors="coerce")
    m = X.merge(P, on=["symbol", "ts"], how="inner")
    ok = {s for s, v in liq.items() if v >= cfg.min_adv}
    m = m[m["symbol"].isin(ok)].sort_values(["symbol", "ts"])
    log.info("프리미엄 %d종목 · 가격 %d종목 · 유동성 통과 교집합 **%d종목** · %s행",
             P["symbol"].nunique(), X["symbol"].nunique(),
             m["symbol"].nunique(), f"{len(m):,}")

    def run(c2: PIConfig) -> pd.DataFrame:
        tr = []
        for s, g in m.groupby("symbol"):
            if len(g) < c2.zwin + 10:
                continue
            tr.extend(simulate(g.reset_index(drop=True), c2))
        return pd.DataFrame(tr)

    d = run(cfg)
    print("=" * 104)
    print(f"  **premium_index_zscore R-5 시드 재검정** — 종목 "
          f"{m['symbol'].nunique()} · 진입 |z| {cfg.entry_z} · 보유 "
          f"{cfg.hold_days}일 · 손절 {cfg.sl:.0%}")
    print(f"  원본: **4종목 · 13~17거래** · DOGE alpha **+348%** · Sharpe 3.15 "
          f"· perm_p 0.0000 (하드 컷오프 거래 30건은 **전부 미달**)")
    print(f"  ⚠ 월별로 묶어 t 를 낸다 — 신호가 시간에 뭉치므로 건별 t 는 부푼다")
    print("=" * 104)
    res: dict = {"config": asdict(cfg), "n_symbols": int(m["symbol"].nunique())}
    res["observed"] = stats(d, cfg, "관측")

    inv = PIConfig(**{**asdict(cfg), "invert": not cfg.invert})
    res["mirror"] = stats(run(inv), cfg, "**방향 대조(거울)**")
    if res["observed"].get("n") and res["mirror"].get("n"):
        s_ = res["observed"]["mean"] + res["mirror"]["mean"]
        print(f"  {'합(관측+거울)':<20} {s_:+.3f}%  ← 0 에 가까우면 규칙이 아니라 "
              f"방향성이다")
        res["sum_obs_mirror"] = s_

    # 원형회전 위약 — 프리미엄만 민다
    rng = np.random.default_rng(20260816)
    obs = res["observed"].get("mean", 0.0)
    null = []
    for _ in range(cfg.rot):
        tr = []
        for s, g in m.groupby("symbol"):
            if len(g) < cfg.zwin + 10:
                continue
            g2 = g.reset_index(drop=True).copy()
            k = int(rng.integers(cfg.zwin, max(cfg.zwin + 1, len(g2))))
            g2["premium"] = np.roll(g2["premium"].values, k)
            tr.extend(simulate(g2, cfg))
        null.append(pd.DataFrame(tr)["ret"].mean() if tr else 0.0)
    null = np.array(null)
    p_rot = float((null >= obs).mean())
    print(f"\n  **원형회전 위약** {cfg.rot}회 (프리미엄만 이동) — 귀무 평균 "
          f"{null.mean():+.3f}% · p95 {np.percentile(null,95):+.3f}% "
          f"→ **p {p_rot:.3f}**")
    res["p_rotation"] = p_rot

    if not d.empty:
        print(f"\n  방향 {d['side'].value_counts().to_dict()} · 청산 "
              f"{d['reason'].value_counts().to_dict()}")
        per = d.groupby("symbol")["ret"].mean()
        print(f"  종목별 양수 **{int((per>0).sum())}/{len(per)}종목**")
        res["per_symbol_positive"] = f"{int((per>0).sum())}/{len(per)}"
        seed = [s for s in ("DOGEUSDT", "LDOUSDT", "SOLUSDT", "AVAXUSDT")
                if s in per.index]
        if seed:
            print(f"  ⭐ 원본 시드 4종목: "
                  + " · ".join(f"{s} {per[s]:+.3f}%" for s in seed))
            res["original_seeds"] = {s: float(per[s]) for s in seed}
    cfg.out_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.out_path.write_text(json.dumps(res, ensure_ascii=False, indent=2,
                                       default=str))
    print("\n" + "=" * 104)
    print(f"  → {cfg.out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
