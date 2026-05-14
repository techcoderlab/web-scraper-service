# ── Pillar 3: Async browser pool — N contexts, non-blocking lifecycle ────────
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from playwright.async_api import (
    async_playwright, Browser, BrowserContext, Playwright,
)
from playwright_stealth import Stealth

from infrastructure.logging_config import get_logger
from application.config import Settings

log = get_logger(__name__)


@dataclass
class _PoolSlot:
    context: BrowserContext
    in_use:  bool = False


class BrowserPool:
    """Fixed-size pool of stealth Playwright contexts."""

    def __init__(self, settings: Settings) -> None:
        self._settings   = settings
        self._pw: Playwright | None    = None
        self._browser: Browser | None = None
        self._slots: list[_PoolSlot]   = []
        self._lock = asyncio.Lock()
        self._semaphore: asyncio.Semaphore  # set in start()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._pw      = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        self._semaphore = asyncio.Semaphore(self._settings.POOL_SIZE)
        for _ in range(self._settings.POOL_SIZE):
            ctx = await self._make_context()
            self._slots.append(_PoolSlot(context=ctx))
        log.info("browser_pool_started", size=self._settings.POOL_SIZE)

    async def stop(self) -> None:
        for slot in self._slots:
            await slot.context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        log.info("browser_pool_stopped")

    # ── Context factory ───────────────────────────────────────────────────────

    async def _make_context(self) -> BrowserContext:
        ctx = await self._browser.new_context(  # type: ignore[union-attr]
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            user_agent=self._settings.USER_AGENT,
            java_script_enabled=True,
            ignore_https_errors=False,
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
            },
        )
        # Apply stealth patches (removes navigator.webdriver, fixes HeadlessChrome, etc.)
        await Stealth().apply_stealth_async(ctx)
        return ctx

    # ── Acquire / release ─────────────────────────────────────────────────────

    @asynccontextmanager
    async def acquire(self):
        """Yield an idle BrowserContext; blocks if pool exhausted (Pillar 3)."""
        await self._semaphore.acquire()
        slot: _PoolSlot | None = None
        try:
            async with self._lock:
                slot = next(s for s in self._slots if not s.in_use)
                slot.in_use = True
            log.debug("context_acquired")
            yield slot.context
        finally:
            if slot:
                async with self._lock:
                    slot.in_use = False
            self._semaphore.release()
            log.debug("context_released")