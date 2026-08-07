#!/usr/bin/env python3
"""Fetch PR170 discriminator receipts and apply the pre-registered verdict.

The `mlxfast submissions` CLI truncates `details` and has no `--json`, so the
full metric set comes from the submissions endpoint:

    curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
      "https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions" \
      -o /tmp/subs.json

A cheaper source for a single known submission is the unauthenticated
`https://api.mlx.fast/api/submissions/<uuid>` (~21 KB), which is what the
receipt waiter archives per arm under research/artifacts/.

Usage: tanjiro-pr170-receipts.py <source.json> [more.json ...] [arm=id-prefix ...]
"""

import json
import sys
from itertools import combinations

# Renormalisation constants (advisor's frozen §9.1 contract).
ND_NUM = 0.013890
NPF_NUM = 0.0003845

# Promoted control 97a5090 / commit 3e165fa.
CTRL = {
    "prefill_s_per_tok": 0.00019120068359375,
    "decode_s_per_tok": 0.0049083720703125,
    "officialScore": 2.58882784082067,
    "ns": 2.5982163,
}

# Measured cost of the routed gather GEMM on the control receipt. This is the
# only empirical anchor; everything else below is an exact ledger derivation.
W = 43.2619            # ms, measured prefill gather-GEMM wall
W_SD = 0.402           # ms

# Exact per-window work, derived from weights/config.json:
#   hidden=2048, moe_intermediate=512, experts=256, top_k=8, blocks=40 with
#   L_moe=39 MoE blocks (one block is a dense MLP), NVFP4 4.5 bit = 0.5625 B.
#   values/expert = 2*(2048*512) + 512*2048            = 3,145,728
#   FLOP  = 512*8 * values * 2 * 39                    = 1005.022 GFLOP
#   bytes = 256  * values * 0.5625  * 39               = 17,666.41 MB
# Both reproduce the ledger exactly, which shows the ledger byte figure is
# WEIGHTS ONLY: activations/outputs (~42 MB/layer vs ~453 MB of weights) are
# not counted, so real DRAM traffic is ~9% higher than GBYTE.
GFLOP = 1005.02
GBYTE = 17.66641       # GB of expert weights read per prefill window
AI = GFLOP / GBYTE     # 56.89 FLOP/B -- equals the 34700/610 ridge exactly

# 34.7 TFLOP/s is a RIDGE ARTIFACT, not an independent number: 34700/610 =
# 56.89 = AI exactly, so it was back-derived to place this kernel on the
# roofline knee. Reported M5 Max bf16 matmul throughput is 52-60 TFLOP/s
# (MLX PR #3211), which puts M_PEAK at 16.8-19.3 ms. It is kept only to print
# the ridge; no gate may depend on it. See report section 4.1.
TFLOPS_RIDGE = 34.7
GBPS = {"546.2": 546.2, "610": 610.0, "651.8": 651.8}

M_RIDGE = GFLOP / TFLOPS_RIDGE                      # 28.96 ms at the knee
D_PEAK = {k: GBYTE / v * 1000.0 for k, v in GBPS.items()}  # 32.3 / 29.0 / 27.1

# Instrument-failure gates (see report section 4.1). Only the LOAD arm has an
# honest floor: bytes must cross DRAM at some finite rate, and half the fastest
# peak (651.8 GB/s -> 27.10 ms) is a conservative half-of-floor threshold.
# There is deliberately NO dM2 floor: at a realistic 52-60 TFLOP/s the
# peak-derived compute floor is negative, so a small dM2 is a DATUM (the
# kernel absorbed the stream), not instrument failure. The caps stay: they
# flag an arm that cost far more than any peak rate can explain, which points
# at occupancy loss rather than the axis under test.
FLOOR_S2 = 9.5         # dS2 below this -> R0a, arm void
CAP_M2 = 33.3          # dM2 above this -> R0b, flag
CAP_S2 = 37.2          # dS2 above this -> R0b, flag

# Measured instrument noise (report section 4.6), from the 1583-submission
# feed. Selection is non-circular: pick the n=16 receipts whose CANDIDATE
# decode is within 1% of the control's, then read their CANDIDATE PREFILL
# spread. Nothing in the selection touches prefill.
#   candidate prefill wall S        sample sd = 0.318 ms  (0.33%)
#   paired baseline prefill wall    sample sd = 3.997 ms  (2.1%)  -> 12.6x
#   paired estimator 188.5/prefill_speedup  sd = 2.139 ms  -> 6.7x worse
# Two consequences, both load-bearing:
#   1. The RAW candidate prefill wall is the right estimator. The harness's
#      pinned-baseline arm carries essentially all the session noise, so
#      "pairing" through prefill_speedup would inject it and cost 6.7x power.
#   2. sigma of a two-receipt difference is 0.318*sqrt(2) = 0.449 ms, so the
#      directional threshold mu=4.326 ms sits at 9.6 sigma. The arms are
#      hugely over-powered for the effects they are designed to resolve; a
#      NULL result is therefore informative rather than merely underpowered.
SIGMA_S = 0.318        # ms, per-receipt sd of the candidate prefill wall
SIGMA_D = SIGMA_S * 2 ** 0.5   # 0.449 ms, sd of a two-receipt difference

# R7 decode negative control. The probes are inside the prefill-only gather
# GEMM (M>=64 tiles; decode takes the M==1 route), so candidate decode must be
# unmoved. Baseline decode is the stable axis in the feed (sd 0.25%), so 2% on
# the raw candidate decode is ~8x instrument noise: generous, and any breach
# means the arm leaked out of prefill or the session misbehaved.
DECODE_TOL = 0.02
BASE_DECODE_MED = 13.86539   # ms/step, feed median of the pinned baseline
BASE_DECODE_TOL = 0.01       # session-health band on the receipt's own baseline

MU = 0.10 * W          # 4.326 ms, minimum separation for a directional claim
R1_WIN = 0.25 * W      # 10.82 ms, dB2 at or above this makes H3 the headline
R1_MAT = 0.10 * W      # 4.326 ms, dB2 at or above this is material
# Corroboration only, never a decision. Under H0 the two arms should each
# cost about W (doubling either axis makes that axis the bottleneck at 2x), so
# their sum lands near 2W. Under H1, H2, or H3 the sum is at most about W.
H0_SUM = 2.0 * W - MU  # 82.19 ms
ONE_W = W + MU         # 47.59 ms


def S_ms(prefill_s_per_tok):
    """Prefill wall for the frozen 512-token window, in ms."""
    return 512000.0 * prefill_s_per_tok


def T_ms(decode_s_per_tok, prefill_s_per_tok):
    """Per-step decode wall with the amortised seed prefill removed, in ms."""
    return 1000.0 * decode_s_per_tok - S_ms(prefill_s_per_tok) / 128.0


def ns_of(decode_s_per_tok, prefill_s_per_tok):
    nd = ND_NUM / decode_s_per_tok
    npf = NPF_NUM / prefill_s_per_tok
    return nd ** 0.75 * npf ** 0.25


def load(path):
    """Accept either the bulk feed or one per-submission record.

    The bulk feed is a list (or a list under a container key). The single
    endpoint `/api/submissions/{uuid}`, which is what the receipt waiter
    archives, nests the row under a `submission` key -- returning that wrapper
    rather than the row is the same mistake that once made the waiter report a
    fabricated receipt, so it is unwrapped here too.
    """
    d = json.load(open(path))
    if isinstance(d, list):
        return d
    for key in ("submissions", "items", "data", "results"):
        if isinstance(d.get(key), list):
            return d[key]
    inner = d.get("submission")
    if isinstance(inner, dict):
        return [inner]
    if "id" in d and "status" in d:
        return [d]
    raise SystemExit(f"no submission record in {path}: keys={list(d)}")


def verdict(dM2, dS2, dB2):
    """Pre-registered decision rules R0-R7 from report section 4.2.

    Deltas are ms of added prefill wall. dS2 is the RAW S2 delta; the pure
    load cost dS2p is only bracketed, not known, because S2 also adds one
    barrier and B2 adds two whose costs may coalesce:
        dS2p in [dS2 - dB2, dS2 - dB2/2]
    """
    out = []

    # R0a, DEMOTED from a hard void gate to a diagnostic. Amended 2026-08-07,
    # before dS2 was known -- the only point at which touching a pre-registered
    # rule is legitimate.
    #
    # As written, R0a voided the arm when dS2 < 9.5 ms, reasoning that +2
    # dev_load on a body of 6 moves +33% of the 17.66 GB weight stream = 5.89 GB
    # extra, which even at the fastest peak (651.8 GB/s) is >= 9.0 ms of bus
    # occupancy. The arithmetic is right and the bytes really do cross the bus.
    # The inference was wrong: bus occupancy only becomes WALL TIME when the bus
    # is the critical path. Peak-rate stream cost is 29.0 ms against W = 43.26
    # and a true runtime G >= W, so a latency-bound kernel has idle bus for the
    # extra stream to hide in. That is precisely H3 -- one of the two surviving
    # hypotheses. R0a would have filed the strongest available H3 signature as
    # an instrument failure.
    #
    # Its three stated failure modes are all excluded by evidence already in
    # hand, none of it timing:
    #   dead-code elimination  -> AIR/IR census compiled probe 2 and counted
    #                             dev_load 6->8 at both shapes (4.0.2 / 4.0.3);
    #                             an elided load is not in the AIR.
    #   wrong probe compiled   -> same census; pb2's delta signature is unique.
    #   kernel not selected    -> the M2 receipt moved the wall clock 4.5 sigma
    #                             through the identical selector plumbing.
    # So the floor is reported as absorbed bus occupancy, and never voids.
    if dS2 is not None and dS2 < FLOOR_S2:
        out.append(f"R0a ABSORPTION (not void): dS2={dS2:+.3f} < {FLOOR_S2} ms, "
                   "the peak-rate cost of the 5.89 GB the arm demonstrably "
                   f"streams. So >= {FLOOR_S2 - max(dS2, 0.0):.1f} ms of extra "
                   "bus occupancy hid inside existing stalls, which means the "
                   "bus is NOT the critical path. Elision and misselection are "
                   "excluded statically by the census and by M2's 4.5-sigma "
                   "receipt, so this is a physical reading, not a failed arm: "
                   "it is positive evidence for H3 over H2.")
    if dM2 is not None and dM2 > CAP_M2:
        out.append(f"R0b FLAG: dM2={dM2:+.3f} > {CAP_M2}; the arm cost far more "
                   "than a peak-rate second stream. Suspect occupancy loss "
                   "(register pressure) rather than pure arithmetic.")
    if dS2 is not None and dS2 > CAP_S2:
        out.append(f"R0b FLAG: dS2={dS2:+.3f} > {CAP_S2}; suspect threadgroup-"
                   "memory or occupancy loss rather than pure load bandwidth.")

    # R6 outranks everything below it. A NEGATIVE dM2 beyond mu is not noise
    # and not absorption: adding independent MMA work made the kernel FASTER,
    # which only happens when the extra instructions fill issue slots that
    # were previously stalling on NAX result latency (~256 cycles for a
    # 32x32x32 tile). That is a strictly stronger H3 finding than R1 or R5,
    # and it names a different fix (more ILP per thread, deeper software
    # pipelining) than "remove barriers".
    if dM2 is not None and dM2 <= -MU:
        out.append(f"R6 H3 WINS (LATENCY VARIANT): dM2={dM2:+.3f} <= -mu="
                   f"{-MU:.2f}. Adding a bit-exact second MMA stream made "
                   "prefill FASTER, so the kernel is latency-bound with idle "
                   "issue slots, not throughput-bound. The next mechanism is "
                   "more independent work in flight per thread (deeper "
                   "pipelining / more accumulator tiles), NOT fewer FLOPs, "
                   "fewer bytes, or fewer barriers. R1-R5 are superseded and "
                   "reported below for the record only.")

    # R1: barriers first, because a large dB2 contaminates dS2's bracket.
    if dB2 is not None:
        if dB2 >= R1_WIN:
            out.append(f"R1 H3 HEADLINE: dB2={dB2:+.3f} >= {R1_WIN:.2f} "
                       "(0.25W). Synchronisation latency dominates; the next "
                       "mechanism is removing barriers / raising occupancy, "
                       "not fewer FLOPs or bytes. dS2's bracket is wide here, "
                       "so treat R2/R3 below as provisional.")
        elif dB2 >= R1_MAT:
            out.append(f"R1' H3 MATERIAL: {R1_MAT:.2f} <= dB2={dB2:+.3f} < "
                       f"{R1_WIN:.2f}. Barriers cost real time but are not the "
                       "binding constraint on their own.")
        else:
            out.append(f"R1'' H3 MINOR: dB2={dB2:+.3f} < {R1_MAT:.2f}. "
                       "Synchronisation is not the constraint; dS2p is tightly "
                       "bracketed.")

    if dM2 is None or dS2 is None or dB2 is None:
        out.append("R2-R5 need all three arms; not all receipts are in.")
        return out

    # Order the bracket explicitly: a negative dB2 (barriers coalescing, or
    # noise around zero) flips dS2-dB2 above dS2-dB2/2.
    lo, hi = sorted((dS2 - dB2, dS2 - dB2 / 2.0))

    # R2-R5 are a 2x2 on (is dM2 large?, is dS2p large?), "large" meaning it
    # exceeds mu. The four cells are the four hypotheses:
    #
    #                 dS2p small        dS2p large
    #   dM2 small     R5  H3 latency    R3  H2 load-bound
    #   dM2 large     R2  H1 compute    R4  H0 jointly saturated
    #
    # This replaces an earlier sum rule (dM2 + dS2p <= W - mu => H3), which
    # was wrong: under H1 the pair is (W, 0) and under H2 it is (0, W), so
    # both sum to ~W and would have been misread as H3. The sum only
    # separates H0 (~2W, because doubling either axis makes that axis the
    # bottleneck at 2x) from everything else. Individual magnitudes are what
    # name the constraint. R5 is evaluated first so the boundary is
    # deterministic when a delta sits near zero.
    m_big = dM2 > MU
    s_big = hi > MU
    if not m_big and not s_big:
        out.append(f"R5 H3 BY ELIMINATION: dM2={dM2:+.3f} and dS2p_hi="
                   f"{hi:+.3f} are both <= mu={MU:.2f}. The kernel absorbed a "
                   "full extra compute stream AND a full extra load stream "
                   "without paying for either, so neither arithmetic nor "
                   "bandwidth is binding. The remaining cost is "
                   "latency/schedule.")
    elif dM2 - hi >= MU:
        out.append(f"R2 H1 WINS: dM2={dM2:+.3f} exceeds dS2p_hi={hi:+.3f} by "
                   f">= mu={MU:.2f}. MMA-limited: reduce arithmetic.")
    elif lo - dM2 >= MU:
        out.append(f"R3 H2 WINS: dS2p_lo={lo:+.3f} exceeds dM2={dM2:+.3f} by "
                   f">= mu={MU:.2f}. Load+dequant-limited: move fewer bytes or "
                   "make dequant cheaper.")
    elif m_big and lo > MU:
        out.append(f"R4 H0 JOINTLY SATURATED: dM2={dM2:+.3f} and dS2p in "
                   f"[{lo:+.3f}, {hi:+.3f}] both exceed mu={MU:.2f} and are "
                   "within mu of each other. Both streams are already "
                   "overlapped about as well as the hardware allows; only a "
                   "change that shrinks both helps.")
    else:
        # This branch used to fall into R4 and assert a joint saturation that
        # its own numbers contradicted. The real content is that the dS2p
        # bracket straddles mu while neither arm leads the other by mu, so no
        # cell is entitled. Report the gap instead of naming a regime.
        out.append(f"AMBIGUOUS CELL: dM2={dM2:+.3f}, dS2p in [{lo:+.3f}, "
                   f"{hi:+.3f}]. The bracket straddles mu={MU:.2f} and neither "
                   f"arm leads the other by mu (gaps: dM2-hi={dM2 - hi:+.3f}, "
                   f"lo-dM2={lo - dM2:+.3f}). No cell is entitled. The bracket "
                   "is wide because dB2 is large relative to dS2, so the "
                   "barrier impurity in S2 -- not the load -- is what blocks "
                   "the reading; a register-sink S2 redesign (section 9) "
                   "removes it. Do not name a regime from this.")

    # Corroboration line. H0 predicts a sum near 2W; H1/H2/H3 predict at most
    # about W. A cell verdict that contradicts this is not fatal but must be
    # reported as such rather than quietly asserted.
    tot = dM2 + hi
    if tot >= H0_SUM:
        shape = f"consistent with H0 (>= 2W-mu = {H0_SUM:.2f})"
    elif tot <= ONE_W:
        shape = f"consistent with H1/H2/H3 (<= W+mu = {ONE_W:.2f})"
    else:
        shape = (f"AMBIGUOUS: between W+mu={ONE_W:.2f} and 2W-mu="
                 f"{H0_SUM:.2f}; the cell verdict above is weakly supported")
    out.append(f"SUM CHECK: dM2+dS2p_hi = {tot:.3f} ms, {shape}.")

    # Spare-receipt rule (report section 4.5). A2 shadows the NVFP4 unpack --
    # index arithmetic, scale lookup, 4-bit extraction -- into unread
    # registers: no extra device load, no extra MMA, so it isolates the
    # scalar-ALU/address axis that M2/S2/B2 all leave untouched. It is worth
    # the fourth receipt only when the three arms agree that the constraint
    # is neither arithmetic, nor bandwidth, nor synchronisation, AND the
    # stronger R6 latency reading did not already name the fix.
    #
    # WITHDRAWN. A2's whole purpose was to size the scalar-ALU axis, but a
    # positive dM2 already bounds it: M2 perturbs int_alu by +15 against a body
    # of 87, so ALU can own at most dM2 * 87/15 of the path (see shares()). At
    # the observed dM2 that ceiling is 27.4% of W, which is too small for A2 to
    # be the headline under any outcome. The rule is kept, and still reports,
    # because the ceiling scales with dM2 -- a much larger dM2 would reopen it.
    r5 = (not m_big) and (not s_big)
    alu_cap = dM2 * BODY["int_alu"] / ADDS["m2"]["int_alu"]
    a2 = r5 and (dB2 < R1_MAT) and (dM2 > -MU) and (alu_cap > 0.5 * W)
    if a2:
        out.append("A2 SPARE: FIRE. R5 holds (both streams absorbed), R1'' "
                   f"holds (dB2={dB2:+.3f} < {R1_MAT:.2f}), R6 does not "
                   f"(dM2={dM2:+.3f} > -mu), and the ALU ceiling from dM2 is "
                   f"{alu_cap:.2f} ms = {100 * alu_cap / W:.0f}% of W, large "
                   "enough for scalar-ALU/address generation in the NVFP4 "
                   "unpack to still be the headline. Spend the spare receipt.")
    else:
        why = []
        if not r5:
            why.append("R5 did not fire (a stream was paid for)")
        if not (dB2 < R1_MAT):
            why.append(f"dB2={dB2:+.3f} >= {R1_MAT:.2f} (R1'' fails)")
        if not (dM2 > -MU):
            why.append("R6 fired and already names the fix")
        if not (alu_cap > 0.5 * W):
            why.append(f"dM2 already caps integer ALU at {alu_cap:.2f} ms = "
                       f"{100 * alu_cap / W:.0f}% of W, so A2 cannot be the "
                       "headline")
        out.append("A2 SPARE: HOLD. " + "; ".join(why) + ". The spare receipt "
                   "stays unspent; the three arms already point somewhere.")
    return out


# Static per-body AIR op counts for the ranked instantiation at the dominant
# 2048x1024_bk64 shape, and the deltas each arm adds. Both are static counts in
# the inner body, so the loop trip count cancels in every ratio below.
BODY = {"mma": 1, "int_alu": 87, "dev_load": 6, "tg_store": 5, "barrier": 7}
ADDS = {"m2": {"mma": 1, "int_alu": 15},
        "s2": {"dev_load": 2, "tg_store": 1, "barrier": 1, "int_alu": 4},
        "b2": {"barrier": 2}}


def shares(arm, delta):
    """Upper bounds on what fraction of the gather GEMM each resource can own.

    One arm gives one equation, sum_r add_r * c_r = delta, in the unknown
    per-op costs c_r >= 0. That is underdetermined, but every c_r is bounded,
    so the *total* body cost of any resource subset is bounded too: maximising
    sum_r body_r * c_r under that one equation is a one-variable LP whose
    optimum puts all of delta on whichever perturbed resource has the largest
    body/add leverage. The result is a genuine ceiling that holds no matter how
    the cost actually splits.

    Denominator is W, the roofline time for this GEMM. The kernel's true wall
    time G is unknown but G >= W, so dividing by W overstates every share. The
    bounds are therefore conservative in the direction that matters: a small
    bound really is small.
    """
    adds = ADDS[arm]
    lev = {r: BODY[r] / adds[r] for r in adds}
    best = max(lev, key=lambda r: lev[r])
    joint = delta * lev[best]
    out = [f"  resource-share ceilings from d{arm.upper()}={delta:+.3f} ms "
           f"(denominator W={W:.2f} ms; true G >= W, so these overstate):"]
    for r in sorted(adds, key=lambda r: -lev[r]):
        cap = delta * lev[r]
        out.append(f"    {r:<9} body={BODY[r]:>3}  arm adds {adds[r]:>2}  "
                   f"=> <= {cap:6.2f} ms = {100 * cap / W:5.1f}% of W")
    out.append(f"  joint ceiling for all {len(adds)} perturbed axes together: "
               f"<= {joint:.2f} ms = {100 * joint / W:.1f}% of W "
               f"(they trade off; the sum peaks on '{best}' alone)")
    if joint >= W:
        out.append("  => no residual bound from this arm alone; the ceiling "
                   "exceeds W and G is known only to be >= W.")
    else:
        out.append(f"  => RESIDUAL >= {100 - 100 * joint / W:.1f}% of the "
                   f"critical path is none of: {', '.join(sorted(adds))}")
    return out


def _gauss(mat, rhs):
    """Exact-ish square solve; returns None when the basis is singular."""
    n = len(rhs)
    m = [list(mat[i]) + [rhs[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12:
            return None
        m[c], m[p] = m[p], m[c]
        pv = m[c][c]
        m[c] = [v / pv for v in m[c]]
        for r in range(n):
            if r != c and m[r][c]:
                f = m[r][c]
                m[r] = [a - f * b for a, b in zip(m[r], m[c])]
    return [m[i][n] for i in range(n)]


def joint_ceiling(deltas):
    """Ceiling on the joint body cost of every axis any arm perturbed.

    Each arm contributes one equality sum_r add_r * c_r = delta over unknown
    marginal per-op costs c_r >= 0. Maximising sum_r body_r * c_r over that
    system is a small LP; with all coefficients and all deltas nonnegative the
    feasible set is a bounded polytope, so the optimum sits at a vertex and
    plain enumeration of bases is exact. Reported as a fraction of W, and since
    the true runtime G >= W every fraction is overstated.

    What the number means, stated carefully. The c_r are MARGINAL costs
    measured by adding work, so `body_r * c_r` is the local sensitivity of the
    kernel's wall time to resource r -- how much a proportional reduction of r
    could save -- not r's share of some hypothetical serial execution. Local
    sensitivity is the quantity an optimisation programme actually wants. The
    model assumes each c_r is constant over the perturbation range, which is
    the one substantive assumption here: a port that is already saturated can
    charge more for added work than it refunds for removed work.
    """
    arms = [a for a in ("m2", "s2", "b2") if deltas.get(a) is not None]
    if not arms:
        return ["  joint ceiling: no arms in yet."]
    neg = [a for a in arms if deltas[a] < 0]
    if neg:
        return ["  joint ceiling: NOT COMPUTED. "
                + ", ".join(f"d{a.upper()}={deltas[a]:+.3f}" for a in neg)
                + " is negative, and with nonnegative op counts and c_r >= 0 no "
                "assignment can produce a negative delta. A negative arm "
                "falsifies the nonnegative-linear cost model itself (occupancy "
                "or scheduling changed), so no ceiling derived from it holds."]
    axes = sorted({r for a in arms for r in ADDS[a]})
    A = [[float(ADDS[a].get(r, 0.0)) for r in axes] for a in arms]
    b = [float(deltas[a]) for a in arms]
    k = len(arms)
    best = None
    for basis in combinations(range(len(axes)), k):
        sol = _gauss([[A[i][j] for j in basis] for i in range(k)], b)
        if sol is None or any(v < -1e-9 for v in sol):
            continue
        val = sum(BODY[axes[j]] * v for j, v in zip(basis, sol))
        if best is None or val > best[0]:
            best = (val, {axes[j]: v for j, v in zip(basis, sol)})
    if best is None:
        return ["  joint ceiling: LP infeasible; the arms cannot be reconciled "
                "with any nonnegative per-op cost vector."]
    val, wit = best
    where = ", ".join(f"{r} at {c:.4f} ms/op" for r, c in sorted(wit.items())
                      if c > 1e-9)
    out = [f"  joint ceiling over arms {'+'.join(a.upper() for a in arms)} "
           f"({len(axes)} axes: {', '.join(axes)}):",
           f"    <= {val:.2f} ms = {100 * val / W:.1f}% of W, attained by "
           f"putting all cost on {where}"]
    if val >= W:
        # A ceiling above W carries no information about the residual: G is
        # only known to be >= W, so "the perturbed axes could own more than W"
        # is consistent with everything. Report that instead of a negative
        # residual, which would look like a finding and be one.
        out.append("    => NO RESIDUAL BOUND. The ceiling exceeds W, and G is "
                   "known only to be >= W, so this is vacuous. It would become "
                   "informative only against a measured G, which no arm in this "
                   "tree provides (that is host-side work -- see PR #148).")
    else:
        out.append(f"    => RESIDUAL >= {100 - 100 * val / W:.1f}% of the "
                   "critical path is none of the perturbed axes")
    return out


def main():
    # Anything with an `=` is an arm selector; everything else is a source
    # file. Several sources concatenate, so the three arms can be read from
    # three per-arm waiter artifacts without refetching the 17.8 MB feed.
    arms, sources = {}, []
    for a in sys.argv[1:]:
        if "=" in a:
            name, _, pref = a.partition("=")
            arms[name] = pref
        else:
            sources.append(a)
    if not sources:
        raise SystemExit(__doc__)

    rows = [r for path in sources for r in load(path)]
    ctrl_S = S_ms(CTRL["prefill_s_per_tok"])
    ctrl_T = T_ms(CTRL["decode_s_per_tok"], CTRL["prefill_s_per_tok"])
    print(f"control 97a5090  S={ctrl_S:8.3f} ms  T={ctrl_T:7.5f} ms  "
          f"ns={CTRL['ns']:.6f}")
    print(f"gather GEMM W={W:.4f}+-{W_SD:.3f} ms   {GFLOP:.2f} GFLOP  "
          f"{GBYTE:.4f} GB (weights only)  AI={AI:.2f} FLOP/B")
    dp = "  ".join(f"{k}GB/s:{v:.1f}" for k, v in sorted(D_PEAK.items()))
    print(f"peak-rate stream cost   dram {dp}  (ms)   ridge-artifact compute "
          f"{M_RIDGE:.1f} ms (NOT a gate)")
    print(f"gates  dS2 void<{FLOOR_S2}  flag>{CAP_S2}   dM2 no floor  "
          f"flag>{CAP_M2}   mu={MU:.3f}  R1_win={R1_WIN:.2f}  "
          f"H0_sum={H0_SUM:.2f}   sigma_delta={SIGMA_D:.3f} ms "
          f"({MU / SIGMA_D:.1f} sigma)   decode_tol={DECODE_TOL}")
    print()

    got = {}
    for name, pref in arms.items():
        hit = next((s for s in rows if (s.get("id") or "").startswith(pref)), None)
        if hit is None:
            print(f"{name:4s} {pref}: NOT FOUND in feed")
            continue
        m = hit.get("officialMetrics") or {}
        print(f"=== {name}  {hit.get('id')}  status={hit.get('status')} "
              f"score={hit.get('officialScore')}")
        if not m:
            print("     officialMetrics: (none published)")
            print(f"     reason: {hit.get('rejectionReason')}")
            print("     R0c INSTRUMENT FAILURE: the harness published no "
                  "metrics, so this arm measured nothing. In the audited feed "
                  "all 489 `failed` submissions have officialMetrics=null and "
                  "the modal step is the timed paired benchmark itself. Read "
                  "the failing step, fix it, and only then re-fire; do NOT "
                  "count this against the receipt budget's evidence, and do "
                  "NOT treat a missing delta as a small delta.")
            continue
        p = m.get("prefill_seconds_per_token")
        dsec = m.get("decode_seconds_per_token")
        S = S_ms(p)
        T = T_ms(dsec, p)
        got[name] = {"S": S, "T": T, "dS": S - ctrl_S, "dT": T - ctrl_T,
                     "ns": ns_of(dsec, p), "id": hit.get("id"),
                     "dec": dsec,
                     "dec_base": m.get("baseline_decode_seconds_per_token")}
        for k in ("passed_correctness", "max_abs_diff",
                  "passed_prefill_speedup_floor", "passed_decode_speedup_floor",
                  "prefill_speedup", "decode_speedup", "gpqa_ttft_passed",
                  "semantic_gpqa_passed", "benchmark_wall_seconds", "commit",
                  "error"):
            if k in m:
                print(f"     {k:32s} {m[k]}")
        print(f"     S                                {S:8.3f} ms "
              f"(dS = {S - ctrl_S:+8.3f})")
        print(f"     T                                {T:8.5f} ms "
              f"(dT = {T - ctrl_T:+8.5f})")
        print()

    dM2 = got.get("m2", {}).get("dS")
    dS2 = got.get("s2", {}).get("dS")
    dB2 = got.get("b2", {}).get("dS")
    span = (None if (dS2 is None or dB2 is None)
            else tuple(sorted((dS2 - dB2, dS2 - dB2 / 2.0))))
    print("--- decomposition ---")
    print(f"  dM2  (pure MMA doubling)        = "
          f"{'n/a' if dM2 is None else f'{dM2:+.3f} ms'}")
    print(f"  dB2  (pure barrier doubling)    = "
          f"{'n/a' if dB2 is None else f'{dB2:+.3f} ms'}")
    print(f"  dS2  (raw, load+dequant+1 barr) = "
          f"{'n/a' if dS2 is None else f'{dS2:+.3f} ms'}")
    print(f"  dS2p (pure load, interval)      = "
          f"{'n/a' if span is None else f'[{span[0]:+.3f}, {span[1]:+.3f}] ms'}")
    print()
    print("--- resource-share ceilings (each arm read on its own) ---")
    for name, delta in (("m2", dM2), ("s2", dS2), ("b2", dB2)):
        if delta is None or delta <= 0:
            continue
        for line in shares(name, delta):
            print(line)
    for line in joint_ceiling({"m2": dM2, "s2": dS2, "b2": dB2}):
        print(line)
    print()
    print("--- verdict ---")
    for line in verdict(dM2, dS2, dB2):
        print(f"  {line}")
    print()
    print("--- R7 decode negative control + session health ---")
    ctrl_dec = 1000.0 * CTRL["decode_s_per_tok"]
    for name, g in got.items():
        dec = 1000.0 * g["dec"]
        rel = abs(dec - ctrl_dec) / ctrl_dec
        flag = "OK" if rel <= DECODE_TOL else "LEAK/SUSPECT"
        print(f"  {name}: decode {dec:.5f} ms/step vs control {ctrl_dec:.5f} "
              f"({rel * 100:+.2f}%)  {flag}")
        if g["dec_base"] is None:
            print("        session health: baseline decode not published")
            continue
        bd = 1000.0 * g["dec_base"]
        brel = abs(bd - BASE_DECODE_MED) / BASE_DECODE_MED
        bflag = "OK" if brel <= BASE_DECODE_TOL else "SESSION DRIFT"
        print(f"        paired baseline decode {bd:.5f} vs feed median "
              f"{BASE_DECODE_MED:.5f} ({brel * 100:+.2f}%)  {bflag}")
        if bflag != "OK":
            print("        R7: this session's pinned baseline is off its own "
                  "feed median, so down-weight this receipt's dS and re-fire "
                  "before drawing a directional conclusion from it.")

    if got:
        print()
        print(f"--- power ---  sigma(S) = {SIGMA_S:.3f} ms/receipt, "
              f"sigma(delta) = {SIGMA_D:.3f} ms, so mu = {MU:.3f} ms is "
              f"{MU / SIGMA_D:.1f} sigma. Any |delta| >= {3 * SIGMA_D:.2f} ms "
              "is already 3 sigma; a delta inside that band is a real null, "
              "not an underpowered one.")


if __name__ == "__main__":
    main()
