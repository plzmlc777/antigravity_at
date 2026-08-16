"""리밸런싱 대 바이앤홀드 — **꼬리를 자르고 있었는가**.

왜 이 질문인가 (2026-08-16)
    오늘 측정에서 반복해 나온 사실:

        동일가중 알트 바스켓 누적 **-8%** (5.4년) · 횡단면 중앙 **-100%**
        상하위 5% 절사하면 **-100%**  ← 바스켓 생존이 전적으로 상위 5%에 달렸다
        꼬리 비대칭 어느 오분위에서든 **+1 ~ +1.9%p 위쪽** (상수)

    그런데 그 바스켓은 전부 **일간 리밸런스**였다. 일간 리밸런스는 오른 종목을
    팔고 빠진 종목을 산다 — **양의 왜도 자산군에서 정확히 반대**다. 상위 5%가
    커질수록 계속 잘라낸다.

    ⚠ 이건 **예측이 필요 없는 질문**이다. 지금까지 닫힌 열두 축은 전부
      "무엇을 고를까"였는데, 이건 "어떻게 들고 있을까"다. 종목 선별도
      국면 판정도 안 쓴다.

설계 (하네스 규칙 준수)
    ① 설정은 `RebalConfig` 한 곳
    ② 같은 시작일 · 같은 유니버스 · 같은 종료일에서 **리밸런스 주기만** 바꾼다
       (짝 비교. 다른 걸 같이 바꾸면 무엇이 원인인지 모른다)
    ③ 시작일을 여러 개 쓴다 — 단일 경로로 결론내지 않는다
    ④ 마찰을 넣는다 — 리밸런스는 **거래를 일으키므로** 수수료가 이 비교의
       핵심 변수다. 펀딩도 롱 부담으로 넣는다.
    ⑤ 출력 경로는 설정에서 유도

⚠ 자격은 **시작 시점 정보로만** 판정한다 — 직전 30일 거래대금.
   시작 후 상장한 종목은 넣지 않는다(그 편입 자체가 미래 정보다).

⚠ 상장폐지·거래정지 처리
    가격이 끊긴 종목은 **마지막 가격에서 정지**한 것으로 본다(0 으로 소각하지
    않는다). 실제로는 청산되므로 이쪽이 낙관적이다 — 그래서 결과가 좋게 나오면
    그만큼 할인해서 읽어야 한다.

사용:
  python3 -m scripts.research.rebalance_vs_hold --hold-months 12
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
log = logging.getLogger("rebal")

OUT_DIR = ROOT / "runs" / "research_track" / "xsection"


@dataclass
class RebalConfig:
    min_adv: float = 1_000_000.0
    adv_window: int = 30
    min_history: int = 60
    min_symbols: int = 30
    hold_months: int = 12
    start_stride_months: int = 3      # 시작일 간격
    first_start: str = "2021-06-01"
    fee: float = 0.0005               # 편도 5bp
    include_funding: bool = True

    def __post_init__(self):
        if self.hold_months < 1:
            raise SystemExit("hold_months >= 1")
        if self.min_symbols < 10:
            raise SystemExit("min_symbols 가 너무 작다 — 바스켓이 아니다")

    @property
    def out_path(self) -> Path:
        return OUT_DIR / f"rebalance_vs_hold_h{self.hold_months}m.json"


def run_window(close: pd.DataFrame, fund: pd.DataFrame, syms: list[str],
               t0: pd.Timestamp, t1: pd.Timestamp, cfg: RebalConfig,
               rebal_days: int | None) -> dict | None:
    """같은 유니버스·같은 창에서 리밸런스 주기만 바꾼다.

    `rebal_days=None` 이면 **바이앤홀드** — 시작 시점에 한 번 사고 끝까지 둔다.
    """
    px = close.loc[(close.index >= t0) & (close.index <= t1), syms]
    if len(px) < 30:
        return None
    # ⚠ 끊긴 종목은 마지막 가격에서 정지(ffill). 0 으로 소각하지 않는다.
    px = px.ffill()
    px = px.loc[:, px.iloc[0].notna()]
    if px.shape[1] < cfg.min_symbols:
        return None
    ret = px.pct_change().fillna(0.0)

    fcost = pd.DataFrame(0.0, index=ret.index, columns=ret.columns)
    if cfg.include_funding:
        f = fund.reindex(index=ret.index, columns=ret.columns).fillna(0.0)
        fcost = f                                  # 롱은 양수 펀딩을 **낸다**

    n = px.shape[1]
    w = np.full(n, 1.0 / n)                        # 시작 동일가중
    equity, turn_total = 1.0, 0.0
    curve = []
    for i, ts in enumerate(ret.index):
        if i == 0:
            continue
        r = ret.iloc[i].values
        fc = fcost.iloc[i].values
        # 보유 비중대로 성장
        grow = w * (1.0 + r)
        gross = grow.sum()
        equity *= gross
        equity *= (1.0 - float((w * fc).sum()))    # 펀딩은 비중 가중으로 부담
        w = grow / gross if gross > 0 else w
        # 리밸런스
        if rebal_days and i % rebal_days == 0:
            tgt = np.full(n, 1.0 / n)
            turn = np.abs(w - tgt).sum() / 2.0     # 편도 회전율
            equity *= (1.0 - 2.0 * cfg.fee * turn)  # 매도+매수
            turn_total += turn
            w = tgt
        curve.append(equity)
    curve = np.array(curve)
    peak = np.maximum.accumulate(curve)
    return {"n_symbols": int(n), "final": float(curve[-1] - 1) * 100,
            "mdd": float(np.min(curve / peak - 1) * 100),
            "turnover": float(turn_total)}


def main() -> int:
    p = argparse.ArgumentParser(description="리밸런싱 대 바이앤홀드")
    for f_ in RebalConfig.__dataclass_fields__.values():
        p.add_argument("--" + f_.name.replace("_", "-"),
                       type=type(f_.default), default=f_.default)
    a = p.parse_args()
    cfg = RebalConfig(**{k: getattr(a, k) for k in RebalConfig.__dataclass_fields__})

    from research.xsection_harness import load_panel
    from app.db.session import engine
    with engine.connect() as conn:
        close, dvol, fund = load_panel(conn)
    adv = dvol.rolling(cfg.adv_window, min_periods=cfg.adv_window // 2
                       ).median().shift(1)
    hist = close.notna().cumsum().shift(1)

    starts = pd.date_range(cfg.first_start, close.index[-1]
                           - pd.DateOffset(months=cfg.hold_months),
                           freq=f"{cfg.start_stride_months}MS")
    log.info("시작일 %d개 (%s ~ %s · %d개월 간격) · 보유 %d개월",
             len(starts), starts[0].date(), starts[-1].date(),
             cfg.start_stride_months, cfg.hold_months)

    variants = [("일간 리밸런스", 1), ("주간 리밸런스", 7),
                ("월간 리밸런스", 30), ("분기 리밸런스", 91),
                ("**바이앤홀드**", None)]
    rows = []
    for t0 in starts:
        if t0 not in adv.index:
            i = adv.index.searchsorted(t0)
            if i >= len(adv.index):
                continue
            t0 = adv.index[i]
        t1 = t0 + pd.DateOffset(months=cfg.hold_months)
        elig = [s for s in adv.columns
                if adv.loc[t0, s] >= cfg.min_adv
                and hist.loc[t0, s] >= cfg.min_history]
        if len(elig) < cfg.min_symbols:
            continue
        rec = {"start": str(t0.date()), "n": len(elig)}
        ok = True
        for lab, rd in variants:
            r = run_window(close, fund, elig, t0, t1, cfg, rd)
            if r is None:
                ok = False
                break
            rec[lab] = r["final"]
            rec[lab + "_mdd"] = r["mdd"]
        if ok:
            rows.append(rec)
    if not rows:
        raise SystemExit("창이 하나도 안 만들어졌다 — 자격 조건을 확인하라")
    df = pd.DataFrame(rows)

    print("=" * 100)
    print(f"  **리밸런싱 대 바이앤홀드** — 동일가중 알트 바스켓 롱 · 보유 "
          f"{cfg.hold_months}개월 · 창 {len(df)}개")
    print(f"  같은 시작일 · 같은 유니버스 · **리밸런스 주기만** 다르다 · "
          f"수수료 편도 {cfg.fee*1e4:.0f}bp + 펀딩")
    print("=" * 100)
    print(f"\n  {'판본':>16}{'평균%':>9}{'중앙%':>9}{'양수':>7}{'최악%':>9}"
          f"{'평균MDD%':>10}{'회전':>8}")
    res = {}
    for lab, _ in variants:
        v = df[lab].values
        m = df[lab + "_mdd"].values
        res[lab.replace("*", "")] = {
            "mean": float(v.mean()), "med": float(np.median(v)),
            "pos": int((v > 0).sum()), "n": int(len(v)),
            "worst": float(v.min()), "mdd": float(m.mean())}
        print(f"  {lab:>16}{v.mean():>+9.1f}{np.median(v):>+9.1f}"
              f"{int((v>0).sum()):>4}/{len(v):<2}{v.min():>+9.1f}{m.mean():>10.1f}")

    # 짝 비교 — 같은 창에서 바이앤홀드 − 일간
    d = df["**바이앤홀드**"].values - df["일간 리밸런스"].values
    se = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else np.nan
    print(f"\n  **짝 비교** 바이앤홀드 − 일간 리밸런스")
    print(f"     평균 {d.mean():+.1f}%p · 중앙 {np.median(d):+.1f}%p · "
          f"t {d.mean()/se if se else np.nan:+.2f} · 양수 "
          f"{int((d>0).sum())}/{len(d)}")
    res["paired_hold_minus_daily"] = {
        "mean": float(d.mean()), "med": float(np.median(d)),
        "t": float(d.mean() / se) if se else None,
        "pos": int((d > 0).sum()), "n": int(len(d))}

    print(f"\n  창별 상세")
    print(f"     {'시작':>12}{'종목':>5}{'일간%':>9}{'월간%':>9}{'홀드%':>9}"
          f"{'홀드−일간':>11}")
    for _, r in df.iterrows():
        print(f"     {r['start']:>12}{int(r['n']):>5}{r['일간 리밸런스']:>+9.1f}"
              f"{r['월간 리밸런스']:>+9.1f}{r['**바이앤홀드**']:>+9.1f}"
              f"{r['**바이앤홀드**']-r['일간 리밸런스']:>+11.1f}")

    print("\n" + "=" * 100)
    print("  읽는 법")
    print("    · 바이앤홀드가 이기면 **일간 리밸런스가 꼬리를 잘라내고 있었다**는 뜻이다.")
    print("    · 지면 리밸런싱의 변동성 수확이 꼬리 손실보다 컸다는 뜻이다.")
    print("    · ⚠ 상폐 종목을 마지막 가격에서 정지시켰다 — 실제보다 **낙관적**이다.")
    cfg.out_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.out_path.write_text(json.dumps({"config": asdict(cfg), "results": res,
                                        "windows": rows},
                                       ensure_ascii=False, indent=2, default=str))
    print(f"  → {cfg.out_path}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
