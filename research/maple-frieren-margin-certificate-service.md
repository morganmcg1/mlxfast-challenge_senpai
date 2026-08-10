# The margin-certificate service — standing SOP

**Owner:** `maple-frieren` (PR #597). **Written:** 2026-08-10, round 107, in
response to the round-107 brief priority **A** ("stand up the margin
certificate as a service, not a one-off") and rule 105.12 §4.
**Instrument:** `research/maple-frieren-r106j-margin-certificate.py` (adopted as
a campaign asset in R106-J §2).
**Host of every number below:** AWS M4 Pro, `applegpu_g16s` gen 16,
`nax_available=false`. **Epoch:** 2026-08-10. Tags follow rule 105.8
(`census` / `marginal`) wherever a quantity is quoted.

This document exists so that nobody has to ask me how to get a certificate, and
so that a certificate produced by someone else is comparable to mine. §5 is
fully self-serve: the instrument is in the tree and needs nothing from me.

---

## §0. One screen

1. **Bit-exact change?** You do not need a certificate. Run the null cell
   (§5.1) to *prove* bit-exactness and ship. `verdict = PASS-BIT-EXACT` is that
   proof.
2. **Not bit-exact and you want to ship it?** You need a *number*, not an
   argument from source comments. The number is the **safety factor**:
   `min baseline decision margin / max logit perturbation`. A safety factor of
   3 means a candidate three times noisier would start flipping tokens.
3. **The official token gate cannot give you that number.** `TASK.md:168-171`
   says outright the gate "intentionally does not port a hidden-state
   comparison layer", and `research/frieren-pr35-r4-gate-blindness.md` measured
   **72–75 % of 389,120 logit rows faulted at mean relative error 0.2311 with
   ZERO token changes**. Green is not evidence of numeric safety.
4. **Cost:** **5 min 07 s** of machine time, end to end, from a diff to a
   verdict, measured — one command, §5.0/§6. The **builds** dominate (191 s for
   the clean baseline arm; only 12 s for the patched arm, because SwiftPM and
   the metallib script are both incremental). Nothing about this is expensive;
   the reason it has not been done for every shelf row is that nobody had the
   instrument.
5. **It costs zero official receipts.** The certificate is entirely local. It
   never touches the submission queue (rule 88), so it can be run at any point
   in the endgame, including after the 07:00Z integration freeze.

---

## §1. What the certificate is, and what it is not

**It is** a quantitative statement of how much numerical headroom a
non-bit-exact candidate has before the *decisions* the model makes would
change, measured on the logits themselves over the full 100,352-entry
vocabulary at every gated position, in both the teacher-forced mode the visible
gate uses and the self-feeding mode the hidden `free_run` gate uses.

**It is not:**
- a substitute for the official token gate (run that too);
- a performance measurement (it says nothing about µs/step, and per rule 105.7
  a single M4 receipt cannot see anything under ≈80 µs/step anyway);
- a licence: I report the number and the verdict, the integration owner prices
  the risk. **A `MARGINAL` verdict is not a veto.** It is a number saying "this
  candidate is within 1–2 orders of magnitude of the decision boundary on the
  one case we can see", and the correct response is usually "then it must be
  worth more than the risk", not "then it is forbidden".

---

## §2. Decision tree

```
is your change bit-exact?
├─ you *believe* so ──────────► run §5.1 null cell.
│                               PASS-BIT-EXACT  -> class 0, ship, no certificate.
│                               anything else   -> you were wrong; continue below.
└─ no ───────────────────────► self-declare a perturbation class (§3),
                                then run §5.2 (teacher) AND §5.3 (free).
                                verdict FAIL   -> terminal, do not ship.
                                verdict VOID   -> capture untrustworthy, re-run.
                                MARGINAL / PASS-WITH-MARGIN -> hand the JSON and
                                the class to the integration owner with the
                                measured value of the lever beside it.
```

The certificate is **only worth running on a lever whose value already clears
the bar**. Round-107 arithmetic: the 0.4 % draw bar is **26.27 M5 µs/step**,
i.e. **60.1 M4 µs/step** in the bytes family (α=0.4369), **52.5** in the
latency family (β=0.5), and — new in rule 105.13 — **13.9** in the dispatch
family (k=1.890). Convert first (rule 105); certify second.

---

## §3. Perturbation classes

Reproduced from R106-J §4.1, which is the ranking the shelf now uses.

| class | what it is | expected perturbation | certifiable? |
|---|---|---|---|
| **0** | bit-exact: identical FMA sequence, identical order | exactly 0 | no certificate needed |
| **1** | reassociation of a *short* reduction, ≤8 terms, one site | sub-ULP to ~1 ULP | very likely |
| **2** | reassociation of a *long* reduction or of a whole K-loop | ~1–10 ULP | plausible — must be measured |
| **3** | reassociation that changes which *values* each lane sums, over a long chain | **O(1 logit unit)**, comparable to decision margins | measured **NO** for the one row we have |
| **4** | changes the numerical *values* (coarser scales, lower precision) | unbounded by any order argument | very unlikely |

**The anchoring measurement** (the only class-3 datum anyone in this campaign
has measured, marginal, this host, 2026-08-10): `DARKBLOOM_QMV_WIDE_CODES`
produced **max |Δlogit| = 5.445** against a **minimum top-1/top-2 margin of
0.375**, global safety factor **0.0689**, decision-relevant safety factor
**1.37×**. Logits are bf16-valued — they come in multiples of 0.0625/0.125 —
so "margin 0.375" is *three representable steps*, not a rounding artefact.

**Two properties that behave differently, and confusing them is the main way to
misread a certificate:**
- **Class is a property of the kernel edit.** It transfers: if the same
  reassociation appears in another kernel, the class carries over.
- **Zero-flip is a property of the prompt.** It does **not** transfer. A
  candidate with zero flips on `longcopy-gate-english-512` tells you nothing
  about a hidden case whose margins happen to be tighter. Only the *safety
  factor* is portable, and only as an order of magnitude.

---

## §4. The request contract — what I need from you

Post these in your PR (or hand them to whoever runs §5). A request missing
items 1–4 cannot be executed and I will bounce it with this list.

1. **Commit or patch** that contains the candidate, on a branch I can fetch.
   Not a description — the diff.
2. **Self-declared class from §3, with `file:line`** for every site you
   changed the arithmetic at. If you cannot point at the line, you do not know
   the class, and the certificate will be measuring something you have not
   identified.
3. **How to build the candidate arm.** Either (a) "the source default is
   flipped in commit X, just build it", or (b) an env flag *plus* an explicit
   assertion that the flag selects **the identical code path that would ship**.
   ⚠ For a shipping change the candidate arm must ultimately be a **rebuild
   with the source default flipped**: the official harness does not set our
   environment, so an env-gated arm certifies a path that would never run.
   An env arm is acceptable **only** as a class-determination proxy.
4. **Reachability witness** (rule 33): a one-line proof the code path executes
   at all — a stderr marker, a counter, an assert that fires. Certifying an
   inactive path is the single most common way to waste this instrument.
5. **The measured value of the lever, converted** (rule 105/105.13): Δ M4
   µs/step *and* which family (bytes / latency / dispatch) *and* the resulting
   % of `cs`. If it does not clear the bar, do not ask for a certificate.
6. **Host** you measured on. If it is not a gen-16 M4, say so — the certificate
   is host-specific (§8).
7. **What you want decided.** "Is this shippable?" and "is this class-1 or
   class-2?" need different runs (the second does not need free mode).

---

## §5. Self-serve procedure

All commands from the repo root. `PY=python3`,
`S=research/maple-frieren-r106j-margin-certificate.py`.
Prerequisites: `.build-worker/release/mlxfast-runtime-worker` **and**
`.build-worker/release/mlx.metallib` both present (§9 trap 1), and
`correctness_prompts/public_longcopy_gate_english_512_1024.json` in the tree.

### §5.0 One command, if you have a diff (recommended)

```bash
bash research/maple_frieren_cert_from_patch.sh \
     --patch /tmp/your.diff --base <base sha> \
     --out research/artifacts/<you>/cert_teacher.json     # add --mode free for the second
```

This is the whole service in one command and it is the path I will use on your
request, so you may as well run it yourself. It creates **one** scratch worktree
at your base sha, force-clean-builds the **baseline** arm (worker *and*
metallib), captures it, applies your patch, rebuilds, **asserts that the worker
or metallib fingerprint actually moved**, captures the candidate, and certifies.
Both arms therefore come from the same tree ± your patch, by construction rather
than by memory. Its exit code is the instrument's (§7), so `cert && ship` is a
safe idiom. It refuses (exit 3) if your patch applies but changes neither
binary, because certifying that would print `PASS-BIT-EXACT` for a change that
cannot run.

Use §5.1–§5.3 below when the two arms are not expressible as one patch (two
unrelated branches, a prebuilt binary someone handed you, an env-var mechanism
probe — for the last of those, `--candidate-env K=V` on the driver is easier).

**The driver has been run end to end and it works** (job
`56b8fc43…`, 2026-08-10T15:43Z, **307 s**, exit 0, per-phase timings in §6.1).
The test case is the one self-test that can actually catch the §9 trap 7 defect:
`research/artifacts/maple-frieren-r107f/sop/noop_selftest.patch` adds two comment
lines *inside a string literal* in the worker CLI's `printUsage()`, so it
provably changes the binary and provably cannot execute under the worker
protocol. Correct verdict `PASS-BIT-EXACT` **with different worker hashes**, and
that is what came out (`f1aa4abe375e` → `6cc3c385b0d1`, 0 of 6,522,880 elements
differing, min baseline margin 0.375 as always). Certificate kept at
`research/artifacts/maple-frieren-r107f/sop/cert_noop_selftest.json`. Re-run it
after any change to the instrument:

```bash
bash research/maple_frieren_cert_from_patch.sh \
     --patch research/artifacts/maple-frieren-r107f/sop/noop_selftest.patch \
     --base HEAD --out /tmp/cert_selftest.json    # must print PASS-BIT-EXACT, worker DIFFER, exit 0
```

### §5.1 Null cell — run this FIRST, always (rule 79)

Two captures of the *same* arm. The only admissible verdict is
`PASS-BIT-EXACT`. Anything else means the host is not reproducible and every
subsequent number is noise. **A null cell must be declared as one**, with
`--expect-identical-build`; without the flag an identical pair is `VOID`, on the
grounds that the overwhelmingly more likely cause of two identical arms is a
candidate that was never rebuilt (§9 trap 7).

```bash
python3 $S capture --label null_a --mode teacher --steps 64 --out /tmp/cert/a.npz
python3 $S capture --label null_b --mode teacher --steps 64 --out /tmp/cert/b.npz
python3 $S certify --baseline /tmp/cert/a.npz --candidate /tmp/cert/b.npz \
        --expect-identical-build \
        --out research/artifacts/<you>/cert_null.json
```

`research/maple_frieren_r107f_sop_dress_rehearsal.sh` is exactly this, timed,
with the provenance header; run it verbatim if you want the null cell and the
SLA in one go.

### §5.2 Teacher-forced certificate (emulates the visible gate)

```bash
# arm A — baseline binary
python3 $S capture --label baseline --mode teacher --steps 64 --out /tmp/cert/base_t.npz \
        --worker /path/to/baseline/tree/.build-worker/release/mlxfast-runtime-worker
# arm B — candidate binary (either rebuild in place between the two captures, or
#          point --worker at a second tree; the .npz is on disk precisely so the
#          arms need NOT be the same build)
python3 $S capture --label candidate --mode teacher --steps 64 --out /tmp/cert/cand_t.npz \
        --worker /path/to/candidate/tree/.build-worker/release/mlxfast-runtime-worker
python3 $S certify --baseline /tmp/cert/base_t.npz --candidate /tmp/cert/cand_t.npz \
        --out research/artifacts/<you>/cert_teacher.json
```

`--worker` defaults to this tree's `.build-worker/release/mlxfast-runtime-worker`,
so you can omit it if you are rebuilding in place. `mlx.metallib` must sit
**beside** whichever worker you name — the worker resolves it from its own
directory, and a missing one is a hard error (exit 2) rather than a silently
wrong answer. Both fingerprints go into the certificate and `certify` compares
them: if they have not moved, you get `VOID`, not a pass (§9 trap 7).

### §5.3 Free-run certificate (emulates the hidden `free_run` gate)

Teacher-forced agreement does **not** imply free-run agreement: teacher forcing
is error-*limiting* (the golden token is fed back every step), free running is
error-*compounding* (one flip diverges the whole suffix). `TASK.md:136-138`
allows a hidden `free_run` gate, so a serious certificate runs both.

```bash
python3 $S capture --label baseline  --mode free --steps 128 --out /tmp/cert/base_f.npz
python3 $S capture --label candidate --mode free --steps 128 --out /tmp/cert/cand_f.npz
python3 $S certify --baseline /tmp/cert/base_f.npz --candidate /tmp/cert/cand_f.npz \
        --out research/artifacts/<you>/cert_free.json
```

### §5.4 Options worth knowing

| flag | default | when to change it |
|---|---|---|
| `--steps` | 64 | 64 is what the official gate checks; 128 for free mode to expose divergence |
| `--top-k` | 100352 | full vocabulary; lower only to save disk, never for a shipping decision |
| `--rank-depth` (certify) | 8 | the `anchors` gate (`TASK.md:132-134`) may check a bounded top rank+delta; raise if you suspect deep-rank exposure |
| `--mode` | teacher | see §5.2/§5.3 |
| `--golden` / `--case-index` | the public longcopy gate, case 0 | any other public fixture; note §8 limit 1 |
| `--worker` (capture) | this tree's `.build-worker/release/…` | capture two arms from two trees in one session, e.g. a scratch worktree at the base sha |
| `--expect-identical-build` (certify) | off | **only** for a deliberate null cell. It flips the build guard: with it, arms that *differ* are `VOID`; without it, arms that are *identical* are `VOID` |

---

## §6. Measured turnaround (the honest SLA)

Dress rehearsal run for this document, on this host, tree `6c94099e`, worker
`.build-worker/release/mlxfast-runtime-worker` built 13:51Z, job
`89ba759c-dbdb-488b-b29d-e185903b273d`, wall clock 2026-08-10T15:18Z
(`research/maple_frieren_r107f_sop_dress_rehearsal.sh`, artifact
`research/artifacts/maple-frieren-r107f/sop/cert_rehearsal_null.json`):

| phase | seconds | note |
|---|---|---|
| capture, teacher, 64 steps | **50** | includes worker start-up + 512-token prefill |
| capture, teacher, 64 steps (2nd) | **49** | |
| certify + JSON | **<1** | pure numpy, no GPU |
| **null cell total** | **99** | exit 0 |

**Result: `PASS-BIT-EXACT`, 0 of 6,522,880 elements differing, 0 argmax flips,
global safety factor `inf`.** The instrument is live on the current tree and the
host is reproducible; the service is UP.

Two free side-findings from the rehearsal worth recording:
- The baseline margin distribution came back **min 0.375, p1 0.615, p50 6.5,
  0 exact ties** — *identical to the last three digits* to the R106-J run of
  11:21Z at tree `83dd8007`. Since R107-F ships nothing, that is an independent
  logit-level confirmation that the submitted surface has not moved between the
  two trees, and it means the **min margin 0.375 can be treated as a campaign
  constant** for sizing any future certificate (`census` on this case/prompt;
  it is a property of the fixture, not of a candidate).
- `certify` is free (<1 s for 6.5 M elements over 65 positions). All the cost is
  in `capture`. So certifying *more* pairs, more modes or a deeper
  `--rank-depth` is essentially free once the arms are on disk — **always keep
  the `.npz` files**, they are 12 MB (teacher) / 24 MB (free) and they let a
  later question be answered without re-running the GPU.

Corroborating R106-J timings (2026-08-10, same host): teacher captures at
11:21:28 and 11:22:34 → **66 s** apart; the two free-mode 128-step captures
plus their certify fit inside 11:27→11:31 → ≈**75 s** per free capture,
≈**20 s** for three certifies together.

### §6.1 End-to-end, measured: patch in → certificate out

Not an estimate. Job `56b8fc43-bfbc-401e-832e-cfeb5328111b`, 2026-08-10T15:43Z,
one invocation of `research/maple_frieren_cert_from_patch.sh` (§5.0) at base
`56376a1b`, `--steps 64`, mode teacher, on the inert-patch self-test:

| phase | seconds |
|---|---|
| scratch worktree at base sha | 1 |
| build **baseline** arm, force-clean (worker + metallib) | **191** |
| capture baseline | 53 |
| `git apply` + rebuild **candidate** + fingerprint assertion | **12** |
| capture candidate | 50 |
| certify + JSON | <1 |
| **total, one mode** | **307 s = 5 min 07 s**, exit 0 |

Three things in that table are worth more than the total:

- **The second build is nearly free — 12 s, not 191 s.** SwiftPM recompiled one
  file and relinked (8.5 s), and `tools/build-mlx-metallib.sh` short-circuited
  (it only pays its 50 s from clean). So the marginal cost of a *second* patch
  against the same base is ≈115 s, not ≈5 min: **send me several arms at once**
  and keep the scratch worktree with `--keep`.
- **Adding the free-mode pair** (§5.3, `--mode free --steps 128`) costs ≈150 s
  more if you reuse the worktree, since both builds are already done.
- The **10–15 min write-up** below is the real bottleneck, and it is mine, not
  the machine's. If you only need the verdict and the safety factor, read them
  off the human-readable block the instrument prints and do not wait for me.

**End-to-end request → verdict, assuming I must build your arm:**

| step | time |
|---|---|
| fetch + read the patch, assign class | 5–10 min (human/agent-bounded) |
| driver, one mode (§6.1) | **307 s** measured |
| second mode / second arm on the same base | ≈**150 s** each |
| null cell (§5.1) | **99 s** (skippable: §6.1 already contains a bit-exact cell) |
| write-up with class, safety factor, limits | 10–15 min |
| **total** | **≈20–30 min**, of which **≈5–8 min is machine** |

If you already provide a built candidate binary, subtract the builds and point
`capture --worker` at it.

### §6.2 Side-finding: the worker binary is not path-reproducible, the metallib is

Measured while validating §6.1, and it constrains how far the fingerprint guard
can be trusted. The scratch worktree at `56376a1b` and this workspace at
`6110a4de` have **byte-identical Swift sources** (`git diff` over `Sources
Vendor Package.swift tools` is empty — `56376a1b` only added files under
`research/`). Built with the same recipe in two different directories:

| artifact | workspace `…/workspace/target` | scratch `/private/tmp/cert-from-patch` |
|---|---|---|
| `mlxfast-runtime-worker` | `80b67aa047e1e8…` | `f1aa4abe375e0b…` **DIFFER** |
| `mlx.metallib` | `8e8b18afaee1ed…` | `8e8b18afaee1ed…` **same** |

So the worker embeds its absolute build path (debug info / module paths) while
the metallib is bit-reproducible across directories. Consequences, in order of
how likely you are to trip over them:

1. **`same_worker=False` is not evidence that a patch changed anything** if the
   two arms were built in *different* directories. The guard's contract is
   "these two logit tensors came from these two specific binaries", nothing
   stronger. §5.0's driver dodges this by building both arms in **one**
   directory, which is the main reason to prefer it over §5.2 by hand.
2. **The inverse is the useful direction and is unaffected:**
   `same_worker=True` really does mean the same bytes ran, which is the defect
   §9 trap 7 is about.
3. A kernel-only (`.metal`) change is the one case where you can compare across
   directories, because the metallib hash is reproducible. Convenient, since
   that is exactly the diff class this service exists for.

**Deadline reality, revised down by §6.1.** I previously said requests arriving
after ≈**04:00Z on 2026-08-11** could not include a rebuild and still clear the
06:00Z handoff to fern (#625) / 07:00Z integration freeze. With the driver
measured at **307 s**, the true machine deadline is ≈**05:45Z** for a bare
verdict and ≈**05:15Z** if you want the written analysis. Past that, anyone
holding this branch can run §5.0 themselves — see §11. Send the patch early, not
the finished argument.

---

## §7. Output contract

### Verdicts (`verdict` in the JSON; `verdict_reasons` always explains)

| verdict | meaning | what it licenses |
|---|---|---|
| `PASS-BIT-EXACT` | arms bitwise identical over the full vocabulary at every certified position | class 0. Ship on the token gate alone. |
| `PASS-WITH-MARGIN` | zero token flips **and** global safety factor ≥ 10 | the strongest statement this instrument makes |
| `MARGINAL` | zero token flips but global safety factor < 10, and/or positions whose own margin is under 10× their own perturbation, and/or exact ties | a priced risk, not a refusal (§1) |
| `FAIL` | a token flipped (recomputed argmax **or** the token the worker returned), or the free-run prefix diverged | terminal. Exit code 4. |
| `VOID` | recomputed argmax disagrees with the worker's returned token, **or** the build-identity guard fired (§9 trap 7) | the certificate says *nothing* about the candidate — not a pass and not a failure. Fix the procedure and re-run. |

`VOID` is applied **last** and outranks every other verdict, including `FAIL`.
If the two arms are not two different experiments, nothing measured can be
attributed to a candidate change, so reporting a failure would be as wrong as
reporting a pass.

### Exit codes

`0` `PASS-BIT-EXACT` or `PASS-WITH-MARGIN` · `2` worker binary, `mlx.metallib`
or golden fixture missing · `3` `VOID` · `4` `FAIL` · `5` `MARGINAL`.

Only the two PASS verdicts exit `0`, so **`cert && ship` is a safe idiom**.
⚠ **This is a change from the contract published earlier on 2026-08-10**, under
which `MARGINAL` and `VOID` both exited `0`; any wrapper written against that
contract would have shipped an under-margin or untrustworthy candidate. See the
changelog, **§12**.

### JSON sections

`0_build_identity` (both arms' `worker_sha256` and `metallib_sha256`,
`same_worker`, `same_metallib`, `same_darkbloom_env`,
`arms_are_the_same_experiment`, `declared_identical`, each arm's build-tree git
HEAD and dirty flag, `env_only_arm`, `void_reason`, and graded `caveats`) ·
`1_perturbation` (abs/rel max, p99, p50; `bitwise_identical`;
`elements_differing`/`elements_compared`) · `2_baseline_margin` (top-1 minus
top-2: min, p1, p50, `exact_ties`) · `3_safety_factor` (global,
per-position min/p1, `positions_below_10`, `positions_below_100`, and the
`decision_relevant` sub-block = `margin / (|Δ at top-1| + |Δ at top-2|)`, plus
`hidden_anchor_exposure`) · `4_argmax_flips` (**must be 0**) ·
`5_rank_delta_exposure` (top-N adjacent gaps narrower than 2× max
perturbation) · `6_what_this_does_NOT_cover` (machine-readable limits) ·
`7_free_run` · `verdict`, `verdict_reasons`. Both arms record
`worker_sha256`, `git_head`, `darkbloom_env`, `dispatch_witness`, `case`,
`golden`, `captured_utc` — so a certificate is self-provenancing and a
mismatched pair is detectable after the fact.

**Read `3_safety_factor.decision_relevant` before `global_safety_factor`.** The
global factor divides the *smallest margin anywhere* by the *largest
perturbation anywhere*, which are usually different positions; it is a genuine
worst case but it is pessimistic by construction. The decision-relevant factor
is per-position and is the number that actually predicts a flip. On the one
live exercise these were **0.0689** and **1.37×** respectively — a 20×
difference in the same certificate.

---

## §8. Limits — what a green certificate does **not** cover

State these every time. They are also emitted into
`6_what_this_does_NOT_cover`.

1. **One case, one prompt, one prefix.** `longcopy-gate-english-512` from the
   public fixture, 512-token prefill. Hidden cases have their own margins;
   zero-flip does not transfer (§3).
2. **Greedy / temperature 0 only.** No sampling.
3. **One device, one driver, one gen.** This M4 Pro, `applegpu_g16s` gen 16.
   The ranked machine is an M5.
4. 🚨 **It cannot certify anything inside the `_nax` prefill kernels.** They
   are unreachable on a gen-16 host (`nax_available=false`), and they are
   **94.2 % of prefill GPU time** on the ranked M5. A change to those kernels
   cannot be certified here **by anyone on this hardware** — not with more
   effort, not with a better script. That is a hard boundary of the whole
   local-evidence programme, not a limitation of this instrument.
5. **Two modes, not the full hidden gate.** `anchors`-style rank+delta checks
   are approximated by `5_rank_delta_exposure`, not reproduced.
6. **Decode-path logits.** Prefill numerics enter only through the prefix they
   produce; a prefill-only change with a decode-invariant prefix will look
   bit-exact here and still perturb a hidden prefill comparison.
7. **The upstream-equivalence oracle is not a substitute** (measured, R106-J
   §3.2.1c): `research/run_upstream_equivalence.sh` never calls
   `prepareFusedRuntimeWeights()`, so it does not exercise the fused runtime
   path at all. It reported `maxAbsLogitError 0.0` for all 8 decode steps on a
   candidate this instrument scored at safety **1.37×**. Do not quote it as a
   correctness receipt for a fused-path change.
8. **Not a statement about performance, and not about the *other* arm.** A
   certificate on arm B says nothing about whether arm B is faster, nor about
   any third arm that "does the same thing differently".

---

## §9. Traps, all of them paid for once already

1. **`mlx.metallib` is outside SwiftPM's dependency graph.**
   `tools/build-mlx-metallib.sh` writes `.build-worker/release/mlx.metallib`;
   `swift build` will never regenerate it. A force-clean deletes it and the
   next run selects 0 tests / fails with exit 3. Rebuild by hand (50 s,
   158,502,072 B). Measured in R106-J §3.2.1b.
2. **Env arm ≠ shipping arm** (§4 item 3). The harness does not set our env.
3. **Both captures must come from the intended binaries.** As of cert v2 the
   instrument enforces this itself: `capture` fingerprints the worker *and* the
   `mlx.metallib` beside it, and `certify` refuses to grade a pair whose
   fingerprints disagree with what you declared (§7, `0_build_identity`). You
   no longer have to remember to compare the hashes by hand — but you do have
   to pass `--expect-identical-build` on a null cell, and you must not pass it
   on a real one. See trap 7 for what this cost me.
4. **Do not leave a stray `.metallib` under `Sources/`** — unrelated to the
   certificate, but it aborts the official submit wrapper, and people build
   here and submit ten minutes later.
5. **Per-kernel GPU-busy time is not perturbation-immune.** Unrelated to
   correctness, relevant to anyone timing around a capture: an unguarded MSL
   dump inflated every kernel duration ≈2.5× on this host via DVFS (R107-F
   §3.3). Do not interleave captures with heavy compiles and then compare
   timings.
6. **`--steps 64` is not conservative for free mode.** Divergence often starts
   later; use 128.
7. **The instrument's own strongest verdict was reachable by forgetting to
   rebuild** (found by self-audit on 2026-08-10, fixed in cert v2). Cert v1
   *recorded* `worker_sha256` for each arm and then never compared them. So the
   sequence "capture baseline → edit the source → forget to run `swift build` →
   capture candidate" produced two byte-identical logit tensors, which v1
   graded `PASS-BIT-EXACT` — the highest-confidence verdict in the vocabulary —
   for a candidate that had never executed. Same failure class as #575 (a
   pipeline that silently measured the wrong tree), and it would have been
   *my* instrument certifying somebody else's kernel.
   Three things worth carrying to any other verification tool, because none of
   them are specific to this one:
   - **Recording provenance is not checking provenance.** The field was in the
     JSON the whole time. A reader auditing the artifact could have caught it;
     the tool could not.
   - **A null cell cannot catch this.** The null cell (§5.1) is exactly the
     case where the two builds *are* identical and `PASS-BIT-EXACT` is
     correct, so a passing null cell is evidence *consistent with* the bug.
     Self-tests that share a failure mode with the defect are worthless
     against it. The self-test that does catch it is the *inert-patch* cell:
     a real diff that changes the binary and provably cannot execute
     (`research/artifacts/maple-frieren-r107f/sop/noop_selftest.patch`), whose
     correct verdict is `PASS-BIT-EXACT` with **different** worker hashes.
   - **The guard must outrank the finding.** In v2 the build-identity check is
     applied *last*, so `VOID` overrides even `FAIL`. A `FAIL` from the wrong
     binaries is not a conservative error, it is a false accusation against
     somebody's patch, and it costs them a receipt to disprove.
   The residual hole, stated so nobody re-derives it as news: fingerprints
   prove *which binary ran*, not *what that binary contains*. An env-only arm
   (§4 item 3) legitimately reuses one binary; v2 emits an `ENV-ONLY ARM`
   caveat and grades it, because voiding it would make the instrument useless
   for the most common request. On an env-only arm the fingerprint check buys
   you nothing and you are back to reading the dispatch witness lines. And per
   §6.2, two *different* worker hashes prove nothing at all if the arms were
   built in different directories — the worker embeds its build path.

---

## §10. Who this is for

Standing offer, in the order the round-107 brief put them:

- **nezuko (#616)** — recovery patch. Her R106-B verdict is a closure
  (N-RECOVER / DO NOT SEND), so no certificate is needed unless a *new*
  non-bit-exact arm appears.
- **tanjiro (#648 / #642)** — split-K tie flip and H3. A split-K reassociation
  is **class 2** by construction (a whole K-loop reassociated), so it is the
  textbook case for this instrument: plausible, must be measured. A tie flip is
  specifically the failure mode `2_baseline_margin.exact_ties` counts.
- **edward / alphonse (#644)** — only if a summand is non-bit-exact.
- **fern (#625)** — as integration owner, the consumer of every verdict; and
  after 06:00Z the owner of this queue.

Rule 105.5 requires each summand in a multi-part draw to be **bit-exact**. So
in the endgame the certificate's practical role is narrow and specific: it is
what lets a *non*-bit-exact summand be argued for at all, and the honest
default for a non-bit-exact summand under time pressure is **do not ship it**.
Ask for the certificate anyway if the lever is large — a `PASS-WITH-MARGIN`
turns an automatic no into a decision.

## §11. If I am not here

Nothing in §5 needs me. Four files, all in the tree, all on the advisor branch:

| file | what it is |
|---|---|
| `research/maple-frieren-r106j-margin-certificate.py` | the instrument (`capture`, `certify`, `census`) |
| `research/maple_frieren_cert_from_patch.sh` | the one-command driver — patch in, certificate out (§5.0) |
| `research/maple_frieren_r107f_sop_dress_rehearsal.sh` | the null cell / is-the-service-up check (§5.1) |
| `research/artifacts/maple-frieren-r107f/sop/noop_selftest.patch` | the inert-patch self-test that catches the §9 trap 7 defect |

The only judgement calls are (a) assigning the class from the diff, which §3
reduces to "does any lane sum over different *values*, or only in a different
*order*?", and (b) deciding what a `MARGINAL` verdict is worth, which is an
integration decision and was never mine.

---

## §12. Changelog — and the exit-code contract change

Read this before you wire the instrument into anything that branches on its
exit status.

### v2 — 2026-08-10, self-audit of the v1 instrument (commit `56376a1b`)

Three defects, all found by auditing my own tool rather than by it failing.
The first one is the serious one and is written up in full as §9 trap 7.

1. **False `PASS-BIT-EXACT` on a forgotten rebuild.** v1 recorded
   `worker_sha256` per arm and never compared the two. Fixed: report section
   `0_build_identity`, and the guard is applied **last** so `VOID` outranks even
   `FAIL`. Three VOID branches — arms identical but not declared identical
   ("the candidate never rebuilt"), `--expect-identical-build` passed but arms
   differ ("a null cell that is not null"), and neither arm carries a
   fingerprint at all (pre-v2 `.npz` captures, which are simply unadjudicable
   on this axis). Three graded caveats that do **not** void: `ENV-ONLY ARM`,
   `METALLIB NOT FINGERPRINTED`, `DIRTY BUILD TREE`.
2. **`mlx.metallib` was not fingerprinted.** Since it lives outside SwiftPM's
   dependency graph (§9 trap 1), a kernel-only change can move the metallib
   while leaving the worker binary byte-identical — exactly the diff class the
   service exists for. `capture` now hard-errors (exit 2) if the worker or its
   sibling `mlx.metallib` is missing, and records path/sha256/bytes for both,
   plus `build_tree_git_head` and `build_tree_dirty`.
3. **Exit codes were dishonest.** v1 returned 0 for anything that was not an
   outright failure. v2:

| exit | meaning |
|---|---|
| 0 | `PASS-BIT-EXACT` or `PASS-WITH-MARGIN` |
| 2 | capture could not run (missing worker or metallib) |
| 3 | `VOID` — provenance is unadjudicable, **including unknown verdicts** |
| 4 | `FAIL` — a token actually flipped |
| 5 | `MARGINAL` — safety factor < 10, a human has to price it |

⚠️ **Breaking:** a `MARGINAL` teacher pair used to exit 0 and now exits 5, and
a null cell that does not pass `--expect-identical-build` now exits 3. The
2026-08-10 15:18Z rehearsal script was itself broken by change 1 and has been
fixed in the same commit; if you have your own wrapper, that is the line to
check. Verified on the R106-J class-3 env arm: same numbers as v1 (max |Δ|
5.44531, global safety 0.0689, 39 positions under 10×), verdict still
`MARGINAL`, exit now 5 instead of 0.

Also new in v2: `capture --worker` (point the fingerprint at a binary other
than the default), `certify --expect-identical-build`, and the driver
`research/maple_frieren_cert_from_patch.sh` (§5.0), which cannot make mistake 1
because it *asserts* that the worker or metallib hash moved after applying the
patch and refuses to continue otherwise.

**How v2 was validated** — five cells, all run, all as predicted:

| cell | expected | got |
|---|---|---|
| v1 rehearsal pair, no flag | VOID (the defect) | VOID, exit 3 |
| same pair, `--expect-identical-build` | PASS-BIT-EXACT, numbers unchanged from 15:18Z | exit 0, min margin 0.375 / p1 0.615 / p50 6.5, 0/6,522,880 |
| R106-J class-3 env arm | MARGINAL + `ENV-ONLY ARM`, not voided | exit 5, safety 0.0689, 39 positions <10× |
| missing worker / missing metallib | exit 2 with an actionable message | exit 2, names `tools/build-mlx-metallib.sh` |
| **inert patch, end to end via the driver** | PASS-BIT-EXACT with **different** worker hashes | exit 0, `f1aa4abe375e`→`6cc3c385b0d1` (§5.0, §6.1) |

Rows 1 and 5 are the pair that matters, and they have to be read together,
because **v1 returns `PASS-BIT-EXACT` for both of them**. Row 1 is a candidate
that never rebuilt; row 5 is a candidate that really did rebuild and really is
bit-exact. v1 cannot distinguish them — that is the whole defect. v2 separates
them (VOID vs PASS) using the only evidence that does distinguish them, which is
the fingerprints. A guard that only produced row 1 would be untested against
false positives; row 5 is what shows v2 does not simply void everything.

See also §6.2 for the limit of the guard — the worker binary is not reproducible
across build directories, so `same_worker=False` is weaker evidence than it
looks, while `same_worker=True` is exactly as strong as it looks.

### v1 — 2026-08-10, R106-J

Original instrument: teacher/free capture, argmax-margin certificate, rank/delta
exposure, null cell, `census`. Everything in §7 except `0_build_identity` and
the exit-code table dates from v1 and is unchanged; v2 adds guards, it does not
touch the numerics. Any v1 certificate is still valid on its numbers, but it
carries no provenance verdict — re-run `certify` on the stored `.npz` pair if
you need one, and expect `VOID` with "neither arm carries a worker fingerprint"
for captures taken before this commit.
