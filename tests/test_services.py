"""Tests du service set_blocked_services."""

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.adguard_clients.const import DOMAIN

from .test_coordinator import _setup, _uid_of
from .test_entities import _dev, _eid


async def _call(hass, device_id, **data):
    return await hass.services.async_call(
        DOMAIN,
        "set_blocked_services",
        {"device_id": device_id, **data},
        blocking=True,
        return_response=True,
    )


async def _ctx(hass):
    entry = await _setup(hass)
    uid = _uid_of(entry.runtime_data, "iPad Gabin")
    return entry, uid, _dev(hass, entry, uid).id


async def test_service_blocks_and_unblocks_in_one_write(hass, patch_api, fake_adguard) -> None:
    fake_adguard.clients[0]["blocked_services"] = ["tiktok"]
    entry, uid, dev_id = await _ctx(hass)
    resp = await _call(hass, dev_id, block=["youtube", "roblox"], unblock=["tiktok"])
    assert len(fake_adguard.updates) == 1
    assert fake_adguard.clients[0]["blocked_services"] == ["roblox", "youtube"]
    assert resp == {"blocked_services": ["roblox", "youtube"]}


async def test_service_accepts_service_without_switch(hass, patch_api, fake_adguard) -> None:
    _, _, dev_id = await _ctx(hass)
    resp = await _call(hass, dev_id, block=["discord"])
    assert fake_adguard.clients[0]["blocked_services"] == ["discord"]
    assert resp == {"blocked_services": ["discord"]}


async def test_service_unknown_service(hass, patch_api, fake_adguard) -> None:
    _, _, dev_id = await _ctx(hass)
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, dev_id, block=["inexistant"])
    assert err.value.translation_key == "unknown_service"
    assert err.value.translation_placeholders == {"services": "inexistant"}
    assert fake_adguard.updates == []


async def test_service_conflict(hass, patch_api, fake_adguard) -> None:
    _, _, dev_id = await _ctx(hass)
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, dev_id, block=["youtube"], unblock=["youtube"])
    assert err.value.translation_key == "conflicting_services"
    assert fake_adguard.updates == []


async def test_service_invalid_device(hass, patch_api, fake_adguard) -> None:
    entry, _, _ = await _ctx(hass)
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "nope", block=["youtube"])
    assert err.value.translation_key == "invalid_device"
    instance = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, instance.id, block=["youtube"])
    assert err.value.translation_key == "invalid_device"
    assert fake_adguard.updates == []


async def test_service_leaves_global_mode(hass, patch_api, fake_adguard) -> None:
    fake_adguard.clients[0]["use_global_blocked_services"] = True
    entry, uid, dev_id = await _ctx(hass)
    eid = _eid(hass, "switch", entry, uid, "svc_youtube")
    assert hass.states.get(eid).state == "unavailable"
    await _call(hass, dev_id, block=["youtube"])
    await hass.async_block_till_done()
    assert fake_adguard.clients[0]["use_global_blocked_services"] is False
    assert hass.states.get(eid).state == "on"


async def test_service_client_gone(hass, patch_api, fake_adguard) -> None:
    _, _, dev_id = await _ctx(hass)
    fake_adguard.clients.pop(0)
    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, dev_id, block=["youtube"])
    assert err.value.translation_key == "client_not_found"
