"""Custom exceptions used across the trading bot.

Keeping these in one place lets the CLI layer catch specific failure types and
show the user a clean message instead of a raw traceback.
"""


class TradingBotError(Exception):
    """Base class for every error this app raises on purpose."""


class ValidationError(TradingBotError):
    """Raised when user input fails a validation check."""


class BinanceAPIError(TradingBotError):
    """Raised when Binance responds with an error payload.

    Binance returns errors as JSON like ``{"code": -2019, "msg": "Margin is
    insufficient."}``. We keep the numeric code and message so callers can react
    to specific cases if they want to.
    """

    def __init__(self, code, msg, status_code=None):
        self.code = code
        self.msg = msg
        self.status_code = status_code
        super().__init__(f"Binance error {code}: {msg}")


class NetworkError(TradingBotError):
    """Raised when the request never reaches Binance (timeout, DNS, etc.)."""
