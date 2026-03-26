import sys
import asyncio

if sys.platform == 'win32':
    # Explicitly set the policy to use ProactorEventLoop on Windows
    # This is required for subprocess support (used by Playwright)
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from database import create_db_and_tables
from contextlib import asynccontextmanager
from routers import tickers, transactions, portfolio, settings, websocket
from routers.websocket import active_connections
from fastapi.responses import RedirectResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield
    for ws in list(active_connections):
        await ws.close()

app = FastAPI(lifespan=lifespan)

# Include routers
app.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
app.include_router(tickers.router, prefix="/tickers", tags=["tickers"])
app.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
app.include_router(settings.router, prefix="/settings", tags=["settings"])
app.include_router(websocket.router)

@app.get("/")
async def root():
    return RedirectResponse(url="/portfolio")
