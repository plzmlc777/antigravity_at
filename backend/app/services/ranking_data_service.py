"""
Ranking Data Service - Cached ranking data from Kiwoom ranking APIs

Provides a singleton service that fetches and caches ranking data from
all available Kiwoom ranking APIs. Cache TTL is 5 minutes (ranking data
is more volatile than stock lists).

Supported APIs (26 configs, 12 unique API IDs):
  ka10020 (호가잔량상위), ka10021 (호가잔량급증), ka10022 (잔량율급증),
  ka10023 (거래량급증), ka10027 (등락률상위), ka10029 (예상체결등락률),
  ka10030 (당일거래량상위), ka10031 (전일거래량상위), ka10032 (거래대금상위),
  ka10033 (신용비율상위), ka10034 (외인순매매), ka10035 (외인연속순매매),
  ka10036 (외인한도소진율), ka10037 (외국계창구매매), ka10062 (동일순매매),
  ka10065 (장중투자자별매매), ka10098 (시간외단일가등락률), ka90009 (외국인기관매매)

Usage:
    service = RankingDataService.get_instance()
    rankings = await service.get_rankings(base_url, token)
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from ..core.http_client import HttpClientManager

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300  # 5 minutes
RANKING_API_URL = "/api/dostk/rkinfo"

# Each ranking config defines one API call.
# Special flags:
#   "market_split": True  - API doesn't support mrkt_tp "000" (all markets),
#                           so we call twice (KOSPI "001" + KOSDAQ "101") and merge.
#   "dynamic_dates": True - Payload needs strt_dt/end_dt computed at fetch time.
#   "custom_transform": "ka90009" - Response has parallel columns requiring transform.
RANKING_CONFIGS = {
    # ================================================================
    # 당일거래량상위 (ka10030)
    # ================================================================
    "volume_top": {
        "api_id": "ka10030",
        "description": "당일거래량상위",
        "payload": {
            "mrkt_tp": "000", "sort_tp": "1", "mang_stk_incls": "1",
            "crd_tp": "0", "trde_qty_tp": "0", "pric_tp": "0",
            "trde_prica_tp": "0", "mrkt_open_tp": "0", "stex_tp": "3",
        },
        "list_key": "tdy_trde_qty_upper",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre",
            "flu_rt", "trde_qty", "pred_rt", "trde_tern_rt", "trde_amt",
        ],
    },
    # ================================================================
    # 등락률상위 - 상승 (ka10027)
    # ================================================================
    "gainers": {
        "api_id": "ka10027",
        "description": "등락률상위(상승)",
        "payload": {
            "mrkt_tp": "000", "sort_tp": "1", "trde_qty_cnd": "0000",
            "stk_cnd": "1", "crd_cnd": "0", "updown_incls": "0",
            "pric_cnd": "0", "trde_prica_cnd": "0", "stex_tp": "3",
        },
        "list_key": "pred_pre_flu_rt_upper",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre",
            "flu_rt", "now_trde_qty", "cntr_str",
        ],
    },
    # ================================================================
    # 등락률상위 - 하락 (ka10027)
    # ================================================================
    "losers": {
        "api_id": "ka10027",
        "description": "등락률상위(하락)",
        "payload": {
            "mrkt_tp": "000", "sort_tp": "3", "trde_qty_cnd": "0000",
            "stk_cnd": "1", "crd_cnd": "0", "updown_incls": "0",
            "pric_cnd": "0", "trde_prica_cnd": "0", "stex_tp": "3",
        },
        "list_key": "pred_pre_flu_rt_upper",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre",
            "flu_rt", "now_trde_qty", "cntr_str",
        ],
    },
    # ================================================================
    # 거래대금상위 (ka10032)
    # ================================================================
    "value_top": {
        "api_id": "ka10032",
        "description": "거래대금상위",
        "payload": {
            "mrkt_tp": "000", "mang_stk_incls": "0", "stex_tp": "3",
        },
        "list_key": "trde_prica_upper",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre",
            "flu_rt", "now_rank", "pred_rank", "now_trde_qty", "trde_prica",
        ],
    },
    # ================================================================
    # 외인순매수상위 (ka10034)
    # ================================================================
    "foreign_buy": {
        "api_id": "ka10034",
        "description": "외인순매수상위",
        "payload": {
            "mrkt_tp": "000", "trde_tp": "2", "dt": "0", "stex_tp": "3",
        },
        "list_key": "for_dt_trde_upper",
        "fields": [
            "rank", "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre",
            "trde_qty", "netprps_qty",
        ],
    },
    # ================================================================
    # 외인순매도상위 (ka10034)
    # ================================================================
    "foreign_sell": {
        "api_id": "ka10034",
        "description": "외인순매도상위",
        "payload": {
            "mrkt_tp": "000", "trde_tp": "1", "dt": "0", "stex_tp": "3",
        },
        "list_key": "for_dt_trde_upper",
        "fields": [
            "rank", "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre",
            "trde_qty", "netprps_qty",
        ],
    },
    # ================================================================
    # 거래량급증 (ka10023)
    # ================================================================
    "volume_spike": {
        "api_id": "ka10023",
        "description": "거래량급증",
        "payload": {
            "mrkt_tp": "000", "sort_tp": "1", "tm_tp": "2",
            "trde_qty_tp": "5", "tm": "", "stk_cnd": "0",
            "pric_tp": "0", "stex_tp": "3",
        },
        "list_key": "trde_qty_sdnin",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre",
            "flu_rt", "prev_trde_qty", "now_trde_qty", "sdnin_qty", "sdnin_rt",
        ],
    },
    # ================================================================
    # 신용비율상위 (ka10033)
    # ================================================================
    "credit_top": {
        "api_id": "ka10033",
        "description": "신용비율상위",
        "payload": {
            "mrkt_tp": "000", "trde_qty_tp": "0", "stk_cnd": "1",
            "updown_incls": "0", "crd_cnd": "0", "stex_tp": "3",
        },
        "list_key": "crd_rt_upper",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre",
            "flu_rt", "crd_rt", "now_trde_qty",
        ],
    },

    # ================================================================
    # 호가잔량상위 (ka10020) - market_split (KOSPI+KOSDAQ)
    # ================================================================
    "bid_balance": {
        "api_id": "ka10020",
        "description": "호가잔량상위",
        "market_split": True,
        "payload": {
            "sort_tp": "1", "trde_qty_tp": "0000",
            "stk_cnd": "0", "crd_cnd": "0", "stex_tp": "3",
        },
        "list_key": "bid_req_upper",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre",
            "trde_qty", "tot_sel_req", "tot_buy_req", "netprps_req", "buy_rt",
        ],
    },
    # ================================================================
    # 호가잔량급증 (ka10021) - market_split (KOSPI+KOSDAQ)
    # ================================================================
    "bid_spike": {
        "api_id": "ka10021",
        "description": "호가잔량급증",
        "market_split": True,
        "payload": {
            "trde_tp": "1", "sort_tp": "1", "tm_tp": "30",
            "trde_qty_tp": "1", "stk_cnd": "0", "stex_tp": "3",
        },
        "list_key": "bid_req_sdnin",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre",
            "sdnin_qty", "sdnin_rt", "tot_buy_qty",
        ],
    },
    # ================================================================
    # 잔량율급증 (ka10022) - market_split (KOSPI+KOSDAQ)
    # ================================================================
    "balance_rate_spike": {
        "api_id": "ka10022",
        "description": "잔량율급증",
        "market_split": True,
        "payload": {
            "rt_tp": "1", "tm_tp": "1", "trde_qty_tp": "5",
            "stk_cnd": "0", "stex_tp": "3",
        },
        "list_key": "req_rt_sdnin",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre",
            "now_rt", "sdnin_rt", "tot_sel_req", "tot_buy_req",
        ],
    },
    # ================================================================
    # 예상체결등락률상위 (ka10029)
    # ================================================================
    "expected_price": {
        "api_id": "ka10029",
        "description": "예상체결등락률상위",
        "payload": {
            "mrkt_tp": "000", "sort_tp": "1", "trde_qty_tp": "0",
            "stk_cnd": "0", "crd_cnd": "0", "pric_cnd": "0", "stex_tp": "3",
        },
        "list_key": "exp_cntr_flu_rt_upper",
        "fields": [
            "stk_cd", "stk_nm", "exp_cntr_pric", "base_pric",
            "pred_pre_sig", "pred_pre", "flu_rt",
            "exp_cntr_qty", "sel_req", "buy_req",
        ],
    },
    # ================================================================
    # 전일거래량상위 (ka10031)
    # ================================================================
    "prev_volume_top": {
        "api_id": "ka10031",
        "description": "전일거래량상위",
        "payload": {
            "mrkt_tp": "000", "qry_tp": "1",
            "rank_strt": "0", "rank_end": "100", "stex_tp": "3",
        },
        "list_key": "pred_trde_qty_upper",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre", "trde_qty",
        ],
    },
    # ================================================================
    # 외인연속순매수 (ka10035)
    # ================================================================
    "foreign_consec_buy": {
        "api_id": "ka10035",
        "description": "외인연속순매수",
        "payload": {
            "mrkt_tp": "000", "trde_tp": "2", "base_dt_tp": "1", "stex_tp": "3",
        },
        "list_key": "for_cont_nettrde_upper",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre",
            "dm1", "dm2", "dm3", "tot", "limit_exh_rt",
        ],
    },
    # ================================================================
    # 외인연속순매도 (ka10035)
    # ================================================================
    "foreign_consec_sell": {
        "api_id": "ka10035",
        "description": "외인연속순매도",
        "payload": {
            "mrkt_tp": "000", "trde_tp": "1", "base_dt_tp": "1", "stex_tp": "3",
        },
        "list_key": "for_cont_nettrde_upper",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre",
            "dm1", "dm2", "dm3", "tot", "limit_exh_rt",
        ],
    },
    # ================================================================
    # 외인한도소진율증가 (ka10036)
    # ================================================================
    "foreign_limit_exhaust": {
        "api_id": "ka10036",
        "description": "외인한도소진율증가",
        "payload": {
            "mrkt_tp": "000", "dt": "1", "stex_tp": "3",
        },
        "list_key": "for_limit_exh_rt_incrs_upper",
        "fields": [
            "rank", "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre",
            "trde_qty", "poss_stkcnt", "base_limit_exh_rt", "limit_exh_rt", "exh_rt_incrs",
        ],
    },
    # ================================================================
    # 외국계창구순매수상위 (ka10037)
    # ================================================================
    "foreign_branch_buy": {
        "api_id": "ka10037",
        "description": "외국계창구순매수상위",
        "payload": {
            "mrkt_tp": "000", "dt": "0", "trde_tp": "1",
            "sort_tp": "2", "stex_tp": "3",
        },
        "list_key": "frgn_wicket_trde_upper",
        "fields": [
            "rank", "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre", "flu_rt",
            "sel_trde_qty", "buy_trde_qty", "netprps_trde_qty", "trde_qty",
        ],
    },
    # ================================================================
    # 외국계창구순매도상위 (ka10037)
    # ================================================================
    "foreign_branch_sell": {
        "api_id": "ka10037",
        "description": "외국계창구순매도상위",
        "payload": {
            "mrkt_tp": "000", "dt": "0", "trde_tp": "2",
            "sort_tp": "2", "stex_tp": "3",
        },
        "list_key": "frgn_wicket_trde_upper",
        "fields": [
            "rank", "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre", "flu_rt",
            "sel_trde_qty", "buy_trde_qty", "netprps_trde_qty", "trde_qty",
        ],
    },
    # ================================================================
    # 동일순매수순위 (ka10062) - dynamic_dates
    # ================================================================
    "same_net_buy": {
        "api_id": "ka10062",
        "description": "동일순매수순위",
        "dynamic_dates": True,
        "payload": {
            "mrkt_tp": "000", "trde_tp": "1", "sort_cnd": "1",
            "unit_tp": "1", "stex_tp": "3",
        },
        "list_key": "eql_nettrde_rank",
        "fields": [
            "stk_cd", "rank", "stk_nm", "cur_prc", "pre_sig", "pred_pre", "flu_rt",
            "acc_trde_qty", "orgn_nettrde_qty", "for_nettrde_qty", "nettrde_qty",
        ],
    },
    # ================================================================
    # 동일순매도순위 (ka10062) - dynamic_dates
    # ================================================================
    "same_net_sell": {
        "api_id": "ka10062",
        "description": "동일순매도순위",
        "dynamic_dates": True,
        "payload": {
            "mrkt_tp": "000", "trde_tp": "2", "sort_cnd": "1",
            "unit_tp": "1", "stex_tp": "3",
        },
        "list_key": "eql_nettrde_rank",
        "fields": [
            "stk_cd", "rank", "stk_nm", "cur_prc", "pre_sig", "pred_pre", "flu_rt",
            "acc_trde_qty", "orgn_nettrde_qty", "for_nettrde_qty", "nettrde_qty",
        ],
    },
    # ================================================================
    # 장중외국인순매수 (ka10065)
    # ================================================================
    "intraday_foreign_buy": {
        "api_id": "ka10065",
        "description": "장중외국인순매수",
        "payload": {
            "trde_tp": "1", "mrkt_tp": "000",
            "orgn_tp": "9000", "stex_tp": "3",
        },
        "list_key": "tdy_invsr_orgn_trde_upper",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre", "flu_rt",
            "sel_trde_qty", "buy_trde_qty", "netprps_trde_qty", "trde_qty",
        ],
    },
    # ================================================================
    # 장중외국인순매도 (ka10065)
    # ================================================================
    "intraday_foreign_sell": {
        "api_id": "ka10065",
        "description": "장중외국인순매도",
        "payload": {
            "trde_tp": "2", "mrkt_tp": "000",
            "orgn_tp": "9000", "stex_tp": "3",
        },
        "list_key": "tdy_invsr_orgn_trde_upper",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre", "flu_rt",
            "sel_trde_qty", "buy_trde_qty", "netprps_trde_qty", "trde_qty",
        ],
    },
    # ================================================================
    # 장중기관순매수 (ka10065)
    # ================================================================
    "intraday_inst_buy": {
        "api_id": "ka10065",
        "description": "장중기관순매수",
        "payload": {
            "trde_tp": "1", "mrkt_tp": "000",
            "orgn_tp": "9999", "stex_tp": "3",
        },
        "list_key": "tdy_invsr_orgn_trde_upper",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre", "flu_rt",
            "sel_trde_qty", "buy_trde_qty", "netprps_trde_qty", "trde_qty",
        ],
    },
    # ================================================================
    # 장중기관순매도 (ka10065)
    # ================================================================
    "intraday_inst_sell": {
        "api_id": "ka10065",
        "description": "장중기관순매도",
        "payload": {
            "trde_tp": "2", "mrkt_tp": "000",
            "orgn_tp": "9999", "stex_tp": "3",
        },
        "list_key": "tdy_invsr_orgn_trde_upper",
        "fields": [
            "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre", "flu_rt",
            "sel_trde_qty", "buy_trde_qty", "netprps_trde_qty", "trde_qty",
        ],
    },
    # ================================================================
    # 시간외단일가등락률 (ka10098)
    # ================================================================
    "after_hours_change": {
        "api_id": "ka10098",
        "description": "시간외단일가등락률",
        "payload": {
            "mrkt_tp": "000", "sort_base": "1", "stk_cnd": "0",
            "trde_qty_cnd": "0", "crd_cnd": "0", "trde_prica": "0",
        },
        "list_key": "ovt_sigpric_flu_rt_rank",
        "fields": [
            "rank", "stk_cd", "stk_nm", "cur_prc", "pred_pre_sig", "pred_pre", "flu_rt",
            "acc_trde_qty", "acc_trde_prica", "tdy_close_pric", "tdy_close_pric_flu_rt",
        ],
    },
    # ================================================================
    # 외국인기관매매상위 (ka90009) - custom_transform
    # Each row contains parallel columns: foreign buy/sell + inst buy/sell.
    # Transform splits into flat list with 'category' field.
    # ================================================================
    "foreign_inst_combined": {
        "api_id": "ka90009",
        "description": "외국인기관매매상위",
        "custom_transform": "ka90009",
        "payload": {
            "mrkt_tp": "000", "amt_qty_tp": "1",
            "qry_dt_tp": "0", "stex_tp": "3",
        },
        "list_key": "frgnr_orgn_trde_upper",
        "fields": [],  # Custom transform handles field extraction
    },
}


class RankingDataService:
    _instance = None

    def __init__(self):
        self._cache: Optional[Dict] = None
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _is_cache_valid(self) -> bool:
        if not self._cache:
            return False
        elapsed = (datetime.now() - self._cache["fetched_at"]).total_seconds()
        return elapsed < CACHE_TTL_SECONDS

    async def get_rankings(self, base_url: str, token: str) -> Dict[str, List]:
        """Get all ranking data (cached for 5 minutes)."""
        if self._is_cache_valid():
            logger.debug("Ranking data cache hit")
            return self._cache["data"]

        async with self._lock:
            # Double-check after acquiring lock
            if self._is_cache_valid():
                return self._cache["data"]

            logger.info("Fetching ranking data from Kiwoom APIs...")
            rankings = await self._fetch_all_rankings(base_url, token)

            self._cache = {
                "data": rankings,
                "fetched_at": datetime.now(),
            }

            total = sum(len(v) for v in rankings.values())
            logger.info(
                f"Ranking data cached: {total} items across "
                f"{sum(1 for v in rankings.values() if v)} categories"
            )
            return rankings

    async def _fetch_all_rankings(self, base_url: str, token: str) -> Dict[str, List]:
        """Fetch all ranking APIs in parallel."""
        keys = list(RANKING_CONFIGS.keys())
        tasks = [
            self._fetch_single_ranking(base_url, token, RANKING_CONFIGS[key])
            for key in keys
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        rankings = {}
        for key, result in zip(keys, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to fetch ranking '{key}': {result}")
                rankings[key] = []
            else:
                rankings[key] = result
                logger.debug(f"  {key}: {len(result)} items")

        return rankings

    async def _fetch_single_ranking(
        self, base_url: str, token: str, config: dict
    ) -> List[Dict]:
        """Fetch one ranking API, handling special cases."""

        # market_split: call for both KOSPI and KOSDAQ, merge results
        if config.get("market_split"):
            results = []
            for mrkt in ("001", "101"):
                payload = {**config["payload"], "mrkt_tp": mrkt}
                items = await self._call_api(base_url, token, config, payload)
                results.extend(items)
            return results

        # Build payload (may need dynamic fields)
        payload = dict(config["payload"])

        # dynamic_dates: compute strt_dt/end_dt for ka10062
        if config.get("dynamic_dates"):
            today = datetime.now()
            payload["end_dt"] = today.strftime("%Y%m%d")
            payload["strt_dt"] = (today - timedelta(days=7)).strftime("%Y%m%d")

        raw_items = await self._call_api(base_url, token, config, payload)

        # custom_transform: ka90009 parallel-column response
        if config.get("custom_transform") == "ka90009":
            return self._transform_ka90009(raw_items)

        return raw_items

    async def _call_api(
        self, base_url: str, token: str, config: dict, payload: dict
    ) -> List[Dict]:
        """Execute a single API call and extract configured fields."""
        url = f"{base_url}{RANKING_API_URL}"
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {token}",
            "api-id": config["api_id"],
        }

        client = HttpClientManager.get_instance()
        resp = await client.post_with_rate_limit(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

        items = data.get(config["list_key"], [])
        fields = config["fields"]

        # If no fields configured, return raw items (for custom transform)
        if not fields:
            return items

        # Extract only configured fields to keep context compact
        slim_items = []
        for item in items:
            slim = {}
            for f in fields:
                val = item.get(f, "")
                if val:  # Skip empty values to save space
                    slim[f] = val
            if slim.get("stk_cd"):  # Must have stock code
                slim_items.append(slim)

        return slim_items

    @staticmethod
    def _transform_ka90009(raw_items: list) -> List[Dict]:
        """Transform ka90009 parallel-column response into flat stock list.

        Each row has 4 stocks in parallel columns:
          - for_netprps_*  (외국인 순매수)
          - for_netslmt_*  (외국인 순매도)
          - orgn_netprps_* (기관 순매수)
          - orgn_netslmt_* (기관 순매도)
        """
        results = []
        prefixes = [
            ("for_netprps_", "foreign_buy"),
            ("for_netslmt_", "foreign_sell"),
            ("orgn_netprps_", "inst_buy"),
            ("orgn_netslmt_", "inst_sell"),
        ]
        for item in raw_items:
            for prefix, category in prefixes:
                stk_cd = item.get(f"{prefix}stk_cd", "")
                if stk_cd:
                    results.append({
                        "stk_cd": stk_cd,
                        "stk_nm": item.get(f"{prefix}stk_nm", ""),
                        "amt": item.get(f"{prefix}amt", ""),
                        "qty": item.get(f"{prefix}qty", ""),
                        "category": category,
                    })
        return results

    def invalidate_cache(self):
        """Force cache refresh on next call."""
        self._cache = None
