"""초단기 신호 탐색 — 주문흐름 기반 후보를 일괄 측정한다.

배경 (2026-08-09, 대표님 지시 "초단기 전략은 기존 파라다임과 별개로 개발"):
  캠페인 graveyard 120여 건은 전부 OHLCV / funding / OI / premium 축이고, 그 축들은
  INDEX.md 가 스스로 "saturated" 라고 5회 기록했다. aggTrades 는 레포가 한 번도
  손대지 않은 축이며, 1분봉에 없는 **주문 흐름 방향**을 싣고 있다:
    is_buyer_maker=true → 테이커 매도 / false → 테이커 매수.
  여기서 CVD·주문흐름 불균형·대형체결 편향·체결 도착률·유효 스프레드가 나온다.

  하나를 찍어 만들지 않고 후보를 일괄 측정한다. 초단기의 합격선이 명확하기
  때문이다 — **왕복 마찰(8~15bp)을 넘는 gross 엣지**가 없으면 그 신호는 죽었다.
  이건 취향이 아니라 산술이라 스캔으로 거르는 게 맞다.

오늘 데인 함정을 방어 조건으로 박는다
  1. **lookahead** — 신호는 봉 t 종가까지의 정보로만 만들고 체결은 t+1 봉 시가.
     (2026-08-08 cd0ca27f: 이 한 줄이 volume_burst 성과의 95.4% 를 만들었다)
  2. **겹친 표본** — 같은 종목에서 보유 기간이 겹치는 거래를 만들지 않는다.
     겹치면 수익률이 상관되어 t 가 부풀려진다. 창 겹침으로 오늘 이미 한 번 데였다
     ([[feedback-overlapping-window-persistence-artifact]]).
  3. **가정 마찰** — 스프레드는 실측(eff_spread_bp_adj)을 쓴다. 가정값 금지.
  4. **생존편향** — 유니버스는 아카이브 전체에서 구성됐다. 유동성은 여기서 관문으로.
  5. **조용한 0** — 신호가 0건이면 0건이라고 보고한다.

판정 기준
  net_bp > 0 그리고 t >= 3.0 그리고 breadth(종목별 net>0 비율) >= 0.55.
  breadth 를 함께 보는 이유: 소수 종목이 전체 엣지를 만드는 신호는 배정기의
  재료가 못 된다 (INDEX.md 의 single-symbol-fit 반복 사례).

사용:
  python3 scripts/research/ultra_signal_scan.py --min-dvol-usd 3000000 --days 60
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ultra_signal_scan")

BAR_MIN = 5                 # 평가봉 (--bar-min 으로 덮어씀)
Z_WIN = 288                 # 24시간 롤링 (해상도에 맞춰 재계산)
TAKER_FEE_BP = 4.0          # 편도
HOLDS = (3, 6, 12, 24, 48, 96)     # 15 / 30 / 60 / 120 / 240 / 480분
Z_THRESHS = (2.0, 3.0, 4.0)

# 마찰 모델 두 가지. 초단기의 승패는 여기서 갈린다.
#   taker: 시장가 양방향 — 스프레드를 건너뛰고 테이커 수수료를 편도 4bp 씩 낸다.
#   maker: 지정가 진입/청산 — 스프레드 크로싱이 없고 수수료도 낮다.
# maker 는 **낙관적**이다. 지정가는 시장이 나에게 와야 체결되는데, 그건 대체로
# 내가 틀렸을 때다(역선택). 체결 확률과 그 편향은 이 모델에 들어 있지 않으므로
# maker 수치는 "마찰을 이만큼 줄이면 되는가"의 상한으로만 읽어야 한다.
MAKER_FEE_BP = 2.0


def to_bars(df1m: pd.DataFrame) -> pd.DataFrame:
    """1분 피처 → 5분 평가봉. 합계는 합, 가격은 시가/종가, 스프레드는 중앙값."""
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


def zscores(b: pd.DataFrame) -> dict[str, pd.Series]:
    """상태 z-score 를 **한 번만** 계산한다. 임계값별로 재계산하면 낭비다."""
    tot = (b["buy"] + b["sell"]).replace(0, np.nan)
    ofi = (b["buy"] - b["sell"]) / tot
    ltot = (b["lbuy"] + b["lsell"]).replace(0, np.nan)
    wimb = (b["lbuy"] - b["lsell"]) / ltot
    return {"ofi": ofi, "ret": b["close"].pct_change(),
            "ofi_z": _z(ofi), "w_z": _z(wimb), "n_z": _z(b["ntr"]),
            "s_z": _z(b["spread"]), "t_z": _z(b["tq50"]), "d_z": _z(ofi.diff())}


def signals(b: pd.DataFrame, zt: float, Z: dict) -> dict[str, pd.Series]:
    """후보 신호. 값은 **방향**(+1 롱 / -1 숏 / 0 무시)이며, 봉 t 종가까지의
    정보만 쓴다. 체결은 호출자가 t+1 봉 시가에 낸다."""
    ofi, ret = Z["ofi"], Z["ret"]
    ofi_z, w_z, n_z, s_z, t_z, d_z = (Z["ofi_z"], Z["w_z"], Z["n_z"],
                                      Z["s_z"], Z["t_z"], Z["d_z"])

    def trig(cond_pos, cond_neg):
        v = pd.Series(0.0, index=b.index)
        v[cond_pos.fillna(False)] = 1.0
        v[cond_neg.fillna(False)] = -1.0
        return v

    out: dict[str, pd.Series] = {}
    # 1) 주문흐름 불균형 극단 — 추종 / 페이드
    out["ofi_follow"] = trig(ofi_z > zt, ofi_z < -zt)
    out["ofi_fade"] = -out["ofi_follow"]
    # 2) 대형 체결(상위 5%) 방향 편향 — 정보 있는 주문 흐름
    out["whale_follow"] = trig(w_z > zt, w_z < -zt)
    out["whale_fade"] = -out["whale_follow"]
    # 3) CVD 다이버전스 — 가격은 내렸는데 공격적 매수가 몰림(흡수) → 반등
    out["cvd_divergence"] = trig((ofi_z > zt) & (ret < 0), (ofi_z < -zt) & (ret > 0))
    # 4) 체결 도착률 급증 + 흐름 방향
    out["arrival_flow"] = trig((n_z > zt) & (ofi > 0), (n_z > zt) & (ofi < 0))
    # 5) 체결 크기 급증 + 흐름 방향
    out["tradesize_flow"] = trig((t_z > zt) & (ofi > 0), (t_z > zt) & (ofi < 0))
    # 6) 스프레드 확대(유동성 이탈) + 흐름 방향
    out["spread_stress_flow"] = trig((s_z > zt) & (ofi > 0), (s_z > zt) & (ofi < 0))
    # 7) 주문흐름 가속(1차 차분)
    out["ofi_accel"] = trig(d_z > zt, d_z < -zt)
    # 8) 대형체결과 전체흐름 불일치 — 큰손이 반대편에 서 있다
    out["whale_vs_crowd"] = trig((w_z > zt) & (ofi_z < 0), (w_z < -zt) & (ofi_z > 0))
    return out


def eval_signal(b: pd.DataFrame, direction: pd.Series, hold: int) -> pd.DataFrame:
    """방향 시계열 → 비겹침 거래. 체결은 **다음 봉 시가**, 청산은 hold 봉 뒤 시가."""
    idx = b.index
    o = b["open"].values
    sp = b["spread"].values
    fired = np.flatnonzero(direction.values != 0)
    rows, last_exit = [], -1
    for i in fired:
        entry_i = i + 1                       # lookahead 방어: 다음 봉 시가
        exit_i = entry_i + hold
        if entry_i <= last_exit or exit_i >= len(idx):
            continue                          # 겹침 방어: 이전 거래 종료 후에만
        e, x = o[entry_i], o[exit_i]
        if not (np.isfinite(e) and np.isfinite(x)) or e <= 0:
            continue
        d = direction.values[i]
        gross = (x / e - 1.0) * d
        s = sp[entry_i] if np.isfinite(sp[entry_i]) else np.nanmedian(sp)
        # 마찰은 여기서 확정하지 않는다 — gross 와 스프레드를 남겨 두고
        # 보고 시점에 taker/maker 두 모델을 각각 적용한다.
        rows.append((gross, s))
        last_exit = exit_i
    return np.array(rows, dtype=float) if rows else np.empty((0, 2))


def main() -> int:
    p = argparse.ArgumentParser(description="초단기 주문흐름 신호 일괄 탐색")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60, help="최근 N일로 절단 (공통 구간)")
    p.add_argument("--min-dvol-usd", type=float, default=3_000_000)
    p.add_argument("--min-trades-sym", type=int, default=3, help="종목별 최소 거래")
    p.add_argument("--limit", type=int, default=0, help="종목 수 제한 (시험용)")
    p.add_argument("--bar-min", type=int, default=5, help="평가봉 분")
    p.add_argument("--holds-min", default="", help="보유(분) 쉼표. 미지정 시 봉의 배수 기본값")
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "ultra_signal_scan.json"))
    args = p.parse_args()

    global BAR_MIN, Z_WIN, HOLDS
    BAR_MIN = args.bar_min
    Z_WIN = max(int(24 * 60 / BAR_MIN), 60)          # 24시간 롤링
    if args.holds_min:
        HOLDS = tuple(max(int(x) // BAR_MIN, 1) for x in args.holds_min.split(","))

    files = sorted(glob.glob(os.path.join(args.data_dir, "*_agg1m.joblib")))
    if args.limit:
        files = files[:args.limit]
    log.info("종목 %d개 | 최근 %d일 | 유동성 관문 $%.0f/일 | 격자 %d신호 x %dz x %d보유",
             len(files), args.days, args.min_dvol_usd, 8, len(Z_THRESHS), len(HOLDS))

    # (signal, z, hold) → gross/spread 누적. 종목별 요약은 breadth 계산용.
    acc: dict[tuple, list] = {}
    per_sym: dict[tuple, list] = {}
    n_used = n_skip_liq = n_skip_short = 0

    for i, f in enumerate(files, 1):
        sym = os.path.basename(f).replace("_agg1m.joblib", "")
        try:
            df = joblib.load(f)
        except Exception as e:
            log.warning("[%s] 로드 실패: %s", sym, e)
            continue
        df = df[~df.index.duplicated(keep="last")].sort_index()
        cut = df.index.max() - pd.Timedelta(days=args.days)
        df = df.loc[df.index >= cut]
        dvol = df["quote_volume"].resample("1D").sum().median() if len(df) else np.nan
        if not np.isfinite(dvol) or dvol < args.min_dvol_usd:
            n_skip_liq += 1
            continue
        b_ = to_bars(df)
        if len(b_) < Z_WIN * 2:
            n_skip_short += 1
            continue
        n_used += 1
        Zs = zscores(b_)
        for zt in Z_THRESHS:
            for name, d in signals(b_, zt, Zs).items():
                for h in HOLDS:
                    arr = eval_signal(b_, d, h)
                    if len(arr) == 0:
                        continue
                    key = (name, zt, h)
                    acc.setdefault(key, []).append(arr)
                    if len(arr) >= args.min_trades_sym:
                        per_sym.setdefault(key, []).append(arr)
        if i % 100 == 0:
            log.info("%d/%d 처리 (사용 %d)", i, len(files), n_used)

    log.info("사용 %d종목 | 유동성 탈락 %d | 표본부족 %d", n_used, n_skip_liq, n_skip_short)
    if not acc:
        log.error("신호 0건 — 탐색 실패")
        return 1

    def stats(arr: np.ndarray, mode: str) -> tuple:
        gross, sp = arr[:, 0], arr[:, 1]
        if mode == "taker":
            fric = (sp + 2.0 * TAKER_FEE_BP) / 10_000.0
        else:                       # maker — 스프레드 크로싱 없음, 수수료 절반
            fric = (2.0 * MAKER_FEE_BP) / 10_000.0 * np.ones_like(gross)
        net = gross - fric
        n, sd = len(net), net.std(ddof=1) if len(net) > 1 else 0.0
        t = float(net.mean() / (sd / np.sqrt(n))) if n > 2 and sd > 0 else float("nan")
        return (float(gross.mean() * 1e4), float(fric.mean() * 1e4),
                float(net.mean() * 1e4), t, n)

    rows = []
    for key, chunks in acc.items():
        name, zt, h = key
        a_all = np.vstack(chunks)
        rec = {"signal": name, "z": zt, "hold_bars": h, "hold_min": h * BAR_MIN,
               "n_symbols": len(per_sym.get(key, []))}
        for mode in ("taker", "maker"):
            g, fr, nt, t, n = stats(a_all, mode)
            syms = per_sym.get(key, [])
            if syms:
                per = [stats(x, mode)[2] for x in syms]
                breadth = float(np.mean([v > 0 for v in per]))
            else:
                breadth = float("nan")
            rec.update({f"{mode}_gross_bp": g, f"{mode}_fric_bp": fr,
                        f"{mode}_net_bp": nt, f"{mode}_t": t,
                        f"{mode}_breadth": breadth})
            rec["n_trades"] = n
        rows.append(rec)

    def ok(r, mode):
        return (r[f"{mode}_net_bp"] > 0 and np.isfinite(r[f"{mode}_t"])
                and r[f"{mode}_t"] >= 3.0
                and np.isfinite(r[f"{mode}_breadth"]) and r[f"{mode}_breadth"] >= 0.55)

    for mode in ("taker", "maker"):
        res = sorted(rows, key=lambda r: -(r[f"{mode}_t"]
                                           if np.isfinite(r[f"{mode}_t"]) else -99))
        head = ("시장가 양방향 (스프레드 크로싱 + 테이커 4bp x2)" if mode == "taker"
                else "지정가 양방향 (크로싱 없음 + 메이커 2bp x2) — 낙관적 상한")
        print("\n" + "=" * 108)
        print(f"초단기 주문흐름 신호 탐색 — {n_used}종목 / 최근 {args.days}일 / "
              f"유동성 ${args.min_dvol_usd:,.0f}일  |  마찰 = {head}")
        print("=" * 108)
        print(f"{'신호':<21}{'z':>4}{'보유':>7}{'거래수':>9}{'종목':>6}"
              f"{'gross bp':>11}{'마찰':>8}{'net bp':>10}{'t':>8}{'breadth':>9}  판정")
        print("-" * 108)
        for r in res[:22]:
            print(f"{r['signal']:<21}{r['z']:>4.0f}{r['hold_min']:>6}분{r['n_trades']:>9,}"
                  f"{r['n_symbols']:>6}{r[f'{mode}_gross_bp']:>+11.2f}"
                  f"{r[f'{mode}_fric_bp']:>8.2f}{r[f'{mode}_net_bp']:>+10.2f}"
                  f"{r[f'{mode}_t']:>+8.2f}{r[f'{mode}_breadth']:>9.2f}"
                  f"  {'★ PASS' if ok(r, mode) else ''}")
        n_pass = sum(1 for r in rows if ok(r, mode))
        print("=" * 108)
        print(f"  기준 net>0 & t>=3.0 & breadth>=0.55  →  통과 {n_pass}/{len(rows)}"
              f"  (상위 22칸만 표시)\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_symbols": n_used, "days": args.days,
                   "min_dvol_usd": args.min_dvol_usd,
                   "z_threshs": list(Z_THRESHS), "holds_min": [h * BAR_MIN for h in HOLDS],
                   "results": rows}, fh, indent=2, ensure_ascii=False)
    log.info("저장: %s (%d칸)", args.out, len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
