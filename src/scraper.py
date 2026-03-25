import asyncio
import os

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from src.logger import get_logger

logger = get_logger(__name__)

_LISTING_URL = "https://www.oddschecker.com/football/english/premier-league"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_CLOUDFLARE_SIGNALS = {"cf-mitigated", "cf_clearance", "just a moment"}
_RETRY_WAIT_SECONDS = 30


class ScraperError(Exception):
    """Raised when a page cannot be rendered after retries."""


class Scraper:
    """Manages the Playwright browser lifecycle and page rendering."""

    def __init__(self) -> None:
        self._delay = float(os.environ.get("PAGE_DELAY_SECONDS", 2))
        self._timeout = float(os.environ.get("PAGE_TIMEOUT_SECONDS", 15)) * 1000  # ms
        self._playwright = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> "Scraper":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _new_context(self) -> BrowserContext:
        return await self._browser.new_context(
            user_agent=_USER_AGENT,
            extra_http_headers={
                "Accept-Language": "en-GB,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "text/html,application/xhtml+xml,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )

    def _is_blocked(self, html: str, status: int) -> bool:
        if status in (429, 503):
            return True
        lower = html.lower()
        return any(signal in lower for signal in _CLOUDFLARE_SIGNALS)

    async def _fetch(self, url: str) -> str:
        """Render *url* and return the full HTML. Retries once on block/timeout."""
        await asyncio.sleep(self._delay)

        for attempt in range(2):
            context = await self._new_context()
            page: Page = await context.new_page()
            try:
                try:
                    from playwright_stealth import stealth_async  # type: ignore
                    await stealth_async(page)
                except ImportError:
                    logger.warning("playwright-stealth not available; skipping stealth")

                response = await page.goto(url, timeout=self._timeout, wait_until="networkidle")
                status = response.status if response else 0
                html = await page.content()

                if self._is_blocked(html, status):
                    logger.warning("Blocked response", extra={"url": url, "status": status, "attempt": attempt + 1})
                    if attempt == 0:
                        await asyncio.sleep(_RETRY_WAIT_SECONDS)
                        continue
                    raise ScraperError(f"Blocked after retry: {url} (status {status})")

                return html

            except PlaywrightTimeoutError as exc:
                logger.warning("Page load timeout", extra={"url": url, "attempt": attempt + 1})
                if attempt == 0:
                    await asyncio.sleep(_RETRY_WAIT_SECONDS)
                    continue
                raise ScraperError(f"Timeout after retry: {url}") from exc

            finally:
                await context.close()

        raise ScraperError(f"Failed to fetch: {url}")  # unreachable, but satisfies type checker

    async def fetch_listing_page(self) -> str:
        """Render the Premier League listing page; return full HTML."""
        logger.info("Fetching listing page", extra={"url": _LISTING_URL})
        return await self._fetch(_LISTING_URL)

    async def fetch_odds_page(self, url: str) -> str:
        """Render a match /winner odds page; return full HTML."""
        logger.info("Fetching odds page", extra={"url": url})
        return await self._fetch(url)
