"""The wearable revocation list for gateways (D16; Iteration 4, Slice 1).

Every gateway enforces the list on its local broker and keeps the last one it received, so a
revoked wearable is refused while the cloud is unreachable too. The cloud publishes it, retained,
on mm/revocations/wearables through EMQX's REST API (app.emqx_api):

- A registry change that alters the list calls `bump` in its own transaction, so the new version
  exists only if the change does. After the commit, the request publishes (`publish_soon`).
- The reconciler (`run`) publishes whatever is still unpublished every few seconds, and the whole
  list again every few minutes. That repairs a publish lost to an EMQX or API outage, and a
  retained message lost when EMQX's data is reset. Gateways ignore a version they already hold.
- The list is built in one REPEATABLE READ snapshot, so its version always matches its contents;
  a list with a new version and older contents would make gateways ignore the correct one.

An expired certificate drops off the list without a new version: expiry refuses it anyway.
"""
import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.contracts import RevocationList
from app.db import many, one
from app.emqx_api import EmqxApi

log = logging.getLogger(__name__)

TOPIC = "mm/revocations/wearables"
LISTED = frozenset({"suspended", "revoked"})


async def bump(conn: AsyncConnection) -> int:
    """A new list version, in the caller's transaction. The row lock orders concurrent changes."""
    return await conn.scalar(text("UPDATE revocation_state SET version = version + 1 RETURNING version"))


async def current(conn: AsyncConnection) -> RevocationList:
    state = await one(conn, "SELECT version FROM revocation_state")
    devices = await many(conn, """
        SELECT device_id, status, status_changed_at AS since FROM devices
        WHERE type = 'wearable' AND status IN ('suspended', 'revoked') ORDER BY device_id
    """)
    # The registry API stores fingerprints normalised; a row written another way must not stop
    # every publish, so the query normalises too and skips anything that is not a fingerprint.
    certificates = await many(conn, """
        SELECT c.device_id, f.fingerprint, c.expires_at AS not_after
        FROM device_credentials c JOIN devices d USING (device_id)
        CROSS JOIN LATERAL (SELECT upper(replace(c.credential_ref, ':', '')) AS fingerprint) f
        WHERE d.type = 'wearable' AND d.status NOT IN ('suspended', 'revoked')
          AND c.auth_method = 'x509_mtls' AND c.status = 'revoked'
          AND (c.expires_at IS NULL OR c.expires_at > now())
          AND f.fingerprint ~ '^[0-9A-F]{64}$'
        ORDER BY c.device_id, f.fingerprint
    """)
    return RevocationList(v=1, version=state["version"], issued_at=datetime.now(UTC),
                          devices=devices, certificates=certificates)


class RevocationSync:
    def __init__(self, engine: AsyncEngine, emqx: EmqxApi | None, *, poll_s: float = 5, republish_s: float = 300):
        self.snapshots = engine.execution_options(isolation_level="REPEATABLE READ")
        self.engine = engine
        self.emqx = emqx
        self.poll_s = poll_s
        self.republish_s = republish_s
        self._lock = asyncio.Lock()  # one publish at a time, so an older list is never retained last

    async def publish(self, *, force: bool = False) -> int | None:
        """Publishes the list if its version is unpublished (or always, with force); the version
        published, or None. Raises EmqxError when EMQX refuses or cannot be reached."""
        if self.emqx is None:
            return None
        async with self._lock:
            async with self.snapshots.begin() as conn:
                state = await one(conn, "SELECT version, published_version FROM revocation_state")
                if not force and state["published_version"] >= state["version"]:
                    return None
                listing = await current(conn)
            await self.emqx.publish_retained(TOPIC, listing.model_dump_json())
            async with self.engine.begin() as conn:
                await conn.execute(text("""
                    UPDATE revocation_state
                    SET published_version = greatest(published_version, :v), published_at = now()
                """), {"v": listing.version})
        log.info("revocation list version %s published: %s devices, %s certificates",
                 listing.version, len(listing.devices), len(listing.certificates))
        return listing.version

    async def publish_soon(self) -> None:
        """After a registry change has committed. A failure is left to the reconciler."""
        try:
            await self.publish()
        except Exception as error:  # noqa: BLE001 - logged; the reconciler retries
            log.warning("revocation list not published, the reconciler will retry: %s", error)

    async def disconnect_gateway(self, device_id: UUID) -> None:
        """After a gateway or one of its credentials was suspended or revoked. Best effort: if it
        fails, the gateway keeps its session until it reconnects (refused by the authentication
        hook), or loses its topic access within EMQX's 1-minute authorisation cache."""
        if self.emqx is None:
            log.warning("EMQX's API is not configured: gateway %s stays connected until it reconnects", device_id)
            return
        try:
            count = await self.emqx.disconnect(str(device_id))
            log.info("gateway %s disconnected (%s sessions)", device_id, count)
        except Exception as error:  # noqa: BLE001 - best effort, logged
            log.warning("gateway %s not disconnected: %s", device_id, error)

    async def run(self) -> None:
        """The reconciler, for the app's lifetime."""
        next_full = 0.0
        while True:
            now = asyncio.get_running_loop().time()
            force = now >= next_full
            try:
                await self.publish(force=force)
                if force:
                    next_full = now + self.republish_s
            except Exception as error:  # noqa: BLE001 - retried at the next poll
                log.warning("revocation list not published: %s", error)
            await asyncio.sleep(self.poll_s)


def get_revocation(request: Request) -> RevocationSync:
    return request.app.state.revocation


Revocation = Annotated[RevocationSync, Depends(get_revocation)]


def changes_list(device_type: str, old_status: str, new_status: str) -> bool:
    """Whether a status change of this device alters the wearable revocation list."""
    return device_type == "wearable" and (old_status in LISTED or new_status in LISTED) and old_status != new_status
