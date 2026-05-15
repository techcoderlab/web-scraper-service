# ── Pillar 3: Async browser pool — N contexts, non-blocking lifecycle ────────
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import random

from playwright.async_api import (
    async_playwright, Browser, BrowserContext, Playwright,
)
from playwright_stealth import Stealth

from infrastructure.logging_config import get_logger
from application.config import Settings
from infrastructure.proxy_manager import ProxyManager

log = get_logger(__name__)


@dataclass
class _PoolSlot:
    context: BrowserContext
    in_use:  bool = False


class BrowserPool:
    """Fixed-size pool of stealth Playwright contexts."""

    def __init__(self, settings: Settings) -> None:
        self._settings   = settings
        self._proxy_manager = ProxyManager(settings)
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
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        ]
        viewports = [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1536, "height": 864},
            {"width": 1440, "height": 900},
            {"width": 2560, "height": 1440},
        ]
        
        # get proxy from proxy manager
        proxy_settings = self._proxy_manager.get_next_proxy()

        ctx = await self._browser.new_context(  # type: ignore[union-attr]
            viewport=random.choice(viewports),
            locale="en-US",
            timezone_id="America/New_York",
            user_agent=random.choice(user_agents),
            proxy=proxy_settings,
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