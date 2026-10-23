"""Alembic environment. Migrations run as mm_migrator, the owner of the medmusketeer database."""
import os

from alembic import context
from sqlalchemy import create_engine, pool

url = os.environ.get("MM_MIGRATOR_DATABASE_URL")
if not url:
    raise SystemExit("MM_MIGRATOR_DATABASE_URL is not set")

engine = create_engine(url, poolclass=pool.NullPool)
with engine.connect() as connection:
    context.configure(connection=connection, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
