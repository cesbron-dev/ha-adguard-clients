"""Lecture et modifications pures des fiches client AdGuard Home."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from typing import Any, Literal

SETTING_KEYS = (
    "filtering_enabled",
    "parental_enabled",
    "safebrowsing_enabled",
    "safe_search",
)


def client_ids(client: Mapping[str, Any]) -> frozenset[str]:
    """Identifiants (IP, MAC, CIDR, ClientID) d'une fiche."""
    return frozenset(str(i) for i in client.get("ids") or ())


def setting_value(client: Mapping[str, Any], key: str) -> bool:
    """Valeur d'un réglage ; `safe_search` lit `safe_search.enabled`."""
    if key == "safe_search":
        return bool((client.get("safe_search") or {}).get("enabled", False))
    return bool(client.get(key, False))


def blocked(client: Mapping[str, Any]) -> frozenset[str]:
    """Services bloqués par la fiche."""
    return frozenset(client.get("blocked_services") or ())


def with_setting(client: Mapping[str, Any], key: str, value: bool) -> dict[str, Any]:
    """Copie avec un réglage modifié ; passe en réglages propres au client."""
    if key not in SETTING_KEYS:
        raise ValueError(f"Réglage inconnu : {key}")
    new = copy.deepcopy(dict(client))
    if key == "safe_search":
        safe_search = new.get("safe_search") or {}
        safe_search["enabled"] = value
        new["safe_search"] = safe_search
    else:
        new[key] = value
    new["use_global_settings"] = False
    return new


def with_flag(
    client: Mapping[str, Any],
    key: Literal["use_global_settings", "use_global_blocked_services"],
    value: bool,
) -> dict[str, Any]:
    """Copie avec un seul drapeau modifié."""
    new = copy.deepcopy(dict(client))
    new[key] = value
    return new


def with_blocked(
    client: Mapping[str, Any], block: Iterable[str], unblock: Iterable[str]
) -> dict[str, Any]:
    """Copie avec services bloqués/débloqués ; passe en services propres au client."""
    block_set, unblock_set = frozenset(block), frozenset(unblock)
    if block_set & unblock_set:
        raise ValueError("Un service ne peut être bloqué et débloqué à la fois")
    new = copy.deepcopy(dict(client))
    new["blocked_services"] = sorted((blocked(client) | block_set) - unblock_set)
    new["use_global_blocked_services"] = False
    return new
