"""FastAPI application. /livez reports that the process is up; /healthz checks its dependencies."""
import asyncio
import contextlib
import logging
import math
from contextlib import asynccontextmanager

from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine

from app import accounts, broker, care, directory, ingest, organisation, registry
from app.emqx_api import EmqxApi
from app.auth import Principal, get_principal
from app.health import check_database, check_http, run_checks
from app.revocation import RevocationSync
from app.settings import Settings
from app.tokens import TokenVerifier, ZitadelConfig, login_scope
from app.zitadel import ZitadelAdmin

log = logging.getLogger(__name__)


def configure_logging(level: str) -> None:
    """INFO lines from app.* (refused requests, broker hook decisions with their check time) with
    millisecond timestamps. Uvicorn configures only its own loggers, so without this they are lost."""
    logger = logging.getLogger("app")
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
                                               datefmt="%Y-%m-%dT%H:%M:%S"))
        logger.addHandler(handler)
        logger.propagate = False


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # raises if a required MM_* variable is missing
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = create_async_engine(
            settings.database_url.get_secret_value(),
            pool_pre_ping=True,
            # libpq takes whole seconds and treats 0 as "wait forever"
            connect_args={"connect_timeout": max(1, math.ceil(settings.dependency_timeout_s))},
        )
        app.state.http = httpx.AsyncClient(timeout=settings.dependency_timeout_s)
        app.state.verifier = None
        app.state.zitadel = None
        if settings.zitadel_config_file.is_file():
            config = ZitadelConfig.load(settings.zitadel_config_file)
            app.state.verifier = TokenVerifier(config, settings.zitadel_url, app.state.http)
            if settings.zitadel_api_token_file.is_file():
                app.state.zitadel = ZitadelAdmin(config, settings.zitadel_url, app.state.http,
                                                 settings.zitadel_api_token_file)
            else:
                log.warning("%s not found: account management is disabled", settings.zitadel_api_token_file)
        else:
            log.warning("%s not found: authentication is disabled", settings.zitadel_config_file)
        emqx = None
        if settings.emqx_api_url and settings.emqx_api_secret:
            emqx = EmqxApi(app.state.http, settings.emqx_api_url, settings.emqx_api_key,
                           settings.emqx_api_secret.get_secret_value())
        else:
            log.warning("EMQX's API is not configured: the revocation list is not published")
        app.state.revocation = RevocationSync(app.state.engine, emqx, poll_s=settings.revocation_poll_s,
                                              republish_s=settings.revocation_republish_s)
        reconciler = asyncio.create_task(app.state.revocation.run()) if emqx else None
        try:
            yield
        finally:
            if reconciler:
                reconciler.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await reconciler
            await app.state.http.aclose()
            await app.state.engine.dispose()

    app = FastAPI(title="MedMusketeer cloud API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(registry.router)
    app.include_router(accounts.router)
    app.include_router(organisation.router)
    app.include_router(care.router)
    app.include_router(directory.router)
    app.include_router(broker.router)
    app.include_router(ingest.router)
    if settings.cors_origins:
        # The dashboard runs on its own origin and sends a bearer token; no cookies are involved.
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                           allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                           allow_headers=["Authorization", "Content-Type"], max_age=600)

    @app.get("/auth/config")
    async def auth_config() -> dict:
        """What the dashboard needs to start a ZITADEL login (D14). Public; nothing in it is secret."""
        verifier = app.state.verifier
        if verifier is None or verifier.config.dashboard_client_id is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "authentication is not configured")
        config = verifier.config
        return {"issuer": config.issuer, "client_id": config.dashboard_client_id,
                "project_id": config.project_id, "scope": login_scope(config.project_id)}

    @app.get("/me")
    async def me(principal: Annotated[Principal, Depends(get_principal)]) -> dict:
        """Who the caller is, for every role (a patient also gets their patient id)."""
        return {"user_id": str(principal.user_id), "role": principal.role,
                "org_id": str(principal.org_id) if principal.org_id else None,
                "patient_id": str(principal.patient_id) if principal.patient_id else None}

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
