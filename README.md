# AdGuard Clients pour Home Assistant

Intégration Home Assistant (HACS) qui expose les **clients persistants** d'une ou plusieurs
instances [AdGuard Home](https://github.com/AdguardTeam/AdGuardHome) : un appareil Home
Assistant par client, avec ses réglages de filtrage et un switch par service bloqué
(YouTube, Roblox, TikTok…).

L'intégration officielle `adguard` ne gère que les réglages globaux d'une instance. Celle-ci
couvre ce qu'elle ne fait pas : bloquer un service pour **un client précis** (les appareils
d'un enfant, par exemple), sans toucher au reste de la maison. Elle est testée avec AdGuard
Home **v0.107.79**.

Elle sert aussi de brique au moteur [`ha-parental-control`](https://github.com/cesbron-dev/ha-parental-control),
qui utilisera le service `set_blocked_services` pour appliquer ses décisions.

## Ce que l'intégration ne fait pas

- Les réglages globaux de l'instance (protection, filtrage global, services bloqués globaux) :
  l'intégration officielle `adguard` s'en charge.
- Les clients « runtime » (vus seulement par IP, sans fiche persistante).
- Créer, supprimer ou renommer un client, ou modifier ses identifiants : cela se fait dans AdGuard.
- Les règles de filtrage personnalisées, les statistiques et le journal des requêtes.
- Les horaires de services d'AdGuard (`blocked_services_schedule`) : ils ne sont **jamais
  modifiés** et continuent de s'appliquer. L'intégration n'en tient pas compte.

## Installation (HACS)

1. HACS, menu en haut à droite, **Dépôts personnalisés**.
2. Dépôt `cesbron-dev/ha-adguard-clients`, catégorie **Intégration**.
3. Installer « AdGuard Clients », puis redémarrer Home Assistant.

## Configuration

**Paramètres, Appareils et services, Ajouter une intégration, AdGuard Clients.**
Ajoutez **une entrée par instance AdGuard Home**, autant que nécessaire.

| Champ | Description |
|---|---|
| Nom de l'instance | Titre de l'entrée et de l'appareil de l'instance (ex. « AdGuard Bordeaux »). |
| URL | Par exemple `https://adguard-bdx.home.cesbron.dev` ou `http://192.168.1.2:3000`. |
| Nom d'utilisateur / Mot de passe | Authentification HTTP basique d'AdGuard Home. |
| Vérifier le certificat | À décocher pour un certificat auto-signé. |

L'URL normalisée identifie l'instance : on ne peut pas l'ajouter deux fois. La
ré-authentification (identifiants refusés) et la reconfiguration (changer l'URL ou les
identifiants) sont proposées par Home Assistant.

### Options

Sur l'entrée, **Configurer** :

- **Services exposés comme switches** : sélection multiple dans le catalogue de l'instance.
  Par défaut : `youtube`, `roblox`, `tiktok`, `netflix`, `disneyplus` et `twitch`, limités à
  ceux qui existent dans le catalogue. Changer la liste recharge l'entrée ; les switches
  retirés sont supprimés.
- **Intervalle de rafraîchissement** : 30 s par défaut, de 10 à 3600 s.

## Entités créées

Chaque client persistant devient un appareil portant son nom AdGuard, rattaché à l'appareil
de l'instance. Les entités sont nommées d'après le client (ex. le switch « Bloquer YouTube »
de l'appareil « iPad Gabin »).

| Entité | Rôle |
|---|---|
| switch « Filtrage » | Filtrage du client. |
| switch « Contrôle parental » | Contrôle parental d'AdGuard. |
| switch « Navigation sécurisée » | Navigation sécurisée. |
| switch « Recherche sécurisée » | Recherche sécurisée. |
| switch « Utiliser les réglages globaux » | Catégorie configuration. |
| switch « Utiliser les services bloqués globaux » | Catégorie configuration. |
| switch « Bloquer *service* » | Un par service choisi ; **activé = bloqué**. |
| capteur « Services bloqués » | Nombre de services bloqués. L'attribut `services` liste tous les ids bloqués (triés, y compris ceux sans switch) ; `ids`, `tags`, `adguard_name` et `use_global_blocked_services` y figurent aussi. |

L'appareil de l'instance porte un capteur binaire de diagnostic « Connecté ».

### Quand les switches sont indisponibles

AdGuard ignore les réglages propres d'un client tant qu'il utilise les réglages globaux :

- Les switches de **services** sont indisponibles tant que « Utiliser les services bloqués
  globaux » est activé.
- Les switches de **réglages** (filtrage, contrôle parental, navigation et recherche
  sécurisées) sont indisponibles tant que « Utiliser les réglages globaux » est activé.

Pour en sortir, **désactivez** le switch « Utiliser les … globaux » correspondant : il n'écrit que
ce drapeau, la liste de services et les réglages gardés par AdGuard redeviennent applicables.
Le service ci-dessous reste utilisable dans ce mode : il désactive lui-même l'option globale.

## Service `adguard_clients.set_blocked_services`

Bloque et débloque des services pour un client en **une seule écriture**. Le service désactive
lui-même « services bloqués globaux ». Il accepte n'importe quel id du catalogue AdGuard, pas
seulement ceux qui ont un switch.

| Champ | Description |
|---|---|
| `device_id` | L'appareil du client (obligatoire). |
| `block` | Ids de services à bloquer (optionnel). |
| `unblock` | Ids de services à débloquer (optionnel). |

Le résultat est (services actuels ∪ `block`) − `unblock`. Un id présent dans `block` et
`unblock`, ou absent du catalogue, est refusé et rien n'est écrit. Le service renvoie la liste
relue après écriture.

```yaml
action: adguard_clients.set_blocked_services
data:
  device_id: 0a1b2c3d4e5f60718293a4b5c6d7e8f9   # appareil « iPad Gabin »
  block: [youtube, roblox]
  unblock: [tiktok]
response_variable: resultat
# resultat.blocked_services -> ["roblox", "youtube"] (par exemple)
```

## Fonctionnement et limites

- **Pas d'état optimiste** : un switch n'affiche que ce qui a été relu dans AdGuard. Chaque
  écriture relit la fiche du client, la modifie, l'écrit entière (les autres champs sont
  conservés) puis relit. Les écritures d'une instance sont sérialisées.
- Un changement fait dans l'interface d'AdGuard apparaît au prochain rafraîchissement.
- **Renommage** : renommer un client dans AdGuard garde son appareil et ses `entity_id` ; seul
  le nom de l'appareil suit. Le rapprochement se fait par nom, puis par identifiants communs.
  En cas de doute, un nouvel appareil est créé plutôt que de réutiliser celui d'un autre.
- Un client supprimé d'AdGuard rend ses entités indisponibles ; l'appareil se supprime à la main.
- Les nouveaux clients apparaissent au rafraîchissement suivant.
- Les horaires de services d'AdGuard ne sont pas gérés (voir plus haut).

## Remplace `adguard-mqtt-bridge`

Cette intégration remplace entièrement le module complémentaire `adguard-mqtt-bridge`, sans
cohabitation possible : **désinstallez-le**. Les `entity_id` changent, car les entités sont
désormais nommées d'après l'appareil du client (switch « Bloquer YouTube » sur l'appareil
« iPad Gabin »). Adaptez en conséquence vos automatisations et tableaux de bord.
