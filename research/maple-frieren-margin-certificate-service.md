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
4. **Cost:** 4 captures + 2 certifies ≈ **5 min** of machine time (§6, measured).
   The candidate **rebuild** dominates at **131 s** force-clean (+50 s if the
   metallib was deleted — see §9 trap 1). Nothing about this is expensive; the
   reason it has not been done for every shelf row is that nobody had the
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

### §5.1 Null cell — run this FIRST, always (rule 79)

Two captures of the *same* arm. The only admissible verdict is
`PASS-BIT-EXACT`. Anything else means the host is not reproducible and every
subsequent number is noise.

```bash
python3 $S capture --label null_a --mode teacher --steps 64 --out /tmp/cert/a.npz
python3 $S capture --label null_b --mode teacher --steps 64 --out /tmp/cert/b.npz
python3 $S certify --baseline /tmp/cert/a.npz --candidate /tmp/cert/b.npz \
        --out research/artifacts/<you>/cert_null.json
```

`research/maple_frieren_r107f_sop_dress_rehearsal.sh` is exactly this, timed,
with the provenance header; run it verbatim if you want the null cell and the
SLA in one go.

### §5.2 Teacher-forced certificate (emulates the visible gate)

```bash
# arm A — baseline binary
python3 $S capture --label baseline --mode teacher --steps 64 --out /tmp/cert/base_t.npz
# arm B — candidate binary (rebuild between the two captures; the .npz is on disk
#          precisely so the arms need NOT be the same build)
python3 $S capture --label candidate --mode teacher --steps 64 --out /tmp/cert/cand_t.npz
python3 $S certify --baseline /tmp/cert/base_t.npz --candidate /tmp/cert/cand_t.npz \
        --out research/artifacts/<you>/cert_teacher.json
```

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

**End-to-end request → verdict, assuming I must build your arm:**

| step | time |
|---|---|
| fetch + read the patch, assign class | 5–10 min (human/agent-bounded) |
| force-clean candidate build | **131 s** (measured, R106-J §3.2.1a; `+50 s` if metallib missing) |
| null cell (§5.1) | **99 s** (skippable if run in the same session) |
| teacher pair (§5.2) | ≈**100 s** (2 × 50 s + certify) |
| free pair (§5.3) | ≈**155 s** (2 × 75 s + certify) |
| write-up with class, safety factor, limits | 10–15 min |
| **total** | **≈25–35 min**, of which <8 min is machine |

If you already provide a built candidate binary, subtract the build.
**Deadline reality:** requests arriving after ≈**04:00Z on 2026-08-11** cannot
include a rebuild and still clear the 06:00Z handoff to fern (#625) / 07:00Z
integration freeze. Send the patch early, not the finished argument.

---

## §7. Output contract

### Verdicts (`verdict` in the JSON; `verdict_reasons` always explains)

| verdict | meaning | what it licenses |
|---|---|---|
| `PASS-BIT-EXACT` | arms bitwise identical over the full vocabulary at every certified position | class 0. Ship on the token gate alone. |
| `PASS-WITH-MARGIN` | zero token flips **and** global safety factor ≥ 10 | the strongest statement this instrument makes |
| `MARGINAL` | zero token flips but global safety factor < 10, and/or positions whose own margin is under 10× their own perturbation, and/or exact ties | a priced risk, not a refusal (§1) |
| `FAIL` | a token flipped (recomputed argmax **or** the token the worker returned) | terminal. Exit code 4. |
| `VOID` | recomputed argmax disagrees with the worker's returned token | the capture is untrustworthy; fix the harness, do not interpret the numbers |

### Exit codes

`0` certificate produced (may still be `FAIL`/`MARGINAL`) · `2` worker binary
or golden fixture missing · `3` protocol/consistency error, certificate not
trustworthy · `4` token flip found.

### JSON sections

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
3. **Both captures must come from the intended binaries.** The certificate
   records `worker_sha256` per arm — *check that the two differ* when you
   expect them to. Two identical hashes with a `MARGINAL` verdict is a bug in
   your driver, not a finding.
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

Nothing in §5 needs me. The instrument, the fixture, the driver script and this
document are all in the tree. The only judgement calls are (a) assigning the
class from the diff, which §3 reduces to "does any lane sum over different
*values*, or only in a different *order*?", and (b) deciding what a `MARGINAL`
verdict is worth, which is an integration decision and was never mine.
