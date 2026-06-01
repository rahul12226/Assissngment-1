"""Order placement logic.

``OrderManager`` turns validated, exchange-rounded amounts into the exact
parameter set each Binance order type expects and hands it to the client. It is
deliberately thin -- one method per supported order type -- so the CLI reads
clearly and new order types are easy to add.
"""

from .logging_config import get_logger
from .validators import format_decimal

log = get_logger("tradingbot.orders")


class OrderManager:
    def __init__(self, client):
        self.client = client

    def place_market_order(self, symbol, side, quantity):
        """Market order: fills immediately at the best available price."""
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": format_decimal(quantity),
        }
        return self.client.new_order(**params)

    def place_limit_order(self, symbol, side, quantity, price, tif="GTC"):
        """Limit order: rests on the book until price is reached."""
        params = {
            "symbol": symbol,
            "side": side,
            "type": "LIMIT",
            "quantity": format_decimal(quantity),
            "price": format_decimal(price),
            "timeInForce": tif,
        }
        return self.client.new_order(**params)

    def place_stop_limit_order(self, symbol, side, quantity, price, stop_price,
                               tif="GTC"):
        """Stop-limit order: once ``stop_price`` triggers, a limit order at
        ``price`` is placed. This is the bonus third order type."""
        params = {
            "symbol": symbol,
            "side": side,
            "type": "STOP",
            "quantity": format_decimal(quantity),
            "price": format_decimal(price),
            "stopPrice": format_decimal(stop_price),
            "timeInForce": tif,
        }
        return self.client.new_order(**params)
