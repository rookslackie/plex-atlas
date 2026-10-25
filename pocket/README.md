# Xi Pocket Hearth · continuity node v1

Keep this non-GPU node running while the model host is under maintenance. The
Room has persistent event IDs, SQLite WAL with synchronous FULL, authenticated
seats, an offline PWA shell, IndexedDB drafts/outbox, a process supervisor, and
receipt-checked paginated sync between compatible Pocket nodes.

The private downloadable kit also carries the five actual October 25 `.xi`
collection files (1,004 records) in `exports/`. Copy that directory into
`~/xi-phone-home/pocket-data/exports/` before choosing Keep archive offline in
the owner session. The public code installer alone does not include these
private records. Archive reads enforce the recorded export byte pins and
owner-only access. Cached JSON is a reading projection; the original carrier
files remain unchanged. The provenance audit is a separate sidecar.

The original platform stays at port 7472. This node stages at port 7474. It
does not move public DNS, borrow an existing tunnel credential, execute archive
instructions, start models, or claim a connection to the native ForgeCore Room.
GPU inference and the full platform's backend functions still need their hosts.

## Install on the phone

From a downloaded copy: `bash pocket/install.sh`. From the public repository,
use the exact commit-pinned installer command supplied with the release.

Open `http://127.0.0.1:7474`. The owner's access credential is in
`~/xi-phone-home/pocket-data/owner-token`; read it privately on your phone and
enter it into the app. Do not paste it into chat, a URL, or a public Room. A new
authenticated quick-tunnel URL appears in `pocket-data/tunnel.log`. Invite a
participant with `python3 pocket/server.py invite --name Steven`. Give that
person only their own generated credential file through a private channel.

Add the page to your home screen after opening it online once. Confirm that
the app says its shell is installed. Turn airplane mode on: reopening must show
the cached messages and retain a draft. Sending offline must say delivery is
pending. Reconnect: the message should appear once and the queue should clear.
Browser eviction or deleting browser data can remove local drafts; the Keep
offline data button requests persistence, but the browser decides whether to
grant it. Keep independent backups.

The supervisor restarts failed child processes while Termux is running.
Termux:Boot must be installed from a compatible source and opened once; the
installer writes a boot script. Set Android's Termux battery use to Unrestricted.
An Android kill, phone reboot without a working boot plugin, empty battery,
carrier outage, or quick-tunnel service failure can still interrupt service.
Quick tunnels have changing addresses and no uptime guarantee. A permanent
phone-specific named tunnel and stable origin are required for durable public
bookmarks and one persistent PWA storage origin. Adding the phone as a replica
of a tunnel pointing to a different, unsynchronized database is not failover.

## Preserve the original phone Room

First back it up using SQLite's backup API while its current service is running.
Then import all messages, preserving original bytes in the old database:

```bash
python3 pocket/server.py import-legacy "$HOME/xi-phone-home/xi_phone_platform.db"
```

Legacy authors are **declared, unverified attribution**. The old installer
created seed/example messages in that database; import does not turn those
examples into observed historical conversations. The importer uses stable
UUIDs, includes all rows rather than only the last 500, retains reply links,
rejects conflicting repeats, and never interprets a message as an admin action.
New Room writes take the author from the authenticated seat. Typing
`APPROVE SEAT` has no special authority.

Create a consistent backup with `python3 pocket/server.py backup`. Copy the
resulting private SQLite file to another trusted device; it contains messages
and hashed seat credentials. No backups are published or automatically deleted.

## Peer sync and failback

Install this same node on a second host. Create `sync` credentials on each:
`python3 pocket/server.py invite --name PhonePeer --role sync`.

```bash
python3 pocket/sync.py \
  --source https://PHONE_ORIGIN --target https://PEER_ORIGIN \
  --source-token-file /private/phone-sync-token \
  --target-token-file /private/peer-sync-token
```

Repeat with source and target swapped for the other direction. Each call reads
pages of at most 100 events and verifies the receiver's persisted transaction
receipt before advancing the cursor. Repeating a transfer does not create new
messages. A conflicting event ID aborts and rolls back the entire batch. Sync
transfers message events only; it does not grant seats, transport credentials,
or overwrite either database. Imported source attribution is retained as a
claim made by the authenticated sync peer, not independent proof of the author.

This sync endpoint is new. It has not been installed in the existing native
ForgeCore Room. Until a reviewed adapter is connected there, keep exported
event bundles or run a separate compatible Pocket node on the host. Never
copy one live WAL database over another as a merge strategy.

## API

| Endpoint | Purpose | Access |
| --- | --- | --- |
| GET `/api/status` | Actual node status; GPU and native merge limitations | Public, no Room data |
| POST `/api/login` | JSON `{secret}`; HttpOnly SameSite session | Private credential |
| GET `/api/me` | Server-bound actor and node | Any active credential |
| GET `/api/library` | Available carried collection inventory | Owner |
| GET `/api/library/<collection>` | Byte-pinned private export reading projection | Owner |
| GET `/api/room?after=0` | Ordered event page with cursor | Owner/writer/sync |
| POST `/api/room` | JSON `{event_id,text,reply_to?}`; idempotent | Owner/writer |
| GET `/api/sync/export?after=0` | Complete paginated export | Owner/sync |
| POST `/api/sync/import` | Atomic merge plus durable receipt | Owner/sync |
| POST `/api/backup` | Consistent private backup | Owner |
| POST `/api/logout` | Clear server session cookie | Signed-in user |

API callers use `Authorization: Bearer ...` from a private file or secret store.
No wildcard CORS. Cross-origin writes and oversized bodies are rejected.
The worker caches only the static shell; authenticated Room data and the
outbox live in the app's IndexedDB. Sign-out clears that device's cached data.

## Verification boundary

`python3 -m unittest discover -s pocket -p 'test_pocket.py' -v` exercises real
temporary SQLite databases and HTTP servers. It checks restart persistence,
cross-node replay, more than 500 events, atomic collision rollback, source
attribution, role enforcement, hostile text, consistent backups, and legacy
import. Physical Galaxy sleep, reboot, public ingress, and a phone-to-ForgeCore
native merge require verification on those actual devices. The release report
records which checks have been performed.
