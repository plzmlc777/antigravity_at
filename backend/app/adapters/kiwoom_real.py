import httpx
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from ..core.exchange_interface import ExchangeInterface
from ..core.config import settings

logger = logging.getLogger(__name__)

class KiwoomRealAdapter(ExchangeInterface):
    """
    Real Adapter for Kiwoom Open API V5 (REST).
    Implemented based on 'Kiwoom REST API Documentation'.
    """
    
    def __init__(self, app_key: str = None, secret_key: str = None, account_no: str = None, account_name: str = None):
        # Base URL from docs: https://api.kiwoom.com (Production)
        # But we respect the config if user wants to override (e.g. mock server)
        self.base_url = settings.HCP_KIWOOM_API_URL or "https://api.kiwoom.com"
        
        # Priority: Passed args > Settings (Env)
        self.app_key = app_key or settings.HCP_KIWOOM_APP_KEY
        self.secret_key = secret_key or settings.HCP_KIWOOM_SECRET_KEY
        self.account_no = account_no or settings.HCP_KIWOOM_ACCOUNT_NO
        self.account_name = account_name or "Unknown"
        
        self.access_token: Optional[str] = None
        self._common_headers = {
            "Content-Type": "application/json;charset=UTF-8"
        }

    def get_name(self) -> str:
        return "KIWOOM (REAL)"

    def get_account_name(self) -> str:
        return self.account_name

    async def _ensure_token(self):
        """
        Fetch Access Token using TR: au10001
        """
        if self.access_token:
            return

        url = f"{self.base_url}/oauth2/token"
        
        headers = {
            **self._common_headers,
            "api-id": "au10001"
        }
        
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.secret_key
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                
                self.access_token = data.get("token")
                logger.info("Kiwoom Access Token acquired successfully")
            except Exception as e:
                logger.error(f"Failed to get Kiwoom Token: {e}")
                # We do not raise here to avoid crashing app startup, 
                # but subsequent calls will fail.

    def _get_auth_headers(self, tr_id: str) -> Dict[str, str]:
        if not self.access_token:
            return {}
            
        return {
            **self._common_headers,
            "Authorization": f"Bearer {self.access_token}",
            "api-id": tr_id
        }

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
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                
                # 'cur_prc' maps to Current Price
                price_str = data.get("cur_prc", "0").replace("+", "").replace("-", "")
                
                return {
                    "symbol": symbol,
                    "price": float(price_str),
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
        
        # Date format: YYYYMMDD
        today_str = datetime.now().strftime("%Y%m%d")
        
        payload = {
            "qry_dt": today_str
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                
                # Parse Response
                # 'dbst_bal': Deposit Balance (Cash)
                # 'day_bal_rt': List of holdings
                
                # DEBUG: Log fields to find correct keys
                if len(data.get("day_bal_rt", [])) > 0:
                     print(f"DEBUG HOLDING ITEM: {data['day_bal_rt'][0]}", flush=True)
                
                # Helper for safe float/int conversion
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
                            "avg_price": safe_float(item.get("buy_uv", "0")),        # Corrected Field
                            "current_price": safe_float(item.get("cur_prc", "0")),
                            "profit_rate": safe_float(item.get("prft_rt", "0")),     # Corrected Field
                            "profit_amount": safe_float(item.get("evltv_prft", "0")) # Corrected Field
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
            price_str = "" # Market order doesn't need price
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
        
        async with httpx.AsyncClient() as client:
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
