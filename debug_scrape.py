"""One-shot script to dump the raw HTML from the listing page for inspection."""
import asyncio
from src.scraper import Scraper

async def main():
    async with Scraper() as scraper:
        html = await scraper.fetch_listing_page()
    with open("debug_listing.html", "w") as f:
        f.write(html)
    print(f"Written {len(html)} chars to debug_listing.html")

asyncio.run(main())
