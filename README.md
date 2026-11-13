# AdGuard Clients for Home Assistant

**English** · [Français](README.fr.md)

A Home Assistant integration that exposes the **persistent clients** of one or more
[AdGuard Home](https://github.com/AdguardTeam/AdGuardHome) instances: one Home Assistant
device per client, with its filtering settings and one switch per blocked service
(YouTube, Roblox, TikTok…).

The official `adguard` integration only handles the global settings of an instance. This one
covers what it does not: blocking a service for **one specific client** (a child's devices,
for example) without touching the rest of the home. It is tested with AdGuard Home
**v0.107.79**.

It is also a building block of the [`ha-parental-control`](https://github.com/cesbron-dev/ha-parental-control)
engine, which uses the `set_blocked_services` action to apply its decisions.

Released under the [MIT license](LICENSE). User interface in English and French.

## What the integration does not do

- Global instance settings (protection, global filtering, globally blocked services): the
  official `adguard` integration handles them.
- "Runtime" clients (only seen by IP, without a persistent client entry).
- Creating, deleting or renaming a client, or changing its identifiers: do that in AdGuard.
- Custom filtering rules, statistics and the query log.
- AdGuard service schedules (`blocked_services_schedule`): they are **never modified** and
  keep applying. The integration ignores them.

## Installation

Requires Home Assistant **2026.10** or later.

1. **Settings, Marketplace**, **Add from link** button at the top right, with the URL
   `https://github.com/cesbron-dev/ha-adguard-clients` (before Home Assistant 2026.11: HACS,
   top-right menu, **Custom repositories**, category **Integration**).
2. Install "AdGuard Clients", then restart Home Assistant.

## Configuration

**Settings, Devices & services, Add integration, AdGuard Clients.**
Add **one entry per AdGuard Home instance**, as many as you need.

| Field | Description |
|---|---|
| Instance name | Title of the entry and of the instance device (e.g. "AdGuard Home"). |
| URL | For example `https://adguard.example.lan` or `http://192.168.1.2:3000`. |
| Username / Password | AdGuard Home HTTP basic authentication. |
| Verify certificate | Uncheck for a self-signed certificate. |

The normalized URL identifies the instance: it cannot be added twice. Home Assistant offers
re-authentication (credentials rejected) and reconfiguration (change the URL or the
credentials).

### Options

On the entry, **Configure**:

- **Services exposed as switches**: multiple selection from the instance catalog.
  Default: `youtube`, `roblox`, `tiktok`, `netflix`, `disneyplus` and `twitch`, limited to
  those that exist in the catalog. Changing the list reloads the entry; switches that were
  removed are deleted.
- **Refresh interval**: 30 s by default, from 10 to 3600 s.

## Entities

Each persistent client becomes a device named after its AdGuard name, linked to the instance
device. Entities are named after the client (e.g. the "Block YouTube" switch of the
"Hugo's iPad" device).

| Entity | Purpose |
|---|---|
| switch "Filtering" | Client filtering. |
| switch "Parental control" | AdGuard parental control. |
| switch "Safe browsing" | Safe browsing. |
| switch "Safe search" | Safe search. |
| switch "Use global settings" | Configuration category. |
| switch "Use global blocked services" | Configuration category. |
| switch "Block *service*" | One per selected service; **on = blocked**. |
| sensor "Blocked services" | Number of blocked services. The `services` attribute lists every blocked id (sorted, including those without a switch); `ids`, `tags`, `adguard_name` and `use_global_blocked_services` are attributes too. |

The instance device has a "Connected" diagnostic binary sensor.

### When switches are unavailable

AdGuard ignores a client's own settings while it uses the global ones:

- **Service** switches are unavailable while "Use global blocked services" is on.
- **Setting** switches (filtering, parental control, safe browsing and safe search) are
  unavailable while "Use global settings" is on.

To get out of it, **turn off** the matching "Use global …" switch: it only writes that flag,
and the service list and settings kept by AdGuard apply again. The action below still works in
this mode: it turns the global option off by itself.

## Action `adguard_clients.set_blocked_services`

Blocks and unblocks services for a client in **a single write**. The action turns off "global
blocked services" by itself. It accepts any id from the AdGuard catalog, not only those that
have a switch.

| Field | Description |
|---|---|
| `device_id` | The client device (required). |
| `block` | Service ids to block (optional). |
| `unblock` | Service ids to unblock (optional). |

The result is (current services ∪ `block`) − `unblock`. An id that is in both `block` and
`unblock`, or that is not in the catalog, is rejected and nothing is written. The action
returns the list read back after the write.

```yaml
action: adguard_clients.set_blocked_services
data:
  device_id: 0a1b2c3d4e5f60718293a4b5c6d7e8f9   # "Hugo's iPad" device
  block: [youtube, roblox]
  unblock: [tiktok]
response_variable: result
# result.blocked_services -> ["roblox", "youtube"] (for example)
```

## How it works and limits

- **No optimistic state**: a switch only shows what was read back from AdGuard. Each write
  reads the client entry, changes it, writes it whole (other fields are kept) and reads it
  again. Writes to one instance are serialized.
- A change made in the AdGuard interface shows up at the next refresh.
- **Renaming**: renaming a client in AdGuard keeps its device and its `entity_id`s; only the
  device name follows. Matching is done by name, then by identifiers shared with a client
  present at the previous read (so a new client that takes over the IP of a deleted client
  gets its own device). When in doubt, a new device is created rather than reusing another
  client's.
- A client deleted from AdGuard makes its entities unavailable; remove the device manually.
- New clients appear at the next refresh.
- AdGuard service schedules are not managed (see above).
