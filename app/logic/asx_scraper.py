import asyncio
# Deferred import of playwright to avoid errors when it's not installed
from bs4 import BeautifulSoup

async def _scrape_process(symbol: str):
    """
    Internal scraping logic that MUST run in a ProactorEventLoop on Windows.
    """
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    url = f"https://www.asx.com.au/markets/etp/{symbol}"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            try:
                await page.wait_for_selector("table.sector-weightings-table", timeout=20000)
            except Exception:
                pass
                
            try:
                await page.wait_for_selector("text='Geographic exposure'", timeout=10000)
            except Exception:
                pass
                
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            sector_breakdown = {}
            market_breakdown = {}
            
            sector_tables = soup.find_all("table", class_="sector-weightings-table")
            for table in sector_tables:
                rows = table.find_all("tr")[1:]
                for row in rows:
                    cols = row.find_all(["td", "th"])
                    if len(cols) >= 3:
                        name = cols[1].text.strip()
                        percent_str = cols[2].text.strip().replace("%", "").replace(",", "")
                        try:
                            val = float(percent_str)
                            if name not in sector_breakdown:
                                sector_breakdown[name] = val
                        except ValueError:
                            pass

            geo_heading = soup.find(lambda tag: tag.name in ["h2", "h3", "h4"] and "Geographic exposure" in tag.text)
            if geo_heading:
                table = geo_heading.find_next("table")
                if table:
                    rows = table.find_all("tr")[1:]
                    for row in rows:
                        cols = row.find_all(["td", "th"])
                        if len(cols) >= 3:
                            name = cols[0].text.strip()
                            percent_str = cols[2].text.strip().replace("%", "").replace(",", "")
                            try:
                                market_breakdown[name] = float(percent_str)
                            except ValueError:
                                pass
                                
            return sector_breakdown, market_breakdown
            
        except Exception as e:
            print(f"Error scraping ASX for {symbol}: {e}")
            return None, None
        finally:
            await browser.close()

def _run_scraper_in_thread(symbol: str):
    """
    Synchronous wrapper to run the async scraper in a dedicated thread with its own loop.
    This bypasses any SelectorEventLoop issues on the main thread.
    """
    import threading
    import sys
    
    result = [None, None]
    def target():
        if sys.platform == 'win32':
            # Ensure this thread uses ProactorEventLoop
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        # asyncio.run creates a new loop and closes it when done
        try:
            result[0], result[1] = asyncio.run(_scrape_process(symbol))
        except Exception as e:
            print(f"Scraper thread failed: {e}")

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    return result[0], result[1]

async def scrape_asx_breakdown(symbol: str):
    """
    Scrapes sector weightings and geographic exposure for an ASX ETP.
    Returns (sector_breakdown, market_breakdown) or (None, None).
    Runs in a separate thread to ensure ProactorEventLoop is used on Windows.
    """
    try:
        import playwright
    except ImportError:
        print("Playwright not installed. Please run 'uv run playwright install chromium'.")
        return None, None

    if symbol.endswith(".AX"):
        symbol = symbol[:-3]

    # Offload to a separate thread to isolate the event loop
    return await asyncio.to_thread(_run_scraper_in_thread, symbol)

if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "VAS"
    s, m = asyncio.run(scrape_asx_breakdown(symbol))
    print(f"Sectors: {s}")
    print(f"Markets: {m}")
