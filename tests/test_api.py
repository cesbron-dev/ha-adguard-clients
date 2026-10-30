"""Tests du client HTTP AdGuard."""

import aiohttp
import pytest

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.adguard_clients.api import (
    AdGuardApi,
    AdGuardAuthError,
    AdGuardConnectionError,
    AdGuardError,
    normalize_url,
)

URL = "http://adguard.test:3000"


def make_api(hass) -> AdGuardApi:
    return AdGuardApi(async_get_clientsession(hass), URL + "/", "admin", "pw")


async def test_clients_returns_list_and_uses_basic_auth(hass, aioclient_mock):
    aioclient_mock.get(
        f"{URL}/control/clients",
        json={"clients": [{"name": "TV"}], "auto_clients": []},
    )
    assert await make_api(hass).clients() == [{"name": "TV"}]
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["Authorization"].startswith("Basic ")


async def test_status_returns_dict(hass, aioclient_mock):
    aioclient_mock.get(f"{URL}/control/status", json={"running": True})
    assert await make_api(hass).status() == {"running": True}


async def test_clients_null_is_empty(hass, aioclient_mock):
    aioclient_mock.get(f"{URL}/control/clients", json={"clients": None})
    assert await make_api(hass).clients() == []


@pytest.mark.parametrize("key", ["blocked_services", "services"])
async def test_catalog_maps_id_to_name(hass, aioclient_mock, key):
    aioclient_mock.get(
        f"{URL}/control/blocked_services/all",
        json={key: [{"id": "youtube", "name": "YouTube"}]},
    )
    assert await make_api(hass).services_catalog() == {"youtube": "YouTube"}


async def test_update_client_posts_full_payload(hass, aioclient_mock):
    aioclient_mock.post(f"{URL}/control/clients/update")
    data = {"name": "TV", "ids": ["1.2.3.4"], "blocked_services": ["youtube"]}
    await make_api(hass).update_client("TV", data)
    method, _, body, _ = aioclient_mock.mock_calls[0][:4]
    assert method == "POST"
    assert body == {"name": "TV", "data": data}


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_error(hass, aioclient_mock, status):
    aioclient_mock.get(f"{URL}/control/clients", status=status)
    with pytest.raises(AdGuardAuthError):
        await make_api(hass).clients()


@pytest.mark.parametrize("exc", [aiohttp.ClientError(), TimeoutError()])
async def test_network_error_raises_connection_error(hass, aioclient_mock, exc):
    aioclient_mock.get(f"{URL}/control/clients", exc=exc)
    with pytest.raises(AdGuardConnectionError):
        await make_api(hass).clients()


async def test_500_raises_adguard_error(hass, aioclient_mock):
    aioclient_mock.get(f"{URL}/control/clients", status=500)
    with pytest.raises(AdGuardError) as err:
        await make_api(hass).clients()
    assert not isinstance(err.value, (AdGuardAuthError, AdGuardConnectionError))


def test_normalize_url():
    assert (
        normalize_url("HTTPS://AdGuard-bdx.home.cesbron.dev/")
        == "https://adguard-bdx.home.cesbron.dev"
    )
