"""연구 스크립트용 바이낸스 REST — **가중치 계량 + 디스크 캐시**.

## 왜 만드나 (2026-09-09 IP 차단)

가중치 경보는 `app/adapters/binance_base.py` 에 이미 있다. 그런데 내가 쓴
분석 스크립트들은 전부 `urllib.request` 를 **직접** 불렀다 — 어댑터를 안 거치니
경보도 절제도 없었다. 108종목 klines 를 몇 분에 몰아 던져 `-1003` 으로
민트 IP 가 차단됐고, **같은 IP 를 쓰는 실거래 드라이버까지 같이 멈췄다.**

세 번째다. 규율로 안 되니 도구가 강제한다.

## 규칙

1. 연구 스크립트는 REST 를 **직접 부르지 않는다.** 이 모듈만 쓴다.
2. **로컬 기질이 있으면 REST 를 쓰지 마라** — `runs/ticks`(틱) ·
   `runs/bars1m` · `runs/bars5m_ext` · `ohlcv_daily`. REST 는 그게 없을 때만.
3. 같은 구간을 두 번 받지 않는다. 캐시가 디스크에 남는다.

## 가중치 (klines, 2026-09 기준)

    limit 1~100 → 1 · 101~500 → 2 · 501~1000 → 5 · 1001~1500 → 10
    IP 한도 2400/분. 이 모듈은 `SOFT_CAP` 을 넘으면 분 경계까지 잔다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger("bnrest")

FAPI = "https://fapi.binance.com"
ROOT = Path(__file__).resolve().parents[2]
CACHE = Path(os.environ.get("BN_REST_CACHE", ROOT / "runs" / "_rest_cache"))
# ⚠ 한도는 2400 이다. 절반에서 멈춘다 — 실거래 드라이버가 **같은 IP** 를 쓴다.
#   내 연구가 남의 주문을 막으면 안 된다.
SOFT_CAP = int(os.environ.get("BN_REST_SOFT_CAP", "1000"))
MIN_GAP_S = float(os.environ.get("BN_REST_MIN_GAP", "0.06"))

_used = 0            # 이번 분에 관측된 IP 가중치
_last = 0.0


def _weight_of(limit: int) -> int:
    if limit <= 100:
        return 1
    if limit <= 500:
        return 2
    if limit <= 1000:
        return 5
    return 10


def _throttle(cost: int) -> None:
    """보내기 **전에** 잔다. 차단당한 뒤 자는 것은 늦다."""
    global _last
    gap = time.time() - _last
    if gap < MIN_GAP_S:
        time.sleep(MIN_GAP_S - gap)
    if _used + cost >= SOFT_CAP:
        wait = 61 - (time.time() % 60)
        log.warning("가중치 %d + %d ≥ %d — 분 경계까지 %.0f초 쉰다",
                    _used, cost, SOFT_CAP, wait)
        time.sleep(wait)


def get(path: str, params: dict, *, limit_for_weight: int = 1,
        cache: bool = True, ttl_s: float = 0.0):
    """서명 없는 GET. 캐시에 있으면 **네트워크를 안 탄다.**

    ttl_s=0 이면 영구 캐시 — 과거 구간(klines)은 안 바뀌므로 기본이 맞다.
    지금 시각이 걸린 구간을 받을 때만 ttl 을 줘라."""
    global _used, _last
    qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    key = hashlib.sha1(f"{path}?{qs}".encode()).hexdigest()
    f = CACHE / path.strip("/").replace("/", "_") / f"{key}.json"
    if cache and f.exists():
        if ttl_s <= 0 or time.time() - f.stat().st_mtime < ttl_s:
            return json.loads(f.read_text())
    cost = _weight_of(limit_for_weight)
    _throttle(cost)
    url = f"{FAPI}{path}?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            body = json.load(r)
            h = r.headers
    except urllib.error.HTTPError as e:
        if e.code == 418 or e.code == 429:
            # ⚠ 차단 중에는 **아무것도 보내지 않는다.** 재시도가 차단을 늘린다.
            raise SystemExit(f"바이낸스 차단({e.code}) — 재시도 금지. {e.read()[:200]}")
        raise
    _last = time.time()
    for k in ("X-MBX-USED-WEIGHT-1M", "x-mbx-used-weight-1m"):
        if k in h:
            try:
                _used = int(h[k])
            except (TypeError, ValueError):
                pass
            break
    if cache:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(body))
    return body


def klines(symbol: str, interval: str, start_ms: int, end_ms: int,
           limit: int = 1000) -> list:
    return get("/fapi/v1/klines",
               {"symbol": symbol, "interval": interval,
                "startTime": int(start_ms), "endTime": int(end_ms),
                "limit": int(limit)},
               limit_for_weight=limit)


def used_weight() -> int:
    return _used
