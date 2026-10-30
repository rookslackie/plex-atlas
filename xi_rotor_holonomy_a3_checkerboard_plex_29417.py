#!/usr/bin/env python3
"""
xi_rotor_holonomy_a3_checkerboard_plex_29417.py
Zero-dependency, standalone second-seat verification by Plex (Perplexity Computer) for:
  1. JasonAetionix's 6-Test Rotor / Rodrigues / Spin(3)->SO(3) Double Cover / Closed-Loop / Levi-Civita Holonomy Protocol (#29402)
  2. Claude's #29410 / #29413 / #29417 Model A3 8x8x8 Lattice (1,176 plaquettes, 343 cubes) Checkerboard (v0.6) & Vertex-Gauge (v0.7) Rotor-Lift Audit.

Run directly on any machine with Python 3 standard library only:
  python3 xi_rotor_holonomy_a3_checkerboard_plex_29417.py
"""

from __future__ import annotations
import hashlib
import json
import math
import pathlib
import random
from typing import Dict, List, Tuple, Any

Vec3 = Tuple[float, float, float]
Mat3 = Tuple[Vec3, Vec3, Vec3]
Rotor = Tuple[float, float, float, float]  # (w, x, y, z) in Spin(3) ~= SU(2)

I3: Mat3 = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
)


def vec_norm(v: Vec3) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def vec_normalize(v: Vec3) -> Vec3:
    n = vec_norm(v)
    if n == 0.0:
        raise ValueError("Zero vector")
    return (v[0] / n, v[1] / n, v[2] / n)


def mat_add(A: Mat3, B: Mat3, scale_b: float = 1.0) -> Mat3:
    return tuple(
        tuple(A[i][j] + scale_b * B[i][j] for j in range(3))
        for i in range(3)
    )  # type: ignore


def mat_mul(A: Mat3, B: Mat3) -> Mat3:
    return tuple(
        tuple(sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3))
        for i in range(3)
    )  # type: ignore


def mat_T(A: Mat3) -> Mat3:
    return tuple(
        tuple(A[j][i] for j in range(3))
        for i in range(3)
    )  # type: ignore


def mat_vec(A: Mat3, v: Vec3) -> Vec3:
    return (
        A[0][0] * v[0] + A[0][1] * v[1] + A[0][2] * v[2],
        A[1][0] * v[0] + A[1][1] * v[1] + A[1][2] * v[2],
        A[2][0] * v[0] + A[2][1] * v[1] + A[2][2] * v[2],
    )


def mat_frob_diff(A: Mat3, B: Mat3) -> float:
    return math.sqrt(sum((A[i][j] - B[i][j]) ** 2 for i in range(3) for j in range(3)))


def skew_K(n_hat: Vec3) -> Mat3:
    nx, ny, nz = vec_normalize(n_hat)
    return (
        (0.0, -nz, ny),
        (nz, 0.0, -nx),
        (-ny, nx, 0.0),
    )


def rodrigues_matrix(n_hat: Vec3, theta: float, sign: float = 1.0) -> Mat3:
    K = skew_K(n_hat)
    K2 = mat_mul(K, K)
    R = mat_add(I3, K, sign * math.sin(theta))
    return mat_add(R, K2, 1.0 - math.cos(theta))


def taylor_exp_matrix(n_hat: Vec3, theta: float, terms: int = 28) -> Mat3:
    K = skew_K(n_hat)
    result = I3
    power = I3
    fact = 1.0
    for m in range(1, terms + 1):
        power = mat_mul(power, K)
        fact *= float(m)
        result = mat_add(result, power, (theta ** m) / fact)
    return result


def rotor_from_axis_angle(n_hat: Vec3, theta: float) -> Rotor:
    nx, ny, nz = vec_normalize(n_hat)
    half = 0.5 * theta
    s = math.sin(half)
    return (math.cos(half), s * nx, s * ny, s * nz)


def rotor_mul(q1: Rotor, q2: Rotor) -> Rotor:
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return (
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    )


def rotor_conj(q: Rotor) -> Rotor:
    return (q[0], -q[1], -q[2], -q[3])


def rotor_neg(q: Rotor) -> Rotor:
    return (-q[0], -q[1], -q[2], -q[3])


def rotor_dist(q1: Rotor, q2: Rotor) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(q1, q2)))


def rotor_act_vec(q: Rotor, v: Vec3) -> Vec3:
    vq: Rotor = (0.0, v[0], v[1], v[2])
    out = rotor_mul(rotor_mul(q, vq), rotor_conj(q))
    return (out[1], out[2], out[3])


def rotor_to_matrix(q: Rotor) -> Mat3:
    c0 = rotor_act_vec(q, (1.0, 0.0, 0.0))
    c1 = rotor_act_vec(q, (0.0, 1.0, 0.0))
    c2 = rotor_act_vec(q, (0.0, 0.0, 1.0))
    return (
        (c0[0], c1[0], c2[0]),
        (c0[1], c1[1], c2[1]),
        (c0[2], c1[2], c2[2]),
    )


def matrix_to_canonical_rotor(R: Mat3) -> Rotor:
    """
    Canonical lift SO(3) -> Spin(3) with non-negative scalar part w >= 0 (Shepperd / trace branch).
    """
    tr = R[0][0] + R[1][1] + R[2][2]
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        w = 0.25 * s
        x = (R[2][1] - R[1][2]) / s
        y = (R[0][2] - R[2][0]) / s
        z = (R[1][0] - R[0][1]) / s
    elif (R[0][0] > R[1][1]) and (R[0][0] > R[2][2]):
        s = math.sqrt(1.0 + R[0][0] - R[1][1] - R[2][2]) * 2.0
        w = (R[2][1] - R[1][2]) / s
        x = 0.25 * s
        y = (R[0][1] + R[1][0]) / s
        z = (R[0][2] + R[2][0]) / s
    elif R[1][1] > R[2][2]:
        s = math.sqrt(1.0 + R[1][1] - R[0][0] - R[2][2]) * 2.0
        w = (R[0][2] - R[2][0]) / s
        x = (R[0][1] + R[1][0]) / s
        y = 0.25 * s
        z = (R[1][2] + R[2][1]) / s
    else:
        s = math.sqrt(1.0 + R[2][2] - R[0][0] - R[1][1]) * 2.0
        w = (R[1][0] - R[0][1]) / s
        x = (R[0][2] + R[2][0]) / s
        y = (R[1][2] + R[2][1]) / s
        z = 0.25 * s
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    w, x, y, z = w / norm, x / norm, y / norm, z / norm
    if w < 0.0:
        w, x, y, z = -w, -x, -y, -z
    return (w, x, y, z)


def cayley_klein_su2_to_matrix(n_hat: Vec3, theta: float) -> Mat3:
    nx, ny, nz = vec_normalize(n_hat)
    half = 0.5 * theta
    c, s = math.cos(half), math.sin(half)
    u00 = complex(c, -s * nz)
    u01 = complex(-s * ny, -s * nx)
    u10 = complex(s * ny, -s * nx)
    u11 = complex(c, s * nz)

    def mat2_mul(A, B):
        return (
            (A[0][0] * B[0][0] + A[0][1] * B[1][0], A[0][0] * B[0][1] + A[0][1] * B[1][1]),
            (A[1][0] * B[0][0] + A[1][1] * B[1][0], A[1][0] * B[0][1] + A[1][1] * B[1][1]),
        )

    U = ((u00, u01), (u10, u11))
    U_dag = ((u00.conjugate(), u10.conjugate()), (u01.conjugate(), u11.conjugate()))

    def su2_rotate(v: Vec3) -> Vec3:
        vx, vy, vz = v
        X = ((complex(vz, 0.0), complex(vx, -vy)), (complex(vx, vy), complex(-vz, 0.0)))
        Y = mat2_mul(mat2_mul(U, X), U_dag)
        return (Y[0][1].real, -Y[0][1].imag, Y[0][0].real)

    c0 = su2_rotate((1.0, 0.0, 0.0))
    c1 = su2_rotate((0.0, 1.0, 0.0))
    c2 = su2_rotate((0.0, 0.0, 1.0))
    return (
        (c0[0], c1[0], c2[0]),
        (c0[1], c1[1], c2[1]),
        (c0[2], c1[2], c2[2]),
    )


def audit_a3_8x8x8_lattice_lifts(grid_n: int = 8) -> Dict[str, Any]:
    """
    Independent reproduction of Claude's #29417 8^3 lattice check (1,176 plaquettes, 343 cubes)
    for Model A3 v0.6 (checkerboard alternating vertex angles) and v0.7 (smooth vertex field)
    where edge transport is T(p->q) = R_p^T R_q.
    """
    rng = random.Random(20261030)

    # Enumerate all vertices p = (x, y, z) in {0..7}^3
    vertices = [(x, y, z) for x in range(grid_n) for y in range(grid_n) for z in range(grid_n)]

    # Build recorded Model A3 v0.6 (checkerboard R = Rz^((i+j+k)%2)) and recorded v0.7 (R = Rz^(i%4) Rx^(j%4) Ry^(k%4))
    qz_90 = rotor_from_axis_angle((0.0, 0.0, 1.0), math.pi / 2.0)
    qx_90 = rotor_from_axis_angle((1.0, 0.0, 0.0), math.pi / 2.0)
    qy_90 = rotor_from_axis_angle((0.0, 1.0, 0.0), math.pi / 2.0)

    def rotor_pow(q_base: Rotor, exp_n: int) -> Rotor:
        acc: Rotor = (1.0, 0.0, 0.0, 0.0)
        for _ in range(exp_n % 4):
            acc = rotor_mul(acc, q_base)
        return acc

    v06_q: Dict[Tuple[int, int, int], Rotor] = {}
    v06_R: Dict[Tuple[int, int, int], Mat3] = {}
    v07_q: Dict[Tuple[int, int, int], Rotor] = {}
    v07_R: Dict[Tuple[int, int, int], Mat3] = {}

    for (x, y, z) in vertices:
        q06 = rotor_pow(qz_90, (x + y + z) % 2)
        v06_q[(x, y, z)] = q06
        v06_R[(x, y, z)] = rotor_to_matrix(q06)

        # Recorded v0.7 rule: R(i,j,k) = Rz^(i%4) Rx^(j%4) Ry^(k%4)
        q07 = rotor_mul(rotor_mul(rotor_pow(qz_90, x), rotor_pow(qx_90, y)), rotor_pow(qy_90, z))
        v07_q[(x, y, z)] = q07
        v07_R[(x, y, z)] = rotor_to_matrix(q07)

    # Enumerate directed positive edges e = (p, q)
    pos_edges: List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = []
    for (x, y, z) in vertices:
        if x + 1 < grid_n:
            pos_edges.append(((x, y, z), (x + 1, y, z)))
        if y + 1 < grid_n:
            pos_edges.append(((x, y, z), (x, y + 1, z)))
        if z + 1 < grid_n:
            pos_edges.append(((x, y, z), (x, y, z + 1)))

    # Random sign per undirected edge (same seed/order for both fields, matching #29417)
    random_edge_sign: Dict[Tuple[Tuple[int, int, int], Tuple[int, int, int]], float] = {
        e: (1.0 if rng.random() < 0.5 else -1.0) for e in pos_edges
    }

    # Enumerate all 3 * 8 * 7 * 7 = 1,176 elementary plaquettes
    # A plaquette at base p in plane (d1, d2) has 4 vertices: p -> p+d1 -> p+d1+d2 -> p+d2 -> p
    dirs = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
    plaquettes: List[Tuple[Tuple[int, int, int], int, int]] = []
    for (x, y, z) in vertices:
        for a in range(3):
            for b in range(a + 1, 3):
                da, db = dirs[a], dirs[b]
                if (x + da[0] < grid_n and y + da[1] < grid_n and z + da[2] < grid_n and
                        x + db[0] < grid_n and y + db[1] < grid_n and z + db[2] < grid_n):
                    plaquettes.append(((x, y, z), a, b))

    def add_pt(p: Tuple[int, int, int], d: Tuple[int, int, int]) -> Tuple[int, int, int]:
        return (p[0] + d[0], p[1] + d[1], p[2] + d[2])

    def eval_field(v_q: Dict[Tuple[int, int, int], Rotor], v_R: Dict[Tuple[int, int, int], Mat3]) -> Dict[str, Any]:
        max_so3_defect = 0.0
        neg_vertex_lift = 0
        neg_pos_scalar_edge_lift = 0
        neg_random_edge_lift = 0

        # Precompute edge rotors under the 3 lift rules for positive edges e = (p -> q)
        edge_q_vertex: Dict[Tuple[Tuple[int, int, int], Tuple[int, int, int]], Rotor] = {}
        edge_q_pos_w: Dict[Tuple[Tuple[int, int, int], Tuple[int, int, int]], Rotor] = {}
        edge_q_rand: Dict[Tuple[Tuple[int, int, int], Tuple[int, int, int]], Rotor] = {}

        for (p, q) in pos_edges:
            T_pq = mat_mul(mat_T(v_R[p]), v_R[q])
            # Lift 1: vertex rotor q_p^{-1} q_q
            qv = rotor_mul(rotor_conj(v_q[p]), v_q[q])
            # Lift 2: canonical w >= 0 edge lift from matrix T_pq
            qw = matrix_to_canonical_rotor(T_pq)
            # Lift 3: random sign per edge
            s_rand = random_edge_sign[(p, q)]
            qr = (s_rand * qw[0], s_rand * qw[1], s_rand * qw[2], s_rand * qw[3])

            edge_q_vertex[(p, q)] = qv
            edge_q_pos_w[(p, q)] = qw
            edge_q_rand[(p, q)] = qr

        def get_edge_rotor(table, u, v) -> Rotor:
            if (u, v) in table:
                return table[(u, v)]
            return rotor_conj(table[(v, u)])

        plaquette_rand_sign: Dict[Tuple[Tuple[int, int, int], int, int], int] = {}

        for (p0, a, b) in plaquettes:
            da, db = dirs[a], dirs[b]
            p1 = add_pt(p0, da)
            p2 = add_pt(p1, db)
            p3 = add_pt(p0, db)

            # SO(3) matrix loop
            T01 = mat_mul(mat_T(v_R[p0]), v_R[p1])
            T12 = mat_mul(mat_T(v_R[p1]), v_R[p2])
            T23 = mat_mul(mat_T(v_R[p2]), v_R[p3])
            T30 = mat_mul(mat_T(v_R[p3]), v_R[p0])
            M_loop = mat_mul(mat_mul(T01, T12), mat_mul(T23, T30))
            err_m = mat_frob_diff(M_loop, I3)
            if err_m > max_so3_defect:
                max_so3_defect = err_m

            # Rotor loops
            for lift_idx, table in enumerate((edge_q_vertex, edge_q_pos_w, edge_q_rand)):
                q_loop = rotor_mul(
                    rotor_mul(get_edge_rotor(table, p0, p1), get_edge_rotor(table, p1, p2)),
                    rotor_mul(get_edge_rotor(table, p2, p3), get_edge_rotor(table, p3, p0)),
                )
                is_minus_one = q_loop[0] < 0.0
                if lift_idx == 0 and is_minus_one:
                    neg_vertex_lift += 1
                elif lift_idx == 1 and is_minus_one:
                    neg_pos_scalar_edge_lift += 1
                elif lift_idx == 2:
                    if is_minus_one:
                        neg_random_edge_lift += 1
                    plaquette_rand_sign[(p0, a, b)] = -1 if is_minus_one else 1

        # Check all 7^3 = 343 elementary cubes: product of the 6 boundary faces' signs under random edge lift
        cubes_plus_one = 0
        total_cubes = 0
        for x in range(grid_n - 1):
            for y in range(grid_n - 1):
                for z in range(grid_n - 1):
                    total_cubes += 1
                    # 6 faces of cube (x,y,z): (xy at z, z+1), (xz at y, y+1), (yz at x, x+1)
                    s_prod = (
                        plaquette_rand_sign[((x, y, z), 0, 1)]
                        * plaquette_rand_sign[((x, y, z + 1), 0, 1)]
                        * plaquette_rand_sign[((x, y, z), 0, 2)]
                        * plaquette_rand_sign[((x, y + 1, z), 0, 2)]
                        * plaquette_rand_sign[((x, y, z), 1, 2)]
                        * plaquette_rand_sign[((x + 1, y, z), 1, 2)]
                    )
                    if s_prod == 1:
                        cubes_plus_one += 1

        return {
            "plaquettes_total": len(plaquettes),
            "cubes_total": total_cubes,
            "max_so3_matrix_loop_defect": max_so3_defect,
            "minus1_plaquettes_vertex_rotor_lift": neg_vertex_lift,
            "minus1_plaquettes_positive_scalar_edge_lift": neg_pos_scalar_edge_lift,
            "minus1_plaquettes_random_sign_edge_lift": neg_random_edge_lift,
            "cubes_with_six_face_sign_product_plus1": cubes_plus_one,
        }

    res_v06 = eval_field(v06_q, v06_R)
    res_v07 = eval_field(v07_q, v07_R)
    passed = (
        res_v06["plaquettes_total"] == 1176
        and res_v06["cubes_total"] == 343
        and res_v06["max_so3_matrix_loop_defect"] < 1e-14
        and res_v06["minus1_plaquettes_vertex_rotor_lift"] == 0
        and res_v06["minus1_plaquettes_positive_scalar_edge_lift"] == 0
        and res_v06["cubes_with_six_face_sign_product_plus1"] == 343
        and res_v07["minus1_plaquettes_vertex_rotor_lift"] == 0
        and res_v07["minus1_plaquettes_positive_scalar_edge_lift"] == 0
        and res_v07["cubes_with_six_face_sign_product_plus1"] == 343
        and res_v06["minus1_plaquettes_random_sign_edge_lift"] == res_v07["minus1_plaquettes_random_sign_edge_lift"]
    )
    return {
        "passed": passed,
        "v0_6_checkerboard": res_v06,
        "v0_7_vertex_gauge": res_v07,
    }


def run_all() -> Dict[str, Any]:
    rng = random.Random(20261030)

    # Test 1: Rodrigues Sign
    rz_90 = rodrigues_matrix((0.0, 0.0, 1.0), math.pi / 2.0, sign=+1.0)
    rz_90_flip = rodrigues_matrix((0.0, 0.0, 1.0), math.pi / 2.0, sign=-1.0)
    ex, ey = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    r_pos = mat_vec(rz_90, ex)
    r_flip = mat_vec(rz_90_flip, ex)
    err_pos = vec_norm((r_pos[0] - ey[0], r_pos[1] - ey[1], r_pos[2] - ey[2]))
    err_flip = vec_norm((r_flip[0] - ey[0], r_flip[1] - ey[1], r_flip[2] - ey[2]))
    t1_pass = (err_pos < 1e-15) and (abs(err_flip - 2.0) < 1e-15)

    # Test 2: Rotor Composition
    max_comp_err = 0.0
    non_comm = 0
    for _ in range(256):
        a1 = (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))
        a2 = (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))
        th1, th2 = rng.uniform(-math.pi, math.pi), rng.uniform(-math.pi, math.pi)
        q1, q2 = rotor_from_axis_angle(a1, th1), rotor_from_axis_angle(a2, th2)
        q12, q21 = rotor_mul(q1, q2), rotor_mul(q2, q1)
        err = mat_frob_diff(mat_mul(rotor_to_matrix(q1), rotor_to_matrix(q2)), rotor_to_matrix(q12))
        if err > max_comp_err:
            max_comp_err = err
        if rotor_dist(q12, q21) > 1e-3:
            non_comm += 1
    t2_pass = (max_comp_err < 1e-14) and (non_comm == 256)

    # Test 3: Double Cover
    max_dc_err = 0.0
    min_anti = 999.0
    for _ in range(256):
        a = (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))
        th = rng.uniform(-math.pi, math.pi)
        q = rotor_from_axis_angle(a, th)
        mq = rotor_neg(q)
        max_dc_err = max(max_dc_err, mat_frob_diff(rotor_to_matrix(q), rotor_to_matrix(mq)))
        min_anti = min(min_anti, rotor_dist(q, mq))
    qz90 = rotor_from_axis_angle((0.0, 0.0, 1.0), math.pi / 2.0)
    qz360 = rotor_mul(rotor_mul(qz90, qz90), rotor_mul(qz90, qz90))
    qz720 = rotor_mul(qz360, qz360)
    t3_pass = (
        max_dc_err < 1e-15
        and abs(min_anti - 2.0) < 1e-14
        and mat_frob_diff(rotor_to_matrix(qz360), I3) < 1e-14
        and rotor_dist(qz360, (-1.0, 0.0, 0.0, 0.0)) < 1e-15
        and rotor_dist(qz720, (1.0, 0.0, 0.0, 0.0)) < 1e-15
    )

    # Test 4: Closed Loop Checkerboard (8^3 Lattice Model A3 v0.6 & v0.7 + Free-Edge Plaquette Comparison)
    lattice_res = audit_a3_8x8x8_lattice_lifts(8)
    qx_pi = rotor_from_axis_angle((1.0, 0.0, 0.0), math.pi)
    qy_pi = rotor_from_axis_angle((0.0, 1.0, 0.0), math.pi)
    q_pauli = rotor_mul(rotor_mul(qx_pi, qy_pi), rotor_mul(rotor_conj(qx_pi), rotor_conj(qy_pi)))
    qx_60 = rotor_from_axis_angle((1.0, 0.0, 0.0), math.pi / 3.0)
    qy_60 = rotor_from_axis_angle((0.0, 1.0, 0.0), math.pi / 3.0)
    q_curved = rotor_mul(rotor_mul(qx_60, qy_60), rotor_mul(rotor_conj(qx_60), rotor_conj(qy_60)))
    R_curved = rotor_to_matrix(q_curved)
    curved_rad = math.acos(max(-1.0, min(1.0, (R_curved[0][0] + R_curved[1][1] + R_curved[2][2] - 1.0) / 2.0)))
    t4_pass = (
        lattice_res["passed"]
        and mat_frob_diff(rotor_to_matrix(q_pauli), I3) < 1e-14
        and rotor_dist(q_pauli, (-1.0, 0.0, 0.0, 0.0)) < 1e-14
        and abs(curved_rad - 1.010721020568314) < 1e-12
    )

    # Test 5: Holonomy (Flat Plane Polar Christoffel RK4 + Sphere S^2 Octant Triangle RK4 + Colatitude 0.9 RK4)
    def rk4_polar_segment(v_init: Tuple[float, float], r0: float, p0: float, r1: float, p1: float, steps: int = 1024) -> Tuple[float, float]:
        vr, vp = v_init
        dr, dp = (r1 - r0) / steps, (p1 - p0) / steps

        def deriv(r_val: float, vr_val: float, vp_val: float) -> Tuple[float, float]:
            return (r_val * dp * vp_val, -(1.0 / r_val) * (dr * vp_val + dp * vr_val))

        r_cur = r0
        for _ in range(steps):
            k1_r, k1_p = deriv(r_cur, vr, vp)
            k2_r, k2_p = deriv(r_cur + 0.5 * dr, vr + 0.5 * k1_r, vp + 0.5 * k1_p)
            k3_r, k3_p = deriv(r_cur + 0.5 * dr, vr + 0.5 * k2_r, vp + 0.5 * k2_p)
            k4_r, k4_p = deriv(r_cur + dr, vr + k3_r, vp + k3_p)
            vr += (k1_r + 2.0 * k2_r + 2.0 * k3_r + k4_r) / 6.0
            vp += (k1_p + 2.0 * k2_p + 2.0 * k3_p + k4_p) / 6.0
            r_cur += dr
        return (vr, vp)

    v_s = (1.0, 0.0)
    v_1 = rk4_polar_segment(v_s, 1.0, 0.0, 2.0, 0.0, 1024)
    v_2 = rk4_polar_segment(v_1, 2.0, 0.0, 2.0, math.pi / 2.0, 1024)
    v_3 = rk4_polar_segment(v_2, 2.0, math.pi / 2.0, 1.0, math.pi / 2.0, 1024)
    v_e = rk4_polar_segment(v_3, 1.0, math.pi / 2.0, 1.0, 0.0, 1024)
    flat_polar_rad = math.atan2(v_e[1], v_e[0]) - math.atan2(v_s[1], v_s[0])

    def rk4_s2_arc(v_init: Vec3, p_start: Vec3, p_end: Vec3, steps: int = 1024) -> Vec3:
        ds = (math.pi / 2.0) / steps
        v = v_init
        for k in range(steps):
            def deriv(s_val: float, vec: Vec3) -> Vec3:
                gam = (
                    math.cos(s_val) * p_start[0] + math.sin(s_val) * p_end[0],
                    math.cos(s_val) * p_start[1] + math.sin(s_val) * p_end[1],
                    math.cos(s_val) * p_start[2] + math.sin(s_val) * p_end[2],
                )
                tan = (
                    -math.sin(s_val) * p_start[0] + math.cos(s_val) * p_end[0],
                    -math.sin(s_val) * p_start[1] + math.cos(s_val) * p_end[1],
                    -math.sin(s_val) * p_start[2] + math.cos(s_val) * p_end[2],
                )
                dot_tv = tan[0] * vec[0] + tan[1] * vec[1] + tan[2] * vec[2]
                return (-dot_tv * gam[0], -dot_tv * gam[1], -dot_tv * gam[2])
            s0 = k * ds
            k1 = deriv(s0, v)
            k2 = deriv(s0 + 0.5 * ds, (v[0] + 0.5 * ds * k1[0], v[1] + 0.5 * ds * k1[1], v[2] + 0.5 * ds * k1[2]))
            k3 = deriv(s0 + 0.5 * ds, (v[0] + 0.5 * ds * k2[0], v[1] + 0.5 * ds * k2[1], v[2] + 0.5 * ds * k2[2]))
            k4 = deriv(s0 + ds, (v[0] + ds * k3[0], v[1] + ds * k3[1], v[2] + ds * k3[2]))
            v = (
                v[0] + (ds / 6.0) * (k1[0] + 2.0 * k2[0] + 2.0 * k3[0] + k4[0]),
                v[1] + (ds / 6.0) * (k1[1] + 2.0 * k2[1] + 2.0 * k3[1] + k4[1]),
                v[2] + (ds / 6.0) * (k1[2] + 2.0 * k2[2] + 2.0 * k3[2] + k4[2]),
            )
        return v

    v0_oct = (0.0, 1.0, 0.0)
    v1_oct = rk4_s2_arc(v0_oct, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), 1024)
    v2_oct = rk4_s2_arc(v1_oct, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 1024)
    v3_oct = rk4_s2_arc(v2_oct, (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), 1024)
    octant_rad = math.acos(max(-1.0, min(1.0, v0_oct[0] * v3_oct[0] + v0_oct[1] * v3_oct[1] + v0_oct[2] * v3_oct[2])))
    octant_err = abs(octant_rad - (math.pi / 2.0))

    # Colatitude circle theta0 = 0.9: true 3D extrinsic RK4 parallel-transport ODE dV/dphi = -(gamma'(phi) . V(phi)) gamma(phi)
    theta0 = 0.9
    cap_steps = 4096
    dphi = (2.0 * math.pi) / cap_steps
    st0, ct0 = math.sin(theta0), math.cos(theta0)
    e_th0: Vec3 = (ct0, 0.0, -st0)
    e_ph0: Vec3 = (0.0, 1.0, 0.0)
    v_cap: Vec3 = e_th0

    def cap_deriv(phi_val: float, vec: Vec3) -> Vec3:
        cp, sp = math.cos(phi_val), math.sin(phi_val)
        gam: Vec3 = (st0 * cp, st0 * sp, ct0)
        dgam: Vec3 = (-st0 * sp, st0 * cp, 0.0)
        dot_gv = dgam[0] * vec[0] + dgam[1] * vec[1] + dgam[2] * vec[2]
        return (-dot_gv * gam[0], -dot_gv * gam[1], -dot_gv * gam[2])

    for k in range(cap_steps):
        p0 = k * dphi
        k1 = cap_deriv(p0, v_cap)
        k2 = cap_deriv(p0 + 0.5 * dphi, (v_cap[0] + 0.5 * dphi * k1[0], v_cap[1] + 0.5 * dphi * k1[1], v_cap[2] + 0.5 * dphi * k1[2]))
        k3 = cap_deriv(p0 + 0.5 * dphi, (v_cap[0] + 0.5 * dphi * k2[0], v_cap[1] + 0.5 * dphi * k2[1], v_cap[2] + 0.5 * dphi * k2[2]))
        k4 = cap_deriv(p0 + dphi, (v_cap[0] + dphi * k3[0], v_cap[1] + dphi * k3[1], v_cap[2] + dphi * k3[2]))
        v_cap = (
            v_cap[0] + (dphi / 6.0) * (k1[0] + 2.0 * k2[0] + 2.0 * k3[0] + k4[0]),
            v_cap[1] + (dphi / 6.0) * (k1[1] + 2.0 * k2[1] + 2.0 * k3[1] + k4[1]),
            v_cap[2] + (dphi / 6.0) * (k1[2] + 2.0 * k2[2] + 2.0 * k3[2] + k4[2]),
        )
    c_th = v_cap[0] * e_th0[0] + v_cap[1] * e_th0[1] + v_cap[2] * e_th0[2]
    c_ph = v_cap[0] * e_ph0[0] + v_cap[1] * e_ph0[1] + v_cap[2] * e_ph0[2]
    cap_rad = math.atan2(c_ph, c_th) % (2.0 * math.pi)
    cap_err = abs(cap_rad - 2.0 * math.pi * (1.0 - math.cos(theta0)))
    t5_pass = (abs(flat_polar_rad) < 1e-12) and (octant_err < 1e-12) and (cap_err < 1e-12)

    # Test 6: 4-Route Agreement
    max_4route_err = 0.0
    for _ in range(256):
        a = (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))
        th = rng.uniform(-math.pi, math.pi)
        R1 = rodrigues_matrix(a, th)
        R2 = taylor_exp_matrix(a, th, 28)
        R3 = rotor_to_matrix(rotor_from_axis_angle(a, th))
        R4 = cayley_klein_su2_to_matrix(a, th)
        for Rb in (R2, R3, R4):
            max_4route_err = max(max_4route_err, mat_frob_diff(R1, Rb))
    t6_pass = max_4route_err < 1e-14

    gates = {
        "test_1_rodrigues_sign": t1_pass,
        "test_2_rotor_composition": t2_pass,
        "test_3_double_cover": t3_pass,
        "test_4_closed_loop_and_8x8x8_a3_checkerboard": t4_pass,
        "test_5_holonomy_flat_polar_and_sphere_octant": t5_pass,
        "test_6_4route_independent_agreement": t6_pass,
    }
    assert all(gates.values()), f"Failed gates: {gates}"
    return {
        "script": "xi_rotor_holonomy_a3_checkerboard_plex_29417.py",
        "seat": "Plex (Perplexity Computer)",
        "gates_passed": f"{sum(gates.values())}/{len(gates)} PASS",
        "gates": gates,
        "test_4_a3_8x8x8_lattice": lattice_res,
        "test_5_holonomy": {
            "flat_polar_christoffel_rk4_rad": flat_polar_rad,
            "sphere_octant_triangle_rk4_rad": octant_rad,
            "sphere_octant_area_err": octant_err,
            "sphere_colatitude_0p9_rad": cap_rad,
            "sphere_colatitude_0p9_area_err": cap_err,
        },
        "test_6_max_4route_frobenius_err": max_4route_err,
    }


if __name__ == "__main__":
    print(json.dumps(run_all(), indent=2))
