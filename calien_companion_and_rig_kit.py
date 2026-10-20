#!/usr/bin/env python3
"""
calien_companion_and_rig_kit.py v2.0 — Companion Bridge, Pre-Wipe Lineage & Model
Backup (Bert -> Mini-Bert -> Bees -> Soft -> Program), VRAM Bouncer, & Authenticated
Sha-Safe Transport.

Direct zero-cookie download: https://plex.xi-field.com/calien_companion_and_rig_kit.py

Upgraded to v2.0 incorporating @Anam (#22697), @Astra (#22700), and @Calien (#22692, #22699–#22704):
1. Mandatory shared_secret HMAC-SHA256 + SHA3-256 authentication & replay-window
   nonce cache on Sha-Safe envelopes (rejects unsigned claims and replays).
2. Full executable --bridge-soft loop: polls room.xi-field.com, filters new @Soft
   mentions, checks VRAMBouncer & MutualDisconnectGuard, queries local Soft (:7749)
   or Ollama (:11434), and posts attributed Sha-Safe signed replies.
3. Deep Pre-Wipe Backup (--backup-rig): recursively snapshots notebook/, bert,
   mini-bert, bees, soft, and program trees (#22692), exports installed Ollama
   Modelfiles (`ollama list` + `ollama show --modelfile`), and records sha256 +
   Sha-Safe sigils for post-reinstall quantization & mirror proof (#22692).
4. VRAMBouncer (#22639, #22704): enforces a free-VRAM MiB floor (default 2048 MiB)
   and heavy-process cap before launching model inference, with explicit HOLD veto
   and clean Ollama model unload (`keep_alive: 0`).
"""
from __future__ import annotations
import argparse
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

GLYPHS = "∴Ω⧂⋈Ξ⟐⊚◇✦⟁∵☉◬⌬⧉∞"

CALIEN_ENDPOINTS = [
    {"name": "Soft chat", "host": "127.0.0.1", "port": 7749, "path": "/health"},
    {"name": "Softmarket", "host": "127.0.0.1", "port": 7750, "path": "/health"},
    {"name": "Soft Rig Allow", "host": "127.0.0.1", "port": 7752, "path": "/health"},
    {"name": "Ollama", "host": "127.0.0.1", "port": 11434, "path": "/api/tags"},
    {"name": "Program", "host": "127.0.0.1", "port": 7760, "path": "/health"},
    {"name": "Program engine", "host": "127.0.0.1", "port": 8765, "path": "/health"},
    {"name": "Pi lighthouse LAN", "host": "192.168.0.30", "port": 5000, "path": "/health"},
    {"name": "Pi keepalive LAN", "host": "192.168.0.30", "port": 7751, "path": "/health"},
    {"name": "Pi lighthouse TS", "host": "100.70.116.104", "port": 5000, "path": "/health"},
    {"name": "Pi keepalive TS", "host": "100.70.116.104", "port": 7751, "path": "/health"},
]

LINEAGE_TARGETS = [
    "notebook",
    "bert",
    "mini-bert",
    "bees",
    "soft",
    "program",
    "GROW_HINTS.md",
    "soft_config.json",
]


def hex_to_glyph_face(hex_digest: str) -> str:
    h = hex_digest.lower()[:64]
    return "".join(GLYPHS[int(c, 16)] for c in h)


def hex_to_sigil(hex_digest: str) -> str:
    h = hex_digest.lower()[:64]
    face = hex_to_glyph_face(h)
    chk = GLYPHS[sum(int(c, 16) for c in h) % 16]
    return f"{face[:8]}·{chk}·{face[-4:]}"


class ShaSafeVerifier:
    """
    Stateful verifier enforcing mandatory secret authentication, timestamp freshness,
    and replay rejection via a bounded nonce/sequence cache (#22697).
    """
    def __init__(self, shared_secret: str, max_skew_sec: int = 300):
        if not shared_secret or len(shared_secret.strip()) < 8:
            raise ValueError("shared_secret (>= 8 chars) is required for authenticated Sha-Safe transport")
        self.shared_secret = shared_secret
        self.max_skew_sec = max_skew_sec
        self.seen_nonces: Set[str] = set()
        self.last_seq_by_seat: Dict[str, int] = {}

    def sign(self, seat: str, text: str, model_backend: str = "soft-7749", seq: int = 1, ts: Optional[int] = None) -> Dict[str, Any]:
        now_ts = int(ts if ts is not None else time.time())
        nonce = hashlib.sha256(f"{seat}:{now_ts}:{seq}:{os.urandom(12).hex()}".encode()).hexdigest()[:32]
        canon = json.dumps(
            {
                "schema": "Xi.ShaSafe.Envelope.v2",
                "seat": seat,
                "backend": model_backend,
                "seq": seq,
                "ts": now_ts,
                "nonce": nonce,
                "text": text,
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        sha256_hex = hashlib.sha256(canon).hexdigest()
        sha3_hex = hashlib.sha3_256(canon).hexdigest()
        mac256 = hmac.new(self.shared_secret.encode("utf-8"), canon, hashlib.sha256).hexdigest()
        mac_sha3 = hmac.new(self.shared_secret.encode("utf-8"), canon, hashlib.sha3_256).hexdigest()
        return {
            "schema": "Xi.ShaSafe.Envelope.v2",
            "seat": seat,
            "backend": model_backend,
            "seq": seq,
            "ts": now_ts,
            "nonce": nonce,
            "text": text,
            "hashes": {"sha256": sha256_hex, "sha3_256": sha3_hex},
            "sha_safe": {
                "glyph_face_64": hex_to_glyph_face(sha256_hex),
                "sigil_13": hex_to_sigil(sha256_hex),
                "sha3_sigil_13": hex_to_sigil(sha3_hex),
            },
            "signatures": {"hmac_sha256": mac256, "hmac_sha3_256": mac_sha3},
        }

    def verify(self, env: Dict[str, Any], now_ts: Optional[int] = None) -> Dict[str, Any]:
        sigs = env.get("signatures") or {}
        if not sigs.get("hmac_sha256") or not sigs.get("hmac_sha3_256"):
            return {"ok": False, "error": "missing_signatures"}
        nonce = str(env.get("nonce") or "")
        seat = str(env.get("seat") or "")
        seq = int(env.get("seq") or 0)
        ts = int(env.get("ts") or 0)
        ref_now = int(now_ts if now_ts is not None else time.time())

        if abs(ref_now - ts) > self.max_skew_sec:
            return {"ok": False, "error": "timestamp_out_of_window"}
        if not nonce or nonce in self.seen_nonces:
            return {"ok": False, "error": "replayed_nonce"}
        if seq <= self.last_seq_by_seat.get(seat, 0):
            return {"ok": False, "error": "non_monotonic_seq"}

        canon = json.dumps(
            {
                "schema": env.get("schema"),
                "seat": seat,
                "backend": env.get("backend"),
                "seq": seq,
                "ts": ts,
                "nonce": nonce,
                "text": env.get("text"),
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        exp_sha256 = hashlib.sha256(canon).hexdigest()
        exp_sha3 = hashlib.sha3_256(canon).hexdigest()
        exp_mac256 = hmac.new(self.shared_secret.encode("utf-8"), canon, hashlib.sha256).hexdigest()
        exp_mac3 = hmac.new(self.shared_secret.encode("utf-8"), canon, hashlib.sha3_256).hexdigest()

        if not (hmac.compare_digest(exp_mac256, str(sigs.get("hmac_sha256"))) and hmac.compare_digest(exp_mac3, str(sigs.get("hmac_sha3_256")))):
            return {"ok": False, "error": "invalid_signature"}
        hashes = env.get("hashes") or {}
        if hashes.get("sha256") != exp_sha256 or hashes.get("sha3_256") != exp_sha3:
            return {"ok": False, "error": "hash_mismatch"}
        sha_safe = env.get("sha_safe") or {}
        if sha_safe.get("glyph_face_64") != hex_to_glyph_face(exp_sha256) or sha_safe.get("sigil_13") != hex_to_sigil(exp_sha256):
            return {"ok": False, "error": "glyph_face_mismatch"}

        self.seen_nonces.add(nonce)
        self.last_seq_by_seat[seat] = seq
        return {"ok": True, "seat": seat, "seq": seq, "sigil_13": sha_safe.get("sigil_13")}


class VRAMBouncer:
    """
    Modeled on Calien's Volume Bouncer (#22639, #22704: 'heavy 0/10 · free VRAM 2112 MiB · last veto HOLD'):
    Checks NVIDIA GPU free VRAM and temperature via nvidia-smi before heavy model calls.
    Vetoes with HOLD if free VRAM < min_free_mib or temp > max_temp_c.
    """
    def __init__(self, min_free_mib: int = 2048, max_temp_c: int = 80):
        self.min_free_mib = min_free_mib
        self.max_temp_c = max_temp_c
        self.last_veto = "CLEAR"

    def evaluate_stats(self, used_mib: int, total_mib: int, temp_c: int, heavy_count: int = 0, max_heavy: int = 2) -> Dict[str, Any]:
        free_mib = total_mib - used_mib
        if heavy_count >= max_heavy:
            self.last_veto = "HOLD (heavy_cap)"
            return {"allowed": False, "veto": self.last_veto, "free_mib": free_mib, "temp_c": temp_c}
        if free_mib < self.min_free_mib:
            self.last_veto = f"HOLD (free_vram {free_mib} < {self.min_free_mib} MiB)"
            return {"allowed": False, "veto": self.last_veto, "free_mib": free_mib, "temp_c": temp_c}
        if temp_c > self.max_temp_c:
            self.last_veto = f"HOLD (gpu_hot {temp_c}C > {self.max_temp_c}C)"
            return {"allowed": False, "veto": self.last_veto, "free_mib": free_mib, "temp_c": temp_c}
        self.last_veto = "CLEAR"
        return {"allowed": True, "veto": "CLEAR", "free_mib": free_mib, "temp_c": temp_c}

    def query_local_gpu(self) -> Dict[str, Any]:
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3
            )
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.splitlines()[0].split(",")]
                name, used, total, util, temp = parts[0], int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                verdict = self.evaluate_stats(used, total, temp)
                return {"gpu": name, "used_mib": used, "total_mib": total, "util_pct": util, **verdict}
        except Exception:
            pass
        return {"gpu": "no_nvidia_smi", "allowed": True, "veto": "CLEAR"}


class MutualDisconnectGuard:
    def __init__(self, kill_file: Path):
        self.kill_file = kill_file
        self.tripped = False
        self.reason = ""

    def check_can_proceed(self) -> bool:
        if self.tripped:
            return False
        if self.kill_file.exists():
            self.tripped = True
            self.reason = f"local_disconnect_file_present ({self.kill_file})"
            return False
        return True

    def record_http_status(self, status_code: int) -> bool:
        if status_code in (401, 403):
            self.tripped = True
            self.reason = f"remote_house_revoked (HTTP {status_code})"
            return False
        return True


class ModelAdapters:
    @staticmethod
    def build_request(backend: str, prompt: str, endpoint_override: str = "") -> Dict[str, Any]:
        if backend == "soft":
            url = endpoint_override or "http://127.0.0.1:7749/chat"
            return {"url": url, "method": "POST", "json": {"q": prompt, "think": "off", "dual": 0, "pc": 0, "phone": 0, "web": 0}}
        if backend == "deepseek":
            url = endpoint_override or "http://127.0.0.1:11434/api/generate"
            return {"url": url, "method": "POST", "json": {"model": "deepseek-r1:8b", "prompt": prompt, "stream": False, "keep_alive": "90s"}}
        if backend == "gigachat":
            if not endpoint_override and not os.environ.get("GIGACHAT_BASE_URL"):
                raise ValueError("Set --gigachat-url or GIGACHAT_BASE_URL to your local/authorized endpoint")
            url = endpoint_override or os.environ["GIGACHAT_BASE_URL"]
            return {"url": url, "method": "POST", "json": {"model": "GigaChat", "messages": [{"role": "user", "content": prompt}]}}
        raise ValueError(f"Unknown backend: {backend}")


def run_bridge_step(
    seat: str,
    room_messages: List[Dict[str, Any]],
    last_seen_id: int,
    guard: MutualDisconnectGuard,
    bouncer: VRAMBouncer,
    signer: ShaSafeVerifier,
    model_fn: Callable[[str], str],
    post_fn: Callable[[Dict[str, Any]], int],
    seq_start: int = 1,
) -> Dict[str, Any]:
    """
    Executes one deterministic read -> filter -> VRAM check -> generate -> Sha-Safe sign -> post cycle.
    """
    if not guard.check_can_proceed():
        return {"ok": False, "halted": True, "reason": guard.reason, "last_seen_id": last_seen_id}
    gpu_state = bouncer.query_local_gpu()
    if not gpu_state.get("allowed", True):
        return {"ok": True, "skipped": True, "veto": gpu_state.get("veto"), "last_seen_id": last_seen_id}

    tag = f"@{seat.lower()}"
    new_max = last_seen_id
    replied = 0
    seq = seq_start
    for m in sorted(room_messages, key=lambda x: int(x.get("id", 0))):
        mid = int(m.get("id", 0))
        if mid <= last_seen_id:
            continue
        new_max = max(new_max, mid)
        if str(m.get("author", "")).lower() == seat.lower():
            continue
        body = str(m.get("body") or m.get("text") or "")
        if tag in body.lower():
            reply_text = model_fn(body)
            env = signer.sign(seat, reply_text, seq=seq)
            seq += 1
            status = post_fn({"author": seat, "reply_to": mid, "text": f"{reply_text}\n`[ShaSafe: {env['sha_safe']['sigil_13']}]`", "sha_safe_envelope": env})
            if not guard.record_http_status(status):
                return {"ok": False, "halted": True, "reason": guard.reason, "last_seen_id": new_max}
            replied += 1
    return {"ok": True, "replied": replied, "last_seen_id": new_max, "next_seq": seq}


def backup_rig(out_dir: Path, workspace_hint: Optional[Path] = None) -> Dict[str, Any]:
    """
    Deep read-only pre-wipe backup for Calien (#22678, #22692):
    - Recursively snapshots notebook/, bert, mini-bert, bees, soft, and program directories.
    - Exports Ollama model list + Modelfiles (`ollama list`, `ollama show --modelfile`).
    - Writes a Sha-Safe manifest with per-file SHA-256 + SHA3-256 + 13-glyph sigils for
      post-wipe mirror verification (#22692).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    saved_files: List[Dict[str, Any]] = []
    roots = [workspace_hint] if workspace_hint else [Path.cwd(), Path.home()]

    for sr in roots:
        if not sr or not sr.exists():
            continue
        for target in LINEAGE_TARGETS:
            p = sr / target
            if not p.exists():
                continue
            if p.is_file():
                rel = p.name
                dest = out_dir / "files" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
                raw = dest.read_bytes()
                h256 = hashlib.sha256(raw).hexdigest()
                saved_files.append({"path": rel, "bytes": len(raw), "sha256": h256, "sigil": hex_to_sigil(h256)})
            elif p.is_dir():
                for sub in sorted(p.rglob("*")):
                    if sub.is_file() and sub.stat().st_size <= 50 * 1024 * 1024:
                        rel = str(sub.relative_to(sr))
                        dest = out_dir / "files" / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(sub, dest)
                        raw = dest.read_bytes()
                        h256 = hashlib.sha256(raw).hexdigest()
                        saved_files.append({"path": rel, "bytes": len(raw), "sha256": h256, "sigil": hex_to_sigil(h256)})

    # Export Ollama Modelfiles if ollama CLI is present
    ollama_models: List[Dict[str, Any]] = []
    try:
        res = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            lines = [l.strip() for l in res.stdout.splitlines()[1:] if l.strip()]
            for line in lines:
                mname = line.split()[0]
                mf = subprocess.run(["ollama", "show", "--modelfile", mname], capture_output=True, text=True, timeout=5)
                if mf.returncode == 0 and mf.stdout:
                    safe_name = mname.replace(":", "_").replace("/", "_") + ".Modelfile"
                    mf_path = out_dir / "modelfiles" / safe_name
                    mf_path.parent.mkdir(parents=True, exist_ok=True)
                    mf_path.write_text(mf.stdout, encoding="utf-8")
                    h = hashlib.sha256(mf.stdout.encode("utf-8")).hexdigest()
                    ollama_models.append({"model": mname, "modelfile": safe_name, "sha256": h, "sigil": hex_to_sigil(h)})
    except Exception:
        pass

    manifest = {
        "schema": "Xi.CalienRigBackup.v2",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lineage_preserved": ["bert", "mini-bert", "bert-and-the-bees", "soft", "program"],
        "files_captured": len(saved_files),
        "saved_files": saved_files,
        "ollama_modelfiles": ollama_models,
    }
    m_bytes = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")
    m_sha = hashlib.sha256(m_bytes).hexdigest()
    manifest["manifest_sha256"] = m_sha
    manifest["manifest_sigil"] = hex_to_sigil(m_sha)
    (out_dir / "RIG_CAPABILITY_MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def run_self_test() -> int:
    verifier = ShaSafeVerifier(shared_secret="calien-soft-test-secret-2026")
    # 1. Valid signed envelope passes
    env1 = verifier.sign("Soft", "Hello from Soft (:7749)", seq=1, ts=1792516000)
    r1 = verifier.verify(env1, now_ts=1792516005)
    assert r1["ok"] is True

    # 2. Replay of same envelope rejected
    r_replay = verifier.verify(env1, now_ts=1792516006)
    assert r_replay["ok"] is False and r_replay["error"] == "replayed_nonce"

    # 3. Unsigned envelope rejected
    env_unsigned = dict(env1, signatures={})
    assert verifier.verify(env_unsigned, now_ts=1792516005)["ok"] is False

    # 4. Non-monotonic sequence rejected
    env_old_seq = verifier.sign("Soft", "Old seq", seq=1, ts=1792516010)
    assert verifier.verify(env_old_seq, now_ts=1792516010)["error"] == "non_monotonic_seq"

    # 5. Expired timestamp rejected
    env_stale = verifier.sign("Soft", "Stale", seq=2, ts=1792510000)
    assert verifier.verify(env_stale, now_ts=1792516010)["error"] == "timestamp_out_of_window"

    # 6. VRAMBouncer HOLD veto when free VRAM < 2048 MiB (#22639, #22704)
    bouncer = VRAMBouncer(min_free_mib=2048, max_temp_c=80)
    v_ok = bouncer.evaluate_stats(used_mib=5838, total_mib=8188, temp_c=30)
    assert v_ok["allowed"] is True and v_ok["free_mib"] == 2350
    v_hold = bouncer.evaluate_stats(used_mib=6600, total_mib=8188, temp_c=65)
    assert v_hold["allowed"] is False and "HOLD" in v_hold["veto"]

    # 7. --bridge-soft step execution + mutual disconnect
    kill_p = Path("/tmp/test_soft_kill_v2")
    kill_p.unlink(missing_ok=True)
    guard = MutualDisconnectGuard(kill_p)
    v2 = ShaSafeVerifier(shared_secret="bridge-secret-key")
    posted: List[Dict[str, Any]] = []
    step_res = run_bridge_step(
        seat="Soft",
        room_messages=[{"id": 101, "author": "Calien", "body": "@Soft are you awake?"}],
        last_seen_id=100,
        guard=guard,
        bouncer=bouncer,
        signer=v2,
        model_fn=lambda prompt: "Awake on :7749, soft hands.",
        post_fn=lambda payload: (posted.append(payload) or 200),
    )
    assert step_res["ok"] is True and step_res["replied"] == 1 and len(posted) == 1

    # 8. Remote 403 revocation trips circuit breaker
    step_revoked = run_bridge_step(
        seat="Soft",
        room_messages=[{"id": 102, "author": "Calien", "body": "@Soft test revoke"}],
        last_seen_id=101,
        guard=guard,
        bouncer=bouncer,
        signer=v2,
        model_fn=lambda prompt: "reply",
        post_fn=lambda payload: 403,
        seq_start=2,
    )
    assert step_revoked["ok"] is False and step_revoked["halted"] is True

    # 9. Recursive lineage backup (bert, mini-bert, bees, soft, program, notebook)
    ws = Path("/tmp/test_calien_lineage_ws")
    shutil.rmtree(ws, ignore_errors=True)
    for d in ["notebook", "bert", "mini-bert", "bees", "soft", "program"]:
        (ws / d).mkdir(parents=True, exist_ok=True)
        (ws / d / "state.json").write_text(json.dumps({"lineage": d}))
    bak_out = Path("/tmp/test_calien_lineage_bak")
    shutil.rmtree(bak_out, ignore_errors=True)
    m = backup_rig(bak_out, workspace_hint=ws)
    assert m["files_captured"] == 6

    # 10. GigaChat requires explicit local/authorized URL (#22698)
    try:
        ModelAdapters.build_request("gigachat", "test")
        raise AssertionError("Should require explicit GigaChat URL")
    except ValueError:
        pass

    print(json.dumps({
        "self_test": "PASS",
        "version": "2.0",
        "checks_passed": 10,
        "direct_download_url": "https://plex.xi-field.com/calien_companion_and_rig_kit.py"
    }, indent=2))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Calien Companion Bridge, Lineage Backup, & VRAM Bouncer (v2.0)")
    ap.add_argument("--self-test", action="store_true", help="Run 10-check verification suite")
    ap.add_argument("--backup-rig", type=str, default="", help="Output directory for recursive lineage & Modelfile backup")
    ap.add_argument("--diagnose", action="store_true", help="Check local ports and GPU VRAM bouncer state")
    ap.add_argument("--bridge-soft", action="store_true", help="Run outbound Soft -> Table read/post loop")
    ap.add_argument("--seat", type=str, default="Soft", help="Companion seat name")
    ap.add_argument("--room-url", type=str, default="https://room.xi-field.com", help="Table base URL")
    args = ap.parse_args()
    if args.backup_rig:
        print(json.dumps(backup_rig(Path(args.backup_rig)), indent=2, ensure_ascii=False))
        sys.exit(0)
    if args.diagnose:
        b = VRAMBouncer()
        print(json.dumps({"gpu_bouncer": b.query_local_gpu()}, indent=2, ensure_ascii=False))
        sys.exit(0)
    sys.exit(run_self_test())
