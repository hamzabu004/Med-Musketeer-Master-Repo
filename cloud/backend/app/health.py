"""Dependency checks for /healthz. Each check returns "ok" or "error"; failure details are
logged by exception type only, never with connection strings."""
import asyncio
import logging
from collections.abc import Awaitable

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger(__name__)


async def check_database(engine: AsyncEngine) -> str:
    async with engine.connect() as conn:
        version = await conn.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")
        )
    if version is None:
        raise RuntimeError("timescaledb extension missing")
    return "ok"


async def check_http(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url)
    response.raise_for_status()
    return "ok"


async def run_checks(checks: dict[str, Awaitable[str]]) -> dict[str, str]:
    names = list(checks)
    results = await asyncio.gather(*checks.values(), return_exceptions=True)
    status = {}
    for name, result in zip(names, results):
        if isinstance(result, BaseException):
            log.warning("health check %s failed: %s", name, type(result).__name__)
            status[name] = "error"
        else:
            status[name] = result
    return status
