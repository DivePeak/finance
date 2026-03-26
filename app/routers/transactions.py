from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
from database import get_session
from models import Transaction, Ticker
from datetime import date
import os

from typing import Optional

router = APIRouter()

# Setup templates directory
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"))

def get_cdia_balance(session: Session) -> float:
    # Sum of 'amount' for all transactions
    # SQLite might return None if no transactions exist
    balance = session.exec(select(func.sum(Transaction.amount))).one()
    return float(balance) if balance is not None else 0.0

@router.get("/", response_class=HTMLResponse)
async def list_transactions(request: Request, session: Session = Depends(get_session)):
    transactions = session.exec(select(Transaction).order_by(Transaction.transaction_date.desc(), Transaction.id.desc())).all()
    tickers = session.exec(select(Ticker)).all()
    balance = get_cdia_balance(session)
    return templates.TemplateResponse("transactions.html", {
        "request": request, 
        "transactions": transactions,
        "tickers": tickers,
        "cdia_balance": balance
    })

@router.post("/", response_class=HTMLResponse)
async def add_transaction(
    request: Request,
    transaction_date: date = Form(...),
    transaction_type: str = Form(...),
    symbol: Optional[str] = Form(None),
    units: Optional[float] = Form(None),
    price: Optional[float] = Form(None),
    fee: float = Form(0.0),
    amount: Optional[float] = Form(None),
    session: Session = Depends(get_session)
):
    if symbol:
        symbol = symbol.upper()
        if not symbol.endswith(".AX") and "." not in symbol:
            symbol += ".AX"
        
        # Ensure ticker exists
        ticker = session.get(Ticker, symbol)
        if not ticker:
            new_ticker = Ticker(symbol=symbol)
            session.add(new_ticker)
    else:
        symbol = None
    
    # Auto-calculate amount from units/price for Buy/Sell
    if amount is None:
        if transaction_type == "Buy" and units is not None and price is not None:
            amount = -(units * price + fee)
        elif transaction_type == "Sell" and units is not None and price is not None:
            amount = units * price - fee
        elif transaction_type in ["Reinvestment", "Reinvest"]:
            amount = 0.0

    # Coerce sign based on type — user always enters absolute value
    DEBIT_TYPES  = {"Buy", "Withdrawal"}
    CREDIT_TYPES = {"Sell", "Dividend", "Deposit", "Interest", "Payment"}
    if amount is not None:
        if transaction_type in DEBIT_TYPES:
            amount = -abs(amount)
        elif transaction_type in CREDIT_TYPES:
            amount = abs(amount)
        # Reinvestment (already 0), ADJ: keep as entered

    new_transaction = Transaction(
        symbol=symbol,
        transaction_date=transaction_date,
        transaction_type=transaction_type,
        units=units,
        price=price,
        fee=fee,
        amount=amount
    )
    session.add(new_transaction)
    session.commit()
    session.refresh(new_transaction)
    
    transactions = session.exec(select(Transaction).order_by(Transaction.transaction_date.desc(), Transaction.id.desc())).all()
    balance = get_cdia_balance(session)

    if request.headers.get("hx-request"):
        return templates.TemplateResponse("_transaction_list.html", {
            "request": request, 
            "transactions": transactions,
            "cdia_balance": balance
        })
    
    tickers = session.exec(select(Ticker)).all()
    return templates.TemplateResponse("transactions.html", {
        "request": request, 
        "transactions": transactions,
        "tickers": tickers,
        "cdia_balance": balance
    })

@router.delete("/{transaction_id}/", response_class=HTMLResponse)
async def delete_transaction(
    request: Request,
    transaction_id: int,
    session: Session = Depends(get_session)
):
    transaction = session.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    session.delete(transaction)
    session.commit()
    
    transactions = session.exec(select(Transaction).order_by(Transaction.transaction_date.desc(), Transaction.id.desc())).all()
    balance = get_cdia_balance(session)

    if request.headers.get("hx-request"):
        return templates.TemplateResponse("_transaction_list.html", {
            "request": request, 
            "transactions": transactions,
            "cdia_balance": balance
        })
    
    tickers = session.exec(select(Ticker)).all()
    return templates.TemplateResponse("transactions.html", {
        "request": request, 
        "transactions": transactions,
        "tickers": tickers,
        "cdia_balance": balance
    })
