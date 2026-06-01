"""Thin REST client for the Binance USDT-M Futures Testnet.

This wraps ``requests`` and handles the parts that are easy to get wrong:
signing requests with HMAC-SHA256, keeping the local clock in sync with the
exchange, attaching the API-key header, and turning HTTP/Binance errors into our
own exception types. Order-building logic lives in ``orders.py`` -- this layer
just knows how to talk to the API.
"""

import hashlib
import hmac
import time
from urllib.parse import urlencode

import requests

from .exceptions import BinanceAPIError, NetworkError
from .logging_config import get_logger, redact

log = get_logger("tradingbot.client")

DEFAULT_BASE_URL = "https://testnet.binancefuture.com"


class BinanceFuturesClient:
    """Signed REST client for Binance Futures (USDT-M)."""

    def __init__(self, api_key, api_secret, base_url=DEFAULT_BASE_URL,
                 recv_window=5000, timeout=10):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.recv_window = recv_window
        self.timeout = timeout

        self._session = requests.Session()
        self._session.headers.update({"X-MBX-APIKEY": api_key})

        # Cache of exchangeInfo symbol filters, filled lazily.
        self._symbol_filters = {}
        # Difference (ms) between Binance server time and our local clock.
        self._time_offset = 0

    # -- low level ---------------------------------------------------------

    def _sign(self, query_string):
        """Return the HMAC-SHA256 signature for an already-encoded query."""
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _timestamp(self):
        return int(time.time() * 1000) + self._time_offset

    def _request(self, method, path, params=None, signed=False):
        """Send a request and return the decoded JSON body.

        Raises ``BinanceAPIError`` if Binance reports an error and
        ``NetworkError`` if the request never completes.
        """
        params = dict(params or {})
        url = f"{self.base_url}{path}"

        if signed:
            params["timestamp"] = self._timestamp()
            params["recvWindow"] = self.recv_window
            query = urlencode(params)
            params["signature"] = self._sign(query)
            # Re-encode with the signature appended in the same order.
            url = f"{url}?{urlencode(params)}"
            send_params = None
        else:
            send_params = params

        log.debug("Request %s %s params=%s", method, path, redact(params))

        try:
            response = self._session.request(
                method, url, params=send_params, timeout=self.timeout
            )
        except requests.RequestException as exc:
            log.error("Network error calling %s %s: %s", method, path, exc)
            raise NetworkError(f"Could not reach Binance: {exc}") from exc

        return self._handle_response(response, method, path)

    def _handle_response(self, response, method, path):
        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text}

        if response.status_code >= 400:
            code = body.get("code") if isinstance(body, dict) else None
            msg = body.get("msg") if isinstance(body, dict) else response.text
            log.error(
                "API error %s %s -> HTTP %s code=%s msg=%s",
                method, path, response.status_code, code, msg,
            )
            raise BinanceAPIError(code, msg or "Unknown error",
                                  status_code=response.status_code)

        # Only the request line + status is logged here; callers that care about
        # the body (e.g. new_order) log it explicitly. This keeps bulk responses
        # like exchangeInfo out of the log file.
        log.debug("Response %s %s -> HTTP %s", method, path, response.status_code)
        return body

    # -- public endpoints --------------------------------------------------

    def ping(self):
        """Test connectivity. Returns an empty dict on success."""
        return self._request("GET", "/fapi/v1/ping")

    def server_time(self):
        """Return the exchange server time in milliseconds."""
        return self._request("GET", "/fapi/v1/time")["serverTime"]

    def sync_time(self):
        """Measure and store the offset between server and local clock.

        Doing this once before signed calls avoids ``-1021`` timestamp errors
        when the local machine's clock drifts.
        """
        server = self.server_time()
        local = int(time.time() * 1000)
        self._time_offset = server - local
        log.debug("Clock synced, offset=%sms", self._time_offset)
        return self._time_offset

    def get_symbol_filters(self, symbol):
        """Return the LOT_SIZE / PRICE_FILTER / MIN_NOTIONAL data for a symbol.

        Results are cached because exchangeInfo is large and rarely changes
        during a single run.
        """
        symbol = symbol.upper()
        if symbol in self._symbol_filters:
            return self._symbol_filters[symbol]

        info = self._request("GET", "/fapi/v1/exchangeInfo")
        for entry in info.get("symbols", []):
            if entry["symbol"] == symbol:
                filters = {f["filterType"]: f for f in entry["filters"]}
                record = {
                    "status": entry.get("status"),
                    "quantityPrecision": entry.get("quantityPrecision"),
                    "pricePrecision": entry.get("pricePrecision"),
                    "filters": filters,
                }
                self._symbol_filters[symbol] = record
                return record

        return None

    def new_order(self, **params):
        """Place an order. ``params`` map directly to the Binance order fields."""
        log.info("Placing order request: %s", redact(params))
        result = self._request("POST", "/fapi/v1/order", params=params,
                               signed=True)
        # The full order response is the key audit record -- log it in one line.
        log.info("Order response: %s", result)
        return result
