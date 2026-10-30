"""Rapprochement des fiches AdGuard avec des identifiants stables (uid)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .client_ops import client_ids


@dataclass(frozen=True)
class KnownClient:
    """Client déjà connu : nom et identifiants à la dernière synchronisation.

    `present` : le client figurait dans la dernière lecture réussie d'AdGuard.
    """

    name: str
    ids: frozenset[str]
    present: bool = True


def match_clients(
    known: Mapping[str, KnownClient],
    current: Sequence[Mapping[str, Any]],
    new_uid: Callable[[], str],
) -> dict[str, dict[str, Any]]:
    """Associe chaque fiche courante nommée à un uid (existant ou nouveau)."""
    result: dict[str, dict[str, Any]] = {}
    remaining: list[Mapping[str, Any]] = []
    named = [f for f in current if f.get("name")]

    # 1. champ uid fourni par AdGuard
    for fiche in named:
        if fiche.get("uid"):
            result[str(fiche["uid"])] = dict(fiche)
        else:
            remaining.append(fiche)

    # 2. même nom qu'un client connu
    unnamed: list[Mapping[str, Any]] = []
    for fiche in remaining:
        uid = next(
            (u for u, k in known.items() if k.name == fiche["name"] and u not in result),
            None,
        )
        if uid is None:
            unnamed.append(fiche)
        else:
            result[uid] = dict(fiche)

    # 3. recoupement d'identifiants non ambigu, parmi les uid présents à la
    #    dernière lecture réussie (jamais un client supprimé), sinon 4. nouvel uid
    candidates = [u for u, k in known.items() if k.present and u not in result]
    for fiche in unnamed:
        ids = client_ids(fiche)
        overlap = [u for u in candidates if known[u].ids & ids]
        uid = None
        if len(overlap) == 1:
            others = (client_ids(g) for g in unnamed if g is not fiche)
            if not any(known[overlap[0]].ids & o for o in others):
                uid = overlap[0]
        if uid is None:
            uid = new_uid()
        result[uid] = dict(fiche)
    return result
