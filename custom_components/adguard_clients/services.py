"""Service `adguard_clients.set_blocked_services`."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .client_ops import blocked, with_blocked
from .const import DOMAIN
from .coordinator import AdGuardClientsCoordinator

SERVICE_SET_BLOCKED_SERVICES = "set_blocked_services"

SET_BLOCKED_SERVICES_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Optional("block", default=[]): [cv.string],
        vol.Optional("unblock", default=[]): [cv.string],
    }
)


def _invalid_device() -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN, translation_key="invalid_device"
    )


def _resolve(hass: HomeAssistant, device_id: str) -> tuple[AdGuardClientsCoordinator, str]:
    """Appareil client -> (coordinateur, uid) ; sinon `invalid_device`."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise _invalid_device()
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        prefix = f"{entry.entry_id}_"
        for domain, identifier in device.identifiers:
            if domain == DOMAIN and identifier.startswith(prefix):
                uid = identifier.removeprefix(prefix)
                if uid:
                    return entry.runtime_data, uid
    raise _invalid_device()


async def _set_blocked_services(call: ServiceCall) -> dict[str, Any]:
    hass = call.hass
    coordinator, uid = _resolve(hass, call.data["device_id"])
    block = set(call.data["block"])
    unblock = set(call.data["unblock"])

    if conflict := block & unblock:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="conflicting_services",
            translation_placeholders={"services": ", ".join(sorted(conflict))},
        )
    if unknown := (block | unblock) - set(coordinator.catalog):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_service",
            translation_placeholders={"services": ", ".join(sorted(unknown))},
        )

    written: list[str] = []

    def mutate(client: dict[str, Any]) -> dict[str, Any]:
        new = with_blocked(client, block, unblock)
        written[:] = new["blocked_services"]
        return new

    await coordinator.async_update_client(uid, mutate)

    fiche = coordinator.data.clients.get(uid) if coordinator.data else None
    result = sorted(blocked(fiche)) if fiche is not None else list(written)
    return {"blocked_services": result}


def async_register_services(hass: HomeAssistant) -> None:
    """Enregistre les services de l'intégration (une seule fois)."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_BLOCKED_SERVICES,
        _set_blocked_services,
        schema=SET_BLOCKED_SERVICES_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
