# Binance Futures Testnet Trading Bot

A small command-line trading bot for the **Binance USDT-M Futures Testnet**. It
places **Market**, **Limit** and **Stop-Limit** orders, validates your input
against the exchange's own rules, and logs every request, response and error to a
file so you can see exactly what happened.

It talks to the testnet with plain signed REST calls (`requests` + HMAC-SHA256) —
no third-party Binance SDK — so there's nothing hidden and it runs anywhere
Python does.

> **Note on the testnet endpoint.** Binance migrated the futures testnet: the old
> `testnet.binancefuture.com` site now redirects to **demo.binance.com** ("Demo
> Trading"), whose futures API base is **`https://demo-fapi.binance.com`**. Both
> share the same `/fapi` API, so the bot works with either — the base URL is set
> in `.env`. The sample logs in this repo were captured against
> `demo-fapi.binance.com`.

---

## Features

- Market, Limit **and** Stop-Limit (bonus third order type) orders
- Both sides: **BUY** and **SELL**
- Two ways to drive it:
  - **flags** for one-shot / scriptable orders
  - an **interactive menu** that prompts for each field with validation (bonus)
- Input validation *before* anything is sent — symbol, side, type, quantity,
  price — plus rounding to the symbol's real step size / tick size and a
  minimum-notional check, so you don't get cryptic exchange rejections
- Clear terminal output: a request summary, the parsed response
  (`orderId`, `status`, `executedQty`, `avgPrice`), and a success/failure line
- File logging of API requests, responses and errors (secrets are redacted)
- Layered code: API client, order logic, validation, logging and CLI are
  separate and reusable

---

## Project structure

```
PrimeTrade-Ai/
├── bot/
│   ├── __init__.py
│   ├── client.py          # BinanceFuturesClient — signed REST wrapper
│   ├── orders.py          # OrderManager — market / limit / stop-limit
│   ├── validators.py      # input validation + exchange-filter rounding
│   ├── logging_config.py  # rotating file logging + secret redaction
│   └── exceptions.py      # ValidationError / BinanceAPIError / NetworkError
├── cli.py                 # CLI entry point (flags + interactive menu)
├── requirements.txt
├── .env.example           # template for your API keys
├── .gitignore
├── logs/                  # log files land here (created on first run)
└── README.md
```

---

## Setup

### 1. Get Binance Futures Testnet API keys

1. Go to **https://demo.binance.com** (Demo Trading — fake funds, separate from
   real Binance). The old `https://testnet.binancefuture.com` also works if it's
   reachable for you; it now redirects here.
2. Open **Account → API Management** and create an HMAC key, or use the **API
   Key** panel on the futures page.
3. Copy the **API Key** and **Secret Key** with the *Copy* buttons. The demo
   account is pre-funded with mock USDT, which is enough to place the test orders.

### 2. Install

```bash
# from the project folder
python -m pip install -r requirements.txt
```

Requires Python 3.9+ (developed and tested on Python 3.14).

### 3. Add your credentials

Copy the example file and fill in your keys:

```bash
cp .env.example .env
```

```
BINANCE_API_KEY=your_testnet_api_key
BINANCE_API_SECRET=your_testnet_api_secret
# demo.binance.com -> https://demo-fapi.binance.com
# classic testnet  -> https://testnet.binancefuture.com
BINANCE_BASE_URL=https://demo-fapi.binance.com
```

`.env` is gitignored, so your keys won't be committed.

---

## Usage

### Flag mode

```bash
# Market BUY
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.002

# Limit SELL (rests on the book until price is hit)
python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.002 --price 70000

# Stop-Limit BUY (triggers at --stop-price, then places a limit at --price)
python cli.py --symbol BTCUSDT --side BUY --type STOP --quantity 0.002 --price 72000 --stop-price 71500
```

Add `-y` / `--yes` to skip the confirmation prompt.

| Flag | Meaning | Required |
|------|---------|----------|
| `--symbol` | Trading pair, e.g. `BTCUSDT` | yes |
| `--side` | `BUY` or `SELL` | yes |
| `--type` | `MARKET`, `LIMIT` or `STOP` | yes |
| `--quantity` | Order size in the base asset | yes |
| `--price` | Limit price | for `LIMIT` and `STOP` |
| `--stop-price` | Trigger price | for `STOP` |
| `--tif` | Time in force: `GTC`/`IOC`/`FOK`/`GTX` (default `GTC`) | no |
| `-y`, `--yes` | Skip the confirmation prompt | no |
| `-i`, `--interactive` | Launch the interactive menu | no |

### Interactive mode

Run with no order flags (or pass `--interactive`) and the bot walks you through
each field, re-prompting on bad input:

```bash
python cli.py --interactive
```

```
============================================
  Binance Futures Testnet - Interactive Order
============================================
Symbol [BTCUSDT]: BTCUSDT
Side (BUY/SELL): BUY
Order type (MARKET/LIMIT/STOP): MARKET
Quantity: 0.002
```

### Example output

```
============================================
  ORDER REQUEST
============================================
  Symbol      : BTCUSDT
  Side        : BUY
  Type        : MARKET
  Quantity    : 0.002
============================================

============================================
  ORDER RESPONSE
============================================
  Order ID    : 4012345678
  Symbol      : BTCUSDT
  Status      : FILLED
  Side        : BUY
  Type        : MARKET
  Orig Qty    : 0.002
  Executed Qty: 0.002
  Avg Price   : 67250.10
============================================

[OK] Order placed successfully.
```

---

## Logging

Everything is written to `logs/trading_bot.log` (a rotating file handler, 1 MB ×
3 backups). The log captures:

- each outgoing request (method, path, parameters)
- the order request and the full order response
- API errors (Binance code + message) and network errors

Real captured examples are committed in this repo:
- [`logs/sample_market_order.log`](logs/sample_market_order.log) — a filled MARKET order
- [`logs/sample_limit_order.log`](logs/sample_limit_order.log) — a resting LIMIT order

The API secret and the request signature are **never** logged — they're redacted
before the parameters are written. The terminal stays clean (the CLI prints its
own summaries); the file is the full audit trail.

Sample log line for a placed order:

```
2026-06-01 12:48:16 | INFO | tradingbot.client | Placing order request: {'symbol': 'BTCUSDT', 'side': 'BUY', 'type': 'MARKET', 'quantity': '0.002'}
2026-06-01 12:48:16 | DEBUG | tradingbot.client | Request POST /fapi/v1/order params={..., 'signature': '***redacted***'}
2026-06-01 12:48:17 | INFO | tradingbot.client | Order response: {'orderId': 4012345678, 'status': 'FILLED', ...}
```

---

## Error handling

The bot distinguishes three failure types and exits with a matching code:

| Situation | Message | Exit code |
|-----------|---------|-----------|
| Bad user input (e.g. missing price on a LIMIT order, quantity below the minimum) | `[INPUT ERROR] ...` | 2 |
| Binance rejected the order (e.g. insufficient margin, invalid key) | `[API ERROR] ... (code -xxxx)` | 1 |
| Couldn't reach the API (timeout, DNS) | `[NETWORK ERROR] ...` | 1 |

Full details (including tracebacks for anything unexpected) go to the log file.

---

## Assumptions

- Targets the **USDT-M Futures Testnet** only (`/fapi/v1`), not spot or the
  production exchange.
- The account is in **one-way** position mode (the default). Hedge mode would
  need an extra `positionSide` parameter.
- Quantity is snapped **down** to the lot step size, and price is rounded to the
  nearest tick, so the values sent always satisfy the exchange filters. The
  minimum-notional check uses the limit price; for market orders the exchange
  validates notional on its side (BTCUSDT requires roughly 0.002 BTC to clear
  the 50 USDT minimum at current prices).
- Market orders are re-queried once after placement so the output shows the
  actual fill (`FILLED` + average price), since the demo endpoint acknowledges
  them as `NEW` and fills a moment later.
- **Stop-Limit (`STOP`)**: implemented against the standard `/fapi/v1/order`
  endpoint, which is how the classic testnet handles it. The newer
  `demo-fapi.binance.com` endpoint rejects conditional orders here with
  `-4120` ("use the Algo Order API endpoints instead"); the bot surfaces that
  cleanly. Market and Limit (the required types) work on both endpoints.
- `python-binance` is intentionally not used — direct REST keeps dependencies
  minimal and the signing logic transparent.

---

## Quick troubleshooting

- **`Missing API credentials`** — you haven't created `.env` (copy it from
  `.env.example`) or the values are blank.
- **`API-key format invalid` (-2014) / `Invalid API-key` (-2015)** — the key in
  `.env` is wrong, or it doesn't match the `BINANCE_BASE_URL` you set. A
  `demo.binance.com` key only works with `https://demo-fapi.binance.com`, and a
  classic-testnet key only with `https://testnet.binancefuture.com`. (`-2015`
  can also mean an IP restriction is set on the key.)
- **`Timestamp ... ahead of the server`** — the bot syncs to the server clock
  automatically before each order, but a wildly wrong system clock can still trip
  this; fix your machine's time.
