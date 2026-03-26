# Finance Tracker

A personal investment portfolio tracker for ASX (Australian Securities Exchange) assets. Tracks holdings, transactions, performance, and sector/market exposure across a portfolio.

> **Personal use only.** This project uses [yfinance](https://github.com/ranaroussi/yfinance) to retrieve market data from Yahoo Finance. Yahoo Finance's [Terms of Service](https://legal.yahoo.com/us/en/yahoo/terms/osd/index.html) prohibit commercial use of their data. This tool is intended for personal portfolio tracking only and should not be used for any commercial purpose.

## Features

- **Portfolio dashboard** — current holdings, market value, cost base, unrealised P&L, XIRR
- **Transaction log** — buy, sell, dividend, deposit, withdrawal, and more
- **Exposure breakdown** — sector and geographic exposure aggregated across all holdings
- **Live prices** — fetched via yfinance, pushed to the browser over WebSocket
- **ASX breakdown scraper** — scrapes sector/market weightings for ETFs from the ASX website
- **Manual breakdown override** — edit sector/market splits for any ticker

## Tech stack

- **[FastAPI](https://fastapi.tiangolo.com/)** — async web framework
- **[SQLModel](https://sqlmodel.tiangolo.com/)** — ORM (SQLAlchemy + Pydantic)
- **[SQLite](https://www.sqlite.org/)** — database
- **[HTMX](https://htmx.org/)** — dynamic page updates without a JS framework
- **[Bulma](https://bulma.io/)** — CSS framework
- **[Playwright](https://playwright.dev/python/)** — headless Chromium for ASX scraping
- **[uv](https://docs.astral.sh/uv/)** — package manager

## Project structure

```
finance/
├── app/                    # Application source (the only thing that goes in the container)
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── config.cfg
│   ├── routers/            # FastAPI route handlers
│   ├── logic/              # Business logic (portfolio calculations, scraping)
│   └── templates/          # Jinja2 HTML templates
├── deploy/
│   ├── finance.container   # Podman Quadlet systemd unit
│   └── README.md           # Deployment instructions
├── Containerfile           # Container image definition (linux/arm64)
├── data.csv                # Example import file
├── import_csv.py           # One-off CSV import utility
├── test_app.py             # Test suite
└── pyproject.toml
```

## Getting started

**Prerequisites:** Python 3.14+, [uv](https://docs.astral.sh/uv/getting-started/installation/)

```bash
git clone <repo-url>
cd finance
uv sync
uv run playwright install chromium
```

Start the dev server:

```bash
dev        # Windows — runs uvicorn on http://localhost:8003
```

Or directly:

```bash
uv run uvicorn main:app --app-dir app --port 8003 --reload
```

## Importing transactions

A CSV importer is included. See `data.csv` for the expected format:

```
Date,Credit,Debit,Balance,Transaction,Name,Symbol,Units,Price,Fee
01/01/2024,1000,,1000,Deposit,,,,,
02/01/2024,,568.12,431.88,Buy,Vanguard Australian Shares,VAS.AX,6,93.02,10
```

```bash
uv run python import_csv.py
```

## Running tests

```bash
uv run pytest
```

## Deployment

The app is containerised and deployed to a Raspberry Pi (aarch64) via Docker Hub and Podman Quadlet. See [`deploy/README.md`](deploy/README.md) for full instructions.

## Configuration

`app/config.cfg` controls the price cache staleness:

```ini
[cache]
stale_time_seconds = 3600
```

This can also be changed at runtime via the Settings page.
