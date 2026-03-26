from fastapi import APIRouter, Depends, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from database import get_session
from logic.portfolio_logic import get_portfolio_holdings, Holding, get_portfolio_exposure
from logic.ticker_logic import check_and_update_ticker
from pyxirr import xirr
from datetime import date
import os

router = APIRouter()

# Setup templates directory
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"))

@router.get("/", response_class=HTMLResponse)
async def view_portfolio(request: Request, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    holdings = get_portfolio_holdings(session)

    # Trigger background updates for stale tickers
    for h in holdings:
        if h.is_stale:
            background_tasks.add_task(check_and_update_ticker, h.symbol)

    stats = calculate_dashboard_stats(session)

    return templates.TemplateResponse("portfolio.html", {
        "request": request,
        "holdings": holdings,
        **stats
    })

def calculate_dashboard_stats(session: Session):
    """Calculate all dashboard statistics (extracted for reuse)"""
    holdings = get_portfolio_holdings(session)

    total_market_value = sum(h.market_value for h in holdings)
    total_cost_base = sum(h.cost_base for h in holdings)
    total_realized_pl = sum(h.realized_pl for h in holdings)
    total_dividends = sum(h.total_dividends for h in holdings)

    total_unrealized_pl = total_market_value - total_cost_base
    total_unrealized_pl_pct = (total_unrealized_pl / total_cost_base * 100) if total_cost_base > 0 else 0

    from models import Transaction
    all_tx = session.exec(select(Transaction)).all()

    from routers.transactions import get_cdia_balance
    cdia_balance = get_cdia_balance(session)

    total_cash_flows = []
    for tx in all_tx:
        if tx.transaction_type == "Deposit":
            total_cash_flows.append((tx.transaction_date, -tx.amount))
        elif tx.transaction_type == "Withdrawal":
            total_cash_flows.append((tx.transaction_date, -tx.amount))

    total_contributions = sum(
        tx.amount for tx in all_tx
        if tx.transaction_type == "Deposit" and tx.amount is not None
    )
    total_gain = total_unrealized_pl + total_realized_pl + total_dividends
    total_gain_pct = (total_gain / total_contributions * 100) if total_contributions > 0 else 0

    total_xirr = 0.0
    if total_cash_flows:
        current_total_value = cdia_balance + total_market_value
        cf_with_current = total_cash_flows + [(date.today(), current_total_value)]
        dates, amounts = zip(*cf_with_current)
        try:
            total_xirr = xirr(dates, amounts) or 0.0
        except:
            total_xirr = 0.0

    return {
        "total_market_value": total_market_value,
        "total_cost_base": total_cost_base,
        "total_realized_pl": total_realized_pl,
        "total_dividends": total_dividends,
        "total_unrealized_pl": total_unrealized_pl,
        "total_unrealized_pl_pct": total_unrealized_pl_pct,
        "total_xirr": total_xirr,
        "total_gain": total_gain,
        "total_gain_pct": total_gain_pct
    }

@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, session: Session = Depends(get_session)):
    """Return updated dashboard HTML for real-time updates"""
    stats = calculate_dashboard_stats(session)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        **stats
    })

@router.get("/holding/{symbol}", response_class=HTMLResponse)
async def get_holding_row(request: Request, symbol: str, session: Session = Depends(get_session)):
    """Return a single holding row HTML for real-time updates"""
    holdings = get_portfolio_holdings(session)
    holding = next((h for h in holdings if h.symbol == symbol), None)

    if not holding:
        return HTMLResponse(content="", status_code=404)

    return templates.TemplateResponse("holding_row.html", {
        "request": request,
        "h": holding
    })

@router.get("/exposure", response_class=HTMLResponse)
async def view_exposure(request: Request, session: Session = Depends(get_session)):
    holdings = get_portfolio_holdings(session)
    exposure = get_portfolio_exposure(session, holdings)
    
    # Sort sectors for display
    sorted_sectors = sorted(exposure.sectors.items(), key=lambda x: x[1], reverse=True)
    
    # Process markets: Australia, USA, and Other
    markets_raw = exposure.markets
    aus_val = markets_raw.get("Australia", 0.0)
    us_val = markets_raw.get("USA", 0.0) + markets_raw.get("United States", 0.0)
    
    other_markets = []
    other_total = 0.0
    for m, v in markets_raw.items():
        if m not in ["Australia", "USA", "United States"]:
            other_markets.append((m, v))
            other_total += v
            
    # Sort the "Other" tail
    other_markets.sort(key=lambda x: x[1], reverse=True)
    
    return templates.TemplateResponse("exposure.html", {
        "request": request,
        "sectors": sorted_sectors,
        "aus_val": aus_val,
        "us_val": us_val,
        "other_total": other_total,
        "other_markets": other_markets,
        "total_value": exposure.total_value
    })
