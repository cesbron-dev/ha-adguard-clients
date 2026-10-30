"""Capteur des services bloqués par client."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AdGuardConfigEntry
from .client_ops import blocked, client_ids
from .entity import AdGuardClientEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AdGuardConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crée un capteur par client, y compris ceux qui apparaissent plus tard."""
    coordinator = entry.runtime_data
    created: set[str] = set()

    @callback
    def _add_new() -> None:
        new = [
            AdGuardBlockedServicesSensor(coordinator, uid)
            for uid in coordinator.data.clients
            if uid not in created
        ]
        created.update(s._uid for s in new)
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class AdGuardBlockedServicesSensor(AdGuardClientEntity, SensorEntity):
    """Nombre de services bloqués."""

    _attr_translation_key = "blocked_services"

    def __init__(self, coordinator, uid: str) -> None:
        super().__init__(coordinator, uid, "blocked_services")

    @property
    def native_value(self) -> int | None:
        client = self.client
        return None if client is None else len(blocked(client))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        client = self.client
        if client is None:
            return None
        return {
            "services": sorted(blocked(client)),
            "ids": sorted(client_ids(client)),
            "tags": list(client.get("tags") or []),
            "adguard_name": client.get("name"),
            "use_global_blocked_services": bool(client.get("use_global_blocked_services")),
        }
