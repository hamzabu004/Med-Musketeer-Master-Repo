"""FastAPI application. /livez reports that the process is up; /healthz checks its dependencies."""
import math
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Response, status
from sqlalchemy.ext.asyncio import create_async_engine

from app.health import check_database, check_http, run_checks
from app.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # raises if a required MM_* variable is missing

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = create_async_engine(
            settings.database_url.get_secret_value(),
            pool_pre_ping=True,
            # libpq takes whole seconds and treats 0 as "wait forever"
            connect_args={"connect_timeout": max(1, math.ceil(settings.dependency_timeout_s))},
        )
        app.state.http = httpx.AsyncClient(timeout=settings.dependency_timeout_s)
        try:
            yield
        finally:
            await app.state.http.aclose()
            await app.state.engine.dispose()

    app = FastAPI(title="MedMusketeer cloud API", version="0.1.0", lifespan=lifespan)

    @app.get("/livez")
    async def livez() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/healthz")
    async def healthz(response: Response) -> dict:
        checks = await run_checks({
            "database": check_database(app.state.engine),
            "zitadel": check_http(app.state.http, f"{settings.zitadel_url}/debug/ready"),
            "emqx": check_http(app.state.http, settings.emqx_status_url),
        }, timeout_s=settings.dependency_timeout_s)
        healthy = all(result == "ok" for result in checks.values())
        if not healthy:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "ok" if healthy else "error", "checks": checks}

    return app
