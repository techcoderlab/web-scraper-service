# ─────────────────────────────────────────────────────
# Module   : main
# Layer    : Presentation (app factory / composition root)
# Pillar   : P0 Stack Bootstrap, P1 Architecture (DI wiring),
#            P3 Concurrency (lifespan lifecycle),
#            P5 Scalability (stateless, config from env),
#            P7 Observability (structured logging init)
# Complexity: O(1) — startup/shutdown lifecycle
# ─────────────────────────────────────────────────────
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from application.analysis_service import AnalysisService
from application.config import Settings
from application.task_queue import TaskQueue
from infrastructure.browser_pool import BrowserPool
from infrastructure.logging_config import configure_logging
from infrastructure.repository import InMemoryAnalysisRepository
from infrastructure.scraper import PlaywrightScraper
from presentation.routes import router

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: wire DI graph on startup, tear down on shutdown.

    Startup sequence (dependency order):
      1. Settings (env / .env)
      2. Logging configuration
      3. BrowserPool (Playwright contexts)
      4. PlaywrightScraper (BrowserPort implementation)
      5. InMemoryAnalysisRepository (AnalysisRepository implementation)
      6. TaskQueue (bounded worker pool)
      7. AnalysisService (orchestrator)

    All services are attached to app.state for request-scoped access
    (Pillar 5 — no module-level singletons).

    Args:
        app: The FastAPI application instance.
    """
    settings = Settings()
    configure_logging(level=settings.LOG_LEVEL)

    log.info(
        "startup_begin",
        host=settings.HOST,
        port=settings.PORT,
        pool_size=settings.POOL_SIZE,
        worker_count=settings.WORKER_COUNT,
        max_queue_size=settings.MAX_QUEUE_SIZE,
    )

    # ── Build dependency graph (bottom-up) ────────────────────────────────
    browser_pool = BrowserPool(settings)
    await browser_pool.start()

    scraper = PlaywrightScraper(pool=browser_pool)
    repository = InMemoryAnalysisRepository()

    task_queue = TaskQueue(
        max_size=settings.MAX_QUEUE_SIZE,
        worker_count=settings.WORKER_COUNT,
    )
    await task_queue.start()

    analysis_service = AnalysisService(
        browser=scraper,
        repository=repository,
        queue=task_queue,
    )

    # ── Attach to app.state for route handlers ────────────────────────────
    app.state.settings = settings
    app.state.browser_pool = browser_pool
    app.state.task_queue = task_queue
    app.state.analysis_service = analysis_service
    
    
    yield  # ── Application is running ──

    # ── Graceful shutdown (reverse order) ─────────────────────────────────
    log.info("shutdown_begin")
    await task_queue.stop()
    await scraper.close()
    await browser_pool.stop()
    log.info("shutdown_complete")


def create_app() -> FastAPI:
    """Application factory — produces a fully configured FastAPI instance.

    Returns:
        FastAPI app with middleware, routes, and lifespan wired.
    """
    app = FastAPI(
        title="Web Analyst",
        description="Production-grade web scraping and analysis microservice.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Pillar 4: compress responses (gzip for payloads > 500 bytes)
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # Mount all routes
    app.include_router(router)

    return app


# Module-level app instance for `uvicorn main:app`
app = create_app()


async def verify_proxy_ip():
   
    # 2. ipify API ko hit karein jo sirf IP return karti hai
    test_url = "https://api.ipify.org?format=json"
    
    try:
        print("Checking IP address through scraper...")
        snapshot = await scraper.fetch(test_url)
        
        # Snapshot ke text mein IP address hoga
        print("-" * 30)
        print(f"Detected IP: {snapshot.text}")
        print("-" * 30)
        
    except Exception as e:
        print(f"Error checking IP: {e}")
    finally:
        await app_container.browser_pool.stop()


if __name__ == "__main__":
    settings = Settings()
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=False,  # Disable in production; enable manually for dev
    )