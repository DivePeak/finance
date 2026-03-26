import csv
from datetime import datetime
from sqlmodel import Session, create_engine, select
from models import Ticker, Transaction
from database import sqlite_url, engine
import os

def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%d/%m/%Y").date()
    except ValueError:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            # Try parsing with single digit day/month if necessary, 
            # though %d and %m usually handle it if zero-padded or not depending on platform
            # In data.csv we see 9/10/2023
            parts = date_str.split('/')
            if len(parts) == 3:
                return datetime(int(parts[2]), int(parts[1]), int(parts[0])).date()
            return None

def import_csv():
    if not os.path.exists("data.csv"):
        print("data.csv not found")
        return

    from models import SQLModel
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        with open("data.csv", mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row["Symbol"].strip().upper()
                if symbol:
                    if not symbol.endswith(".AX") and "." not in symbol:
                        symbol += ".AX"
                    
                    # Ensure Ticker exists
                    ticker = session.get(Ticker, symbol)
                    if not ticker:
                        ticker = Ticker(symbol=symbol, name=row["Name"].strip() or None)
                        session.add(ticker)
                        session.commit()
                        session.refresh(ticker)
                else:
                    symbol = None

                trans_date = parse_date(row["Date"])
                trans_type = row["Transaction"].strip()
                
                credit = float(row["Credit"]) if row["Credit"] else 0.0
                debit = float(row["Debit"]) if row["Debit"] else 0.0
                
                # amount: credit is positive cash flow, debit is negative cash flow
                amount = credit - debit if (credit or debit) else None
                
                units = float(row["Units"]) if row["Units"] else None
                price = float(row["Price"]) if row["Price"] else None
                fee = float(row["Fee"]) if row["Fee"] else 0.0
                
                transaction = Transaction(
                    symbol=symbol,
                    transaction_date=trans_date,
                    transaction_type=trans_type,
                    units=units,
                    price=price,
                    fee=fee,
                    amount=amount
                )
                session.add(transaction)
            
            session.commit()
            print("Import completed successfully")

if __name__ == "__main__":
    import_csv()
