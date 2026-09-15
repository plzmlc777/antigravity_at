"""손익 가속도 — 정기 보고용 (2026-09-12, 대표님 지시).

속도 = 누적 자본%의 시간당 기울기.  가속도 = 속도의 변화율.
`누적 ~ a + b·t + c·t²` 의 **2c** 가 평균 가속도다.

⚠ 누적곡선은 자기상관이 극도로 높아 t 를 과대평가한다. 부호와 크기만 읽고,
  유의성 판정은 **거래당 엣지 기울기**(맨 아래)로 한다 — 그쪽이 독립 관측이다.
⚠ 청산 기준은 보유시간만큼 밀린다(교훈#110). 보유가 다른 갈래를 비교할 땐
  신호(진입) 기준을 같이 본다.
"""
import numpy as np, pandas as pd, pathlib, sys

ROOT = pathlib.Path("/home/mint/auto_trading/backend")
PAPER = ROOT / "runs" / "kinematics_paper"
START = pd.Timestamp("2026-09-09 02:00", tz="UTC")
# ⚠ **슬롯 수는 갈래마다 다르다.** 2026-09-15 15:22~21:10 동안 여기가 `SL = 3`
#   으로 박혀 있어, 슬롯 6인 s6양다리(계좌15 실거래)의 자본%가 **정확히 2배**로
#   출력됐다(+1.24% 로 찍혔으나 실제 +0.62%). 매 보고마다 손으로 고쳐야 했다.
#   자본% = 실현합 ÷ **그 갈래의 슬롯 수**다 — 상수로 두면 안 된다.
# ⚠ 목록은 `_rotate.BR` 과 같아야 한다. 이름은 `paper_ab.TRACKS` 가 정본이다.
#   09-15 에 풀을 9 → 16 으로 넓혔는데 여기만 9 로 남아, ⑦항에 **현행 실거래
#   규칙이 없는** 상태가 여섯 시간 이어졌다(교훈#88 — 경로를 검증하라).
BR = [("s3short_h4", "충격240", 3), ("s3short_h1", "충격60", 3),
      ("s3short_imp", "충격숏3", 3), ("s3short_impns", "무손숏3", 3),
      ("s3short_dir", "방향숏3", 3), ("s3short_conf", "확인숏3", 3),
      ("s3short_anti", "역확인3", 3), ("s3short_h4ec", "충격240냉", 3),
      ("s6both_imp", "충격스프3", 6),
      # ── 2026-09-15 풀 확장분 ────────────────────────────────
      ("s6both_h240", "s6양다리", 6), ("s2both", "s2양다리", 2),
      ("s10both", "s10양다리", 10), ("s6both_ac1", "체결자기여기", 6),
      ("s3short_rmz", "최장연속숏", 3),
      ("s10both_d5_utc01", "되돌림UTC1", 10),
      ("s10both_d5_revcont", "되돌림연속", 10)]
SLOTS = {nm: sl for _, nm, sl in BR}

# 실거래 원장 → (계좌번호, 이름) — **규칙을 교체하면 새 원장 디렉터리로 바꾼다.**
# ⚠ 이 등록표는 `_rotate.LIVE` · `_regime.TWINS` · `kine_halt_gate.ACCTS` 와
#   **네 곳이 함께** 움직인다. 2026-09-15 교체 때 이 파일만 빠져, 보고의
#   "실거래" 줄이 **이미 내려간 충격240 원장(imp3s·120건)** 을 계속 읽었다.
# 옛 원장은 보존만 한다 — runs/kinematics_live/imp3s · imp3s480
# (계좌번호, 이름, **슬롯 수**) — 슬롯을 빼먹으면 자본%가 통째로 틀린다.
LIVE = {"s6b240": (15, "s6양다리", 6), "anti3s": (8, "역확인3", 3)}

# quad() 는 10시간, edge() 는 10거래가 있어야 답을 낸다. 모자라면 **추정하지
# 않고 표본부족으로 비운다** — 보고 형식 §2 "스크립트가 비운 칸을 채우지 않는다".
MIN_N = 10


def ld(tag, sl):
    # ⚠ 갓 띄운 갈래는 청산이 없어 trades.csv 가 아직 없다. 여기서 죽으면
    #   **표가 통째로 안 나온다.** 빈 표로 넘긴다.
    f = PAPER / tag / "trades.csv"
    if not f.exists():
        return pd.DataFrame({"entry_ts": pd.Series(dtype="datetime64[ns, UTC]"),
                             "closed_ts": pd.Series(dtype="datetime64[ns, UTC]"),
                             "net_pct": pd.Series(dtype=float),
                             "cap": pd.Series(dtype=float)})
    d = pd.read_csv(f)
    for c in ("entry_ts", "closed_ts"):
        d[c] = pd.to_datetime(d[c], utc=True, format="mixed")
    d = d[d.entry_ts >= START].copy()
    d["cap"] = d.net_pct / sl          # ← 갈래별 슬롯
    return d


def curve(d, tcol, end):
    g = d.groupby(d[tcol].dt.floor("h")).cap.sum()
    idx = pd.date_range(START.floor("h"), end.ceil("h"), freq="h")
    return g.reindex(idx, fill_value=0.0).cumsum()


def quad(cum):
    t = np.arange(len(cum), dtype=float); y = cum.to_numpy()
    if len(t) < 10:
        return np.nan, np.nan, np.nan
    c2, c1, c0 = np.polyfit(t, y, 2)
    res = y - np.polyval([c2, c1, c0], t)
    X = np.vstack([t**2, t, np.ones_like(t)]).T
    se = np.sqrt(((res**2).sum() / (len(t) - 3)) * np.linalg.inv(X.T @ X)[0, 0])
    return 2*c2, c1, 2*c2/se if se else np.nan


def vel(cum, w):
    return (cum.iloc[-1] - cum.iloc[-1-w]) / w if len(cum) > w else np.nan


def edge(d):
    y = d.sort_values("entry_ts").net_pct.to_numpy(); x = np.arange(len(y), dtype=float)
    if len(y) < 10:
        return np.nan, np.nan
    b, a = np.polyfit(x, y, 1)
    res = y - (a + b*x)
    se = np.sqrt((res**2).sum()/(len(x)-2)/((x-x.mean())**2).sum())
    return b, b/se if se else np.nan


def main():
    ds = {nm: ld(tag, sl) for tag, nm, sl in BR}
    end = max(d.closed_ts.max() for d in ds.values() if len(d))
    print("■ 손익 가속도 — 페이퍼 (공통 출발선 09-09 11:00 KST~)")
    print(f"{'갈래':<11}{'슬롯':>5}{'6h':>8}{'12h':>8}{'24h':>8}{'평균속도':>9}"
          f"{'가속도':>10}{'판정':>7}{'엣지기울기':>11}{'t':>7}")
    print("-" * 86)
    for _, nm, sl in BR:
        d = ds[nm]
        if len(d) < MIN_N:
            print(f"{nm:<11}{sl:>5}   청산 {len(d)}건 — 표본부족(필요 {MIN_N})")
            continue
        cum = curve(d, "closed_ts", end)
        acc, v, _ = quad(cum)
        eb, et = edge(d)
        mark = "감속" if acc < 0 else "가속"
        star = "*" if abs(et) > 1.96 else " "
        print(f"{nm:<11}{sl:>5}{vel(cum,6):>8.3f}{vel(cum,12):>8.3f}"
              f"{vel(cum,24):>8.3f}{v:>9.3f}{acc:>10.5f}{mark:>7}"
              f"{eb:>10.4f}{star}{et:>7.2f}")
    print("  속도 %p/h · 가속도 %p/h² · 엣지기울기 %p/거래(* = |t|>1.96 유의)")
    print("  ※ 가속도 t 는 자기상관으로 부풀려진다 — **판정은 엣지기울기 t 로 한다**")

    # 신호(진입) 기준 — 보유시간 보정
    print("\n  ▸ 신호(진입) 기준 가속도 — 교훈#110 보정")
    o = []
    for _, nm, _sl in BR[:2]:
        cum = curve(ds[nm], "entry_ts", end)
        acc, v, _ = quad(cum)
        o.append(f"{nm} 속도 {v:+.3f} · 가속도 {acc:+.5f}")
    print("    " + " | ".join(o))

    # 실거래 — 계좌별 새 원장
    for d, (aid, nm, sl) in LIVE.items():
        f = ROOT / "runs" / "kinematics_live" / d / "trades.csv"
        if not f.exists():
            print(f"\n■ 실거래 계좌 {aid} ({nm} 규칙) — 원장 0건 · 청산 이력 없음")
            print(f"  표본부족 (필요 {MIN_N}건) — 속도·가속도·엣지기울기 판정 보류")
            continue
        L = pd.read_csv(f)
        for c in ("entry_ts", "closed_ts"):
            L[c] = pd.to_datetime(L[c], utc=True, format="mixed")
        L = L.sort_values("closed_ts")
        L["cap"] = L.net_pct / sl          # ← 계좌별 슬롯
        n_st = int(L.stopped.sum()) if "stopped" in L else 0
        print(f"\n■ 실거래 계좌 {aid} ({nm} 규칙 · 슬롯 {sl}) — 원장 {len(L)}건 · "
              f"{L.closed_ts.min():%m-%d} ~ {L.closed_ts.max():%m-%d} · "
              f"실현합 {L.net_pct.sum():+.2f}%p (자본 {L.cap.sum():+.2f}%) · 손절 {n_st}")
        if len(L) < MIN_N:
            print(f"  표본부족 (필요 {MIN_N}건) — 속도·가속도·엣지기울기 판정 보류")
            continue
        g = L.groupby(L.closed_ts.dt.floor("h")).cap.sum()
        idx = pd.date_range(g.index.min(), g.index.max(), freq="h")
        cum = g.reindex(idx, fill_value=0.0).cumsum()
        acc, v, _ = quad(cum)
        eb, et = edge(L)
        print(f"  속도 6h {vel(cum,6):+.3f} · 12h {vel(cum,12):+.3f} · "
              f"24h {vel(cum,24):+.3f} · 평균 {v:+.3f} %p/h")
        print(f"  가속도 {acc:+.5f} %p/h² ({'감속' if acc<0 else '가속'}) · "
              f"엣지기울기 {eb:+.4f}%p/거래 (t {et:+.2f}{'*' if abs(et)>1.96 else ''})")


if __name__ == "__main__":
    main()
