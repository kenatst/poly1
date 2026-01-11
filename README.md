# Polymarket Anomaly Bot

Python bot for monitoring Polymarket CLOB markets, detecting abnormal volume/churn events, and optionally fading microstructure moves with **strict risk controls**. Alerts are sent to Discord via webhook.

## Safety & Compliance

- **Default mode is simulation** (`TRADING_MODE=simulation`).
- **Live trading only when `TRADING_MODE=live`.**
- **No secrets in the repo.** Use environment variables or `.env` loaded by your process manager.
- **No market manipulation.** The strategy only detects anomalies and applies a conservative fade.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Populate `.env` with real values, **never commit it**.

## Configuration

- `config.yaml` contains all defaults.
- Environment variables override config values. See `.env.example`.

Required inputs (fill via env vars):

```
POLYMARKET_REST_BASE_URL=...
POLYMARKET_WS_URL=...  # optional
POLYMARKET_API_KEY=... # if required
POLYMARKET_API_SECRET=... # if required
POLYMARKET_API_PASSPHRASE=... # if required
WALLET_SIGNER_MODE=external|private_key_env
PRIVATE_KEY=... # only if private_key_env
WALLET_SIGNER_URL=... # required if external signer
WALLET_PUBLIC_KEY=... # optional override for private_key_env
DISCORD_WEBHOOK_URL=...
ALLOWLIST_MARKETS=[...]  # optional, if using a wrapper to parse list
TOP_N_BY_VOLUME=200
```

Risk defaults:

```
MAX_POSITION_PER_MARKET=100
MAX_GLOBAL_EXPOSURE=500
MAX_DAILY_LOSS=50
ORDER_SIZE_DEFAULT=10
ORDER_SIZE_PERCENT_WALLET=0.5  # optional, requires WALLET_BALANCE_OVERRIDE
WALLET_BALANCE_OVERRIDE=1000   # optional
TAKE_PROFIT_BPS=40
STOP_LOSS_BPS=25
TIME_STOP_MIN=10
```

## Run

```bash
python -m src.main
```

To enable live trading:

```bash
TRADING_MODE=live python -m src.main
```

### Live wallet signing

Live trading requires a wallet signer. Choose one:

- **external**: run your own signing service and set `WALLET_SIGNER_URL`. The engine will POST
  `{ "payload": { ... } }` and expects `{ "signature": "...", "public_key": "..." }` in response.
- **private_key_env**: store your private key only in env (`PRIVATE_KEY`) and the bot will sign
  order payloads locally (Ed25519). Do **not** commit private keys to the repo.

### Order sizing (50% of wallet)

If you want each order to be 50% of your wallet, set:

```
ORDER_SIZE_PERCENT_WALLET=0.5
WALLET_BALANCE_OVERRIDE=...  # current wallet balance in quote units
```

This uses the override value until a proper balance endpoint is wired in.

## Backtest

```bash
python -c "from src.backtest.backtest_runner import backtest; print(backtest('data.sqlite', 'MARKET_ID'))"
```

## Project Structure

```
src/config.py
src/data/
src/features/
src/strategy/
src/execution/
src/risk/
src/alerts/
src/backtest/
src/main.py
tests/
```

## Notes

- The Polymarket REST/WS schemas are assumed to be compatible with the configuration you provide.
- Use the `KILL_SWITCH` file in the repo root to halt order placement.
