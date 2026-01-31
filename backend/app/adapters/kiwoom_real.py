from ..core.http_client import HttpClientManager
import httpx
import logging
import asyncio
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from ..core.exchange_interface import ExchangeInterface
from ..core.config import settings
from ..core.token_manager import KiwoomTokenManager
from .kiwoom_websocket import KiwoomWebSocket
from .kiwoom_base import KiwoomBaseAdapter
from ..models.live_trading import ErrorType
from ..services.error_logger import error_logger

logger = logging.getLogger(__name__)

class KiwoomRealAdapter(ExchangeInterface, KiwoomBaseAdapter):
    """
    Real Adapter for Kiwoom Open API V5 (REST).
    Implemented based on 'Kiwoom REST API Documentation'.
    """
    
    def __init__(self, app_key: str = None, secret_key: str = None, account_no: str = None, account_name: str = None, api_url: str = None, is_virtual: bool = False):
        # Initialize Base Class
        KiwoomBaseAdapter.__init__(self, app_key or settings.HCP_KIWOOM_APP_KEY, secret_key or settings.HCP_KIWOOM_SECRET_KEY)

        # Base URL - Priority:
        # 1. Explicit api_url parameter (for per-account virtual/real server)
        # 2. Global config HCP_KIWOOM_API_URL
        # 3. Default production server
        self.base_url = api_url or settings.HCP_KIWOOM_API_URL or "https://api.kiwoom.com"

        self.account_no = account_no or settings.HCP_KIWOOM_ACCOUNT_NO
        self.account_name = account_name or "Unknown"
        self.is_virtual = is_virtual  # 가상 계좌 (모의투자) 여부
        
        # WebSocket Integration (shared singleton)
        # NOTE: Do NOT set callbacks here — multiple KiwoomRealAdapter instances
        # are created for REST API calls, and each would overwrite the singleton's
        # tick callback, breaking LiveManager's real-time tick routing.
        # Callbacks are set explicitly via setup_realtime_callbacks().
        self.ws_client = KiwoomWebSocket.get_instance()
        self.tick_listeners: List[Callable[[Dict], None]] = []
        self.order_listeners: List[Callable[[Dict], None]] = []
        self.balance_listeners: List[Callable[[Dict], None]] = []
        self._ws_task = None

    def setup_realtime_callbacks(self):
        """
        Set this adapter's callbacks for WebSocket events.
        Should only be called ONCE by the owner (LiveManager).
        """
        self.ws_client.set_callbacks(
            on_tick=self._on_ws_tick,
            on_order=self._on_ws_order,
            on_balance=self._on_ws_balance
        )
        logger.info(f"WebSocket callbacks registered (tick: {len(self.tick_listeners)}, order: {len(self.order_listeners)})")

    async def register_real_listener(self, symbol: str, callback: Callable[[Dict], Any]):
        """
        Special registration for MarketDataRouter/Watching.
        """
        self.add_tick_listener(callback)
        await self.start_realtime([symbol])

    def _on_ws_tick(self, tick_data: Dict):
        for listener in self.tick_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(tick_data))
                else:
                    listener(tick_data)
            except Exception as e:
                logger.error(f"Error in tick listener: {e}")
                error_logger.log_api_error(
                    message=f"Error in tick listener: {e}",
                    symbol=tick_data.get("symbol"),
                    exception=e
                )

    def _on_ws_order(self, order_data: Dict):
        """Handle order execution events from WebSocket"""
        for listener in self.order_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(order_data))
                else:
                    listener(order_data)
            except Exception as e:
                logger.error(f"Error in order listener: {e}")
                error_logger.log_order_error(
                    message=f"Error in order listener: {e}",
                    session_id=None,
                    symbol=order_data.get("symbol"),
                    exception=e,
                    context=order_data
                )

    def _on_ws_balance(self, balance_data: Dict):
        """Handle balance change events from WebSocket"""
        for listener in self.balance_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(balance_data))
                else:
                    listener(balance_data)
            except Exception as e:
                logger.error(f"Error in balance listener: {e}")
                error_logger.log_error(
                    error_type=ErrorType.BALANCE_SYNC_ERROR,
                    message=f"Error in balance listener: {e}",
                    symbol=balance_data.get("symbol"),
                    exception=e,
                    context=balance_data,
                    source_function="_on_ws_balance"
                )

    async def start_realtime(self, symbols: List[str] = None):
        """
        Start WebSocket connection and subscribe to symbols.
        """
        await self._ensure_token()
        if not self.access_token:
            logger.error("Cannot start Realtime: No Token")
            return

        if not self.ws_client.is_running:
            await self.ws_client.connect(self.access_token)
            
        if symbols:
            await self.ws_client.subscribe_symbols(symbols)

    async def stop_realtime(self):
        self.ws_client.is_running = False

    def add_tick_listener(self, callback: Callable[[Dict], None]):
        """Add a tick listener callback."""
        if callback not in self.tick_listeners:
            self.tick_listeners.append(callback)
            logger.debug(f"Added tick listener. Total: {len(self.tick_listeners)}")

    def remove_tick_listener(self, callback: Callable[[Dict], None]):
        """Remove a tick listener callback."""
        if callback in self.tick_listeners:
            self.tick_listeners.remove(callback)
            logger.debug(f"Removed tick listener. Total: {len(self.tick_listeners)}")

    def add_order_listener(self, callback: Callable[[Dict], None]):
        """Add an order execution listener callback."""
        if callback not in self.order_listeners:
            self.order_listeners.append(callback)
            logger.debug(f"Added order listener. Total: {len(self.order_listeners)}")

    def remove_order_listener(self, callback: Callable[[Dict], None]):
        """Remove an order execution listener callback."""
        if callback in self.order_listeners:
            self.order_listeners.remove(callback)
            logger.debug(f"Removed order listener. Total: {len(self.order_listeners)}")

    def add_balance_listener(self, callback: Callable[[Dict], None]):
        """Add a balance change listener callback."""
        if callback not in self.balance_listeners:
            self.balance_listeners.append(callback)
            logger.debug(f"Added balance listener. Total: {len(self.balance_listeners)}")

    def remove_balance_listener(self, callback: Callable[[Dict], None]):
        """Remove a balance change listener callback."""
        if callback in self.balance_listeners:
            self.balance_listeners.remove(callback)
            logger.debug(f"Removed balance listener. Total: {len(self.balance_listeners)}")


    def get_name(self) -> str:
        return "KIWOOM (VIRTUAL)" if self.is_virtual else "KIWOOM (REAL)"

    def get_account_name(self) -> str:
        return self.account_name

    async def get_current_price(self, symbol: str) -> Dict[str, Any]:
        """
        Get Price using TR: ka10001 (Stock Basic Info)
        """
        await self._ensure_token()
        
        url = f"{self.base_url}/api/dostk/stkinfo"
        headers = self._get_auth_headers(tr_id="ka10001")
        
        payload = {
            "stk_cd": symbol
        }
        
        client = HttpClientManager.get_instance().get_client()
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            data = response.json()
            
            # 'cur_prc' maps to Current Price
            price_str = data.get("cur_prc", "0").replace("+", "").replace("-", "")
            volume_str = data.get("trde_qty", "0") # Accumulated Volume
            
            return {
                "symbol": symbol,
                "price": float(price_str),
                "volume": int(volume_str),
                "name": data.get("stk_nm", symbol) # Return name or code if missing
            }
        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
            error_logger.log_api_error(
                message=f"Error fetching price for {symbol}: {e}",
                symbol=symbol,
                exception=e
            )
            return {
                "symbol": symbol,
                "price": 0.0,
                "name": "Unknown"
            }

    async def get_balance(self) -> Dict[str, Any]:
        """
        Get Balance using:
        - kt00004 (계좌평가현황요청) for mock server (mockapi.kiwoom.com)
        - ka01690 (일별잔고수익률) for real server (api.kiwoom.com)

        Note: ka01690 does NOT support mock trading, so we use kt00004 for virtual accounts.
        """
        await self._ensure_token()

        url = f"{self.base_url}/api/dostk/acnt"

        def safe_float(v):
            if not v: return 0.0
            return float(str(v).replace("+", "").replace("-", ""))

        def safe_int(v):
            if not v: return 0
            return int(str(v).replace("+", "").replace("-", ""))

        client = HttpClientManager.get_instance().get_client()

        # Use different TR ID based on server type
        is_mock_server = "mockapi" in self.base_url.lower()

        try:
            if is_mock_server:
                # Use kt00004 for mock server (ka01690 doesn't support mock trading)
                headers = self._get_auth_headers(tr_id="kt00004")
                payload = {
                    "qry_tp": "0",      # 전체
                    "dmst_stex_tp": "KRX"  # 한국거래소
                }

                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

                # Parse kt00004 response
                # 'entr': 예수금, 'prsm_dpst_aset_amt': 추정예탁자산
                cash_balance = safe_float(data.get("entr", "0"))
                holdings_data = data.get("stk_acnt_evlt_prst", [])

                holdings = {}
                for item in holdings_data:
                    code = item.get("stk_cd", "").replace("A", "")  # Remove 'A' prefix
                    qty = safe_int(item.get("rmnd_qty", "0"))
                    if code and qty > 0:
                        holdings[code] = {
                            "quantity": qty,
                            "avg_price": safe_float(item.get("avg_prc", "0")),
                            "current_price": safe_float(item.get("cur_prc", "0")),
                            "profit_rate": safe_float(item.get("pl_rt", "0")),
                            "profit_amount": safe_float(item.get("pl_amt", "0"))
                        }
            else:
                # Use ka01690 for real server
                headers = self._get_auth_headers(tr_id="ka01690")
                today_str = datetime.now().strftime("%Y%m%d")
                payload = {
                    "qry_dt": today_str
                }

                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

                # Parse ka01690 response
                # 'dbst_bal': Deposit Balance (Cash)
                cash_balance = safe_float(data.get("dbst_bal", "0"))
                holdings_data = data.get("day_bal_rt", [])

                holdings = {}
                for item in holdings_data:
                    code = item.get("stk_cd")
                    qty = safe_int(item.get("rmnd_qty", "0"))
                    if code and qty > 0:
                        holdings[code] = {
                            "quantity": qty,
                            "avg_price": safe_float(item.get("buy_uv", "0")),
                            "current_price": safe_float(item.get("cur_prc", "0")),
                            "profit_rate": safe_float(item.get("prft_rt", "0")),
                            "profit_amount": safe_float(item.get("evltv_prft", "0"))
                        }

            return {
                "cash": {"KRW": cash_balance},
                "holdings": holdings
            }
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            error_logger.log_error(
                error_type=ErrorType.BALANCE_SYNC_ERROR,
                message=f"Error fetching balance: {e}",
                exception=e,
                source_function="get_balance"
            )
            return {"cash": {"KRW": 0}, "holdings": {}}

    async def place_buy_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        """
        Place Buy Order using TR: kt10000
        """
        return await self._place_order(
            tr_id="kt10000",
            symbol=symbol,
            price=price,
            quantity=quantity,
            trade_type="0" # 0: Limit Order (Designated Price)
        )

    async def place_sell_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        """
        Place Sell Order using TR: kt10001
        """
        return await self._place_order(
            tr_id="kt10001",
            symbol=symbol,
            price=price,
            quantity=quantity,
            trade_type="0" # 0: Limit Order
        )

    async def _place_order(self, tr_id: str, symbol: str, price: float, quantity: float, trade_type: str) -> Dict[str, Any]:
        await self._ensure_token()
        
        url = f"{self.base_url}/api/dostk/ordr"
        headers = self._get_auth_headers(tr_id=tr_id)
        
        # If price is 0, assume Market Order (trade_type '3')
        if price == 0:
            trade_type = "3"
            price_str = "" 
        else:
            price_str = str(int(price))

        payload = {
            "dmst_stex_tp": "KRX",
            "stk_cd": symbol,
            "ord_qty": str(int(quantity)),
            "ord_uv": price_str,
            "trde_tp": trade_type,
            "cond_uv": ""
        }
        
        client = HttpClientManager.get_instance().get_client()
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if data.get("return_code") == 0:
                 return {
                    "status": "success",
                    "order_id": data.get("ord_no"),
                    "symbol": symbol,
                    "side": "buy" if tr_id == "kt10000" else "sell",
                    "price": price,
                    "quantity": quantity
                }
            else:
                return {
                    "status": "failed",
                    "message": data.get("return_msg", "Unknown Error")
                }

        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            error_logger.log_order_error(
                message=f"Order placement failed: {e}",
                session_id=None,
                symbol=symbol,
                exception=e,
                context={"tr_id": tr_id, "price": price, "quantity": quantity, "trade_type": trade_type}
            )
            return {"status": "failed", "message": str(e)}

    async def get_outstanding_orders(self) -> list:
        """
        Get Outstanding Orders using TR: ka10075
        """
        await self._ensure_token()
        
        url = f"{self.base_url}/api/dostk/acnt"
        headers = self._get_auth_headers(tr_id="ka10075")
        
        payload = {
            "all_stk_tp": "0", 
            "trde_tp": "0",
            "stk_cd": "", 
            "stex_tp": "0" 
        }
        
        client = HttpClientManager.get_instance().get_client()
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            orders_data = data.get("oso", [])
            
            outstanding_orders = []
            for item in orders_data:
                def clean(v): return str(v).strip()
                def safe_int(v): return int(str(v).replace("+","").replace("-","")) if v else 0
                def safe_float(v): return float(str(v).replace("+","").replace("-","")) if v else 0.0

                outstanding_orders.append({
                    "order_no": clean(item.get("ord_no")),
                    "origin_order_no": clean(item.get("orig_ord_no")),
                    "symbol": clean(item.get("stk_cd")),
                    "name": clean(item.get("stk_nm")),
                    "order_type": clean(item.get("trde_tp")),
                    "side": clean(item.get("io_tp_nm")),
                    "order_price": safe_float(item.get("ord_pric")),
                    "order_qty": safe_int(item.get("ord_qty")),
                    "unfilled_qty": safe_int(item.get("oso_qty")),
                    "time": clean(item.get("tm"))
                })
                
            return outstanding_orders

        except Exception as e:
            logger.error(f"Error fetching outstanding orders: {e}")
            error_logger.log_api_error(
                message=f"Error fetching outstanding orders: {e}",
                exception=e
            )
            return []

    async def cancel_order(self, order_id: str, symbol: str, quantity: int, origin_order_id: str = "") -> Dict[str, Any]:
        """
        Cancel Order using TR: kt10003 (주식 취소주문)
        Note: API docs say 'orig_ord_no' is required. Usually this is the order_id we want to cancel.
        """
        await self._ensure_token()
        
        url = f"{self.base_url}/api/dostk/ordr"
        headers = self._get_auth_headers(tr_id="kt10003")
        
        # origin_order_id typically IS the order_id in Kiwoom logic for cancellation, 
        # or the 'orig_ord_no' field from the outstanding list.
        target_oid = origin_order_id if origin_order_id else order_id

        payload = {
            "dmst_stex_tp": "KRX",
            "orig_ord_no": target_oid,
            "stk_cd": symbol,
            "cncl_qty": str(quantity) # '0' for all
        }
        
        client = HttpClientManager.get_instance().get_client()
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if data.get("return_code") == 0:
                return {
                    "status": "success",
                    "message": "Cancel order submitted",
                    "cancel_order_no": data.get("ord_no")
                }
            else:
                return {
                    "status": "failed",
                    "message": data.get("return_msg", "Unknown Error")
                }

        except Exception as e:
            logger.error(f"Cancel order failed: {e}")
            error_logger.log_order_error(
                message=f"Cancel order failed: {e}",
                session_id=None,
                symbol=symbol,
                exception=e,
                context={"order_id": order_id, "origin_order_id": origin_order_id, "quantity": quantity}
            )
            return {"status": "failed", "message": str(e)}

    async def get_minute_candles(self, symbol: str, interval_minutes: int = 1) -> list:
        """
        Fetch minute candles using ka10080 (Stock Minute Chart)
        """
        await self._ensure_token()
        token = self.access_token
        if not token:
            logger.error("Failed to acquire token from TokenManager")
            return []

        url = f"{self.base_url}/api/dostk/chart"
        headers = self._get_auth_headers(tr_id="ka10080")
        headers["content-type"] = "application/json;charset=UTF-8" # Ensure content type is set (though _common_headers has it)
        
        # Payload per doc (page 197)
        payload = {
            "stk_cd": symbol,
            "tic_scope": str(interval_minutes),
            "upd_stkpc_tp": "1" # Adjusted Price
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload, timeout=10.0)
                
                if response.status_code != 200:
                    logger.error(f"Error fetching candles: Server error '{response.status_code} {response.reason_phrase}' for url '{url}'")
                    return []
                
                data = response.json()
                if data.get("return_code") != 0:
                    logger.error(f"API Error get_minute_candles: {data.get('return_msg')}")
                    return []
                
                output = data.get("stk_min_pole_chart_qry", [])
                candles = []
                
                for item in output:
                    # Parse fields (prices might be negative string)
                    # cntr_tm: 20250917132000
                    try:
                        ts = item.get("cntr_tm")
                        c = abs(int(item.get("cur_prc", 0)))
                        o = abs(int(item.get("open_pric", 0)))
                        h = abs(int(item.get("high_pric", 0)))
                        l = abs(int(item.get("low_pric", 0)))
                        v = int(item.get("trde_qty", 0))
                        
                        candles.append({
                            "timestamp": ts,
                            "open": o,
                            "high": h,
                            "low": l,
                            "close": c,
                            "volume": v
                        })
                    except ValueError:
                        continue

                # Sort by time ascending
                candles.sort(key=lambda x: x['timestamp'])
                return candles

        except Exception as e:
            logger.error(f"Exception in get_minute_candles: {e}")
            error_logger.log_api_error(
                message=f"Exception in get_minute_candles: {e}",
                symbol=symbol,
                exception=e,
                context={"interval_minutes": interval_minutes}
            )
            return []

    async def get_daily_candles(self, symbol: str) -> list:
        """
        Fetch daily candles using ka10081 (Stock Daily Chart)
        """
        await self._ensure_token()
        token = self.access_token
        if not token:
            return []

        url = f"{self.base_url}/api/dostk/chart"
        headers = self._get_auth_headers(tr_id="ka10081")
        headers["content-type"] = "application/json;charset=UTF-8"
        
        payload = {
            "stk_cd": symbol,
            "upd_stkpc_tp": "1" # Adjusted Price
        }

        try:
            from httpx import AsyncClient
            async with AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload, timeout=10.0)
                
                if response.status_code != 200:
                    logger.error(f"Error fetching daily candles: {response.status_code}")
                    return []
                
                data = response.json()
                if data.get("return_code") != 0:
                    return []
                
                output = data.get("stk_day_pole_chart_qry", []) 
                
                candles = []
                for item in output:
                    try:
                        ts = item.get("stk_dt") # YYYYMMDD
                        
                        c = abs(int(item.get("cur_prc", 0)))
                        o = abs(int(item.get("open_pric", 0)))
                        h = abs(int(item.get("high_pric", 0)))
                        l = abs(int(item.get("low_pric", 0)))
                        v = int(item.get("trde_qty", 0))
                        
                        # Convert YYYYMMDD to ISO date string (YYYY-MM-DD) for consistency
                        if ts and len(ts) == 8:
                            ts_iso = f"{ts[:4]}-{ts[4:6]}-{ts[6:]}"
                        else:
                            ts_iso = ts

                        candles.append({
                            "timestamp": ts_iso,
                            "open": o,
                            "high": h,
                            "low": l,
                            "close": c,
                            "volume": v
                        })
                    except ValueError:
                        continue

                candles.sort(key=lambda x: x['timestamp'])
                return candles

        except Exception as e:
            logger.error(f"Exception in get_daily_candles: {e}")
            error_logger.log_api_error(
                message=f"Exception in get_daily_candles: {e}",
                symbol=symbol,
                exception=e
            )
            return []

    async def get_candles(self, symbol: str, interval: str, days: int = 30, limit: int = 1000) -> list:
        """
        Unified get_candles method.
        interval: "1m", "30m", "1d"
        """
        candles = []
        if interval == "1d":
            candles = await self.get_daily_candles(symbol)
        elif interval.endswith("m"):
            minute = int(interval.replace("m", ""))
            candles = await self.get_minute_candles(symbol, minute)
        else:
            # Default
            candles = await self.get_minute_candles(symbol, 1)

        # Filter by Days (Cutoff)
        if days > 0 and candles:
            try:
                from datetime import datetime, timedelta
                cutoff = datetime.now() - timedelta(days=days)
                # Parse timestamp and filter
                # Format is usually YYYY-MM-DD or YYYYMMDDHHMMSS
                filtered = []
                for c in candles:
                    ts_str = str(c['timestamp'])
                    # Normalize if needed, but assuming ISO or comparable string
                    # Simple string comparison works for ISO YYYY-MM-DD
                    # Construct cutoff string
                    cutoff_str = cutoff.strftime("%Y-%m-%d")
                    if ts_str >= cutoff_str:
                        filtered.append(c)
                return filtered[-limit:] if limit > 0 else filtered
            except Exception as e:
                logger.error(f"Error filtering candles: {e}")
                return candles[-limit:] if limit > 0 else candles

        return candles[-limit:] if limit > 0 else candles
