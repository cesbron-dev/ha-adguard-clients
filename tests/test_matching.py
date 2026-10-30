"""Tests du rapprochement des fiches AdGuard avec les clients connus."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from custom_components.adguard_clients.matching import KnownClient, match_clients


def gen() -> Callable[[], str]:
    """Générateur déterministe "n1", "n2", ..."""
    counter = iter(range(1, 1000))
    return lambda: f"n{next(counter)}"


def c(name: str, ids: list[str], **extra: Any) -> dict[str, Any]:
    return {"name": name, "ids": ids, **extra}


def test_new_clients_get_new_uids() -> None:
    a, b = c("A", ["1"]), c("B", ["2"])
    assert match_clients({}, [a, b], gen()) == {"n1": a, "n2": b}


def test_same_name_keeps_uid() -> None:
    known = {"u1": KnownClient("A", frozenset({"1"}))}
    a = c("A", ["9"])
    assert match_clients(known, [a], gen()) == {"u1": a}


def test_rename_matched_by_single_id_overlap() -> None:
    known = {"u1": KnownClient("A", frozenset({"1", "mac"}))}
    a2 = c("A2", ["mac"])
    assert match_clients(known, [a2], gen()) == {"u1": a2}


def test_ambiguous_overlap_creates_new() -> None:
    known = {
        "u1": KnownClient("A", frozenset({"1"})),
        "u2": KnownClient("B", frozenset({"1"})),
    }
    cc = c("C", ["1"])
    assert match_clients(known, [cc], gen()) == {"n1": cc}


def test_overlap_shared_with_other_remaining_client_creates_new() -> None:
    known = {"u1": KnownClient("A", frozenset({"1", "2"}))}
    x, y = c("X", ["1"]), c("Y", ["2"])
    assert match_clients(known, [x, y], gen()) == {"n1": x, "n2": y}


def test_name_match_wins_over_id_overlap() -> None:
    known = {
        "u1": KnownClient("A", frozenset({"1"})),
        "u2": KnownClient("B", frozenset({"2"})),
    }
    b = c("B", ["1"])
    assert match_clients(known, [b], gen()) == {"u2": b}


def test_rename_and_all_ids_changed_creates_new() -> None:
    known = {"u1": KnownClient("A", frozenset({"1"}))}
    z = c("Z", ["9"])
    assert match_clients(known, [z], gen()) == {"n1": z}


def test_adguard_uid_field_wins() -> None:
    known = {"u1": KnownClient("A", frozenset({"1"}))}
    a = c("A", ["1"], uid="abc")
    assert match_clients(known, [a], gen()) == {"abc": a}


def test_uid_taken_by_step_1_is_not_reused_by_name() -> None:
    known = {"u1": KnownClient("A", frozenset({"1"}))}
    x = c("X", ["5"], uid="u1")
    a = c("A", ["1"])
    assert match_clients(known, [x, a], gen()) == {"u1": x, "n1": a}


def test_absent_known_client_is_not_returned() -> None:
    known = {"u1": KnownClient("A", frozenset({"1"}))}
    assert match_clients(known, [], gen()) == {}


def test_nameless_entries_ignored() -> None:
    a = c("A", ["1"])
    assert match_clients({}, [{"ids": ["x"]}, {"name": "", "ids": ["y"]}, a], gen()) == {
        "n1": a
    }


def test_deleted_client_ids_reused_by_new_client_creates_new() -> None:
    known = {"u1": KnownClient("A", frozenset({"1", "mac"}), present=False)}
    tom = c("Tom", ["1"])
    assert match_clients(known, [tom], gen()) == {"n1": tom}


def test_absent_client_reappearing_with_same_name_keeps_uid() -> None:
    known = {"u1": KnownClient("A", frozenset({"1"}), present=False)}
    a = c("A", ["9"])
    assert match_clients(known, [a], gen()) == {"u1": a}


def test_known_client_present_by_default() -> None:
    assert KnownClient("A", frozenset({"1"})).present is True
