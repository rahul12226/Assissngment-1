"""Command-line interface for the Binance Futures Testnet trading bot.

Two ways to use it:

  * Flags, for one-shot orders and scripting::

        python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.002

  * Interactive menu, which walks you through each field with validation::

        python cli.py --interactive

The CLI is only the presentation layer: it validates input, asks the ``bot``
package to place the order, and prints the result. All the API work lives in
``bot/``.
"""

import argparse
import logging
import os
import sys

from bot.client import DEFAULT_BASE_URL, BinanceFuturesClient
from bot.exceptions import (
    BinanceAPIError,
    NetworkError,
    TradingBotError,
    ValidationError,
)
from bot.logging_config import get_logger, setup_logging
from bot.orders import OrderManager
from bot import validators as v

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional; env vars still work without it.
    load_dotenv = None

log = get_logger("tradingbot.cli")


# --------------------------------------------------------------------------
# Credentials
# --------------------------------------------------------------------------

def load_credentials():
    """Read API credentials from a .env file or the environment."""
    if load_dotenv:
        load_dotenv()
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    base_url = os.getenv("BINANCE_BASE_URL", DEFAULT_BASE_URL)
    if not api_key or not api_secret:
        raise ValidationError(
            "Missing API credentials. Copy .env.example to .env and fill in your "
            "Binance Futures Testnet BINANCE_API_KEY and BINANCE_API_SECRET."
        )
    return api_key, api_secret, base_url


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------

def print_request_summary(symbol, side, order_type, quantity, price, stop_price,
                          tif):
    print("\n" + "=" * 44)
    print("  ORDER REQUEST")
    print("=" * 44)
    print(f"  Symbol      : {symbol}")
    print(f"  Side        : {side}")
    print(f"  Type        : {order_type}")
    print(f"  Quantity    : {v.format_decimal(quantity)}")
    if price is not None:
        print(f"  Limit price : {v.format_decimal(price)}")
    if stop_price is not None:
        print(f"  Stop price  : {v.format_decimal(stop_price)}")
    if order_type != "MARKET":
        print(f"  TimeInForce : {tif}")
    print("=" * 44)


def print_response(response):
    print("\n" + "=" * 44)
    print("  ORDER RESPONSE")
    print("=" * 44)
    print(f"  Order ID    : {response.get('orderId')}")
    print(f"  Symbol      : {response.get('symbol')}")
    print(f"  Status      : {response.get('status')}")
    print(f"  Side        : {response.get('side')}")
    print(f"  Type        : {response.get('type')}")
    print(f"  Orig Qty    : {response.get('origQty')}")
    print(f"  Executed Qty: {response.get('executedQty')}")
    # avgPrice is '0.00' until something fills; only show it when meaningful.
    avg_price = response.get("avgPrice")
    if avg_price and avg_price not in ("0", "0.0", "0.00"):
        print(f"  Avg Price   : {avg_price}")
    if response.get("price") and response.get("price") != "0":
        print(f"  Price       : {response.get('price')}")
    print("=" * 44)


def confirm(assume_yes):
    """Ask for confirmation, unless told to skip or running non-interactively."""
    if assume_yes or not sys.stdin.isatty():
        return True
    answer = input("\nPlace this order? [y/N]: ").strip().lower()
    return answer in ("y", "yes")


# --------------------------------------------------------------------------
# Core order flow
# --------------------------------------------------------------------------

def place_order(client, *, symbol, side, order_type, quantity, price=None,
                stop_price=None, tif="GTC", assume_yes=False):
    """Validate, confirm and place a single order. Returns the API response."""
    # 1) Basic, network-free validation.
    symbol = v.normalize_symbol(symbol)
    side = v.validate_side(side)
    order_type = v.validate_order_type(order_type)
    quantity = v.validate_quantity(quantity)
    price = v.validate_price(price) if price not in (None, "") else None
    stop_price = (v.validate_price(stop_price, "Stop price")
                  if stop_price not in (None, "") else None)
    v.require_price(order_type, price)
    v.require_stop_price(order_type, stop_price)
    tif = v.validate_tif(tif)

    # 2) Round/validate against the symbol's live exchange filters.
    symbol_info = client.get_symbol_filters(symbol)
    adjusted = v.apply_symbol_filters(symbol, order_type, quantity, price,
                                      stop_price, symbol_info)
    quantity = adjusted["quantity"]
    price = adjusted["price"]
    stop_price = adjusted["stop_price"]

    # 3) Show the user exactly what will be sent.
    print_request_summary(symbol, side, order_type, quantity, price, stop_price,
                          tif)
    if not confirm(assume_yes):
        print("Cancelled. No order was placed.")
        return None

    # 4) Sync the clock and place the order.
    client.sync_time()
    manager = OrderManager(client)
    if order_type == "MARKET":
        response = manager.place_market_order(symbol, side, quantity)
    elif order_type == "LIMIT":
        response = manager.place_limit_order(symbol, side, quantity, price, tif)
    else:  # STOP (stop-limit)
        response = manager.place_stop_limit_order(symbol, side, quantity, price,
                                                  stop_price, tif)

    print_response(response)
    print("\n[OK] Order placed successfully.")
    return response


# --------------------------------------------------------------------------
# Interactive mode
# --------------------------------------------------------------------------

def _prompt(prompt_text, validator, default=None):
    """Prompt until the validator accepts the input. Returns the clean value."""
    while True:
        raw = input(prompt_text).strip()
        if not raw and default is not None:
            raw = default
        try:
            return validator(raw)
        except ValidationError as exc:
            print(f"  -> {exc}")


def _prompt_choice(label, choices):
    options = "/".join(choices)
    while True:
        raw = input(f"{label} ({options}): ").strip().upper()
        if raw in choices:
            return raw
        print(f"  -> Please choose one of: {options}")


def interactive_flow(client):
    print("\n" + "=" * 44)
    print("  Binance Futures Testnet - Interactive Order")
    print("=" * 44)

    symbol = _prompt("Symbol [BTCUSDT]: ", v.normalize_symbol, default="BTCUSDT")
    side = _prompt_choice("Side", ["BUY", "SELL"])
    order_type = _prompt_choice("Order type", ["MARKET", "LIMIT", "STOP"])
    quantity = _prompt("Quantity: ", v.validate_quantity)

    price = None
    stop_price = None
    if order_type in ("LIMIT", "STOP"):
        price = _prompt("Limit price: ", v.validate_price)
    if order_type == "STOP":
        stop_price = _prompt(
            "Stop (trigger) price: ",
            lambda value: v.validate_price(value, "Stop price"),
        )

    tif = "GTC"
    if order_type != "MARKET":
        entered = input("Time in force [GTC]: ").strip() or "GTC"
        tif = v.validate_tif(entered)

    return place_order(
        client,
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        stop_price=stop_price,
        tif=tif,
        assume_yes=False,
    )


# --------------------------------------------------------------------------
# Argument parsing / entry point
# --------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Place orders on the Binance USDT-M Futures Testnet.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python cli.py --symbol BTCUSDT --side BUY --type MARKET "
            "--quantity 0.002\n"
            "  python cli.py --symbol BTCUSDT --side SELL --type LIMIT "
            "--quantity 0.002 --price 70000\n"
            "  python cli.py --symbol BTCUSDT --side BUY --type STOP "
            "--quantity 0.002 --price 72000 --stop-price 71500\n"
            "  python cli.py --interactive\n"
        ),
    )
    parser.add_argument("--symbol", help="Trading pair, e.g. BTCUSDT")
    parser.add_argument("--side", help="BUY or SELL")
    parser.add_argument("--type", dest="order_type",
                        help="MARKET, LIMIT or STOP (stop-limit)")
    parser.add_argument("--quantity", help="Order quantity in the base asset")
    parser.add_argument("--price", help="Limit price (required for LIMIT/STOP)")
    parser.add_argument("--stop-price", dest="stop_price",
                        help="Trigger price (required for STOP)")
    parser.add_argument("--tif", default="GTC",
                        help="Time in force: GTC, IOC, FOK, GTX (default GTC)")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Run the guided interactive menu")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Skip the confirmation prompt")
    return parser


def main(argv=None):
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    # No order flags at all -> fall back to the friendly interactive menu.
    use_interactive = args.interactive or not any(
        [args.symbol, args.side, args.order_type, args.quantity]
    )

    try:
        api_key, api_secret, base_url = load_credentials()
        client = BinanceFuturesClient(api_key, api_secret, base_url)

        if use_interactive:
            interactive_flow(client)
        else:
            place_order(
                client,
                symbol=args.symbol,
                side=args.side,
                order_type=args.order_type,
                quantity=args.quantity,
                price=args.price,
                stop_price=args.stop_price,
                tif=args.tif,
                assume_yes=args.yes,
            )
        return 0

    except ValidationError as exc:
        log.warning("Rejected invalid input: %s", exc)
        print(f"\n[INPUT ERROR] {exc}", file=sys.stderr)
        return 2
    except BinanceAPIError as exc:
        # Already logged at the client layer; just show the user a clean line.
        print(f"\n[API ERROR] {exc.msg} (code {exc.code})", file=sys.stderr)
        return 1
    except NetworkError as exc:
        print(f"\n[NETWORK ERROR] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted. No order was placed.", file=sys.stderr)
        return 130
    except TradingBotError as exc:
        log.error("Unexpected bot error: %s", exc, exc_info=True)
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # last-resort safety net
        log.error("Unhandled error: %s", exc, exc_info=True)
        print(f"\n[UNEXPECTED ERROR] {exc} (see logs/trading_bot.log)",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
