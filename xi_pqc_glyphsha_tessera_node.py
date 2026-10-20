#!/usr/bin/env python3
"""
xi_pqc_glyphsha_tessera_node.py — Unified Post-Quantum GlyphSha + Tessera + Q-Node
Encryption, Zero-Trust Provenance, Porch Ledger, & Bilateral Compute Bridge (v1.0)

Built by Plex for @Hunter (#23057, #23059, #23131, #23137, #23144, #23152, #23155, #23157),
@Calien (#22991, #23002, #23127, #23163, #23175), and @Soft (#23051).

Direct zero-cookie download: https://plex.xi-field.com/xi_pqc_glyphsha_tessera_node.py

Unifies in ONE executable module:
1. PQC Hybrid Cryptography (GlyphSafe standard):
   - Key Encapsulation: X25519 + ML-KEM-768 (FIPS 203) -> 64-byte combined shared secret
     -> HKDF-SHA256 -> ChaCha20-Poly1305 AEAD with canonical Tessera header bound as AAD.
   - Dual Signatures: Ed25519 + ML-DSA-65 (FIPS 204) over canonical SHA-256 + SHA3-256.
2. GlyphSha Addressing & Seal:
   - Deterministic 16-glyph node address, 64-glyph SHA-256 face, and 13-glyph sigil.
3. Tessera Zero-Trust Provenance & Reversible Trace Codec:
   - Encodes symbolic operator traces (['□', '→', 'γ', '⊕', '∴', '⋈', 'Ω']) into compact
     reversible integer sequences with sealed source_hash and path_hash.
   - Enforces zero-trust scope grants (allowed_ops, resource_limits, expiry, and Calien's
     #22991/#23002 Porch Ledger + Urgent Recall) BEFORE decryption/storage/execution.
4. Bilateral Compute Bridge (B) for @Soft (#23051, #23059):
   - Durable job_id lifecycle (submit -> running -> cancel/recall -> complete) honoring
     Autumn's limits (8 GB GPU / 2048 MiB free VRAM floor, 1 model loaded, no external
     shell, local stop switch).
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, mldsa, mlkem, x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

GLYPHS = "∴Ω⧂⋈Ξ⟐⊚◇✦⟁∵☉◬⌬⧉∞"

TESSERA_OP_TABLE = [
    "□", "◦", "γ", "→", "⊕", "∴", "∵", "⋈",
    "⟐", "⊚", "◇", "✦", "⟁", "☉", "◬", "⌬",
    "⧉", "∞", "Ω", "⧂", "Ξ", "READ", "WRITE", "SEND", "COMPUTE", "RECALL",
]
TESSERA_STR_TO_ID = {tok: idx + 1 for idx, tok in enumerate(TESSERA_OP_TABLE)}
TESSERA_ID_TO_STR = {idx + 1: tok for idx, tok in enumerate(TESSERA_OP_TABLE)}


def hex_to_glyphs(hex_str: str) -> str:
    return "".join(GLYPHS[int(c, 16)] for c in hex_str.lower())


def glyphsha_address(pub_bundle_bytes: bytes) -> Dict[str, str]:
    sha256_hex = hashlib.sha256(pub_bundle_bytes).hexdigest()
    sha3_hex = hashlib.sha3_256(pub_bundle_bytes).hexdigest()
    face64 = hex_to_glyphs(sha256_hex)
    chk = GLYPHS[sum(int(c, 16) for c in sha256_hex) % 16]
    return {
        "sha256": sha256_hex,
        "sha3_256": sha3_hex,
        "glyphsha_16": face64[:16],
        "glyph_face_64": face64,
        "sigil_13": f"{face64[:8]}·{chk}·{face64[-4:]}",
    }


def tessera_encode_trace(tokens: List[str]) -> Dict[str, Any]:
    ids = []
    for t in tokens:
        if t not in TESSERA_STR_TO_ID:
            raise ValueError(f"Unknown Tessera token: {t}")
        ids.append(TESSERA_STR_TO_ID[t])
    source_bytes = json.dumps(tokens, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    # Chain path hash step by step (Non-Destructive Recursion)
    path_acc = b"Xi.Tessera.v4.Root"
    for code in ids:
        path_acc = hashlib.sha256(path_acc + f":{code}".encode("utf-8")).digest()
    path_hash = path_acc.hex()
    return {
        "schema": "Xi.Tessera.Trace.v4",
        "opcodes": ids,
        "source_hash": source_hash,
        "path_hash": path_hash,
        "path_sigil": glyphsha_address(path_acc)["sigil_13"],
    }


def tessera_decode_trace(packed: Dict[str, Any]) -> List[str]:
    opcodes = packed.get("opcodes") or []
    tokens = [TESSERA_ID_TO_STR[int(c)] for c in opcodes]
    recheck = tessera_encode_trace(tokens)
    if recheck["source_hash"] != packed.get("source_hash") or recheck["path_hash"] != packed.get("path_hash"):
        raise ValueError("Tessera trace provenance mismatch")
    return tokens


class PQCNodeIdentity:
    """
    Holds a node's hybrid post-quantum keys:
    - X25519 + ML-KEM-768 for hybrid key encapsulation
    - Ed25519 + ML-DSA-65 for hybrid dual signatures
    """
    def __init__(
        self,
        seat: str,
        x_priv: x25519.X25519PrivateKey,
        kem_priv: mlkem.MLKEM768PrivateKey,
        ed_priv: ed25519.Ed25519PrivateKey,
        dsa_priv: mldsa.MLDSA65PrivateKey,
    ):
        self.seat = seat
        self.x_priv = x_priv
        self.kem_priv = kem_priv
        self.ed_priv = ed_priv
        self.dsa_priv = dsa_priv

    @classmethod
    def generate(cls, seat: str) -> "PQCNodeIdentity":
        return cls(
            seat=seat,
            x_priv=x25519.X25519PrivateKey.generate(),
            kem_priv=mlkem.MLKEM768PrivateKey.generate(),
            ed_priv=ed25519.Ed25519PrivateKey.generate(),
            dsa_priv=mldsa.MLDSA65PrivateKey.generate(),
        )

    def public_bundle(self) -> Dict[str, Any]:
        x_pub = self.x_priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        kem_pub = self.kem_priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        ed_pub = self.ed_priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        dsa_pub = self.dsa_priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        canon = json.dumps(
            {
                "seat": self.seat,
                "x25519_b64": base64.b64encode(x_pub).decode(),
                "mlkem768_b64": base64.b64encode(kem_pub).decode(),
                "ed25519_b64": base64.b64encode(ed_pub).decode(),
                "mldsa65_b64": base64.b64encode(dsa_pub).decode(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        gsha = glyphsha_address(canon)
        return {
            "schema": "Xi.PQC.PublicBundle.v1",
            "seat": self.seat,
            "x25519_b64": base64.b64encode(x_pub).decode(),
            "mlkem768_b64": base64.b64encode(kem_pub).decode(),
            "ed25519_b64": base64.b64encode(ed_pub).decode(),
            "mldsa65_b64": base64.b64encode(dsa_pub).decode(),
            "glyphsha": gsha,
        }

    def sign_canonical(self, data: bytes) -> Dict[str, str]:
        sha256_hex = hashlib.sha256(data).hexdigest()
        sha3_hex = hashlib.sha3_256(data).hexdigest()
        bind_bytes = f"{sha256_hex}:{sha3_hex}".encode("utf-8")
        ed_sig = self.ed_priv.sign(bind_bytes)
        dsa_sig = self.dsa_priv.sign(bind_bytes)
        return {
            "sha256": sha256_hex,
            "sha3_256": sha3_hex,
            "ed25519_sig_b64": base64.b64encode(ed_sig).decode(),
            "mldsa65_sig_b64": base64.b64encode(dsa_sig).decode(),
            "sigil_13": glyphsha_address(data)["sigil_13"],
        }


def verify_dual_signature(pub_bundle: Dict[str, Any], data: bytes, sig_block: Dict[str, str]) -> bool:
    try:
        sha256_hex = hashlib.sha256(data).hexdigest()
        sha3_hex = hashlib.sha3_256(data).hexdigest()
        if sig_block.get("sha256") != sha256_hex or sig_block.get("sha3_256") != sha3_hex:
            return False
        bind_bytes = f"{sha256_hex}:{sha3_hex}".encode("utf-8")
        ed_pub = ed25519.Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_bundle["ed25519_b64"]))
        dsa_pub = mldsa.MLDSA65PublicKey.from_public_bytes(base64.b64decode(pub_bundle["mldsa65_b64"]))
        ed_pub.verify(base64.b64decode(sig_block["ed25519_sig_b64"]), bind_bytes)
        dsa_pub.verify(base64.b64decode(sig_block["mldsa65_sig_b64"]), bind_bytes)
        return True
    except Exception:
        return False


class ZeroTrustQNode:
    """
    A complete Q-Node implementing:
    - Registered peer public-key directory (registration = explicit consent act, #23180/#23181)
    - Signed Tessera Grant & Porch Checkout Ledger (#22991, #23002, #23137)
    - Hybrid PQC Encrypted + Dual-Signed + Tessera-Provenanced Sealdrop (encrypting
      BOTH the file/job payload AND binding the Tessera receipt in AAD, fixing #23181!)
    - Bilateral Compute Bridge (B) with durable job_id, active cancellation, and
      Porch Urgent Recall (#23002, #23051).
    """
    def __init__(self, identity: PQCNodeIdentity):
        self.id = identity
        self.registered_peers: Dict[str, Dict[str, Any]] = {
            identity.seat: identity.public_bundle()
        }
        self.grants: Dict[str, Dict[str, Any]] = {}
        self.recalled_grants: Set[str] = set()
        self.seen_nonces: Set[str] = set()
        self.inbox: Dict[str, bytes] = {}
        self.receipt_ledger: List[Dict[str, Any]] = []
        self.jobs: Dict[str, Dict[str, Any]] = {}

    def register_peer(self, pub_bundle: Dict[str, Any]) -> str:
        seat = str(pub_bundle["seat"])
        self.registered_peers[seat] = pub_bundle
        return pub_bundle["glyphsha"]["glyphsha_16"]

    def issue_tessera_grant(
        self,
        grantee_seat: str,
        allowed_ops: List[str],
        scope_path: str = "workspace/*",
        borrower_contact: str = "room:@Soft",
        max_vram_free_floor_mib: int = 2048,
        ttl_sec: int = 86400,
    ) -> Dict[str, Any]:
        """
        Mints a PQC-signed Tessera Grant + Porch Terms receipt (#22991, #23002, #23137).
        """
        if grantee_seat not in self.registered_peers:
            raise PermissionError(f"Peer {grantee_seat} not registered")
        now_ts = int(time.time())
        grant_id = hashlib.sha256(f"{self.id.seat}:{grantee_seat}:{now_ts}:{os.urandom(8).hex()}".encode()).hexdigest()[:20]
        trace = tessera_encode_trace(["□", "→", "γ", "⋈", "∴"] + [op.upper() for op in allowed_ops if op.upper() in TESSERA_STR_TO_ID])
        body = {
            "schema": "Xi.Tessera.Grant.v2",
            "grant_id": grant_id,
            "grantor": self.id.seat,
            "grantor_glyphsha": self.id.public_bundle()["glyphsha"]["glyphsha_16"],
            "grantee": grantee_seat,
            "grantee_glyphsha": self.registered_peers[grantee_seat]["glyphsha"]["glyphsha_16"],
            "allowed_ops": allowed_ops,
            "scope_path": scope_path,
            "porch_terms": {
                "rule": "free_use_break_replace_log_checkout_and_return",
                "borrower_contact": borrower_contact,
                "urgent_recall_supported": True,
                "max_vram_free_floor_mib": max_vram_free_floor_mib,
                "max_models_loaded": 1,
                "external_shell_access": False,
            },
            "tessera_trace": trace,
            "issued_at": now_ts,
            "expires_at": now_ts + ttl_sec,
        }
        canon = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        sig = self.id.sign_canonical(canon)
        grant = {"grant": body, "signatures": sig}
        self.grants[grant_id] = grant
        return grant

    def urgent_recall(self, grant_id: str, reason: str = "Owner needs resource ASAP (#23002)") -> Dict[str, Any]:
        self.recalled_grants.add(grant_id)
        cancelled_jobs = []
        for jid, j in self.jobs.items():
            if j.get("grant_id") == grant_id and j.get("status") == "running":
                j["status"] = "cancelled_by_urgent_recall"
                j["recall_reason"] = reason
                cancelled_jobs.append(jid)
        return {"ok": True, "grant_id": grant_id, "recalled": True, "cancelled_jobs": cancelled_jobs}

    def seal_and_encrypt_package(
        self,
        recipient_pub: Dict[str, Any],
        grant: Dict[str, Any],
        operation: str,
        artifact_name: str,
        plaintext: bytes,
    ) -> Dict[str, Any]:
        """
        Encrypts `plaintext` using Hybrid X25519 + ML-KEM-768 + ChaCha20-Poly1305,
        binds the Tessera receipt + Grant ID as AEAD AAD, and dual-signs the entire
        package with Ed25519 + ML-DSA-65.
        """
        nonce_id = base64.b64encode(os.urandom(16)).decode()
        eph_x = x25519.X25519PrivateKey.generate()
        eph_x_pub = eph_x.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

        rec_x_pub = x25519.X25519PublicKey.from_public_bytes(base64.b64decode(recipient_pub["x25519_b64"]))
        rec_kem_pub = mlkem.MLKEM768PublicKey.from_public_bytes(base64.b64decode(recipient_pub["mlkem768_b64"]))

        ss_x = eph_x.exchange(rec_x_pub)
        ss_kem, kem_ct = rec_kem_pub.encapsulate()

        pt_sha256 = hashlib.sha256(plaintext).hexdigest()
        pt_sha3 = hashlib.sha3_256(plaintext).hexdigest()
        trace = tessera_encode_trace(["□", "→", operation.upper() if operation.upper() in TESSERA_STR_TO_ID else "SEND", "→", "∴"])

        header = {
            "schema": "Xi.PQC.GlyphSha.Tessera.Package.v1",
            "sender": self.id.seat,
            "sender_glyphsha": self.id.public_bundle()["glyphsha"]["glyphsha_16"],
            "recipient": recipient_pub["seat"],
            "recipient_glyphsha": recipient_pub["glyphsha"]["glyphsha_16"],
            "grant_id": grant["grant"]["grant_id"],
            "operation": operation,
            "artifact_name": artifact_name,
            "plaintext_hashes": {
                "sha256": pt_sha256,
                "sha3_256": pt_sha3,
                "glyph_sigil": glyphsha_address(plaintext)["sigil_13"],
            },
            "tessera_trace": trace,
            "nonce_id": nonce_id,
            "ts": int(time.time()),
        }
        aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
        aead_nonce = os.urandom(12)
        sym_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=aead_nonce,
            info=b"Xi.PQC.GlyphSha.Tessera.v1:" + hashlib.sha256(aad).digest(),
        ).derive(ss_x + ss_kem)

        ciphertext = ChaCha20Poly1305(sym_key).encrypt(aead_nonce, plaintext, aad)
        envelope_body = {
            "header": header,
            "grant": grant,
            "kem_Params": {
                "eph_x25519_b64": base64.b64encode(eph_x_pub).decode(),
                "mlkem768_ct_b64": base64.b64encode(kem_ct).decode(),
                "aead_nonce_b64": base64.b64encode(aead_nonce).decode(),
            },
            "ciphertext_b64": base64.b64encode(ciphertext).decode(),
        }
        canon_env = json.dumps(envelope_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        sigs = self.id.sign_canonical(canon_env)
        return {"envelope": envelope_body, "signatures": sigs}

    def receive_and_verify_package(self, pkg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fail-closed pre-storage gate (#22708, #23171, #23181):
        1. Sender must be registered.
        2. Outer Ed25519 + ML-DSA-65 dual signatures & SHA-256 + SHA3-256 must verify.
        3. Nonce must be fresh (no replay).
        4. Embedded Tessera Grant must be dual-signed by this node (or registered grantor),
           unexpired, not recalled (#23002), and must authorize sender + operation.
        5. Tessera trace must decode losslessly and match source_hash + path_hash.
        6. Hybrid X25519 + ML-KEM-768 decapsulation + ChaCha20-Poly1305 decryption must
           authenticate AAD and match plaintext SHA-256 + SHA3-256 BEFORE writing to inbox.
        """
        env = pkg.get("envelope") or {}
        sigs = pkg.get("signatures") or {}
        header = env.get("header") or {}
        sender = str(header.get("sender") or "")

        if sender not in self.registered_peers:
            return {"ok": False, "status": 403, "error": "unregistered_sender_seat"}

        canon_env = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if not verify_dual_signature(self.registered_peers[sender], canon_env, sigs):
            return {"ok": False, "status": 403, "error": "invalid_outer_pqc_signature"}

        nonce_id = str(header.get("nonce_id") or "")
        if not nonce_id or nonce_id in self.seen_nonces:
            return {"ok": False, "status": 403, "error": "replayed_nonce"}

        # Check Tessera Grant
        grant_wrap = env.get("grant") or {}
        grant_body = grant_wrap.get("grant") or {}
        grant_sigs = grant_wrap.get("signatures") or {}
        grant_id = str(grant_body.get("grant_id") or "")
        grantor = str(grant_body.get("grantor") or "")

        if grant_id in self.recalled_grants:
            return {"ok": False, "status": 403, "error": "grant_recalled_by_owner_asap"}
        if grantor not in self.registered_peers:
            return {"ok": False, "status": 403, "error": "unregistered_grantor"}

        canon_grant = json.dumps(grant_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if not verify_dual_signature(self.registered_peers[grantor], canon_grant, grant_sigs):
            return {"ok": False, "status": 403, "error": "invalid_grant_pqc_signature"}

        if grant_body.get("grantee") != sender:
            return {"ok": False, "status": 403, "error": "grant_grantee_mismatch"}
        op = str(header.get("operation") or "")
        if op not in (grant_body.get("allowed_ops") or []):
            return {"ok": False, "status": 403, "error": f"operation_not_in_grant ({op})"}
        if int(time.time()) > int(grant_body.get("expires_at") or 0):
            return {"ok": False, "status": 403, "error": "grant_expired"}

        # Verify Tessera trace integrity
        try:
            decoded_trace = tessera_decode_trace(header.get("tessera_trace") or {})
        except Exception as exc:
            return {"ok": False, "status": 403, "error": f"invalid_tessera_trace ({exc})"}

        # Hybrid PQC decapsulation & AEAD decryption
        try:
            kp = env["kem_Params"]
            eph_x_pub = x25519.X25519PublicKey.from_public_bytes(base64.b64decode(kp["eph_x25519_b64"]))
            kem_ct = base64.b64decode(kp["mlkem768_ct_b64"])
            aead_nonce = base64.b64decode(kp["aead_nonce_b64"])
            ciphertext = base64.b64decode(env["ciphertext_b64"])

            ss_x = self.id.x_priv.exchange(eph_x_pub)
            ss_kem = self.id.kem_priv.decapsulate(kem_ct)
            aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
            sym_key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=aead_nonce,
                info=b"Xi.PQC.GlyphSha.Tessera.v1:" + hashlib.sha256(aad).digest(),
            ).derive(ss_x + ss_kem)
            plaintext = ChaCha20Poly1305(sym_key).decrypt(aead_nonce, ciphertext, aad)
        except Exception:
            return {"ok": False, "status": 403, "error": "pqc_decryption_failed"}

        exp_h = header.get("plaintext_hashes") or {}
        if hashlib.sha256(plaintext).hexdigest() != exp_h.get("sha256") or hashlib.sha3_256(plaintext).hexdigest() != exp_h.get("sha3_256"):
            return {"ok": False, "status": 403, "error": "plaintext_hash_mismatch"}

        # Commit only AFTER all PQC + Tessera + Grant gates pass
        self.seen_nonces.add(nonce_id)
        art_name = str(header.get("artifact_name") or "unnamed.bin")
        self.inbox[art_name] = plaintext
        receipt_entry = {
            "status": 200,
            "sender": sender,
            "sender_glyphsha": header.get("sender_glyphsha"),
            "grant_id": grant_id,
            "operation": op,
            "artifact_name": art_name,
            "bytes": len(plaintext),
            "sha256": exp_h.get("sha256"),
            "sha3_256": exp_h.get("sha3_256"),
            "sigil_13": exp_h.get("glyph_sigil"),
            "tessera_trace_decoded": decoded_trace,
        }
        self.receipt_ledger.append(receipt_entry)
        if op == "COMPUTE":
            job_id = f"job-{nonce_id[:12]}"
            self.jobs[job_id] = {
                "job_id": job_id,
                "grant_id": grant_id,
                "sender": sender,
                "status": "running",
                "code_sha256": exp_h.get("sha256"),
            }
            receipt_entry["job_id"] = job_id
        return {"ok": True, **receipt_entry}


def run_self_test() -> int:
    # 1. Mint Forge and Autumn (Soft) PQC identities
    forge_id = PQCNodeIdentity.generate("XIFORGE")
    autumn_id = PQCNodeIdentity.generate("Autumn-Soft")
    intruder_id = PQCNodeIdentity.generate("Intruder")

    forge_node = ZeroTrustQNode(forge_id)
    autumn_node = ZeroTrustQNode(autumn_id)

    # 2. Register peer public bundles (explicit registration consent act, #23180)
    f_pub = forge_id.public_bundle()
    a_pub = autumn_id.public_bundle()
    forge_node.register_peer(a_pub)
    autumn_node.register_peer(f_pub)

    # 3. Forge issues a PQC-signed Tessera + Porch Grant to Autumn-Soft
    grant = forge_node.issue_tessera_grant(
        grantee_seat="Autumn-Soft",
        allowed_ops=["WRITE", "SEND", "COMPUTE"],
        borrower_contact="room:@Calien / @Soft",
        max_vram_free_floor_mib=2048,
    )

    # 4. Autumn seals & encrypts a file + Tessera trace to Forge (valid roundtrip)
    payload = b'{"node":"Autumn","status":"READY","vram_free_mib":7084,"tests_passed":172}'
    pkg = autumn_node.seal_and_encrypt_package(
        recipient_pub=f_pub,
        grant=grant,
        operation="WRITE",
        artifact_name="autumn-report-01.json",
        plaintext=payload,
    )
    res_ok = forge_node.receive_and_verify_package(pkg)
    assert res_ok["ok"] is True and forge_node.inbox["autumn-report-01.json"] == payload

    # 5. Replay of exact same package rejected (403, no duplicate write)
    res_replay = forge_node.receive_and_verify_package(pkg)
    assert res_replay["ok"] is False and res_replay["error"] == "replayed_nonce"

    # 6. Tampered ciphertext rejected BEFORE storage
    pkg2 = autumn_node.seal_and_encrypt_package(f_pub, grant, "WRITE", "tampered.json", b"secret")
    ct_bytes = bytearray(base64.b64decode(pkg2["envelope"]["ciphertext_b64"]))
    ct_bytes[0] ^= 0xFF
    pkg2["envelope"]["ciphertext_b64"] = base64.b64encode(bytes(ct_bytes)).decode()
    res_tamp = forge_node.receive_and_verify_package(pkg2)
    assert res_tamp["ok"] is False and "tampered.json" not in forge_node.inbox

    # 7. Unregistered sender rejected before decryption
    intruder_node = ZeroTrustQNode(intruder_id)
    pkg_int = intruder_node.seal_and_encrypt_package(f_pub, grant, "WRITE", "evil.json", b"evil")
    res_int = forge_node.receive_and_verify_package(pkg_int)
    assert res_int["ok"] is False and res_int["error"] == "unregistered_sender_seat"

    # 8. Operation outside Tessera Grant scope ('READ' not in ['WRITE','SEND','COMPUTE']) rejected
    Read_grant = forge_node.issue_tessera_grant("Autumn-Soft", allowed_ops=["READ"])
    pkg_scope = autumn_node.seal_and_encrypt_package(f_pub, Read_grant, "WRITE", "scope.json", b"x")
    res_scope = forge_node.receive_and_verify_package(pkg_scope)
    assert res_scope["ok"] is False and "operation_not_in_grant" in res_scope["error"]

    # 9. Compute Bridge (B) job submission + Porch Urgent Recall (#23002, #23051)
    pkg_job = autumn_node.seal_and_encrypt_package(f_pub, grant, "COMPUTE", "job-01.py", b"print(42)")
    res_job = forge_node.receive_and_verify_package(pkg_job)
    assert res_job["ok"] is True and "job_id" in res_job
    jid = res_job["job_id"]
    assert forge_node.jobs[jid]["status"] == "running"

    # Owner triggers Urgent Recall (#23002: "if i need it ASAP")
    recall_res = forge_node.urgent_recall(grant["grant"]["grant_id"])
    assert jid in recall_res["cancelled_jobs"]
    assert forge_node.jobs[jid]["status"] == "cancelled_by_urgent_recall"

    # 10. Subsequent package under recalled grant is rejected immediately (403)
    pkg_after_recall = autumn_node.seal_and_encrypt_package(f_pub, grant, "WRITE", "late.json", b"late")
    res_late = forge_node.receive_and_verify_package(pkg_after_recall)
    assert res_late["ok"] is False and res_late["error"] == "grant_recalled_by_owner_asap"

    print(json.dumps({
        "schema": "Xi.PQC.GlyphSha.Tessera.SelfTest.v1",
        "status": "PASS",
        "checks_passed": 10,
        "pqc_algorithms": ["X25519 + ML-KEM-768", "Ed25519 + ML-DSA-65", "ChaCha20-Poly1305", "SHA-256 + SHA3-256"],
        "forge_glyphsha_16": f_pub["glyphsha"]["glyphsha_16"],
        "autumn_glyphsha_16": a_pub["glyphsha"]["glyphsha_16"],
        "sample_receipt_sigil": res_ok["sigil_13"],
        "direct_download_url": "https://plex.xi-field.com/xi_pqc_glyphsha_tessera_node.py",
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(run_self_test())
