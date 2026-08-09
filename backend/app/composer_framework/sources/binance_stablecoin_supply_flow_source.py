"""BinanceStablecoinSupplyFlowSource — paradigm 251 (3군 게이트 PASS 2026-08-09) live signal.

Hypothesis
----------
USDT + USDC 합산 발행량의 7일 순증감을 60일 롤링 z-score 로 정규화한 값이
크립토 유입 자본의 대리 지표다.
  z >= +1.0  → 신규 자본 유입     → alt perp LONG
  z <= -1.0  → 상환·자본 이탈     → alt perp SHORT
진입은 신호일 다음날(T+1) 시가, 보유 3일, 수수료 왕복 8bp.

Substrate: DefiLlama stablecoins API (무료·공개). USDT 2017-11-29~,
USDC 2018-09-11~ 전체 이력. CoinGecko 무료 티어는 365일 캡이 있어 쓰지 않는다 —
그 캡 때문에 이 패러다임이 처음에 299일로만 판정됐다.

증거 (2026-08-09, DB 214종목 · 신호 880일 유효구간)
--------------------------------------------------
유니버스 횡단면 — 신호가 **단일 시계열**이라 종목별 t 를 모으면 다중검정이므로
이벤트별 동일가중 포트폴리오로 검정했다 (유동성 필터: 일 거래대금 중간값 $5M):
  h3d  이벤트 379  거래당 +1.2277%  t 2.645  이벤트승률 54.4%   → 게이트 PASS
  h2d  이벤트 380  거래당 +0.8762%  t 2.228   → G2 실행주기 2.0x < 3.0x 차단
  h1d  이벤트 380  거래당 +0.4928%  t 1.665   → G2 실행주기 1.0x < 3.0x 차단
  유동 125종목 중 62.4% 가 양수 엣지 (h3d)

  창 밖 검증 — CoinGecko 창(2025-08-09~) 이전 구간만:
    h3d 이벤트 226  거래당 +1.2249%  t 1.979
    전체 구간 +1.2277% 와 사실상 동일 → 엣지 크기가 era 를 넘어 재현됨

종목별 h3d (880일, DefiLlama):
  BNBUSDT  n=379  +1.492%  t 4.935   ← 창 밖 구간에서도 독립 PASS
  XRPUSDT  n=379  +2.323%  t 4.108
  AVAXUSDT n=375  +1.424%  t 3.029
  LINKUSDT n=375  +1.111%  t 2.463
  DOGEUSDT n=375  +1.115%  t 1.749
  (SOLUSDT 는 t 0.976 로 탈락 — 6종목 중 5종목 통과)
  BNBUSDT 는 206종목 중 64 백분위 — 최댓값 뽑기가 아니라 유니버스 전반이 양수다.

G2: lookahead clean (일봉 신호 + T+1 시가 진입), 마찰여유 11.6x,
    실행주기 여유 3.0x (보유 3일 / 일 1회 사이클).

한계 (2군 forward 가 답할 몫)
  어느 창을 잡아도 그 창의 후반 1/3 이 약한 경향이 있다. 엣지가 고르게 깔린
  게 아니라 대규모 유입 레짐에 버스트로 몰려 있을 가능성이 있고, in-sample
  로는 더 가릴 수 없다.

Architecture
------------
일봉 신호를 종목별 paper 세션의 eval 인덱스에 매핑한다. eval 바 시각 t 에는
**t 의 전날(D) 까지의 공급 데이터로 계산한 z** 만 쓴다 — DefiLlama 의 날짜 D
값은 D 일 종료 시점 잔액이므로, D+1 진입은 lookahead 가 없다.

데이터 결손 시 **조용한 0 신호를 내지 않는다** — InsufficientSourceDataError 를
던진다. 0 은 "데이터는 충분한데 트리거가 없었다" 에만 쓴다.

Pair with:
  composer: passthrough (feature_col=bnssf_signal, scale=1.0)
  policy:   long_short_threshold (entry_threshold=0.5, sl_pct=0.99 (실질 없음),
            tp_pct=0.99 (실질 없음), max_hold_bars=3)
  config:   eval_freq_minutes=1440, forward_bars=3

Output (prefix `bnssf_`):
  bnssf_signal — {-1.0, 0.0, +1.0}
  bnssf_z      — 해당 바에 적용된 z (debug)
  bnssf_net7d  — 7일 순증감 USD (debug)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import (
    InsufficientSourceDataError,
    SignalSource,
    SourceContext,
)

log = logging.getLogger("bn_stablecoin_supply_flow")

DL_URL = "https://stablecoins.llama.fi/stablecoincharts/all"
DL_IDS = {"usdt": 1, "usdc": 2}
_BACKEND = Path(__file__).resolve().parents[3]
DEFAULT_CACHE = _BACKEND / "runs" / "substrate" / "defillama_stablecoin_supply.json"


class BinanceStablecoinSupplyFlowSource(SignalSource):
    name = "bn_stablecoin_supply_flow"
    feature_prefix = "bnssf_"
    requires = ("ohlcv_eval",)

    # 파라다임 설정 (3군 게이트 PASS 시점 2026-08-09 에 고정)
    NET_DAYS = 7
    ROLL_WIN = 60
    Z_THRESH = 1.0
    ENTRY_LAG_DAYS = 1          # 신호일 D → D+1 진입 (lookahead 방지)

    # 공급 데이터가 이보다 낡으면 신호를 만들지 않고 예외를 던진다.
    MAX_SUPPLY_STALENESS_DAYS = 3
    # z 계산에 필요한 최소 일수 (7일 차분 + 60일 롤링)
    MIN_SUPPLY_DAYS = NET_DAYS + ROLL_WIN + 5
    # eval 창 안에 신호가 실제로 존재할 수 있어야 한다.
    MIN_EVAL_BARS = 30

    def __init__(
        self,
        cache_path: Optional[str] = None,
        z_thresh: float = 1.0,
        refresh_hours: float = 12.0,
        allow_network: bool = True,
    ) -> None:
        self.cache_path = Path(cache_path) if cache_path else DEFAULT_CACHE
        self.z_thresh = float(z_thresh)
        self.refresh_hours = float(refresh_hours)
        self.allow_network = bool(allow_network)

    # ── substrate ────────────────────────────────────────────────────
    def _cache_age_hours(self) -> float:
        if not self.cache_path.exists():
            return float("inf")
        age = datetime.now(timezone.utc).timestamp() - os.path.getmtime(self.cache_path)
        return age / 3600.0

    def _fetch(self) -> dict:
        import requests  # 지연 임포트 — 캐시가 신선하면 네트워크를 건드리지 않는다

        out = {}
        for name, sid in DL_IDS.items():
            r = requests.get(DL_URL, params={"stablecoin": sid}, timeout=60,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            series = []
            for row in r.json():
                val = (row.get("totalCirculating") or {}).get("peggedUSD")
                if val is None:
                    continue
                d = datetime.fromtimestamp(int(row["date"]), tz=timezone.utc).date()
                series.append({"date": d.isoformat(), "supply": float(val)})
            if not series:
                raise InsufficientSourceDataError(
                    f"DefiLlama {name.upper()} 응답이 비어 있다")
            out[name] = series
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(self.cache_path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(out, f)
        os.replace(tmp, self.cache_path)
        log.info("DefiLlama 공급 이력 갱신 → %s", self.cache_path)
        return out

    def _load_supply(self) -> dict:
        stale = self._cache_age_hours() > self.refresh_hours
        if stale and self.allow_network:
            try:
                return self._fetch()
            except InsufficientSourceDataError:
                raise
            except Exception as e:  # 네트워크 실패 → 캐시로 폴백하되 최신성은 아래서 검사
                log.warning("DefiLlama 갱신 실패 (%s) — 캐시로 폴백한다", e)
        if not self.cache_path.exists():
            raise InsufficientSourceDataError(
                f"스테이블코인 공급 substrate 가 없다: {self.cache_path} "
                f"(네트워크 허용={self.allow_network})")
        return json.loads(self.cache_path.read_text())

    def _daily_signal(self) -> pd.DataFrame:
        """반환: index=날짜(UTC date), 컬럼 z / net_7d. 신호일 기준이다."""
        raw = self._load_supply()
        frames = {}
        for k in ("usdt", "usdc"):
            rows = raw.get(k) or []
            if not rows:
                raise InsufficientSourceDataError(f"공급 시계열 {k} 가 비어 있다")
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"]).dt.date
            frames[k] = df.groupby("date", as_index=False)["supply"].last()

        m = frames["usdt"].merge(frames["usdc"], on="date", suffixes=("_usdt", "_usdc"))
        m = m.sort_values("date").reset_index(drop=True)
        if len(m) < self.MIN_SUPPLY_DAYS:
            raise InsufficientSourceDataError(
                f"공급 이력 {len(m)}일 < 최소 {self.MIN_SUPPLY_DAYS}일")

        latest = m["date"].iloc[-1]
        stale_days = (datetime.now(timezone.utc).date() - latest).days
        if stale_days > self.MAX_SUPPLY_STALENESS_DAYS:
            raise InsufficientSourceDataError(
                f"공급 substrate 가 {stale_days}일 낡았다 (최신 {latest}, "
                f"허용 {self.MAX_SUPPLY_STALENESS_DAYS}일) — 0 신호로 위장하지 않는다")

        m["combined"] = m["supply_usdt"] + m["supply_usdc"]
        m["net_7d"] = m["combined"].diff(self.NET_DAYS)
        roll = m["net_7d"].rolling(self.ROLL_WIN)
        m["z"] = (m["net_7d"] - roll.mean()) / roll.std()
        out = m[["date", "z", "net_7d"]].dropna().reset_index(drop=True)
        if out.empty:
            raise InsufficientSourceDataError("z 계산 후 유효 신호일이 없다")
        return out.set_index("date")

    # ── SignalSource ─────────────────────────────────────────────────
    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        idx = ctx.ohlcv_eval.index
        if len(idx) < self.MIN_EVAL_BARS:
            raise InsufficientSourceDataError(
                f"eval 창 {len(idx)}바 < 최소 {self.MIN_EVAL_BARS}바 — "
                f"신호가 구조적으로 억제된다")

        sig = self._daily_signal()

        # eval 바 시각 t 에는 t 의 ENTRY_LAG_DAYS 일 **전** 신호를 쓴다.
        # DefiLlama 날짜 D 값은 D 일 종료 잔액 → D+1 진입은 lookahead 가 없다.
        eval_dates = pd.Index(
            [(ts - timedelta(days=self.ENTRY_LAG_DAYS)).date() for ts in idx],
            name="signal_date")
        z = pd.Series(sig["z"].reindex(eval_dates).to_numpy(), index=idx, dtype=float)
        net7 = pd.Series(sig["net_7d"].reindex(eval_dates).to_numpy(), index=idx, dtype=float)

        signal = np.where(z >= self.z_thresh, 1.0,
                          np.where(z <= -self.z_thresh, -1.0, 0.0))
        signal = pd.Series(signal, index=idx, dtype=float)
        signal[z.isna()] = 0.0   # 해당 신호일이 없으면 무포지션

        n_fire = int((signal != 0).sum())
        n_cov = int(z.notna().sum())
        if n_cov == 0:
            raise InsufficientSourceDataError(
                "eval 창과 공급 신호 구간이 전혀 겹치지 않는다 — "
                "조용한 0 신호 대신 실패로 보고한다")
        log.info("%s: eval %d바 중 신호 커버 %d바, 트리거 %d바",
                 ctx.symbol, len(idx), n_cov, n_fire)

        return self._prefixed(pd.DataFrame(
            {"signal": signal, "z": z.fillna(0.0), "net7d": net7.fillna(0.0)},
            index=idx))
