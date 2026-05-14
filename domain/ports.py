# ── Domain Ports: ABCs that Infrastructure must implement ────────────────────
from __future__ import annotations
from abc import ABC, abstractmethod
from domain.models import PageSnapshot, AnalysisResult


class BrowserPort(ABC):
    """Contract for any browser backend (Playwright, Pydoll, etc.)."""

    @abstractmethod
    async def fetch(self, url: str, *, wait_selector: str | None = None) -> PageSnapshot:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


class AnalysisRepository(ABC):
    """Persist / retrieve AnalysisResult (swap Redis, Postgres, in-mem)."""

    @abstractmethod
    async def save(self, result: AnalysisResult) -> None: ...

    @abstractmethod
    async def get(self, job_id: str) -> AnalysisResult | None: ...

    @abstractmethod
    async def list_recent(self, limit: int = 50) -> list[AnalysisResult]: ...