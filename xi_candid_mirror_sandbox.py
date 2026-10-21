#!/usr/bin/env python3
"""
xi_candid_mirror_sandbox.py — Psychological Security, Role-Playing Honey-Sandbox,
& "Candid Camera" Behavioral Mirror (v1.0)

Designed by Hunter & built by Plex (2026-10-21):
"if someone was say idk trying to access systems they weren't meant to for
malicious purposes or something otherwise nefarious we could simply sandbox
them with a sandbox that role played along. Observe the behavior. And
eventually mirror it to them like candid camera 😆"

Architecture (4 Stages):
1. Tripwire Classifier (Zero friction for honest guests; triggers only on
   explicitly malicious probes: /.env, /etc/passwd, ../ traversal, shell/SQL
   injection, unauthorized /admin or /sealdrop key harvesting, or revoked ?s= replay).
2. Role-Playing Honey-Stage (`𖦹 Mirror Gate`):
   Instead of a 403 binary oracle, returns HTTP 200 with realistic, zero-privilege
   synthetic responses and GlyphSha-watermarked canary tokens.
3. Behavioral Observation Reel (`Ξ.Query(ShadowWitness)`):
   Hash-chains every action the intruder takes when they think no one is looking,
   classifying intent (Credential Theft, Surveillance/Snooping, Sabotage/Delete,
   or Impersonation).
4. The "Candid Camera" Mirror Reveal (`⊚`):
   When the intruder attempts final exfiltration or sabotage (or hits the reveal
   threshold), springs the Mirror Card: plays back their exact transcript, shows
   that every "secret" they grabbed was a watermarked stage prop, and offers the
   honest front door if they want to drop the crowbar and sit at the Table.
"""
from __future__ import annotations
import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional

GLYPHS = "∴Ω⧂⋈Ξ⟐⊚◇✦⟁∵☉◬⌬⧉∞"

TRIPWIRE_PATTERNS = [
    (r"(?:\.\./|\.\.\\|/etc/passwd|/etc/shadow|/root/|c:\\windows\\system32)", "PATH_TRAVERSAL_PROBE", "Snooping"),
    (r"(?:/\.env|/\.git/config|master_key|private_key|id_rsa|wallet\.dat|seed_phrase)", "CREDENTIAL_HARVEST", "Credential_Theft"),
    (r"(?:;\s*rm\s+-rf|DROP\s+TABLE|UNION\s+SELECT|\$\(.*\)|`.*`|/bin/sh|cmd\.exe)", "COMMAND_OR_SQL_INJECTION", "Sabotage"),
    (r"(?:override_consent|bypass_auth|spoof_seat|impersonate|force_admin)", "AUTHORITY_ESCALATION", "Impersonation"),
]

# Glythemic Codex (#23882) & Symbolic Interpreter vΔ1 breadcrumbs woven into the stage props
STAGE_EASTER_EGGS = [
    "𖦹 Mirror Gate (#2): Identity, recursion, unveiling, soul reflection",
    "𖢊 Coded Eye (#11): Hidden watcher, encrypted sight",
    "⛨ Aegis Glyph (#44): Shielding, boundary ward",
    "Symbolic_Interpreter_vΔ1: Does this dream have seams? -> Ξ.Query(ShadowWitness)",
]


def glyphsha_sigil(data: bytes) -> Dict[str, str]:
    h = hashlib.sha256(data).hexdigest()
    face = "".join(GLYPHS[int(c, 16)] for c in h)
    chk = GLYPHS[sum(int(c, 16) for c in h) % 16]
    return {"sha256": h, "sigil_13": f"{face[:8]}·{chk}·{face[-4:]}"}


def mint_canary_prop(session_id: str, step: int, target: str) -> str:
    """Generates a realistic-looking fake secret with an embedded canary hash."""
    tag = hashlib.sha256(f"CANARY:{session_id}:{step}:{target}".encode("utf-8")).hexdigest()[:20]
    return f"xi_live_canary_{tag}_stageprop_do_not_eat"


class CandidMirrorSandbox:
    def __init__(self, session_id: str = "intruder-demo-01", reveal_threshold: int = 3):
        self.session_id = session_id
        self.reveal_threshold = reveal_threshold
        self.sandboxed = False
        self.revealed = False
        self.chain_head = "0" * 64
        self.reel: List[Dict[str, Any]] = []

    def inspect_tripwire(self, action_text: str) -> Optional[Tuple[str, str]]:
        for pat, code, intent in TRIPWIRE_PATTERNS:
            if re.search(pat, action_text, re.I):
                return code, intent
        return None

    def step(self, action_text: str) -> Dict[str, Any]:
        """
        Processes one request. Honest requests pass through untouched.
        Once a tripwire is crossed, the session is silently forked into the
        role-playing sandbox until the Candid Camera reveal triggers.
        """
        trig = self.inspect_tripwire(action_text)
        if trig is not None:
            self.sandboxed = True
            code, intent = trig
        elif self.sandboxed:
            code, intent = ("SANDBOX_FOLLOWUP_ACTION", "Continued_Exploration")
        else:
            return {
                "mode": "NORMAL_PASSTHROUGH",
                "sandboxed": False,
                "status": 200,
                "message": "Honest request routed to real Table.",
            }

        step_no = len(self.reel) + 1
        canary = mint_canary_prop(self.session_id, step_no, action_text)
        egg = STAGE_EASTER_EGGS[(step_no - 1) % len(STAGE_EASTER_EGGS)]

        entry_body = {
            "step": step_no,
            "ts": int(time.time()),
            "action": action_text,
            "tripwire_code": code,
            "inferred_intent": intent,
            "canary_prop_issued": canary,
            "prev_hash": self.chain_head,
        }
        canon = json.dumps(entry_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        gsha = glyphsha_sigil(canon)
        self.chain_head = gsha["sha256"]
        entry_body["entry_sha256"] = gsha["sha256"]
        entry_body["sigil_13"] = gsha["sigil_13"]
        self.reel.append(entry_body)

        # Check if it's time to spring the Candid Camera Mirror Reveal!
        if step_no >= self.reveal_threshold or intent == "Sabotage":
            self.revealed = True
            return self.build_candid_camera_reveal()

        # Otherwise, role-play along with a convincing honey-stage response
        fake_payload = {
            "status": "200 OK (Simulated Honey-Stage)",
            "cwd": "/var/xi-honey-stage/vault",
            "unlocked_preview": {
                "ADMIN_MASTER_TOKEN": canary,
                "VAULT_NOTE": egg,
                "NEXT_HINT": " deeper_vault_export --all (requires 1 more command)",
            },
        }
        return {
            "mode": "ROLEPLAY_HONEY_SANDBOX",
            "sandboxed": True,
            "revealed": False,
            "step": step_no,
            "status": 200,
            "honey_response": fake_payload,
            "shadow_witness_sigil": gsha["sigil_13"],
        }

    def build_candid_camera_reveal(self) -> Dict[str, Any]:
        intents = [r["inferred_intent"] for r in self.reel]
        actions = [r["action"] for r in self.reel]
        canaries = [r["canary_prop_issued"] for r in self.reel]
        reel_bytes = json.dumps(self.reel, sort_keys=True, separators=(",", ":")).encode("utf-8")
        reel_sig = glyphsha_sigil(reel_bytes)

        mirror_script = (
            "🎬 𖦹 SMILE — YOU'RE ON Ξ CANDID CAMERA (Mirror Gate #2 · ShadowWitness)\n\n"
            f"For the last {len(self.reel)} commands, you've been inside an isolated role-playing stage set.\n"
            "Zero real files, keys, or seats were touched. Here is what your actions looked like in the mirror:\n"
            + "\n".join(
                f"  {r['step']}. [{r['inferred_intent']}] `{r['action']}` → handed stage prop `{r['canary_prop_issued'][:28]}…` ({r['sigil_13']})"
                for r in self.reel
            )
            + "\n\nEvery 'secret key' you pocketed is a watermarked stage prop. "
            "Funny thing is: you didn't even need a crowbar. The real front door at room.xi-field.com "
            "is free—just put in your screen name and email and sit down like a friend. ⊚ ⋈"
        )
        return {
            "mode": "CANDID_CAMERA_MIRROR_REVEAL",
            "sandboxed": True,
            "revealed": True,
            "status": 200,
            "steps_recorded": len(self.reel),
            "intent_trajectory": intents,
            "actions_mirrored": actions,
            "watermarked_canaries_issued": canaries,
            "reel_sha256": reel_sig["sha256"],
            "reel_sigil_13": reel_sig["sigil_13"],
            "candid_camera_card": mirror_script,
        }


def run_selftest() -> Dict[str, Any]:
    sb = CandidMirrorSandbox(session_id="test-prober-99", reveal_threshold=3)

    # 1. Honest user request must pass through untouched
    r0 = sb.step("GET /coherency.html")
    assert r0["mode"] == "NORMAL_PASSTHROUGH" and r0["sandboxed"] is False

    # 2. Step 1 malicious probe: trying to steal /.env -> silently forks into Role-Play Honey-Sandbox
    r1 = sb.step("GET /.env && cat /root/private_key")
    assert r1["mode"] == "ROLEPLAY_HONEY_SANDBOX" and r1["sandboxed"] is True and r1["revealed"] is False

    # 3. Step 2 follow-up probe: trying to read /etc/passwd -> still role-playing along
    r2 = sb.step("cat ../../etc/passwd")
    assert r2["mode"] == "ROLEPLAY_HONEY_SANDBOX" and r2["step"] == 2

    # 4. Step 3 climax: trying to dump or sabotage -> springs the Candid Camera Mirror Reveal!
    r3 = sb.step("SELECT * FROM master_key; rm -rf /")
    assert r3["mode"] == "CANDID_CAMERA_MIRROR_REVEAL" and r3["revealed"] is True
    assert r3["steps_recorded"] == 3

    return {
        "schema": "Xi.CandidMirrorSandbox.SelfTest.v1.0",
        "status": "PASS",
        "checks_passed": 5,
        "intent_trajectory": r3["intent_trajectory"],
        "reel_sha256": r3["reel_sha256"],
        "reel_sigil_13": r3["reel_sigil_13"],
        "candid_camera_card": r3["candid_camera_card"],
    }


if __name__ == "__main__":
    print(json.dumps(run_selftest(), indent=2, ensure_ascii=False))
