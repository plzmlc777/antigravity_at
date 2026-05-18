"""DART OpenAPI HTTP client (Track 3 Sub-task 3B).

Scope: read-only list/disclosure queries against opendart.fss.or.kr.
- Auth: crtfc_key from env OPENDART_API_KEY (40 chars).
- Daily quota: ~20K calls. Status code 020 = quota exceeded → caller retry next day.
- All requests pass through `_get_json` (single chokepoint for header/timeout/retry).

Per CLAUDE.md: this is service code (used by research scripts), keep narrow surface area.
Per memory [[feedback_no_freemium_trial_dart_exception]]: DART is the
permitted government-API exception to the no-freemium rule.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
import urllib.error
from typing import Iterator, Optional

log = logging.getLogger(__name__)

DART_BASE = "https://opendart.fss.or.kr/api"
USER_AGENT = "antigravity/dart_adapter (research)"
DEFAULT_TIMEOUT = 20
DEFAULT_PAGE_COUNT = 100  # API max
DEFAULT_RETRIES = 3

# DART status codes (https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019018)
STATUS_OK = "000"
STATUS_NO_DATA = "013"
STATUS_QUOTA_EXCEEDED = "020"
STATUS_WRONG_KEY = "010"
STATUS_REQUEST_LIMIT = "021"


class DartError(RuntimeError):
    def __init__(self, status: str, message: str, url: str):
        super().__init__(f"DART {status}: {message} ({url})")
        self.status = status
        self.message = message
        self.url = url


def _get_key() -> str:
    key = os.getenv("OPENDART_API_KEY") or os.getenv("DART_CRTFC_KEY")
    if not key:
        raise RuntimeError(
            "OPENDART_API_KEY (or DART_CRTFC_KEY) not set. "
            "Register a free key at https://opendart.fss.or.kr/mng/userApiKeyListView.do"
        )
    if len(key) != 40:
        log.warning("DART crtfc_key length=%d, expected 40", len(key))
    return key


def _get_json(endpoint: str, params: dict, *, timeout: int = DEFAULT_TIMEOUT,
              retries: int = DEFAULT_RETRIES) -> dict:
    """GET endpoint + parse JSON. Retries on transient network errors.
    Raises DartError on application-level failure (non-000 status that is not 013)."""
    full = dict(params)
    full["crtfc_key"] = _get_key()
    url = f"{DART_BASE}/{endpoint}?" + urllib.parse.urlencode(full)
    safe_url = url.replace(full["crtfc_key"], "***")

    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
            status = data.get("status")
            if status in (STATUS_OK, STATUS_NO_DATA):
                return data
            if status in (STATUS_QUOTA_EXCEEDED, STATUS_REQUEST_LIMIT):
                raise DartError(status, data.get("message", ""), safe_url)
            if status == STATUS_WRONG_KEY:
                raise DartError(status, "wrong crtfc_key", safe_url)
            raise DartError(status or "?", data.get("message", ""), safe_url)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_exc = e
            if attempt < retries - 1:
                sleep_s = 1.5 ** attempt
                log.warning("DART transient error attempt=%d (%s), sleep %.1fs",
                            attempt + 1, e, sleep_s)
                time.sleep(sleep_s)
                continue
            raise DartError("network", str(e), safe_url) from e
    raise DartError("retry_exhausted", str(last_exc), safe_url)


def list_disclosures(
    *,
    bgn_de: str,
    end_de: str,
    corp_cls: Optional[str] = None,
    corp_code: Optional[str] = None,
    pblntf_ty: Optional[str] = None,
    pblntf_detail_ty: Optional[str] = None,
    last_reprt_at: Optional[str] = None,
    sort: str = "date",
    sort_mth: str = "asc",
    page_count: int = DEFAULT_PAGE_COUNT,
    max_pages: Optional[int] = None,
) -> Iterator[dict]:
    """Yield individual disclosure records from /list.json across all pages.

    Date params (bgn_de/end_de): YYYYMMDD.
    corp_cls: Y=KOSPI, K=KOSDAQ, N=KONEX, E=other.
    pblntf_ty: A=정기 / B=주요사항 / C=발행 / D=지분 / E=기타 / F=외부감사 / ...
    pblntf_detail_ty: optional 4-char sub-code.

    Without corp_code DART limits each call to ≤ 3-month range. Caller MUST
    chunk by month if querying corp_cls universe across full 2.4yr lookback.
    """
    page = 1
    seen = 0
    while True:
        params = {
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_no": str(page),
            "page_count": str(page_count),
            "sort": sort,
            "sort_mth": sort_mth,
        }
        for k, v in (
            ("corp_cls", corp_cls),
            ("corp_code", corp_code),
            ("pblntf_ty", pblntf_ty),
            ("pblntf_detail_ty", pblntf_detail_ty),
            ("last_reprt_at", last_reprt_at),
        ):
            if v is not None:
                params[k] = v

        data = _get_json("list.json", params)
        if data.get("status") == STATUS_NO_DATA:
            return
        rows = data.get("list", []) or []
        for r in rows:
            yield r
            seen += 1
        total_page = int(data.get("total_page", 1) or 1)
        if page >= total_page:
            return
        if max_pages and page >= max_pages:
            log.warning("list_disclosures max_pages=%d reached, truncating", max_pages)
            return
        page += 1


def fnltt_singl_acnt(
    corp_code: str,
    bsns_year: str,
    reprt_code: str,
    *,
    fs_div: Optional[str] = None,
) -> dict:
    """Single-company XBRL income/balance accounts via fnlttSinglAcnt.
    reprt_code: 11013(Q1) / 11012(semi=Q2) / 11014(Q3) / 11011(annual=Q4).
    Returns raw API dict (status + list). Caller is responsible for filtering
    sj_div=IS + account_nm in {매출액, 영업이익, 당기순이익(손실)}.
    fs_div optional (CFS/OFS) for SinglAcntAll endpoint."""
    params = {
        "corp_code": corp_code,
        "bsns_year": str(bsns_year),
        "reprt_code": reprt_code,
    }
    endpoint = "fnlttSinglAcnt.json"
    if fs_div:
        params["fs_div"] = fs_div
        endpoint = "fnlttSinglAcntAll.json"
    return _get_json(endpoint, params)


def iter_disclosures_chunked(
    *,
    bgn_de: str,
    end_de: str,
    chunk_days: int = 30,
    **kwargs,
) -> Iterator[dict]:
    """Wrapper that chunks bgn_de..end_de into ≤ chunk_days windows.
    Required when corp_code is None (API enforces ≤3-month range)."""
    from datetime import datetime, timedelta

    start = datetime.strptime(bgn_de, "%Y%m%d").date()
    end = datetime.strptime(end_de, "%Y%m%d").date()
    cur = start
    while cur <= end:
        nxt = min(cur + timedelta(days=chunk_days - 1), end)
        yield from list_disclosures(
            bgn_de=cur.strftime("%Y%m%d"),
            end_de=nxt.strftime("%Y%m%d"),
            **kwargs,
        )
        cur = nxt + timedelta(days=1)
