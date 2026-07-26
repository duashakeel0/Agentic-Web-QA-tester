"""Wraps Playwright so the rest of the app can drive a real browser without
every caller needing to touch Playwright's async API directly.
"""

from playwright.async_api import Browser, Page, async_playwright


class BrowserSession:
    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._page = await self._browser.new_page()

    async def goto(self, url: str) -> str:
        if self._page is None:
            raise RuntimeError("Browser session was not started before goto().")
        await self._page.goto(url)
        return await self._page.title()

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
