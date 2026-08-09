# R85-B results — is the source split neutral?

Research-only note. Not part of `editablePaths`.

Base `3217f111142346e004f41fae611a8bede172a659` (the scored-surface-move base
fb5 required). Campaign run 2026-08-08T22:54Z–23:14Z on the M4 Pro research
host. Pre-registered in `research/maple-fern-r85b-neutrality-prereg.md`, which
was written before any duplex was analysed. Every rule below was fixed in
advance; nothing here is a post-hoc choice of estimator, window, or margin.

## 0. The claim, in the form fb6 asked for

> The split is neutral to within **±7.50 µs/step** (two-sided 95 % CI,
> **cross-process ABBA adjacent-duplex, ratio-adjusted GPU-busy**, n = 8
> duplexes, **σ_d = 8.97 µs/step**), point estimate **+3.40 µs/step**
> (+0.040 % of the 8562 µs/step GPU-busy decode step). The one-sided 95 %
> upper bound — the decision statistic for a non-inferiority claim — is
> **+9.41 µs/step**.

Two qualifications that are part of the claim, not footnotes to it:

1. **δ = 5.0 µs/step is below this rig's resolvable floor**, so the campaign
   reports a *bound*, not a δ = 5 pass. §3 gives the arithmetic.
2. **The build-lottery control band is as wide as the effect band**, so per
   pre-registration §5 the honest statement is *"no source-attributable cost
   above the build-lottery floor"*, not "the split costs nothing". §4.

The load-bearing evidence for neutrality is **not** statistical. It is that the
split changes **zero command buffers** (§1) and **zero timed-path instruction
bodies** (§2). The timing campaign is a bound on what those two facts could
still be hiding, not the primary argument.

## 1. The split changes zero GPU work

`research/r85b-logs-rebased/dispatch-identity.txt`:

```
reference 01-rep1-base.err: 80794 records = 406/step x 199 steady steps
runs compared: 24, differing: 0
VERDICT: dispatch-sequence identical across all runs
```

All 24 runs across all three arms issue the **same 80,794 command buffers in
the same order with the same kernel labels**. Whatever the split did, it did
not change what the GPU is asked to do.

`cbs_per_step = 406` is **re-derived from this session**, not inherited from
PR #457, by two routes that agree
(`research/r85b-logs-rebased/cbs-per-step-derivation.txt`): the decode-step
terminator gap is 406 in 199 of 201 gaps (the two exceptions are the prefill
boundary, 1066, and the first decode step, 506), and the smallest exact period
of the tail label sequence is also 406.

**Token identity gate (pre-registration §7): PASSED.** `cksum` over all 24
`.tokens` dumps collapses to the single value `4007321606 866`
(`research/r85b-logs-rebased/token-identity.txt`), and the unscored warm-up
agrees. Zero divergence.

## 2. The split changes zero timed-path instruction bodies

`research/r85b-logs-rebased/asm-body-identity.log`, disassembling every
matching symbol in the two linked workers:

| needle | symbols | body-identical | island-only | body-different | one-side |
|---|---|---|---|---|---|
| `LagunaRuntime` (timed path) | 119 | **116** | 1 | 2 | 0 |
| `12MLXFastModel` (whole module) | 926 | **917** | 2 | 3 | 8 |

Every flagged symbol is accounted for:

* **`island-only`** — `LagunaRuntimeMLP.callAsFunction` is a genuine hot-path
  function, and its body is identical; only trailing linker-inserted branch
  padding differs. That is a linker artefact, not codegen.
* **The 2 timed-path `body-different` symbols are both `init`s**, confirmed by
  demangling: `LagunaRuntimeModelInner.init(LagunaConfig)` and
  `LagunaRuntimeDecoderLayer.init(_:layerIdx:)`. They run once at model
  construction, before the timed window opens.
* **Their delta is one instruction each**, and it is the *same* instruction
  (`research/r85b-logs-rebased/insn-diff.log`): a `mov x0, #imm` inserted
  immediately before a `bl`. That is a type-metadata request argument. In the
  base the compiler could elide it; once five declarations widen from `private`
  to `internal`, their metadata accessors move to module scope (the `…GMd` /
  `…GMR` / `…sWL` symbols the forensics note found newly emitted in the second
  object) and the request argument must be materialised explicitly. This is the
  widening showing up in codegen exactly where it should.
* **The third module-level `body-different`** is `outlined destroy of
  LagunaNativeAffineWeight`, a compiler-generated value-witness helper, which
  *shrank* 20 → 11 instructions.
* **The 8 `one-side` entries are 4 pairs, and every pair is body-identical**
  (`research/r85b-logs-rebased/one-side-pairs.txt`, produced by
  `research/maple_r85b_oneside_pairs.py`, which matches each only-in-base body
  against every only-in-cand body and exits non-zero on any orphan; it exited
  `0` — *only-in-base symbols with no body-identical partner: 0*):
  * Three pairs are one function under two manglings — base
    `<PRIV>`-discriminated, candidate undiscriminated:
    `lagunaDecodeEmbeddingRoPEAtlas` (353 insns both sides), and the `_WZ`
    once-tokens of `lagunaRouterPrecomputedKeysEnabled` and
    `lagunaTerminalPrefillFusionEnabled` (81 insns both sides). These are three
    of the five `private` → `internal` widenings losing their file-private
    discriminator — a rename, not an addition.
  * The fourth pair is **not** a rename and deserves naming precisely, because
    the obvious reading of it is wrong. Both binaries contain *both*
    constant-propagated closure specialisations of
    `makeLagunaAttentionGateProjection`, `…Tf3nnnpSi48pSi128_n` and
    `…pSi64pSi128_n`. What moves is only which one carries the extra `Tm`
    merged-function alias: base attaches it to the `Si48` variant, candidate to
    the `Si64` variant. Both bodies are 188 instructions and identical — which
    is precisely why LLVM's function-merging pass is allowed to fold them — so
    the move is that pass picking a different canonical representative out of a
    tie. No specialisation was added, removed, or re-specialised.

**Determinism control.** The same sweep on `cand` vs `cand2` — byte-identical
source, independently rebuilt with a full `base` build in between — returns
**119/119 and 926/926 body-identical, zero differences of any kind**. So the
disassembler is not simply insensitive: it resolves the split's changes and
reports genuinely nothing for a null.

## 3. Timing, and the floor that limits it

Primary instrument, ratio-adjusted GPU-busy total
(`research/r85b-logs-rebased/contrast-summary.txt`). Base level
**8562.2 µs/step** GPU-busy:

| contrast | n | est µs/step | σ_d | two-sided 95 % CI | one-sided 95 % upper |
|---|---|---|---|---|---|
| **EFFECT** cand − base | 8 | **+3.40** | 8.97 | [−4.10, +10.90] | **+9.41** |
| **LOTTERY** cand2 − cand | 8 | +2.54 | 13.24 | [−8.52, +13.62] | +11.41 |
| NULL cand2 − cand2 | 4 | −3.90 | 2.54 | [−7.93, +0.14] | −0.91 |
| NULL base − base | 3 | +6.12 | 7.08 | [−11.46, +23.73] | +18.04 |

**The resolvable floor, with the arithmetic fb5 asked for.** The smallest true
effect this design can declare non-inferior at 95 % confidence with 80 % power
is

```
delta_min(n) = (t_{0.95,n-1} + t_{0.80,n-1}) * sigma_d / sqrt(n)
delta_min(8) = (1.895 + 0.896) * 8.97 / sqrt(8)
             = 2.791 * 8.97 / 2.828
             = 8.85 us/step
```

δ = 5.0 µs/step is **below** 8.85, so this campaign **cannot** establish
non-inferiority at δ = 5. The pre-registration recorded that risk in advance
and fixed the fallback: report the bound. That bound is **+9.41 µs/step**.
Reaching δ = 5 at this σ_d needs **n = 22** duplexes: at n = 22,
`(1.721 + 0.859) × 8.97 / √22 = 4.93 < 5`, while n = 21 gives 5.06 and still
misses. The six-slot order used here yields 8 effect duplexes per 24 runs, so
n = 22 costs **≈ 66 profiled runs**. This campaign ran 24 runs in 18 min 02 s
(22:55:47 → 23:13:49, ≈ 45 s/run against reusable snapshots), so ≈ 66 runs is
**≈ 50 min**. Dropping the `cand2` lottery arm — order `base cand cand base` —
raises the yield to 2 duplexes per 4 runs, so **44 runs, ≈ 33 min**, at the
cost of losing the build-lottery reference that §5's verdict rests on.
Affordable either way, but the advisor should decide whether a tighter bound on
an already-mechanism-closed change is worth the slot.

**Why not the within-process paired design fb6 prescribed.** That design (σ =
19.5, n = 8, ±19.1 µs/step) requires toggling the treatment *inside one
process*. A source-file split cannot be toggled at runtime: the two arms are
different executables, so cross-process is the only instrument physically
available here. Worth noting that the instrument actually used is **2.5×
tighter than fb6's reference design anyway** — ±7.50 vs ±19.1 µs/step at the
same n = 8 — because ratio-adjusting the GPU-busy total against an untouched
control kernel removes most of the session drift that dominates wall clock.

**Wall clock, the pre-declared underpowered secondary**
(`research/r85b-logs-rebased/wall-clock-stats.log`): point estimate
−8.89 µs/step, 95 % CI [−101.32, +83.54], σ_d = 110.54, floor at n = 8 =
109.08 µs/step. As registered, this axis resolves nothing at δ = 5 — it would
need ~1,100 pairs. It is reported for completeness and is not evidence either
way. Note its σ_d = 110.54 exceeds the √2 × 48 = 67.9 that the advisor's
cross-process σ table implies under independence, and 67.9 sits just below the
lower limit of this session's χ² interval on σ_d, [73.09, 224.97]: **this
session was noisier than the reference table**, which is itself a reason not to
lean on wall clock.

## 4. The build lottery, and the limit it imposes (pre-registration §5)

The lottery band (one-sided upper **+11.41** µs/step, σ_d = 13.24) is **wider**
than the effect band (**+9.41**, σ_d = 8.97). The registered rule then applies
verbatim:

> If the lottery band is comparable to or larger than the effect band, then the
> honest claim is **"no source-attributable cost above the build-lottery
> floor"**, and the margin must be restated against the lottery band rather
> than against zero. I will not quote a tighter claim than that.

So: **the split carries no cost distinguishable from the cost of simply
rebuilding.** The most compact way to see this is that the effect point
estimate (+3.40 µs/step) is *smaller* than the same-binary null duplex measured
in the same session (+6.12 µs/step on `base` vs `base`). The instrument
attributes more to rebuilding nothing than it attributes to the split.

Two honest caveats on the null arms: `base`–`base` has n = 3, not the 4 the
pre-registration guessed (the order `base cand cand2 cand2 cand base` repeated
4× yields base→base adjacencies only at the 3 rep boundaries), and
`cand2`–`cand2` at n = 4 returns σ_d = 2.54, implausibly tight for 4 duplexes
and best read as a small-sample draw rather than the true noise level.

**Symmetric skepticism (§6) applied.** The wall-clock effect estimate is
negative (−8.89 µs/step, "split is faster"). Per the rule fixed in advance,
this is **not** claimed as a win. A verbatim text move with five visibility
widenings has no mechanism to accelerate decode; the negative draw is evidence
about the noise process, not about the split.

## 5. Correctness (all green on this base)

* `./benchmark.sh --local-submit`: `"passed": true`, `max_abs_diff: 0`,
  `checked_steps: 1025`, golden `f49e4c2c…`, decode-speedup floor passed. The
  prefill-floor / GPQA-TTFT / semantic-GPQA failures are pinned-M5-calibration
  artefacts on an M4 Pro host, not candidate regressions.
* 64-step drift tripwire: `passed = True`, `checked_steps = 64`, golden
  `b9509697…`.
* Upstream equivalence: 1 test executed (non-zero, per the runbook's warning
  about the empty XCTest suite); decode steps 0–7 exactly 0; the prefill
  argmax-tie artefact is digit-for-digit the documented pre-existing M4
  Pro / gen-16 divergence, unchanged by this branch.

## 6. What this does and does not license

Established:

* The per-file cap on `LagunaRuntimeModel.swift` is relieved: **510,964 B →
  398,661 B**, headroom **13,324 B → 125,627 B**, a **9.4×** increase, for
  **+275 B** of total surface growth. Measured, not subtracted —
  `research/r85b-logs-rebased/budget.txt`. Quotable form, base line from fb6 and
  candidate line from `senpai/check-editable-budget.sh 3217f111`:

  ```
  base      editable budget OK: current=2890889/3000000 headroom=109111 growth=0/262144 files=140
  candidate editable budget OK: current=2891164/3000000 headroom=108836 growth=275/262144 files=141

  Sources/MLXFastModel/LagunaRuntimeModel.swift   510,964 -> 398,661 B  (cap 524,288)
  Sources/MLXFastModel/LagunaRuntimeLayers.swift     (new) -> 112,578 B
                                                  511,239 B across the two files
  per-file headroom on the scored forward pass     13,324 -> 125,627 B
  ```

  The +275 B is fully accounted: +316 B of new-file header, −1 blank line, and
  −40 B from five `"private "` keywords deleted (5 × 8 B).
* The change is behaviour-neutral by construction, by dispatch identity, by
  instruction-body identity, and by every correctness gate.
* It carries no timing cost distinguishable from a rebuild, bounded at
  **+9.41 µs/step** (one-sided 95 %) on the ratio-adjusted GPU-busy axis.

Not established:

* Non-inferiority at δ = 5.0 µs/step. The rig's floor is 8.85 µs/step at n = 8.
* Anything about the M5. This is an M4 Pro host reporting Apple GPU generation
  16; it does not select the `_nax` prefill kernels the ranked M5 uses. The
  dispatch-identity and instruction-body results are properties of the *build*
  and carry over; the timing bound does not.
* That determinism implies neutrality. `cand2` proves the toolchain is
  reproducible, which closes "a different build rolls different code" as a
  mechanism, but a deterministic relayout can still be a slower relayout. That
  is exactly what the +9.41 µs/step bound is for.

## 7. What it unblocks, priced against the bound

fb6 §1 priced the norm→QKV thin-boundary fusion at **−52 … −55 µs/step**
end-to-end after rule 38's 40 % give-back discount. fb7 withdrew rule 38 (PR
\#473 showed the give-back is an artefact of the `DARKBLOOM_GPU_PROFILE_SPLIT=1`
instrument, which itself costs 1642 µs/step in the shipped regime), repricing
the lever undiscounted at **≈ −87 … −128 µs/step ⇒ ≈ −1.3 … −1.9 % score**.
fb6 also states that lever cannot start until per-file headroom exists, because
13,324 B does not carry a fused kernel source plus its dispatch plumbing.

The comparison that matters is therefore between the headroom this delivers and
the worst case this campaign failed to exclude:

| quantity | µs/step |
|---|---|
| lever unblocked, undiscounted (fb7) | **−87 … −128** |
| same lever under the withdrawn rule-38 discount (fb6 §1) | −52 … −55 |
| worst case still permitted by this campaign's bound | **+9.41** |
| ratio, undiscounted | **9.2 … 13.6 ×** |

Even if the split sat exactly on its one-sided upper bound — a value already
argued against by zero changed command buffers, zero changed timed-path
instruction bodies, and a same-binary null that is larger than the effect — the
lever it unblocks is an order of magnitude larger in the opposite direction.
Tightening the bound below +9.41 changes that arithmetic by at most 9 µs/step
against an 87–128 µs/step gain, which is the concrete reason §3's ≈ 50-minute
follow-up campaign is offered as optional rather than recommended. Rule 38's
withdrawal does not touch anything else in this report: no measurement here
used the split-profile instrument, and no number was discounted.

## 8. Re-check against the moved base (fb7)

fb7 moved the assignment base from `7687c2e4` to
`4dd8410f05605cb2730bc82c56f7529fd515ce97`. `Sources`, `Vendor`, and
`benchmark.json` are byte-identical between `3217f111` (the base every
measurement above was taken on) and `4dd8410f`:

```
git diff --stat 3217f111 4dd8410f -- Sources Vendor benchmark.json   # empty
```

So no measurement is rebased. The budget check re-run on the carved tree
against the **new** base reproduces the old numbers exactly, covering the
total-surface and growth-per-review limits, not only the per-file cap:

```
$ senpai/check-editable-budget.sh 4dd8410f05605cb2730bc82c56f7529fd515ce97
editable budget OK: current=2891164/3000000 bytes headroom=108836 growth=275/262144 files=141 (file count is diagnostic only; base=140)
```

Per-file: 398,661 B and 112,578 B against the 524,288 B cap, both measured with
`wc -c` on the built tree (§0), not subtracted from an estimate.

fb7's σ table adds a third form, `paired ABBA census, nat ratio-adjusted busy
= 10.65 µs/step`. That is the estimator this campaign used, and this session's
own paired `sd_d = 8.97` sits just inside it — an independent corroboration of
the published figure rather than a conflict. The reported bound uses 8.97, the
in-session value; substituting 10.65 would widen the one-sided upper bound from
+9.41 to 3.40 + 1.895 · 10.65 / √8 = **+10.53 µs/step**, which does not change
any conclusion in §6 or §7.

fb7 also asks for a *within-process* paired design. §3 records why that
instrument does not exist for this treatment: a source-file split is not
runtime-toggleable, so the two arms are necessarily different executables and
the pairing can only be cross-process. The cross-process ABBA duplex used here
achieved ±7.50 µs/step at n = 8, still 2.5× tighter than the within-process
reference half-width (±19.1) quoted in fb6.
