# AdGuard Clients — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Intégration HACS `adguard_clients` qui expose chaque client persistant de une ou plusieurs instances AdGuard Home comme appareil HA, avec switches de réglages, switches de services bloqués et un service d'écriture atomique.

**Architecture:** Un client HTTP mince (`api.py`) ; deux modules purs sans import HA (`matching.py` pour l'identité stable des clients, `client_ops.py` pour les modifications de fiche) ; un `DataUpdateCoordinator` par entrée qui lit les clients, tient la table `uid ↔ client` dans un `Store` et porte la seule voie d'écriture (verrou, lecture fraîche, POST, relecture). Les entités et le service ne font que déléguer au coordinateur.

**Tech Stack:** Home Assistant 2026.10, Python 3.14, aiohttp (session HA), pytest-homeassistant-custom-component 0.13.375, uv.

**Spec:** `docs/superpowers/specs/2026-10-29-ha-adguard-clients-design.md`

## Global Constraints

- Dépôt : `/Users/olivier/dev/github.com/cesbron-dev/ha-adguard-clients`, branche de travail `feat/integration` (créée en Task 1 à partir de `main`).
- Domaine `adguard_clients` ; dossier `custom_components/adguard_clients/`.
- HA ≥ 2026.10 (`hacs.json` : `"homeassistant": "2026.10.0"`), Python 3.14, aucune dépendance externe (`"requirements": []`), session via `async_get_clientsession(hass, verify_ssl=...)`.
- Tests : `.venv/bin/pytest -W error -q` doit passer sans avertissement à la fin de chaque tâche.
- Textes d'interface en français dans `translations/fr.json`, anglais dans `strings.json` et `translations/en.json` (mêmes clés).
- Écriture AdGuard uniquement via `POST /control/clients/update` avec la fiche **complète** ; jamais d'état optimiste.
- `blocked_services_schedule` et tous les champs non visés sont renvoyés tels quels.
- Services par défaut : `youtube`, `roblox`, `tiktok`, `netflix`, `disneyplus`, `twitch` (filtrés par le catalogue).
- Intervalle de rafraîchissement : défaut 30 s, bornes 10–3600 s.
- Commits en français, style `feat: …`, terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Ne jamais pousser ni créer de dépôt GitHub (le contrôleur demande à Olivier).

## Review Focus

1. Fiche AdGuard incomplète (`blocked_services: null`, pas de `safe_search`, pas de `ids`) → traitée comme vide / faux, pas de plantage. Test en Task 2 (`test_ops_tolerate_missing_fields`) et Task 5 (`test_client_with_null_fields_creates_entities`).
2. Client renommé dans AdGuard entre le dernier rafraîchissement et une écriture → l'écriture vise le nouveau nom (rapprochement sur la lecture fraîche). Test en Task 4 (`test_write_follows_rename_since_last_refresh`).
3. Deux instances avec un client du même nom → appareils et `unique_id` distincts. Test en Task 5 (`test_two_instances_same_client_name`).
4. Service retiré du catalogue AdGuard mais encore dans les options → pas de switch, avertissement, pas d'erreur. Test en Task 6 (`test_unknown_service_in_options_is_skipped`).
5. `set_blocked_services` sur un client en mode global → écrit la liste et `use_global_blocked_services: false` ; les switches redeviennent disponibles. Test en Task 7 (`test_service_leaves_global_mode`).

## Structure des fichiers

```
custom_components/adguard_clients/
  __init__.py        setup/unload d'entrée, runtime_data, enregistrement du service (async_setup)
  manifest.json      domaine, config_flow, iot_class local_polling
  const.py           DOMAIN, clés de config/options, défauts
  api.py             AdGuardApi + exceptions
  matching.py        KnownClient, match_clients (pur)
  client_ops.py      with_setting, with_flag, with_blocked, client_ids (pur)
  coordinator.py     AdGuardClientsCoordinator (lecture, Store, écriture)
  entity.py          AdGuardClientEntity (appareil client), instance_device_info
  switch.py          réglages, use_global_*, services
  sensor.py          Services bloqués
  binary_sensor.py   Connecté (appareil d'instance)
  config_flow.py     user, reauth, reconfigure, options
  services.py        set_blocked_services
  services.yaml
  strings.json, translations/en.json, translations/fr.json
hacs.json, README.md, pyproject.toml, requirements_test.txt
tests/conftest.py, tests/fake_adguard.py, tests/test_*.py
```

---

### Task 1: Squelette, outillage et client HTTP

**Files:**
- Create: `pyproject.toml`, `requirements_test.txt`, `hacs.json`, `custom_components/__init__.py` (vide), `custom_components/adguard_clients/{__init__.py,manifest.json,const.py,api.py}`, `tests/__init__.py`, `tests/conftest.py`, `tests/fake_adguard.py`, `tests/test_api.py`

**Interfaces:**
- Produces:
  - `const.py` : `DOMAIN = "adguard_clients"`, `CONF_URL = "url"`, `CONF_VERIFY_SSL = "verify_ssl"`, `CONF_SERVICES = "services"`, `CONF_SCAN_INTERVAL = "scan_interval"`, `DEFAULT_SERVICES: tuple[str, ...]`, `DEFAULT_SCAN_INTERVAL = 30`, `MIN_SCAN_INTERVAL = 10`, `MAX_SCAN_INTERVAL = 3600`. (`CONF_USERNAME`, `CONF_PASSWORD`, `CONF_NAME` viennent de `homeassistant.const`.)
  - `api.py` :
    - `class AdGuardError(Exception)`, `class AdGuardConnectionError(AdGuardError)`, `class AdGuardAuthError(AdGuardError)`.
    - `class AdGuardApi: __init__(self, session: aiohttp.ClientSession, url: str, username: str, password: str)`.
    - `async status() -> dict[str, Any]` (`GET /control/status`).
    - `async clients() -> list[dict[str, Any]]` (`GET /control/clients`, clé `clients`, `None` → `[]`).
    - `async services_catalog() -> dict[str, str]` (`GET /control/blocked_services/all`, `id → name`, accepte la clé `blocked_services` ou `services`).
    - `async update_client(name: str, data: dict[str, Any]) -> None` (`POST /control/clients/update`, corps `{"name": name, "data": data}`).
    - `normalize_url(url: str) -> str` (minuscule, sans `/` final) — sert d'`unique_id`.
  - `tests/fake_adguard.py` : `class FakeAdGuard` en mémoire avec la même interface que `AdGuardApi` (`status`, `clients`, `services_catalog`, `update_client`), attributs `clients: list[dict]`, `catalog: dict[str, str]`, `updates: list[tuple[str, dict]]` (journal des écritures), `fail_next: Exception | None` (levée au prochain appel puis remise à `None`) ; `update_client` remplace la fiche dont `name` correspond par `data` (copie profonde) ou lève `AdGuardError` si absente. Fonction `sample_client(name: str, ids: list[str], **overrides) -> dict` qui produit une fiche réaliste v0.107 (`name`, `ids`, `tags: []`, `use_global_settings: False`, `filtering_enabled: True`, `parental_enabled: False`, `safebrowsing_enabled: False`, `safe_search: {"enabled": False, "bing": True, "duckduckgo": True, "google": True, "pixabay": True, "yandex": True, "youtube": True}`, `use_global_blocked_services: False`, `blocked_services: []`, `blocked_services_schedule: {"time_zone": "Local"}`, `upstreams: []`, `ignore_querylog: False`, `ignore_statistics: False`, `upstreams_cache_enabled: False`, `upstreams_cache_size: 0`).
  - `tests/conftest.py` : fixture autouse `auto_enable_custom_integrations` (comme dans `ha-parental-control`), fixture `fake_adguard` → `FakeAdGuard` avec 2 clients (`sample_client("iPad Gabin", ["192.168.0.50", "aa:bb:cc:dd:ee:01"])`, `sample_client("TV", ["192.168.0.60"])`) et un catalogue `{"youtube": "YouTube", "roblox": "Roblox", "tiktok": "TikTok", "netflix": "Netflix", "disneyplus": "Disney+", "twitch": "Twitch", "discord": "Discord"}` ; fixture `patch_api(fake_adguard)` qui patche `custom_components.adguard_clients.AdGuardApi` **et** `custom_components.adguard_clients.config_flow.AdGuardApi` pour renvoyer `fake_adguard`.

- [ ] **Step 1: Créer la branche et l'environnement**

```bash
cd /Users/olivier/dev/github.com/cesbron-dev/ha-adguard-clients
git checkout -b feat/integration
uv venv --python 3.14 .venv && uv pip install --python .venv/bin/python -r requirements_test.txt
```
`requirements_test.txt` : `pytest-homeassistant-custom-component==0.13.375`. `pyproject.toml` : `[tool.pytest.ini_options] asyncio_mode = "auto"`, `testpaths = ["tests"]`. `manifest.json` : `domain`, `name: "AdGuard Clients"`, `version: "0.1.0"`, `config_flow: true`, `iot_class: "local_polling"`, `integration_type: "hub"`, `dependencies: []`, `requirements: []`, `codeowners: ["@cesbron-dev"]`, `documentation: "https://github.com/cesbron-dev/ha-adguard-clients"`. `hacs.json` : `{"name": "AdGuard Clients", "homeassistant": "2026.10.0", "render_readme": true}`. `__init__.py` : minimal — import de `AdGuardApi` au niveau module (pour que le patch fonctionne) et `async_setup_entry` / `async_unload_entry` provisoires qui renvoient `True` (remplacés en Task 4).

- [ ] **Step 2: Écrire les tests de `api.py` (`tests/test_api.py`, avec `aioclient_mock`)**

```python
URL = "http://adguard.test:3000"

async def test_clients_returns_list_and_uses_basic_auth(hass, aioclient_mock):
    aioclient_mock.get(f"{URL}/control/clients", json={"clients": [{"name": "TV"}], "auto_clients": []})
    api = AdGuardApi(async_get_clientsession(hass), URL + "/", "admin", "pw")
    assert await api.clients() == [{"name": "TV"}]
    assert aioclient_mock.mock_calls[0][3]["Authorization"].startswith("Basic ")  # en-têtes

async def test_clients_null_is_empty(hass, aioclient_mock):  # {"clients": null} -> []
async def test_catalog_maps_id_to_name(hass, aioclient_mock):  # {"blocked_services": [{"id": "youtube", "name": "YouTube"}]} -> {"youtube": "YouTube"}
async def test_update_client_posts_full_payload(hass, aioclient_mock):
    # corps JSON exact == {"name": "TV", "data": {...fiche...}}
async def test_401_raises_auth_error(hass, aioclient_mock):  # status=401 et 403 -> AdGuardAuthError
async def test_network_error_raises_connection_error(hass, aioclient_mock):  # exc=aiohttp.ClientError() et TimeoutError -> AdGuardConnectionError
async def test_500_raises_adguard_error(hass, aioclient_mock):  # status=500 -> AdGuardError, mais ni AdGuardAuthError ni AdGuardConnectionError
def test_normalize_url():
    assert normalize_url("HTTPS://AdGuard-bdx.home.cesbron.dev/") == "https://adguard-bdx.home.cesbron.dev"
```

Si `aioclient_mock` ne permet pas de lire les en-têtes, vérifier l'auth en construisant l'API puis en inspectant l'argument `auth` passé (au choix de l'implémenteur), mais l'auth basique doit être testée.

- [ ] **Step 3: Vérifier l'échec** — `.venv/bin/pytest tests/test_api.py -q` → erreurs d'import.

- [ ] **Step 4: Implémenter `api.py`** — `aiohttp.BasicAuth`, `timeout=aiohttp.ClientTimeout(total=10)`, `raise_for_status` manuel : 401/403 → `AdGuardAuthError`, autre ≥ 400 → `AdGuardError`, `aiohttp.ClientError`/`TimeoutError` → `AdGuardConnectionError`.

- [ ] **Step 5: Vérifier** — `.venv/bin/pytest -W error -q` → tout passe.

- [ ] **Step 6: Commit** — `feat: squelette de l'intégration et client HTTP AdGuard`

---

### Task 2: Modules purs — identité des clients et modifications de fiche

**Files:**
- Create: `custom_components/adguard_clients/matching.py`, `custom_components/adguard_clients/client_ops.py`, `tests/test_matching.py`, `tests/test_client_ops.py`

**Interfaces:**
- Produces:
  - `matching.py` (aucun import HA) :
    - `@dataclass(frozen=True) class KnownClient: name: str; ids: frozenset[str]`
    - `def match_clients(known: Mapping[str, KnownClient], current: Sequence[Mapping[str, Any]], new_uid: Callable[[], str]) -> dict[str, dict[str, Any]]` — renvoie `uid → fiche` pour **chaque** fiche de `current` (ignorer celles sans `name`).
  - `client_ops.py` (aucun import HA) :
    - `SETTING_KEYS = ("filtering_enabled", "parental_enabled", "safebrowsing_enabled", "safe_search")`
    - `def client_ids(client: Mapping) -> frozenset[str]`
    - `def setting_value(client: Mapping, key: str) -> bool` (`safe_search` lit `safe_search.enabled` ; absent → `False`)
    - `def blocked(client: Mapping) -> frozenset[str]` (`None`/absent → vide)
    - `def with_setting(client: Mapping, key: str, value: bool) -> dict` — copie profonde, met la valeur et `use_global_settings = False`.
    - `def with_flag(client: Mapping, key: Literal["use_global_settings", "use_global_blocked_services"], value: bool) -> dict` — copie profonde, ne change que ce drapeau.
    - `def with_blocked(client: Mapping, block: Iterable[str], unblock: Iterable[str]) -> dict` — copie profonde, `blocked_services = sorted((blocked ∪ block) − unblock)`, `use_global_blocked_services = False` ; lève `ValueError` si `block ∩ unblock` non vide.

Algorithme de `match_clients` (spec, « Algorithme de rapprochement ») :

```
1. fiche avec champ "uid" non vide -> ce uid (chaîne).
2. sinon nom identique à known[uid].name (uid pas encore pris) -> uid.
3. restants : candidats = uids connus non pris ; pour la fiche f,
   C = {u ∈ candidats : known[u].ids ∩ ids(f) ≠ ∅}.
   Si |C| == 1 (= {u}) et qu'aucune AUTRE fiche restante ne partage d'id avec known[u].ids -> u.
4. sinon -> new_uid().
Les étapes 1 et 2 sont faites pour toutes les fiches avant l'étape 3.
```

- [ ] **Step 1: Tests `tests/test_matching.py`**

```python
def gen():  # générateur déterministe "n1", "n2", ...
def test_new_clients_get_new_uids(): match_clients({}, [c("A", ["1"]), c("B", ["2"])], gen()) -> {"n1": A, "n2": B}
def test_same_name_keeps_uid(): known {"u1": KnownClient("A", {"1"})}, current [c("A", ["9"])] -> {"u1": ...}
def test_rename_matched_by_single_id_overlap(): known u1=("A",{"1","mac"}), current [c("A2", ["mac"])] -> u1
def test_ambiguous_overlap_creates_new(): known u1=("A",{"1"}), u2=("B",{"1"}); current [c("C", ["1"])] -> nouveau uid
def test_overlap_shared_with_other_remaining_client_creates_new(): known u1=("A",{"1","2"}); current [c("X",["1"]), c("Y",["2"])] -> deux nouveaux uids
def test_name_match_wins_over_id_overlap(): known u1=("A",{"1"}), u2=("B",{"2"}); current [c("B",["1"])] -> u2
def test_rename_and_all_ids_changed_creates_new(): known u1=("A",{"1"}); current [c("Z",["9"])] -> nouveau
def test_adguard_uid_field_wins(): current [c("A",["1"], uid="abc")] -> {"abc": ...}
def test_absent_known_client_is_not_returned(): known u1, current [] -> {}
def test_nameless_entries_ignored()
```

- [ ] **Step 2: Tests `tests/test_client_ops.py`**

```python
def test_with_setting_forces_local_settings():  # with_setting(c, "parental_enabled", True) -> parental_enabled True, use_global_settings False
def test_with_setting_safe_search_nested():  # safe_search.enabled True, autres clés safe_search conservées
def test_with_flag_only_touches_flag():  # tout le reste == original
def test_with_blocked_union_difference_sorted():  # blocked ["tiktok"], block ["youtube","roblox"], unblock ["tiktok"] -> ["roblox","youtube"], use_global_blocked_services False
def test_with_blocked_conflict_raises():  # block ["youtube"], unblock ["youtube"] -> ValueError
def test_ops_do_not_mutate_input_and_keep_other_fields():  # blocked_services_schedule, upstreams, tags, ids identiques ; original inchangé
def test_ops_tolerate_missing_fields():  # {"name": "X"} : blocked() == frozenset(), setting_value(...,"safe_search") is False, with_blocked OK, client_ids == frozenset()
```

- [ ] **Step 3: Vérifier l'échec**, **Step 4: Implémenter**, **Step 5: `.venv/bin/pytest -W error -q`**, **Step 6: Commit** — `feat: identité stable des clients et modifications de fiche`

---

### Task 3: Config flow (user, reauth, reconfigure)

**Files:**
- Create: `custom_components/adguard_clients/config_flow.py`, `strings.json`, `translations/en.json`, `translations/fr.json`, `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `AdGuardApi`, `AdGuardAuthError`, `AdGuardConnectionError`, `normalize_url` (Task 1).
- Produces: entrée `data = {url, username, password, verify_ssl}`, `title = name`, `unique_id = normalize_url(url)`. Clés de traduction : `config.step.user` (champs `name`, `url`, `username`, `password`, `verify_ssl`), `config.step.reauth_confirm` (`username`, `password`), `config.step.reconfigure` (`url`, `username`, `password`, `verify_ssl`), `config.error.cannot_connect`, `config.error.invalid_auth`, `config.error.unknown`, `config.abort.already_configured`, `config.abort.reauth_successful`, `config.abort.reconfigure_successful`, `config.abort.unique_id_mismatch` non utilisé (reconfigure peut changer l'URL : on met à jour `unique_id`). Défaut du champ `name` : `"AdGuard Home"`. Défaut `verify_ssl` : `True`.

Le test de connexion appelle `api.status()` avec une session `async_get_clientsession(hass, verify_ssl=...)`.

- [ ] **Step 1: Tests**

```python
async def test_user_flow_creates_entry(hass, patch_api):
    # saisie name="AdGuard Bordeaux", url="https://Adguard-bdx.home.cesbron.dev/", username, password, verify_ssl True
    # -> CREATE_ENTRY, title "AdGuard Bordeaux", data["url"] == "https://adguard-bdx.home.cesbron.dev",
    #    unique_id == "https://adguard-bdx.home.cesbron.dev"
async def test_user_flow_cannot_connect(hass, patch_api, fake_adguard):  # fail_next = AdGuardConnectionError -> errors {"base": "cannot_connect"}
async def test_user_flow_invalid_auth(...)  # AdGuardAuthError -> {"base": "invalid_auth"}
async def test_user_flow_unknown_error(...)  # Exception -> {"base": "unknown"}
async def test_duplicate_url_aborts(...)  # même URL normalisée -> ABORT already_configured
async def test_reauth_updates_password(...)  # MockConfigEntry, entry.start_reauth_flow(hass) -> form reauth_confirm -> ABORT reauth_successful, data["password"] nouveau
async def test_reconfigure_changes_url(...)  # entry.start_reconfigure_flow(hass) -> ABORT reconfigure_successful, data["url"] et unique_id mis à jour
```

Patcher `async_setup_entry` (`custom_components.adguard_clients.async_setup_entry`, `return_value=True`) dans ces tests.

- [ ] **Step 2–5:** échec, implémentation (`ConfigFlow`, `VERSION = 1`, `async_step_user`, `async_step_reauth` → `async_step_reauth_confirm`, `async_step_reconfigure`, `async_update_reload_and_abort`), tests verts, `-W error`.
- [ ] **Step 6: Commit** — `feat: config flow AdGuard Clients`

---

### Task 4: Coordinateur — lecture, identité persistée, écriture

**Files:**
- Create: `custom_components/adguard_clients/coordinator.py`, `tests/test_coordinator.py`
- Modify: `custom_components/adguard_clients/__init__.py`

**Interfaces:**
- Consumes: `AdGuardApi` (Task 1), `match_clients`, `KnownClient`, `client_ids` (Task 2).
- Produces:
  - `@dataclass class AdGuardData: clients: dict[str, dict[str, Any]]` (uid → fiche, clients présents seulement).
  - `class AdGuardClientsCoordinator(DataUpdateCoordinator[AdGuardData])` :
    - `__init__(self, hass, entry: ConfigEntry, api: AdGuardApi, scan_interval: int)`
    - `catalog: dict[str, str]` (rempli par `async_load()`)
    - `known: dict[str, KnownClient]` (tous les uids jamais vus, présents ou non)
    - `async async_load() -> None` — charge le `Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")` (`{"clients": {uid: {"name": str, "ids": list[str]}}}`) et le catalogue ; erreur réseau → `ConfigEntryNotReady`, auth → `ConfigEntryAuthFailed`.
    - `_async_update_data()` — `api.clients()`, `match_clients(self.known, ..., lambda: uuid4().hex)`, met à jour `known` (nom et ids des présents) et sauvegarde le Store si changé (`async_delay_save` 1 s ou `async_save`), renvoie `AdGuardData`. `AdGuardConnectionError`/`AdGuardError` → `UpdateFailed` ; `AdGuardAuthError` → `ConfigEntryAuthFailed`.
    - `async async_update_client(self, uid: str, mutate: Callable[[dict[str, Any]], dict[str, Any]]) -> None` — sous `self._write_lock` (`asyncio.Lock`) : lecture fraîche `api.clients()`, rapprochement (même algorithme, met à jour `known`), fiche du `uid` absente → `HomeAssistantError(translation_domain=DOMAIN, translation_key="client_not_found")` ; `api.update_client(<nom actuel dans la lecture fraîche>, mutate(fiche))` ; erreurs : `AdGuardAuthError` → `entry.async_start_reauth(hass)` puis `HomeAssistantError(translation_key="auth_failed")`, autres → `HomeAssistantError(translation_key="write_failed")` ; enfin `await self.async_refresh()` (une relecture en échec ne fait **pas** échouer l'appel ; journaliser un avertissement).
    - `client_device_identifier(uid) -> tuple[str, str]` = `(DOMAIN, f"{entry_id}_{uid}")`.
  - `__init__.py` : `type AdGuardConfigEntry = ConfigEntry[AdGuardClientsCoordinator]` ; `async_setup_entry` crée l'API (session `async_get_clientsession(hass, verify_ssl=entry.data[CONF_VERIFY_SSL])`), le coordinateur (`scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)`), `await coordinator.async_load()`, `await coordinator.async_config_entry_first_refresh()`, `entry.runtime_data = coordinator`, enregistre l'appareil d'instance (identifiant `(DOMAIN, entry.entry_id)`, nom = titre, fabricant « AdGuard Team », `sw_version` = `status()["version"]`, `configuration_url` = URL), transmet les plateformes `PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]` (fichiers vides acceptables à ce stade : créer `async_setup_entry` de plateforme qui n'ajoute rien), écoute les mises à jour d'options (`entry.add_update_listener` → reload). `async_unload_entry` décharge les plateformes. Ajouter les clés `exceptions.client_not_found`, `exceptions.auth_failed`, `exceptions.write_failed` aux traductions.

- [ ] **Step 1: Tests (`tests/test_coordinator.py`, avec `patch_api` et `MockConfigEntry` du domaine)**

```python
async def test_setup_creates_instance_device_and_uids(hass, patch_api):  # entrée chargée, 2 uids dans coordinator.data.clients, appareil d'instance avec sw_version
async def test_uids_persist_across_reload(hass, patch_api, hass_storage):  # mêmes uids après async_reload ; hass_storage[f"adguard_clients.{entry_id}"] contient les deux noms
async def test_rename_keeps_uid(hass, patch_api, fake_adguard):  # renommer "iPad Gabin" -> "iPad de Gabin" dans fake, async_refresh -> même uid, nouveau nom
async def test_absent_client_kept_in_known(...)  # retirer TV -> absent de data.clients, présent dans coordinator.known
async def test_write_reads_fresh_and_keeps_fields(hass, patch_api, fake_adguard):
    # modifier upstreams du client dans fake APRÈS le dernier refresh, puis
    # async_update_client(uid, lambda c: with_setting(c, "parental_enabled", True))
    # -> fake.updates[-1][1]["upstreams"] == valeur modifiée ; parental_enabled True
async def test_write_follows_rename_since_last_refresh(...)  # renommer dans fake sans refresh, écrire -> update_client appelé avec le NOUVEAU nom
async def test_concurrent_writes_are_serialized(...)  # deux async_update_client en asyncio.gather sur 2 services différents -> les deux présents dans la fiche finale
async def test_write_missing_client_raises(...)  # client supprimé dans fake -> HomeAssistantError translation_key "client_not_found"
async def test_write_auth_error_starts_reauth(...)  # fail_next=AdGuardAuthError sur update -> HomeAssistantError "auth_failed" et un flux reauth en cours (hass.config_entries.flow.async_progress())
async def test_write_ok_refresh_fails_does_not_raise(...)  # update OK puis clients() en échec -> pas d'exception, coordinator.last_update_success False
async def test_refresh_network_error_marks_unavailable(...)  # -> last_update_success False
async def test_setup_catalog_failure_not_ready(...)  # fail_next sur services_catalog -> entry.state SETUP_RETRY
```

Pour `fail_next` ciblé, l'implémenteur peut enrichir `FakeAdGuard` d'un `fail_on: dict[str, Exception]` (nom de méthode → exception levée une fois).

- [ ] **Step 2–5:** échec, implémentation, verts, `-W error`.
- [ ] **Step 6: Commit** — `feat: coordinateur AdGuard Clients avec identité persistée et écriture sûre`

---

### Task 5: Entités des clients et de l'instance

**Files:**
- Create: `custom_components/adguard_clients/entity.py`, `tests/test_entities.py`
- Modify: `switch.py`, `sensor.py`, `binary_sensor.py`, traductions

**Interfaces:**
- Consumes: coordinateur (Task 4), `setting_value`, `blocked`, `with_setting`, `with_flag`, `with_blocked` (Task 2).
- Produces:
  - `entity.py` : `class AdGuardClientEntity(CoordinatorEntity[AdGuardClientsCoordinator])` avec `__init__(coordinator, uid: str, key: str)`, `_attr_has_entity_name = True`, `unique_id = f"{entry_id}_{uid}_{key}"`, `device_info` : identifiants `coordinator.client_device_identifier(uid)`, `name` = nom AdGuard actuel, `manufacturer = "AdGuard Home"`, `model = "Client"`, `via_device = (DOMAIN, entry_id)` ; propriété `client -> dict | None` (`coordinator.data.clients.get(uid)`) ; `available` = `super().available and self.client is not None`. Le nom de l'appareil suit les renommages : à chaque mise à jour du coordinateur, si le nom AdGuard a changé, `device_registry.async_update_device(device_id, name=...)` (sans toucher `name_by_user`).
  - Ajout dynamique : chaque plateforme mémorise les uids déjà créés et, sur `coordinator.async_add_listener`, ajoute les entités des nouveaux uids.
  - `switch.py` :
    - réglages, clés `filtering`, `parental`, `safebrowsing`, `safe_search` → champs `filtering_enabled`, `parental_enabled`, `safebrowsing_enabled`, `safe_search` ; `is_on = setting_value(...)` ; disponible seulement si `use_global_settings` est faux ; écriture `with_setting`.
    - `use_global_settings`, `use_global_blocked_services` : `EntityCategory.CONFIG`, écriture `with_flag`.
    - services : clé `svc_<id>`, `translation_key = "blocked_service"`, `translation_placeholders = {"service": catalog[id]}`, `is_on = id in blocked(client)`, disponible seulement si `use_global_blocked_services` est faux ; écriture `with_blocked(c, [id], [])` / `with_blocked(c, [], [id])`. Liste des services = `coordinator.services` (calculée en Task 6 ; en Task 5, utiliser `DEFAULT_SERVICES` filtrés par le catalogue via une propriété `coordinator.services: list[str]` que la Task 6 remplacera par la version options).
    - toutes les écritures passent par `coordinator.async_update_client(uid, mutate)` ; pas d'état optimiste.
  - `sensor.py` : clé `blocked_services`, valeur = `len(blocked(client))`, attributs `services` (liste **triée**), `ids` (liste), `tags`, `adguard_name`, `use_global_blocked_services`.
  - `binary_sensor.py` : sur l'appareil d'instance, `translation_key = "connected"`, `BinarySensorDeviceClass.CONNECTIVITY`, `EntityCategory.DIAGNOSTIC`, `is_on = coordinator.last_update_success`, toujours disponible.
  - `__init__.py` : `async_remove_config_entry_device(hass, entry, device) -> bool` = vrai si l'appareil est un client dont l'uid n'est pas dans `coordinator.data.clients`, faux pour l'appareil d'instance.
  - Traductions : `entity.switch.{filtering,parental,safebrowsing,safe_search,use_global_settings,use_global_blocked_services,blocked_service}.name` (fr : « Filtrage », « Contrôle parental », « Navigation sécurisée », « Recherche sécurisée », « Utiliser les réglages globaux », « Utiliser les services bloqués globaux », « Bloquer {service} »), `entity.sensor.blocked_services.name` (« Services bloqués »), `entity.binary_sensor.connected.name` (« Connecté »).

Les tests retrouvent les entités par `unique_id` via le registre (`er.async_get(hass).async_get_entity_id("switch", DOMAIN, uid_key)`), pas par `entity_id`, la langue de test étant l'anglais.

- [ ] **Step 1: Tests**

```python
async def test_client_devices_and_entities(hass, patch_api):  # 2 appareils clients via_device instance ; par client : 6 switches réglages/flags + 6 services par défaut + 1 sensor
async def test_service_switch_state_and_toggle(hass, patch_api, fake_adguard):  # turn_on youtube -> fake fiche blocked_services ["youtube"], use_global_blocked_services False ; état on après ; turn_off -> []
async def test_setting_switch_forces_local_settings(...)  # turn_on parental -> parental_enabled True, use_global_settings False
async def test_global_blocked_services_makes_service_switches_unavailable(...)  # fiche use_global_blocked_services True -> switches svc indisponibles, switch flag on
async def test_global_settings_makes_setting_switches_unavailable(...)
async def test_flag_switch_writes_only_flag(...)  # turn_off use_global_blocked_services -> seule différence dans la fiche
async def test_sensor_attributes(...)  # blocked ["tiktok","discord","youtube"] -> state "3", attributes["services"] == ["discord","tiktok","youtube"], ids, adguard_name
async def test_new_client_added_on_refresh(...)  # ajouter un client dans fake, refresh -> nouvel appareil et entités
async def test_rename_keeps_entity_and_updates_device_name(...)  # même entity_id, device.name nouveau
async def test_absent_client_unavailable_and_removable(...)  # entités indisponibles ; async_remove_config_entry_device True ; appareil d'instance -> False
async def test_two_instances_same_client_name(...)  # deux entrées (URLs différentes, deux FakeAdGuard) avec "TV" -> 2 appareils, unique_ids distincts
async def test_client_with_null_fields_creates_entities(...)  # fiche {"name": "Vieux", "ids": None, "blocked_services": None} -> entités créées, sensor "0"
async def test_connected_binary_sensor(...)  # on ; après échec de refresh -> off
async def test_write_failure_raises_and_state_unchanged(...)  # fail_on update_client -> HomeAssistantError, switch toujours off
```

- [ ] **Step 2–5:** échec, implémentation, verts, `-W error`.
- [ ] **Step 6: Commit** — `feat: appareils et entités des clients AdGuard`

---

### Task 6: Options (services choisis, intervalle)

**Files:**
- Modify: `config_flow.py`, `coordinator.py`, `switch.py`, traductions
- Test: `tests/test_options.py`

**Interfaces:**
- Consumes: coordinateur, switches (Tasks 4–5).
- Produces:
  - `OptionsFlow` (`async_get_options_flow`) : étape `init` avec `services` (sélecteur multiple, `SelectSelector` options = catalogue `id → nom` trié par nom, `multiple=True`) et `scan_interval` (`NumberSelector` 10–3600, pas 1, unité s). Défauts : options actuelles, sinon `DEFAULT_SERVICES` ∩ catalogue, `DEFAULT_SCAN_INTERVAL`. Clés `options.step.init.data.{services,scan_interval}`.
  - `coordinator.services -> list[str]` : `entry.options[CONF_SERVICES]` si présent sinon `DEFAULT_SERVICES`, **filtré** par le catalogue (ordre conservé) ; chaque id inconnu → un avertissement journalisé une seule fois par chargement.
  - Au chargement des switches : supprimer du registre les entités `svc_*` de cette entrée dont l'id n'est plus dans `coordinator.services`.
  - Changement d'options → rechargement de l'entrée (listener posé en Task 4).

- [ ] **Step 1: Tests**

```python
async def test_options_flow_sets_services_and_interval(hass, patch_api):  # services ["youtube","discord"], scan_interval 60 -> entry.options ; après reload : switches svc youtube et discord seulement ; update_interval == 60 s
async def test_removed_service_switch_deleted_from_registry(...)  # retirer "roblox" -> entité absente du registre
async def test_default_services_filtered_by_catalog(...)  # catalogue sans "disneyplus" -> pas de switch disneyplus, avertissement dans caplog
async def test_unknown_service_in_options_is_skipped(...)  # options services ["youtube","inexistant"] -> un switch, avertissement, entrée LOADED
```

- [ ] **Step 2–5:** échec, implémentation, verts, `-W error`.
- [ ] **Step 6: Commit** — `feat: options de l'intégration AdGuard Clients`

---

### Task 7: Service `set_blocked_services`

**Files:**
- Create: `custom_components/adguard_clients/services.py`, `services.yaml`, `tests/test_services.py`
- Modify: `__init__.py` (`async_setup(hass, config)` enregistre le service une fois ; `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`), traductions

**Interfaces:**
- Consumes: coordinateur (`async_update_client`, `catalog`, `data`, `client_device_identifier`), `with_blocked`, `blocked` (Task 2).
- Produces: service `adguard_clients.set_blocked_services`, schéma `{vol.Required("device_id"): cv.string, vol.Optional("block", default=[]): [cv.string], vol.Optional("unblock", default=[]): [cv.string]}`, `supports_response=SupportsResponse.OPTIONAL`, réponse `{"blocked_services": sorted(list)}` (lue dans `coordinator.data` après relecture ; si la relecture a échoué, la liste écrite). Erreurs `ServiceValidationError(translation_domain=DOMAIN, ...)` : `invalid_device` (appareil inconnu, appareil d'instance, entrée non chargée, autre domaine), `unknown_service` (placeholder `services` = ids inconnus, triés, séparés par « , »), `conflicting_services` (placeholder idem). `services.yaml` : `device_id` avec sélecteur `device: {integration: adguard_clients}`, `block` et `unblock` avec sélecteur `text: {multiple: true}`. Traductions `services.set_blocked_services.{name,description,fields.*}` et `exceptions.{invalid_device,unknown_service,conflicting_services}`.

Résolution : `dr.async_get(hass).async_get(device_id)` → identifiant `(DOMAIN, "<entry_id>_<uid>")` → `hass.config_entries.async_get_entry(entry_id)` chargée → `entry.runtime_data`. Validation (catalogue, conflit) **avant** toute écriture. Écriture par `coordinator.async_update_client(uid, lambda c: with_blocked(c, block, unblock))`.

- [ ] **Step 1: Tests**

```python
async def test_service_blocks_and_unblocks_in_one_write(hass, patch_api, fake_adguard):  # blocked ["tiktok"], block ["youtube","roblox"], unblock ["tiktok"] -> une seule écriture (len(fake.updates) == 1), fiche ["roblox","youtube"], réponse {"blocked_services": ["roblox","youtube"]}
async def test_service_accepts_service_without_switch(...)  # block ["discord"] (pas dans les services choisis) -> écrit
async def test_service_unknown_service(...)  # block ["inexistant"] -> ServiceValidationError translation_key "unknown_service", aucune écriture
async def test_service_conflict(...)  # même id dans block et unblock -> "conflicting_services", aucune écriture
async def test_service_invalid_device(...)  # id inconnu, puis appareil d'instance -> "invalid_device"
async def test_service_leaves_global_mode(...)  # fiche use_global_blocked_services True -> après service : False, switches svc disponibles
async def test_service_client_gone(...)  # client supprimé dans fake -> HomeAssistantError "client_not_found"
```

- [ ] **Step 2–5:** échec, implémentation, verts, `-W error`.
- [ ] **Step 6: Commit** — `feat: service set_blocked_services`

---

### Task 8: README et finitions

**Files:**
- Create: `README.md`
- Modify: au besoin `manifest.json`, traductions

**Interfaces:** aucune nouvelle.

- [ ] **Step 1: README en français** : à quoi sert l'intégration (et ce qu'elle ne fait pas, d'après les non-objectifs de la spec), installation HACS (dépôt personnalisé `cesbron-dev/ha-adguard-clients`, catégorie Intégration), configuration (une entrée par instance ; URL, identifiants, vérification du certificat), options, entités créées et règles d'indisponibilité (`use_global_*`), service `set_blocked_services` avec exemple YAML, renommage des clients, limites (pas d'état optimiste, horaires AdGuard non gérés), remplacement de `adguard-mqtt-bridge` (le désinstaller ; les `entity_id` changent).
- [ ] **Step 2: Vérification finale** — `.venv/bin/pytest -W error -q` tout vert ; `python -m json.tool` sur `manifest.json`, `hacs.json`, `strings.json`, `translations/*.json` ; les clés de `strings.json`, `en.json` et `fr.json` sont identiques (petit script ou test `test_translations_keys_match` ajouté dans `tests/test_translations.py`).
- [ ] **Step 3: Commit** — `docs: README de l'intégration AdGuard Clients`

---

## Hors plan (contrôleur, avec accord d'Olivier)

- Créer le dépôt GitHub `cesbron-dev/ha-adguard-clients` (public) et pousser.
- Installer via HACS sur l'instance de test, configurer l'instance de Bordeaux, vérifier l'id réel de Disney+ dans le catalogue.
- Désinstaller `adguard-mqtt-bridge`.
- Adapter `ha-parental-control` (ressources AdGuard par `device_id`, adaptateur via `set_blocked_services`) : plan séparé dans ce dépôt-là.
