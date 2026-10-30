"""Switches des clients AdGuard : réglages, drapeaux et services bloqués."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AdGuardConfigEntry
from .client_ops import blocked, setting_value, with_blocked, with_flag, with_setting
from .coordinator import AdGuardClientsCoordinator
from .entity import AdGuardClientEntity

PARALLEL_UPDATES = 1

SETTINGS = ("filtering", "parental", "safebrowsing", "safe_search")
SETTING_FIELDS = {
    "filtering": "filtering_enabled",
    "parental": "parental_enabled",
    "safebrowsing": "safebrowsing_enabled",
    "safe_search": "safe_search",
}
FLAGS = ("use_global_settings", "use_global_blocked_services")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AdGuardConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crée les switches, y compris pour les clients qui apparaissent plus tard."""
    coordinator = entry.runtime_data
    created: set[str] = set()

    @callback
    def _add_new() -> None:
        new: list[SwitchEntity] = []
        for uid in coordinator.data.clients:
            if uid in created:
                continue
            created.add(uid)
            new.extend(AdGuardSettingSwitch(coordinator, uid, k) for k in SETTINGS)
            new.extend(AdGuardFlagSwitch(coordinator, uid, k) for k in FLAGS)
            new.extend(
                AdGuardServiceSwitch(coordinator, uid, sid)
                for sid in coordinator.services
            )
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class _AdGuardSwitch(AdGuardClientEntity, SwitchEntity):
    """Base : lecture depuis la fiche, écriture via le coordinateur."""

    def _is_on(self, client: dict[str, Any]) -> bool:
        raise NotImplementedError

    @property
    def is_on(self) -> bool | None:
        client = self.client
        return None if client is None else self._is_on(client)

    def _mutation(self, value: bool) -> Callable[[dict[str, Any]], dict[str, Any]]:
        raise NotImplementedError

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_update_client(self._uid, self._mutation(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_update_client(self._uid, self._mutation(False))


class AdGuardSettingSwitch(_AdGuardSwitch):
    """Réglage de filtrage ; indisponible sous réglages globaux."""

    def __init__(self, coordinator: AdGuardClientsCoordinator, uid: str, key: str) -> None:
        super().__init__(coordinator, uid, key)
        self._attr_translation_key = key
        self._field = SETTING_FIELDS[key]

    @property
    def available(self) -> bool:
        client = self.client
        return super().available and not (client or {}).get("use_global_settings")

    def _is_on(self, client: dict[str, Any]) -> bool:
        return setting_value(client, self._field)

    def _mutation(self, value: bool) -> Callable[[dict[str, Any]], dict[str, Any]]:
        return lambda c: with_setting(c, self._field, value)


class AdGuardFlagSwitch(_AdGuardSwitch):
    """Drapeau « utiliser les réglages globaux »."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: AdGuardClientsCoordinator, uid: str, key: str) -> None:
        super().__init__(coordinator, uid, key)
        self._attr_translation_key = key
        self._key: Literal["use_global_settings", "use_global_blocked_services"] = key  # type: ignore[assignment]

    def _is_on(self, client: dict[str, Any]) -> bool:
        return bool(client.get(self._key))

    def _mutation(self, value: bool) -> Callable[[dict[str, Any]], dict[str, Any]]:
        return lambda c: with_flag(c, self._key, value)


class AdGuardServiceSwitch(_AdGuardSwitch):
    """Blocage d'un service ; indisponible sous services globaux."""

    _attr_translation_key = "blocked_service"

    def __init__(self, coordinator: AdGuardClientsCoordinator, uid: str, service: str) -> None:
        super().__init__(coordinator, uid, f"svc_{service}")
        self._service = service
        self._attr_translation_placeholders = {
            "service": coordinator.catalog.get(service, service)
        }

    @property
    def available(self) -> bool:
        client = self.client
        return super().available and not (client or {}).get("use_global_blocked_services")

    def _is_on(self, client: dict[str, Any]) -> bool:
        return self._service in blocked(client)

    def _mutation(self, value: bool) -> Callable[[dict[str, Any]], dict[str, Any]]:
        sid = self._service
        if value:
            return lambda c: with_blocked(c, [sid], [])
        return lambda c: with_blocked(c, [], [sid])
