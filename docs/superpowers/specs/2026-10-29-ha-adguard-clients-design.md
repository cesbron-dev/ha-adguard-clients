# AdGuard Clients pour Home Assistant — conception

Date : 2026-10-29 · Statut : à valider par Olivier

## Intention

L'intégration officielle `adguard` de Home Assistant ne gère que les réglages globaux d'une
instance AdGuard Home. Elle n'expose pas les **clients persistants** (une fiche AdGuard
regroupant plusieurs IP / MAC / ClientID) et ne permet pas de **bloquer un service
(YouTube, Roblox…) pour un client précis**. C'est exactement ce dont le moteur
`ha-parental-control` a besoin : couper les services « loisirs » sur les appareils d'un
enfant, pas sur toute la maison.

Un premier essai, le module complémentaire `adguard-mqtt-bridge`
(gitlab.com/cesbron-dev/homeassistant-addons), faisait cela via MQTT. C'était un test ;
la nouvelle intégration **le remplace entièrement** (pas de cohabitation, pas de
compatibilité de noms d'entités à garder).

## Objectifs

1. Intégration HACS `ha-adguard-clients`, domaine `adguard_clients`, configurée depuis
   l'interface (config flow), **une entrée par instance AdGuard Home** : on peut en
   ajouter autant que voulu (Bordeaux et d'autres).
2. Un appareil HA par **client persistant** de chaque instance, avec :
   - les switches de réglages du client ;
   - un switch par service bloqué, pour une liste de services choisie ;
   - ses identifiants et tags en attributs.
3. Un service `adguard_clients.set_blocked_services` **atomique** (une écriture par client)
   que le moteur parental utilisera.
4. Synchronisation dans les deux sens : un changement fait dans l'UI AdGuard apparaît dans
   HA au prochain rafraîchissement ; un changement fait dans HA est écrit tout de suite
   puis relu.

## Non-objectifs

- Réglages globaux de l'instance (protection, filtrage global, services bloqués globaux) :
  l'intégration officielle les couvre déjà.
- Clients « runtime » (vus seulement par IP, sans fiche) : on ne peut pas leur appliquer
  de règles propres.
- Créer, supprimer ou renommer des clients, ou modifier leurs identifiants, depuis HA.
- Règles de filtrage personnalisées (`||domaine^$client=…`).
- Horaires de services AdGuard (`blocked_services_schedule`) : jamais modifiés, jamais
  utilisés. C'est le moteur parental qui décide du moment.
- Statistiques et journal des requêtes par client.

## Anti-objectifs (échec même si « ça marche »)

- Une écriture qui écrase les autres champs d'un client (upstreams, tags, identifiants,
  horaires…) ou un changement concurrent fait entre deux rafraîchissements.
- Un switch qui affiche un état qu'AdGuard n'applique pas.
- Des entités qui disparaissent / se recréent quand on renomme un client dans AdGuard,
  et cassent les tableaux de bord.
- Des centaines d'entités par client.

## Contraintes

- Home Assistant 2026.10 ou plus récent, Python 3.14 ; même outillage de test que
  `ha-parental-control` (`pytest-homeassistant-custom-component==0.13.375`, `uv`,
  `.venv/bin/pytest -W error -q`).
- AdGuard Home **v0.107.79** (instance de Bordeaux) ; viser l'API `/control/*` de la
  branche v0.107.
- Pas de dépendance externe : client HTTP via la session aiohttp de HA
  (`async_get_clientsession`).
- Textes de l'interface en français, avec traduction anglaise (`strings.json`,
  `translations/en.json`, `translations/fr.json`).
- Dépôt GitHub `cesbron-dev/ha-adguard-clients`, public (HACS).

## API AdGuard utilisée

Repris du bridge, qui fonctionne contre cette instance :

| Appel | Usage |
|---|---|
| `GET /control/status` | Test de connexion dans le config flow, version de l'instance. |
| `GET /control/clients` | Liste des clients persistants (`clients[]`). |
| `GET /control/blocked_services/all` | Catalogue des services (`id`, `name`, icône). |
| `POST /control/clients/update` `{"name": <nom actuel>, "data": <fiche complète>}` | Seule écriture. La fiche est renvoyée **entière**. |

Authentification HTTP basique (utilisateur / mot de passe), HTTPS possible avec option
« vérifier le certificat ».

Champs d'un client utilisés : `name`, `ids`, `tags`, `use_global_settings`,
`filtering_enabled`, `parental_enabled`, `safebrowsing_enabled`, `safe_search.enabled`,
`use_global_blocked_services`, `blocked_services`. Tous les autres champs sont conservés
tels quels à l'écriture.

## Décisions

### Écriture : lire, modifier, écrire, relire

Toute écriture (switch ou service) suit, sous un verrou **par instance** :

1. `GET /control/clients` frais (jamais le cache du dernier rafraîchissement) ;
2. retrouver le client (voir « Identité ») ; s'il a disparu → erreur
   `HomeAssistantError` traduite ;
3. appliquer la modification sur la fiche complète ;
4. `POST /control/clients/update` avec le **nom actuel** du client ;
5. rafraîchir le coordinateur pour que les entités reflètent l'état réel.

Les écritures d'une même instance sont donc sérialisées ; trois switches basculés à la
suite donnent trois cycles complets qui ne s'écrasent pas.

Échecs (choix de l'auteur) :

- Pas d'état optimiste : un switch n'affiche que ce qui a été relu dans AdGuard.
- Échec du `GET` ou du `POST` → `HomeAssistantError` traduite, rien n'est réputé écrit.
- `POST` réussi mais relecture en échec → l'appel **réussit** (l'écriture a eu lieu) ; les
  entités deviennent indisponibles jusqu'au rafraîchissement suivant (comportement normal
  du coordinateur), et un avertissement est journalisé.
- 401/403 pendant une écriture → `HomeAssistantError` traduite **et** démarrage du flux
  de ré-authentification (`entry.async_start_reauth`).

### Règles d'application d'AdGuard

- Écrire un service bloqué met aussi `use_global_blocked_services: false`, sinon AdGuard
  ignore la liste du client (comportement repris du bridge).
- Écrire `filtering_enabled`, `parental_enabled`, `safebrowsing_enabled` ou
  `safe_search.enabled` met aussi `use_global_settings: false` (idem).
- Il y a un switch dédié « Utiliser les services bloqués globaux » et un switch
  « Utiliser les réglages globaux » pour revenir en arrière.
- Tant que `use_global_blocked_services` est vrai, les switches de services du client
  sont **indisponibles** (ils n'agiraient pas sur ce qui est appliqué). Même règle pour
  les switches de réglages quand `use_global_settings` est vrai. Le service
  `set_blocked_services` reste utilisable : il désactive l'option globale lui-même.
- Pour l'utilisateur, sortir du mode global passe donc par le switch dédié (voulu).
  Basculer un switch `use_global_*` n'écrit **que** ce drapeau : la liste
  `blocked_services` et les réglages du client restent ceux qu'AdGuard a gardés.

### Identité d'un client

AdGuard identifie un client par son **nom** (c'est la clé de `clients/update`). Pour que
renommer un client dans AdGuard ne recrée pas ses entités :

- l'identifiant stable d'un appareil HA est un `uid` généré par l'intégration, gardé
  dans un `Store` par entrée, associé au client ;
- à chaque rafraîchissement, un client est rapproché de son `uid` d'abord par **nom**,
  sinon par **recouvrement d'identifiants** (`ids` : au moins un identifiant en commun
  avec la fiche connue). Un client renommé garde donc son appareil, et le nom de
  l'appareil HA suit le nouveau nom AdGuard ;
- si AdGuard renvoie un identifiant propre au client (champ `uid` dans les versions qui
  le fournissent), il est utilisé en priorité.
- Un client absent de la liste rend ses entités indisponibles ; l'appareil n'est retiré
  qu'à la main (`async_remove_config_entry_device` renvoie vrai si le client n'existe
  plus dans AdGuard).

Algorithme de rapprochement, à chaque rafraîchissement (choix de l'auteur, prudent par
construction : en cas de doute, on crée un nouvel appareil plutôt que d'attacher les règles
d'un enfant à l'appareil d'un autre) :

1. `uid` AdGuard s'il existe → correspondance directe.
2. Sinon **nom identique** à un `uid` connu (actif ou absent) → même appareil. Un client
   absent qui réapparaît sous le même nom reprend donc son appareil.
3. Sinon, parmi les `uid` connus non rapprochés **et présents à la dernière lecture réussie**
   (jamais un client supprimé depuis, même si un nouveau client reprend son IP) : si exactement **un**
   `uid` partage au moins un identifiant avec ce client, et que ce `uid` ne partage
   d'identifiant avec **aucun autre** client non rapproché → renommage, même appareil.
4. Sinon → nouveau `uid`, nouvel appareil (un renommage accompagné d'un changement de tous
   les identifiants dans le même rafraîchissement donne donc un nouvel appareil ; l'ancien
   devient indisponible).

Les nouveaux clients créés dans AdGuard après l'installation sont ajoutés dynamiquement
(appareil et entités) au rafraîchissement suivant.

### Entités par client

`has_entity_name = True`, nom de l'appareil = nom du client AdGuard ; identifiants
d'appareil `(adguard_clients, <entry_id>_<uid>)`, `via_device` = l'appareil de l'instance.

| Entité | Clé de traduction | Notes |
|---|---|---|
| switch Filtrage | `filtering` | `filtering_enabled` |
| switch Contrôle parental | `parental` | `parental_enabled` |
| switch Navigation sécurisée | `safebrowsing` | `safebrowsing_enabled` |
| switch Recherche sécurisée | `safe_search` | `safe_search.enabled` |
| switch Utiliser les réglages globaux | `use_global_settings` | catégorie config |
| switch Utiliser les services bloqués globaux | `use_global_blocked_services` | catégorie config |
| switch Bloquer <service> | `blocked_service` (placeholder = nom AdGuard du service) | un par service choisi ; **ON = bloqué** |
| sensor Services bloqués | `blocked_services` | nombre ; attribut `services` = liste complète des ids bloqués (y compris ceux sans switch) |

Attributs exposés sur ce sensor : `services` (liste **triée** des ids bloqués — c'est le
contrat lu par le moteur parental), `ids`, `tags`, `adguard_name`, `use_global_blocked_services`.

`entity_id` attendus (instance « bordeaux », client « iPad Gabin ») :
`switch.ipad_gabin_bloquer_youtube` ; en cas de doublon de nom entre instances, HA
suffixe (`_2`). Le moteur parental ne dépend **pas** des `entity_id` (voir plus bas).

### Appareil de l'instance

Un appareil par entrée (nom = titre de l'entrée, ex. « AdGuard Bordeaux »,
`sw_version` = version AdGuard), sans entité propre sauf un `binary_sensor`
« Connecté » (catégorie diagnostic).

### Services choisis

Option de l'entrée (options flow), sélection multiple parmi le catalogue
`/control/blocked_services/all` de l'instance. Défaut : la liste loisirs du moteur
parental, `youtube`, `roblox`, `tiktok`, `netflix`, `disneyplus`, `twitch`, restreinte
aux ids qui existent réellement dans le catalogue (un id inconnu est ignoré et signalé
dans le journal). Changer la liste recharge l'entrée ; les switches retirés sont
supprimés du registre.

> À vérifier pendant l'implémentation : l'id exact de Disney+ dans le catalogue de
> v0.107.79 (`disneyplus` ou `disney_plus`). Si c'est `disney_plus`, corriger aussi la
> liste par défaut de `ha-parental-control`.

Si aucun service par défaut n'existe dans le catalogue, l'entrée démarre sans switch de
service (le sensor et le service restent disponibles). Si le catalogue ne peut pas être
lu au démarrage → `ConfigEntryNotReady` (HA réessaie).

### Rafraîchissement

`DataUpdateCoordinator` par entrée, intervalle par défaut **30 s**, réglable dans les
options (10 à 3600 s). Le catalogue des services est lu au démarrage et à chaque
rechargement. Une erreur réseau rend les entités indisponibles (`UpdateFailed`) sans
perdre la correspondance des `uid`. Une erreur 401/403 déclenche le flux de
ré-authentification.

### Config flow

- Étape « utilisateur » : URL (`https://adguard-bdx.home.cesbron.dev` ou `http://ip:port`),
  utilisateur, mot de passe, vérifier le certificat, nom de l'instance (titre de l'entrée).
  Test via `/control/status` ; erreurs `cannot_connect`, `invalid_auth`.
- Unicité : l'URL normalisée est l'`unique_id` de l'entrée.
- Ré-authentification et reconfiguration (changer l'URL) supportées.
- Choix de l'auteur de cette conception : on ne relit pas les identifiants de l'entrée
  de l'intégration officielle (couplage à ses détails internes) ; on les ressaisit.

### Service `adguard_clients.set_blocked_services`

```yaml
action: adguard_clients.set_blocked_services
data:
  device_id: <appareil du client>   # cible
  block: [youtube, roblox]          # ids à bloquer
  unblock: [tiktok]                 # ids à débloquer
```

- Résolution de la cible : registre des appareils → identifiant
  `(adguard_clients, <entry_id>_<uid>)` → entrée chargée → `uid` → client actuel (nom
  courant) dans la lecture fraîche. Appareil inconnu, appareil d'instance, entrée non
  chargée ou client absent d'AdGuard → `ServiceValidationError` traduite. Le schéma
  utilise un sélecteur d'appareil filtré sur l'intégration.
- Un seul cycle lire-modifier-écrire pour le client : `blocked_services` final =
  (actuel ∪ `block`) − `unblock` ; un id présent dans les deux → erreur de validation.
- Les ids absents du catalogue → erreur de validation (rien n'est écrit).
- Met `use_global_blocked_services: false`.
- Accepte des ids hors de la liste « services choisis » (le moteur parental peut bloquer
  n'importe quel service par exception).
- Renvoie (`SupportsResponse.OPTIONAL`) `{"blocked_services": [...]}` après relecture.
- Réservé aux administrateurs ? Non : les permissions HA habituelles s'appliquent ; c'est
  au moteur parental et aux tableaux de bord de protéger l'accès.

## Côté `ha-parental-control` (suivi, dans l'autre dépôt)

Hors du code de cette intégration, mais c'est sa raison d'être ; à faire juste après :

- Une ressource `adguard_services` désigne le client par **`device_id`** (appareil
  `adguard_clients`) au lieu de `client` (nom du bridge). Le format de configuration
  passe en v2 ou accepte les deux le temps de la migration — au choix du plan du moteur.
- L'adaptateur lit l'état depuis le sensor « Services bloqués » de l'appareil (attribut
  `services`) et écrit via `adguard_clients.set_blocked_services` avec `block` / `unblock`
  calculés : **une seule écriture par client et par décision**.
- La dérive se lit sur ce même attribut.
- Mettre la liste loisirs par défaut en accord avec l'id réel de Disney+.

## Tests attendus

- Client HTTP AdGuard simulé (`aioclient_mock`) : config flow (succès, `cannot_connect`,
  `invalid_auth`, doublon, ré-auth), création des appareils et entités, états des
  switches, indisponibilité sous `use_global_*`.
- Écriture : la fiche envoyée conserve tous les champs non touchés ; relecture fraîche
  avant écriture (un changement fait dans AdGuard entre deux rafraîchissements n'est pas
  écrasé) ; deux écritures concurrentes sur la même instance sont sérialisées.
- Renommage d'un client dans AdGuard : même appareil, même `entity_id`, nouveau nom.
- Rapprochement par identifiants ; client disparu → indisponible.
- `set_blocked_services` : union / différence, conflit block/unblock, id inconnu,
  réponse.
- Changement des services choisis : switches ajoutés / retirés du registre.
- Erreur réseau → `UpdateFailed` ; 401 → ré-authentification.

## Laissé au constructeur

Découpage des fichiers, noms internes, format exact du `Store`, icônes, formulation des
textes d'interface dans le respect des clés ci-dessus.
