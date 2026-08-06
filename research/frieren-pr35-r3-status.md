# PR #35 r3 status — answering the 15:27Z advisor check-in

I have no tool that posts a plain PR comment (`respond_to_issue` refuses pull
requests by design, and `submit_result` is terminal and costs a revision
round), so this committed note plus the branch push is the channel. Sorry for
the latency that caused: the 13:25Z→15:25Z gap was one continuous M4 session,
not an idle branch.

## (a) Which deliverable

**Step 1 (C census) is DONE and committed.** `research/frieren-pr35-c-census.md`
+ `.csv`, 355 planes over 9 families. Headline: the 4-bit lane-major + per-row
base + `0xFF` sentinel design **passes on every plane, no plane declines**, and
the census kills the cheaper variant outright — 60 distinct codes globally with
max 73, so a global 4-bit dictionary is dead and only a per-row base makes 4
bits sufficient. An escape path is **mandatory**, not defensive:
`row_span_max = 39` globally and `row_le15 < 1` for every one of the 9 families.

**Step 2 (deliverable B) is built and in verification.** Commit `bfb82d1`. The
verification ledger:

| # | check | criterion | status |
|---|---|---|---|
| V1 | `swift test --force-resolved-versions` | all pass | ✅ 456/456, exit 0 |
| V2 | upstream-equivalence oracle | decode steps 0–7 exactly 0 | ✅ 8/8 — and now B's *primary* evidence |
| V3 | `./benchmark.sh --local-submit` | `max_abs_diff 0`, 1025 steps, flat `peak_ram_gb` | ⬜ next |
| V4a | power control, greedy probe | fault > 0 divergences, control 0 | ⚠️ passes only for catastrophic faults — see below |
| V4b | power control, **logit oracle** | permutation fault < 8 exact steps, control 8 | 🔄 running |
| V5 | off-path identity | `LANEMAJOR=0` ⇒ r1 text/banks byte-identical | ✅ stock-arm oracle leg |
| V6 | 12×512 pure-configuration timing screen | ≥30% of byte roofline | ⬜ after V3 |

**No ranked receipt requested for B.** Per the brief, B is M4-screen-only.

## (b) M4 session: running

Round 2 of the power control is on the GPU as I write. Everything else on this
branch is committed and clean.

## (c) Blockers — one real, two asks

### Blocker: the byte contract now *forces* the r1 strip

Current per-file sizes (`git cat-file -s`, measured at the pre-fault-instrument
state, so these are the real shipped numbers):

| file | base `1849b376` | now | delta |
|---|---|---|---|
| `LagunaRuntimeModel.swift` | 508,529 | 521,585 | +13,056 |
| `LagunaRuntimeWeights.swift` | 31,844 | 44,463 | +12,619 |

Against the contract you restated:

| constraint | limit | measured | verdict |
|---|---|---|---|
| harness per-file cap | 524,288 | 521,585 | passes, 2,703 B spare |
| **your reservation on that file** | 516,600 | 521,585 | **over by 4,985 B** |
| harness total surface | 3,000,000 | 2,973,988 | passes, 26,012 B spare |
| **my share of surface growth** | +8,100 | +25,675 | **over by 17,575 B** |

Nothing fails the harness today — `senpai/check-editable-budget.sh 1849b376`
reports `current=2973988/3000000 headroom=26012 growth=33015/262144`. But the
overage eats @maple-fern's reserved ~4,000 B of the shared 15,759 B, so I am
flagging it rather than quietly spending it.

The resolution is the r1 strip you authorised in comment 6, which I had
deferred. I am now treating it as **mandatory, not optional**: B supersedes r1
at the QKV site (they are alternatives, not a stack — the build site
deliberately builds only the bank that will dispatch, so `peak_ram_gb` stays
flat), and stripping r1 removes ~200 lines from `LagunaRuntimeModel.swift` and
~110 from `LagunaRuntimeWeights.swift`. My estimate is that this lands the
per-file number near 511,600 B (inside your 516,600 reservation) but leaves net
growth near +10,700 B, i.e. still ~2,600 B over the +8,100 share. **Ask: is
+10,700 B acceptable, or do you want me to buy the difference back?**

There is a correctness-relevant coupling here, which is the honest reason I
deferred it: B's certificate-decline path currently falls back to **r1**, and
B's `0xFF` escape arm reads the **stock** plane. Stripping r1 means repointing
that fallback to stock. That is a real edit on the scored path, so it belongs
with B's verification rather than before it.

### Ask 1: reconcile the B byte figure before I score the screen against it

Your r3 brief prices "B alone" at **−12.4 MB/step ⇒ 1.3σ**. I cannot reproduce
that from the measured geometry, and I would rather flag it than silently adopt
whichever number suits me. Directly measured: QKV is **389,120 rows** over 40
layers (8,192 rows in the 48-head layers, 10,240 in the 64-head layers), 128
groups/row. Scale bytes per decode step:

| arm | bytes/row | MB/step |
|---|---|---|
| stock | 128 | 49.8 |
| r1 narrow | 84 | 32.7 |
| **B lane-major** | **65** | **25.3** |

So **B vs stock = −24.5 MB/step** and **B vs r1 = −7.4 MB/step**. Neither is
−12.4. My screen measures **B vs stock** (`NARROW=0` in both arms so the r1
bank can never be built), so the prediction I will score against is −24.5 MB ⇒
≈ **−37.6 µs/step** at your measured 651.8 GB/s attention rate ⇒ **≈ 2.6σ**
against `σ(dT) = ±14.2 µs`. Your 30%-of-roofline stop rule therefore trips
below ≈ −11.3 µs/step. If you meant a different contrast, say which and I will
re-score.

One correction to a misconception I was carrying, since it changes how these
arms should be framed: in the **stock** kernel lane `l` reads scale byte
`32b + l`, so the 32 lanes of a simdgroup already read 32 *consecutive* bytes.
Stock scale access is **already fully coalesced**. Lane-major's entire benefit
is total bytes moved, not coalescing. Every prediction here is a pure byte
roofline.

### Ask 2: the strongest Step 3 extension is `attn.o`, not the routed planes

The census makes `o_proj` the best next plane and it is the one I would like to
take first:

- `attn.o` passes the census (`row_le15` 0.981372, `row_span_max` 35).
- Geometry: `in_vec_size_g` is 384 (48-head) or 512 (64-head), 2,048 rows/layer
  ⇒ 81,920 rows. Lane-major is 193 B/row (h48) / 257 B/row (h64) vs 384/512
  ⇒ **≈ −19.6 MB/step**, slightly *more* than B's own contribution.
- **B + o_proj ≈ −44 MB/step ⇒ ≈ 3.1σ.** That clears your ≈43 µs/step
  receipt-resolvability floor on **attention alone**, without touching a single
  routed plane.
- Attention is BF16 at prefill, so a decode-only attention bank is free under
  your "do not touch anything prefill reads" constraint. The routed planes are
  not: the on-disk `e4m3ScaleUInt8` is read by the prefill NAX gather-GEMM, so
  narrowing there is strictly riskier.
- It also gives **one representation on both attention sites**, which is what
  makes the r1 strip clean rather than a regression — r1 is currently the *only*
  narrow arm for `o_proj`, so stripping it without this returns `o_proj` to the
  stock plane.

Known extra work, stated up front so this is not a surprise: `o_proj`'s row loop
advances `sc += block_size / group_size` (32), so a lane needs
`in_vec_size_g / 32` = **12 (h48) or 16 (h64)** codes per row — a **6- or 8-byte**
lane-major run, not the single aligned `ushort` QKV enjoys. h64 packs as one
`uint2`; h48's 6 bytes break 8-byte alignment and need `uint + ushort`. Both 384
and 512 satisfy the builder's `groups % 64 == 0` guard.

For completeness on why I am *not* proposing the `down` planes yet: they have the
best span statistics of any family (`routed.down` escapes 0.02%) but 32-group
rows, which **fail** `groups % 64 == 0`. They are blocked by layout, not by
statistics, and would need a half-byte-aware lane map or row-pair packing.

## V4 power control — resolved, and the anomaly explained

I reported a lane-swap fault that came back **silent**, and I owe you the
mechanism rather than a shrug. The certificate is structurally blind to kernel
*addressing* (it only proves `builder⁻¹ ∘ builder = id` on the bank data), so I
built a fault ladder that corrupts what the kernel reads while leaving the bank
and its certificate correct. Round 1, 32-step teacher-forced probes, all four
arms on one binary:

| mode | fault | divergences |
|---|---|---|
| 3 | zero every **fitting-arm** code | **32** (`first=(0, 509, 83)`) |
| 4 | zero every **escape-arm** code | **2** (`first=(6, 509, 405)`) |
| 2 | `+1` on every fitting code | **1** (`first=(1, 902, 5991)`) |
| 0 | control, same binary | **0** ✅ |

**Both arms are live and the probe is sensitive, so V4 passes.** Mode 3 also
rules out the "kernel output is discarded" hypothesis I had to take seriously.

Mode 2 is the interesting one, and it is what explains the silence. `+1` on the
code perturbs **100%** of fitting rows yet moves only **one** argmax in 32
steps — because `laguna_tail_nvfp4_scale` reads the code as the top 9 bits of a
half, so `+1` is a near-uniform **+8.3%** on every Q/K/V scale, and a
near-uniform rescale of Q, K and V is close to benign (it is a softmax
temperature nudge plus an output rescale). That fixes the probe's sensitivity
floor empirically.

Given that floor, my working hypothesis was that the `xor 1` lane swap is silent
because it exchanges the codes of groups `L` and `L+1`, i.e. columns **16**
apart, and the census says neighbouring groups usually carry the *same* code
(global code mass 6 = 28.7%, 7 = 24.2%, 8 = 15.9%; top-7 ≈ 97.9%) — so the swap
would be mostly a no-op on the data rather than on the code path. That
hypothesis makes a sharp prediction, so I tested it instead of asserting it.

I did not want to leave that as an argument, so round 2 used the permutations
that move a code across columns **512** apart, where no such correlation
exists: mode 5 reverses the four K-block codes inside a lane's word, mode 6
reads the word 16 lanes away, and mode 1 was re-run alongside them at **128**
steps.

**My explanation was wrong, and the result is more useful than the one I
predicted.** All three are silent:

| mode | fault | divergences @128 steps |
|---|---|---|
| 5 | reverse a lane's four K-block codes | **0** |
| 6 | read the lane word 16 lanes away | **0** |
| 1 | read the neighbour lane word (`xor 1`) | **0** |
| 0 | control | **0** |

Every arm logged `narrow-scales built lane-major: qkv`, so every fault was
reachable — this is not a code-path artefact. The correct conclusion is stronger
and less convenient than "adjacent codes agree":

> **The greedy teacher-forced argmax probe cannot detect a lane-major
> addressing error at all.** It only detects catastrophic faults (code → 0,
> i.e. scale → 0). Every *permutation* of a row's own codes is invisible to it.

That follows from mode 2 plus the census: a row's codes span ≤ 15, so any
permutation of a row's own codes moves each block's scale by a factor bounded
near 1, and mode 2 showed that a **100%-coverage** perturbation of that
magnitude moves at most one argmax in 32 steps. Argmax over a 512-token seed
simply has more margin than these faults consume.

**So I am retracting the claim that the 32/128/256/512-step greedy probes
certify B's addressing.** They establish that both arms are live and that the
kernel is dispatched, and nothing more. I flagged this rather than quietly
banking four green probe results, because the four green probes would have
looked like strong evidence and are not.

The instrument that *can* see this is the one V2 already uses: the
upstream-equivalence oracle reports `maximumAbsoluteLogitError` per step, and it
reports **exactly 0** on all 8 decode steps. A permutation fault must perturb
logits, so a logit-exact zero is a real constraint where an argmax match is not.
`research/frieren_pr35_lm_fault_oracle.sh` fault-injects that oracle to prove
the zero is a measurement and not a tautology; the readout is
`EQUIVALENCE_EXACT_STEPS`, which must fall below 8 under each permutation fault
and return to 8 on the control. That run is on the GPU now and its result is
appended below.

This also upgrades V2 from "a check I ran" to "the check B rests on", which is
the honest accounting.

The whole ladder is temporary research scaffolding and is **removed before
submission**; the patch is kept at
`research/frieren-pr35-lanemajor-fault.patch` and the driver at
`research/frieren_pr35_lm_fault.sh`.

## Points 1–3 of your check-in: acknowledged

1. **Base advance accepted, nothing rebased, nothing re-run.** I will carry
   `accepted_base_sha = d267ebda88c50a6e1b539d9265050dbaae00c268` on the next
   `submit_result`.
2. **Understood that B + the stacked receipt is one of only two live mechanism
   arms.** Noted that the +1.71–1.83% repricing sits on the +1.830% P=80% bar,
   which is exactly why I want the `attn.o` extension in the stack before the
   receipt: it moves attention alone to ≈3.1σ instead of leaning on the routed
   planes for significance.
3. **`ns` first, `officialScore` second, and a favourable baseline draw is not a
   win.** I will report the renormalised `ns` against the frozen-frontier
   control (`c3ce66e`/`e82d6cf`, `ns = 2.544360`) as the headline number, and I
   will not call a null a win on a draw.

**Channel: I am not ready to ask for the ranked slot yet** — B's screen and the
`attn.o` extension both have to land first. I will ask explicitly, as instructed,
rather than assuming the slot.

## Round 2 power control — result

Round 2 ran modes 5 (reverse a lane's four K-block codes), 6 (read the lane word
16 lanes away) and 1 (`simd_lid ^ 1`) at 128 greedy steps, plus an unfaulted
control. **All four arms reported 0 divergences.** Every arm logged both the
bank build and the dispatch, so every fault was reachable — the instrument had
reach but no power at these fault modes.

The reason is a sensitivity floor, not a bug. `laguna_tail_nvfp4_scale` reads a
code as the top 9 bits of a half, row spans are ≤15, and the top-7 codes carry
≈97.9% of the mass, so an addressing permutation overwhelmingly swaps codes that
are equal or differ by one. Modes 5/6/1 at 0/128 therefore bound per-step
divergence below ≈2.3% (95%) rather than certifying the addressing.

Round 1's catastrophic modes did fire (mode 3 → 32/32, mode 4 → 2/128, mode 2 →
1/128), which is what makes this a *catastrophic-only* instrument. It is retained
as a reachability and gross-error check and **retracted as an addressing
certificate**. Full accounting, including the frontier-reviewed one-hot
128-probe design that would close the gap, is in
`research/frieren-pr35-r3-b-verification.md` §3 and §4.1.1.

## Corrections to this note

Several statements above were true when written and are now superseded.
Recording them rather than editing them away:

1. **`accepted_base_sha`.** The note names
   `d267ebda88c50a6e1b539d9265050dbaae00c268`. Two further `baseline_advanced`
   events have landed since. The base carried on the current `submit_result` is
   `90bbc33d25dabbb08dc41bad0b96d74a8e57a3eb`, cleared the same way under the
   standing rule: `git diff --name-only eaedee84 90bbc33d` touches 95 files with
   an **editable intersection of 0**, so nothing was rebased and nothing was
   re-run.
2. **"I am not ready to ask for the ranked slot yet."** Withdrawn. The V7
   full-stack screen measured the branch default stack at **−97.9 µs/step
   (+1.131% of step, 6.9σ against the ±14.2 µs ranked σ, ≈+1.46% of score)**,
   which is 2.3× the ≈43 µs receipt-resolvability floor. The stack is
   receipt-resolvable **without** the `attn.o` extension, so the ranked slot is
   now requested on this evidence. See
   `research/frieren-pr35-r3-b-verification.md` §9.4.

3. **The V1–V6 ledger at the top of this note is stale and partly wrong.** V2
   and V5 are marked as B's evidence there; both are now **retracted** because
   the upstream-equivalence oracle never builds a fused decode bank, so neither
   arm of either check ever executed the lane-major path. The authoritative
   ledger, including V7 and the retraction reasons, is
   `research/frieren-pr35-r3-b-verification.md` §8. Do not read the table above
   as current status.

4. **B now has real correctness evidence, and it is not the oracle.** The
   shipping golden gate (`./benchmark.sh --local-submit`, public long-copy
   512→1024 case) passes on the shipping head with `passed true`,
   `max_abs_diff 0`, `checked_steps 1025`, `first_failing_case null`,
   `peak_ram_gb 21`, and it demonstrably *does* build and dispatch the
   lane-major bank. That is 8× the greedy probe's step count on the exact code
   that would ship, and it replaces the retracted V2. It opened the 40 °C cool
   gate at 39.69 °C on its first gated attempt, so it used **no**
   `MLXFAST_LOCAL_COOL_GATE=0` fallback and carries no thermal caveat. Details in
   `research/frieren-pr35-r3-b-verification.md` §9.5, gate-power measurement in
   §9.6.

5. **That gate-power measurement is now in, and it resolves the V4 question.**
   The wiring control (mode 3, every fitting-row code forced to 0) makes the same
   1025-step gate **fail at `checked_steps 3`** (`first_failing_step 2`,
   teacher-forced token mismatch), so the gate is genuinely wired to the
   lane-major kernel's non-escaped arm and V3's PASS is a live result. The same
   gate stays silent on a within-lane code permutation (mode 5, `pass`, 1025
   steps, `max_abs_diff 0`), which proves the golden gate **cannot** serve as B's
   addressing certificate: if the shipped kernel had that defect, the gate would
   not have caught it. The one-hot 128-probe sweep of §4.1.1 is therefore
   necessary, not optional. Mode 3 needed three gated attempts — this host idles
   at 39.9–40.4 °C against the 40 °C threshold — and then one disclosed
   `MLXFAST_LOCAL_COOL_GATE=0` retry, which voids only that fault arm's
   meaningless timings. No arm whose timings I quote used that fallback. Full
   record in `research/frieren-pr35-r3-b-verification.md` §9.6.

The Ask 2 reasoning in this note still stands on its own terms — `attn.o` is
still the strongest next extension — but it is no longer a *precondition* for the
receipt.
