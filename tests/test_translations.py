"""Les trois fichiers de traduction doivent avoir les mêmes clés."""

import json
from pathlib import Path

BASE = Path(__file__).parent.parent / "custom_components" / "adguard_clients"


def _paths(node, prefix=""):
    if isinstance(node, dict):
        out = set()
        for key, value in node.items():
            out |= _paths(value, f"{prefix}{key}.")
        return out
    return {prefix.rstrip(".")}


def _load(rel):
    return json.loads((BASE / rel).read_text(encoding="utf-8"))


def test_translations_keys_match():
    strings = _load("strings.json")
    en = _load("translations/en.json")
    fr = _load("translations/fr.json")
    assert _paths(strings) == _paths(en) == _paths(fr)
    assert (
        fr["entity"]["switch"]["parental"]["name"]
        != en["entity"]["switch"]["parental"]["name"]
    )
