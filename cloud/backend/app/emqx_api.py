"""EMQX's REST API (D16), with the API key EMQX loads from its bootstrap file at start.

Used to publish the retained wearable revocation list and to disconnect a gateway when it is
suspended or revoked (D4). A REST publish does not pass through client authorisation, so no MQTT
account needs publish rights to the list's topic. Verified against EMQX 6.3.2 in the Iteration 4
Slice 0 spike.
"""
import logging
from urllib.parse import quote

import httpx

log = logging.getLogger(__name__)


class EmqxError(Exception):
    pass


class EmqxApi:
    def __init__(self, http: httpx.AsyncClient, base_url: str, key: str, secret: str):
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.auth = httpx.BasicAuth(key, secret)

    async def _call(self, method: str, path: str, *, also_ok: tuple[int, ...] = (), **kwargs) -> httpx.Response:
        try:
            response = await self.http.request(method, f"{self.base_url}{path}", auth=self.auth, **kwargs)
        except httpx.HTTPError as error:
            raise EmqxError(f"{method} {path}: {type(error).__name__}: {error}") from error
        if response.status_code >= 300 and response.status_code not in also_ok:
            raise EmqxError(f"{method} {path}: HTTP {response.status_code} {response.text[:200]}")
        return response

    async def publish_retained(self, topic: str, payload: str) -> None:
        """QoS 1, retained. EMQX answers 200 also when nobody is subscribed."""
        await self._call("POST", "/publish", json={"topic": topic, "payload": payload, "qos": 1, "retain": True})

    async def disconnect(self, username: str) -> int:
        """Disconnects every session of `username` (reason 0x98); the number disconnected."""
        clients = (await self._call("GET", "/clients", params={"username": username, "limit": 100})).json()["data"]
        for client in clients:
            # 404: it disconnected on its own in between.
            await self._call("DELETE", f"/clients/{quote(client['clientid'], safe='')}", also_ok=(404,))
        return len(clients)
