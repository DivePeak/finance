import time
from main import app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import create_engine, SQLModel, Session
from database import get_session
from contextlib import asynccontextmanager
import os
import time

# Use a separate database for testing
sqlite_file_name = "test_database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

# Point the database module to our test engine
import database
database.engine = engine 

import logic.ticker_logic
logic.ticker_logic.engine = engine # ALSO OVERRIDE IN logic module if it imports engine separately

def override_get_session():
    with Session(engine) as session:
        yield session

app.dependency_overrides[get_session] = override_get_session

# Ensure tables are created
SQLModel.metadata.drop_all(engine)
SQLModel.metadata.create_all(engine)

# Override the lifespan to avoid creating tables in the production DB during tests
@asynccontextmanager
async def override_lifespan(app: FastAPI):
    # We already created tables for the test engine above
    yield

app.router.lifespan_context = override_lifespan

client = TestClient(app)

TEST_SYMBOL = "BHP.AX"

from logic.ticker_logic import update_ticker_data

def test_add_ticker():
    # Test adding a dummy ticker
    response = client.post(f"/tickers/{TEST_SYMBOL}")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"]["symbol"] == TEST_SYMBOL
    
    # Background tasks in TestClient (non-async) run immediately if triggered.
    # However, sometimes they don't or yfinance takes too long.
    # Let's call the logic directly to ensure it runs during testing if background fails.
    ticker_obj = update_ticker_data(TEST_SYMBOL)
    print(f"DEBUG: update_ticker_data returned {ticker_obj.symbol if ticker_obj else 'None'}, status: {ticker_obj.breakdown_status if ticker_obj else 'N/A'}")
    
    response = client.get("/tickers")
    assert response.status_code == 200
    tickers = response.json()
    ticker = next((t for t in tickers if t["symbol"] == TEST_SYMBOL), None)
    
    # Check if it was added and has breakdown data
    assert ticker is not None
    assert ticker["symbol"] == TEST_SYMBOL
    
    # BHP.AX is an EQUITY on ASX, so it should have 100% breakdown
    assert ticker["breakdown_status"] == "ok"
    assert ticker["sector_breakdown"] is not None
    assert "Basic Materials" in ticker["sector_breakdown"]
    assert ticker["market_breakdown"] == {"Australia": 100.0}

def test_add_etf_ticker():
    ETF_SYMBOL = TEST_SYMBOL
    response = client.post(f"/tickers/{ETF_SYMBOL}")
    assert response.status_code == 200
    
    update_ticker_data(ETF_SYMBOL)
    
    response = client.get("/tickers")
    tickers = response.json()
    ticker = next((t for t in tickers if t["symbol"] == ETF_SYMBOL), None)
    
    assert ticker is not None
    assert ticker["breakdown_status"] == "missing"

def test_edit_breakdown():
    # We'll use the test symbol which we added in the previous test
    ETF_SYMBOL = TEST_SYMBOL
    
    # Check current status
    response = client.get(f"/tickers/{ETF_SYMBOL}/breakdown")
    assert response.status_code == 200
    assert ETF_SYMBOL in response.text
    
    # Update breakdown
    payload = {
        "sector_name[]": ["Financials", "Technology"],
        "sector_percent[]": [60.0, 40.0],
        "market_name[]": ["Australia"],
        "market_percent[]": [100.0]
    }
    response = client.post(f"/tickers/{ETF_SYMBOL}/breakdown", data=payload, follow_redirects=True)
    assert response.status_code == 200
    
    # Verify changes
    response = client.get("/tickers")
    tickers = response.json()
    ticker = next((t for t in tickers if t["symbol"] == ETF_SYMBOL), None)
    
    assert ticker is not None
    assert ticker["breakdown_status"] == "manual_override"
    assert ticker["sector_breakdown"] == {"Financials": 60.0, "Technology": 40.0}
    assert ticker["market_breakdown"] == {"Australia": 100.0}

def test_scrape_asx_endpoint():
    ETF_SYMBOL = TEST_SYMBOL
    # We'll mock the scraper because we don't want to run a real browser in tests (slow/flaky)
    import logic.asx_scraper
    
    # We must ensure the function is mocked BEFORE the router uses it
    # Since the router already imported it, we mock it in logic.asx_scraper
    
    original_scrape = logic.asx_scraper.scrape_asx_breakdown
    
    async def mock_scrape(symbol):
        return {"Scraped Sector": 100.0}, {"Scraped Market": 100.0}
        
    logic.asx_scraper.scrape_asx_breakdown = mock_scrape
    
    try:
        # Note: We must use the mocked version even if Playwright is not installed
        response = client.post(f"/tickers/{ETF_SYMBOL}/scrape_asx", follow_redirects=True)
        assert response.status_code == 200
        # If the mock is working, we should see the success message
        assert "Data successfully fetched from ASX" in response.text
        assert "Scraped Sector" in response.text
        
        # Verify DB
        response = client.get("/tickers")
        tickers = response.json()
        ticker = next((t for t in tickers if t["symbol"] == ETF_SYMBOL), None)
        assert ticker["sector_breakdown"] == {"Scraped Sector": 100.0}
    finally:
        logic.asx_scraper.scrape_asx_breakdown = original_scrape

def test_view_exposure():
    # Before checking exposure, we need some transactions so there are holdings
    # test_add_ticker only adds the ticker to the DB, not a transaction.
    from models import Transaction, Ticker
    from datetime import date
    with Session(engine) as session:
        # Add a UK stock for "Other" market
        ticker_uk = Ticker(symbol="BP.L", name="BP PLC", market_breakdown={"UK": 100.0}, breakdown_status="ok", current_price=5.0)
        session.add(ticker_uk)
        
        tx1 = Transaction(symbol=TEST_SYMBOL, transaction_date=date.today(), transaction_type="Buy", units=10, price=100.0, amount=-1000.0)
        tx2 = Transaction(symbol="BP.L", transaction_date=date.today(), transaction_type="Buy", units=100, price=5.0, amount=-500.0)
        session.add(tx1)
        session.add(tx2)
        session.commit()

    response = client.get("/portfolio/exposure")
    assert response.status_code == 200
    assert "Portfolio Exposure Breakdown" in response.text
    assert "Sector Breakdown" in response.text
    assert "Market Breakdown" in response.text
    # Now Australia should be there because BHP.AX has 100% Australia market exposure
    assert "Australia" in response.text
    # "Other" should be there because BP.L is in "UK"
    assert "Other" in response.text
    assert "UK" in response.text
    assert "other-market-row" in response.text

def test_holding_row_endpoint():
    """Test the holding row endpoint returns correct HTML"""
    from models import Transaction, Ticker
    from datetime import date
    with Session(engine) as session:
        # Ensure we have a ticker and transaction
        ticker = session.get(Ticker, TEST_SYMBOL)
        if not ticker:
            ticker = Ticker(symbol=TEST_SYMBOL, name="BHP Group", current_price=45.0, breakdown_status="ok")
            session.add(ticker)

        # Add a transaction
        tx = Transaction(symbol=TEST_SYMBOL, transaction_date=date.today(), transaction_type="Buy", units=100, price=40.0, amount=-4000.0, fee=10.0)
        session.add(tx)
        session.commit()

    response = client.get(f"/portfolio/holding/{TEST_SYMBOL}")
    assert response.status_code == 200
    assert TEST_SYMBOL in response.text
    assert "data-symbol" in response.text
    assert "market-value-cell" in response.text

def test_dashboard_endpoint():
    """Test the dashboard endpoint returns correct HTML"""
    response = client.get("/portfolio/dashboard")
    assert response.status_code == 200
    assert "Total Market Value" in response.text
    assert "Total Cost Base" in response.text
    assert "Total Unrealized P/L" in response.text
    assert "Total Portfolio XIRR" in response.text
    assert "Total Realized P/L" in response.text
    assert "Total Dividends" in response.text
    assert "Total Gain" in response.text

def test_websocket_broadcast():
    """Test WebSocket price update broadcasting"""
    import asyncio
    from routers.websocket import broadcast_price_update, active_connections

    # Since we can't easily test WebSocket in TestClient, we'll test the broadcast function
    # Mock a connection
    class MockWebSocket:
        def __init__(self):
            self.messages = []

        async def send_text(self, message):
            self.messages.append(message)

    mock_ws = MockWebSocket()
    active_connections.add(mock_ws)

    try:
        # Broadcast a price update
        asyncio.run(broadcast_price_update("TEST.AX", 123.45))

        # Check the message was sent
        assert len(mock_ws.messages) == 1
        import json
        message = json.loads(mock_ws.messages[0])
        assert message["type"] == "price_update"
        assert message["symbol"] == "TEST.AX"
        assert message["price"] == 123.45
    finally:
        active_connections.discard(mock_ws)

def test_stale_price_background_update():
    """Test that stale prices trigger background updates and WebSocket broadcasts"""
    import asyncio
    from datetime import datetime, timedelta
    from models import Ticker, Transaction
    from routers.websocket import active_connections
    from datetime import date

    # Create a ticker with a stale price
    with Session(engine) as session:
        ticker = Ticker(
            symbol="STALE.AX",
            name="Stale Test",
            current_price=100.0,
            last_updated=datetime.now() - timedelta(hours=2),  # 2 hours old, assuming stale_time is 1 hour
            breakdown_status="ok"
        )
        session.add(ticker)

        # Add a transaction so it shows up in portfolio
        tx = Transaction(
            symbol="STALE.AX",
            transaction_date=date.today(),
            transaction_type="Buy",
            units=10,
            price=100.0,
            amount=-1000.0
        )
        session.add(tx)
        session.commit()

    # Mock WebSocket connection
    class MockWebSocket:
        def __init__(self):
            self.messages = []

        async def send_text(self, message):
            self.messages.append(message)

    mock_ws = MockWebSocket()
    active_connections.add(mock_ws)

    try:
        # Mock the update_ticker_data to avoid actual API call
        import logic.ticker_logic
        original_update = logic.ticker_logic.update_ticker_data

        def mock_update(symbol):
            with Session(engine) as session:
                ticker = session.get(Ticker, symbol)
                if ticker:
                    ticker.current_price = 150.0  # Updated price
                    ticker.last_updated = datetime.now()
                    session.add(ticker)
                    session.commit()
                    session.refresh(ticker)
                return ticker

        logic.ticker_logic.update_ticker_data = mock_update

        try:
            # Call the portfolio endpoint which should trigger background update
            response = client.get("/portfolio/")
            assert response.status_code == 200

            # The background task should have run (TestClient runs them synchronously)
            # But we need to manually trigger it since it's async
            from logic.ticker_logic import check_and_update_ticker
            asyncio.run(check_and_update_ticker("STALE.AX"))

            # Check that WebSocket broadcast was sent
            assert len(mock_ws.messages) >= 1
            import json
            # Find the message for STALE.AX
            stale_messages = [msg for msg in mock_ws.messages if "STALE.AX" in msg]
            assert len(stale_messages) == 1

            message = json.loads(stale_messages[0])
            assert message["type"] == "price_update"
            assert message["symbol"] == "STALE.AX"
            assert message["price"] == 150.0

            # Verify the price was actually updated in DB
            with Session(engine) as session:
                ticker = session.get(Ticker, "STALE.AX")
                assert ticker.current_price == 150.0

        finally:
            logic.ticker_logic.update_ticker_data = original_update

    finally:
        active_connections.discard(mock_ws)
        # Cleanup
        with Session(engine) as session:
            ticker = session.get(Ticker, "STALE.AX")
            if ticker:
                session.delete(ticker)
            session.commit()

def test_delete_ticker():
    # Delete dummy ticker
    response = client.delete(f"/tickers/{TEST_SYMBOL}")
    assert response.status_code == 200

    # Verify deletion
    response = client.get("/tickers")
    tickers = response.json()
    assert not any(t["symbol"] == TEST_SYMBOL for t in tickers)

if __name__ == "__main__":
    # Quick manual run
    try:
        test_add_ticker()
        print("Add ticker test passed")
        test_add_etf_ticker()
        print("Add ETF ticker test passed")
        test_edit_breakdown()
        print("Edit breakdown test passed")
        test_scrape_asx_endpoint()
        print("Scrape ASX endpoint test passed")
        test_view_exposure()
        print("View exposure test passed")
        test_holding_row_endpoint()
        print("Holding row endpoint test passed")
        test_dashboard_endpoint()
        print("Dashboard endpoint test passed")
        test_websocket_broadcast()
        print("WebSocket broadcast test passed")
        test_stale_price_background_update()
        print("Stale price background update test passed")
        test_delete_ticker()
        print("Delete ticker test passed")
    finally:
        # Cleanup
        engine.dispose() # Ensure all connections are closed
        if os.path.exists("test_database.db"):
             try:
                 os.remove("test_database.db")
             except PermissionError:
                 print("Could not remove test_database.db, it might be locked.")
