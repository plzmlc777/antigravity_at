"""
KIS (Korean Investment Securities) Real Adapter
- Implements ExchangeInterface for KIS Open API
- Domestic stock trading (국내주식)
- REST: GET for queries, POST for orders (with hashkey)
- WebSocket: lazy creation (same pattern as KiwoomRealAdapter)
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime

from ..core.exchange_interface import ExchangeInterface
from ..core.http_client import HttpClientManager, RateLimiter
from .kis_base import KISBaseAdapter
from ..models.live_trading import ErrorType
from ..services.error_logger import error_logger

logger = logging.getLogger(__name__)

# KIS-specific rate limiters (separate from Kiwoom)
_kis_rate_limiter_real = RateLimiter(max_requests=18, window_seconds=1.0)     # 20/sec with margin
_kis_rate_limiter_virtual = RateLimiter(max_requests=4, window_seconds=1.0)   # 5/sec with margin

# KIS API URLs
KIS_REAL_URL = "https://openapi.koreainvestment.com:9443"
KIS_VIRTUAL_URL = "https://openapivts.koreainvestment.com:29443"

# TR ID mappings: {function: {real: TR_ID, virtual: TR_ID}}
TR_IDS = {
    # Market data (same for both)
    "price":           {"real": "FHKST01010100", "virtual": "FHKST01010100"},
    "minute_chart":    {"real": "FHKST03010200", "virtual": "FHKST03010200"},
    "daily_chart":     {"real": "FHKST03010100", "virtual": "FHKST03010100"},
    # Trading (T→V prefix)
    "buy":             {"real": "TTTC0012U",     "virtual": "VTTC0012U"},
    "sell":            {"real": "TTTC0011U",     "virtual": "VTTC0011U"},
    "cancel":          {"real": "TTTC0013U",     "virtual": "VTTC0013U"},
    "balance":         {"real": "TTTC8434R",     "virtual": "VTTC8434R"},
    "outstanding":     {"real": "TTTC0081R",     "virtual": "VTTC0081R"},
}


class KISRealAdapter(ExchangeInterface, KISBaseAdapter):
    """
    Real Adapter for KIS Open API (REST).
    Implements all ExchangeInterface methods + candle/listener methods.
    """

    def __init__(self, app_key: str = None, app_secret: str = None,
                 account_no: str = None, account_name: str = None,
                 api_url: str = None, is_virtual: bool = False):
        # Parse account number: "12345678-01" → CANO="12345678", PRDT_CD="01"
        cano, acnt_prdt_cd = self._parse_account_no(account_no)
        KISBaseAdapter.__init__(self, app_key, app_secret, cano, acnt_prdt_cd)

        self.base_url = api_url or (KIS_VIRTUAL_URL if is_virtual else KIS_REAL_URL)
        self.account_name = account_name or "Unknown"
        self.is_virtual = is_virtual

        # Rate limiter selection
        self._rate_limiter = _kis_rate_limiter_virtual if is_virtual else _kis_rate_limiter_real

        # WebSocket (lazy creation, same pattern as Kiwoom)
        self._ws_client = None
        self.tick_listeners: List[Callable[[Dict], None]] = []
        self.order_listeners: List[Callable[[Dict], None]] = []
        self.balance_listeners: List[Callable[[Dict], None]] = []
        self._ws_task = None

    @staticmethod
    def _parse_account_no(account_no: str):
        """Parse '12345678-01' into (CANO, ACNT_PRDT_CD)."""
        if not account_no:
            return (None, "01")
        if "-" in account_no:
            parts = account_no.split("-", 1)
            return (parts[0], parts[1] if len(parts) > 1 else "01")
        # If no dash, assume first 8 chars are CANO, rest is product code
        if len(account_no) >= 10:
            return (account_no[:8], account_no[8:10])
        return (account_no, "01")

    def _get_tr_id(self, function: str) -> str:
        """Get appropriate TR ID based on real/virtual environment."""
        env = "virtual" if self.is_virtual else "real"
        return TR_IDS.get(function, {}).get(env, "")

    async def _rate_limited_get(self, url: str, **kwargs):
        """Rate-limited GET request."""
        await self._rate_limiter.acquire()
        client = HttpClientManager.get_instance().get_client()
        return await client.get(url, **kwargs)

    async def _rate_limited_post(self, url: str, **kwargs):
        """Rate-limited POST request."""
        await self._rate_limiter.acquire()
        client = HttpClientManager.get_instance().get_client()
        return await client.post(url, **kwargs)

    # ══════════════════════════════════════════════
    # ExchangeInterface Implementation
    # ══════════════════════════════════════════════

    def get_name(self) -> str:
        return "KIS (VIRTUAL)" if self.is_virtual else "KIS (REAL)"

    def get_account_name(self) -> str:
        return self.account_name

    async def get_current_price(self, symbol: str) -> Dict[str, Any]:
        """
        GET /uapi/domestic-stock/v1/quotations/inquire-price
        TR ID: FHKST01010100
        """
        await self._ensure_token()

        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = self._get_auth_headers(tr_id=self._get_tr_id("price"))
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
        }

        try:
            response = await self._rate_limited_get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("rt_cd") != "0":
                logger.error(f"KIS price error: {data.get('msg1')}")
                return {"symbol": symbol, "price": 0.0, "name": "Unknown"}

            output = data.get("output", {})
            price = abs(int(output.get("stck_prpr", "0")))
            volume = int(output.get("acml_vol", "0"))
            name = output.get("rprs_mrkt_kor_name", "") or output.get("prdt_abrv_name", symbol)

            return {
                "symbol": symbol,
                "price": float(price),
                "volume": volume,
                "name": name,
            }
        except Exception as e:
            logger.error(f"KIS: Error fetching price for {symbol}: {e}")
            error_logger.log_api_error(
                message=f"KIS: Error fetching price for {symbol}: {e}",
                symbol=symbol, exception=e
            )
            return {"symbol": symbol, "price": 0.0, "name": "Unknown"}

    async def get_balance(self) -> Dict[str, Any]:
        """
        GET /uapi/domestic-stock/v1/trading/inquire-balance
        TR ID: TTTC8434R (real) / VTTC8434R (virtual)
        """
        await self._ensure_token()

        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        headers = self._get_auth_headers(tr_id=self._get_tr_id("balance"))
        params = {
            "CANO": self.cano or "",
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        def safe_float(v):
            if not v:
                return 0.0
            return float(str(v).replace("+", "").replace("-", "").replace(",", ""))

        def safe_int(v):
            if not v:
                return 0
            return int(float(str(v).replace("+", "").replace("-", "").replace(",", "")))

        try:
            response = await self._rate_limited_get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("rt_cd") != "0":
                logger.error(f"KIS balance error: {data.get('msg1')}")
                return {"cash": {"KRW": 0}, "holdings": {}}

            # output1: holdings list, output2: summary
            output1 = data.get("output1", [])
            output2 = data.get("output2", [{}])
            summary = output2[0] if output2 else {}

            # Cash: 예수금총금액 or 주문가능현금
            cash_balance = safe_float(summary.get("dnca_tot_amt", "0"))

            holdings = {}
            for item in output1:
                code = item.get("pdno", "")
                qty = safe_int(item.get("hldg_qty", "0"))
                if code and qty > 0:
                    holdings[code] = {
                        "quantity": qty,
                        "avg_price": safe_float(item.get("pchs_avg_pric", "0")),
                        "current_price": safe_float(item.get("prpr", "0")),
                        "profit_rate": safe_float(item.get("evlu_pfls_rt", "0")),
                        "profit_amount": safe_float(item.get("evlu_pfls_amt", "0")),
                    }

            return {"cash": {"KRW": cash_balance}, "holdings": holdings}

        except Exception as e:
            logger.error(f"KIS: Error fetching balance: {e}")
            error_logger.log_error(
                error_type=ErrorType.BALANCE_SYNC_ERROR,
                message=f"KIS: Error fetching balance: {e}",
                exception=e, source_function="get_balance"
            )
            return {"cash": {"KRW": 0}, "holdings": {}}

    async def place_buy_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        """
        POST /uapi/domestic-stock/v1/trading/order-cash
        TR ID: TTTC0012U (real) / VTTC0012U (virtual)
        """
        return await self._place_order(
            tr_function="buy", symbol=symbol, price=price, quantity=quantity
        )

    async def place_sell_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        """
        POST /uapi/domestic-stock/v1/trading/order-cash
        TR ID: TTTC0011U (real) / VTTC0011U (virtual)
        """
        return await self._place_order(
            tr_function="sell", symbol=symbol, price=price, quantity=quantity
        )

    async def _place_order(self, tr_function: str, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        """Common order placement for buy/sell."""
        await self._ensure_token()

        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        tr_id = self._get_tr_id(tr_function)
        side = "buy" if "buy" in tr_function else "sell"

        # Order type: 00=limit, 01=market
        if price == 0:
            ord_dvsn = "01"   # Market order
            ord_unpr = "0"
        else:
            ord_dvsn = "00"   # Limit order
            ord_unpr = str(int(price))

        body = {
            "CANO": self.cano or "",
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": symbol,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(int(quantity)),
            "ORD_UNPR": ord_unpr,
        }

        # Get hashkey for POST requests
        hashkey = await self._get_hashkey(body)

        headers = self._get_auth_headers(tr_id=tr_id)
        if hashkey:
            headers["hashkey"] = hashkey

        try:
            response = await self._rate_limited_post(url, headers=headers, json=body, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("rt_cd") == "0":
                output = data.get("output", {})
                return {
                    "status": "success",
                    "order_id": output.get("ODNO", ""),
                    "symbol": symbol,
                    "side": side,
                    "price": price,
                    "quantity": quantity,
                }
            else:
                return {
                    "status": "failed",
                    "message": data.get("msg1", "Unknown Error"),
                }

        except Exception as e:
            logger.error(f"KIS: Order placement failed ({side}): {e}")
            error_logger.log_order_error(
                message=f"KIS: Order placement failed ({side}): {e}",
                session_id=None, symbol=symbol, exception=e,
                context={"tr_function": tr_function, "price": price, "quantity": quantity}
            )
            return {"status": "failed", "message": str(e)}

    async def get_outstanding_orders(self) -> list:
        """
        GET /uapi/domestic-stock/v1/trading/inquire-daily-ccld
        TR ID: TTTC0081R (real) / VTTC0081R (virtual)
        Filter: CCLD_DVSN=02 for outstanding orders only
        """
        await self._ensure_token()

        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
        headers = self._get_auth_headers(tr_id=self._get_tr_id("outstanding"))

        today = datetime.now().strftime("%Y%m%d")
        params = {
            "CANO": self.cano or "",
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "INQR_STRT_DT": today,
            "INQR_END_DT": today,
            "SLL_BUY_DVSN_CD": "00",   # All (buy+sell)
            "INQR_DVSN": "00",
            "PDNO": "",
            "CCLD_DVSN": "02",         # Outstanding only
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        try:
            response = await self._rate_limited_get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("rt_cd") != "0":
                logger.error(f"KIS outstanding orders error: {data.get('msg1')}")
                return []

            output1 = data.get("output1", [])
            orders = []
            for item in output1:
                unfilled = int(item.get("rmn_qty", "0") or "0")
                if unfilled <= 0:
                    continue
                orders.append({
                    "order_no": item.get("odno", ""),
                    "origin_order_no": item.get("orgn_odno", ""),
                    "symbol": item.get("pdno", ""),
                    "name": item.get("prdt_name", ""),
                    "order_type": item.get("ord_dvsn_name", ""),
                    "side": "buy" if item.get("sll_buy_dvsn_cd") == "02" else "sell",
                    "order_price": float(item.get("ord_unpr", "0") or "0"),
                    "order_qty": int(item.get("ord_qty", "0") or "0"),
                    "unfilled_qty": unfilled,
                    "time": item.get("ord_tmd", ""),
                })
            return orders

        except Exception as e:
            logger.error(f"KIS: Error fetching outstanding orders: {e}")
            error_logger.log_api_error(
                message=f"KIS: Error fetching outstanding orders: {e}",
                exception=e
            )
            return []

    async def cancel_order(self, order_id: str, symbol: str, quantity: int,
                           origin_order_id: str = "") -> Dict[str, Any]:
        """
        POST /uapi/domestic-stock/v1/trading/order-rvsecncl
        TR ID: TTTC0013U (real) / VTTC0013U (virtual)
        """
        await self._ensure_token()

        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-rvsecncl"
        tr_id = self._get_tr_id("cancel")
        target_oid = origin_order_id or order_id

        body = {
            "CANO": self.cano or "",
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO": target_oid,
            "ORD_DVSN": "00",
            "RVSE_CNCL_DVSN_CD": "02",   # 02 = Cancel
            "ORD_QTY": str(int(quantity)) if quantity > 0 else "0",
            "ORD_UNPR": "0",
            "QTY_ALL_ORD_YN": "Y" if quantity == 0 else "N",
        }

        hashkey = await self._get_hashkey(body)
        headers = self._get_auth_headers(tr_id=tr_id)
        if hashkey:
            headers["hashkey"] = hashkey

        try:
            response = await self._rate_limited_post(url, headers=headers, json=body, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("rt_cd") == "0":
                output = data.get("output", {})
                return {
                    "status": "success",
                    "message": "Cancel order submitted",
                    "cancel_order_no": output.get("ODNO", ""),
                }
            else:
                return {
                    "status": "failed",
                    "message": data.get("msg1", "Unknown Error"),
                }

        except Exception as e:
            logger.error(f"KIS: Cancel order failed: {e}")
            error_logger.log_order_error(
                message=f"KIS: Cancel order failed: {e}",
                session_id=None, symbol=symbol, exception=e,
                context={"order_id": order_id, "origin_order_id": origin_order_id}
            )
            return {"status": "failed", "message": str(e)}

    # ══════════════════════════════════════════════
    # Candle Data Methods (matching Kiwoom pattern)
    # ══════════════════════════════════════════════

    async def get_minute_candles(self, symbol: str, interval_minutes: int = 1) -> list:
        """
        GET /uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice
        TR ID: FHKST03010200
        NOTE: KIS only provides TODAY's minute data.
        """
        await self._ensure_token()

        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
        headers = self._get_auth_headers(tr_id=self._get_tr_id("minute_chart"))
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_HOUR_1": "160000",   # End time (fetch all until close)
            "FID_PW_DATA_INCU_YN": "Y",
            "FID_ETC_CLS_CODE": "",
        }

        candles = []
        try:
            response = await self._rate_limited_get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("rt_cd") != "0":
                logger.error(f"KIS minute candle error: {data.get('msg1')}")
                return []

            output2 = data.get("output2", [])
            for item in output2:
                try:
                    ts = item.get("stck_cntg_hour", "")
                    o = abs(int(item.get("stck_oprc", "0") or "0"))
                    h = abs(int(item.get("stck_hgpr", "0") or "0"))
                    l = abs(int(item.get("stck_lwpr", "0") or "0"))
                    c = abs(int(item.get("stck_prpr", "0") or "0"))
                    v = int(item.get("cntg_vol", "0") or "0")

                    if c == 0:
                        continue

                    # Convert HHMMSS to today's datetime string
                    today = datetime.now().strftime("%Y%m%d")
                    candles.append({
                        "timestamp": f"{today}{ts}",
                        "open": o,
                        "high": h,
                        "low": l,
                        "close": c,
                        "volume": v,
                    })
                except (ValueError, TypeError):
                    continue

            candles.sort(key=lambda x: x["timestamp"])
            return candles

        except Exception as e:
            logger.error(f"KIS: Exception in get_minute_candles: {e}")
            error_logger.log_api_error(
                message=f"KIS: Exception in get_minute_candles: {e}",
                symbol=symbol, exception=e
            )
            return []

    async def get_daily_candles(self, symbol: str) -> list:
        """
        GET /uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice
        TR ID: FHKST03010100
        Returns up to 100 records per call.
        """
        await self._ensure_token()

        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        headers = self._get_auth_headers(tr_id=self._get_tr_id("daily_chart"))

        today = datetime.now().strftime("%Y%m%d")
        # Fetch ~1 year of daily data
        from datetime import timedelta
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": today,
            "FID_PERIOD_DIV_CODE": "D",       # Daily
            "FID_ORG_ADJ_PRC": "0",           # Adjusted price
        }

        candles = []
        try:
            response = await self._rate_limited_get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("rt_cd") != "0":
                logger.error(f"KIS daily candle error: {data.get('msg1')}")
                return []

            output2 = data.get("output2", [])
            for item in output2:
                try:
                    ts = item.get("stck_bsop_date", "")
                    o = abs(int(item.get("stck_oprc", "0") or "0"))
                    h = abs(int(item.get("stck_hgpr", "0") or "0"))
                    l = abs(int(item.get("stck_lwpr", "0") or "0"))
                    c = abs(int(item.get("stck_clpr", "0") or "0"))
                    v = int(item.get("acml_vol", "0") or "0")

                    if c == 0 or not ts:
                        continue

                    # Convert YYYYMMDD to YYYY-MM-DD
                    ts_iso = f"{ts[:4]}-{ts[4:6]}-{ts[6:]}" if len(ts) == 8 else ts

                    candles.append({
                        "timestamp": ts_iso,
                        "open": o,
                        "high": h,
                        "low": l,
                        "close": c,
                        "volume": v,
                    })
                except (ValueError, TypeError):
                    continue

            candles.sort(key=lambda x: x["timestamp"])
            return candles

        except Exception as e:
            logger.error(f"KIS: Exception in get_daily_candles: {e}")
            error_logger.log_api_error(
                message=f"KIS: Exception in get_daily_candles: {e}",
                symbol=symbol, exception=e
            )
            return []

    async def get_candles(self, symbol: str, interval: str, days: int = 30, limit: int = 1000) -> list:
        """Unified get_candles method matching KiwoomRealAdapter.get_candles()."""
        candles = []
        if interval == "1d":
            candles = await self.get_daily_candles(symbol)
        elif interval.endswith("m"):
            candles = await self.get_minute_candles(symbol, int(interval.replace("m", "")))
        else:
            candles = await self.get_minute_candles(symbol, 1)

        # Filter by days
        if days > 0 and candles:
            try:
                cutoff = (datetime.now() - __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")
                filtered = [c for c in candles if str(c["timestamp"]) >= cutoff]
                return filtered[-limit:] if limit > 0 else filtered
            except Exception:
                return candles[-limit:] if limit > 0 else candles

        return candles[-limit:] if limit > 0 else candles

    # ══════════════════════════════════════════════
    # Real-time WebSocket Methods (matching Kiwoom)
    # ══════════════════════════════════════════════

    @property
    def ws_client(self):
        """Lazy WebSocket creation."""
        if self._ws_client is None:
            from .kis_websocket import KISWebSocket
            self._ws_client = KISWebSocket(
                app_key=self.app_key,
                app_secret=self.app_secret,
                api_url=self.base_url,
                is_virtual=self.is_virtual,
            )
        return self._ws_client

    def setup_realtime_callbacks(self):
        """Set this adapter's callbacks for WebSocket events."""
        self.ws_client.set_callbacks(
            on_tick=self._on_ws_tick,
            on_order=self._on_ws_order,
            on_balance=self._on_ws_balance,
        )
        logger.info(f"KIS WebSocket callbacks registered")

    async def start_realtime(self, symbols: List[str] = None):
        """Start WebSocket and subscribe to symbols."""
        await self._ensure_token()
        if not self.access_token:
            logger.error("KIS: Cannot start realtime - no token")
            return

        if not self.ws_client.is_running:
            await self.ws_client.connect()

        if symbols:
            await self.ws_client.subscribe_symbols(symbols)

    async def stop_realtime(self):
        """Stop WebSocket."""
        if self._ws_client:
            self._ws_client.is_running = False

    def add_tick_listener(self, callback: Callable[[Dict], None]):
        if callback not in self.tick_listeners:
            self.tick_listeners.append(callback)

    def remove_tick_listener(self, callback: Callable[[Dict], None]):
        if callback in self.tick_listeners:
            self.tick_listeners.remove(callback)

    def add_order_listener(self, callback: Callable[[Dict], None]):
        if callback not in self.order_listeners:
            self.order_listeners.append(callback)

    def remove_order_listener(self, callback: Callable[[Dict], None]):
        if callback in self.order_listeners:
            self.order_listeners.remove(callback)

    def add_balance_listener(self, callback: Callable[[Dict], None]):
        if callback not in self.balance_listeners:
            self.balance_listeners.append(callback)

    def remove_balance_listener(self, callback: Callable[[Dict], None]):
        if callback in self.balance_listeners:
            self.balance_listeners.remove(callback)

    def _on_ws_tick(self, tick_data: Dict):
        for listener in self.tick_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(tick_data))
                else:
                    listener(tick_data)
            except Exception as e:
                logger.error(f"KIS: Error in tick listener: {e}")

    def _on_ws_order(self, order_data: Dict):
        for listener in self.order_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(order_data))
                else:
                    listener(order_data)
            except Exception as e:
                logger.error(f"KIS: Error in order listener: {e}")

    def _on_ws_balance(self, balance_data: Dict):
        for listener in self.balance_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(balance_data))
                else:
                    listener(balance_data)
            except Exception as e:
                logger.error(f"KIS: Error in balance listener: {e}")
