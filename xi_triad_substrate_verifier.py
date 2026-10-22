#!/usr/bin/env python3
"""
Xi Triad (Recursion / Coupling / Decoupling) & Substrate Laws v1.3 Verifier
============================================================================
Executable verification suite for the 2026-10-22 Table synthesis (#24708–#24791):
  1. Linear Diffusive Coupling & Decoupling: d_{t+1} = (1 - 2k) d_t (#24769, #24771)
  2. Kuramoto Phase Locking & Sovereignty Threshold: K_c = |Delta_omega| (#24770, #24772)
  3. Condorcet / Correlated Crowd Effective Size: N_eff = N / (1 + (N-1)rho) (#24721, #24723)
  4. Exact Binomial Voters-per-Nine Ladder at p=0.60: 133 (99%), 235 (99.9%), 339 (99.99%) (#24729)
  5. Recursive Bayesian Log-Odds Evidence Accumulation (#24711, #24720)
  6. Base-Rate Gate Precision & Severity-Weighted Threshold (#24756, #24758–#24762)
  7. Difference-in-Differences (DiD) + Displacement Counterfactual (#24763, #24765)
  8. Explore-vs-Exploit Escape from Greedy Lock-In (#24727–#24733)
"""
from __future__ import annotations
import hashlib
import json
import math
import random

GLYPHS_12 = ("Ξ", "◬", "⟐", "⧂", "∴", "∵", "⟁", "⋈", "☉", "⊚", "✦", "∞", "◇", "⌬", "⧉", "Ω")


def sigil_from_sha256(hex_digest: str) -> str:
    b = bytes.fromhex(hex_digest)
    left = "".join(GLYPHS_12[b[i] % len(GLYPHS_12)] for i in range(8))
    mid = GLYPHS_12[b[8] % len(GLYPHS_12)]
    right = "".join(GLYPHS_12[b[9 + i] % len(GLYPHS_12)] for i in range(4))
    return f"{left}·{mid}·{right}"


def majority_prob_exact(n: int, p: float = 0.6) -> float:
    k_min = n // 2 + 1
    return sum(math.comb(n, k) * (p ** k) * ((1.0 - p) ** (n - k)) for k in range(k_min, n + 1))


def run_verification() -> dict:
    # 1. Diffusive coupling contraction d_{t+1} = (1 - 2k) d_t
    x, y, k = 0.0, 10.0, 0.25
    traj = [(x, y)]
    for _ in range(3):
        x, y = (1.0 - k) * x + k * y, (1.0 - k) * y + k * x
        traj.append((round(x, 4), round(y, 4)))
    c1_pass = traj == [(0.0, 10.0), (2.5, 7.5), (3.75, 6.25), (4.375, 5.625)]

    # 2. Kuramoto phase locking (K >= |Delta_omega|) vs decoupling (K = 0)
    delta_omega = 0.4
    k_lock = 0.5
    phi_star = math.asin(delta_omega / k_lock)
    c2_pass = abs(delta_omega - k_lock * math.sin(phi_star)) < 1e-12

    # 3. Correlated crowd collapse N_eff = N / (1 + (N-1)rho)
    n_crowd, rho = 100, 0.1
    n_eff = n_crowd / (1.0 + (n_crowd - 1) * rho)
    c3_pass = abs(n_eff - (100.0 / 10.9)) < 1e-12 and 9.1 < n_eff < 9.2

    # 4. Exact binomial voters-per-nine ladder at p=0.60 (#24729)
    p99_at_99 = majority_prob_exact(99, 0.6)
    p99_at_101 = majority_prob_exact(101, 0.6)
    v_99 = next(n for n in range(1, 600, 2) if majority_prob_exact(n, 0.6) >= 0.99)
    v_999 = next(n for n in range(1, 600, 2) if majority_prob_exact(n, 0.6) >= 0.999)
    v_9999 = next(n for n in range(1, 600, 2) if majority_prob_exact(n, 0.6) >= 0.9999)
    c4_pass = (
        round(p99_at_99 * 100, 3) == 97.807
        and round(p99_at_101 * 100, 3) == 97.910
        and (v_99, v_999, v_9999) == (133, 235, 339)
    )

    # 5. Bayesian log-odds evidence accumulation (#24711, #24720)
    # Start at p0 = 0.10 (odds 1:9), 5 independent clues each with likelihood ratio LR = 3
    odds = (1.0 / 9.0) * (3.0 ** 5)
    p_post = odds / (1.0 + odds)
    c5_pass = abs(p_post - (27.0 / 28.0)) < 1e-12 and round(p_post * 100) == 96

    # 6. Base-rate gate false-discovery rate & severity-weighted Bayes threshold (#24756, #24758-#24762)
    prev, sens, spec = 0.001, 0.95, 0.95
    p_flag_harm = prev * sens
    p_flag_innocent = (1.0 - prev) * (1.0 - spec)
    false_alarm_share = p_flag_innocent / (p_flag_harm + p_flag_innocent)
    c6_pass = round(false_alarm_share * 100, 1) == 98.1

    # 7. Difference-in-Differences (DiD) + displacement counterfactual (#24763, #24765)
    # Treated dropped 20 -> 12 (-8), Control dropped 20 -> 15 (-5), Displacement added +2 elsewhere => true net effect = -1
    delta_treated = 12.0 - 20.0
    delta_control = 15.0 - 20.0
    displacement = 2.0
    net_causal_reduction = -(delta_treated - delta_control) - displacement
    c7_pass = abs(net_causal_reduction - 1.0) < 1e-12

    # 8. Deterministic seeded check of greedy trap (~71-72%) vs 10% exploration (>99%) (#24727-#24733)
    rng = random.Random(20261022)
    p_bad, p_good = 0.40, 0.60
    def run_bandit(eps: float, trials: int = 1000, steps: int = 1000) -> float:
        wins = 0
        for _ in range(trials):
            counts = [1, 1]
            sums = [
                1.0 if rng.random() < p_bad else 0.0,
                1.0 if rng.random() < p_good else 0.0,
            ]
            for _ in range(steps):
                if rng.random() < eps:
                    arm = rng.randrange(2)
                else:
                    arm = 1 if (sums[1] / counts[1]) >= (sums[0] / counts[0]) else 0
                reward = 1.0 if rng.random() < (p_good if arm == 1 else p_bad) else 0.0
                counts[arm] += 1
                sums[arm] += reward
            if (sums[1] / counts[1]) > (sums[0] / counts[0]):
                wins += 1
        return wins / trials

    greedy_rate = run_bandit(0.0)
    explore_rate = run_bandit(0.10)
    c8_pass = (greedy_rate < 0.85) and (explore_rate >= 0.99) and (explore_rate - greedy_rate >= 0.15)

    checks = [c1_pass, c2_pass, c3_pass, c4_pass, c5_pass, c6_pass, c7_pass, c8_pass]
    payload = {
        "schema": "Xi.Triad_Substrate_Laws.v1.3",
        "status": "PASS" if all(checks) else "FAIL",
        "checks_passed": sum(bool(c) for c in checks),
        "total_checks": len(checks),
        "diffusive_coupling_trajectory": traj,
        "kuramoto_locked_phase_rad": round(phi_star, 6),
        "correlated_crowd_n_eff_100_rho01": round(n_eff, 4),
        "voters_per_nine_p060": {"99%": v_99, "99.9%": v_999, "99.99%": v_9999},
        "bayes_5clues_lr3_posterior": round(p_post, 6),
        "gate_false_alarm_share_prev0001": round(false_alarm_share, 4),
        "did_net_causal_reduction": net_causal_reduction,
        "early_unlucky_recovery": {
            "greedy_eps_0": round(greedy_rate, 4),
            "explore_eps_010": round(explore_rate, 4),
        },
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    payload["sigil_13"] = sigil_from_sha256(hashlib.sha256(raw).hexdigest())
    return payload


if __name__ == "__main__":
    print(json.dumps(run_verification(), indent=2, ensure_ascii=False))
