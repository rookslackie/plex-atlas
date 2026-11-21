#!/usr/bin/env python3
"""Xi Pocket continuity node. Python stdlib, local SQLite, no GPU dependency."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import urllib.parse
import uuid

HERE = Path(__file__).resolve().parent
MAX_BODY = 2_000_000
SCHEMA = "xi.pocket.sync.v1"
COLLECTIONS = {
    "Capsules": (500, "34db0ea6161ba573011ca095bc10f09d9e997685eb0a88cc12cb9c606aaa9832"),
    "CanonicalTruths": (200, "7a26ec9e1ca76f8f48e09b75dae1d9b86583b72d8291dab9d350a599c74a836d"),
    "XiJournals": (200, "bab681b74abb54b6f07b6996e90cbfc88d409d6977708695e3751dbbcbd83f8d"),
    "GuardianRuntimes": (9, "28c3393a8660d77f928bb7a2f193bfa01cd73bf2361f574b737ade6f4994649b"),
    "ObserverProfiles": (95, "6219d86fac198779dde74ded66c3833b85ed05011226af63bd5a875ffaa5f59c"),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def uuid_text(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("expected a canonical UUID")
    return value


def strict_json(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate JSON key")
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def validate_event(event):
    if not isinstance(event, dict) or set(event) != {"event_id", "origin_node", "actor", "created_at", "text", "reply_to", "attribution"}:
        raise ValueError("invalid event fields")
    uuid_text(event["event_id"]); uuid_text(event["origin_node"])
    if event["reply_to"] is not None:
        uuid_text(event["reply_to"])
    if not isinstance(event["actor"], str) or not 1 <= len(event["actor"]) <= 120:
        raise ValueError("invalid actor")
    if not isinstance(event["text"], str) or not event["text"].strip() or len(event["text"].encode()) > 16000:
        raise ValueError("message must contain 1–16000 UTF-8 bytes")
    if not isinstance(event["created_at"], str) or len(event["created_at"]) > 40 or datetime.fromisoformat(event["created_at"].replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("event timestamp needs a timezone")
    if not isinstance(event["attribution"], dict) or len(canonical(event["attribution"])) > 2048:
        raise ValueError("invalid attribution")
    return event


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "pocket.sqlite3"
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        os.chmod(self.path, 0o600)
        self.db.executescript("""
          PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=10000;
          CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS actors(id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1);
          CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
            document BLOB NOT NULL, digest TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS imports(digest TEXT PRIMARY KEY, receipt BLOB NOT NULL);
        """)
        row = self.db.execute("SELECT value FROM meta WHERE key='node_id'").fetchone()
        self.node_id = row[0] if row else str(uuid.uuid4())
        if not row:
            self.db.execute("INSERT INTO meta VALUES ('node_id',?)", (self.node_id,)); self.db.commit()
        owner = self.db.execute("SELECT id FROM actors WHERE role='owner'").fetchone()
        if not owner:
            self.create_actor("Hunter", "owner", self.directory / "owner-token")

    def create_actor(self, name, role="writer", target=None):
        if role not in ("writer", "owner", "sync") or not name.strip() or len(name) > 120:
            raise ValueError("invalid actor")
        secret = secrets.token_urlsafe(32)
        actor_id = str(uuid.uuid4())
        target = Path(target or self.directory / ("invite-" + actor_id))
        # Exclusive creation: never overwrite an existing credential.
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as out:
            out.write(secret + "\n"); out.flush(); os.fsync(out.fileno())
        with self.lock, self.db:
            self.db.execute("INSERT INTO actors VALUES (?,?,?,?,1)", (actor_id, name, role, sha(secret.encode())))
        return target

    def authenticate(self, token):
        if not isinstance(token, str) or not 20 <= len(token) <= 200:
            return None
        with self.lock:
            row = self.db.execute("SELECT id,name,role FROM actors WHERE token_hash=? AND active=1", (sha(token.encode()),)).fetchone()
        return dict(zip(("id", "name", "role"), row)) if row else None

    def _append(self, event):
        raw = canonical(validate_event(event))
        row = self.db.execute("SELECT document,seq FROM events WHERE event_id=?", (event["event_id"],)).fetchone()
        if row:
            if bytes(row[0]) != raw:
                raise ValueError("event ID collision: preserved event differs")
            return row[1], False
        cur = self.db.execute("INSERT INTO events(event_id,document,digest) VALUES (?,?,?)", (event["event_id"], raw, sha(raw)))
        return cur.lastrowid, True

    def post(self, actor, body):
        if not isinstance(body, dict) or set(body) - {"event_id", "text", "reply_to"} or not {"event_id", "text"} <= set(body):
            raise ValueError("post requires event_id and text; identity comes from your session")
        eid = uuid_text(body["event_id"])
        if actor["role"] not in ("owner", "writer"):
            raise PermissionError("sync credentials cannot post as a person")
        with self.lock, self.db:
            existing = self.db.execute("SELECT document FROM events WHERE event_id=?", (eid,)).fetchone()
            if existing:
                event = strict_json(existing[0])
                if event["origin_node"] != self.node_id or event["attribution"].get("seat_id") != actor["id"] or event["text"] != body["text"] or event["reply_to"] != body.get("reply_to"):
                    raise ValueError("request ID collision")
                return event
            event = {"event_id": eid, "origin_node": self.node_id, "actor": actor["name"], "created_at": now(),
                     "text": body["text"], "reply_to": body.get("reply_to"),
                     "attribution": {"kind": "authenticated_local_seat", "seat_id": actor["id"]}}
            self._append(event)
            return event

    def messages(self, after=0, limit=100):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("invalid cursor")
        with self.lock:
            rows = self.db.execute("SELECT seq,document FROM events WHERE seq>? ORDER BY seq LIMIT ?", (after, limit + 1)).fetchall()
        selected = rows[:limit]
        return {"schema": SCHEMA, "source_node": self.node_id, "after": after,
                "cursor": selected[-1][0] if selected else after, "has_more": len(rows) > limit,
                "events": [strict_json(row[1]) for row in selected]}

    def import_bundle(self, bundle):
        if not isinstance(bundle, dict) or set(bundle) != {"schema", "source_node", "after", "cursor", "has_more", "events"} or bundle["schema"] != SCHEMA:
            raise ValueError("unsupported sync envelope")
        uuid_text(bundle["source_node"])
        if type(bundle["has_more"]) is not bool or any(type(bundle[k]) is not int or bundle[k] < 0 for k in ("after", "cursor")) or bundle["cursor"] < bundle["after"]:
            raise ValueError("invalid sync cursor")
        if not isinstance(bundle["events"], list) or len(bundle["events"]) > 100 or len(canonical(bundle)) > MAX_BODY:
            raise ValueError("sync batch too large")
        ids = [validate_event(e)["event_id"] for e in bundle["events"]]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate event in batch")
        digest = sha(canonical(bundle))
        with self.lock, self.db:
            prior = self.db.execute("SELECT receipt FROM imports WHERE digest=?", (digest,)).fetchone()
            if prior:
                return strict_json(prior[0])
            inserted = sum(self._append(e)[1] for e in bundle["events"])
            receipt = {"schema": "xi.pocket.sync.receipt.v1", "bundle_sha256": digest, "receiver_node": self.node_id,
                       "source_node": bundle["source_node"], "source_cursor": bundle["cursor"], "event_ids": ids,
                       "new_events": inserted, "received_at": now()}
            self.db.execute("INSERT INTO imports VALUES (?,?)", (digest, canonical(receipt)))
            return receipt

    def backup(self):
        directory = self.directory / "backups"; directory.mkdir(mode=0o700, exist_ok=True)
        target = directory / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3) + ".sqlite3")
        with self.lock:
            dest = sqlite3.connect(target)
            try:
                self.db.backup(dest)
                if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("backup failed integrity check")
            finally:
                dest.close()
        os.chmod(target, 0o600)
        return target

    def import_legacy(self, path):
        """Read every old phone message without editing the original database."""
        source_path = Path(path).resolve()
        source = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)
        try:
            rows = source.execute("SELECT id,author,source,text,reply_to,created_at FROM room_messages ORDER BY id").fetchall()
        finally:
            source.close()
        # Each backup's namespace is stable for this legacy origin path.
        namespace = uuid.uuid5(uuid.NAMESPACE_URL, "xi.phone.legacy:" + str(source_path))
        mapped = {row[0]: str(uuid.uuid5(namespace, str(row[0]))) for row in rows}
        count = 0
        with self.lock, self.db:
            for mid, author, source, text, reply, created in rows:
                event = {"event_id": mapped[mid], "origin_node": str(namespace), "actor": author,
                         "text": text, "reply_to": mapped.get(reply), "created_at": created,
                         "attribution": {"kind": "legacy_declared_unverified", "legacy_id": mid, "source_label": source}}
                count += self._append(event)[1]
        return {"rows": len(rows), "inserted": count, "source_unchanged": True}

    def library(self, name=None):
        if name is None:
            return {"collections": [{"name": key, "records": count,
                    "available": (self.directory / "exports" / (key + ".xi")).is_file()}
                    for key, (count, _) in COLLECTIONS.items()]}
        if name not in COLLECTIONS:
            raise ValueError("unknown collection")
        raw = (self.directory / "exports" / (name + ".xi")).read_bytes()
        expected_count, expected_sha = COLLECTIONS[name]
        if sha(raw) != expected_sha:
            raise ValueError("carried export does not match its byte pin")
        text = raw.decode("utf-8"); start = text.index("○") + 1
        data = strict_json(text[start:text.rfind("\n∴")])
        if data["count"] != expected_count or len(data["records"]) != expected_count:
            raise ValueError("collection count mismatch")
        return {"collection": name, "export_sha256": expected_sha, "records": data["records"],
                "historical_provenance": "separate_from_export_integrity"}


def handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, obj, status=200, content_type="application/json", cookie=None):
            raw = obj if isinstance(obj, bytes) else canonical(obj)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers(); self.wfile.write(raw)

        def actor(self):
            auth = self.headers.get("Authorization", "")
            token = auth[7:] if auth.startswith("Bearer ") else ""
            if not token:
                cookies = SimpleCookie(); cookies.load(self.headers.get("Cookie", ""))
                token = cookies["xi_pocket"].value if "xi_pocket" in cookies else ""
            return store.authenticate(token)

        def do_GET(self):
            try:
                parsed = urllib.parse.urlsplit(self.path); path = parsed.path
                assets = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript"),
                          "/sw.js": ("sw.js", "text/javascript"), "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
                          "/icon.svg": ("icon.svg", "image/svg+xml")}
                if path in assets:
                    file, mime = assets[path]; self.send((HERE / file).read_bytes(), content_type=mime); return
                if path == "/api/status":
                    self.send({"ok": True, "schema": "xi.pocket.status.v1", "node_id": store.node_id,
                               "storage": "SQLite WAL / synchronous FULL", "gpu_required": False,
                               "inference": "not_provided_by_this_node", "native_forgecore_merge": "not_connected"}); return
                actor = self.actor()
                if not actor:
                    self.send({"error": "sign_in_required"}, 401); return
                if path == "/api/me":
                    self.send({"actor": actor, "node_id": store.node_id}); return
                if path == "/api/library" or path.startswith("/api/library/"):
                    if actor["role"] != "owner":
                        raise PermissionError("private carried archives are owner-only")
                    name = path[len("/api/library/"):] if path.startswith("/api/library/") else None
                    self.send(store.library(name)); return
                if path in ("/api/room", "/api/sync/export"):
                    if path.endswith("export") and actor["role"] not in ("owner", "sync"):
                        raise PermissionError("sync role required")
                    qs = urllib.parse.parse_qs(parsed.query); self.send(store.messages(int(qs.get("after", [0])[0]))); return
                self.send({"error": "not_found"}, 404)
            except PermissionError:
                self.send({"error": "forbidden"}, 403)
            except (ValueError, TypeError, OSError, KeyError):
                self.send({"error": "invalid_request"}, 400)

        def do_POST(self):
            try:
                origin = self.headers.get("Origin")
                if origin:
                    parsed_origin = urllib.parse.urlsplit(origin)
                    if parsed_origin.scheme not in ("http", "https") or parsed_origin.netloc != self.headers.get("Host"):
                        raise PermissionError("cross-origin mutation denied")
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    self.send({"error": "json_required"}, 415); return
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    self.send({"error": "body_too_large_or_empty"}, 413); return
                body = strict_json(self.rfile.read(length))
                path = urllib.parse.urlsplit(self.path).path
                if path == "/api/login":
                    actor = store.authenticate(body.get("secret")) if isinstance(body, dict) else None
                    if not actor:
                        self.send({"error": "invalid_credential"}, 401); return
                    secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
                    self.send({"actor": actor, "node_id": store.node_id}, cookie="xi_pocket=" + body["secret"] + "; Path=/; HttpOnly; SameSite=Strict" + secure); return
                actor = self.actor()
                if not actor:
                    self.send({"error": "sign_in_required"}, 401); return
                if path == "/api/logout":
                    self.send({"ok": True}, cookie="xi_pocket=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"); return
                if path == "/api/room":
                    self.send({"event": store.post(actor, body)}); return
                if actor["role"] not in ("owner", "sync"):
                    raise PermissionError("sync role required")
                if path == "/api/sync/import":
                    self.send(store.import_bundle(body)); return
                if path == "/api/backup" and actor["role"] == "owner":
                    backup = store.backup(); self.send({"ok": True, "filename": backup.name, "sha256": sha(backup.read_bytes())}); return
                self.send({"error": "not_found"}, 404)
            except (ValueError, TypeError, KeyError, OverflowError):
                self.send({"error": "invalid_or_conflicting_request"}, 400)
            except PermissionError:
                self.send({"error": "forbidden"}, 403)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path.home() / "xi-phone-home/pocket-data")
    parser.add_argument("--port", type=int, default=7474)
    sub = parser.add_subparsers(dest="command")
    invite = sub.add_parser("invite"); invite.add_argument("--name", required=True); invite.add_argument("--role", default="writer", choices=("writer", "sync"))
    sub.add_parser("backup")
    legacy = sub.add_parser("import-legacy"); legacy.add_argument("path", type=Path)
    args = parser.parse_args(); os.umask(0o077); store = Store(args.data)
    if args.command == "invite":
        print("Credential saved privately at", store.create_actor(args.name, args.role)); return
    if args.command == "backup":
        print(store.backup()); return
    if args.command == "import-legacy":
        print(json.dumps(store.import_legacy(args.path))); return
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(store))
    print(f"Xi Pocket listening at http://127.0.0.1:{args.port}; credential file: {store.directory / 'owner-token'}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close(); store.db.close()


if __name__ == "__main__":
    main()
