#!/usr/bin/env python3
"""paradigm 251 등록 산출물 — 거래 JSON + paper spec + 게이트 CLI 명령 생성.

3군 게이트 통과분(2026-08-09, DefiLlama 880일 · h3d)을 2군 승격 큐에 올리기
위한 준비. **판정과 등록은 손으로 하지 않는다** — 이 스크립트는 거래 파일과
spec 만 만들고, 실제 판정·등록은 tier3_gate.py CLI 가 한다(생성된 .sh 참조).

가격은 `_substrate.daily_ohlcv` 로만 읽는다 — joblib 캐시 금지, 7일 초과 노후
시 SubstrateStale 로 중단(이 패러다임이 처음 GRAVEYARD 된 원인이 그 캐시였다).

등록 단위에 대하여
  검정은 이벤트별 동일가중 포트폴리오로 했으나(단일 시계열 신호라 종목별 t 를
  모으면 다중검정이다), 2군 인프라는 **종목별 세션**이고 좌석이 24석이다.
  포트폴리오를 한 세션으로 올릴 수 없으므로 게이트를 통과한 종목을 개별 등록한다.

  포트폴리오는 **최신성이 살아 있는 유동 32종목** 기준으로 봐야 한다 — DB 1m 이
  168종목에 대해 2026-05-12 에 멈춰 있어(백필 대상 26종목 하드코딩), 그걸 섞으면
  포트폴리오 구성이 그 날짜에 132 → 32 로 축소되고 recent_edge / decay_ratio 가
  구성변화를 알파로 오독한다. 실측 차이가 작지 않다:
    정지 포함 132종목  +1.2277%  t 2.645  양수비율 62.4%
    최신 32종목        +0.9146%  t 2.222  양수비율 50.0%   ← 이쪽이 근거
  즉 "종목 특수적이 아니다" 는 여전히 서지만(포트폴리오 t 2.222 PASS), breadth 는
  동전던지기 수준이다. 등록의 1차 근거는 종목 개별 게이트 통과이고, 포트폴리오는
  그것이 단일 종목 우연이 아님을 보이는 보조 근거다.

사용:
  cd backend && source venv/bin/activate
  python3 scripts/research/p251_emit_specs_and_trades.py
  bash runs/research_track/paradigm_251_stablecoin_supply_flow/enqueue_p251.sh
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._substrate import daily_ohlcv  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p251_emit")

OUT = ROOT / "runs" / "research_track" / "paradigm_251_stablecoin_supply_flow"
OUT.mkdir(parents=True, exist_ok=True)
SPEC_DIR = ROOT / "configs" / "paper_sessions"
DL_CACHE = ROOT / "runs" / "substrate" / "defillama_stablecoin_supply.json"

FEE_RT = 0.0008
Z_THRESH = 1.0
ROLL_WIN = 60
NET_DAYS = 7
HOLD = 3
CYCLE_MINUTES = 1440
ROUNDTRIP_FRICTION = 0.0008

# 게이트를 통과한 종목 (DL_full h3d, 앵커=구간종료). SOLUSDT 는 t 0.976 로 탈락.
SYMBOLS = ["BNBUSDT", "XRPUSDT", "AVAXUSDT", "LINKUSDT", "DOGEUSDT"]

NOTES = (
    "Research Track paradigm 251 — 3군 게이트 PASS 2026-08-09. "
    "USDT+USDC 합산 발행량 7일 순증감의 60일 롤링 z: z>=+1.0 LONG / z<=-1.0 SHORT, "
    "T+1 시가 진입, 보유 3일, 왕복 8bp. Substrate=DefiLlama stablecoins(무료·공개, "
    "USDT 2017-11~ 전체 이력). "
    "[종목 개별 판정] n=375~379, 거래당 +1.11~+2.32%, raw_t 1.75~4.94 (전 종목 h3d). "
    "[유니버스 횡단면] 신호가 단일 시계열이라 종목별 t 를 모으면 다중검정이므로 "
    "이벤트별 동일가중 포트폴리오로 검정. **최신성 갱신이 살아 있는 유동 32종목 기준**: "
    "h3d 이벤트 379 거래당 +0.9146% t 2.222 승률 56.5% decay 0.423 → G1 PASS. "
    "창 밖 구간(CoinGecko 365일 창 이전, 2024-01~2025-08)은 이벤트 226 거래당 "
    "+1.3506% t 2.357 로 오히려 더 강함 — 한 번도 검증 안 한 era 에서 재현됨. "
    "주의: 정지 종목(2026-05-12 이후 미갱신 100개)을 섞으면 +1.2277%/t 2.645/양수비율 "
    "62.4% 로 부풀려지는데 그건 포트폴리오 구성이 그 날짜에 132→32 로 축소되는 "
    "아티팩트다. 최신 32종목 기준 양수엣지 비율은 50.0% (동전던지기 수준). "
    "[G2] lookahead clean(일봉+T+1 시가), 마찰여유 9.7~28.6x, 실행주기여유 3.0x. "
    "h1d/h2d 는 G2 실행주기(1.0x/2.0x < 3.0x)로 차단되어 h3d 만 실행 가능. "
    "[한계] 포트폴리오 wt_t = -0.159 — 반감기 90일 가중으로 보면 최근 약 4개월이 "
    "음수다. raw_t 2.222 로 통과했으나 엣지가 고르게 깔린 게 아니라 대규모 유입 "
    "레짐에 버스트로 몰려 있을 가능성이 크다. in-sample 로는 더 못 가리며 이 세션의 "
    "forward 성과가 그 판별이다. Day-30 에 alpha<0 이면 TERMINATE 가 정상 동작이다. "
    "[substrate 주의] DB 1m 214종목 중 과거 온전(2024-01 시작)+최신 갱신을 모두 갖춘 "
    "종목은 12개뿐이며 본 종목은 그 안에 속한다. 최초 판정은 stale joblib(2026-05-12 "
    "정지)으로 decay_ratio 0.138 GRAVEYARD 됐다가 DB 재판정에서 0.481 로 반전된 건이다. "
    "Source: bn_stablecoin_supply_flow."
)


def build_signal() -> pd.DataFrame:
    raw = json.loads(DL_CACHE.read_text())
    frames = {}
    for k in ("usdt", "usdc"):
        d = pd.DataFrame(raw[k])
        d["date"] = pd.to_datetime(d["date"]).dt.date
        frames[k] = d.groupby("date", as_index=False)["supply"].last()
    m = frames["usdt"].merge(frames["usdc"], on="date", suffixes=("_usdt", "_usdc"))
    m = m.sort_values("date").reset_index(drop=True)
    m["combined"] = m["supply_usdt"] + m["supply_usdc"]
    m["net_7d"] = m["combined"].diff(NET_DAYS)
    roll = m["net_7d"].rolling(ROLL_WIN)
    m["z"] = (m["net_7d"] - roll.mean()) / roll.std()
    return m[["date", "z"]].dropna().reset_index(drop=True)


def backtest(price: pd.DataFrame, sig: pd.DataFrame, lag: int) -> tuple[list, int]:
    by_date = {d: (o, c) for d, o, c in
               zip(price.index.date, price["open"], price["close"])}
    trades, skipped = [], 0
    for _, row in sig.iterrows():
        z = row["z"]
        if abs(z) < Z_THRESH:
            continue
        side = 1.0 if z > 0 else -1.0
        entry_d = row["date"] + timedelta(days=lag)
        exit_d = entry_d + timedelta(days=HOLD)
        e, x = by_date.get(entry_d), by_date.get(exit_d)
        if e is None or x is None:
            skipped += 1
            continue
        ep, xp = float(e[0]), float(x[1])
        if not np.isfinite(ep) or not np.isfinite(xp) or ep <= 0:
            skipped += 1
            continue
        trades.append({
            "entry_ts": entry_d.isoformat(),
            "exit_ts": exit_d.isoformat(),
            "net_ret": side * (xp - ep) / ep - FEE_RT,
            "side": "long" if side > 0 else "short",
            "z": float(z),
        })
    return trades, skipped


def spec_for(sym: str) -> dict:
    return {
        "name": f"{sym}_stablecoin_supply_flow_paper_seed",
        "symbol": sym,
        "mode": "paper",
        "initial_capital": 1000000,
        "refit_interval_days": 30,
        "fee_rate": 0.0004,
        "notes": NOTES,
        "pipeline_spec": {
            "sources": [{"type": "bn_stablecoin_supply_flow",
                         "kwargs": {"z_thresh": Z_THRESH}}],
            "composer": {"type": "passthrough",
                         "kwargs": {"feature_col": "bnssf_signal", "scale": 1.0}},
            "policy": {"type": "long_short_threshold",
                       "kwargs": {"entry_threshold": 0.5,
                                  "sl_pct": 0.99,     # 실질 없음
                                  "tp_pct": 0.99,     # 실질 없음
                                  "max_hold_bars": HOLD}},
            "config": {"eval_freq_minutes": CYCLE_MINUTES, "forward_bars": HOLD},
        },
    }


def main() -> int:
    sig = build_signal()
    log.info(f"신호 {len(sig)}일 {sig['date'].min()} ~ {sig['date'].max()} | "
             f"트리거 {int((sig['z'].abs() >= Z_THRESH).sum())}건")
    SPEC_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    lines = ["#!/usr/bin/env bash",
             "# paradigm 251 — 3군 게이트 판정 + 2군 승격 큐 등록 (코드로 강제)",
             "# 생성: p251_emit_specs_and_trades.py",
             "set -euo pipefail", "cd \"$(dirname \"$0\")/../../..\"", ""]
    try:
        for sym in SYMBOLS:
            px = daily_ohlcv(db, sym)          # 최신성 검사 내장
            tr, skipped = backtest(px, sig, lag=1)
            trd, _ = backtest(px, sig, lag=2)
            if not tr:
                log.warning(f"{sym}: 거래 0건 — 건너뛴다")
                continue
            nets = np.array([t["net_ret"] for t in tr])
            delayed_edge = float(np.mean([t["net_ret"] for t in trd])) if trd else 0.0

            tp = OUT / f"gate_trades_{sym}_h{HOLD}d.json"
            tp.write_text(json.dumps(tr, indent=1))
            sp = SPEC_DIR / f"{sym}_stablecoin_supply_flow.json"
            sp.write_text(json.dumps(spec_for(sym), indent=2, ensure_ascii=False))

            log.info(f"  {sym:9s} n={len(tr):3d} 엣지 {nets.mean()*100:+.4f}% "
                     f"지연후 {delayed_edge*100:+.4f}% 버려진트리거 {skipped} "
                     f"가격종료 {px.index.max().date()}")

            lines += [
                f"echo '=== {sym} ==='",
                "python3 scripts/research/tier3_gate.py \\",
                f"  --trades runs/research_track/paradigm_251_stablecoin_supply_flow/"
                f"gate_trades_{sym}_h{HOLD}d.json \\",
                f"  --label 'p251 stablecoin_supply_flow {sym} h{HOLD}d' \\",
                f"  --lookahead-clean true --edge-after-1bar {delayed_edge:.8f} \\",
                f"  --friction {ROUNDTRIP_FRICTION} --hold-min {HOLD*1440} "
                f"--cycle-min {CYCLE_MINUTES} \\",
                f"  --out runs/research_track/paradigm_251_stablecoin_supply_flow/"
                f"tier3_gate__{sym}.json \\",
                f"  --enqueue --name {sym}_stablecoin_supply_flow_paper_seed \\",
                f"  --spec configs/paper_sessions/{sym}_stablecoin_supply_flow.json \\",
                f"  --paradigm alt_stablecoin_supply_net_flow_7d_z_bilateral_alt_1d_3d "
                f"--symbol {sym}",
                "",
            ]
    finally:
        db.close()

    sh = OUT / "enqueue_p251.sh"
    sh.write_text("\n".join(lines) + "\n")
    sh.chmod(0o755)
    log.info(f"등록 스크립트 → {sh}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
