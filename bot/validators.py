"""Input validation and exchange-filter helpers.

These are plain functions that raise ``ValidationError`` with a human-readable
message when something is wrong. The basic checks (side, type, positive numbers)
need no network access; the filter checks take the symbol's exchange rules and
make sure the quantity/price respect Binance's step size, tick size and minimum
notional before we send anything.
"""

from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP

from .exceptions import ValidationError

VALID_SIDES = ("BUY", "SELL")
VALID_TYPES = ("MARKET", "LIMIT", "STOP")
VALID_TIF = ("GTC", "IOC", "FOK", "GTX")

# Order types that require a limit price / a trigger (stop) price.
TYPES_NEEDING_PRICE = ("LIMIT", "STOP")
TYPES_NEEDING_STOP = ("STOP",)


def normalize_symbol(symbol):
    if not symbol or not symbol.strip():
        raise ValidationError("Symbol is required (e.g. BTCUSDT).")
    return symbol.strip().upper()


def validate_side(side):
    if not side:
        raise ValidationError("Side is required: BUY or SELL.")
    side = side.strip().upper()
    if side not in VALID_SIDES:
        raise ValidationError(f"Side must be BUY or SELL, got '{side}'.")
    return side


def validate_order_type(order_type):
    if not order_type:
        raise ValidationError("Order type is required: MARKET, LIMIT or STOP.")
    value = order_type.strip().upper().replace("-", "_")
    # Accept a few friendly aliases for the stop-limit type.
    if value in ("STOP", "STOP_LIMIT", "STOPLIMIT"):
        return "STOP"
    if value in VALID_TYPES:
        return value
    raise ValidationError(
        f"Order type must be MARKET, LIMIT or STOP, got '{order_type}'."
    )


def validate_tif(tif):
    if not tif:
        return "GTC"
    tif = tif.strip().upper()
    if tif not in VALID_TIF:
        raise ValidationError(
            f"timeInForce must be one of {', '.join(VALID_TIF)}, got '{tif}'."
        )
    return tif


def parse_decimal(value, field):
    """Convert user input to a Decimal or raise a clear error."""
    if value is None or str(value).strip() == "":
        raise ValidationError(f"{field} is required.")
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValidationError(f"{field} must be a number, got '{value}'.")


def validate_quantity(quantity):
    qty = parse_decimal(quantity, "Quantity")
    if qty <= 0:
        raise ValidationError(f"Quantity must be greater than 0, got {qty}.")
    return qty


def validate_price(price, field="Price"):
    value = parse_decimal(price, field)
    if value <= 0:
        raise ValidationError(f"{field} must be greater than 0, got {value}.")
    return value


def require_price(order_type, price):
    """LIMIT and STOP orders need a limit price; MARKET must not have one."""
    if order_type in TYPES_NEEDING_PRICE and price is None:
        raise ValidationError(f"A price is required for {order_type} orders.")
    if order_type == "MARKET" and price is not None:
        raise ValidationError("MARKET orders must not include a price.")


def require_stop_price(order_type, stop_price):
    if order_type in TYPES_NEEDING_STOP and stop_price is None:
        raise ValidationError(
            "A stop (trigger) price is required for STOP orders."
        )


# -- exchange-filter aware checks -----------------------------------------

def _round_to_step(value, step, rounding):
    step = Decimal(str(step))
    if step == 0:
        return value
    steps = (value / step).to_integral_value(rounding=rounding)
    return (steps * step).quantize(step, rounding=rounding)


def format_decimal(value):
    """Render a Decimal as a plain (non-scientific) string for the API."""
    return format(value.normalize(), "f")


def apply_symbol_filters(symbol, order_type, quantity, price, stop_price,
                         symbol_info):
    """Validate and round amounts against a symbol's exchange filters.

    ``symbol_info`` is the dict returned by ``client.get_symbol_filters``. Returns
    a dict with the adjusted Decimal values. Raises ``ValidationError`` if the
    symbol is unknown/halted or an amount can't be made valid.
    """
    if symbol_info is None:
        raise ValidationError(
            f"Unknown symbol '{symbol}'. Check it exists on the futures testnet."
        )
    if symbol_info.get("status") != "TRADING":
        raise ValidationError(
            f"Symbol '{symbol}' is not currently trading "
            f"(status={symbol_info.get('status')})."
        )

    filters = symbol_info["filters"]
    adjusted = {"quantity": quantity, "price": price, "stop_price": stop_price}

    # Quantity: snap down to the lot step, then enforce the minimum.
    lot = filters.get("LOT_SIZE")
    if lot:
        step = Decimal(lot["stepSize"])
        min_qty = Decimal(lot["minQty"])
        adjusted["quantity"] = _round_to_step(quantity, step, ROUND_DOWN)
        if adjusted["quantity"] < min_qty:
            raise ValidationError(
                f"Quantity {format_decimal(quantity)} is below the minimum "
                f"of {format_decimal(min_qty)} for {symbol}."
            )

    price_filter = filters.get("PRICE_FILTER")
    if price_filter:
        tick = Decimal(price_filter["tickSize"])
        if price is not None:
            adjusted["price"] = _round_to_step(price, tick, ROUND_HALF_UP)
        if stop_price is not None:
            adjusted["stop_price"] = _round_to_step(stop_price, tick,
                                                    ROUND_HALF_UP)

    # Minimum notional only makes sense when we know the price (LIMIT / STOP).
    notional = filters.get("MIN_NOTIONAL")
    if notional and adjusted["price"] is not None:
        min_notional = Decimal(notional["notional"])
        order_value = adjusted["quantity"] * adjusted["price"]
        if order_value < min_notional:
            raise ValidationError(
                f"Order notional {format_decimal(order_value)} USDT is below the "
                f"minimum of {format_decimal(min_notional)} USDT. Increase the "
                f"quantity or price."
            )

    return adjusted
