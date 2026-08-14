"""Wraps Playwright so the rest of the app can drive a real browser without
every caller needing to touch Playwright's async API directly.
"""

import asyncio
import os

from playwright.async_api import Browser, Page, async_playwright

# Normally unset - Playwright auto-locates a matching browser build. Only
# needed when the installed browser cache doesn't match the pinned
# Playwright version exactly (e.g. a CI image or sandbox with a stale
# cache), where plain launch() fails to find the expected executable.
_CHROMIUM_EXECUTABLE_ENV = "PLAYWRIGHT_CHROMIUM_EXECUTABLE"

# A misconfigured environment (wrong event loop policy, missing browser
# binary, broken sandbox) can make Playwright's startup hang with no
# exception at all instead of failing fast - this bounds it so that always
# shows up as a clear, timely error instead of a silent freeze.
STARTUP_TIMEOUT_SECONDS = 30.0


class BrowserSession:
    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    async def start(self) -> None:
        try:
            self._playwright = await asyncio.wait_for(async_playwright().start(), timeout=STARTUP_TIMEOUT_SECONDS)
            launch_kwargs: dict = {"headless": True}
            executable_path = os.environ.get(_CHROMIUM_EXECUTABLE_ENV)
            if executable_path:
                launch_kwargs["executable_path"] = executable_path
            self._browser = await asyncio.wait_for(
                self._playwright.chromium.launch(**launch_kwargs), timeout=STARTUP_TIMEOUT_SECONDS
            )
            self._page = await self._browser.new_page()
            # Playwright auto-dismisses (cancels) any alert/confirm/prompt
            # dialog with no listener - some real sites (e.g. Automation
            # Exercise's Contact Us form) submit via a JS confirm() before
            # proceeding, so an unhandled dialog silently cancels the
            # submission: the click itself still reports success, but the
            # page never reaches its actual result, and a real assertion
            # ends up failing for a reason that has nothing to do with the
            # workflow being wrong. Auto-accepting is the closest match to
            # what a real user clicking "OK" would do.
            self._page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f"Browser failed to start within {STARTUP_TIMEOUT_SECONDS:.0f}s - "
                "check the event loop policy and that a matching browser build is installed."
            ) from exc

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
