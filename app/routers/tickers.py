from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from database import get_session
from models import Ticker
from logic.ticker_logic import update_ticker_data, check_and_update_ticker, get_stale_time
import logic.asx_scraper
from datetime import datetime
import os
from typing import Optional, List

router = APIRouter()

# Setup templates directory
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"))

def _wants_html(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "text/html" in accept

def _ticker_payload(ticker: Ticker) -> dict:
    return {
        "symbol": ticker.symbol,
        "name": ticker.name,
        "asset_type": ticker.asset_type,
        "current_price": ticker.current_price,
        "breakdown_status": ticker.breakdown_status,
        "sector_breakdown": ticker.sector_breakdown,
        "market_breakdown": ticker.market_breakdown
    }

@router.get("/", response_class=HTMLResponse)
async def list_tickers(request: Request, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    tickers = session.exec(select(Ticker)).all()
    for ticker in tickers:
        background_tasks.add_task(check_and_update_ticker, ticker.symbol)
    
    stale_time = get_stale_time()
    now = datetime.now()
    
    if not request.headers.get("hx-request") and not _wants_html(request):
        return JSONResponse(content=[_ticker_payload(t) for t in tickers])

    return templates.TemplateResponse("tickers.html", {
        "request": request,
        "tickers": tickers,
        "stale_time": stale_time,
        "now": now,
        "missing_breakdowns": [t for t in tickers if t.breakdown_status == "missing"]
    })

@router.post("/", response_class=HTMLResponse)
async def add_ticker(
    request: Request, 
    background_tasks: BackgroundTasks, 
    symbol: str = Form(...), 
    session: Session = Depends(get_session)
):
    symbol = symbol.upper()
    if not symbol.endswith(".AX") and "." not in symbol:
        symbol += ".AX"
    
    db_ticker = session.get(Ticker, symbol)
    if not db_ticker:
        new_ticker = Ticker(symbol=symbol)
        session.add(new_ticker)
        session.commit()
        session.refresh(new_ticker)
        background_tasks.add_task(update_ticker_data, symbol)
    
    tickers = session.exec(select(Ticker)).all()
    # Return partial for HTMX requests to avoid page duplication
    if request.headers.get("hx-request"):
        return templates.TemplateResponse("_ticker_list.html", {
            "request": request, 
            "tickers": tickers,
            "stale_time": get_stale_time(),
            "now": datetime.now()
        })
    if not _wants_html(request):
        return JSONResponse(content={"ticker": _ticker_payload(session.get(Ticker, symbol))})
    return templates.TemplateResponse("tickers.html", {
        "request": request, 
        "tickers": tickers,
        "stale_time": get_stale_time(),
        "now": datetime.now()
    })

@router.post("/{symbol}", response_class=HTMLResponse)
async def add_ticker_by_symbol(
    request: Request,
    symbol: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    symbol = symbol.upper()
    if not symbol.endswith(".AX") and "." not in symbol:
        symbol += ".AX"

    db_ticker = session.get(Ticker, symbol)
    if not db_ticker:
        new_ticker = Ticker(symbol=symbol)
        session.add(new_ticker)
        session.commit()
        session.refresh(new_ticker)
        background_tasks.add_task(update_ticker_data, symbol)

    if not _wants_html(request):
        return JSONResponse(content={"ticker": _ticker_payload(session.get(Ticker, symbol))})

    tickers = session.exec(select(Ticker)).all()
    return templates.TemplateResponse("tickers.html", {
        "request": request,
        "tickers": tickers,
        "stale_time": get_stale_time(),
        "now": datetime.now()
    })

@router.post("/{symbol}/update_portfolio/", response_class=HTMLResponse)
async def update_ticker_portfolio(
    request: Request,
    symbol: str,
    portfolio: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    symbol = symbol.upper()
    ticker = session.get(Ticker, symbol)
    if not ticker:
        raise HTTPException(status_code=404, detail="Ticker not found")
    
    ticker.portfolio = portfolio
    session.add(ticker)
    session.commit()
    
    return HTMLResponse(status_code=204)


@router.delete("/{symbol}", response_class=HTMLResponse)
@router.delete("/{symbol}/", response_class=HTMLResponse)
async def delete_ticker(
    request: Request,
    symbol: str, 
    session: Session = Depends(get_session)
):
    symbol = symbol.upper()
    ticker = session.get(Ticker, symbol)
    if not ticker:
        raise HTTPException(status_code=404, detail="Ticker not found")
    session.delete(ticker)
    session.commit()
    
    tickers = session.exec(select(Ticker)).all()
    # Return partial for HTMX requests to avoid page duplication
    if request.headers.get("hx-request"):
        return templates.TemplateResponse("_ticker_list.html", {
            "request": request, 
            "tickers": tickers,
            "stale_time": get_stale_time(),
            "now": datetime.now()
        })
    if not _wants_html(request):
        return JSONResponse(content={"deleted": symbol})
    return templates.TemplateResponse("tickers.html", {
        "request": request, 
        "tickers": tickers,
        "stale_time": get_stale_time(),
        "now": datetime.now()
    })

@router.get("/{symbol}/breakdown", response_class=HTMLResponse)
async def edit_ticker_breakdown(
    request: Request,
    symbol: str,
    session: Session = Depends(get_session)
):
    symbol = symbol.upper()
    ticker = session.get(Ticker, symbol)
    if not ticker:
        raise HTTPException(status_code=404, detail="Ticker not found")
    
    return templates.TemplateResponse("ticker_edit_breakdown.html", {
        "request": request,
        "ticker": ticker
    })

@router.post("/{symbol}/breakdown", response_class=HTMLResponse)
async def update_ticker_breakdown(
    request: Request,
    symbol: str,
    session: Session = Depends(get_session)
):
    form_data = await request.form()
    sector_names = form_data.getlist("sector_name[]")
    sector_percents = form_data.getlist("sector_percent[]")
    market_names = form_data.getlist("market_name[]")
    market_percents = form_data.getlist("market_percent[]")

    symbol = symbol.upper()
    ticker = session.get(Ticker, symbol)
    if not ticker:
        raise HTTPException(status_code=404, detail="Ticker not found")
    
    # Reconstruct breakdowns
    sector_breakdown = {}
    for name, percent in zip(sector_names, sector_percents):
        name = name.strip()
        if name:
            sector_breakdown[name] = float(percent)
            
    market_breakdown = {}
    for name, percent in zip(market_names, market_percents):
        name = name.strip()
        if name:
            market_breakdown[name] = float(percent)
            
    ticker.sector_breakdown = sector_breakdown
    ticker.market_breakdown = market_breakdown
    ticker.breakdown_status = "manual_override"
    ticker.last_breakdown_update = datetime.now()
    
    session.add(ticker)
    session.commit()
    
    return RedirectResponse(url="/tickers", status_code=303)

@router.post("/{symbol}/scrape_asx", response_class=HTMLResponse)
async def scrape_asx_for_ticker(
    request: Request,
    symbol: str,
    session: Session = Depends(get_session)
):
    symbol = symbol.upper()
    ticker = session.get(Ticker, symbol)
    if not ticker:
        raise HTTPException(status_code=404, detail="Ticker not found")
    
    # For ASX scraping, we usually want the base symbol without .AX
    search_symbol = symbol.upper()
    if search_symbol.endswith(".AX"):
        search_symbol = search_symbol[:-3]
    
    sector, market = await logic.asx_scraper.scrape_asx_breakdown(search_symbol)
    
    if sector is not None and market is not None:
        ticker.sector_breakdown = sector
        ticker.market_breakdown = market
        ticker.breakdown_status = "ok" # Or maybe stay as 'ok' if scraped successfully
        ticker.last_breakdown_update = datetime.now()
        session.add(ticker)
        session.commit()
        session.refresh(ticker)
    
    # Return to the edit page which will now show the scraped data
    return templates.TemplateResponse("ticker_edit_breakdown.html", {
        "request": request,
        "ticker": ticker,
        "scraped": True if sector is not None else False
    })
