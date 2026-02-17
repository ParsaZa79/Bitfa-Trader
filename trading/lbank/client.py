"""LBank Futures (Contract) API client.

Base URL: https://lbkperp.lbank.com
Auth: HmacSHA256 signature on MD5(sorted params).upper()
Docs: https://www.lbank.com/docs/contract.html
"""

import hashlib
import hmac
import random
import string
import time

import httpx
from django.conf import settings


class LBankFuturesClient:
    """Async client for LBank Futures (CFD) REST API."""

    PRODUCT_GROUP = "SwapU"  # USDT-margined perpetual

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
        signature_method: str | None = None,
    ):
        self.api_key = api_key or settings.LBANK_API_KEY
        self.secret_key = secret_key or settings.LBANK_SECRET_KEY
        self.base_url = (base_url or settings.LBANK_BASE_URL).rstrip("/")
        self.signature_method = signature_method or settings.LBANK_SIGNATURE_METHOD
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=30)

    async def close(self):
        await self._http.aclose()

    # ── Helpers ──────────────────────────────────────────────

    def _echostr(self, length: int = 35) -> str:
        return "".join(random.choices(string.ascii_letters + string.digits, k=length))

    def _sign(self, params: dict) -> str:
        """Generate signature per LBank contract API spec.

        1. Sort params alphabetically, build query string
        2. MD5 → uppercase
        3. HmacSHA256 with secret key
        """
        sorted_keys = sorted(params.keys())
        query = "&".join(f"{k}={params[k]}" for k in sorted_keys)

        # Step 2: MD5 uppercase
        md5_digest = hashlib.md5(query.encode()).hexdigest().upper()

        # Step 3: HmacSHA256
        signature = hmac.new(
            self.secret_key.encode(),
            md5_digest.encode(),
            hashlib.sha256,
        ).hexdigest()

        return signature

    def _auth_headers(self, params: dict) -> dict:
        """Build authenticated request headers + inject auth params."""
        ts = str(int(time.time() * 1000))
        echostr = self._echostr()

        # Add auth params to sign
        params["api_key"] = self.api_key
        params["signature_method"] = self.signature_method
        params["timestamp"] = ts
        params["echostr"] = echostr

        sign = self._sign(params)

        headers = {
            "Content-Type": "application/json",
            "timestamp": ts,
            "signature_method": self.signature_method,
            "echostr": echostr,
        }
        params["sign"] = sign
        return headers

    async def _get(self, path: str, params: dict | None = None, auth: bool = False) -> dict:
        params = params or {}
        headers = {}
        if auth:
            headers = self._auth_headers(params)
        resp = await self._http.get(path, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, data: dict | None = None) -> dict:
        data = data or {}
        headers = self._auth_headers(data)
        resp = await self._http.post(path, json=data, headers=headers)
        resp.raise_for_status()
        return resp.json()

    # ── Public Endpoints ─────────────────────────────────────

    async def get_time(self) -> dict:
        """Get server time."""
        return await self._get("/cfd/openApi/v1/pub/getTime")

    async def get_instruments(self) -> list[dict]:
        """Get available contract instruments."""
        return await self._get(
            "/cfd/openApi/v1/pub/instrument",
            {"productGroup": self.PRODUCT_GROUP},
        )

    async def get_market_data(self) -> list[dict]:
        """Get market data for all contracts."""
        return await self._get(
            "/cfd/openApi/v1/pub/marketData",
            {"productGroup": self.PRODUCT_GROUP},
        )

    async def get_orderbook(self, symbol: str, depth: int = 10) -> dict:
        """Get orderbook for a symbol."""
        return await self._get(
            "/cfd/openApi/v1/pub/marketOrder",
            {"symbol": symbol, "depth": depth},
        )

    # ── Account Endpoints ────────────────────────────────────

    async def get_account(self, asset: str = "USDT") -> dict:
        """Get account balance info."""
        return await self._post(
            "/cfd/openApi/v1/prv/account",
            {"asset": asset, "productGroup": self.PRODUCT_GROUP},
        )

    async def get_positions(self, symbol: str | None = None) -> dict:
        """Get open positions."""
        params = {"productGroup": self.PRODUCT_GROUP}
        if symbol:
            params["symbol"] = symbol
        return await self._post("/cfd/openApi/v1/prv/position", params)

    # ── Trading Endpoints ────────────────────────────────────

    async def set_leverage(self, symbol: str, leverage: int) -> dict:
        """Set leverage for a symbol."""
        return await self._post(
            "/cfd/openApi/v1/prv/setLeverage",
            {
                "symbol": symbol,
                "leverage": str(leverage),
                "productGroup": self.PRODUCT_GROUP,
            },
        )

    async def set_margin_type(self, symbol: str, margin_type: str = "isolated") -> dict:
        """Set margin type (isolated/cross) for a symbol."""
        return await self._post(
            "/cfd/openApi/v1/prv/setMarginType",
            {
                "symbol": symbol,
                "positionType": "1" if margin_type == "isolated" else "2",
                "productGroup": self.PRODUCT_GROUP,
            },
        )

    async def place_order(
        self,
        symbol: str,
        side: str,
        volume: str,
        price: str | None = None,
        order_type: str = "limit",
    ) -> dict:
        """Place a futures order.

        Args:
            symbol: Trading pair (e.g. "ETHUSDT")
            side: "open_long", "open_short", "close_long", "close_short"
            volume: Order quantity
            price: Limit price (None for market order)
            order_type: "limit" or "market"
        """
        data = {
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "type": order_type,
            "productGroup": self.PRODUCT_GROUP,
        }
        if price and order_type == "limit":
            data["price"] = price
        return await self._post("/cfd/openApi/v1/prv/order", data)

    async def cancel_order(self, symbol: str, order_id: str) -> dict:
        """Cancel an open order."""
        return await self._post(
            "/cfd/openApi/v1/prv/cancelOrder",
            {
                "symbol": symbol,
                "orderId": order_id,
                "productGroup": self.PRODUCT_GROUP,
            },
        )

    async def get_order(self, symbol: str, order_id: str) -> dict:
        """Get order details."""
        return await self._post(
            "/cfd/openApi/v1/prv/orderDetail",
            {
                "symbol": symbol,
                "orderId": order_id,
                "productGroup": self.PRODUCT_GROUP,
            },
        )

    async def get_open_orders(self, symbol: str | None = None) -> dict:
        """Get all open orders."""
        params = {"productGroup": self.PRODUCT_GROUP}
        if symbol:
            params["symbol"] = symbol
        return await self._post("/cfd/openApi/v1/prv/openOrders", params)

    async def set_stop_loss(
        self,
        symbol: str,
        side: str,
        stop_price: str,
    ) -> dict:
        """Set stop loss for a position.

        Args:
            symbol: Trading pair
            side: "long" or "short"
            stop_price: Stop loss trigger price
        """
        return await self._post(
            "/cfd/openApi/v1/prv/setStopOrder",
            {
                "symbol": symbol,
                "side": side,
                "stopPrice": stop_price,
                "triggerType": "mark_price",
                "orderType": "stop_loss",
                "productGroup": self.PRODUCT_GROUP,
            },
        )

    async def set_take_profit(
        self,
        symbol: str,
        side: str,
        stop_price: str,
    ) -> dict:
        """Set take profit for a position."""
        return await self._post(
            "/cfd/openApi/v1/prv/setStopOrder",
            {
                "symbol": symbol,
                "side": side,
                "stopPrice": stop_price,
                "triggerType": "mark_price",
                "orderType": "take_profit",
                "productGroup": self.PRODUCT_GROUP,
            },
        )
