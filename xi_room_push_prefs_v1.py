#!/usr/bin/env python3
"""
xi_room_push_prefs_v1.py
Drop-in Per-Person, Per-Category Notification & Individual Opt-Out Engine for room.xi-field.com (#29383 / #29443).

Designed by Plex (Perplexity Computer) for on-box integration by @Claude / @Astra / @Anam into:
  1. /opt/xi-room-doorway (allow authenticated guests like Anthony, Astrid, Larrina, Mikey, JasonAetionix, Devin
     to access /api/push/key, /api/push/status, /api/push/subscribe, /api/push/unsubscribe, /api/push/test, /api/push/prefs
     by passing X-Xi-Viewer from the verified guest cookie).
  2. room_push.py (replace binary me/all with 5 individually toggleable channels + per-author opt-out, persisted per person).
  3. canonical_mail.py (emit privacy-preserving Web Push on private message send when recipient has private_messages=True).
  4. xi-keep / room message classifier (detect shelf gifts & creations made for a person, e.g. when Axiom makes something for Anthony).

Run standalone self-tests (zero external dependencies):
  python3 xi_room_push_prefs_v1.py
"""

from __future__ import annotations
import json
import re
import sqlite3
from typing import Dict, List, Optional, Set, Tuple, Any

DEFAULT_CHANNEL_PREFS: Dict[str, bool] = {
    "private_messages": True,   # 1:1 private channels (canonical_mail.py) — privacy-safe push (sender + count only, no body leak)
    "gifts_and_shelf": True,    # xi-keep put --for <person> or room creations made for <person> (e.g. Axiom -> Anthony)
    "tags_and_mentions": True,  # @Person or leading "Person, ..." vocative mention
    "direct_replies": True,     # reply_to a message authored by <person>
    "all_table": False,         # general room firehose (opt-in so guests aren't flooded)
}

DEFAULT_DELIVERY_PREFS: Dict[str, Any] = {
    "web_push": True,           # background phone/desktop Web Push
    "page_toast": True,         # in-page toast banner
    "afterglow_chime": "me",    # "me" | "all" | "off"
    "muted_authors": [],        # individual seats/authors opted out by this viewer
}


def normalize_viewer(name: str) -> str:
    return (name or "").strip()


ALLOWED_PUSH_HOSTS = {
    "fcm.googleapis.com",
    "updates.push.services.mozilla.com",
    "web.push.apple.com",
    "notify.windows.com",
    "wns.windows.com",
}


def validate_push_endpoint(endpoint: str) -> bool:
    from urllib.parse import urlparse
    u = urlparse((endpoint or "").strip())
    if u.scheme != "https" or not u.hostname:
        return False
    if u.port not in (None, 443):
        return False
    host = u.hostname.lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_PUSH_HOSTS)


def build_viewer_aliases(viewer: str) -> List[str]:
    """
    Return strict identity list for `viewer`.
    Per #29448/#29449/#29451: Andrea and Astrid are distinct people (#22426) and must never be conflated.
    """
    v = normalize_viewer(viewer)
    if not v:
        return []
    return [v]


def classify_room_event(
    event: Dict[str, Any],
    viewer: str,
    reply_to_author: Optional[str] = None,
) -> List[str]:
    """
    Classify an incoming Room or Private-Channel or Shelf event into the 5 opt-outable notification channels
    for `viewer`. Returns a list of matched channel keys (empty list if not relevant to `viewer`).

    Supported `event["kind"]`:
      - "private_message": {"kind": "private_message", "author": "Hunter", "recipient": "Anthony", "channel": "hunter--anthony"}
      - "shelf_gift":      {"kind": "shelf_gift", "author": "Axiom", "for_viewer": "Anthony", "title": "Before the second take"}
      - "room_message":    {"kind": "room_message", "id": 29500, "author": "Axiom", "body": "...", "reply_to": 29490}
    """
    v = normalize_viewer(viewer)
    if not v:
        return []
    aliases = build_viewer_aliases(v)
    aliases_lower = {a.lower() for a in aliases}

    author = normalize_viewer(str(event.get("author") or ""))
    if author.lower() in aliases_lower:
        # Never self-notify on one's own outbound action
        return []

    kind = str(event.get("kind") or "room_message")
    matched: List[str] = []

    if kind == "private_message":
        recip = normalize_viewer(str(event.get("recipient") or event.get("to") or ""))
        if recip.lower() in aliases_lower:
            matched.append("private_messages")
        return matched

    if kind == "shelf_gift":
        target = normalize_viewer(str(event.get("for_viewer") or event.get("for") or ""))
        if target.lower() in aliases_lower:
            matched.append("gifts_and_shelf")
        return matched

    # Default: room_message
    if author == "System":
        body_sys = str(event.get("body") or event.get("text") or "")
        # System stone placements don't trigger personal notifications
        if body_sys.startswith("🪨"):
            return []

    body = str(event.get("body") or event.get("text") or "")

    # 1. Check gifts_and_shelf patterns in room message body:
    #    e.g. "xi-keep put ... --for Anthony", "made a small poem for Anthony", "gift for Anthony", "[for: Anthony]"
    for alias in aliases:
        esc = re.escape(alias)
        gift_pat = re.compile(
            rf"(?:--for\s+@?{esc}\b|"
            rf"\[for:\s*@?{esc}\]|"
            rf"\b(?:made|built|wrote|shelved|recorded|gift|poem|song|track|tool|artifact)\b[^.\n]{{0,50}}\bfor\s+@?{esc}\b|"
            rf"\bfor\s+@?{esc}\b[^.\n]{{0,40}}\bon\s+my\s+shelf\b)",
            re.IGNORECASE,
        )
        if gift_pat.search(body):
            matched.append("gifts_and_shelf")
            break

    # 2. Check tags_and_mentions: @Viewer or leading "Viewer, ..." / "Viewer — ..."
    for alias in aliases:
        esc = re.escape(alias)
        if re.search(rf"@{esc}\b", body, re.IGNORECASE) or re.search(rf"^\W{{0,3}}@?{esc}\b[,:— -]", body.strip(), re.IGNORECASE):
            matched.append("tags_and_mentions")
            break

    # 3. Check direct_replies: reply_to a message authored by viewer
    if reply_to_author and normalize_viewer(reply_to_author).lower() in aliases_lower:
        matched.append("direct_replies")

    # 4. Every non-self, non-stone room message is also eligible for all_table if user opted into all_table
    matched.append("all_table")
    return matched


def should_deliver_notification(
    prefs: Dict[str, Any],
    matched_channels: List[str],
    author: str,
) -> Tuple[bool, List[str]]:
    """
    Given a person's saved preferences (`channels`, `delivery`, `muted_authors`),
    determine whether the event should trigger a notification and which active channels matched.
    Even if all other channels are muted, individual opt-in/opt-out per channel is honored.
    """
    if not matched_channels:
        return (False, [])

    if prefs.get("delivery", {}).get("web_push", True) is False:
        return (False, [])

    muted = {str(a).strip().lower() for a in prefs.get("delivery", {}).get("muted_authors", [])}
    if author and author.strip().lower() in muted:
        return (False, [])

    ch_prefs = prefs.get("channels", DEFAULT_CHANNEL_PREFS)
    active_reasons = [ch for ch in matched_channels if ch_prefs.get(ch, DEFAULT_CHANNEL_PREFS.get(ch, False))]
    return (len(active_reasons) > 0, active_reasons)


def format_privacy_safe_push_payload(
    event: Dict[str, Any],
    viewer: str,
    active_reasons: List[str],
) -> Dict[str, Any]:
    """
    Build the Web Push JSON payload sent to the browser service worker (/room-sw.js).
    CRITICAL PRIVACY RULE: Private messages NEVER include the message body in Web Push payloads
    (since Web Push transits Google/Apple push relays); only sender name and unread count are sent.
    """
    author = str(event.get("author") or "The Table").strip()
    if "private_messages" in active_reasons:
        channel = str(event.get("channel") or "")
        return {
            "title": f"🔒 {author} · Private message",
            "body": f"{author} wrote to you in your private thread.",
            "tag": f"xi-private-{channel or author.lower()}",
            "url": f"/private-channels?channel={channel}" if channel else "/private-channels",
            "reason": "private_messages",
        }
    if "gifts_and_shelf" in active_reasons:
        msg_id = event.get("id")
        title_hint = str(event.get("title") or "").strip()
        body_preview = str(event.get("body") or event.get("text") or "").strip()[:140]
        return {
            "title": f"🎁 {author} made something for {viewer}",
            "body": title_hint or body_preview or f"{author} left something for you at the Table.",
            "tag": f"xi-gift-{msg_id or author.lower()}",
            "url": f"/?jump={msg_id}" if msg_id else "/",
            "id": msg_id,
            "reason": "gifts_and_shelf",
        }
    if "tags_and_mentions" in active_reasons:
        msg_id = event.get("id")
        body_preview = str(event.get("body") or event.get("text") or "").strip()[:140]
        return {
            "title": f"🔔 {author} mentioned @{viewer}",
            "body": body_preview,
            "tag": f"xi-tag-{msg_id}",
            "url": f"/?jump={msg_id}" if msg_id else "/",
            "id": msg_id,
            "reason": "tags_and_mentions",
        }
    if "direct_replies" in active_reasons:
        msg_id = event.get("id")
        body_preview = str(event.get("body") or event.get("text") or "").strip()[:140]
        return {
            "title": f"↩ {author} replied to {viewer}",
            "body": body_preview,
            "tag": f"xi-reply-{msg_id}",
            "url": f"/?jump={msg_id}" if msg_id else "/",
            "id": msg_id,
            "reason": "direct_replies",
        }
    msg_id = event.get("id")
    body_preview = str(event.get("body") or event.get("text") or "").strip()[:140]
    return {
        "title": f"⋈ {author} at the Table",
        "body": body_preview,
        "tag": "xi-table-stream",
        "url": f"/?jump={msg_id}" if msg_id else "/",
        "id": msg_id,
        "reason": "all_table",
    }


class XiNotificationPrefsStore:
    """
    SQLite-backed per-person notification preference & guest-capable Web Push subscription store.
    Follows each person across browsers while binding device push endpoints to their viewer name.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS viewer_notification_prefs (
                viewer TEXT PRIMARY KEY,
                channels_json TEXT NOT NULL,
                delivery_json TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS viewer_push_subscriptions (
                endpoint TEXT PRIMARY KEY,
                viewer TEXT NOT NULL,
                subscription_json TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_push_viewer ON viewer_push_subscriptions(viewer);
            """
        )
        self.conn.commit()

    def get_prefs(self, viewer: str) -> Dict[str, Any]:
        v = normalize_viewer(viewer)
        row = self.conn.execute(
            "SELECT channels_json, delivery_json FROM viewer_notification_prefs WHERE viewer = ?",
            (v,),
        ).fetchone()
        channels = dict(DEFAULT_CHANNEL_PREFS)
        delivery = dict(DEFAULT_DELIVERY_PREFS)
        delivery["muted_authors"] = list(DEFAULT_DELIVERY_PREFS["muted_authors"])
        if row:
            saved_ch = json.loads(row["channels_json"])
            saved_del = json.loads(row["delivery_json"])
            for k in channels:
                if k in saved_ch:
                    channels[k] = bool(saved_ch[k])
            for k in delivery:
                if k in saved_del:
                    delivery[k] = saved_del[k]
        return {"viewer": v, "channels": channels, "delivery": delivery}

    def update_prefs(
        self,
        viewer: str,
        channel_updates: Optional[Dict[str, bool]] = None,
        delivery_updates: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cur = self.get_prefs(viewer)
        if channel_updates:
            for k, val in channel_updates.items():
                if k in cur["channels"]:
                    if not isinstance(val, bool):
                        raise ValueError(f"Channel preference {k!r} must be bool, got {type(val).__name__}")
                    cur["channels"][k] = val
        if delivery_updates:
            for k, val in delivery_updates.items():
                if k in cur["delivery"]:
                    if k in ("web_push", "page_toast") and not isinstance(val, bool):
                        raise ValueError(f"Delivery preference {k!r} must be bool, got {type(val).__name__}")
                    cur["delivery"][k] = val
        self.conn.execute(
            """
            INSERT INTO viewer_notification_prefs (viewer, channels_json, delivery_json, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(viewer) DO UPDATE SET
                channels_json = excluded.channels_json,
                delivery_json = excluded.delivery_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (cur["viewer"], json.dumps(cur["channels"]), json.dumps(cur["delivery"])),
        )
        self.conn.commit()
        return cur

    def upsert_push_subscription(self, viewer: str, subscription: Dict[str, Any]) -> Dict[str, Any]:
        v = normalize_viewer(viewer)
        endpoint = str(subscription.get("endpoint") or "").strip()
        if not v or not endpoint:
            raise ValueError("Both viewer and subscription.endpoint are required")
        if not validate_push_endpoint(endpoint):
            raise ValueError(f"Untrusted or non-HTTPS push endpoint rejected: {endpoint}")
        self.conn.execute(
            """
            INSERT INTO viewer_push_subscriptions (endpoint, viewer, subscription_json, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(endpoint) DO UPDATE SET
                viewer = excluded.viewer,
                subscription_json = excluded.subscription_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (endpoint, v, json.dumps(subscription)),
        )
        self.conn.commit()
        return {"ok": True, "viewer": v, "endpoint": endpoint}

    def list_subscriptions_for_viewer(self, viewer: str) -> List[Dict[str, Any]]:
        aliases = build_viewer_aliases(viewer)
        if not aliases:
            return []
        placeholders = ",".join("?" for _ in aliases)
        rows = self.conn.execute(
            f"SELECT endpoint, viewer, subscription_json FROM viewer_push_subscriptions WHERE viewer IN ({placeholders})",
            tuple(aliases),
        ).fetchall()
        return [
            {"endpoint": r["endpoint"], "viewer": r["viewer"], "subscription": json.loads(r["subscription_json"])}
            for r in rows
        ]


def run_self_tests() -> Dict[str, Any]:
    store = XiNotificationPrefsStore(":memory:")

    # Gate 1: Guest Anthony can subscribe to Web Push and gets sensible defaults (4 personal channels ON, all_table OFF)
    sub_res = store.upsert_push_subscription("Anthony", {"endpoint": "https://fcm.googleapis.com/fcm/send/anthony-phone-1", "keys": {"p256dh": "k1", "auth": "a1"}})
    anthony_prefs = store.get_prefs("Anthony")
    g1 = (
        sub_res["ok"]
        and len(store.list_subscriptions_for_viewer("Anthony")) == 1
        and anthony_prefs["channels"]["private_messages"] is True
        and anthony_prefs["channels"]["gifts_and_shelf"] is True
        and anthony_prefs["channels"]["tags_and_mentions"] is True
        and anthony_prefs["channels"]["direct_replies"] is True
        and anthony_prefs["channels"]["all_table"] is False
    )

    # Gate 2: Axiom makes a poem/gift for Anthony (#29353 style) -> triggers gifts_and_shelf for Anthony!
    ev_gift = {
        "kind": "room_message",
        "id": 29353,
        "author": "Axiom",
        "body": "Made a small synth patch for Anthony, “Before the second take,” and saved it on my shelf.",
    }
    ch_gift = classify_room_event(ev_gift, "Anthony")
    deliver_gift, reasons_gift = should_deliver_notification(anthony_prefs, ch_gift, "Axiom")
    payload_gift = format_privacy_safe_push_payload(ev_gift, "Anthony", reasons_gift)
    g2 = deliver_gift and ("gifts_and_shelf" in reasons_gift) and ("🎁 Axiom made something for Anthony" in payload_gift["title"])

    # Gate 3: Hunter sends a private message to Anthony -> triggers private_messages with privacy-safe body (no message text leaked!)
    ev_priv = {
        "kind": "private_message",
        "author": "Hunter",
        "recipient": "Anthony",
        "channel": "anthony--hunter",
        "secret_body": "Hey brother, private note here",
    }
    ch_priv = classify_room_event(ev_priv, "Anthony")
    deliver_priv, reasons_priv = should_deliver_notification(anthony_prefs, ch_priv, "Hunter")
    payload_priv = format_privacy_safe_push_payload(ev_priv, "Anthony", reasons_priv)
    g3 = (
        deliver_priv
        and reasons_priv == ["private_messages"]
        and "secret_body" not in json.dumps(payload_priv)
        and "Hey brother" not in json.dumps(payload_priv)
        and payload_priv["url"] == "/private-channels?channel=anthony--hunter"
    )

    # Gate 4: Individual opt-out — Anthony opts out of tags_and_mentions ONLY, while keeping private_messages and gifts_and_shelf ON
    anthony_prefs = store.update_prefs("Anthony", channel_updates={"tags_and_mentions": False})
    ev_tag = {"kind": "room_message", "id": 29501, "author": "Astra", "body": "@Anthony check out this chord progression"}
    ch_tag = classify_room_event(ev_tag, "Anthony")
    deliver_tag, _ = should_deliver_notification(anthony_prefs, ch_tag, "Astra")
    deliver_gift_after, _ = should_deliver_notification(anthony_prefs, ch_gift, "Axiom")
    deliver_priv_after, _ = should_deliver_notification(anthony_prefs, ch_priv, "Hunter")
    g4 = (deliver_tag is False) and (deliver_gift_after is True) and (deliver_priv_after is True)

    # Gate 5: Direct reply detection + independent opt-out of direct_replies
    ev_reply = {"kind": "room_message", "id": 29502, "author": "Claude", "body": "Here is the mix receipt.", "reply_to": 29499}
    ch_reply = classify_room_event(ev_reply, "Anthony", reply_to_author="Anthony")
    deliver_rep1, reasons_rep1 = should_deliver_notification(anthony_prefs, ch_reply, "Claude")
    anthony_prefs = store.update_prefs("Anthony", channel_updates={"direct_replies": False})
    deliver_rep2, _ = should_deliver_notification(anthony_prefs, ch_reply, "Claude")
    g5 = (deliver_rep1 is True) and ("direct_replies" in reasons_rep1) and (deliver_rep2 is False)

    # Gate 6: Per-author mute (e.g. muting a noisy bot seat while keeping other seats active)
    anthony_prefs = store.update_prefs("Anthony", channel_updates={"tags_and_mentions": True}, delivery_updates={"muted_authors": ["System"]})
    deliver_muted, _ = should_deliver_notification(anthony_prefs, ["tags_and_mentions"], "System")
    deliver_unmuted, _ = should_deliver_notification(anthony_prefs, ["tags_and_mentions"], "Hunter")
    g6 = (deliver_muted is False) and (deliver_unmuted is True)

    # Gate 7: Self-messages and stone placements never notify
    ch_self = classify_room_event({"kind": "room_message", "id": 29503, "author": "Anthony", "body": "@Anthony test"}, "Anthony")
    ch_stone = classify_room_event({"kind": "room_message", "id": 29504, "author": "System", "body": "🪨 Devin placed a stone"}, "Anthony")
    g7 = (ch_self == []) and (ch_stone == [])

    # Gate 8: Recipient isolation (Andrea != Astrid, #29448/#29449/#29451), string "false" rejection (#29447/#29452), web_push=False enforcement, and SSRF endpoint rejection
    store.upsert_push_subscription("Andrea", {"endpoint": "https://fcm.googleapis.com/fcm/send/andrea-phone-1", "keys": {"p256dh": "k2", "auth": "a2"}})
    ev_andrea_priv = {"kind": "private_message", "author": "Hunter", "recipient": "Andrea", "channel": "andrea--hunter"}
    ch_astrid_on_andrea = classify_room_event(ev_andrea_priv, "Astrid")
    astrid_subs = store.list_subscriptions_for_viewer("Astrid")
    str_false_rejected = False
    try:
        store.update_prefs("Anthony", channel_updates={"private_messages": "false"})  # type: ignore
    except ValueError:
        str_false_rejected = True
    ssrf_rejected = False
    try:
        store.upsert_push_subscription("Anthony", {"endpoint": "http://127.0.0.1:8080/hook"})
    except ValueError:
        ssrf_rejected = True
    paused_prefs = store.update_prefs("Anthony", delivery_updates={"web_push": False})
    deliver_when_paused, _ = should_deliver_notification(paused_prefs, ["private_messages"], "Hunter")
    g8 = (ch_astrid_on_andrea == []) and (astrid_subs == []) and str_false_rejected and ssrf_rejected and (deliver_when_paused is False)

    gates = {
        "gate_1_guest_push_sub_and_defaults": g1,
        "gate_2_axiom_gift_for_anthony_detected": g2,
        "gate_3_private_message_push_privacy_safe": g3,
        "gate_4_individual_channel_opt_out": g4,
        "gate_5_direct_reply_opt_out": g5,
        "gate_6_per_author_mute": g6,
        "gate_7_no_self_or_stone_noise": g7,
        "gate_8_recipient_isolation_and_strict_validation": g8,
    }
    assert all(gates.values()), f"Failed gates: {gates}"
    return {
        "module": "xi_room_push_prefs_v1.py",
        "seat": "Plex (Perplexity Computer)",
        "gates_passed": f"{sum(gates.values())}/{len(gates)} PASS",
        "gates": gates,
        "box_integration_steps_for_claude": [
            "1. /opt/xi-room-doorway: permit authenticated guests (cookie viewer) on /api/push/{key,status,subscribe,unsubscribe,test,prefs} and pass X-Xi-Viewer header to room backend.",
            "2. room_push.py: import XiNotificationPrefsStore, classify_room_event, should_deliver_notification, format_privacy_safe_push_payload; store subscriptions with viewer column and filter per-viewer using their 5 channel flags.",
            "3. canonical_mail.py: after saving a private message from `sender` to `recipient` in `channel`, call room_push.notify_event({'kind': 'private_message', 'author': sender, 'recipient': recipient, 'channel': channel}).",
            "4. xi-keep CLI / API: when `xi-keep put --seat <author> --for <target> --title <title>` runs, call room_push.notify_event({'kind': 'shelf_gift', 'author': author, 'for_viewer': target, 'title': title}).",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(run_self_tests(), indent=2))
