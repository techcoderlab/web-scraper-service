# ── Infrastructure Scraper: BrowserPort impl with resilience decorators ──────
from __future__ import annotations
import asyncio
import time
from typing import Any

import structlog
from playwright.async_api import BrowserContext, TimeoutError as PWTimeout

from domain.models import PageSnapshot
from domain.ports import BrowserPort
from infrastructure.browser_pool import BrowserPool
from infrastructure.resilience import (
    BlockedError, RateLimitError, TransientNetworkError,
    with_backoff, with_circuit_breaker,
)

log = structlog.get_logger(__name__)

# ── Status-code → exception mapping ──────────────────────────────────────────
_STATUS_MAP: dict[int, type[Exception]] = {
    403: BlockedError,
    429: RateLimitError,
}


class PlaywrightScraper(BrowserPort):

    def __init__(self, pool: BrowserPool) -> None:
        self._pool = pool

    # Pillar 6: circuit breaker wraps backoff
    @with_circuit_breaker(failure_threshold=5, recovery_timeout=30)
    @with_backoff(max_attempts=5, base_wait=2.0, max_wait=60.0)
    async def fetch(
        self,
        url: str,
        *,
        wait_selector: str | None = None,
        timeout_ms: int = 60_000,
    ) -> PageSnapshot:
        t0 = time.monotonic()

        # Pillar 7: bind trace fields to all log calls in this span
        structlog.contextvars.bind_contextvars(url=url)

        async with self._pool.acquire() as ctx:
            page = await ctx.new_page()
            try:
                log.info("fetch_start")
                response = await page.goto(
                    url,
                    wait_until="load",
                    timeout=timeout_ms,
                )
                if response is None:
                    raise TransientNetworkError("No response object returned")

                status = response.status
                log.info("fetch_response", status=status)

                if status in _STATUS_MAP:
                    raise _STATUS_MAP[status](f"HTTP {status} from {url}")

                if wait_selector:
                    await page.wait_for_selector(wait_selector, timeout=timeout_ms)

                snapshot = await self._build_snapshot(page, url, status)
                elapsed = (time.monotonic() - t0) * 1000
                log.info("fetch_complete", duration_ms=round(elapsed, 2))
                return snapshot

            except PWTimeout as exc:
                log.warning("fetch_timeout", error=str(exc))
                raise TransientNetworkError(str(exc)) from exc
            except (BlockedError, RateLimitError):
                raise  # let resilience decorators handle
            except Exception as exc:
                log.error("fetch_error", error=str(exc), exc_info=True)
                raise TransientNetworkError(str(exc)) from exc
            finally:
                await page.close()
                structlog.contextvars.clear_contextvars()

    async def _build_snapshot(self, page, url: str, status: int) -> PageSnapshot:
        """Extract structured data from live page DOM."""
        title = await page.title()
        html  = await page.content()
        text  = await page.inner_text("body")
        final = page.url

        # meta tags
        meta: dict[str, str] = await page.evaluate("""() => {
            const m = {};
            document.querySelectorAll('meta[name], meta[property]').forEach(el => {
                const k = el.getAttribute('name') || el.getAttribute('property');
                const v = el.getAttribute('content');
                if (k && v) m[k] = v;
            });
            return m;
        }""")

        # unique absolute links
        links: list[str] = await page.evaluate("""() =>
            [...new Set(
                [...document.querySelectorAll('a[href]')]
                .map(a => a.href)
                .filter(h => h.startsWith('http'))
            )]
        """)

        screenshot = await page.screenshot(full_page=True, type="png")

        return PageSnapshot(
            url=url,
            final_url=final,
            status_code=status,
            html=html,
            text=text,
            title=title,
            meta=meta,
            links=links,
            screenshots=[screenshot],
        )

    async def close(self) -> None:
        pass  # pool manages lifecycle