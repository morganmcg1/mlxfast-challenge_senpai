# PR #22 — `Sources/MLXFastTransform/`: the axis is zero-attempt because it is *dominated*, not because it is unexplored

SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":false,"value":null},"test_metric":{"name":"passed_correctness","available":false,"value":null}}

- Student / PR: maple-fern / #22
- Hypothesis and target cost: interleaving NVFP4 g16 codes with their E4M3 group
  scales in the offline transform removes real DRAM traffic from the ~150 MB/token
  scale stream, bit-exactly.
- Decision: **dead hypothesis.** The mechanism has nothing to remove, and the
  layer is the wrong one. Closed on Part 0 + Part 1 with **0 official
  submissions and 0 benchmark host-hours spent.**
- `BASE_SHA` / candidate commit: `aecc470edecf01cbf9cb708bdc5ad69b90c73754` /
  no runtime change proposed (documentation only).
- Submitted candidate files: **none.** No `editablePaths` file is modified.
- Supporting files: this report.

## Part 0 — the contract kill check says GREEN. That is the one durable positive.

You asked whether the official pipeline accepts a changed transform output at
all. **It does.** This is a reusable capability the campaign did not know it had,
so I am recording it precisely even though my own arm does not need it.

1. **The official run executes our transform.** `benchmark.yml:1074-1113` runs
   `.build/release/mlxfast-swift transform --reference "${MLXFAST_REFERENCE_DIR}"
   --output weights` from the submission-built binary, on the submission branch
   (`:1089-1101`). The only post-condition asserted inline is
   `test -f "${MLXFAST_JOB_WS}/weights/config.json"` (`:1115`).

2. **`weights_hash` is an emitted-artifact hash, and it is not pinned.**
   `hash-weights-directory.sh` runs *after* the transform (`benchmark.yml:1122`)
   and its own header says it exists so "the gates run's reported weights hash is
   cross-checked against it before any score is trusted." Every comparison is
   same-session TOCTOU only:
   - `benchmark.yml:1573` "transformed weights changed between trusted hashing
     and the gates run"; `:1686` "...changed before timing".
   - `overlay-paired-timing.sh:101` `.metrics.weights_hash == $gates[0].metrics.weights_hash`.
   - `validate-benchmark-artifacts.sh:309` `$score[0].metrics.weights_hash == $integrity[0].weights_sha256`.

   No trusted file contains a pinned 64-hex weights constant. The observed
   `aff9943...` appears only in our own `research/` artifacts and
   `score.local-iterate.json`. nezuko's three receipts report it "unchanged"
   simply because none of those three changed the transform.

3. **`weights_file_count` / `weights_byte_count` are `> 0` plus same-session
   equality only** (`overlay-paired-timing.sh:98,100,102-103`;
   `validate-benchmark-artifacts.sh:205,207,310-311`). There is no `== 9` and no
   `== 21568891382`.

4. **`MLXFAST_VERIFY_TRANSFORM` is determinism-only and defaults false**
   (`benchmark.yml:105` `default: false`, wired at `:267`).
   `MLXFastTrustedHarness/TransformVerification.swift:79-81` re-runs *our own*
   `SwiftTransform.run` into a temp dir and diffs its two outputs (`:127` path
   sets, `:139` sizes/contents). It never compares against the reference
   checkpoint or a layout expectation.

5. **No trusted check requires the output to be a copy of the reference.** The
   only manifest check is on the *input* (`benchmark.yml:510,518-521`). Trusted
   code requires just two paths to exist — `weights/config.json` and
   `weights/model.safetensors.index.json`
   (`Sources/MLXFastTrustedHarness/BenchmarkSupport.swift:105-106`).

**Answering your reconciliation question:** `AGENTS.md` lists *generated-weight
files* under "What Not To Change" (the checked-in artifacts) while listing
`Sources/MLXFastTransform/` as editable (the code that generates them). Those are
consistent: we may change the generator, not the checked-in generated files.

**Constraints if anyone ever needs this:** keep `config.json` +
`model.safetensors.index.json`; all entries regular non-symlink files with link
count 1 (`hash-weights-directory.sh:25,34`); total ≤ 25 GiB
(`Sources/MLXFastCore/Constants.swift:176`
`defaultMaxTransformedWeightsBytes`, vs 21.57 GB today); keep the transform
bit-deterministic in case `verify_transform` is ever dispatched.

One caveat I did **not** need to test: `Safetensors.validateSourceIdentity`
(`Sources/MLXFastCore/Safetensors.swift:184`) is *trusted* code —
`MLXFastCore` has zero entries in `editablePaths` — but it is *invoked* from our
editable `Transform.swift:313`. A layout change would mean our own file stops
calling a trusted byte-identity helper. Legal, but it removes a safety net.

So the contract did not kill this arm. Three structural facts did.

## Part 1 — I did not need tanjiro's probe. The amplification is exactly 1.0, provable from the addressing.

Your premise was: "if a threadgroup pulls a 128 B cache line to use 16 B of
scales, that stream is amplified up to 8x." **In this codebase every NVFP4 scale
read is already 100% cache-line dense.**

`laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5`, the current frontier's
down/residual kernel (`LagunaRuntimeModel.swift:7658-7705`):

```
constexpr uint outputs_per_simd = 4;      // :7660
constexpr uint scale_row_bytes  = 32;     // :7663
uint first_row = tile * outputs_per_simd; // :7672
const device uint8_t* scale =
    expert_scales + output_row * scale_row_bytes + lane;  // :7704-7705
```

One simdgroup covers `row ∈ [0,4)` and `lane ∈ [0,32)`, so its scale bytes are
exactly `[128·tile, 128·tile + 128)`: **one aligned 128 B cache line, all 128
bytes consumed.** Codes are likewise `output_row * 256 + lane * 8` = 1024
contiguous bytes, fully consumed. Amplification **A = 1.000** on both streams.

An independent check that does not rely on reading the addressing at all. The
base tree measured this kernel at **231 GB/s achieved against a 260.2 GB/s
streaming ceiling** (88.8%), computed on *logical* bytes of 1024 B codes + 128 B
scales = 1152 B. If scales were amplified ×A while codes stayed dense:

```
231 × (1024 + 128A)/1152 ≤ 260.2   ⇒   A ≤ 2.14
```

So the 8x premise was already arithmetically impossible from a number we had
before this arm started. The addressing then tightens it to exactly 1.0.

**For tanjiro (#21), as coordinated:** your Part 1 **case (2) vs case (3) is
answered negatively from source — please do not spend probe effort on it.**
Separate-buffer scale reads are already cache-line dense, so interleaving is
byte-neutral by construction. More usefully: since A = 1.0, **your 1.88 ms
residual cannot be scale amplification.** It has to be latency, gather
behaviour, or an unreachable ceiling for this access mix, so cases (4) gathered
1.77 MB expert blocks and (5) ring-buffer KV are where the remaining explanatory
power is.

## The three structural kills

### 1. 59% of the premised surface has no NVFP4 bytes on disk

Attention `q/k/v/o` and per-head `g_proj` are **BF16 in the checkpoint**
(`LagunaCheckpointValidation.swift:355-360`, all `add(..., .bf16, ...)`). The
NVFP4/INT8 attention banks are *synthesised at load* from those BF16 tensors by
`lagunaNativeAffineWeight` inside `prepareNativeAffineQKVWeight`
(`LagunaRuntimeModel.swift:5301-5305`).

`addNVFP4` is called only for `mlp.switch_mlp.*` and `mlp.shared_expert.*`
(`LagunaCheckpointValidation.swift:389-408`).

| stream | premised as NVFP4 g16 | actually NVFP4 on disk? |
| --- | ---: | --- |
| attention q/k/v/o + g_proj | 807.7 MB/token | **no — BF16, built at load** |
| routed + shared experts | 552.1 MB/token | yes |

So **807.7 MB — 59.4% of the premised 1360 MB — is not offline-addressable at
all**, and the offline-addressable scale stream is ≤ **61.3 MB/token (3.4% of the
1794 MB budget)**, not 150 MB.

### 2. The mechanism is already shipped, at load time, default ON

`DARKBLOOM_PACKED_SCALES` (`LagunaRuntimeModel.swift:152-167`) states the
hypothesis verbatim and already implements it for the routed gate/up path:

> the stock `lagunaRoutedSwiGLUQMV` reads codes and E4M3 scales from two
> separate tensors (four device streams per simdgroup iteration)… The packed
> side bank stores only the 32 scale bytes for each row and K block, **in the
> kernel's exact walk order** … only scale address computation changes, so the
> packed dispatch is bit-exact

Built by `preparePackedRoutedGateUpBank` (`:9824-9856`), default ON (`:166-167`).
The place the scale stream was largest is already walk-order packed.

### 3. Dominance — this is the general result, and it is why 0-of-147 is rational

`prepareFusedRuntimeWeights` is **eager**: "Called by the weight cache after
`update` + `eval`, before constructor-time warmup … the fused arrays are
resident **before the first forward**" (`:10893-10898`), invoked from
`LagunaRuntimeWeights.swift:638`. I checked this specifically because a *lazy*
repack would have leaked cost into the cold 512-token prefill and rescued the
arm. It does not.

Therefore:

- Weights land in unified memory at init, outside both timed axes.
- The runtime already builds arbitrary derived banks there — packed scales
  (`:9824`), fused `[gate32, up32]` (`:9777-9800`), attention affine banks from
  BF16 (`:5301-5305`).
- **Anything an offline layout change can do to the in-memory stream, a
  load-time repack can also do — strictly more flexibly**, since it can also
  repack the BF16-on-disk attention weights, which offline cannot.
- Offline's *only* unique advantage is avoiding a resident duplicate bank. RAM
  is not binding: 21.57 GB against a 25 GiB cap (`Constants.swift:176`), and the
  packed bank costs ~32 MB per sparse layer (~1.25 GB total).

`Sources/MLXFastTransform/` is untouched in 147 swept diffs because it is
**dominated by a strictly more capable, unscored layer** — not because the field
overlooked it. A zero-attempt coverage signal is only an opportunity when the
axis is *reachable and non-dominated*; this one is neither.

## Part 3 — the fallback levers die to the same argument

I did not implement one, because dominance is not specific to interleaving:

- **Pre-permuting for RoPE/head reordering** and **pre-transposing strided
  reads** are both pure layout, so the load-time repack does them at equal
  benefit and zero contract risk.
- **Static per-layer routing metadata** from my #11 histogram (CV 1.80, 20.3%
  zero-row) is genuinely not reproducible at load — but it is a function of the
  *input tokens*, so baking it offline is input-dependent specialization and
  reads directly against the fixture-specialization and benchmark-dependent-switch
  prohibitions. I am not proposing it.

The honest statement is that the offline transform is worth revisiting only if
the campaign ever becomes RAM-bound, i.e. if a desirable load-time bank cannot
fit under the 25 GiB cap. Then offline pre-packing buys the duplicate back. Not
today, with 3.3 GB of headroom.

### Evidence

- Host, memory profile, toolchain, thermal policy: **not applicable — no
  benchmark run.** The arm closed on source and trusted-harness evidence. Both
  gating questions were decidable statically, so per the ladder I did not spend
  host time proving an already-answered fact.
- Exact baseline and candidate commands: none run.
- Tests and risk-based checks run: none. No `editablePaths` file changed, so
  there is no numerical, dispatch, or representation risk to gate.
- Correctness and serial-protocol verdict: unchanged by construction — zero
  runtime diff.
- Peak RAM / generated-weight size: unchanged (21.57 GB, 9 files); recorded the
  25 GiB trusted ceiling as the axis's real constraint.

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | — | not measured | — |
| prefill seconds/token | — | not measured | — |
| same-host paired estimate | — | not measured | — |

No timing is reported because no candidate exists. The mechanism's ceiling is
**0 bytes/token** at A = 1.0, against your 17 MB / 0.61% promotion bar.

### Conclusion

- **What happened:** the contract permits a changed transform output (a useful,
  durable finding), but the interleave mechanism has zero bytes to recover, 59%
  of its intended surface is BF16 on disk, the part that mattered is already
  walk-order packed at load, and the offline layer is structurally dominated by
  an eager, unscored load-time repack.
- **Evidence against the mechanism:** amplification is provably A = 1.000 from
  the v5 addressing (`:7660-7705`) and independently bounded A ≤ 2.14 by that
  kernel's own measured 231/260.2 GB/s.
- **Uncertainty / M5 transfer risk:** none of this is host-dependent — it is
  checkpoint dtypes, addressing arithmetic, and trusted-harness control flow. The
  one thing I could not read is the box-owned `measure-job.sh`, so the Part 0
  GREEN verdict rests on the readable trusted harness; that verdict is moot for
  my own conclusion, which does not depend on it.
- **Smallest useful next action:** redirect this axis's effort to the load-time
  bank layer in `Sources/MLXFastModel/`, and treat "zero-attempt in the corpus"
  as a hypothesis about *reachability* that needs a dominance check before it
  earns an arm.
- **Recommendation: close.** The last unexplored axis in the corpus is now
  explored and explained. Nothing here should be merged into the runtime.
