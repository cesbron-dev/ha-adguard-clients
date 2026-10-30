"""Fixtures communes."""

from unittest.mock import patch

import pytest

from .fake_adguard import FakeAdGuard, sample_client


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Active le chargement de `custom_components/` dans chaque test."""
    yield


@pytest.fixture
def fake_adguard() -> FakeAdGuard:
    """Faux AdGuard en mémoire avec deux clients."""
    return FakeAdGuard(
        clients=[
            sample_client("iPad Gabin", ["192.168.0.50", "aa:bb:cc:dd:ee:01"]),
            sample_client("TV", ["192.168.0.60"]),
        ],
        catalog={
            "youtube": "YouTube",
            "roblox": "Roblox",
            "tiktok": "TikTok",
            "netflix": "Netflix",
            "disneyplus": "Disney+",
            "twitch": "Twitch",
            "discord": "Discord",
        },
    )


@pytest.fixture
def patch_api(fake_adguard):
    """Remplace AdGuardApi par le faux dans l'intégration et le config flow."""
    with (
        patch("custom_components.adguard_clients.AdGuardApi", return_value=fake_adguard),
        patch(
            "custom_components.adguard_clients.config_flow.AdGuardApi",
            return_value=fake_adguard,
        ),
    ):
        yield fake_adguard
