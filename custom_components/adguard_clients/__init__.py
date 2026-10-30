"""Intégration AdGuard Clients."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import AdGuardApi  # noqa: F401  (patchable dans les tests)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Mise en place provisoire."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Déchargement provisoire."""
    return True
