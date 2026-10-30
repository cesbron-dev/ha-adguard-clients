"""Constantes de l'intégration AdGuard Clients."""

DOMAIN = "adguard_clients"

CONF_URL = "url"
CONF_VERIFY_SSL = "verify_ssl"
CONF_SERVICES = "services"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SERVICES: tuple[str, ...] = (
    "youtube",
    "roblox",
    "tiktok",
    "netflix",
    "disneyplus",
    "twitch",
)
DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 3600
