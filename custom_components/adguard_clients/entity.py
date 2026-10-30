"""Entité de base d'un client AdGuard."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AdGuardClientsCoordinator


class AdGuardClientEntity(CoordinatorEntity[AdGuardClientsCoordinator]):
    """Entité rattachée à l'appareil d'un client."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: AdGuardClientsCoordinator, uid: str, key: str
    ) -> None:
        super().__init__(coordinator)
        self._uid = uid
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{uid}_{key}"
        name = (coordinator.data.clients.get(uid) or {}).get("name")
        if name is None and uid in coordinator.known:
            name = coordinator.known[uid].name
        self._attr_device_info = DeviceInfo(
            identifiers={coordinator.client_device_identifier(uid)},
            name=name,
            manufacturer="AdGuard Home",
            model="Client",
            via_device=(DOMAIN, entry_id),
        )

    @property
    def client(self) -> dict[str, Any] | None:
        """Fiche actuelle du client, ou None s'il est absent d'AdGuard."""
        return self.coordinator.data.clients.get(self._uid)

    @property
    def available(self) -> bool:
        return super().available and self.client is not None
