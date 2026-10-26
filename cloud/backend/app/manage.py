"""Operator commands. Run inside the api container, e.g.:

    docker compose exec api python -m app.manage register-user --zitadel-sub <id> --role system_admin

register-user records an existing ZITADEL user in `users`, so their tokens are accepted (app.auth).
Organisation users get an --org-id; the system admin has none.

seed-dev fills an empty stack with development data and sign-in accounts for the dashboard
(app.dev_seed). Never run it on a stack that holds real data; it refuses if any organisation exists.
"""
import argparse
import asyncio
import sys
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth import ROLES
from app.settings import Settings


async def register_user(settings: Settings, zitadel_sub: str, role: str, org_id: UUID | None) -> UUID:
    engine = create_async_engine(settings.database_url.get_secret_value())
    try:
        async with engine.begin() as conn:
            return await conn.scalar(text("""
                INSERT INTO users (zitadel_sub, role, org_id) VALUES (:sub, :role, :org) RETURNING user_id
            """), {"sub": zitadel_sub, "role": role, "org": org_id})
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.manage")
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register-user", help="record a ZITADEL user in the users table")
    register.add_argument("--zitadel-sub", required=True, help="the user's ZITADEL id (the token's sub)")
    register.add_argument("--role", required=True, choices=ROLES)
    register.add_argument("--org-id", type=UUID, help="MedMusketeer organisation id; omit for system_admin")
    seed = commands.add_parser("seed-dev", help="development data and dashboard sign-in accounts (empty stack only)")
    seed.add_argument("--password", help="password for every seeded account (default: generated, printed)")
    seed.add_argument("--allow-existing", action="store_true", help=argparse.SUPPRESS)  # the stack tests
    args = parser.parse_args(argv)

    if args.command == "seed-dev":
        from app import dev_seed  # only this command needs it

        print(dev_seed.describe(dev_seed.seed(Settings(), args.password, args.allow_existing)))
        return 0

    try:
        user_id = asyncio.run(register_user(Settings(), args.zitadel_sub, args.role, args.org_id))
    except IntegrityError as error:
        print(f"not registered: {error.orig}", file=sys.stderr)
        return 1
    print(user_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
