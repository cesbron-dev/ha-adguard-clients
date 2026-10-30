"""Tests des entités des clients et de l'instance."""

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adguard_clients import async_remove_config_entry_device
from custom_components.adguard_clients.api import AdGuardConnectionError
from custom_components.adguard_clients.const import DOMAIN

from .fake_adguard import FakeAdGuard, sample_client
from .test_coordinator import URL, _setup, _uid_of

SETTINGS = ["filtering", "parental", "safebrowsing", "safe_search"]
FLAGS = ["use_global_settings", "use_global_blocked_services"]
DEFAULTS = ["youtube", "roblox", "tiktok", "netflix", "disneyplus", "twitch"]


def _dev(hass, entry, uid):
    return dr.async_get(hass).async_get_device_by_identifier(
        entry.runtime_data.client_device_identifier(uid), entry.entry_id
    )


def _eid(hass, platform, entry, uid, key):
    reg = er.async_get(hass)
    eid = reg.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{uid}_{key}")
    assert eid is not None, key
    return eid


async def _call(hass, service, eid):
    await hass.services.async_call(
        "switch", service, {"entity_id": eid}, blocking=True
    )
    await hass.async_block_till_done()


async def _ctx(hass, name="iPad Gabin"):
    entry = await _setup(hass)
    return entry, _uid_of(entry.runtime_data, name)


async def test_client_devices_and_entities(hass, patch_api) -> None:
    entry = await _setup(hass)
    devreg, entreg = dr.async_get(hass), er.async_get(hass)
    instance = devreg.async_get_device_by_identifier((DOMAIN, entry.entry_id), entry.entry_id)
    clients = [
        d
        for d in dr.async_entries_for_config_entry(devreg, entry.entry_id)
        if d.id != instance.id
    ]
    assert len(clients) == 2
    for d in clients:
        assert d.via_device_id == instance.id
        assert d.manufacturer == "AdGuard Home"
        assert d.model == "Client"
        ents = er.async_entries_for_device(entreg, d.id)
        assert len([e for e in ents if e.domain == "switch"]) == 6 + 6
        assert len([e for e in ents if e.domain == "sensor"]) == 1
    assert {d.name for d in clients} == {"iPad Gabin", "TV"}


async def test_service_switch_state_and_toggle(hass, patch_api, fake_adguard) -> None:
    entry, uid = await _ctx(hass)
    eid = _eid(hass, "switch", entry, uid, "svc_youtube")
    assert hass.states.get(eid).state == "off"
    await _call(hass, "turn_on", eid)
    assert fake_adguard.clients[0]["blocked_services"] == ["youtube"]
    assert fake_adguard.clients[0]["use_global_blocked_services"] is False
    assert hass.states.get(eid).state == "on"
    await _call(hass, "turn_off", eid)
    assert fake_adguard.clients[0]["blocked_services"] == []
    assert hass.states.get(eid).state == "off"


async def test_setting_switch_forces_local_settings(hass, patch_api, fake_adguard) -> None:
    fake_adguard.clients[0]["use_global_settings"] = False
    entry, uid = await _ctx(hass)
    await _call(hass, "turn_on", _eid(hass, "switch", entry, uid, "parental"))
    assert fake_adguard.clients[0]["parental_enabled"] is True
    assert fake_adguard.clients[0]["use_global_settings"] is False
    await _call(hass, "turn_on", _eid(hass, "switch", entry, uid, "safe_search"))
    assert fake_adguard.clients[0]["safe_search"]["enabled"] is True
    assert fake_adguard.clients[0]["safe_search"]["bing"] is True


async def test_global_blocked_services_makes_service_switches_unavailable(
    hass, patch_api, fake_adguard
) -> None:
    fake_adguard.clients[0]["use_global_blocked_services"] = True
    entry, uid = await _ctx(hass)
    for sid in DEFAULTS:
        assert hass.states.get(_eid(hass, "switch", entry, uid, f"svc_{sid}")).state == "unavailable"
    assert hass.states.get(_eid(hass, "switch", entry, uid, "use_global_blocked_services")).state == "on"
    assert hass.states.get(_eid(hass, "switch", entry, uid, "filtering")).state == "on"


async def test_global_settings_makes_setting_switches_unavailable(
    hass, patch_api, fake_adguard
) -> None:
    fake_adguard.clients[0]["use_global_settings"] = True
    entry, uid = await _ctx(hass)
    for key in SETTINGS:
        assert hass.states.get(_eid(hass, "switch", entry, uid, key)).state == "unavailable"
    assert hass.states.get(_eid(hass, "switch", entry, uid, "use_global_settings")).state == "on"
    assert hass.states.get(_eid(hass, "switch", entry, uid, "svc_youtube")).state == "off"


async def test_flag_switch_writes_only_flag(hass, patch_api, fake_adguard) -> None:
    fake_adguard.clients[0]["use_global_blocked_services"] = True
    fake_adguard.clients[0]["blocked_services"] = ["youtube"]
    before = {k: v for k, v in fake_adguard.clients[0].items()}
    entry, uid = await _ctx(hass)
    await _call(hass, "turn_off", _eid(hass, "switch", entry, uid, "use_global_blocked_services"))
    after = fake_adguard.clients[0]
    diff = {k for k in after if after[k] != before[k]}
    assert diff == {"use_global_blocked_services"}


async def test_sensor_attributes(hass, patch_api, fake_adguard) -> None:
    fake_adguard.clients[0]["blocked_services"] = ["tiktok", "discord", "youtube"]
    entry, uid = await _ctx(hass)
    state = hass.states.get(_eid(hass, "sensor", entry, uid, "blocked_services"))
    assert state.state == "3"
    assert state.attributes["services"] == ["discord", "tiktok", "youtube"]
    assert state.attributes["ids"] == ["192.168.0.50", "aa:bb:cc:dd:ee:01"]
    assert state.attributes["adguard_name"] == "iPad Gabin"
    assert state.attributes["use_global_blocked_services"] is False
    assert state.attributes["tags"] == []


async def test_new_client_added_on_refresh(hass, patch_api, fake_adguard) -> None:
    entry, _ = await _ctx(hass)
    fake_adguard.clients.append(sample_client("Nouveau", ["192.168.0.99"]))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    uid = _uid_of(entry.runtime_data, "Nouveau")
    assert hass.states.get(_eid(hass, "switch", entry, uid, "svc_youtube")) is not None
    assert hass.states.get(_eid(hass, "sensor", entry, uid, "blocked_services")).state == "0"
    assert _dev(hass, entry, uid)


async def test_rename_keeps_entity_and_updates_device_name(hass, patch_api, fake_adguard) -> None:
    entry, uid = await _ctx(hass)
    eid = _eid(hass, "switch", entry, uid, "filtering")
    fake_adguard.clients[0]["name"] = "iPad de Gabin"
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _eid(hass, "switch", entry, uid, "filtering") == eid
    device = _dev(hass, entry, uid)
    assert device.name == "iPad de Gabin"


async def test_absent_client_unavailable_and_removable(hass, patch_api, fake_adguard) -> None:
    entry, uid = await _ctx(hass, "TV")
    fake_adguard.clients.pop(1)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    for platform, key in (("switch", "filtering"), ("switch", "svc_youtube"), ("sensor", "blocked_services")):
        assert hass.states.get(_eid(hass, platform, entry, uid, key)).state == "unavailable"
    devreg = dr.async_get(hass)
    device = _dev(hass, entry, uid)
    assert await async_remove_config_entry_device(hass, entry, device) is True
    instance = devreg.async_get_device_by_identifier((DOMAIN, entry.entry_id), entry.entry_id)
    assert await async_remove_config_entry_device(hass, entry, instance) is False
    present = _uid_of(entry.runtime_data, "iPad Gabin")
    dev2 = _dev(hass, entry, present)
    assert await async_remove_config_entry_device(hass, entry, dev2) is False


async def test_two_instances_same_client_name(hass, patch_api, fake_adguard) -> None:
    from unittest.mock import patch

    entry1 = await _setup(hass)
    other = FakeAdGuard(clients=[sample_client("TV", ["10.0.0.1"])], catalog=dict(fake_adguard.catalog))
    entry2 = MockConfigEntry(
        domain=DOMAIN,
        title="AdGuard Paris",
        data={"url": "https://other", "username": "a", "password": "x", "verify_ssl": True},
        unique_id="https://other",
    )
    entry2.add_to_hass(hass)
    with patch("custom_components.adguard_clients.AdGuardApi", return_value=other):
        await hass.config_entries.async_setup(entry2.entry_id)
        await hass.async_block_till_done()
    uid1, uid2 = _uid_of(entry1.runtime_data, "TV"), _uid_of(entry2.runtime_data, "TV")
    e1 = _eid(hass, "switch", entry1, uid1, "filtering")
    e2 = _eid(hass, "switch", entry2, uid2, "filtering")
    assert e1 != e2
    devreg = dr.async_get(hass)
    assert _dev(hass, entry1, uid1) != _dev(hass, entry2, uid2)


async def test_client_with_null_fields_creates_entities(hass, patch_api, fake_adguard) -> None:
    fake_adguard.clients.append({"name": "Vieux", "ids": None, "blocked_services": None, "tags": None})
    entry = await _setup(hass)
    uid = _uid_of(entry.runtime_data, "Vieux")
    assert hass.states.get(_eid(hass, "sensor", entry, uid, "blocked_services")).state == "0"
    assert hass.states.get(_eid(hass, "switch", entry, uid, "svc_youtube")) is not None


async def test_connected_binary_sensor(hass, patch_api, fake_adguard) -> None:
    entry = await _setup(hass)
    eid = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_connected"
    )
    assert hass.states.get(eid).state == "on"
    fake_adguard.fail_next = AdGuardConnectionError("down")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "off"


async def test_write_failure_raises_and_state_unchanged(hass, patch_api, fake_adguard) -> None:
    entry, uid = await _ctx(hass)
    eid = _eid(hass, "switch", entry, uid, "svc_youtube")
    fake_adguard.fail_on["update_client"] = AdGuardConnectionError("down")
    with pytest.raises(HomeAssistantError):
        await _call(hass, "turn_on", eid)
    assert hass.states.get(eid).state == "off"


async def test_client_devices_no_deprecation_warning(hass, patch_api, caplog) -> None:
    await _setup(hass)
    assert "deprecated" not in caplog.text
    assert "via_device_id instead" not in caplog.text
