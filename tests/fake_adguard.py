"""Faux AdGuard Home en mémoire, même interface que AdGuardApi."""

from __future__ import annotations

import asyncio
import copy
from typing import Any

from custom_components.adguard_clients.api import AdGuardError


def sample_client(name: str, ids: list[str], **overrides: Any) -> dict[str, Any]:
    """Fiche client réaliste (AdGuard Home v0.107)."""
    client: dict[str, Any] = {
        "name": name,
        "ids": list(ids),
        "tags": [],
        "use_global_settings": False,
        "filtering_enabled": True,
        "parental_enabled": False,
        "safebrowsing_enabled": False,
        "safe_search": {
            "enabled": False,
            "bing": True,
            "duckduckgo": True,
            "google": True,
            "pixabay": True,
            "yandex": True,
            "youtube": True,
        },
        "use_global_blocked_services": False,
        "blocked_services": [],
        "blocked_services_schedule": {"time_zone": "Local"},
        "upstreams": [],
        "ignore_querylog": False,
        "ignore_statistics": False,
        "upstreams_cache_enabled": False,
        "upstreams_cache_size": 0,
    }
    client.update(overrides)
    return client


class _Clients(list):
    """Liste de fiches, appelable comme `AdGuardApi.clients()` (copie profonde)."""

    def __init__(self, owner: FakeAdGuard, items: list[dict[str, Any]]) -> None:
        super().__init__(items)
        self._owner = owner

    async def __call__(self) -> list[dict[str, Any]]:
        self._owner._maybe_fail("clients")
        snapshot = copy.deepcopy(list(self))
        await asyncio.sleep(0)  # cède la main : expose les courses sans verrou
        return snapshot


class FakeAdGuard:
    """Implémentation en mémoire de l'API."""

    def __init__(
        self,
        clients: list[dict[str, Any]] | None = None,
        catalog: dict[str, str] | None = None,
    ) -> None:
        self.clients = clients if clients is not None else []
        self.catalog: dict[str, str] = catalog if catalog is not None else {}
        self.updates: list[tuple[str, dict[str, Any]]] = []
        self.fail_next: Exception | None = None
        self.fail_on: dict[str, Exception] = {}

    @property
    def clients(self) -> _Clients:
        """Fiches en mémoire ; `await fake.clients()` imite l'API."""
        return self._clients

    @clients.setter
    def clients(self, value: list[dict[str, Any]]) -> None:
        self._clients = _Clients(self, value)

    def _maybe_fail(self, method: str) -> None:
        if method in self.fail_on:
            raise self.fail_on.pop(method)
        if self.fail_next is not None:
            err, self.fail_next = self.fail_next, None
            raise err

    async def status(self) -> dict[str, Any]:
        self._maybe_fail("status")
        return {"running": True, "version": "v0.107.0"}

    async def services_catalog(self) -> dict[str, str]:
        self._maybe_fail("services_catalog")
        return dict(self.catalog)

    async def update_client(self, name: str, data: dict[str, Any]) -> None:
        self._maybe_fail("update_client")
        await asyncio.sleep(0)
        for i, client in enumerate(self.clients):
            if client["name"] == name:
                self._clients[i] = copy.deepcopy(data)
                self.updates.append((name, copy.deepcopy(data)))
                return
        raise AdGuardError(f"client inconnu : {name}")
