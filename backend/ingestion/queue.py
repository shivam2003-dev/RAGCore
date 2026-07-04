"""Ingestion scheduling seam.

BackgroundTasksQueue is fine for a single-node deployment. Moving to a durable
worker (arq, Celery) means one new class here — call sites depend on the
protocol only. Redis stays cache-only by design.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from fastapi import BackgroundTasks


class IngestionQueue(Protocol):
    def enqueue(self, job: Callable[..., Awaitable[None]], /, **kwargs: Any) -> None: ...


class BackgroundTasksQueue:
    """Passes the async function itself (not a lambda) so Starlette detects it
    as a coroutine function and awaits it instead of threadpooling it."""

    def __init__(self, background: BackgroundTasks) -> None:
        self._background = background

    def enqueue(self, job: Callable[..., Awaitable[None]], /, **kwargs: Any) -> None:
        self._background.add_task(job, **kwargs)
