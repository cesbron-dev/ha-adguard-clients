"""Tests des modifications pures de fiches client."""

from __future__ import annotations

import copy

import pytest

from custom_components.adguard_clients.client_ops import (
    SETTING_KEYS,
    blocked,
    client_ids,
    setting_value,
    with_blocked,
    with_flag,
    with_setting,
)
from tests.fake_adguard import sample_client


def test_with_setting_forces_local_settings() -> None:
    c = sample_client("A", ["1"], use_global_settings=True)
    new = with_setting(c, "parental_enabled", True)
    assert new["parental_enabled"] is True
    assert new["use_global_settings"] is False
    assert setting_value(new, "parental_enabled") is True


def test_with_setting_safe_search_nested() -> None:
    c = sample_client("A", ["1"])
    new = with_setting(c, "safe_search", True)
    assert new["safe_search"] == {**c["safe_search"], "enabled": True}
    assert setting_value(new, "safe_search") is True


def test_with_setting_safe_search_missing_creates_it() -> None:
    new = with_setting({"name": "X"}, "safe_search", True)
    assert new["safe_search"] == {"enabled": True}


def test_with_setting_unknown_key_raises() -> None:
    with pytest.raises(ValueError):
        with_setting(sample_client("A", ["1"]), "name", True)
    assert "safe_search" in SETTING_KEYS


def test_with_flag_only_touches_flag() -> None:
    c = sample_client("A", ["1"], use_global_settings=False)
    new = with_flag(c, "use_global_settings", True)
    assert new["use_global_settings"] is True
    assert {k: v for k, v in new.items() if k != "use_global_settings"} == {
        k: v for k, v in c.items() if k != "use_global_settings"
    }


def test_with_blocked_union_difference_sorted() -> None:
    c = sample_client("A", ["1"], blocked_services=["tiktok"], use_global_blocked_services=True)
    new = with_blocked(c, ["youtube", "roblox"], ["tiktok"])
    assert new["blocked_services"] == ["roblox", "youtube"]
    assert new["use_global_blocked_services"] is False


def test_with_blocked_conflict_raises() -> None:
    with pytest.raises(ValueError):
        with_blocked(sample_client("A", ["1"]), ["youtube"], ["youtube"])


def test_ops_do_not_mutate_input_and_keep_other_fields() -> None:
    c = sample_client(
        "A",
        ["1"],
        tags=["t"],
        upstreams=["1.1.1.1"],
        blocked_services_schedule={"time_zone": "Europe/Paris", "mon": {"start": 0, "end": 1}},
    )
    original = copy.deepcopy(c)
    for new in (
        with_setting(c, "safe_search", True),
        with_flag(c, "use_global_blocked_services", True),
        with_blocked(c, ["youtube"], []),
    ):
        for key in ("blocked_services_schedule", "upstreams", "tags", "ids", "name"):
            assert new[key] == original[key]
        assert new["blocked_services_schedule"] is not c["blocked_services_schedule"]
    assert c == original


def test_ops_tolerate_missing_fields() -> None:
    c = {"name": "X"}
    assert blocked(c) == frozenset()
    assert blocked({"blocked_services": None}) == frozenset()
    assert setting_value(c, "safe_search") is False
    assert setting_value(c, "parental_enabled") is False
    assert with_blocked(c, ["youtube"], [])["blocked_services"] == ["youtube"]
    assert client_ids(c) == frozenset()
    assert client_ids({"ids": None}) == frozenset()
    assert client_ids({"ids": ["a", "b"]}) == frozenset({"a", "b"})
