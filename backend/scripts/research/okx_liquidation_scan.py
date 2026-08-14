"""가설 12 — **강제청산 캐스케이드** (OKX 라벨 → 바이낸스 실행).

왜 이 축인가
  초단기 8가설이 전부 같은 벽에서 멈췄다: **역선택**. 상대가 나보다 안다.
  강제청산은 그 벽에 뚫린 유일한 구멍이다 — 청산당하는 쪽은 정보가 있어서
  파는 게 아니라 **거래소가 강제로 닫는 것**이고, 추측이 아니라 **거래소가
  라벨을 붙여준다.**

  2026-08-11 오전에 이 축을 "데이터 부재" 로 닫았다. **바이낸스만 보고 닫았다.**
      바이낸스: `!forceOrder@arr` 3형태 전부 0건 / REST 404·계좌한정
      **OKX: WS `liquidation-orders` 작동 + REST 과거분 제공 (둘 다 무료)**
  OKX USDT 무기한 428종목 중 **256종목이 바이낸스에도 있다.**

가설
  OKX 에서 강제 매도가 쏟아지면 같은 코인의 **바이낸스 가격**도 눌린다.
  그 압력은 **정보가 아니라 강제**이므로 되돌아온다.
  → 청산 방향의 **반대**로 진입해 1~30분 보유.

  교차 거래소인 것이 오히려 유리하다. OKX 청산을 보고 바이낸스에서 실행하므로
  같은 장부를 밟지 않는다.

오늘 검증한 세 조건을 유일하게 다 만족한다
  · 속도 불필요 — 캐스케이드는 초~분 단위로 전개된다
  · 미리 반영 불가 — 예고가 없다 (펀딩 정산과 결정적으로 다름, 교훈 #85)
  · 마찰 대비 큰 이동 — 캐스케이드는 수십~수백 bp

한계 (정직하게)
  OKX REST 는 **약 1일치**만 준다. 그래서 이 스캔은 **권고용(advisory)** 이다
  (교훈 #30: 데이터 창 30% 미만 → 판정 아닌 권고). 확정은 WS 수집기로 축적한
  뒤에 한다.

무엇을 조심하는가
  · 마찰 = 바이낸스 테이커 왕복 10bp + 실측 스프레드.
  · **겹침 금지** — 같은 캐스케이드를 여러 번 세지 않게 보유기간만큼 debounce.
  · 종목별 백분위 (교훈 #75), 유동성 관문 (교훈 #78).
  · 신호 시각 이후 봉에서만 진입 (교훈 #83 lookahead).

사용:
  python3 scripts/research/okx_liquidation_scan.py
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("okx_liq")

OKX = "https://www.okx.com/api/v5/public/liquidation-orders"
FAPI = "https://fapi.binance.com"
TAKER_RT_BP = 10.0
HOLDS_MIN = (1, 3, 5, 15, 30)
MIN_CELL = 200


def matched_symbols() -> list:
    ok = requests.get("https://www.okx.com/api/v5/public/instruments",
                      params={"instType": "SWAP"}, timeout=30).json()["data"]
    oks = [x["instId"] for x in ok if x["instId"].endswith("-USDT-SWAP")]
    bn = requests.get(f"{FAPI}/fapi/v1/exchangeInfo", timeout=30).json()
    bns = {s["symbol"] for s in bn["symbols"]
           if s["contractType"] == "PERPETUAL" and s["status"] == "TRADING"}
    out = []
    for o in oks:
        b = o.replace("-USDT-SWAP", "") + "USDT"
        if b in bns:
            out.append((o, o.replace("-SWAP", ""), b))
    return out


def fetch_liq(fam: str, pages: int = 6) -> list:
    """OKX 청산 이력. after=가장 오래된 ts 로 페이지네이션."""
    rows, after = [], None
    for _ in range(pages):
        p = {"instType": "SWAP", "state": "filled", "instFamily": fam, "limit": "100"}
        if after:
            p["after"] = after
        try:
            r = requests.get(OKX, params=p, timeout=25).json()
        except Exception:
            break
        d = r.get("data") or []
        if not d:
            break
        ts = []
        for x in d:
            inst = x.get("instId", "")
            for y in x.get("details", []):
                try:
                    t = int(y["ts"])
                    px = float(y.get("bkPx") or 0)
                    sz = float(y.get("sz") or 0)
                except Exception:
                    continue
                ts.append(t)
                # posSide=long 청산 → 강제 **매도**. side 필드는 청산주문 방향.
                rows.append({"inst": inst, "ts": t, "bkPx": px, "sz": sz,
                             "pos": y.get("posSide"), "side": y.get("side")})
        if not ts:
            break
        after = str(min(ts))
        time.sleep(0.22)
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description="OKX 강제청산 → 바이낸스 되돌림")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--cache", default=str(ROOT / "runs" / "okx_liq"))
    p.add_argument("--min-dvol-usd", type=float, default=10_000_000)
    p.add_argument("--limit-sym", type=int, default=120)
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "okx_liquidation_scan.json"))
    args = p.parse_args()
    os.makedirs(args.cache, exist_ok=True)

    pairs = matched_symbols()
    log.info("OKX↔바이낸스 대응 %d종목", len(pairs))

    # 바이낸스 유동성 관문 + 가격 준비
    px_map, sp_map = {}, {}
    for f in sorted(glob.glob(os.path.join(args.data_dir, "*_agg1m.joblib"))):
        b = os.path.basename(f).replace("_agg1m.joblib", "")
        px_map[b] = f
    use = []
    for inst, fam, bsym in pairs:
        if bsym in px_map:
            use.append((inst, fam, bsym))
    use = use[:args.limit_sym]
    log.info("아카이브 보유 %d종목 사용", len(use))

    all_rows, fams = [], set()
    for i, (inst, fam, bsym) in enumerate(use, 1):
        if fam in fams:
            continue
        fams.add(fam)
        cf = os.path.join(args.cache, f"{fam}.json")
        if os.path.exists(cf):
            rows = json.load(open(cf))
        else:
            rows = fetch_liq(fam)
            json.dump(rows, open(cf, "w"))
        all_rows.extend(rows)
        if i % 20 == 0:
            log.info("%d/%d (청산 %d건 누적)", i, len(use), len(all_rows))

    if not all_rows:
        log.error("청산 기록 0건")
        return 1
    L = pd.DataFrame(all_rows)
    L["ts"] = pd.to_datetime(L["ts"], unit="ms")
    L["usd"] = L["bkPx"] * L["sz"]
    L["bsym"] = L["inst"].str.replace("-USDT-SWAP", "USDT", regex=False)
    log.info("청산 %d건 / 종목 %d / 기간 %s ~ %s",
             len(L), L.bsym.nunique(), L.ts.min(), L.ts.max())

    # 분 단위로 집계 — posSide=long 청산은 강제 매도(가격 하락 압력)
    L["dir"] = np.where(L["pos"] == "long", -1.0, 1.0)
    L["minute"] = L["ts"].dt.floor("1min")
    g = L.groupby(["bsym", "minute"]).apply(
        lambda x: pd.Series({"net_usd": float((x.usd * x.dir).sum()),
                             "gross_usd": float(x.usd.sum()),
                             "n": len(x)}), include_groups=False).reset_index()

    # 아카이브(≈8/09까지)와 청산 구간(8/10~)이 겹치지 않는다 → 해당 구간 1분봉을
    # 바이낸스 REST 로 직접 받는다. 스프레드는 아카이브 중앙값을 재사용한다.
    t_lo = int((L.ts.min() - pd.Timedelta(minutes=10)).timestamp() * 1000)
    t_hi = int((L.ts.max() + pd.Timedelta(minutes=60)).timestamp() * 1000)
    kdir = os.path.join(args.cache, "klines")
    os.makedirs(kdir, exist_ok=True)

    def live_1m(sym: str):
        cf = os.path.join(kdir, f"{sym}.joblib")
        if os.path.exists(cf):
            return joblib.load(cf)
        rows, cur = [], t_lo
        while cur < t_hi:
            try:
                r = requests.get(f"{FAPI}/fapi/v1/klines",
                                 params={"symbol": sym, "interval": "1m",
                                         "startTime": cur, "limit": 1500}, timeout=25)
                if r.status_code != 200:
                    break
                d = r.json()
            except Exception:
                break
            if not d:
                break
            rows.extend(d)
            nxt = int(d[-1][0]) + 60_000
            if nxt <= cur:
                break
            cur = nxt
            time.sleep(0.06)
        if not rows:
            return None
        df = pd.DataFrame(rows).iloc[:, :5]
        df.columns = ["ot", "o", "h", "l", "c"]
        df["ts"] = pd.to_datetime(df["ot"].astype("int64"), unit="ms")
        out = df.set_index("ts")["o"].astype(float).sort_index()
        out = out[~out.index.duplicated(keep="last")]
        joblib.dump(out, cf)
        return out

    res = []
    cells: dict = {}
    for bsym, gg in g.groupby("bsym"):
        f = px_map.get(bsym)
        if not f:
            continue
        try:
            d = joblib.load(f)
        except Exception:
            continue
        d = d[~d.index.duplicated(keep="last")].sort_index()
        if d["quote_volume"].resample("1D").sum().median() < args.min_dvol_usd:
            continue
        px = live_1m(bsym)
        if px is None or len(px) < 500:
            continue
        fric = TAKER_RT_BP + float(d["eff_spread_bp_adj"].median())
        idx = px.index
        gg = gg.sort_values("minute")
        # 종목별 청산 규모 백분위 (교훈 #75)
        thr = gg.gross_usd.quantile([0.5, 0.8, 0.95]).to_dict()
        for H in HOLDS_MIN:
            last = pd.Timestamp("1970-01-01")
            for _, r in gg.iterrows():
                m = r.minute
                if (m - last).total_seconds() / 60 < H:      # 겹침·중복 차단
                    continue
                # lookahead 방지: 그 분의 청산은 다음 봉 시가에야 실행 가능
                t0 = m + pd.Timedelta(minutes=1)
                t1 = t0 + pd.Timedelta(minutes=H)
                if t0 not in idx or t1 not in idx:
                    continue
                last = m
                fwd = (px[t1] / px[t0] - 1.0) * 1e4
                # 되돌림 베팅: 강제 매도(dir<0)면 **롱**
                sgn = -np.sign(r.net_usd)
                if sgn == 0:
                    continue
                bp = sgn * fwd - fric
                band = ("① 중앙이하" if r.gross_usd < thr[0.5]
                        else "② 50~80%" if r.gross_usd < thr[0.8]
                        else "③ 80~95%" if r.gross_usd < thr[0.95]
                        else "④ 상위5%")
                cells.setdefault((H, band), []).append(bp)
                cells.setdefault((H, "전체"), []).append(bp)

    for (H, band), v in cells.items():
        if len(v) < MIN_CELL:
            continue
        a = np.array(v)
        se = a.std(ddof=1) / np.sqrt(len(a))
        res.append({"hold": H, "band": band, "n": len(a), "net_bp": float(a.mean()),
                    "se_bp": float(se), "t": float(a.mean() / se) if se else np.nan,
                    "win": float((a > 0).mean() * 100)})
    if not res:
        log.error("판정 가능한 셀 없음 (표본 부족)")
        return 1
    df = pd.DataFrame(res)

    print("\n" + "=" * 100)
    print(f"가설 12 — OKX 강제청산 → 바이낸스 되돌림  ({L.bsym.nunique()}종목)")
    print("=" * 100)
    print(f"  기간 {L.ts.min()} ~ {L.ts.max()} (약 {(L.ts.max()-L.ts.min()).total_seconds()/86400:.1f}일)")
    print(f"  ** 데이터 창이 짧다 — 판정이 아니라 **권고(advisory)** 다 (교훈 #30) **")
    print(f"  베팅: 강제 매도면 롱, 강제 매수면 숏. 마찰 = 테이커 왕복 10bp + 스프레드, 차감 후")
    print("-" * 100)
    print(f"{'보유(분)':>9}{'청산규모':<14}{'표본':>8}{'net bp':>11}{'오차':>8}{'t':>8}{'승률%':>8}  판정")
    print("-" * 100)
    for _, r in df.sort_values(["hold", "band"]).iterrows():
        ok = r.net_bp > 0 and r.t >= 3.0
        print(f"{r.hold:>9.0f}{r.band:<14}{r.n:>8,.0f}{r.net_bp:>+11.2f}{r.se_bp:>8.2f}"
              f"{r.t:>+8.2f}{r.win:>8.1f}  {'★ 유망' if ok else ''}")
    n_pass = int(((df.net_bp > 0) & (df.t >= 3.0)).sum())
    print("-" * 100)
    print(f"  net>0 & t>=3.0 : {n_pass}/{len(df)}")
    b = df.sort_values("net_bp", ascending=False).iloc[0]
    print(f"  최고: 보유 {b.hold:.0f}분 / {b.band} → {b.net_bp:+.2f} ± {b.se_bp:.2f}bp "
          f"(승률 {b.win:.1f}%, 표본 {b.n:,.0f})")
    print("=" * 100 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_liq": len(L), "n_symbols": int(L.bsym.nunique()),
                   "span_days": float((L.ts.max() - L.ts.min()).total_seconds() / 86400),
                   "advisory_only": True, "results": res}, fh, indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
