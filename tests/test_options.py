"""Tests des options : services choisis et intervalle."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adguard_clients.const import DOMAIN

from .test_coordinator import URL


async def _setup_with(hass, options=None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="AdGuard Bordeaux",
        data={"url": URL, "username": "admin", "password": "x", "verify_ssl": True},
        options=options or {},
        unique_id=URL,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _svc_ids(hass, entry) -> set[str]:
    return {
        e.unique_id.split("_svc_")[1]
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if "_svc_" in e.unique_id
    }


async def test_options_flow_sets_services_and_interval(hass, patch_api) -> None:
    entry = await _setup_with(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"services": ["youtube", "discord"], "scan_interval": 60}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {"services": ["youtube", "discord"], "scan_interval": 60}
    assert entry.state is ConfigEntryState.LOADED
    assert _svc_ids(hass, entry) == {"youtube", "discord"}
    assert entry.runtime_data.update_interval == timedelta(seconds=60)


async def test_options_flow_aborts_when_not_loaded(hass, patch_api) -> None:
    entry = await _setup_with(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_loaded"


async def test_removed_service_switch_deleted_from_registry(hass, patch_api) -> None:
    entry = await _setup_with(hass)
    assert "roblox" in _svc_ids(hass, entry)
    hass.config_entries.async_update_entry(
        entry,
        options={
            "services": ["youtube", "tiktok", "netflix", "disneyplus", "twitch"],
            "scan_interval": 30,
        },
    )
    await hass.async_block_till_done()
    assert "roblox" not in _svc_ids(hass, entry)
    assert _svc_ids(hass, entry) == {
        "youtube", "tiktok", "netflix", "disneyplus", "twitch"
    }


async def test_default_services_filtered_by_catalog(hass, patch_api, caplog) -> None:
    del patch_api.catalog["disneyplus"]
    with caplog.at_level(logging.WARNING):
        entry = await _setup_with(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert "disneyplus" not in _svc_ids(hass, entry)
    assert len(_svc_ids(hass, entry)) == 5
    assert "disneyplus" in caplog.text


async def test_unknown_service_in_options_is_skipped(hass, patch_api, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        entry = await _setup_with(
            hass, {"services": ["youtube", "inexistant"], "scan_interval": 30}
        )
    assert entry.state is ConfigEntryState.LOADED
    assert _svc_ids(hass, entry) == {"youtube"}
    assert "inexistant" in caplog.text
    assert caplog.text.count("inexistant") == 1
