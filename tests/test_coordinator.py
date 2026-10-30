"""Tests du coordinateur."""

import asyncio

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adguard_clients.api import (
    AdGuardAuthError,
    AdGuardConnectionError,
)
from custom_components.adguard_clients.client_ops import with_setting
from custom_components.adguard_clients.const import DOMAIN

URL = "https://adguard-bdx.home.cesbron.dev"


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="AdGuard Bordeaux",
        data={"url": URL, "username": "admin", "password": "x", "verify_ssl": True},
        unique_id=URL,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _uid_of(coordinator, name):
    return next(u for u, f in coordinator.data.clients.items() if f["name"] == name)


async def test_setup_creates_instance_device_and_uids(hass, patch_api) -> None:
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data
    assert len(coordinator.data.clients) == 2
    assert coordinator.catalog["youtube"] == "YouTube"
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    assert device is not None
    assert device.sw_version == "v0.107.0"
    assert device.manufacturer == "AdGuard Team"
    assert device.name == "AdGuard Bordeaux"


async def test_uids_persist_across_reload(hass, patch_api, hass_storage) -> None:
    entry = await _setup(hass)
    before = {u: f["name"] for u, f in entry.runtime_data.data.clients.items()}
    stored = hass_storage[f"adguard_clients.{entry.entry_id}"]["data"]["clients"]
    assert {v["name"] for v in stored.values()} == {"iPad Gabin", "TV"}
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    after = {u: f["name"] for u, f in entry.runtime_data.data.clients.items()}
    assert before == after


async def test_rename_keeps_uid(hass, patch_api, fake_adguard) -> None:
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    uid = _uid_of(coordinator, "iPad Gabin")
    fake_adguard.clients[0]["name"] = "iPad de Gabin"
    fake_adguard.clients[0]["ids"] = ["192.168.0.50"]
    await coordinator.async_refresh()
    assert coordinator.data.clients[uid]["name"] == "iPad de Gabin"
    assert coordinator.known[uid].name == "iPad de Gabin"


async def test_absent_client_kept_in_known(hass, patch_api, fake_adguard) -> None:
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    uid = _uid_of(coordinator, "TV")
    fake_adguard.clients.pop(1)
    await coordinator.async_refresh()
    assert uid not in coordinator.data.clients
    assert uid in coordinator.known


async def test_write_reads_fresh_and_keeps_fields(hass, patch_api, fake_adguard) -> None:
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    uid = _uid_of(coordinator, "iPad Gabin")
    fake_adguard.clients[0]["upstreams"] = ["1.1.1.1"]
    await coordinator.async_update_client(
        uid, lambda c: with_setting(c, "parental_enabled", True)
    )
    name, data = fake_adguard.updates[-1]
    assert name == "iPad Gabin"
    assert data["upstreams"] == ["1.1.1.1"]
    assert data["parental_enabled"] is True
    assert coordinator.data.clients[uid]["parental_enabled"] is True


async def test_write_follows_rename_since_last_refresh(
    hass, patch_api, fake_adguard
) -> None:
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    uid = _uid_of(coordinator, "iPad Gabin")
    fake_adguard.clients[0]["name"] = "iPad de Gabin"
    await coordinator.async_update_client(
        uid, lambda c: with_setting(c, "parental_enabled", True)
    )
    assert fake_adguard.updates[-1][0] == "iPad de Gabin"


async def test_concurrent_writes_are_serialized(hass, patch_api, fake_adguard) -> None:
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    uid = _uid_of(coordinator, "iPad Gabin")
    await asyncio.gather(
        coordinator.async_update_client(uid, lambda c: {**c, "ignore_querylog": True}),
        coordinator.async_update_client(uid, lambda c: {**c, "ignore_statistics": True}),
    )
    final = fake_adguard.clients[0]
    assert final["ignore_querylog"] is True
    assert final["ignore_statistics"] is True


async def test_write_missing_client_raises(hass, patch_api, fake_adguard) -> None:
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    uid = _uid_of(coordinator, "TV")
    fake_adguard.clients.pop(1)
    with pytest.raises(HomeAssistantError) as err:
        await coordinator.async_update_client(uid, lambda c: c)
    assert err.value.translation_key == "client_not_found"
    assert fake_adguard.updates == []


async def test_write_auth_error_starts_reauth(hass, patch_api, fake_adguard) -> None:
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    uid = _uid_of(coordinator, "TV")
    fake_adguard.fail_on["update_client"] = AdGuardAuthError("401")
    with pytest.raises(HomeAssistantError) as err:
        await coordinator.async_update_client(uid, lambda c: c)
    assert err.value.translation_key == "auth_failed"
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"].get("source") == "reauth" for f in flows)


async def test_write_failure_raises_write_failed(hass, patch_api, fake_adguard) -> None:
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    uid = _uid_of(coordinator, "TV")
    fake_adguard.fail_on["update_client"] = AdGuardConnectionError("down")
    with pytest.raises(HomeAssistantError) as err:
        await coordinator.async_update_client(uid, lambda c: c)
    assert err.value.translation_key == "write_failed"


async def test_write_ok_refresh_fails_does_not_raise(
    hass, patch_api, fake_adguard, caplog
) -> None:
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    uid = _uid_of(coordinator, "TV")
    original = fake_adguard.update_client

    async def update_then_break(name, data):
        await original(name, data)
        fake_adguard.fail_on["clients"] = AdGuardConnectionError("down")

    fake_adguard.update_client = update_then_break
    await coordinator.async_update_client(uid, lambda c: {**c, "ignore_querylog": True})
    assert fake_adguard.updates[-1][1]["ignore_querylog"] is True
    assert coordinator.last_update_success is False


async def test_refresh_network_error_marks_unavailable(
    hass, patch_api, fake_adguard
) -> None:
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    fake_adguard.fail_on["clients"] = AdGuardConnectionError("down")
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False


async def test_setup_catalog_failure_not_ready(hass, patch_api, fake_adguard) -> None:
    fake_adguard.fail_on["services_catalog"] = AdGuardConnectionError("down")
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_deleted_client_ids_reused_gets_new_device(
    hass, patch_api, fake_adguard, hass_storage
) -> None:
    from .fake_adguard import sample_client

    entry = await _setup(hass)
    coordinator = entry.runtime_data
    tv = _uid_of(coordinator, "TV")
    fake_adguard.clients.pop(1)
    await coordinator.async_refresh()
    assert coordinator.known[tv].present is False
    stored = hass_storage[f"adguard_clients.{entry.entry_id}"]["data"]["clients"]
    assert stored[tv]["present"] is False
    fake_adguard.clients.append(sample_client("Tom", ["192.168.0.60"]))
    await coordinator.async_refresh()
    tom = _uid_of(coordinator, "Tom")
    assert tom != tv
    assert coordinator.known[tom].present is True
    assert coordinator.known[tv].present is False


async def test_known_without_present_defaults_true(hass, patch_api, hass_storage) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="AdGuard Bordeaux",
        data={"url": URL, "username": "admin", "password": "x", "verify_ssl": True},
        unique_id=URL,
    )
    hass_storage[f"adguard_clients.{entry.entry_id}"] = {
        "version": 1,
        "key": f"adguard_clients.{entry.entry_id}",
        "data": {"clients": {"old": {"name": "Ancien", "ids": ["192.168.0.60"]}}},
    }
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    # renommage TV -> présent supposé à la dernière lecture : même uid
    assert coordinator.data.clients["old"]["name"] == "TV"


async def test_remove_device_purges_known_and_store(
    hass, patch_api, fake_adguard, hass_storage
) -> None:
    from custom_components.adguard_clients import async_remove_config_entry_device

    entry = await _setup(hass)
    coordinator = entry.runtime_data
    tv = _uid_of(coordinator, "TV")
    fake_adguard.clients.pop(1)
    await coordinator.async_refresh()
    device = dr.async_get(hass).async_get_device_by_identifier(
        coordinator.client_device_identifier(tv), entry.entry_id
    )
    assert await async_remove_config_entry_device(hass, entry, device) is True
    assert tv not in coordinator.known
    stored = hass_storage[f"adguard_clients.{entry.entry_id}"]["data"]["clients"]
    assert tv not in stored


async def test_remove_device_refused_when_not_loaded(
    hass, patch_api, fake_adguard
) -> None:
    from custom_components.adguard_clients import async_remove_config_entry_device

    entry = await _setup(hass)
    coordinator = entry.runtime_data
    tv = _uid_of(coordinator, "TV")
    fake_adguard.clients.pop(1)
    await coordinator.async_refresh()
    device = dr.async_get(hass).async_get_device_by_identifier(
        coordinator.client_device_identifier(tv), entry.entry_id
    )
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert await async_remove_config_entry_device(hass, entry, device) is False


async def test_remove_entry_deletes_store(hass, patch_api, hass_storage) -> None:
    entry = await _setup(hass)
    key = f"adguard_clients.{entry.entry_id}"
    assert key in hass_storage
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage


async def test_stale_refresh_does_not_overwrite_write(
    hass, patch_api, fake_adguard
) -> None:
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    uid = _uid_of(coordinator, "TV")
    original = coordinator.api
    gate = asyncio.Event()
    reading = asyncio.Event()

    class Gated:
        armed = True

        def __getattr__(self, name):
            return getattr(original, name)

        async def clients(self):
            snapshot = await original.clients()
            if Gated.armed:
                Gated.armed = False
                reading.set()
                await gate.wait()
            return snapshot

    coordinator.api = Gated()
    # rafraîchissement planifié, bloqué après avoir lu l'état d'avant l'écriture
    refresh = hass.async_create_task(coordinator._handle_refresh_interval())
    await reading.wait()
    write = hass.async_create_task(
        coordinator.async_update_client(uid, lambda c: {**c, "ignore_querylog": True})
    )
    for _ in range(10):
        await asyncio.sleep(0)
    gate.set()
    await asyncio.gather(refresh, write)
    assert fake_adguard.clients[1]["ignore_querylog"] is True
    assert coordinator.data.clients[uid]["ignore_querylog"] is True
