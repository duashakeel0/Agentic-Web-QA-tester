"""Wraps Playwright so the rest of the app can drive a real browser without
every caller needing to touch Playwright's async API directly.
"""

import os

from playwright.async_api import Browser, Page, async_playwright

# Normally unset - Playwright auto-locates a matching browser build. Only
# needed when the installed browser cache doesn't match the pinned
# Playwright version exactly (e.g. a CI image or sandbox with a stale
# cache), where plain launch() fails to find the expected executable.
_CHROMIUM_EXECUTABLE_ENV = "PLAYWRIGHT_CHROMIUM_EXECUTABLE"


class BrowserSession:
    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        launch_kwargs: dict = {"headless": True}
        executable_path = os.environ.get(_CHROMIUM_EXECUTABLE_ENV)
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        self._page = await self._browser.new_page()

    async def goto(self, url: str) -> str:
        if self._page is None:
            raise RuntimeError("Browser session was not started before goto().")
        # "domcontentloaded" fires once the page's HTML is parsed, rather
        # than waiting for every last subresource (ads, trackers, fonts) to
        # finish - many real-world sites never cleanly hit the "load" event
        # at all, which was timing out real, working pages.
        await self._page.goto(url, wait_until="domcontentloaded", timeout=45000)
        return await self._page.title()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser session was not started.")
        return self._page

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
