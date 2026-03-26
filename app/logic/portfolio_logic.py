from sqlmodel import Session, select
from models import Transaction, Ticker
from typing import List, Dict
from dataclasses import dataclass
from pyxirr import xirr
from datetime import date, datetime, timedelta
from logic.ticker_logic import get_stale_time

@dataclass
class Holding:
    symbol: str
    name: str
    units: float
    cost_base: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_pl_pct: float
    realized_pl: float = 0.0
    total_dividends: float = 0.0
    is_stale: bool = False
    portfolio: str = "Unassigned"
    xirr: float = 0.0

@dataclass
class ExposureBreakdown:
    sectors: Dict[str, float]  # Name -> Dollar Value
    markets: Dict[str, float]  # Name -> Dollar Value
    total_value: float

def get_portfolio_exposure(session: Session, holdings: List[Holding]) -> ExposureBreakdown:
    tickers = {t.symbol: t for t in session.exec(select(Ticker)).all()}
    
    sector_exposure = {}
    market_exposure = {}
    total_value = 0.0
    
    for h in holdings:
        ticker = tickers.get(h.symbol)
        if not ticker:
            continue
            
        total_value += h.market_value
        
        # Sector aggregation
        if ticker.sector_breakdown:
            for sector, pct in ticker.sector_breakdown.items():
                value = h.market_value * (pct / 100.0)
                sector_exposure[sector] = sector_exposure.get(sector, 0.0) + value
        else:
            # Fallback if no breakdown
            sector_exposure["Unknown"] = sector_exposure.get("Unknown", 0.0) + h.market_value
            
        # Market aggregation
        if ticker.market_breakdown:
            for market, pct in ticker.market_breakdown.items():
                value = h.market_value * (pct / 100.0)
                market_exposure[market] = market_exposure.get(market, 0.0) + value
        else:
            # Fallback if no breakdown
            market_exposure["Unknown"] = market_exposure.get("Unknown", 0.0) + h.market_value
            
    return ExposureBreakdown(
        sectors=sector_exposure,
        markets=market_exposure,
        total_value=total_value
    )

def get_portfolio_holdings(session: Session) -> List[Holding]:
    transactions = session.exec(select(Transaction).order_by(Transaction.transaction_date)).all()
    tickers = {t.symbol: t for t in session.exec(select(Ticker)).all()}
    
    holdings_data = {}
    stale_time = get_stale_time()
    now = datetime.now()
    
    for tx in transactions:
        if not tx.symbol:
            continue
            
        if tx.symbol not in holdings_data:
            ticker = tickers.get(tx.symbol)
            holdings_data[tx.symbol] = {
                "units": 0.0,
                "cost_base": 0.0,
                "realized_pl": 0.0,
                "total_dividends": 0.0,
                "name": ticker.name if ticker else tx.symbol,
                "current_price": ticker.current_price if ticker else 0.0,
                "cash_flows": []
            }
        
        h = holdings_data[tx.symbol]
        
        if tx.transaction_type in ["Dividend", "Payment"]:
            h["total_dividends"] += (tx.amount or 0.0)

        # Cash flow for XIRR: we use the 'amount' field which is already 
        # negative for buys and positive for sells/dividends/payments.
        # But wait, amount is from CDIA perspective.
        # For asset XIRR, we want the asset's perspective? 
        # Usually XIRR is calculated from cash flows OUT of your pocket (+) and INTO your pocket (-)?
        # Actually pyxirr expects: negative for investments (outflow), positive for returns (inflow).
        # Our 'amount' in Transaction is:
        # Buy: amount = -(units * price + fee)  [Negative, good]
        # Sell: amount = (units * price - fee)  [Positive, good]
        # Payment/Dividend: amount = positive   [Positive, good]
        
        if tx.amount is not None:
            h["cash_flows"].append((tx.transaction_date, tx.amount))
        
        if tx.transaction_type == "Buy":
            h["units"] += tx.units
            h["cost_base"] += (tx.units * tx.price + tx.fee)
        elif tx.transaction_type == "Sell":
            # Simple weighted average cost reduction
            if h["units"] > 0:
                avg_cost = h["cost_base"] / h["units"]
                h["cost_base"] -= (tx.units * avg_cost)
                h["realized_pl"] += (tx.amount - (tx.units * avg_cost))
            h["units"] -= tx.units
        elif tx.transaction_type in ["Reinvestment", "Reinvest"]:
            h["units"] += tx.units
            # For reinvestment, the amount is usually 0 in CDIA, 
            # but it adds to cost base of the asset.
            # We use units * price as the cost addition.
            if tx.units is not None and tx.price is not None:
                h["cost_base"] += (tx.units * tx.price)
                # For XIRR, a reinvestment is like a dividend payment immediately followed by a buy.
                # Since it's net 0 cash flow to CDIA, it doesn't affect XIRR if we only look at CDIA flows.
                # However, if we want to treat it as a "virtual" flow:
                # h["cash_flows"].append((tx.transaction_date, -tx.units * tx.price))
                # h["cash_flows"].append((tx.transaction_date, tx.units * tx.price))
                # It cancels out.
                pass

    portfolio = []
    for symbol, data in holdings_data.items():
        if data["units"] <= 0.0001:
            continue
            
        market_value = data["units"] * data["current_price"]
        unrealized_pl = market_value - data["cost_base"]
        unrealized_pl_pct = (unrealized_pl / data["cost_base"] * 100) if data["cost_base"] > 0 else 0
        
        # Calculate XIRR
        asset_xirr = 0.0
        if data["cash_flows"]:
            # Add virtual sell today at current price
            cf_with_current = data["cash_flows"] + [(date.today(), market_value)]
            dates, amounts = zip(*cf_with_current)
            try:
                asset_xirr = xirr(dates, amounts)
                if asset_xirr is None:
                    asset_xirr = 0.0
            except Exception:
                asset_xirr = 0.0
        
        ticker = tickers.get(symbol)
        is_stale = False
        if ticker:
            is_stale = (ticker.last_updated is None or 
                        (now - ticker.last_updated) > timedelta(seconds=stale_time))
                
        portfolio.append(Holding(
            symbol=symbol,
            name=data["name"],
            units=data["units"],
            cost_base=data["cost_base"],
            current_price=data["current_price"],
            market_value=market_value,
            unrealized_pl=unrealized_pl,
            unrealized_pl_pct=unrealized_pl_pct,
            realized_pl=data["realized_pl"],
            total_dividends=data["total_dividends"],
            is_stale=is_stale,
            portfolio=tickers[symbol].portfolio if (symbol in tickers and tickers[symbol].portfolio) else "Unassigned",
            xirr=asset_xirr
        ))
        
    return portfolio
