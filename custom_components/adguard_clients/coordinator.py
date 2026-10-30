"""Coordinateur : lecture, identité persistée des clients, écriture sûre."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AdGuardApi, AdGuardAuthError, AdGuardError
from .client_ops import client_ids
from .const import DEFAULT_SERVICES, DOMAIN
from .matching import KnownClient, match_clients

_LOGGER = logging.getLogger(__name__)


@dataclass
class AdGuardData:
    """Clients présents dans AdGuard, indexés par uid."""

    clients: dict[str, dict[str, Any]]


class AdGuardClientsCoordinator(DataUpdateCoordinator[AdGuardData]):
    """Lit les clients AdGuard et sérialise les écritures."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: AdGuardApi,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.title}",
            config_entry=entry,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.catalog: dict[str, str] = {}
        self.known: dict[str, KnownClient] = {}
        self._store: Store[dict[str, Any]] = Store(
            hass, 1, f"{DOMAIN}.{entry.entry_id}"
        )
        self._write_lock = asyncio.Lock()

    @property
    def services(self) -> list[str]:
        """Services proposés en switches (provisoire : défauts présents au catalogue)."""
        return [s for s in DEFAULT_SERVICES if s in self.catalog]

    def client_device_identifier(self, uid: str) -> tuple[str, str]:
        """Identifiant d'appareil d'un client."""
        return (DOMAIN, f"{self.config_entry.entry_id}_{uid}")

    async def async_load(self) -> None:
        """Charge l'identité persistée et le catalogue des services."""
        stored = await self._store.async_load()
        if stored:
            self.known = {
                uid: KnownClient(item["name"], frozenset(item["ids"]))
                for uid, item in stored.get("clients", {}).items()
            }
        try:
            self.catalog = await self.api.services_catalog()
        except AdGuardAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AdGuardError as err:
            raise ConfigEntryNotReady(str(err)) from err

    async def _read_and_match(self) -> dict[str, dict[str, Any]]:
        """Lecture fraîche, rapprochement, mise à jour et persistance de `known`."""
        current = await self.api.clients()
        matched = match_clients(self.known, current, lambda: uuid4().hex)
        changed = False
        for uid, fiche in matched.items():
            new = KnownClient(fiche["name"], frozenset(client_ids(fiche)))
            if self.known.get(uid) != new:
                self.known[uid] = new
                changed = True
        if changed:
            await self._store.async_save(
                {
                    "clients": {
                        uid: {"name": k.name, "ids": sorted(k.ids)}
                        for uid, k in self.known.items()
                    }
                }
            )
        return matched

    async def _async_update_data(self) -> AdGuardData:
        try:
            return AdGuardData(clients=await self._read_and_match())
        except AdGuardAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AdGuardError as err:
            raise UpdateFailed(str(err)) from err

    async def async_update_client(
        self,
        uid: str,
        mutate: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Modifie un client : lecture fraîche, mutation, écriture, relecture."""
        async with self._write_lock:
            try:
                matched = await self._read_and_match()
                fiche = matched.get(uid)
                if fiche is None:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN, translation_key="client_not_found"
                    )
                await self.api.update_client(fiche["name"], mutate(fiche))
            except AdGuardAuthError as err:
                self.config_entry.async_start_reauth(self.hass)
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="auth_failed"
                ) from err
            except AdGuardError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="write_failed"
                ) from err
            await self.async_refresh()
            if not self.last_update_success:
                _LOGGER.warning(
                    "Écriture réussie mais relecture AdGuard en échec (%s)",
                    self.config_entry.title,
                )
