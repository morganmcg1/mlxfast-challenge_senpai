# R107-F — T2d routed+shared down+residual: output-row amortisation

**Student** maple-frieren · **PR** #597 · **revision** `r105-b-rev6` ·
**base** `2454cc01ea3afabac067f0a271e36901fea7d21c` · **host** AWS M4 Pro,
Apple GPU generation 16, 20 cores, measured DRAM ceiling 260.2 GB/s.

Every M5 figure quoted from the state-doc pool table (§B.0.3, lines 1685–1705)
carries its mandatory provenance label verbatim:
**`α = 0.4369, β = 0.5 two-pool map, residual −6.63 %, #561`**.

---

## §0 Outcome

**`PENDING`** — filled at the end of Stage 1 or Stage 2. The permitted vocabulary
is fixed in §2.7 below and may not be extended after the fact.

---

## §1 Stage-0 receipt (rev6 §1) — DONE

My branch head `95a0ef9e` carried a replay of the `4b0e051b` editable surface
(32 files diverging from the advisor tip). Left in place it would have swapped
the integration tree under the advisor. Stripped with the Rule 95.6 recipe:

```sh
PATHS=$(jq -r '.editablePaths[]' benchmark.json)          # 97 paths
git rm -r -q --ignore-unmatch -- $PATHS
git checkout 2454cc01ea3afabac067f0a271e36901fea7d21c -- $PATHS
git add -A && git commit -m "strip r106e replay: restore advisor-tip editable surface"
```

Result commit **`87d7d13da74596b040de06f2168a42fce4ed480e`**. Both mandated
commands print **nothing**:

```
$ git diff --numstat 2454cc01ea3afabac067f0a271e36901fea7d21c HEAD -- $PATHS
$ git status --porcelain=v1 --untracked-files=all -- $PATHS
```

`git status --porcelain=v1` over the whole tree is also empty. All `research/`
files survive: `research/` is outside `editablePaths` and outside
`harnessHash()`, so preserving it cannot move the integration tree. #597 is
mergeable on the advisor tip.

---

## §2 Preregistration

Written **before any timing run**. Nothing below is retrofitted; the Stage-1
and Stage-2 sections are appended after this section, not woven into it.

### §2.1 The pot, and both Rule 81 reference rates

| rank | family | calls | M4 µs | M5 µs | regime | % M5 peak | headroom µs | % score |
|---|---|---:|---:|---:|---|---:|---:|---:|
| 4 | T2d routed+shared down+residual | 39 | 858.9 | 375.3 | bytes | 85.3 | 55.1 | **0.84** |

`α = 0.4369, β = 0.5 two-pool map, residual −6.63 %, #561`.

Byte census (`research/artifacts/fern-r105d/decode-byte-census.json`):
195,526,656 B/step = **11.6984 % of `B`**, 5,013,504 B/call × 39 calls,
unique-byte floor 320.536 µs = 4.881 % of the step.

Rule 81 clause (b) needs the achieved rate ≥10 pp below a same-access-pattern
family's best rate on the same host. **Both reference rates, side by side, and
I do not get to pick:**

- against **`lmhead`** at 97.4 % of peak: 12.1 pp, implied gain **46.4 µs/step** — clause (b) **passes**;
- against **`dense_down`** at 94.0 % of peak (the fairer comparator, a plain NVFP4 QMV): 8.7 pp, implied gain **34.6 µs/step** — clause (b) **fails**.

Clause (c) (≥30 µs/step) holds on both. The honest sentence: *T2d is licensed
under the lmhead reference (46.4 µs, 12.1 pp) and marginal under the dense_down
reference (34.6 µs, 8.7 pp); both are reported.*

### §2.2 My own in-situ baseline for this kernel

R106-J §3.3 invariant control, measured on this host with the per-kernel GPU
profile split: `routed_shared_nvfp4_down_residual` = **22.0637 µs/call**,
sd across blocks 0.1068, n = 3 blocks. × 39 calls = **860.48 µs/step**, against
the pool table's 858.9 — a 0.18 % agreement between two independent
instruments. This is the only decode byte family where a student already holds
a contemporaneous in-situ per-call number, and it is the A0 anchor.

Derived M4 rates (mine, not the two-pool map's):

- achieved 5,013,504 B / 22.0637 µs = **227.15 GB/s**;
- 87.30 % of this host's measured 260.2 GB/s stream ceiling;
- 87.04 % of 105-E's *pattern-specific* ceiling (a faithful nvfp4_qmv replica at 260.97 GB/s);
- M4 headroom to the pattern ceiling = 22.0637 × (1 − 0.8704) = 2.859 µs/call = **111.5 µs/step**.

At the campaign decode price (0.015228 % of `cs` per locally measured µs/step,
the same price under which #308's −36.9 µs/step was booked as +0.562 % of `cs`),
the **bar of 0.4 % of `cs` is 26.27 µs/step**, i.e. I must capture **23.6 % of
the measured M4 headroom**. That is the honest framing of the target.

### §2.3 §6.4 arithmetic, re-derived from the source on this host

Read at `2454cc01` from `Sources/MLXFastModel/LagunaRuntimeModel.swift`
(`lagunaRoutedSharedDownResidualSource`, `:8277`; launch wrapper `:8578`).
Emitted constants: `input_width = 512`, `output_width = 2048`,
`routed_experts = 8`, `shared_slot = 8`, `outputs_per_simd = 4`,
`values_per_lane = 16`, `packed_row_bytes = 256`, `scale_patch_bytes = 128`,
`routed_scale_row_bytes = 16`, `shared_scale_row_bytes = 16 (halved) | 32`.
Launch `grid = (2048/4 × 288, 1, 1)`, `threadGroup = (288, 1, 1)` ⇒ **512
threadgroups × 9 simdgroups × 32 lanes = 147,456 threads**, tile count 512.

Per lane, per call, from the emitted body:

| load | count | width | bytes | source line |
|---|---:|---:|---:|---|
| activation `vec<bfloat,4>` from `expert_input + lane*16` | 4 | 8 B | **32** | `input_vectors[i]` loop |
| weight codes `uint2` at `output_row*256 + lane*8` | 4 | 8 B | **32** | `row_codes[row]` |
| scale `uint8_t` at `output_row*scale_row_bytes + scale_lane` | 4 | 1 B | **4** | `row_sb[row]` |
| **total** | **12** | | **68** | |

32/68 = **47.06 % of issued bytes is the re-read activation** ✓ — §6.4's figure
reproduced exactly.

Replay factors, per call:

| stream | unique B | issued B | replay |
|---|---:|---:|---:|
| weight codes | 4,718,592 | 4,718,592 | 1.000× (every lane byte distinct) |
| scales | 294,912 | 589,824 | 2× (`lane>>1`: lane pairs share a byte) |
| activation | 9,216 | 4,718,592 | **512×** (once per tile) |
| residual + output | 8,192 | 8,192 | 1× |

Unique DRAM read = 4,718,592 + 294,912 + 9,216 = **5,022,720 B**, of which the
census's scored 5,013,504 B is the weight+scale part (9 × 4 × 256 = 9,216 B and
9 × 4 × 16 = 576 B per threadgroup, × 512 = 4,718,592 + 294,912 = **5,013,504 B
✓**). Total issued = **10,027,008 B/call**, a 2.000× issue/unique ratio.

**Byte identity independently pins the shipped variant.** 576 scale B per
threadgroup requires `shared_scale_row_bytes = 16`, i.e. the **halved** shared
scale plane; the unhalved variant would give 8 × 4 × 16 + 1 × 4 × 32 = 640 B
per threadgroup and 5,046,272 B/call, which is *not* the census figure. With
`DARKBLOOM_SHARED_FIRST_DOWN` unset (default, `:8218`) and
`DARKBLOOM_FUSED_DOWN_ROW_STAGING` unset (default ON, `:8226`), the resolved
pipeline is therefore predicted to be
**`laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6`**. Stage 0
confirms this on the device rather than by inference.

### §2.4 What actually amortises at `outputs_per_simd = 8` — a correction to §6.4

§6.4 says "per-row metadata **and** activation loads are amortised over only 4
output rows". Re-deriving from the source, that is half right and I will not
carry the error forward: the scale byte is indexed by `output_row`, so scale
loads scale **1:1 with rows and do not amortise at all**. Only the activation
load, the `indices[slot]` load, the pointer setup, and the threadgroup barrier
amortise.

| quantity per call | A0 (`opsi=4`, 512 TG) | A1 (`opsi=8`, 256 TG) | change |
|---|---:|---:|---:|
| threadgroups | 512 | 256 | −50 % |
| total threads | 147,456 | 73,728 | −50 % |
| load instructions per lane | 12 | 20 | +67 % |
| **load instructions per call** | 1,769,472 | 1,474,560 | **−16.67 %** |
| issued activation B | 4,718,592 | 2,359,296 | −50 % |
| issued scale B | 589,824 | 589,824 | 0 % |
| issued weight B | 4,718,592 | 4,718,592 | 0 % |
| **issued B per call** | 10,027,008 | 7,667,712 | **−23.53 %** |
| issued B per unique weight B | 2.125 | 1.625 | −23.53 % |
| unique DRAM B | 5,022,720 | 5,022,720 | **0 %** |
| `threadgroup down_outputs` | 72 B | 144 B | +72 B |
| live thread state (`row_codes`+`row_sb`+`result`) | 4×2 + 4×1 + 4 regs | 8×2 + 8×1 + 8 regs | ~2× |

So the sharpened hypothesis I am actually testing is:

> **H-T2D-AMORT′** — T2d's 12.7 pp shortfall against its pattern ceiling is
> paid in *load-issue slots spent replaying an SLC-resident activation row*,
> and halving that replay (512× → 256×) converts into wall-clock. The scale
> stream does not amortise; the ceiling on this lever is therefore the
> activation-replay component alone.

### §2.5 The adverse prior, confronted before anything is built

State doc §5e (105-E) priced exactly this replay: driving *issued* bandwidth to
752 GB/s by replaying a 4 KB activation per simdgroup cost **0.45 µs out of
4371 = 0.010 %**. Scaled to 39 dispatches that is **17.6 µs/step = 0.27 % of
`cs`** — the whole lever, at its ceiling, lands **below the 0.4 % bar**. 105-E
also showed 64-thread threadgroups are not a bandwidth handicap
(`stream_tg64` at 99.1 % of stream peak) and closed
bandwidth-efficiency-at-fixed-bytes as a family with a ≤1.548 % ceiling.

I accept that prior as stated and record its consequences honestly:

1. **The lever must be argued as an issue/amortisation effect, not a
   bandwidth-efficiency effect.** 105-E measured the marginal cost of *bytes
   that are already resident*. A1 does not change resident bytes; it changes
   the **number of load instructions issued per unique DRAM byte** (2.125 →
   1.625) and the **number of threadgroups** (512 → 256). If the limiter is a
   per-load issue slot or a per-threadgroup launch/barrier cost, 105-E's
   marginal-byte price says nothing about it.
2. **The prior is nevertheless adverse by 1.49×.** Bar 26.27 µs/step ÷ prior
   ceiling 17.6 µs/step = 1.49. For a `V-T2D-AMORT` outcome the 105-E price
   must be wrong by at least half again in the direction that favours me. I put
   the prior probability of clearing the bar at **≈15 %**, and the probability
   of a *measurable but sub-bar* effect (`N-T2D-AMORT`) at ≈35 %.
3. **Therefore Stage 1 is the deliverable, not a formality.** The most likely
   honest outcome of this assignment is a null that retires 11.7 % of decode
   bytes from the live list, and I am preregistering that as a success rather
   than something to be avoided.
4. The one piece of same-class positive evidence is **#308**: raising
   `num_simdgroups` 2 → 8 on the QKV lane-major kernel measured **−36.9 µs/step,
   CI [−61.0, −12.9] = +0.562 % of `cs`, CI [+0.196 %, +0.929 %]**. It is real,
   measured, on this host, and it is the reason the 15 % is not 2 %.

### §2.6 Arms

Stage 2 runs only if Stage 1 supports it (§2.8). All three arms are bit-exact
by construction — per-row k-traversal, FMA order within a row, and `simd_sum`
are untouched; only *which simdgroup computes which output row* changes — and
that is **proved, not assumed**, with `logit_delta == 0` on the full golden set.

| id | `outputs_per_simd` | threads/TG | TGs | grid | role |
|---|---:|---:|---:|---|---|
| **A0** | 4 | 288 (9 sg) | 512 | `2048/4 × 288` | shipped baseline |
| **A1** | 8 | 288 (9 sg) | 256 | `2048/8 × 288` | 2× activation-replay amortisation |
| **A2** | 4 | 576 (18 sg) | 256 | `2048/8 × 576` | **negative control** |

**A2 is the discriminator.** It packs two `opsi=4` tiles into one threadgroup:
`slot = sg % 9`, `subtile = sg / 9`, `first_row = (tile*2 + subtile) * 4`,
`down_outputs[18*4]`, and the epilogue runs on `sg % 9 == 0` so both subtiles
reduce independently. A2 therefore has **exactly A0's load count, A0's issued
bytes and A0's per-lane work**, but A1's threadgroup count. If A1 wins and A2
does not, the mechanism is activation-replay amortisation. If both move
together, the mechanism is threadgroup count / launch / barrier cost and
H-T2D-AMORT′ is refuted in favour of `V-T2D-TGSHAPE`.

Mechanics that are mandatory for every arm:

- **distinct pipeline names** (`…_sh_stage4_v6_a1`, `…_sh_stage4_v6_a2`) so
  Metal cannot serve a cached sibling pipeline;
- all four kernel objects updated coherently
  (`{staged, unstaged} × {sharedHalved, not}`), because `sharedHalved` is
  inferred at run time from `sharedDownScales.ndim == 1` and the staged
  default can be flipped by env;
- a **spill check** in the Stage-0 reflection. A1 doubles `row_codes[]`,
  `row_sb[]` and `result[]`. **If a spill appears I stop and report it rather
  than reporting a contaminated number.**

### §2.7 Acceptance, null cell, and outcome vocabulary

Acceptance for a `V-` outcome, all of which must hold:

1. in-situ paired ABBA under `./benchmark.sh --local-iterate`, **≥8 pairs**,
   order reversed every round, GPU-dispatch timestamps plus a wall-clock twin
   (Rule 86: a bare `--local-iterate` score delta is never evidence);
2. decode **and** prefill both reported — the kernel is decode-only but both
   score floors are 0.95;
3. mean decode delta ≤ −26.27 µs/step with a CI excluding zero;
4. `logit_delta == 0` on the full golden set; force-clean build (#575);
   `research/run_upstream_equivalence.sh` green on the exact tree;
5. no spill in the pipeline reflection;
6. Rule 98.9: no cache-resident kernel-local number is a headline; every
   probe number is reported beside its residency-defeated twin, and the
   headline is the in-situ wall clock.

**Null cell (preregistered):** A0-vs-A0. The same ABBA driver, same pair count,
with the "candidate" arm being a semantically inert rename of the shipped
pipeline (`…_sh_stage4_v6_null`). Its measured delta and CI are the noise floor
against which A1 and A2 are read. Without it a 26 µs/step claim on this host is
not interpretable.

**Preregistered revert:** `git checkout 2454cc01 -- Sources/MLXFastModel/LagunaRuntimeModel.swift`.

Outcome vocabulary — exactly one is named in §0:

- **`V-T2D-AMORT`** — A1 wins in situ, A2 does not, gain ≥ 0.4 % of `cs`.
- **`N-T2D-AMORT`** — amortisation measurable but below the bar; point estimate and CI given.
- **`V-T2D-TGSHAPE`** — A1 and A2 move together; effect is threadgroup shape; H-T2D-AMORT′ refuted, the exposed lever priced.
- **`N-T2D-ISSUE-BOUND`** — Stage 1 refutes the premise. **A success**: it retires 11.7 % of decode bytes and bears directly on the §B.0.6 α/β degeneracy (α ≈ 0.389 ⇒ efficiency work pays; α ≈ 0.437 ⇒ only bytes pay).
- **`N-T2D-ROOFLINE`** — the family is genuinely at its achievable roofline; 85.3 % is an artefact of the two-pool map.
- **`N-CORRECT`** / **`N-BUILD`** — a `logit_delta` failure or a spill; which, and why.

### §2.8 Stopping rule

Stage 1 fits **`T = B/BW + L`** with uncertainties on a residency-defeated
standalone replica of this exact access shape, and runs an **AIR load census**
of the shipped kernel classifying loads by buffer. Per rev6 §6.6 I do **not**
report "% of peak bandwidth" as the regime statistic (state-doc rule (i): it is
confounded by fixed cost).

**If `L` is small, or the load census does not match §2.3, I declare
`N-T2D-ISSUE-BOUND`, write it up, and stop.** Additionally — and this is my own
added gate, because the replica is cheap and the runtime edit is not — the
replica must show an A1-vs-A0 improvement whose extrapolation to 39 calls
reaches at least the 17.6 µs/step adverse-prior ceiling. A replica that cannot
find the effect with the confound removed will not find it in situ.

---

## §3 Stage 0 — reachability, geometry, digests

_Appended after §2 was committed. See `research/artifacts/maple-frieren-r107f/`._

---

## §6 Deconfliction (rev6 §6.7) — reproduced and honoured

| owner | PR | region I do not touch |
|---|---|---|
| maple-edward | #629 | `lagunaDecodeNVFP4QKVLaneMajorSource` (`:4922`), `lagunaRoutedSwiGLUQMVPackedTop8` (`:8030`) |
| maple-alphonse | #644 | `lagunaGatedAffineOProjNVFP4Source` (`:4222`), `lagunaGatedAffineOProjNVFP4` (`:4586`) |
| maple-tanjiro | #642 | `laguna_sliding_fused_attn_ring_v1` (`:1508`), `laguna_full_fused_attn_grow_v1` (`:2028`) |
| maple-fern | #625 | integration — I hand to him |
| maple-nezuko | #616 | revert residual forensics |

My whole diff is confined to `lagunaRoutedSharedDownResidualSource` (`:8277`),
its four kernel-object name strings (`:8225-8276`, `:8429-8430`, `:8558-8559`)
and the `grid:`/`threadGroup:` line of `lagunaRoutedSharedDownResidual`
(`:8578`+68) — a byte range that contains none of the five regions above.

**Why alphonse's #644 and my R107-F cannot collide:** they edit different MSL
generator functions (`lagunaGatedAffineOProjNVFP4Source` vs
`lagunaRoutedSharedDownResidualSource`) which build different pipelines from
different weight tensors (`o_proj` vs routed/shared `down_proj`) and are
launched from different dispatch wrappers with different grids, so neither
edit can change a line, pipeline, buffer or launch the other touches. He is
running the same *class* of change (output-row amortisation) on oproj: if his
G1 arm wins, my prior rises — I note that and do not wait for him.

---

## §10 Housekeeping the advisor asked for

### §10.1 The tree-swap question is closed by my own measurement

`4b0e051b` 3-replicate mean official score **2.582463** vs `bd33883e`
**2.582286** ⇒ **+0.007 %**, entirely inside the campaign σ of
`sd(ln cs) | fixed tree = 0.3607 %`. Two trees separated by 0.007 % when the
instrument's own noise is 0.36 % are indistinguishable, so there is no evidence
for swapping the integration base. We hold **`bd33883e` + 1 file**. I withdraw
the tree-swap proposal and I am not asking for it again.

### §10.2 Acceptance of the #615 nibble-delta ruling

I accept the ruling and will not re-open it. The decisive number is mine: after
subtracting what the strided-aliased `_nax` prefill views
(`LagunaRuntimeWeights.swift:998-1039`), the 16-byte packed-bank granularity
and the 128-entry `lagunaScalePatchHeaderBytes` make unreachable, the remainder
worth **+0.158 % of `cs`** — under half the ship bar — and buying it costs
+337 MB of double residency on a 128 GB box that already holds a 21.6 GB tower.
Counter-evidence #85 and #513/#525 point the same way. A lever whose *entire
reachable* upside is 0.4× the bar is not a lever; it is a footnote, and it now
reads as one.
