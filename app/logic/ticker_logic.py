import yfinance as yf
from datetime import datetime, timedelta
from models import Ticker
from sqlmodel import Session
import configparser
import os

from database import engine

def get_stale_time():
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.cfg')
    if os.path.exists(config_path):
        config.read(config_path)
        return int(config.get('cache', 'stale_time_seconds', fallback=3600))
    return 3600

def update_ticker_data(symbol: str):
    ticker_data = yf.Ticker(symbol)
    
    # yfinance info can be unreliable for some ASX tickers (e.g. PMGOLD.AX)
    # We use multiple sources to get the most accurate data
    info = {}
    try:
        info = ticker_data.info
    except Exception:
        pass

    fast_info = {}
    try:
        # fast_info is a newer and often more reliable source for current price
        fi = ticker_data.fast_info
        fast_info = {k: fi[k] for k in fi.keys()}
    except Exception:
        pass
    
    with Session(engine) as session:
        ticker = session.get(Ticker, symbol)
        if ticker:
            ticker.name = info.get('longName') or info.get('shortName') or fast_info.get('name')
            
            # Price logic: prefer fast_info, then info, then history
            price = fast_info.get('lastPrice') or info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose')
            
            # Verification/Fallback with history
            try:
                # Some tickers fail with period='1d' but work with '5d'
                hist = ticker_data.history(period='5d')
                if not hist.empty:
                    hist_price = hist['Close'].iloc[-1]
                    # If current price is missing or significantly different from history, prefer history
                    if not price or (hist_price and abs(price - hist_price) / hist_price > 0.1):
                        price = hist_price
            except Exception:
                pass

            ticker.current_price = price
            
            # Asset Type: Check if it's an ETP (common for gold/commodities on ASX)
            asset_type = info.get('quoteType') or fast_info.get('quoteType')
            if symbol == "PMGOLD.AX":
                asset_type = "ETP"
            elif asset_type == "ETF" and "GOLD" in symbol:
                # Many gold-backed products are technically ETPs/ETCs
                asset_type = "ETP"
            
            ticker.asset_type = asset_type
            ticker.currency = info.get('currency') or fast_info.get('currency') or 'AUD'
            ticker.last_updated = datetime.now()

            # --- Handle Sector/Market Breakdown ---
            # Only update if status is 'missing' or 'ok' (don't overwrite 'manual_override')
            if ticker.breakdown_status != "manual_override":
                sector = info.get('sector')
                exchange = info.get('exchange')

                # Mapping common exchange codes to regions
                market_map = {
                    'ASX': 'Australia',
                    'NYQ': 'USA',
                    'NMS': 'USA',
                    'NGM': 'USA',
                    'NCM': 'USA',
                    'PNK': 'USA',
                    'BTS': 'Other',
                }
                market = market_map.get(exchange, 'Other')
                if not exchange and symbol.endswith('.AX'):
                    market = 'Australia'

                # If it's a single stock (EQUITY), we can set 100% exposure
                if asset_type == 'EQUITY' and sector:
                    ticker.sector_breakdown = {sector: 100.0}
                    ticker.market_breakdown = {market: 100.0}
                    ticker.breakdown_status = "ok"
                    ticker.last_breakdown_update = datetime.now()
                elif asset_type == 'ETF':
                    # For ETFs, yfinance.info often lacks full breakdown.
                    # We mark as missing to trigger manual review/fetch
                    # But we can try to get the primary sector if available
                    if sector:
                         ticker.sector_breakdown = {sector: 100.0} # Placeholder
                    
                    ticker.breakdown_status = "missing"
                else:
                    ticker.breakdown_status = "missing"

            session.add(ticker)
            session.commit()
            session.refresh(ticker)
        return ticker

async def check_and_update_ticker(symbol: str):
    with Session(engine) as session:
        ticker = session.get(Ticker, symbol)
        if not ticker:
            return None

        stale_time = get_stale_time()
        is_stale = (ticker.last_updated is None or
                    (datetime.now() - ticker.last_updated) > timedelta(seconds=stale_time))

        if is_stale:
            # We call update_ticker_data which also opens its own session
            # This is fine for a background task.
            pass
        else:
            return ticker

    if is_stale:
        updated_ticker = update_ticker_data(symbol)

        # Broadcast the price update via WebSocket
        if updated_ticker and updated_ticker.current_price:
            try:
                from routers.websocket import broadcast_price_update
                await broadcast_price_update(symbol, updated_ticker.current_price)
            except Exception:
                pass  # Don't fail if WebSocket broadcast fails

        return updated_ticker
    return None
