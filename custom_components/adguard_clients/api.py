"""Client HTTP pour l'API AdGuard Home."""

from __future__ import annotations

from typing import Any

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=10)


class AdGuardError(Exception):
    """Erreur générique AdGuard."""


class AdGuardConnectionError(AdGuardError):
    """AdGuard injoignable."""


class AdGuardAuthError(AdGuardError):
    """Identifiants refusés."""


def normalize_url(url: str) -> str:
    """URL en minuscules, sans `/` final (sert d'unique_id)."""
    return url.strip().lower().rstrip("/")


class AdGuardApi:
    """Accès à l'API de contrôle d'AdGuard Home."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._base = url.strip().rstrip("/")
        self._headers = {"Authorization": aiohttp.encode_basic_auth(username, password)}

    async def _request(
        self, method: str, path: str, json: Any | None = None
    ) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self._base}{path}",
                json=json,
                headers=self._headers,
                timeout=TIMEOUT,
            ) as resp:
                if resp.status in (401, 403):
                    raise AdGuardAuthError(f"accès refusé ({resp.status})")
                if resp.status >= 400:
                    raise AdGuardError(f"{method} {path} : HTTP {resp.status}")
                body = await resp.read()
                if not body:
                    return None
                try:
                    return await resp.json(content_type=None)
                except ValueError:  # réponse texte (ex. « OK »)
                    return None
        except (aiohttp.ClientError, TimeoutError) as err:
            raise AdGuardConnectionError(str(err) or type(err).__name__) from err

    async def status(self) -> dict[str, Any]:
        return await self._request("GET", "/control/status")

    async def clients(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/control/clients")
        return (data or {}).get("clients") or []

    async def services_catalog(self) -> dict[str, str]:
        data = await self._request("GET", "/control/blocked_services/all") or {}
        items = data.get("blocked_services") or data.get("services") or []
        return {item["id"]: item["name"] for item in items}

    async def update_client(self, name: str, data: dict[str, Any]) -> None:
        await self._request(
            "POST", "/control/clients/update", json={"name": name, "data": data}
        )
