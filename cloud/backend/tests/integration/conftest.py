"""Fixtures for tests against a real PostgreSQL + TimescaleDB.

A throwaway container (the same image and init script as the compose stack) is started once per
test session, migrated as mm_migrator, and removed afterwards. The API under test connects as
mm_api, so the tests also exercise the runtime privileges.
"""
import os
import secrets
import shlex
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.auth import Principal, get_principal, get_zitadel
from app.main import create_app
from app.settings import Settings
from tests.fake_zitadel import FakeZitadelAdmin

BACKEND_DIR = Path(__file__).resolve().parents[2]
CLOUD_DIR = BACKEND_DIR.parent
POSTGRES_IMAGE = "timescale/timescaledb:2.31.0-pg18"  # keep in step with postgres/Dockerfile


def engine_command() -> str:
    return shlex.split(os.environ.get("MM_COMPOSE", "docker compose"))[0]


@pytest.fixture(scope="session")
def database():
    engine = engine_command()
    if shutil.which(engine) is None:
        pytest.skip(f"{engine} not found; database tests need a container engine")
    passwords = {name: secrets.token_hex(16) for name in
                 ("POSTGRES_PASSWORD", "ZITADEL_DB_PASSWORD", "MM_MIGRATOR_PASSWORD", "MM_API_PASSWORD")}
    name = f"mm-cloud-dbtest-{uuid.uuid4().hex[:8]}"
    env_args = [arg for key, value in passwords.items() for arg in ("-e", f"{key}={value}")]
    # Copied in rather than bind-mounted: Docker Desktop cannot bind-mount a single file from some
    # host drives, and copying works the same on every engine.
    subprocess.run([engine, "create", "--name", name, *env_args, "-p", "127.0.0.1::5432", POSTGRES_IMAGE],
                   check=True, capture_output=True)
    try:
        subprocess.run([engine, "cp", str(CLOUD_DIR / "postgres/init/010-databases.sh"),
                        f"{name}:/docker-entrypoint-initdb.d/010-databases.sh"], check=True, capture_output=True)
        subprocess.run([engine, "start", name], check=True, capture_output=True)
        deadline = time.monotonic() + 90
        ready = ["exec", name, "psql", "-h", "127.0.0.1", "-U", "postgres", "-d", "medmusketeer", "-Atc", "select 1"]
        while subprocess.run([engine, *ready], capture_output=True).returncode != 0:
            if time.monotonic() > deadline:
                logs = subprocess.run([engine, "logs", name], capture_output=True, text=True)
                pytest.fail(f"test database did not become ready:\n{logs.stdout[-3000:]}{logs.stderr[-3000:]}")
            time.sleep(1)
        port = subprocess.run([engine, "port", name, "5432/tcp"], capture_output=True, text=True, check=True)
        host_port = port.stdout.strip().splitlines()[0].rsplit(":", 1)[1]
        base = f"127.0.0.1:{host_port}/medmusketeer"
        yield {
            "migrator": f"postgresql+psycopg://mm_migrator:{passwords['MM_MIGRATOR_PASSWORD']}@{base}",
            "api": f"postgresql+psycopg://mm_api:{passwords['MM_API_PASSWORD']}@{base}",
        }
    finally:
        subprocess.run([engine, "rm", "-f", name], capture_output=True)


def alembic_config(migrator_url: str) -> Config:
    os.environ["MM_MIGRATOR_DATABASE_URL"] = migrator_url
    return Config(str(BACKEND_DIR / "alembic.ini"))


@pytest.fixture(scope="session")
def migrated(database):
    command.upgrade(alembic_config(database["migrator"]), "head")
    return database


@pytest.fixture(scope="session")
def owner_engine(migrated):
    engine = create_engine(migrated["migrator"])
    yield engine
    engine.dispose()


@pytest.fixture
def db(owner_engine):
    """A connection as the schema owner, for arranging data and checking results. Every table is
    emptied first, so tests do not see each other's rows."""
    with owner_engine.begin() as conn:
        tables = conn.scalars(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
        )).all()
        conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
    with owner_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        yield conn


@pytest.fixture
def system_admin(db) -> Principal:
    user_id = db.scalar(text(
        "INSERT INTO users (zitadel_sub, role) VALUES (:sub, 'system_admin') RETURNING user_id"
    ), {"sub": f"sub-{uuid.uuid4()}"})
    return Principal(user_id=user_id, role="system_admin", org_id=None)


@pytest.fixture
def zitadel() -> FakeZitadelAdmin:
    return FakeZitadelAdmin()


@pytest.fixture
def make_client(migrated, zitadel):
    """Build a TestClient for the API as the given principal (None: no override, as in production).
    ZITADEL's management API is the in-memory fake, also for None."""
    clients = []

    def build(principal: Principal | None) -> TestClient:
        settings = Settings(
            database_url=migrated["api"],
            zitadel_url="http://127.0.0.1:1",
            emqx_status_url="http://127.0.0.1:1/status",
        )
        app = create_app(settings)
        if principal is not None:
            app.dependency_overrides[get_principal] = lambda: principal
        app.dependency_overrides[get_zitadel] = lambda: zitadel
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield build
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def admin_client(make_client, system_admin) -> TestClient:
    return make_client(system_admin)
