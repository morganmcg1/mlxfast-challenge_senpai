#!/usr/bin/env python3
"""Margin certificate for a NON-BIT-EXACT candidate (R106-J, Rule 96 shelf).

WHY THIS EXISTS
---------------
The official correctness gate is token-based, not numeric.  `TASK.md:120-126`
checks the first 64 teacher-forced continuation positions at temperature zero
and records only (case, step, expected, actual).  `TASK.md:168-171` states
outright that the gate "intentionally does not port a hidden-state comparison
layer".  So a change that moves logits but not tokens passes.

That cuts both ways, and the repo already contains the cautionary measurement:
`research/frieren-pr35-r4-gate-blindness.md` records a sweep that faulted
72-75 % of 389,120 rows at mean relative error 0.2311 with ZERO token changes.
A green token gate is therefore NOT evidence that a numeric change is safe.  It
is only evidence that it did not happen to flip a token on the cases we can see.

This script produces the thing a green token gate does not: a quantitative
statement of how much headroom the candidate has before a token WOULD flip.

    safety factor = (smallest baseline decision margin)
                    / (largest logit perturbation the candidate introduces)

A safety factor of 3 means a candidate three times noisier would start flipping
tokens.  A safety factor of 10^6 means the candidate is numerically irrelevant
next to the decisions the model is making.  That number, not the token gate, is
what should decide whether a non-bit-exact lever ships.

WHAT IT MEASURES  (the five required sections)
----------------------------------------------
 1. Perturbation distribution |logit_cand - logit_base| over the FULL vocabulary
    at every gate position: absolute max / p99 / p50, and the same relative to
    the baseline logit magnitude.
 2. Baseline decision margin (top-1 minus top-2) at every gate position:
    min / p1 / p50.  This is the quantity a perturbation has to beat.
 3. Safety factor = min margin / max perturbation, plus the count of positions
    whose own margin is below 10x their own perturbation, plus the count of
    EXACT ties (margin == 0), which are fragile at any perturbation whatsoever.
 4. Argmax under both arms at every gate position.  FLIP COUNT MUST BE ZERO.
    Non-zero is terminal for the candidate.
 5. Rank-and-delta exposure.  `TASK.md:132-134` allows a hidden `anchors` gate
    to require "a bounded top-logit rank and delta", so argmax stability is not
    sufficient: the ORDER of the top few tokens is also observable.  We count
    adjacent gaps inside the top-N that are narrower than the perturbation.

USAGE  (two arms, captured separately so they may be different BUILDS)
---------------------------------------------------------------------
    # arm A: baseline
    python3 research/maple-frieren-r106j-margin-certificate.py capture \
        --label baseline --out /tmp/cert/baseline.npz --steps 64

    # arm B: candidate (env-selected lever, or a different build entirely)
    DARKBLOOM_QMV_WIDE_CODES=1 \
    python3 research/maple-frieren-r106j-margin-certificate.py capture \
        --label qmv_wide --out /tmp/cert/qmv_wide.npz --steps 64

    python3 research/maple-frieren-r106j-margin-certificate.py certify \
        --baseline /tmp/cert/baseline.npz --candidate /tmp/cert/qmv_wide.npz \
        --out research/<name>-certificate.json

`capture` writes the arm to disk precisely so the two arms need not be the same
binary.  For a shipping change the candidate arm is a REBUILD with the source
default flipped, not an environment variable, because the official harness does
not set our environment.

Exit codes:
    0  certificate produced (see "verdict" in the report; may still be FAIL)
    2  worker binary or golden fixture missing
    3  protocol/consistency error -- the certificate is not trustworthy
    4  certify found a TOKEN FLIP (terminal for the candidate)

MODES
-----
    --mode teacher   teacher-forced: feed the golden token back (what the
                     official gate does, TASK.md:120-126).  Error-limiting.
    --mode free      greedy self-feed: feed the model's OWN token back.  This
                     emulates the hidden `free_run` gate (TASK.md:136-138),
                     which is error-COMPOUNDING: one flip diverges the whole
                     suffix.  Teacher-forced agreement does not imply free-run
                     agreement, so a serious certificate runs both.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER = os.path.join(REPO, ".build-worker/release/mlxfast-runtime-worker")
GOLDEN = os.path.join(
    REPO, "correctness_prompts/public_longcopy_gate_english_512_1024.json"
)
VOCAB_SIZE = 100_352

# Fusion/dispatch witnesses, so "the candidate path actually ran" is recorded
# in the same artifact as the numbers rather than asserted separately (Rule 33).
TRACE_RE = re.compile(r"^.*(fusion|fused|DARKBLOOM|wide-codes|narrow-scales|"
                      r"lane-major|declined|inactive|escaped).*$", re.M)


# --------------------------------------------------------------------------
# capture
# --------------------------------------------------------------------------
def capture(args) -> int:
    if not os.path.exists(WORKER):
        print(f"missing worker binary {WORKER}; build with ./benchmark.sh --local-iterate",
              file=sys.stderr)
        return 2
    if not os.path.exists(args.golden):
        print(f"missing golden fixture {args.golden}", file=sys.stderr)
        return 2

    with open(args.golden) as fh:
        case = json.load(fh)["cases"][args.case_index]
    prompt = case["prompt_tokens"]
    expected = case["expected_tokens"]
    steps = min(args.steps, len(expected) - 1)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    err_path = os.path.splitext(args.out)[0] + ".worker.err"

    env = dict(os.environ)
    env.setdefault("MLXFAST_WEIGHTS_PATH", args.weights)
    # Ask every known tracer to speak, so reachability is witnessed for free.
    env["DARKBLOOM_TRACE_FUSION"] = env.get("DARKBLOOM_TRACE_FUSION", "1")
    env["DARKBLOOM_ATTN_SCALE_NARROW_LOG"] = env.get(
        "DARKBLOOM_ATTN_SCALE_NARROW_LOG", "1")

    # +1 because correctness_begin already produces the step-0 distribution.
    logits = np.zeros((steps + 1, VOCAB_SIZE), dtype=np.float32)
    filled = np.zeros(steps + 1, dtype=bool)
    tokens: list[int] = []
    expected_seen: list[int] = []

    t_launch = time.perf_counter()
    with open(err_path, "wb") as errfh:
        proc = subprocess.Popen(
            [WORKER, "runtime-worker", "--weights", args.weights],
            cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=errfh, env=env, text=True,
        )

        def send(req):
            proc.stdin.write(json.dumps(req) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            if not line:
                raise SystemExit(f"worker closed stdout; see {err_path}")
            resp = json.loads(line)
            if not resp.get("ok", False):
                raise SystemExit("worker error: " + json.dumps(resp)[:2000])
            return resp

        hello = json.loads(proc.stdout.readline())
        print(f"[{args.label}] worker up in {time.perf_counter() - t_launch:.1f}s "
              f"ok={hello.get('ok')} mode={args.mode} steps={steps} "
              f"top_k={args.top_k}", flush=True)

        def absorb(idx, resp):
            top = resp["top_logits"]
            # The worker contract (LagunaRuntimeCorrectnessCompare.swift:443-462)
            # guarantees top_logits[0].token == returned token and descending
            # order with ties broken by LOWER token id.  Check the first
            # invariant here: if it fails the whole certificate is void.
            if top[0]["token"] != resp["token"]:
                raise SystemExit("protocol: top_logits[0] != returned token")
            row = logits[idx]
            ids = np.fromiter((e["token"] for e in top), dtype=np.int64,
                              count=len(top))
            vals = np.fromiter((e["logit"] for e in top), dtype=np.float64,
                               count=len(top))
            row[ids] = vals.astype(np.float32)
            filled[idx] = len(top) >= VOCAB_SIZE
            tokens.append(resp["token"])

        resp = send({"id": 1, "kind": "correctness_begin",
                     "prompt_tokens": prompt, "top_k": args.top_k,
                     "expected_token": expected[0]})
        absorb(0, resp)
        expected_seen.append(expected[0])

        for i in range(steps):
            # teacher-forced feeds the GOLDEN token; free-run feeds OUR token.
            feed = expected[i] if args.mode == "teacher" else tokens[-1]
            resp = send({"id": 2 + i, "kind": "correctness_step",
                         "token": feed, "top_k": args.top_k,
                         "expected_token": expected[i + 1]})
            absorb(i + 1, resp)
            expected_seen.append(expected[i + 1])
            if (i + 1) % 16 == 0:
                print(f"[{args.label}] step {i + 1}/{steps} "
                      f"({time.perf_counter() - t_launch:.0f}s)", flush=True)

        proc.stdin.close()
        proc.wait(timeout=300)

    with open(err_path, "r", errors="replace") as fh:
        stderr_text = fh.read()
    witness = sorted(set(m.strip() for m in TRACE_RE.findall(stderr_text)))[:200]

    darkbloom = {k: v for k, v in sorted(os.environ.items())
                 if k.startswith("DARKBLOOM_")}
    meta = {
        "label": args.label,
        "mode": args.mode,
        "steps": int(steps),
        "top_k": int(args.top_k),
        "full_vocab_rows": int(filled.sum()),
        "golden": os.path.relpath(args.golden, REPO),
        "case": case.get("name"),
        "worker_sha256": _sha256(WORKER),
        "darkbloom_env": darkbloom,
        "dispatch_witness": witness,
        "git_head": _git_head(),
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    np.savez_compressed(
        args.out,
        logits=logits,
        tokens=np.asarray(tokens, dtype=np.int64),
        expected=np.asarray(expected_seen, dtype=np.int64),
        meta=np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8),
    )
    mism = int((np.asarray(tokens) != np.asarray(expected_seen)).sum())
    print(f"[{args.label}] wrote {args.out}  full-vocab rows "
          f"{int(filled.sum())}/{steps + 1}  token mismatches vs golden {mism}",
          flush=True)
    if witness:
        print(f"[{args.label}] dispatch witness lines: {len(witness)}"
              f" (first: {witness[0][:110]})", flush=True)
    else:
        print(f"[{args.label}] NO dispatch witness lines captured", flush=True)
    return 0


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO,
                                       text=True).strip()
    except Exception:
        return None


# --------------------------------------------------------------------------
# certify
# --------------------------------------------------------------------------
def _load(path):
    z = np.load(path, allow_pickle=False)
    meta = json.loads(bytes(z["meta"]).decode())
    return z["logits"], z["tokens"], z["expected"], meta


def certify(args) -> int:
    b_log, b_tok, b_exp, b_meta = _load(args.baseline)
    c_log, c_tok, c_exp, c_meta = _load(args.candidate)

    if b_log.shape != c_log.shape:
        print(f"shape mismatch {b_log.shape} vs {c_log.shape}", file=sys.stderr)
        return 3
    if b_meta["mode"] != c_meta["mode"]:
        print("arms captured in different modes; refusing", file=sys.stderr)
        return 3
    if b_meta["full_vocab_rows"] != b_log.shape[0] or \
       c_meta["full_vocab_rows"] != c_log.shape[0]:
        print("WARNING: an arm was captured with top_k < vocab; the "
              "perturbation maximum is a LOWER BOUND only.", file=sys.stderr)

    # In free-run mode the two arms feed their OWN tokens back, so after the
    # first divergence they are conditioned on different contexts and a
    # position-wise logit comparison is apples-to-oranges. Truncate to the
    # common prefix and report the divergence step as the headline.
    free_run = {"applicable": b_meta["mode"] == "free"}
    if free_run["applicable"]:
        diff = np.nonzero(b_tok != c_tok)[0]
        first = int(diff[0]) if diff.size else None
        free_run.update({
            "first_divergence_step": first,
            "common_prefix_length": int(first if first is not None else b_tok.size),
            "total_steps": int(b_tok.size),
            "diverged": first is not None,
            "note": ("TASK.md:136-138 hidden `free_run` gates require the exact "
                     "greedy prefix to match. Divergence is absorbing: the "
                     "suffix after the first flip is unrelated, so statistics "
                     "below cover only the common prefix."),
        })
        if first is not None:
            b_log = b_log[:first + 1]
            c_log = c_log[:first + 1]
            b_tok = b_tok[:first + 1]
            c_tok = c_tok[:first + 1]

    n_pos = b_log.shape[0]
    bl = b_log.astype(np.float64)
    cd = c_log.astype(np.float64)

    # --- 1. perturbation --------------------------------------------------
    d = np.abs(cd - bl)
    denom = np.maximum(np.abs(bl), 1e-9)
    rel = d / denom
    per_pos_max = d.max(axis=1)
    pert = {
        "abs_max": float(d.max()),
        "abs_p99": float(np.percentile(d, 99)),
        "abs_p50": float(np.percentile(d, 50)),
        "rel_max": float(rel.max()),
        "rel_p99": float(np.percentile(rel, 99)),
        "rel_p50": float(np.percentile(rel, 50)),
        "bitwise_identical": bool(np.array_equal(b_log, c_log)),
        "elements_compared": int(d.size),
        "elements_differing": int((d > 0).sum()),
    }

    # --- 2. baseline decision margin -------------------------------------
    # top-1 minus top-2 at each position, from the baseline arm.
    part = np.partition(bl, -2, axis=1)
    top1 = part[:, -1]
    top2 = part[:, -2]
    margin = top1 - top2
    marg = {
        "min": float(margin.min()),
        "p1": float(np.percentile(margin, 1)),
        "p50": float(np.percentile(margin, 50)),
        "exact_ties": int((margin == 0.0).sum()),
        "positions": int(n_pos),
    }

    # --- 3. safety factor -------------------------------------------------
    # Global: the worst margin anywhere against the worst perturbation
    # anywhere.  This is deliberately pessimistic -- they need not co-occur.
    max_pert = pert["abs_max"]
    global_sf = float(marg["min"] / max_pert) if max_pert > 0 else float("inf")
    with np.errstate(divide="ignore", invalid="ignore"):
        per_pos_sf = np.where(per_pos_max > 0, margin / per_pos_max, np.inf)
    safety = {
        "global_safety_factor": global_sf,
        "per_position_safety_factor_min": float(np.min(per_pos_sf)),
        "per_position_safety_factor_p1": float(np.percentile(
            per_pos_sf[np.isfinite(per_pos_sf)], 1))
        if np.isfinite(per_pos_sf).any() else float("inf"),
        "positions_below_10": int((per_pos_sf < 10).sum()),
        "positions_below_100": int((per_pos_sf < 100).sum()),
        "positions_at_exact_tie": marg["exact_ties"],
        "interpretation": (
            "A candidate whose perturbation were multiplied by the global "
            "safety factor would begin to flip a token. Ties (margin == 0) "
            "are resolved by LOWER token id in the worker contract, so they "
            "are fragile at ANY nonzero perturbation and are counted "
            "separately rather than folded into the ratio."),
    }

    # --- 4. argmax flips --------------------------------------------------
    # Reproduce the worker's tie-break (descending logit, then LOWER token id)
    # so the comparison matches what the harness would actually emit.
    b_arg = _argmax_tiebreak(bl)
    c_arg = _argmax_tiebreak(cd)
    flips = np.nonzero(b_arg != c_arg)[0]
    # Cross-check against the tokens the worker itself returned.
    worker_flips = np.nonzero(b_tok != c_tok)[0]
    argmax = {
        "flip_count": int(flips.size),
        "flip_positions": [int(x) for x in flips[:64]],
        "worker_returned_token_flip_count": int(worker_flips.size),
        "worker_returned_token_flip_positions": [int(x) for x in worker_flips[:64]],
        "recomputed_matches_worker_baseline": bool(np.array_equal(b_arg, b_tok)),
        "recomputed_matches_worker_candidate": bool(np.array_equal(c_arg, c_tok)),
    }

    # --- 5. rank-and-delta exposure (TASK.md:132-134) ---------------------
    N = args.rank_depth
    idx = np.argpartition(-bl, N, axis=1)[:, :N + 1]
    rows = np.arange(n_pos)[:, None]
    vals = bl[rows, idx]
    order = np.argsort(-vals, axis=1, kind="stable")
    sorted_vals = np.take_along_axis(vals, order, axis=1)
    gaps = sorted_vals[:, :-1] - sorted_vals[:, 1:]
    narrow = gaps < (2.0 * max_pert)
    rank = {
        "rank_depth": int(N),
        "adjacent_gaps_examined": int(gaps.size),
        "gaps_narrower_than_2x_max_perturbation": int(narrow.sum()),
        "positions_with_any_narrow_gap": int(narrow.any(axis=1).sum()),
        "min_adjacent_gap": float(gaps.min()),
        "note": (
            "TASK.md:132-134 permits a hidden anchor to require a bounded "
            "top-logit RANK and DELTA, not only the argmax. A gap narrower "
            "than twice the maximum perturbation is a rank the candidate "
            "could in principle reorder at an unseen context."),
    }

    # The decision-relevant safety factor. A flip at a position requires the
    # top-1/top-2 gap to be closed, which needs |d(top1)| + |d(top2)| >= margin.
    # Perturbation at rank 2170 cannot flip anything, so the full-vocabulary
    # maximum above is a deliberately pessimistic bound and this is the tight
    # one. Both are reported; the tight one is what a ship decision should use.
    ord2 = np.argsort(-bl, axis=1)[:, :2]
    r = np.arange(n_pos)
    t1, t2 = ord2[:, 0], ord2[:, 1]
    closing = d[r, t1] + d[r, t2]
    with np.errstate(divide="ignore", invalid="ignore"):
        dsf = np.where(closing > 0, margin / closing, np.inf)
    realised = cd[r, t1] - cd[r, t2]
    safety["decision_relevant"] = {
        "definition": "margin / (|delta logit at baseline top-1| + "
                      "|delta logit at baseline top-2|)",
        "min": float(dsf.min()),
        "p1": float(np.percentile(dsf[np.isfinite(dsf)], 1))
        if np.isfinite(dsf).any() else float("inf"),
        "p50": float(np.percentile(dsf[np.isfinite(dsf)], 50))
        if np.isfinite(dsf).any() else float("inf"),
        "positions_below_1": int((dsf < 1).sum()),
        "positions_below_2": int((dsf < 2).sum()),
        "positions_below_10": int((dsf < 10).sum()),
        "realised_margin_min": float(realised.min()),
        "realised_margin_negative_count": int((realised < 0).sum()),
        "perturbation_at_baseline_top1_max": float(d[r, t1].max()),
        "perturbation_at_baseline_top2_max": float(d[r, t2].max()),
    }

    # --- 5b. hidden-anchor exposure (TASK.md:131-134) ---------------------
    # The observed margin distribution is NOT the distribution an anchor is
    # drawn from: TASK.md:134 says anchors cover "near-tie hardware cases",
    # i.e. they are SELECTED for small margins. So the question that matters
    # is not "did our margins survive" but "how much ground can a competitor
    # gain on the incumbent here". That quantity is a property of the
    # perturbation alone and transfers to a tighter margin distribution.
    #
    # gain(t) = max over the baseline top-N challengers j != top1 of
    #           (delta_j - delta_top1), signed. A challenger sitting m below
    #           the incumbent overtakes it iff gain > m.
    sd = cd - bl                      # signed delta, candidate - baseline
    chal = idx[rows, order]           # baseline top-(N+1) token ids, sorted
    chal_sd = sd[rows, chal]          # signed delta at each of them
    gain = (chal_sd[:, 1:] - chal_sd[:, :1]).max(axis=1)
    probe = [0.0, 0.0625, 0.125, 0.25, 0.375, 0.5, 1.0, 2.0, 4.0]
    safety["hidden_anchor_exposure"] = {
        "definition": "signed ground a baseline top-%d challenger gains on the "
                      "baseline top-1 at this position; a near-tie anchor with "
                      "margin m flips iff gain > m" % N,
        "gain_max": float(gain.max()),
        "gain_p99": float(np.percentile(gain, 99)),
        "gain_p50": float(np.percentile(gain, 50)),
        "positions": int(n_pos),
        "fraction_of_positions_that_would_flip_at_margin": {
            f"{m:g}": float((gain > m).mean()) for m in probe},
        "note": (
            "This is the extrapolation the required sections cannot make. It "
            "reads: IF a hidden anchor sits at a near-tie of margin m in a "
            "context whose perturbation looks like ours, it flips with about "
            "this probability. It is an estimate, not a bound: the anchor's "
            "context is not ours."),
    }

    verdict, reasons = _verdict(pert, marg, safety, argmax, rank)
    if free_run.get("diverged"):
        verdict = "FAIL"
        reasons.insert(0, f"FREE-RUN DIVERGENCE at step "
                          f"{free_run['first_divergence_step']} of "
                          f"{free_run['total_steps']}: the greedy prefix does "
                          f"not match, which a hidden `free_run` gate "
                          f"(TASK.md:136-138) checks exactly.")

    report = {
        "instrument": "maple-frieren-r106j-margin-certificate.py",
        "produced_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "baseline_arm": b_meta,
        "candidate_arm": c_meta,
        "mode": b_meta["mode"],
        "positions_certified": int(n_pos),
        "1_perturbation": pert,
        "2_baseline_margin": marg,
        "3_safety_factor": safety,
        "4_argmax_flips": argmax,
        "5_rank_delta_exposure": rank,
        "7_free_run": free_run,
        "verdict": verdict,
        "verdict_reasons": reasons,
        "6_what_this_does_NOT_cover": _limitations(b_meta, n_pos),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=1)

    _print_human(report)
    print(f"\nwrote {args.out}")
    return 4 if argmax["flip_count"] or argmax["worker_returned_token_flip_count"] else 0


def _argmax_tiebreak(a):
    """Argmax with the worker's tie-break: highest logit, then LOWEST token id.

    np.argmax already returns the first (lowest) index on ties, which is the
    same rule; this wrapper exists to make the assumption explicit and to keep
    the certificate honest if the contract ever changes.
    """
    return np.argmax(a, axis=1)


def _verdict(pert, marg, safety, argmax, rank):
    reasons = []
    if argmax["flip_count"] or argmax["worker_returned_token_flip_count"]:
        reasons.append("TOKEN FLIP observed; terminal under the assignment's B1 rule.")
        return "FAIL", reasons
    if pert["bitwise_identical"]:
        reasons.append("Arms are bitwise identical over the full vocabulary at "
                       "every certified position: the change is bit-exact here "
                       "and no margin argument is needed for these positions.")
        return "PASS-BIT-EXACT", reasons
    if not argmax["recomputed_matches_worker_baseline"] or \
       not argmax["recomputed_matches_worker_candidate"]:
        reasons.append("Recomputed argmax disagrees with the token the worker "
                       "returned; the capture is not trustworthy.")
        return "VOID", reasons
    if marg["exact_ties"]:
        reasons.append(f"{marg['exact_ties']} exact top-1/top-2 tie(s): fragile "
                       "at any nonzero perturbation.")
    if safety["positions_below_10"]:
        reasons.append(f"{safety['positions_below_10']} position(s) with margin "
                       "under 10x their own perturbation.")
    if safety["global_safety_factor"] < 10:
        reasons.append(f"Global safety factor {safety['global_safety_factor']:.3g} "
                       "< 10.")
        return "MARGINAL", reasons
    reasons.append(f"Global safety factor {safety['global_safety_factor']:.3g}; "
                   f"zero token flips over {marg['positions']} positions.")
    if rank["gaps_narrower_than_2x_max_perturbation"]:
        reasons.append(f"{rank['gaps_narrower_than_2x_max_perturbation']} "
                       "top-N adjacent gap(s) narrower than 2x max perturbation: "
                       "a rank-and-delta anchor could in principle see these.")
    return "PASS-WITH-MARGIN", reasons


def _limitations(meta, n_pos):
    return [
        "COVERAGE. Certified on the public golden case(s) only "
        f"({meta.get('case')}, {n_pos} positions, mode={meta['mode']}). The "
        "local tree contains ONE public golden case; the official gate runs "
        "private fixtures we cannot see.",
        "HIDDEN ANCHORS. TASK.md:130-134 allows private `anchors` at selected "
        "hidden contexts, including bounded top-logit RANK and DELTA checks. "
        "Those contexts are not in our tree, so the margin distribution "
        "measured here is a sample from a different (and probably easier) "
        "distribution than the one the anchors were chosen from. Anchors are "
        "explicitly described as covering 'near-tie hardware cases', i.e. they "
        "are SELECTED for small margins. Our minimum margin is therefore an "
        "optimistic estimate of theirs.",
        "FREE RUN. TASK.md:136-138 adds hidden `free_run` greedy continuations. "
        "Teacher-forced certification is error-LIMITING (every step restarts "
        "from the golden prefix); free_run is error-COMPOUNDING (one flip "
        "diverges the whole suffix and is absorbing). Run this instrument a "
        "second time with --mode free to cover part of that, but the hidden "
        "free_run prompts are still not ours.",
        "BEHAVIOR / GPQA. TASK.md:139-142 checks GPQA-style answers against "
        "precomputed accepted token sequences, and TASK.md:146-155 adds a "
        "Claude semantic judge with a baseline-calibrated pass threshold "
        "(MLXFastConstants.semanticGPQAMinPassCount). Neither the prompts nor "
        "the accepted answers are in this repository. A flip inside an answer "
        "span is worth more than a flip in ordinary prose, and we cannot see "
        "which spans those are.",
        "TTFT. TASK.md:157-163 times prefill through the first greedy answer "
        "token on the hidden GPQA cases and requires that first token to be "
        "accepted. That is a first-token argmax gate on unseen contexts.",
        "EXTRAPOLATION IS WEAK. This certificate licenses one inference only: "
        "'on the contexts we can see, the candidate is X times smaller than "
        "the decisions being made'. It is NOT a proof of gate safety. It "
        "converts an unquantified risk into a quantified one. The honest use "
        "is a threshold argument: ship only when the safety factor is so large "
        "that the unseen distribution would have to be orders of magnitude "
        "tighter than the seen one to matter.",
        "PRIOR EVIDENCE THAT TOKENS ARE BLIND. "
        "research/frieren-pr35-r4-gate-blindness.md records 72-75 % of 389,120 "
        "rows faulted at mean relative error 0.2311 with ZERO token changes. "
        "Token agreement alone is worth very little; the safety factor is the "
        "load-bearing number in this report.",
    ]


def _print_human(r):
    p, m, s, a, k = (r["1_perturbation"], r["2_baseline_margin"],
                     r["3_safety_factor"], r["4_argmax_flips"],
                     r["5_rank_delta_exposure"])
    print("=" * 74)
    print(f"MARGIN CERTIFICATE   {r['baseline_arm']['label']} -> "
          f"{r['candidate_arm']['label']}   mode={r['mode']}   "
          f"positions={r['positions_certified']}")
    print("=" * 74)
    print(f"1 perturbation |cand-base|   max {p['abs_max']:.6g}   "
          f"p99 {p['abs_p99']:.6g}   p50 {p['abs_p50']:.6g}")
    print(f"                 relative     max {p['rel_max']:.6g}   "
          f"p99 {p['rel_p99']:.6g}   p50 {p['rel_p50']:.6g}")
    print(f"                 differing elements {p['elements_differing']} / "
          f"{p['elements_compared']}   bitwise-identical={p['bitwise_identical']}")
    print(f"2 baseline margin top1-top2  min {m['min']:.6g}   "
          f"p1 {m['p1']:.6g}   p50 {m['p50']:.6g}   exact ties {m['exact_ties']}")
    print(f"3 safety factor  global {s['global_safety_factor']:.6g}   "
          f"per-position min {s['per_position_safety_factor_min']:.6g}")
    print(f"                 positions below 10x: {s['positions_below_10']}   "
          f"below 100x: {s['positions_below_100']}")
    print(f"4 argmax flips   {a['flip_count']}  (worker-returned tokens: "
          f"{a['worker_returned_token_flip_count']})   MUST BE ZERO")
    print(f"5 rank exposure  top-{k['rank_depth']} adjacent gaps narrower than "
          f"2x max perturbation: {k['gaps_narrower_than_2x_max_perturbation']}"
          f"  (min gap {k['min_adjacent_gap']:.6g})")
    d = s.get("decision_relevant")
    if d:
        print("3b decision-relevant safety factor "
              "margin / (|d top1| + |d top2|)")
        print(f"                 min {d['min']:.6g}   p1 {d['p1']:.6g}   "
              f"p50 {d['p50']:.6g}")
        print(f"                 positions below 1x: "
              f"{d['positions_below_1']}   below 2x: {d['positions_below_2']}"
              f"   below 10x: {d['positions_below_10']}")
        print(f"                 perturbation at baseline top1 max "
              f"{d['perturbation_at_baseline_top1_max']:.6g}   at top2 max "
              f"{d['perturbation_at_baseline_top2_max']:.6g}")
        print(f"                 realised candidate margin min "
              f"{d['realised_margin_min']:.6g}   negative "
              f"{d['realised_margin_negative_count']}")
    h = s.get("hidden_anchor_exposure")
    if h:
        print(f"5b anchor exposure  challenger gain on incumbent: max "
              f"{h['gain_max']:.6g}   p99 {h['gain_p99']:.6g}   p50 "
              f"{h['gain_p50']:.6g}")
        cells = "  ".join(
            f"m={k}:{v * 100:.0f}%"
            for k, v in h["fraction_of_positions_that_would_flip_at_margin"]
            .items())
        print(f"                 est. flip rate at a near-tie of margin m")
        print(f"                 {cells}")
    f = r.get("7_free_run")
    if f and f.get("applicable"):
        print(f"7 free-run       diverged={f['diverged']}   common prefix "
              f"{f['common_prefix_length']} / {f['total_steps']} steps"
              + ("" if not f["diverged"]
                 else f"   first divergence at step "
                      f"{f['first_divergence_step']}"))
    print(f"\nVERDICT: {r['verdict']}")
    for reason in r["verdict_reasons"]:
        print(f"  - {reason}")
    print("\nNOT COVERED:")
    for lim in r["6_what_this_does_NOT_cover"]:
        head = lim.split(".")[0]
        print(f"  - {head}.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("capture", help="run one arm and store its logits")
    c.add_argument("--label", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--steps", type=int, default=64,
                   help="gate positions after step 0 (official gate uses 64)")
    c.add_argument("--top-k", type=int, default=VOCAB_SIZE)
    c.add_argument("--mode", choices=("teacher", "free"), default="teacher")
    c.add_argument("--golden", default=GOLDEN)
    c.add_argument("--case-index", type=int, default=0)
    c.add_argument("--weights", default="weights")
    c.set_defaults(func=capture)

    v = sub.add_parser("certify", help="compare two captured arms")
    v.add_argument("--baseline", required=True)
    v.add_argument("--candidate", required=True)
    v.add_argument("--out", required=True)
    v.add_argument("--rank-depth", type=int, default=8)
    v.set_defaults(func=certify)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
