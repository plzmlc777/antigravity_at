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

logger = logging.getLogger(__name__)

class KiwoomRealAdapter(ExchangeInterface, KiwoomBaseAdapter):
    """
    Real Adapter for Kiwoom Open API V5 (REST).
    Implemented based on 'Kiwoom REST API Documentation'.
    """
    
    def __init__(self, app_key: str = None, secret_key: str = None, account_no: str = None, account_name: str = None):
        # Initialize Base Class
        KiwoomBaseAdapter.__init__(self, app_key or settings.HCP_KIWOOM_APP_KEY, secret_key or settings.HCP_KIWOOM_SECRET_KEY)
        
        # Base URL from docs: https://api.kiwoom.com (Production)
        # But we respect the config if user wants to override (e.g. mock server)
        self.base_url = settings.HCP_KIWOOM_API_URL or "https://api.kiwoom.com"
        
        self.account_no = account_no or settings.HCP_KIWOOM_ACCOUNT_NO
        self.account_name = account_name or "Unknown"
        
        # WebSocket Integration
        self.ws_client = KiwoomWebSocket.get_instance()
        self.ws_client.set_callbacks(on_tick=self._on_ws_tick)
        self.tick_listeners: List[Callable[[Dict], None]] = []
        self._ws_task = None
        
    def add_tick_listener(self, callback: Callable[[Dict], None]):
        self.tick_listeners.append(callback)

    def _on_ws_tick(self, tick_data: Dict):
        for listener in self.tick_listeners:
            try:
                listener(tick_data)
            except Exception as e:
                logger.error(f"Error in tick listener: {e}")

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


    def get_name(self) -> str:
        return "KIWOOM (REAL)"

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
            return {
                "symbol": symbol,
                "price": 0.0,
                "name": "Unknown"
            }

    async def get_balance(self) -> Dict[str, Any]:
        """
        Get Balance using TR: ka01690 (Daily Balance & Return)
        """
        await self._ensure_token()
        
        url = f"{self.base_url}/api/dostk/acnt"
        headers = self._get_auth_headers(tr_id="ka01690")
        
        today_str = datetime.now().strftime("%Y%m%d")
        
        payload = {
            "qry_dt": today_str
        }
        
        client = HttpClientManager.get_instance().get_client()
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            # Parse Response logic (omitted for brevity, assume similar structure)
            # 'dbst_bal': Deposit Balance (Cash)
            
            def safe_float(v):
                if not v: return 0.0
                return float(str(v).replace("+", "").replace("-", ""))

            def safe_int(v):
                if not v: return 0
                return int(str(v).replace("+", "").replace("-", ""))
            
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
