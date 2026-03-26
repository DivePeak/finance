from datetime import datetime, date
from typing import Optional, Dict
from sqlmodel import SQLModel, Field, Column, JSON

class Ticker(SQLModel, table=True):
    # Symbol is the primary key and the only mandatory field
    symbol: str = Field(primary_key=True, index=True)
    
    # All other fields are optional (nullable in the database)
    name: Optional[str] = Field(default=None)
    asset_type: Optional[str] = Field(default=None)
    portfolio: Optional[str] = Field(default=None)
    current_price: Optional[float] = Field(default=None)
    currency: Optional[str] = Field(default="AUD")
    last_updated: Optional[datetime] = Field(default=None)

    # Sector and Market exposure tracking
    # Store as Dict[str, float] e.g. {"Technology": 33.5, "Finance": 12.0}
    sector_breakdown: Optional[Dict[str, float]] = Field(default=None, sa_column=Column(JSON))
    market_breakdown: Optional[Dict[str, float]] = Field(default=None, sa_column=Column(JSON))
    
    # Status to track if breakdown data is complete or needs manual entry
    # "ok", "missing", "manual_override"
    breakdown_status: Optional[str] = Field(default="missing")
    last_breakdown_update: Optional[datetime] = Field(default=None)

class Transaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: Optional[str] = Field(default=None, foreign_key="ticker.symbol")
    transaction_date: date
    transaction_type: str  # Buy, Sell, Dividend, Reinvestment, Deposit, Withdrawal, Interest, Payment, ADJ
    units: Optional[float] = Field(default=None)
    price: Optional[float] = Field(default=None)
    fee: float = Field(default=0.0)
    amount: Optional[float] = Field(default=None)  # Total cash impact for the transaction
