"""Database access: one AsyncEngine per app, one transaction per request, and small query helpers."""
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

# SQLSTATE codes mapped to HTTP responses when a database rule rejects a write.
_CONFLICT = {"23505": "conflicts with an existing record", "23P01": "conflicts with an existing record"}
_INVALID = {"23503": "refers to a record that does not exist", "23514": "violates a data rule"}


async def connection(request: Request) -> AsyncIterator[AsyncConnection]:
    # The try covers the commit as well: a deferred constraint fails only when the block exits.
    try:
        async with request.app.state.engine.begin() as conn:
            yield conn
    except IntegrityError as error:
        raise http_error(error) from error


def http_error(error: IntegrityError) -> HTTPException:
    code = getattr(error.orig, "sqlstate", None)
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if code in _CONFLICT:
        return HTTPException(status.HTTP_409_CONFLICT, {"error": _CONFLICT[code], "constraint": constraint})
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        {"error": _INVALID.get(code, "violates a data rule"), "constraint": constraint},
    )


# scope="function": commit (and turn a failed commit into an error response) before the response
# is sent. With the default request scope the commit would run after the client got its answer.
Conn = Annotated[AsyncConnection, Depends(connection, scope="function")]


async def one(conn: AsyncConnection, sql: str, **params) -> dict | None:
    row = (await conn.execute(text(sql), params)).mappings().first()
    return dict(row) if row else None


async def many(conn: AsyncConnection, sql: str, **params) -> list[dict]:
    return [dict(row) for row in (await conn.execute(text(sql), params)).mappings()]


def not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


async def audit(conn: AsyncConnection, actor_id, scope: str, action: str, *, org_id=None, target_id=None,
                **details) -> None:
    """Append an audit_log row in the request's transaction, so it exists only if the action does (D11)."""
    await conn.execute(text("""
        INSERT INTO audit_log (actor_id, scope, org_id, action, target_id, details)
        VALUES (:actor, :scope, :org, :action, :target, CAST(:details AS jsonb))
    """), {"actor": actor_id, "scope": scope, "org": org_id, "action": action, "target": target_id,
           "details": json.dumps(details, default=str)})
