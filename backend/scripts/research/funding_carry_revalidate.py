"""R-5 시드 `funding_carry` 재검정 — 3종목 19거래를 유니버스로 넓힌다.

## 왜 재검정하나

원본 판정(2026-05-06, `runs/research_track/funding_carry/`):

    HBAR/AXS/COMP 3종목 · alpha +107.7% · Sharpe 1.87 · perm p 0.000
    **거래 19건**

두 가지가 그 판정 이후 바뀌었다:

  ① **정본 통일(2026-08-14)** — 손익 구현체 6개 중 4개가 오염돼 있었고 BT 를
     커널로 이관했다. 이 시드는 그 **이전** 판정이다.
     [[project-canon-backtest-unification]]
  ② **펀딩 기질(2026-08-15)** — 26종목 → **354종목 · 116만 행 · 2021-01~**.
     원본은 26종목 중 3개를 골랐다. 19거래는 **그 자체로 판정 불가**다
     (교훈: 소표본이 부호를 뒤집는다 — 25종목 vs 265종목에서 둘 다 반대였다).

## 규칙 (원본 `poc_funding_carry` 그대로)

    z = (funding − 30기간 평균) / 30기간 표준편차     (8시간 = 1기간)
    z > +entry_z  → **숏** (롱이 몰려 펀딩을 낸다 · 되돌림 기대)
    z < -entry_z  → **롱**
    청산: |z| < exit_z  |  손절 sl_pct  |  max_hold 기간 초과
    손익 = 가격손익 + **누적 펀딩** − 수수료
           (숏은 양수 펀딩을 받는다)

## 무엇을 다르게 하나

  · 종목 **3개 → 유니버스 전체**(시간봉 보유 & 유동성 통과분)
  · 관측 단위 — 거래가 시간에 **뭉치므로** 월별로 묶어 t 를 낸다(교훈 #92).
    거래 수백 건을 독립 표본으로 세면 t 가 부푼다.
  · **방향 대조**(교훈 #91) — 같은 규칙을 뒤집어 돌린다. 둘 다 벌면 규칙이
    아니라 국면이다.
  · **원형회전 위약** — 펀딩 계열만 통째로 밀어 가격과의 짝을 깬다.
  · IS/OOS 분할

⚠ 진입은 **신호 다음 기간 시가**에 넣는다. 같은 기간 종가로 넣으면 그 기간의
  펀딩·가격을 이미 보고 들어가는 것이다.

사용:
  python3 -m scripts.research.funding_carry_revalidate
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
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("fcarry")

OUT_DIR = ROOT / "runs" / "research_track" / "funding_carry"


@dataclass
class CarryConfig:
    """원본 시드 스펙 그대로. 값을 바꾸려면 여기서만 바꾼다."""
    lookback: int = 30          # 펀딩 기간(8h) 단위
    entry_z: float = 2.5
    exit_z: float = 0.5
    max_hold: int = 7           # 펀딩 기간
    sl_pct: float = 0.03
    fee: float = 0.0004         # 편도
    min_adv: float = 3e6
    since: str = "2025-01-01"
    split: str = "2026-02-01"
    rot: int = 200
    invert: bool = False        # 방향 대조용

    def __post_init__(self):
        if self.exit_z >= self.entry_z:
            raise SystemExit("exit_z 는 entry_z 보다 작아야 한다")
        if self.max_hold < 1:
            raise SystemExit("max_hold >= 1")

    @property
    def out_path(self) -> Path:
        return OUT_DIR / (f"revalidate_z{self.entry_z}_h{self.max_hold}"
                          f"{'_inv' if self.invert else ''}.json")


def load(conn, cfg: CarryConfig):
    from sqlalchemy import text
    # 8시간 격자에 맞춘 가격 — 시간봉에서 00/08/16 UTC 만 뽑는다
    h = conn.execute(text(
        "SELECT symbol, ts, open, close FROM ohlcv_hourly "
        "WHERE ts >= :d AND extract(hour from ts) IN (0, 8, 16) "
        "ORDER BY symbol, ts"), {"d": cfg.since}).fetchall()
    px = pd.DataFrame(h, columns=["symbol", "ts", "open", "close"])
    px["ts"] = pd.to_datetime(px["ts"])
    for c in ("open", "close"):
        px[c] = pd.to_numeric(px[c], errors="coerce")
    f = conn.execute(text(
        "SELECT symbol, funding_time, funding_rate FROM binance_funding_rate "
        "WHERE funding_time >= :d ORDER BY symbol, funding_time"),
        {"d": cfg.since}).fetchall()
    fu = pd.DataFrame(f, columns=["symbol", "ts", "fr"])
    fu["ts"] = pd.to_datetime(fu["ts"]).dt.floor("h")
    fu["fr"] = pd.to_numeric(fu["fr"], errors="coerce")
    liq = conn.execute(text(
        "SELECT symbol, avg(close*volume) FROM ohlcv_daily WHERE date >= :d "
        "GROUP BY symbol"), {"d": cfg.since}).fetchall()
    adv = {r[0]: float(r[1] or 0) for r in liq}
    return px, fu, adv


def simulate(g: pd.DataFrame, cfg: CarryConfig) -> list[dict]:
    """한 종목. 원본 규칙 그대로, 진입은 **신호 다음 기간 시가**."""
    fr = g["fr"].values
    op = g["open"].values
    ts = g["ts"].values
    mu = pd.Series(fr).rolling(cfg.lookback).mean().values
    sd = pd.Series(fr).rolling(cfg.lookback).std().values
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (fr - mu) / sd
    trades, i, n = [], cfg.lookback, len(g)
    while i < n - 1:
        zi = z[i]
        if not np.isfinite(zi) or abs(zi) < cfg.entry_z:
            i += 1
            continue
        side = -1 if zi > 0 else 1          # z>0 → 숏(-1)
        if cfg.invert:
            side = -side
        j = i + 1                            # 다음 기간 시가 진입
        entry = op[j]
        if not (entry > 0):
            i += 1
            continue
        fsum, k = 0.0, j
        exit_reason, exit_px = "time", op[min(j + cfg.max_hold, n - 1)]
        while k < min(j + cfg.max_hold, n - 1):
            # ⚠ 펀딩 부호 — 양수 펀딩은 **롱이 숏에게** 지급한다.
            #   숏(side=-1) 은 받고, 롱(side=+1) 은 낸다.
            #     side=-1, fr>0  →  -(-1)*fr = +fr   (받는다)
            #     side=+1, fr>0  →  -(+1)*fr = -fr   (낸다)
            fsum += -side * fr[k]
            k += 1
            px_k = op[k]
            move = side * (px_k / entry - 1.0)
            if move <= -cfg.sl_pct:
                exit_reason, exit_px = "sl", px_k
                break
            if np.isfinite(z[k]) and abs(z[k]) < cfg.exit_z:
                exit_reason, exit_px = "z", px_k
                break
            exit_px = px_k
        ret = side * (exit_px / entry - 1.0) + fsum - 2 * cfg.fee
        trades.append({"symbol": g["symbol"].iloc[0], "ts": pd.Timestamp(ts[j]),
                       "side": "short" if side < 0 else "long",
                       "z": float(zi), "ret": float(ret) * 100,
                       "funding": float(fsum) * 100, "reason": exit_reason,
                       "bars": int(k - j)})
        i = k + 1                            # 겹치지 않게 다음 기간부터
    return trades


def stats(d: pd.DataFrame, cfg: CarryConfig, label: str) -> dict:
    """월별로 묶어 t 를 낸다 — 거래가 시간에 뭉치므로(교훈 #92)."""
    if d.empty:
        print(f"  {label:<18} 거래 0건")
        return {"n": 0}
    out = {"n": int(len(d)), "mean": float(d["ret"].mean()),
           "med": float(d["ret"].median()),
           "win": float(100 * (d["ret"] > 0).mean()),
           "funding_share": float(d["funding"].sum() / d["ret"].sum() * 100)
           if d["ret"].sum() else None}
    sp = pd.Timestamp(cfg.split)
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
    print(f"  {label:<18} 거래 {out['n']:>5} · 평균 {out['mean']:+6.3f}% · "
          f"승률 {out['win']:4.1f}% | IS {i_.get('n',0):>4}건 "
          f"{i_.get('mean',np.nan):+6.3f}% t {(i_.get('t_monthly') or 0):+5.2f} | "
          f"OOS {o_.get('n',0):>4}건 {o_.get('mean',np.nan):+6.3f}% "
          f"t {(o_.get('t_monthly') or 0):+5.2f}")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="funding_carry R-5 시드 재검정")
    for f_ in CarryConfig.__dataclass_fields__.values():
        if f_.type is bool:
            p.add_argument("--" + f_.name.replace("_", "-"), action="store_true")
        else:
            p.add_argument("--" + f_.name.replace("_", "-"),
                           type=type(f_.default), default=f_.default)
    a = p.parse_args()
    cfg = CarryConfig(**{k: getattr(a, k) for k in CarryConfig.__dataclass_fields__})

    from app.db.session import engine
    with engine.connect() as conn:
        px, fu, adv = load(conn, cfg)
    syms = sorted(set(px["symbol"]) & set(fu["symbol"])
                  & {s for s, v in adv.items() if v >= cfg.min_adv})
    log.info("가격 %d종목 · 펀딩 %d종목 · 유동성 통과 교집합 **%d종목**",
             px["symbol"].nunique(), fu["symbol"].nunique(), len(syms))

    m = px.merge(fu, on=["symbol", "ts"], how="inner")
    m = m[m["symbol"].isin(syms)].sort_values(["symbol", "ts"])
    log.info("8시간 격자 표본 %s행 · %s ~ %s", f"{len(m):,}",
             m["ts"].min(), m["ts"].max())

    all_tr = []
    for s, g in m.groupby("symbol"):
        if len(g) < cfg.lookback + 10:
            continue
        all_tr.extend(simulate(g.reset_index(drop=True), cfg))
    d = pd.DataFrame(all_tr)

    print("=" * 104)
    print(f"  **funding_carry R-5 시드 재검정** — 종목 {len(syms)} · "
          f"진입 z {cfg.entry_z} · 청산 z {cfg.exit_z} · 최대 {cfg.max_hold}기간 · "
          f"손절 {cfg.sl_pct:.0%}")
    print(f"  원본: **3종목 · 19거래** · alpha +107.7% · Sharpe 1.87 (2026-05-06, "
          f"정본 통일 이전)")
    print(f"  ⚠ 월별로 묶어 t 를 낸다 — 거래가 시간에 뭉치므로 건별 t 는 부푼다")
    print("=" * 104)
    res: dict = {"config": asdict(cfg), "n_symbols": len(syms)}
    res["observed"] = stats(d, cfg, "관측")

    # ── 방향 대조 (교훈 #91) ──────────────────────────────────────────
    inv = CarryConfig(**{**asdict(cfg), "invert": not cfg.invert})
    tr2 = []
    for s, g in m.groupby("symbol"):
        if len(g) < cfg.lookback + 10:
            continue
        tr2.extend(simulate(g.reset_index(drop=True), inv))
    d2 = pd.DataFrame(tr2)
    res["mirror"] = stats(d2, cfg, "**방향 대조(거울)**")
    if res["observed"].get("n") and res["mirror"].get("n"):
        s_ = res["observed"]["mean"] + res["mirror"]["mean"]
        print(f"  {'합(관측+거울)':<18} {s_:+.3f}%  ← 0 에 가까우면 규칙 효과가 "
              f"아니라 방향성이다")
        res["sum_obs_mirror"] = s_

    # ── 원형회전 위약 ─────────────────────────────────────────────────
    rng = np.random.default_rng(20260816)
    obs = res["observed"].get("mean", 0.0)
    null = []
    for _ in range(cfg.rot):
        tr3 = []
        for s, g in m.groupby("symbol"):
            if len(g) < cfg.lookback + 10:
                continue
            g2 = g.reset_index(drop=True).copy()
            k = int(rng.integers(cfg.lookback, max(cfg.lookback + 1, len(g2))))
            g2["fr"] = np.roll(g2["fr"].values, k)
            tr3.extend(simulate(g2, cfg))
        null.append(pd.DataFrame(tr3)["ret"].mean() if tr3 else 0.0)
    null = np.array(null)
    p_rot = float((null >= obs).mean())
    print(f"\n  **원형회전 위약** {cfg.rot}회 (펀딩 계열만 이동) — 귀무 평균 "
          f"{null.mean():+.3f}% · p95 {np.percentile(null,95):+.3f}% "
          f"→ **p {p_rot:.3f}**")
    res["p_rotation"] = p_rot

    if not d.empty:
        print(f"\n  청산 사유: {d['reason'].value_counts().to_dict()}")
        print(f"  방향: {d['side'].value_counts().to_dict()}")
        print(f"  펀딩이 손익에서 차지하는 비중 "
              f"{res['observed'].get('funding_share', float('nan')):.1f}%")
    cfg.out_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.out_path.write_text(json.dumps(res, ensure_ascii=False, indent=2,
                                       default=str))
    print("\n" + "=" * 104)
    print(f"  → {cfg.out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
