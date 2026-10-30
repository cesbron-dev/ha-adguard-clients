"""Tests du config flow."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adguard_clients.api import (
    AdGuardAuthError,
    AdGuardConnectionError,
)
from custom_components.adguard_clients.const import DOMAIN

URL = "https://adguard-bdx.home.cesbron.dev"
USER_INPUT = {
    "name": "AdGuard Bordeaux",
    "url": "https://Adguard-bdx.home.cesbron.dev/",
    "username": "admin",
    "password": "secret",
    "verify_ssl": True,
}


@pytest.fixture(autouse=True)
def patch_setup():
    with patch(
        "custom_components.adguard_clients.async_setup_entry", return_value=True
    ) as mock:
        yield mock


def _entry(**data) -> MockConfigEntry:
    base = {"url": URL, "username": "admin", "password": "old", "verify_ssl": True}
    base.update(data)
    return MockConfigEntry(
        domain=DOMAIN, title="AdGuard Bordeaux", data=base, unique_id=base["url"]
    )


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


async def test_user_flow_creates_entry(hass: HomeAssistant, patch_api) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "AdGuard Bordeaux"
    assert result["data"] == {
        "url": URL,
        "username": "admin",
        "password": "secret",
        "verify_ssl": True,
    }
    assert result["result"].unique_id == URL


@pytest.mark.parametrize(
    ("exc", "error"),
    [
        (AdGuardConnectionError("x"), "cannot_connect"),
        (AdGuardAuthError("x"), "invalid_auth"),
        (RuntimeError("x"), "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, patch_api, fake_adguard, exc, error
) -> None:
    result = await _start(hass)
    fake_adguard.fail_next = exc
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    # Récupération après erreur
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_url_aborts(hass: HomeAssistant, patch_api) -> None:
    _entry().add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_password(hass: HomeAssistant, patch_api) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "admin2", "password": "new"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new"
    assert entry.data["username"] == "admin2"
    assert entry.data["url"] == URL


async def test_reauth_invalid_auth(
    hass: HomeAssistant, patch_api, fake_adguard
) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    fake_adguard.fail_next = AdGuardAuthError("x")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "admin", "password": "bad"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["password"] == "old"


async def test_reconfigure_changes_url(hass: HomeAssistant, patch_api) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "url": "https://New.example.com:3000/",
            "username": "admin",
            "password": "pw",
            "verify_ssl": False,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["url"] == "https://new.example.com:3000"
    assert entry.data["verify_ssl"] is False
    assert entry.unique_id == "https://new.example.com:3000"


async def test_reconfigure_error(hass: HomeAssistant, patch_api, fake_adguard) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    fake_adguard.fail_next = AdGuardConnectionError("x")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"url": URL, "username": "admin", "password": "pw", "verify_ssl": True},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reconfigure_duplicate_aborts(hass: HomeAssistant, patch_api) -> None:
    other = _entry(url="https://other.example.com")
    other.add_to_hass(hass)
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "url": "https://Other.example.com/",
            "username": "admin",
            "password": "pw",
            "verify_ssl": True,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
