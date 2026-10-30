"""Config flow : une entrée par instance AdGuard Home."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import AdGuardApi, AdGuardAuthError, AdGuardConnectionError, normalize_url
from .const import CONF_URL, CONF_VERIFY_SSL, DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "AdGuard Home"

_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _schema(
    defaults: Mapping[str, Any], *, with_name: bool = False, with_url: bool = True
) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if with_name:
        fields[vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME))] = str
    if with_url:
        fields[vol.Required(CONF_URL, default=defaults.get(CONF_URL, vol.UNDEFINED))] = str
    fields[
        vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, vol.UNDEFINED))
    ] = str
    fields[vol.Required(CONF_PASSWORD)] = _PASSWORD
    if with_url:
        fields[
            vol.Required(CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, True))
        ] = bool
    return vol.Schema(fields)


class AdGuardClientsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Création, ré-authentification et reconfiguration."""

    VERSION = 1

    async def _test(
        self, url: str, username: str, password: str, verify_ssl: bool
    ) -> str | None:
        """Teste la connexion ; renvoie le code d'erreur ou None."""
        session = async_get_clientsession(self.hass, verify_ssl=verify_ssl)
        api = AdGuardApi(session, url, username, password)
        try:
            await api.status()
        except AdGuardAuthError:
            return "invalid_auth"
        except AdGuardConnectionError:
            return "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Erreur inattendue lors du test de connexion")
            return "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = normalize_url(user_input[CONF_URL])
            await self.async_set_unique_id(url)
            self._abort_if_unique_id_configured()
            error = await self._test(
                url,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                user_input[CONF_VERIFY_SSL],
            )
            if error is None:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_URL: url,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                    },
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or {}, with_name=True),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._test(
                entry.data[CONF_URL],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                entry.data[CONF_VERIFY_SSL],
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_schema(user_input or entry.data, with_url=False),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            url = normalize_url(user_input[CONF_URL])
            if any(
                other.unique_id == url and other.entry_id != entry.entry_id
                for other in self._async_current_entries(include_ignore=True)
            ):
                return self.async_abort(reason="already_configured")
            error = await self._test(
                url,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                user_input[CONF_VERIFY_SSL],
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=url,
                    data_updates={
                        CONF_URL: url,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                    },
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(user_input or entry.data),
            errors=errors,
        )
