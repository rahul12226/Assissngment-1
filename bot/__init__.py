"""Simplified Binance Futures Testnet trading bot.

Layers:
    client.py      -- signed REST calls to the testnet
    orders.py      -- build and place market / limit / stop-limit orders
    validators.py  -- validate and round user input against exchange rules
    logging_config -- file + console logging
    exceptions     -- the error types the CLI catches
"""

from .client import BinanceFuturesClient
from .orders import OrderManager

__all__ = ["BinanceFuturesClient", "OrderManager"]
__version__ = "1.0.0"
