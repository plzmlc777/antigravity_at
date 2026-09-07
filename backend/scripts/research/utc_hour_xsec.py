"""UTC01(되돌림 횡단면) — 시각 위약 · 방향 대조군 · 최대통계량.

## 무엇을 재나

페이퍼 갈래 `utc01` 은 매일 **01:00 UTC** 에 1시간 되돌림 순위를 매겨
가장 많이 떨어진 5종목 롱 · 가장 많이 오른 5종목 숏을 5분 뒤 잡고 120분 뒤 판다.
5일 · 5묶음으로 +4.80% 가 나왔다. **독립 관측이 5개**라 판정할 수 없다.

여기서는 아카이브 5분봉(`runs/bars5m_ext`, 521종목 · 중앙 2024-10~2026-08)으로
같은 규칙을 **24개 시각 전부** 돌려 세 가지를 묻는다.

    ① 시각 위약     01시가 특별한가, 아무 시각이나 되는가 (교훈#85)
    ② 방향 대조군   뒤집으면 어떻게 되나. 합이 -2×통행료면 정보가 없다 (교훈#91)
    ③ 최대통계량    24시각 × 2방향 = 48칸을 뒤졌다. 섞은 자료로 **같은 48칸을
                    다시 전부** 뒤진 최고 t 가 기준선이다 (교훈#95)

## 관측 단위는 **날**이다

한 날의 열 다리는 같은 2시간의 시장을 공유한다 — 독립이 아니다.
묶음(날) 수익 하나를 관측 하나로 세고, t 는 날 위에서 잰다 (교훈#92·#112).

## 페이퍼와 다른 점 (정직하게 적는다)

    체결가   페이퍼는 1분봉 종가, 여기는 5분봉 종가
    생존필터 페이퍼는 분당 체결수 중앙 >= 5. 아카이브에 체결수가 없어
             **거래대금**으로 대신한다 — 같은 것이 아니다
    손절     페이퍼는 최근 10분 1분봉 저/고. 여기는 보유 구간 5분봉 저/고라
             **더 촘촘하다**(발동이 더 잘 잡힌다)
    펀딩     120분 보유는 정산을 거의 안 지난다. 페이퍼 실측 합 0.0000% → 뺀다
    이력요구 페이퍼의 rev 는 z_vel 계산 때문에 790분 이력을 요구한다.
             여기도 158봉(=790분)으로 맞춘다

사용:
    python3 -m scripts.research.utc_hour_xsec --smoke          # 예비비행 20종목
    python3 -m scripts.research.utc_hour_xsec                  # 본실행
    python3 -m scripts.research.utc_hour_xsec --perm 500
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("utc_xsec")


# ── 설정은 이 하나뿐이다. 즉석 하드코딩 금지(하네스 규칙 ①)
@dataclass
class Cfg:
    bars: str = "runs/bars5m_ext"
    out: str = "runs/research_track/utc_hour_xsec"
    bar_min: int = 5                    # 봉 길이(분)
    sig_min: int = 60                   # 되돌림 창(분)
    delay_min: int = 5                  # 신호 뒤 진입 지연(분)
    hold_min: int = 120                 # 보유(분)
    n_side: int = 5                     # 다리당 종목 수
    stop_pct: float = 5.0               # 최대 손절(%)
    fee_rt: float = 0.072               # **왕복** 수수료(%)
    warmup_bars: int = 158              # 790분 = 페이퍼 rev 이력 요구량
    min_dv_usd: float = 50_000.0        # 직전 24h 5분 거래대금 중앙 하한
    hours: tuple = tuple(range(24))     # ① 시각 위약
    dirs: tuple = (1, -1)               # ② 방향 대조군
    n_perm: int = 200                   # ③ 최대통계량 반복
    seed: int = 20260905
    min_days: int = 60                  # 검정력 사전검사 하한(규칙 ⑦)
    symbols: int = 0                    # 0 = 전부. 예비비행은 20

    @property
    def sig_bars(self) -> int:
        return self.sig_min // self.bar_min

    @property
    def delay_bars(self) -> int:
        return self.delay_min // self.bar_min

    @property
    def hold_bars(self) -> int:
        return self.hold_min // self.bar_min


# ── 기질 적재 ─────────────────────────────────────────────
def load_panel(c: Cfg) -> pd.DataFrame:
    """종목별로 한 번씩 읽어 (날 · 시각) 앵커 표를 만든다.

    ⚠ 종목을 하나씩 처리하고 결과만 남긴다. 전 패널을 메모리에 올리면
      1.9GB 원본이 수 GB 로 부푼다(2026-09-04 민트 I/O 붕괴 전례).
    """
    fs = sorted((ROOT / c.bars).glob("*.parquet"))
    if c.symbols:
        fs = fs[:c.symbols]
    log.info("종목 %d개 적재 시작", len(fs))
    out, t0 = [], time.time()
    for i, f in enumerate(fs, 1):
        d = pd.read_parquet(f, columns=["ts", "h", "l", "c", "v"])
        if len(d) < c.warmup_bars + c.hold_bars + 10:
            continue
        d = d.sort_values("ts").reset_index(drop=True)
        ts = d.ts.to_numpy()
        cl = d.c.to_numpy(np.float64)
        hi = d.h.to_numpy(np.float64)
        lo = d.l.to_numpy(np.float64)
        dv = (d.v.to_numpy(np.float64) * cl)          # 거래대금 근사
        n = len(d)

        # ⚠ 격자가 끊겨 있으면(상장정지·수집결손) 인덱스 산술이 시각을 어긴다.
        #   앵커에서 실제 시각 간격을 다시 확인한다.
        i_sig = np.arange(n)
        i_ent = i_sig + c.delay_bars
        i_ext = i_ent + c.hold_bars
        ok = (i_sig >= c.sig_bars + c.warmup_bars) & (i_ext < n)
        i_sig, i_ent, i_ext = i_sig[ok], i_ent[ok], i_ext[ok]
        if len(i_sig) == 0:
            continue
        step = np.timedelta64(c.bar_min, "m")
        grid = ((ts[i_ent] - ts[i_sig]) == step * c.delay_bars) & \
               ((ts[i_ext] - ts[i_ent]) == step * c.hold_bars) & \
               ((ts[i_sig] - ts[i_sig - c.sig_bars]) == step * c.sig_bars)
        i_sig, i_ent, i_ext = i_sig[grid], i_ent[grid], i_ext[grid]
        if len(i_sig) == 0:
            continue

        # 앵커는 정각만 — 24시각 × 날
        anc = pd.DatetimeIndex(ts[i_sig])
        m0 = anc.minute == 0
        i_sig, i_ent, i_ext, anc = i_sig[m0], i_ent[m0], i_ext[m0], anc[m0]
        if len(i_sig) == 0:
            continue

        px = cl[i_ent]
        sig = cl[i_sig] / cl[i_sig - c.sig_bars] - 1.0     # 1시간 수익
        fwd = cl[i_ext] / px - 1.0                          # 보유 수익(롱 기준)
        # 보유 경로의 저/고 — 진입 **다음** 봉부터 청산 봉까지.
        # i_ext = i_ent + hold_bars 이므로 그 구간은 정확히 hold_bars 개다.
        # ⚠ 앵커마다 슬라이스를 잘라 min/max 하면 종목당 3초다(521종목 26분).
        #   구르는 창을 한 번 만들어 앵커에서 꺼내면 같은 값이 수십 배 빠르다.
        lo_roll = pd.Series(lo).rolling(c.hold_bars).min().to_numpy()
        hi_roll = pd.Series(hi).rolling(c.hold_bars).max().to_numpy()
        plo, phi = lo_roll[i_ext], hi_roll[i_ext]
        # 유동성 — 직전 24h(288봉) 5분 거래대금 중앙
        dvm = pd.Series(dv).rolling(288, min_periods=96).median().shift(1) \
                .to_numpy()[i_sig]

        out.append(pd.DataFrame({
            "sym": f.stem,
            "day": anc.normalize().values,
            "hour": anc.hour.values.astype(np.int8),
            "sig": sig.astype(np.float32),
            "fwd": fwd.astype(np.float32),
            "lo_r": (plo / px - 1.0).astype(np.float32),
            "hi_r": (phi / px - 1.0).astype(np.float32),
            "dvm": dvm.astype(np.float32)}))
        if i % 50 == 0:
            el = time.time() - t0
            log.info("  [%d/%d] %.1f분 · 남은 %.1f분", i, len(fs), el / 60,
                     el / 60 * (len(fs) - i) / max(i, 1))
    p = pd.concat(out, ignore_index=True)
    p = p.dropna(subset=["sig", "fwd", "lo_r", "hi_r", "dvm"])
    p = p[p.dvm >= c.min_dv_usd]
    p["sym"] = p.sym.astype("category")
    log.info("앵커 %s행 · 종목 %d · 날 %d",
             f"{len(p):,}", p.sym.nunique(), p.day.nunique())
    return p


# ── 커널 — 모든 칸이 **이 함수 하나**를 지난다(하네스 규칙 ⑤)
def basket_daily(g: pd.DataFrame, c: Cfg, direction: int,
                 fwd: np.ndarray, lo_r: np.ndarray, hi_r: np.ndarray
                 ) -> tuple[np.ndarray, np.ndarray]:
    """한 시각의 (날별 묶음 수익, 날) 을 낸다. 수익 단위는 **%**.

    direction +1 : 많이 떨어진 쪽 롱 · 많이 오른 쪽 숏 (되돌림, 페이퍼와 같음)
    direction -1 : 거울 (추세)
    """
    sig = g.sig.to_numpy()
    day = g.day.to_numpy()
    order = np.lexsort((sig, day))                  # 날 안에서 sig 오름차순
    day_s, sig_s = day[order], sig[order]
    fwd_s, lo_s, hi_s = fwd[order], lo_r[order], hi_r[order]
    bounds = np.flatnonzero(np.r_[True, day_s[1:] != day_s[:-1], True])
    days, rets = [], []
    st = c.stop_pct / 100.0
    for a, b in zip(bounds[:-1], bounds[1:]):
        k = b - a
        if k < 2 * c.n_side:                        # 후보 부족한 날은 건너뛴다
            continue
        lo_idx = np.arange(a, a + c.n_side)         # sig 최저 = 가장 떨어진
        hi_idx = np.arange(b - c.n_side, b)         # sig 최고 = 가장 오른
        if direction > 0:
            L, S = lo_idx, hi_idx
        else:
            L, S = hi_idx, lo_idx
        # 롱 — 손절은 저가가 -stop 을 스치면
        rl = np.where(lo_s[L] <= -st, -st, fwd_s[L])
        # 숏 — 고가가 +stop 을 스치면. 부호 규약 (진입-청산)/진입 (교훈#89)
        rs = np.where(hi_s[S] >= st, -st, -fwd_s[S])
        net = np.r_[rl, rs] * 100.0 - c.fee_rt
        days.append(day_s[a])
        rets.append(net.mean())
    return np.asarray(rets), np.asarray(days)


def tstat(x: np.ndarray) -> float:
    if len(x) < 3 or np.std(x, ddof=1) == 0:
        return np.nan
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def sweep(p: pd.DataFrame, c: Cfg, fwd=None, lo_r=None, hi_r=None) -> pd.DataFrame:
    """48칸(24시각 × 2방향) 전부. 같은 커널을 지난다."""
    fwd = p.fwd.to_numpy() if fwd is None else fwd
    lo_r = p.lo_r.to_numpy() if lo_r is None else lo_r
    hi_r = p.hi_r.to_numpy() if hi_r is None else hi_r
    hh = p.hour.to_numpy()
    rows = []
    for h in c.hours:
        m = hh == h
        if not m.any():
            continue
        g = p[m]
        for d in c.dirs:
            r, dy = basket_daily(g, c, d, fwd[m], lo_r[m], hi_r[m])
            if len(r) == 0:
                continue
            rows.append({"hour": h, "dir": d, "days": len(r),
                         "일평균%": r.mean(), "합%": r.sum(),
                         "t": tstat(r), "양수일%": 100 * (r > 0).mean()})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--smoke", action="store_true", help="예비비행 — 20종목")
    ap.add_argument("--symbols", type=int, default=0)
    ap.add_argument("--perm", type=int, default=200)
    ap.add_argument("--hours", default="", help="쉼표. 비우면 0~23 전부")
    ap.add_argument("--reuse", action="store_true",
                    help="앵커 표를 다시 만들지 않고 저장분을 쓴다")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    c = Cfg(symbols=20 if a.smoke else a.symbols, n_perm=a.perm)
    if a.hours:
        c.hours = tuple(int(x) for x in a.hours.split(","))
    # 설정 전문 기록(하네스 규칙 ⑦) — 나중에 "무슨 설정이었지"가 안 생기게
    log.info("설정 전문: %s", json.dumps(asdict(c), ensure_ascii=False))
    log.info("파생: 신호봉 %d · 지연봉 %d · 보유봉 %d",
             c.sig_bars, c.delay_bars, c.hold_bars)

    # 앵커 표를 디스크에 남긴다 — 적재가 30분대라 재실행마다 다시 만들면 낭비다.
    cache = ROOT / c.out / ("panel_%s.parquet" % (c.symbols or "all"))
    if a.reuse and cache.exists():
        p = pd.read_parquet(cache)
        p["sym"] = p.sym.astype("category")
        log.info("앵커 표 재사용 — %s (%s행)", cache, f"{len(p):,}")
    else:
        p = load_panel(c)
        cache.parent.mkdir(parents=True, exist_ok=True)
        p.to_parquet(cache, index=False)
        log.info("앵커 표 저장 — %s", cache)
    nd = p.groupby("hour").day.nunique()
    log.info("검정력 사전검사 — 시각별 날 수 최소 %d · 중앙 %d (하한 %d)",
             nd.min(), int(nd.median()), c.min_days)
    if nd.min() < c.min_days and not a.smoke:
        log.warning("일부 시각의 날 수가 하한 미만이다 — 결론을 그 시각에 걸지 마라")

    obs = sweep(p, c)
    obs = obs.sort_values("t", ascending=False)
    pd.set_option("display.width", 200)
    print("\n■ 관측 — 48칸 (dir +1 = 되돌림 = 페이퍼 규칙)")
    print(obs.to_string(index=False, float_format=lambda x: f"{x:9.4f}"))

    d = ROOT / c.out
    d.mkdir(parents=True, exist_ok=True)
    obs.to_csv(d / "observed.csv", index=False)
    (d / "config.json").write_text(json.dumps(asdict(c), ensure_ascii=False, indent=1))
    log.info("관측·설정 먼저 기록 — %s", d)

    # ③ 최대통계량 귀무 — 종목별 원형회전으로 신호↔미래 대응만 끊는다
    rng = np.random.default_rng(c.seed)
    fwd, lo_r, hi_r = (p.fwd.to_numpy(), p.lo_r.to_numpy(), p.hi_r.to_numpy())
    codes = p.sym.cat.codes.to_numpy()
    order = np.argsort(codes, kind="stable")
    bnd = np.flatnonzero(np.r_[True, codes[order][1:] != codes[order][:-1], True])
    null = []
    t1 = time.time()
    for j in range(c.n_perm):
        f2, l2, h2 = fwd.copy(), lo_r.copy(), hi_r.copy()
        for x, y in zip(bnd[:-1], bnd[1:]):
            idx = order[x:y]
            k = int(rng.integers(1, max(len(idx) - 1, 2)))
            f2[idx] = np.roll(fwd[idx], k)
            l2[idx] = np.roll(lo_r[idx], k)
            h2[idx] = np.roll(hi_r[idx], k)
        s = sweep(p, c, f2, l2, h2)
        null.append(np.nanmax(s.t.to_numpy()))
        if (j + 1) % 20 == 0:
            el = time.time() - t1
            log.info("  위약 %d/%d · %.1f분 · 남은 %.1f분", j + 1, c.n_perm,
                     el / 60, el / 60 * (c.n_perm - j - 1) / (j + 1))
            # ⚠ 부분 저장. 끝에 한 번에 쓰다 죽으면 몇 시간을 잃는다.
            np.save(ROOT / c.out / "null_max_t_partial.npy", np.asarray(null))
    null = np.asarray(null)
    obs_max = float(np.nanmax(obs.t.to_numpy()))
    pv = float((null >= obs_max).mean())
    print("\n■ 최대통계량 귀무 (원형회전 %d회 · 같은 48칸을 매번 다시 뒤짐)" % c.n_perm)
    print("  관측 최고 t  %.3f  (시각 %d · 방향 %+d)"
          % (obs_max, obs.iloc[0].hour, obs.iloc[0]["dir"]))
    print("  귀무 최고 t  중앙 %.3f · 90%% %.3f · 최대 %.3f"
          % (np.median(null), np.quantile(null, 0.9), null.max()))
    print("  **p = %.3f**" % pv)

    np.save(d / "null_max_t.npy", null)
    (d / "verdict.json").write_text(json.dumps(
        {"obs_max_t": obs_max, "p": pv, "n_perm": c.n_perm,
         "best_hour": int(obs.iloc[0].hour), "best_dir": int(obs.iloc[0]["dir"]),
         "null_med": float(np.median(null)), "null_max": float(null.max())},
        ensure_ascii=False, indent=1))
    log.info("기록 — %s", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
