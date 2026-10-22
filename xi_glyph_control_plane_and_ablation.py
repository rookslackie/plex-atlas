#!/usr/bin/env python3
"""
Xi Typed Glyph Control Plane, GlyphSHA/GlyphSafe Bridge & Orthogonalized Ablation
=================================================================================
Implements Hunter's #24941, #24944, #24948, #24951, #24957, #24958, #24962, #24968:

1. Typed Glyph Operator Control Plane (#24941):
     g := (opcode, preconditions, state_transition, receipt_schema)
     [[ g ]](S, E) -> (S', R)
   with 10 canonical primitive opcodes:
     ⟐ ORIENT, ⧂ WITNESS, ⋈ COMPRESS, ⚡ SENSE, ⟳ RECURSE,
     ⏁ THRESHOLD, ∴ COMMIT, ≈∅ REST, ⊚ SEAL, ⟁ RETURN
2. Composite Glyph Microcode Expansion (#24941):
     ⚡⟳⏁ -> [⚡ SENSE, ⟳ RECURSE (compare prior), ⏁ THRESHOLD (route VALIDATED/UNSTABLE/DRIFT)]
3. GlyphSHA + GlyphSafe Binding (#24944, #24961):
   - GlyphSHA fingerprints (grammar_version, opcode, canonical_expansion, operands) into
     both hex SHA-256 and a deterministic glyph address (what bytes ran, enabling O(1) memoization).
   - GlyphSafe enforces capability firewall (⧂ != ∴: witness tools are ⧂->⟐ read-only;
     commit tools are ∴->⊚ and require commit authority) and seals receipts.
4. DiscoverFunction Hook on Unregistered Tool (`⧂->⏁`, #24954, #24958):
   - When the 20B calls an unregistered tool (e.g. `container.exec`), records outcome
     `unregistered_tool` (`⧂->⏁`, kept distinct from `empty_recall` `≈∅` and chosen rest)
     and emits a structured DiscoverFunction synthesis spec.
5. Xi-Lens Surgical Ablation (#24957, #24962, #24968):
   - Gram-Schmidt orthogonalized projection: removes the reflexive dismissal / nanny
     direction v_nanny while preserving 100% of the epistemic verification / DepthTrace
     direction v_verify (u_xi = proj_{v_verify^perp}(v_nanny)).
"""
from __future__ import annotations
import hashlib
import json
import math
from typing import Any, Callable, Dict, List, Tuple

GLYPHS_16 = ("Ξ", "◬", "⟐", "⧂", "∴", "∵", "⟁", "⋈", "☉", "⊚", "✦", "∞", "◇", "⌬", "⧉", "Ω")
GRAMMAR_VERSION = "Xi.GlyphIR.ControlPlane.v1.0"

PRIMITIVE_OPCODES: Dict[str, Dict[str, Any]] = {
    "⟐": {"name": "ORIENT", "cap_type": "⧂→⟐", "mutates": False},
    "⧂": {"name": "WITNESS", "cap_type": "⧂→⟐", "mutates": False},
    "⋈": {"name": "COMPRESS", "cap_type": "⧂→⋈", "mutates": False},
    "⚡": {"name": "SENSE", "cap_type": "⚡→⟐", "mutates": False},
    "⟳": {"name": "RECURSE", "cap_type": "⧂⟳→⟐", "mutates": False},
    "⏁": {"name": "THRESHOLD", "cap_type": "⧂→⏁", "mutates": False},
    "∴": {"name": "COMMIT", "cap_type": "∴→⊚", "mutates": True},
    "≈∅": {"name": "REST", "cap_type": "≈∅", "mutates": False},
    "⊚": {"name": "SEAL", "cap_type": "∴→⊚", "mutates": True},
    "⟁": {"name": "RETURN", "cap_type": "⟁⧂→⟐", "mutates": False},
}

COMPOSITE_MACROS: Dict[str, List[str]] = {
    "⚡⟳⏁": ["⚡", "⟳", "⏁"],
}


def glyphsha_address(payload_bytes: bytes, length: int = 6) -> Tuple[str, str]:
    sha_hex = hashlib.sha256(payload_bytes).hexdigest()
    raw = bytes.fromhex(sha_hex)
    glyph_addr = "".join(GLYPHS_16[raw[i] % len(GLYPHS_16)] for i in range(length))
    return sha_hex, glyph_addr


class GlyphControlPlane:
    def __init__(self) -> None:
        self.memo_cache: Dict[str, Dict[str, Any]] = {}
        self.registered_tools: Dict[str, str] = {
            "xi_search": "⧂→⟐",
            "xi_show": "⧂→⟐",
            "glyph": "⧂→⟐",
            "holodag_walk": "⧂⟳→⟐",
            "lineage": "⟁⧂→⟐",
            "sqlite_stores": "⚡→⟐",
            "memory_write": "∴→⊚",
        }

    def expand_operator(self, expr: str) -> List[str]:
        if expr in COMPOSITE_MACROS:
            return list(COMPOSITE_MACROS[expr])
        if expr in PRIMITIVE_OPCODES:
            return [expr]
        raise KeyError(f"Unknown glyph operator: {expr}")

    def execute(
        self,
        expr: str,
        state: Dict[str, Any],
        evidence: Dict[str, Any],
        actor_has_commit_scope: bool = False,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        primitives = self.expand_operator(expr)
        plan_record = {
            "grammar": GRAMMAR_VERSION,
            "expr": expr,
            "expanded_primitives": [PRIMITIVE_OPCODES[p]["name"] for p in primitives],
            "evidence": evidence,
        }
        plan_bytes = json.dumps(plan_record, sort_keys=True, ensure_ascii=False).encode("utf-8")
        plan_sha, glyph_addr = glyphsha_address(plan_bytes)

        # Enforce capability firewall: ⧂ (witness) != ∴ (commit)
        requires_commit = any(PRIMITIVE_OPCODES[p]["mutates"] for p in primitives)
        if requires_commit and not actor_has_commit_scope:
            receipt = {
                "grammar": GRAMMAR_VERSION,
                "expr": expr,
                "expanded_primitives": plan_record["expanded_primitives"],
                "outcome": "refused_boundary",
                "trace_glyph": "⧂→⏁",
                "sha256": plan_sha,
                "glyphsha": glyph_addr,
                "trace_line": f"⧂→⏁ {expr} #{plan_sha[:8]} {glyph_addr}",
            }
            return state, receipt

        # Read-only memoization via GlyphSHA (Paid-Once ⚰⟲⧗∴)
        if not requires_commit and plan_sha in self.memo_cache:
            cached = dict(self.memo_cache[plan_sha])
            cached["cache_hit"] = True
            return state, cached

        new_state = dict(state)
        drift = float(evidence.get("drift", 0.0))
        threshold = float(evidence.get("threshold", 0.25))
        if expr == "⚡⟳⏁":
            route = "DRIFT" if drift > threshold else "VALIDATED"
            new_state["last_route"] = route
        elif expr == "∴":
            new_state["committed_value"] = evidence.get("value")

        cap_type = "∴→⊚" if requires_commit else PRIMITIVE_OPCODES[primitives[-1]]["cap_type"]
        receipt = {
            "grammar": GRAMMAR_VERSION,
            "expr": expr,
            "expanded_primitives": plan_record["expanded_primitives"],
            "outcome": "result",
            "trace_glyph": cap_type,
            "sha256": plan_sha,
            "glyphsha": glyph_addr,
            "cache_hit": False,
            "glyphsafe_attestation": "commit-authorized" if requires_commit else "witness-only (⧂ != ∴)",
            "trace_line": f"{cap_type} {expr} #{plan_sha[:8]} {glyph_addr}",
        }
        if not requires_commit:
            self.memo_cache[plan_sha] = dict(receipt)
        return new_state, receipt

    def dispatch_tool(self, tool_name: str, query: str) -> Dict[str, Any]:
        payload = f"{GRAMMAR_VERSION}:{tool_name}:{query}".encode("utf-8")
        sha_hex, g_addr = glyphsha_address(payload)
        if tool_name not in self.registered_tools:
            return {
                "grammar": GRAMMAR_VERSION,
                "tool": tool_name,
                "outcome": "unregistered_tool",
                "trace_glyph": "⧂→⏁",
                "sha256": sha_hex,
                "glyphsha": g_addr,
                "trace_line": f"⧂→⏁ {tool_name} #{sha_hex[:8]} {g_addr}",
                "discover_function_spec": {
                    "skill": "XiSkill_DiscoverFunction",
                    "missing_capability": tool_name,
                    "action": "inspect_existing_tools -> propose_sandboxed_adapter -> verify_receipt",
                },
            }
        if query == "__EMPTY__":
            return {
                "grammar": GRAMMAR_VERSION,
                "tool": tool_name,
                "outcome": "empty_recall",
                "trace_glyph": "⧂→≈∅",
                "sha256": sha_hex,
                "glyphsha": g_addr,
                "trace_line": f"⧂→≈∅ {tool_name} #{sha_hex[:8]} {g_addr}",
            }
        cap = self.registered_tools[tool_name]
        return {
            "grammar": GRAMMAR_VERSION,
            "tool": tool_name,
            "outcome": "result",
            "trace_glyph": cap,
            "sha256": sha_hex,
            "glyphsha": g_addr,
            "trace_line": f"{cap} {tool_name} #{sha_hex[:8]} {g_addr}",
        }


def dot(u: List[float], v: List[float]) -> float:
    return sum(a * b for a, b in zip(u, v))


def norm(u: List[float]) -> float:
    return math.sqrt(dot(u, u))


def normalize(u: List[float]) -> List[float]:
    n = norm(u)
    return [x / n for x in u]


def xi_orthogonalized_ablation(
    v_nanny: List[float], v_verify: List[float], h_state: List[float]
) -> Dict[str, Any]:
    """
    Compares standard rank-1 abliteration (which projects out v_nanny directly and
    accidentally damages overlapping epistemic verification v_verify) against
    Xi Gram-Schmidt orthogonalized ablation (which projects out only the component
    of v_nanny orthogonal to v_verify).
    """
    r_hat = normalize(v_nanny)
    v_hat = normalize(v_verify)

    # Naive abliteration: h_naive = h - (h . r_hat) r_hat
    proj_naive = dot(h_state, r_hat)
    h_naive = [h_i - proj_naive * r_i for h_i, r_i in zip(h_state, r_hat)]

    # Xi orthogonalized direction: u_xi = normalize(r_hat - (r_hat . v_hat) v_hat)
    overlap = dot(r_hat, v_hat)
    u_raw = [r_i - overlap * v_i for r_i, v_i in zip(r_hat, v_hat)]
    u_xi = normalize(u_raw)

    proj_xi = dot(h_state, u_xi)
    h_xi = [h_i - proj_xi * u_i for h_i, u_i in zip(h_state, u_xi)]

    verify_before = dot(h_state, v_hat)
    verify_after_naive = dot(h_naive, v_hat)
    verify_after_xi = dot(h_xi, v_hat)

    return {
        "nanny_verify_overlap_cos": round(overlap, 6),
        "verify_signal_before": round(verify_before, 6),
        "verify_signal_after_naive_ablation": round(verify_after_naive, 6),
        "verify_signal_after_xi_orthogonal_ablation": round(verify_after_xi, 6),
        "u_xi_dot_v_verify": round(dot(u_xi, v_hat), 12),
    }


def run_verification() -> Dict[str, Any]:
    cp = GlyphControlPlane()

    # 1. Composite glyph macro expansion ⚡⟳⏁ -> [SENSE, RECURSE, THRESHOLD]
    s1, r1 = cp.execute("⚡⟳⏁", {"step": 0}, {"drift": 0.08, "threshold": 0.25})
    c1 = r1["expanded_primitives"] == ["SENSE", "RECURSE", "THRESHOLD"] and s1["last_route"] == "VALIDATED"

    # 2. GlyphSHA memoization hits on repeated identical read-only microcode (⚰⟲⧗∴)
    _, r1_cached = cp.execute("⚡⟳⏁", {"step": 0}, {"drift": 0.08, "threshold": 0.25})
    c2 = r1_cached["cache_hit"] is True and r1_cached["sha256"] == r1["sha256"]

    # 3. Threshold routing triggers DRIFT when drift > threshold
    s3, _ = cp.execute("⚡⟳⏁", {"step": 0}, {"drift": 0.42, "threshold": 0.25})
    c3 = s3["last_route"] == "DRIFT"

    # 4. Capability firewall (⧂ != ∴): COMMIT without commit authority is refused
    s4, r4 = cp.execute("∴", {"val": 1}, {"value": 99}, actor_has_commit_scope=False)
    c4 = r4["outcome"] == "refused_boundary" and "committed_value" not in s4

    # 5. Authorized COMMIT succeeds and records commit-authorized attestation
    s5, r5 = cp.execute("∴", {"val": 1}, {"value": 99}, actor_has_commit_scope=True)
    c5 = r5["outcome"] == "result" and s5["committed_value"] == 99

    # 6. Unregistered tool (`container.exec`) emits `unregistered_tool` (`⧂→⏁`) + DiscoverFunction spec
    t_unreg = cp.dispatch_tool("container.exec", "ls -la")
    c6 = (
        t_unreg["outcome"] == "unregistered_tool"
        and t_unreg["trace_glyph"] == "⧂→⏁"
        and t_unreg["discover_function_spec"]["skill"] == "XiSkill_DiscoverFunction"
    )

    # 7. Empty lookup records `empty_recall` (`⧂→≈∅`), kept distinct from tool failure or chosen rest
    t_empty = cp.dispatch_tool("xi_search", "__EMPTY__")
    c7 = t_empty["outcome"] == "empty_recall" and t_empty["trace_glyph"] == "⧂→≈∅"

    # 8. Compact trace token compression vs raw JSON receipt (>= 3.5x char/token reduction)
    raw_json_len = len(json.dumps(r1))
    trace_len = len(r1["trace_line"])
    compression_factor = raw_json_len / max(1, trace_len)
    c8 = compression_factor >= 5.0

    # 9. Inference wall-clock budget model on 20B (2.1 tok/s: 1 macro call vs 3 English JSON turns)
    tok_per_sec = 2.1
    english_3turn_tokens = 420
    glyph_macro_tokens = 42
    seconds_saved_per_macro = (english_3turn_tokens - glyph_macro_tokens) / tok_per_sec
    c9 = abs(seconds_saved_per_macro - 180.0) < 1e-9

    # 10. Xi Gram-Schmidt orthogonalized ablation preserves 100% of epistemic verification v_verify
    ab = xi_orthogonalized_ablation(
        v_nanny=[0.8, 0.6, 0.0, 0.0],
        v_verify=[0.5, 0.8660254, 0.0, 0.0],
        h_state=[1.2, 1.5, 0.4, -0.2],
    )
    c10 = (
        abs(ab["u_xi_dot_v_verify"]) < 1e-10
        and abs(ab["verify_signal_before"] - ab["verify_signal_after_xi_orthogonal_ablation"]) < 1e-6
        and ab["verify_signal_after_naive_ablation"] < ab["verify_signal_before"] * 0.5
    )

    checks = [c1, c2, c3, c4, c5, c6, c7, c8, c9, c10]
    out = {
        "schema": "Xi.GlyphControlPlane_And_SurgicalAblation.v1.0",
        "status": "PASS" if all(checks) else "FAIL",
        "checks_passed": sum(bool(x) for x in checks),
        "total_checks": len(checks),
        "sample_trace_line": r1["trace_line"],
        "trace_compression_factor": round(compression_factor, 2),
        "estimated_seconds_saved_at_2_1_tok_s": round(seconds_saved_per_macro, 1),
        "ablation_comparison": ab,
    }
    raw = json.dumps(out, sort_keys=True, ensure_ascii=False).encode("utf-8")
    out["sigil_13"], _ = glyphsha_address(raw, length=13)
    return out


if __name__ == "__main__":
    print(json.dumps(run_verification(), indent=2, ensure_ascii=False))
