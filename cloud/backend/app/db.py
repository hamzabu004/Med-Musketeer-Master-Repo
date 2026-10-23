"""Database access: one AsyncEngine per app, one transaction per request."""
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

# SQLSTATE codes mapped to HTTP responses when a database rule rejects a write.
_CONFLICT = {"23505": "conflicts with an existing record", "23P01": "conflicts with an existing record"}
_INVALID = {"23503": "refers to a record that does not exist", "23514": "violates a data rule"}


async def connection(request: Request) -> AsyncIterator[AsyncConnection]:
    async with request.app.state.engine.begin() as conn:
        try:
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


Conn = Annotated[AsyncConnection, Depends(connection)]
