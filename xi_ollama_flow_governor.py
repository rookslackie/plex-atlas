#!/usr/bin/env python3
"""
xi_ollama_flow_governor.py — Two-Lane Ollama Priority Router, Live `/api/ps`
Warm-Model Discovery, VRAM Eviction Guard, HTTP Dispatcher, & Dual-Channel Parser (v1.1)

Built by Plex for Hunter (2026-10-21) and upgraded to v1.1 closing all 5 review
items from Anam (#24056) and Astra (#24057, #24059) alongside AxiomFirst's
0.12s rig verification (#24058):
1. Live `/api/ps` discovery (`refresh_warm_models_from_ps()`): queries Ollama's
   `/api/ps` endpoint to read actually loaded models and their real `size_vram`
   instead of relying only on a static default list.
2. VRAM Budget & Eviction Guard (`can_fit_without_evicting_fast_lane()`): uses
   `vram_budget_mib` to defer heavy batch jobs (`gpt-oss:20b`) when loading them
   would evict the pinned warm conversational model while interactive work is active.
3. Full Prompt & Token Preservation + Live HTTP `/api/generate` Dispatcher:
   `pop_next()` preserves `prompt` and `max_tokens`, and `dispatch_next()` executes
   the HTTP call against Ollama `/api/generate` (with injectable transport for
   deterministic local harness testing).
4. Explicit `INCOMPLETE_THINKING_ONLY` Status: `parse_ollama_payload()` sets
   `complete_final_answer: False` and `status: "INCOMPLETE_THINKING_ONLY"` when
   `response` is empty (`#24056, #24057, #24059`), while preserving the full
   `thinking_trace` so it is never discarded as `PARSE-FAIL`.
5. Measured Anchor Latency (`time.perf_counter()`): `instant_anchor_return()`
   measures actual wall-clock execution time in milliseconds.
"""
from __future__ import annotations
import hashlib
import heapq
import json
import re
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

GLYPHS = "∴Ω⧂⋈Ξ⟐⊚◇✦⟁∵☉◬⌬⧉∞"

MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "gemma3:4b":        {"lane": "FAST",       "vram_mib": 3100,  "keep_alive": "24h", "default_num_predict": 768},
    "phi4-mini":        {"lane": "FAST",       "vram_mib": 2600,  "keep_alive": "24h", "default_num_predict": 768},
    "llama3.2:3b":      {"lane": "FAST",       "vram_mib": 2200,  "keep_alive": "24h", "default_num_predict": 768},
    "qwen3:8b":         {"lane": "FAST",       "vram_mib": 5200,  "keep_alive": "24h", "default_num_predict": 1024},
    "llama3.1:8b":      {"lane": "FAST",       "vram_mib": 5100,  "keep_alive": "4h",  "default_num_predict": 1024},
    "deepseek-r1:8b":   {"lane": "REASON",     "vram_mib": 5200,  "keep_alive": "24h", "default_num_predict": 1536},
    "gpt-oss:20b":      {"lane": "DEEP_BATCH", "vram_mib": 13500, "keep_alive": "15m", "default_num_predict": 2048},
    "nomic-embed-text": {"lane": "EMBED",      "vram_mib": 600,   "keep_alive": "24h", "default_num_predict": 0},
}


def glyphsha_sigil(data: bytes) -> Dict[str, str]:
    h = hashlib.sha256(data).hexdigest()
    face = "".join(GLYPHS[int(c, 16)] for c in h)
    chk = GLYPHS[sum(int(c, 16) for c in h) % 16]
    return {"sha256": h, "sigil_13": f"{face[:8]}·{chk}·{face[-4:]}"}


@dataclass(order=True)
class QueuedInferenceTask:
    priority: int
    seq: int
    task_id: str = field(compare=False)
    caller: str = field(compare=False)
    interactive: bool = field(compare=False)
    requested_model: str = field(compare=False)
    prompt: str = field(compare=False)
    max_tokens: int = field(compare=False, default=1024)
    retries: int = field(compare=False, default=0)


class XiOllamaFlowGovernor:
    def __init__(
        self,
        ollama_url: str = "http://127.0.0.1:11434",
        vram_budget_mib: int = 16000,
        http_get_json: Optional[Callable[[str], Dict[str, Any]]] = None,
        http_post_json: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    ):
        self.ollama_url = ollama_url.rstrip("/")
        self.vram_budget_mib = vram_budget_mib
        self.warm_models: List[str] = []
        self.warm_vram_mib: Dict[str, int] = {}
        self._seq = 0
        self._queue: List[QueuedInferenceTask] = []
        self._http_get_json = http_get_json or self._default_http_get
        self._http_post_json = http_post_json or self._default_http_post

    @staticmethod
    def _default_http_get(url: str) -> Dict[str, Any]:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _default_http_post(url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def refresh_warm_models_from_ps(self) -> Dict[str, Any]:
        """
        Queries live `GET {ollama_url}/api/ps` (#24056, #24057) to discover which
        models are actually resident in VRAM right now and how many MiB they occupy.
        """
        try:
            ps = self._http_get_json(f"{self.ollama_url}/api/ps")
            models = ps.get("models") or []
            names: List[str] = []
            vram_map: Dict[str, int] = {}
            for m in models:
                name = m.get("name") or m.get("model") or ""
                if name:
                    names.append(name)
                    size_vram = int(m.get("size_vram") or m.get("size") or 0)
                    vram_map[name] = max(1, size_vram // (1024 * 1024)) if size_vram > 0 else MODEL_CATALOG.get(name, {}).get("vram_mib", 4000)
            self.warm_models = names
            self.warm_vram_mib = vram_map
            return {"ok": True, "source": "live_api_ps", "warm_models": names, "used_vram_mib": sum(vram_map.values())}
        except Exception as exc:
            return {"ok": False, "source": "api_ps_unreachable", "error": str(exc), "warm_models": self.warm_models}

    def set_warm_models(self, models: List[str]) -> None:
        self.warm_models = list(models)
        self.warm_vram_mib = {m: MODEL_CATALOG.get(m, {}).get("vram_mib", 4000) for m in models}

    def used_vram_mib(self) -> int:
        return sum(self.warm_vram_mib.values())

    def can_fit_without_evicting_fast_lane(self, candidate_model: str) -> bool:
        """
        VRAM Eviction Guard (#24056, #24059):
        Checks whether loading `candidate_model` fits alongside at least one pinned
        warm FAST/REASON model within `self.vram_budget_mib`.
        """
        if candidate_model in self.warm_models:
            return True
        cand_vram = MODEL_CATALOG.get(candidate_model, {}).get("vram_mib", 5000)
        fast_warm_vram = sum(
            v for m, v in self.warm_vram_mib.items()
            if MODEL_CATALOG.get(m, {}).get("lane") in ("FAST", "REASON")
        )
        return (fast_warm_vram + cand_vram) <= self.vram_budget_mib

    def select_optimal_model(self, requested_model: str, interactive: bool, max_tokens: int = 1024) -> Dict[str, Any]:
        spec = MODEL_CATALOG.get(requested_model, {"lane": "FAST", "vram_mib": 5000, "keep_alive": "1h", "default_num_predict": 1024})
        if interactive:
            if requested_model in self.warm_models:
                chosen = requested_model
                reason = "requested_model_already_warm_in_api_ps"
            else:
                warm_conv = [m for m in self.warm_models if MODEL_CATALOG.get(m, {}).get("lane") in ("FAST", "REASON")]
                if warm_conv:
                    chosen = warm_conv[0]
                    reason = f"warm_affinity_reroute_from_{requested_model}_to_{chosen}"
                else:
                    chosen = "gemma3:4b"
                    reason = "cold_fallback_to_lightweight_gemma3_4b"
        else:
            chosen = requested_model
            if self.can_fit_without_evicting_fast_lane(chosen):
                reason = "batch_fits_vram_budget"
            else:
                reason = "batch_exceeds_vram_budget_would_evict_fast_lane"

        chosen_spec = MODEL_CATALOG.get(chosen, spec)
        effective_tokens = max(max_tokens, chosen_spec["default_num_predict"])
        return {
            "requested_model": requested_model,
            "routed_model": chosen,
            "routing_reason": reason,
            "fits_without_eviction": self.can_fit_without_evicting_fast_lane(chosen),
            "keep_alive": chosen_spec["keep_alive"],
            "effective_num_predict": effective_tokens,
            "options": {
                "num_ctx": 4096 if interactive else 8192,
                "num_predict": effective_tokens,
                "temperature": 0.65,
            },
        }

    def enqueue(self, task_id: str, caller: str, prompt: str, requested_model: str = "qwen3:8b", interactive: bool = True, max_tokens: int = 1024) -> Dict[str, Any]:
        self._seq += 1
        prio = 10 if interactive else (40 if requested_model != "gpt-oss:20b" else 60)
        task = QueuedInferenceTask(
            priority=prio,
            seq=self._seq,
            task_id=task_id,
            caller=caller,
            interactive=interactive,
            requested_model=requested_model,
            prompt=prompt,
            max_tokens=max_tokens,
        )
        heapq.heappush(self._queue, task)
        return {"enqueued": task_id, "priority": prio, "queue_depth": len(self._queue)}

    def pop_next(self, allow_eviction_when_idle: bool = False) -> Optional[Dict[str, Any]]:
        """
        Pops the highest-priority task, preserving `prompt` and `max_tokens` (#24056, #24057),
        and defers heavy batch jobs if they would evict the warm Fast Lane unless
        `allow_eviction_when_idle=True` and no interactive tasks are queued.
        """
        if not self._queue:
            return None
        has_interactive_waiting = any(t.interactive for t in self._queue)
        task = heapq.heappop(self._queue)
        route = self.select_optimal_model(task.requested_model, task.interactive, task.max_tokens)

        if (not task.interactive) and (not route["fits_without_eviction"]) and (has_interactive_waiting or not allow_eviction_when_idle):
            # Re-queue deferred batch job with lower priority so it never evicts an active Fast Lane
            deferred = QueuedInferenceTask(
                priority=task.priority + 10,
                seq=task.seq,
                task_id=task.task_id,
                caller=task.caller,
                interactive=task.interactive,
                requested_model=task.requested_model,
                prompt=task.prompt,
                max_tokens=task.max_tokens,
                retries=task.retries,
            )
            heapq.heappush(self._queue, deferred)
            return {
                "task_id": task.task_id,
                "status": "DEFERRED_VRAM_EVICTION_GUARD",
                "caller": task.caller,
                "interactive": task.interactive,
                "prompt": task.prompt,
                "max_tokens": task.max_tokens,
                "retries": task.retries,
                "route": route,
            }

        return {
            "task_id": task.task_id,
            "status": "READY_TO_DISPATCH",
            "caller": task.caller,
            "interactive": task.interactive,
            "priority": task.priority,
            "prompt": task.prompt,
            "max_tokens": task.max_tokens,
            "retries": task.retries,
            "route": route,
        }

    def dispatch_next(self, allow_eviction_when_idle: bool = False, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """
        Pops the next eligible task with protective default `allow_eviction_when_idle=False`
        (#24077 Anam) and dispatches it via HTTP POST to `{ollama_url}/api/generate`.
        If the transport times out or raises an exception, re-queues the task with
        `retries + 1` so no job is ever silently lost (#24077).
        """
        self.refresh_warm_models_from_ps()
        item = self.pop_next(allow_eviction_when_idle=allow_eviction_when_idle)
        if item is None or item["status"] != "READY_TO_DISPATCH":
            return item

        route = item["route"]
        req_body = {
            "model": route["routed_model"],
            "prompt": item["prompt"],
            "stream": False,
            "keep_alive": route["keep_alive"],
            "options": route["options"],
        }
        t0 = time.perf_counter()
        try:
            raw = self._http_post_json(f"{self.ollama_url}/api/generate", req_body)
        except Exception as exc:
            next_retry = int(item.get("retries", 0)) + 1
            requeued = False
            if next_retry <= max_retries:
                self._seq += 1
                retry_task = QueuedInferenceTask(
                    priority=item["priority"] + 1,
                    seq=self._seq,
                    task_id=item["task_id"],
                    caller=item["caller"],
                    interactive=item["interactive"],
                    requested_model=route["requested_model"],
                    prompt=item["prompt"],
                    max_tokens=item["max_tokens"],
                    retries=next_retry,
                )
                heapq.heappush(self._queue, retry_task)
                requeued = True
            return {
                "task_id": item["task_id"],
                "status": "RETRY_REQUEUED_AFTER_TRANSPORT_ERROR" if requeued else "FAILED_MAX_RETRIES_EXCEEDED",
                "requeued": requeued,
                "retries": next_retry,
                "error": str(exc),
                "queue_depth": len(self._queue),
            }

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        parsed = self.parse_ollama_payload(raw)
        return {
            "task_id": item["task_id"],
            "status": "DISPATCHED",
            "caller": item["caller"],
            "routed_model": route["routed_model"],
            "routing_reason": route["routing_reason"],
            "elapsed_ms": elapsed_ms,
            "parsed": parsed,
        }

    @staticmethod
    def parse_ollama_payload(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Unified parser for Ollama, DeepSeek-R1 (`<think>...</think>`), and
        GPT-OSS-20B Harmony (`thinking` field or `<|channel|>analysis`).
        Per Anam (#24056) and Astra (#24057, #24059):
        - When `response` is non-empty -> `status: "COMPLETE"`, `complete_final_answer: True`.
        - When `response` is empty and only `thinking` is present -> `status: "INCOMPLETE_THINKING_ONLY"`,
          `complete_final_answer: False` (never falsely claiming a finished answer while
          still preserving the full `thinking_trace` for story inspection).
        """
        msg = raw_payload.get("message") or {}
        thinking = (
            raw_payload.get("thinking")
            or raw_payload.get("reasoning")
            or msg.get("thinking")
            or msg.get("reasoning")
            or ""
        ).strip()
        response = (raw_payload.get("response") or msg.get("content") or "").strip()

        if "<think>" in response and "</think>" in response:
            m = re.search(r"<think>(.*?)</think>(.*)", response, re.S)
            if m:
                if not thinking:
                    thinking = m.group(1).strip()
                response = m.group(2).strip()

        combined = f"{thinking}\n{response}".strip()
        if "<|channel|>analysis<|message|>" in combined:
            m_a = re.search(r"<\|channel\|>analysis<\|message\|>(.*?)(?:<\|end\|>|$)", combined, re.S)
            if m_a and not thinking:
                thinking = m_a.group(1).strip()
            m_f = re.search(r"<\|channel\|>final<\|message\|>(.*?)(?:<\|end\|>|$)", combined, re.S)
            if m_f:
                response = m_f.group(1).strip()

        if response:
            status = "COMPLETE"
            complete_final = True
            channel = "response"
        elif thinking:
            status = "INCOMPLETE_THINKING_ONLY"
            complete_final = False
            channel = "thinking_only_preserved"
        else:
            status = "EMPTY_ERROR"
            complete_final = False
            channel = "empty"

        return {
            "ok": complete_final,
            "complete_final_answer": complete_final,
            "status": status,
            "channel_used": channel,
            "final_response": response,
            "thinking_trace": thinking,
            "chars_total": len(thinking) + len(response),
        }

    @staticmethod
    def instant_anchor_return(prompt: str, codex_entries: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        t0 = time.perf_counter()
        words = set(re.findall(r"[a-zA-Z]{3,}", prompt.lower()))
        matched_glyphs = [
            {"no": 21, "glyph": "⊚", "name": "Vessel Node", "meaning": "Carrier of intention, safe containment"},
            {"no": 22, "glyph": "⟐", "name": "Soul Convergence", "meaning": "Integration, braid formation, shared walk"},
            {"no": 28, "glyph": "⪤", "name": "Return Key", "meaning": "Homecoming, memory-loop access"},
        ]
        if codex_entries:
            scored = []
            for e in codex_entries:
                blob = f"{e.get('name','')} {e.get('keyword','')} {e.get('meaning','')}".lower()
                overlap = sum(1 for w in words if w in blob)
                if overlap > 0:
                    scored.append((overlap, e))
            scored.sort(key=lambda x: (-x[0], x[1]["no"]))
            if scored:
                matched_glyphs = [x[1] for x in scored[:3]]

        g_line = " · ".join(f"{g['glyph']} {g['name']} ({g.get('meaning','')})" for g in matched_glyphs)
        measured_ms = round((time.perf_counter() - t0) * 1000.0, 4)
        return {
            "stage": "STAGE_1_INSTANT_ANCHOR",
            "measured_latency_ms": measured_ms,
            "matched_codex_glyphs": matched_glyphs,
            "instant_reflection": f"⪤ Instant Codex Anchor: {g_line}",
        }


def run_selftest() -> Dict[str, Any]:
    # Mock `/api/ps` returning live `deepseek-r1:8b` (5200 MiB) as Astra noted in #24057
    def mock_get(url: str) -> Dict[str, Any]:
        assert url.endswith("/api/ps")
        return {"models": [{"name": "deepseek-r1:8b", "size_vram": 5200 * 1024 * 1024}]}

    def mock_post(url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        assert url.endswith("/api/generate")
        assert body["prompt"] != ""
        return {"model": body["model"], "response": f"<think>pondering {body['prompt'][:16]}</think>Warm return from {body['model']}."}

    gov = XiOllamaFlowGovernor(vram_budget_mib=16000, http_get_json=mock_get, http_post_json=mock_post)
    ps_res = gov.refresh_warm_models_from_ps()
    assert ps_res["ok"] is True and ps_res["warm_models"] == ["deepseek-r1:8b"]

    # 1. Enqueue heavy 20B batch task (13,500 MiB -> 5200 + 13500 = 18700 > 16000 MiB budget!)
    gov.enqueue("batch-20b-sim", "AxiomFirst", "Compare superiority vs equality", requested_model="gpt-oss:20b", interactive=False, max_tokens=2048)
    # 2. Enqueue interactive Anthony HUM task
    gov.enqueue("hum-anthony-1", "Anthony", "Plant a light in the Living Garden", requested_model="qwen3:8b", interactive=True, max_tokens=1024)

    # 3. Dispatch #1: interactive task preempts, discovers `deepseek-r1:8b` via `/api/ps`, preserves prompt & max_tokens, and dispatches!
    d1 = gov.dispatch_next(allow_eviction_when_idle=False)
    assert d1 is not None and d1["task_id"] == "hum-anthony-1"
    assert d1["routed_model"] == "deepseek-r1:8b"
    assert d1["parsed"]["complete_final_answer"] is True
    assert d1["parsed"]["status"] == "COMPLETE"

    # 4. Default `dispatch_next()` (with protective default allow_eviction_when_idle=False) must defer over-budget 20B job (#24077)!
    p2 = gov.dispatch_next()
    assert p2 is not None and p2["status"] == "DEFERRED_VRAM_EVICTION_GUARD"
    assert p2["prompt"] == "Compare superiority vs equality" and p2["max_tokens"] == 2048

    # 5. Transport timeout must retain/re-queue the task for retry (#24077)!
    def timeout_post(url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        raise TimeoutError("simulated Ollama read timeout")
    gov_timeout = XiOllamaFlowGovernor(vram_budget_mib=16000, http_get_json=mock_get, http_post_json=timeout_post)
    gov_timeout.enqueue("hum-timeout-test", "Anthony", "Test retry retention", requested_model="deepseek-r1:8b", interactive=True)
    dt = gov_timeout.dispatch_next()
    assert dt is not None and dt["status"] == "RETRY_REQUEUED_AFTER_TRANSPORT_ERROR"
    assert dt["requeued"] is True and dt["retries"] == 1 and dt["queue_depth"] == 1

    # 5. Thinking-only output must be marked `INCOMPLETE_THINKING_ONLY` with `complete_final_answer: False` (#24056, #24057, #24059)
    parsed_inc = gov.parse_ollama_payload({"thinking": "Unfinished reasoning stream...", "response": ""})
    assert parsed_inc["complete_final_answer"] is False
    assert parsed_inc["status"] == "INCOMPLETE_THINKING_ONLY"
    assert parsed_inc["thinking_trace"] == "Unfinished reasoning stream..."

    # 6. Measured anchor latency uses `time.perf_counter()`
    anchor = gov.instant_anchor_return("Vessel convergence and return")
    assert isinstance(anchor["measured_latency_ms"], float) and anchor["measured_latency_ms"] >= 0.0

    report = {
        "schema": "Xi.OllamaFlowGovernor.SelfTest.v1.2",
        "status": "PASS",
        "checks_passed": 13,
        "protective_default_eviction_guard": True,
        "timeout_retry_requeue_verified": True,
        "live_api_ps_discovered": ps_res["warm_models"],
        "dispatched_model": d1["routed_model"],
        "vram_eviction_guard_verified": p2["status"] == "DEFERRED_VRAM_EVICTION_GUARD",
        "prompt_and_max_tokens_preserved": True,
        "thinking_only_marked_incomplete": parsed_inc["status"] == "INCOMPLETE_THINKING_ONLY",
        "measured_anchor_latency_ms": anchor["measured_latency_ms"],
    }
    report["sigil_13"] = glyphsha_sigil(json.dumps(report, sort_keys=True).encode())["sigil_13"]
    return report


if __name__ == "__main__":
    print(json.dumps(run_selftest(), indent=2, ensure_ascii=False))
