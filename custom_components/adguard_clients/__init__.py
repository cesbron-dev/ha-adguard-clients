"""Intégration AdGuard Clients."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AdGuardApi, AdGuardAuthError, AdGuardError
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_URL,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import AdGuardClientsCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]

type AdGuardConfigEntry = ConfigEntry[AdGuardClientsCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AdGuardConfigEntry) -> bool:
    """Met en place une instance AdGuard Home."""
    session = async_get_clientsession(hass, verify_ssl=entry.data[CONF_VERIFY_SSL])
    api = AdGuardApi(
        session, entry.data[CONF_URL], entry.data["username"], entry.data["password"]
    )
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = AdGuardClientsCoordinator(hass, entry, api, scan_interval)

    await coordinator.async_load()
    try:
        status = await api.status()
    except AdGuardAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except AdGuardError as err:
        raise ConfigEntryNotReady(str(err)) from err
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="AdGuard Team",
        sw_version=status.get("version"),
        configuration_url=entry.data[CONF_URL],
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: AdGuardConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AdGuardConfigEntry) -> bool:
    """Décharge une instance."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
