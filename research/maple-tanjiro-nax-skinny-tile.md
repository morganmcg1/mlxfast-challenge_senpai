# H2: skinny-N regular-NAX steel tile downsize for the 78 wk/wv prefill GEMMs

PR #293 · assignment `maple-2026-08-07l-nax-skinny-tile` r1 · student maple-tanjiro
BASE_SHA `13f9b6f7960bf1872465f2e7950685d52ccf2e48` (branch
`codex/mlxfast-maple-20260804-advisor`)

## 1. Hypothesis and mechanism

The 78 wk/wv prefill projections are M=512, N=1024, K=2048. They reach
`steel_matmul_regular_axpby_nax` and receive the M5 head-class tile
bm=64 / bn=128 / bk=256 / wm=2 / wn=4. That covers 8x8 pre-swizzle tiles, and the
unconditional `swizzle_log = 2` turns it into **64 threadgroups — 1.6 per core on
a 40-core M5 Max**. With only 1.6 waves of work per core there is no second
threadgroup to hide the tail, the k-loop prologue, or memory latency.

Halving `bn` 128 -> 64 and `wn` 4 -> 2 together doubles the threadgroup count to
128 (3.2 per core) while holding `SN = bn/wn = 32`. The cost is re-reading A once
more per n-tile column: +33% GEMM-visible traffic on this class.

Predicted effect from the brief: **-1.5 to -5 ms prefill (+0.56% to +1.87%
score)**. Resolution bar at 3 sigma: **1.35 ms** (sigma(S)=0.318 ms, n=16, paired
sigma ~0.4497 ms). Conversion constants used throughout: prefill **0.374750 %
score per ms**, decode **0.015280 % per us**.

## 2. Why the change is bit-exact

Stronger than the argument in the brief. `SM`, `SN`, `SK`, `TM`, `TN` are
*identical* between the incumbent and candidate A:

| geometry | SM | SN | SK | TM | TN | threads/TG | simdgroups |
|---|---|---|---|---|---|---|---|
| incumbent 64/128/256/2/4 | 32 | 32 | 32 | 2 | 2 | 256 | 8 |
| **candidate A 64/64/256/2/2** | 32 | 32 | 32 | 2 | 2 | 128 | 4 |
| candidate B 32/64/256/2/2 | 16 | 32 | 32 | 1 | 2 | 128 | 4 |

So `gemm_loop` (`gemm_nax.h:26-130`) receives the **same template
instantiation** `<T, SM=32, SN=32, SK=32, BK=256, ...>` in both arms. It uses no
threadgroup memory and performs no cross-simdgroup data exchange — its only
barrier is `threadgroup_barrier(mem_flags::mem_none)`, a scheduling barrier.
Only simdgroups-per-threadgroup (8 -> 4), the `tid` -> `(c_row, c_col)` map,
`tiles_m`/`tiles_n`, and the grid dims change. Every output element therefore
keeps the same k-ascending in-register MMA accumulation chain, so **candidate A
is bit-exact by construction**, not merely numerically close.

Empirically confirmed (see §3): `staticThreadgroupMemoryLength = 0` for all three
geometries, so there is no shared-memory staging that could reorder anything.

Candidate B changes SM to 16 (TM=1) and is a *different* instantiation, so its
bit-exactness rests only on the weaker per-element-order argument. That is why B
is a strict follow-up, not part of the primary arm.

## 3. Stage 0 — offline MSL dispatchability (KILL GATE 0: PASSED)

M4 hosts never JIT this source (§6), so I reproduced
`get_steel_gemm_fused_nax_kernel()`'s concatenation order
(`jit_kernels.cpp:979-1010`) offline in
`research/tanjiro_steel_nax_compile_check.sh`. Two details had to be right:

- The JIT emits **eight** template args (`AccumType` defaults to `float`), while
  the AOT macro in `steel_gemm_fused_nax.metal:15` passes `float` explicitly as a
  ninth. `jit_kernels.cpp` is the compiled path (`Package.swift:25` sources it,
  `:284` excludes `nojit_kernels.cpp`), so the JIT form is authoritative.
- The kernel is specialised by function constants 10/100/110/200/201/202, so the
  pipeline must be built with `MTLFunctionConstantValues`; a plain
  `makeFunction(name:)` fails with `validateWithDevice:1530 ... Use
  newFunctionWithName:constantValues:`. My first attempt hit exactly that and it
  was **my harness bug, not a hardware limit** — worth recording because it
  looks like a gen-16 NAX rejection.

| geometry | compile | metallib | maxTotalThreads/TG | staticTGMem | execWidth |
|---|---|---|---|---|---|
| incumbent 64/128/256/2/4 | OK (metal4.0) | 75,090 B | 256 | 0 | 32 |
| **candidate A 64/64/256/2/2** | OK (metal4.0) | 75,073 B | **128** | **0** | 32 |
| candidate B 32/64/256/2/2 | OK (metal4.0) | 64,753 B | 128 | 0 | 32 |

All three compile, link, and create a real pipeline state. `maxTotalThreads/TG`
matches `WM*WN*32` exactly, confirming the compile-time
`max_total_threads_per_threadgroup` attribute resolves as intended.

Logs: `research/pr-nax-skinny-logs/compile-bm*-bn*-bk*-wm*-wn*.log`.

## 4. Stage 1 — the guard, and one correction to the brief

Implemented in the single submitted file
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp`, immediately
after the `devc` branch and before kernel-name construction, mirroring the
in-tree `darkbloom_steel_prefill_tile()` idiom (env gate, default ON, same
comment style):

```cpp
if (darkbloom_steel_regular_skinny_tile() && bn == 128 && wn == 4 &&
    (N % 64) == 0) {
  const int tiles_m = (M + bm - 1) / bm;
  const int tiles_n = (N + bn - 1) / bn;
  if (tiles_m >= 4 && tiles_m * tiles_n <= 96) {
    bn = 64;
    wn = 2;
  }
}
```

`bn == 128 && wn == 4` makes the SN=32 invariance — the bit-exactness anchor —
explicit and future-proof against later tile retuning.

### The `tiles_m >= 4` term is load-bearing, not cosmetic

The brief proposed `tiles <= 96 && N % 64 == 0`. I verified the NAX split-K
admission at `matmul.cpp:1019-1021` and found that **all three M=1 decode classes
reach the regular-NAX function**, and the tile ceiling alone would have admitted
every one of them:

| decode class | tiles_m | tiles_n | tiles | ceiling alone | with `tiles_m>=4` |
|---|---|---|---|---|---|
| wq/gate/up (1,8192,2048) | 1 | 64 | 64 | ADMIT | exclude |
| wk+wv (1,1024,2048) | 1 | 8 | 8 | ADMIT | exclude |
| L39 bank (1,2048,2048) | 1 | 16 | 16 | ADMIT | exclude |

That would have retiled the entire decode QKV/gate/up projection path — 75% of
the score weight — making any prefill result unattributable. With `tiles_m >= 4`
the arm is prefill-only and the decode axis remains a genuine negative control.

This is shape-based branching of exactly the kind MLX already uses
(`K > (M+N)`, `max(M,N)`), not prompt or fixture specialisation.

### Admitted vs excluded classes (verified two ways)

Verified by a Python model of the grid arithmetic
(`research/tanjiro_nax_skinny_occupancy.py`) and independently by a standalone
C++ replay of the guard body (`/tmp/guardcheck.cpp`, output archived at
`research/pr-nax-skinny-logs/guard-logic-replay.log`). Both agree.

| class | M | N | K | route | TG | TG/core | verdict | new TG/core |
|---|---|---|---|---|---|---|---|---|
| wq slide + dense gate/up | 512 | 8192 | 2048 | regular-NAX | 512 | 12.80 | exclude | - |
| wq full | 512 | 6144 | 2048 | regular-NAX | 384 | 9.60 | exclude | - |
| **wk + wv (TARGET, 78x)** | 512 | 1024 | 2048 | regular-NAX | 64 | **1.60** | **ADMIT** | **3.20** |
| L39 [K;V] bank | 512 | 2048 | 2048 | regular-NAX | 128 | 3.20 | exclude | - |
| wo slide / dense down | 512 | 2048 | 8192 | split-K | - | - | never reached | - |
| wo full | 512 | 2048 | 6144 | split-K | - | - | never reached | - |
| router | 512 | 256 | 2048 | split-K | - | - | never reached | - |
| g_proj | 512 | 128 | 2048 | split-K | - | - | never reached | - |
| decode wq/gate/up | 1 | 8192 | 2048 | regular-NAX | 256 | 6.40 | exclude | - |
| decode wk+wv | 1 | 1024 | 2048 | regular-NAX | 32 | 0.80 | exclude | - |
| decode L39 bank | 1 | 2048 | 2048 | regular-NAX | 64 | 1.60 | exclude | - |

Exactly one class changes. Full routing derivation:
`research/pr-nax-skinny-logs/routing-verification.md`.

## 5. Reconciling the arithmetic-intensity figure with the brief

I reproduce the brief's DRAM re-read element counts exactly
(`(M/bm)*K*N + (N/bn)*M*K`):

| tile | elems | MB/GEMM | GB over 78 | vs base |
|---|---|---|---|---|
| incumbent 64/128 | 25,165,824 | 50.3 | 3.93 | 0% |
| A 64/64 | 33,554,432 | 67.1 | 5.23 | **+33%** |
| B 32/64 | 50,331,648 | 100.7 | 7.85 | +100% |

But the brief's **293 FLOP/byte** is the *compulsory-traffic* intensity
(2.15 GFLOP / 7.34 MB). The **achieved** intensity at the incumbent tile is
**43 FLOP/byte** (2.15 GFLOP / 50.3 MB), dropping to 32 under candidate A. Both
numbers are arithmetically correct; they have different denominators. Flagging it
because 293 makes the class look far more compute-bound than it is.

**This is the main quantitative risk to H2.** If the extra re-read went to DRAM,
at ~550 GB/s it would cost 7.14 ms -> 9.52 ms, i.e. **+2.4 ms**, which would
swamp the predicted -1.5 to -5 ms occupancy win. The reason to still expect a net
gain: the per-GEMM working set is only **7.3 MB** (A 2.1 + B 4.2 + C 1.0), well
inside an M-series Max system-level cache, so the additional re-reads should be
SLC hits rather than DRAM traffic. That is an assumption about cache residency,
not a proof, and **only the ranked M5 run resolves it.** If the arm comes back
flat-to-negative, this is my first-suspect explanation.

## 6. Why local M4 timing has zero power here (and what I ran instead)

`is_nax_available()` (`device.cpp:913-931`) requires
`gen >= (arch == 'p' ? 18 : 17)`. This host is an **Apple M4 Pro**: arch back
`'p'`, generation 16. So `use_nax` is permanently false, the NAX split-K and
regular-NAX functions are **never called**, and my guard is unreachable dead code
locally. A matched local-iterate pair would compare two binaries that execute
identical instructions on this host — it would measure noise and nothing else.

I therefore did **not** dress up an M4 timing pair as a negative control. What I
ran instead, all of which does carry information:

- `./setup.sh` — clean exit, so the change compiles into the scored worker and
  the `VendoredMetalFingerprint` (`VendoredMetalFingerprint.swift:18-21`, which
  SHA-256s the `mlx` and `mlx-generated` subtrees) is consistent. Skipping this
  after a `matmul.cpp` edit fails benchmarks with a misleading harness error.
- `research/nax_twin_check.py` — PASS; no `mlx-generated/*.cpp` twin was touched,
  so no AOT/JIT divergence was introduced.
- Offline MSL pipeline creation for all three geometries (§3) — the only local
  way to prove dispatchability.
- The pre-existing `DARKBLOOM_STEEL_TRACE=1` dispatch trace, to *measure*
  rather than assume that no NAX GEMM is dispatched here (§7.2).
- `research/run_upstream_equivalence.sh`, in two arms: guard on, and guard off
  via `DARKBLOOM_STEEL_REGULAR_SKINNY_TILE=0` as a same-binary base control
  (§7.3). **This exercises the non-NAX path only and cannot validate NAX
  numerics.** Its value is proving the edit did not damage shared tile
  selection or the non-`_nax` `steel_matmul_regular_axpby`.

## 7. Local verification results

### 7.1 Gates that passed before any build

| gate | command | result |
| --- | --- | --- |
| assignment scope | `senpai/validate-assignment-scope.sh 13f9b6f7960bf1872465f2e7950685d52ccf2e48 Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp` | `assignment scope OK: 1 submitted path(s)` |
| editable budget | `senpai/check-editable-budget.sh 13f9b6f7960bf1872465f2e7950685d52ccf2e48` | `OK current=2952350/3000000 headroom=47650 growth=1495/262144 files=142 (base=142)` |
| AOT/JIT twin | `python3 research/nax_twin_check.py` | `TWIN CHECK: generated copy matches the header` (no twin touched) |
| worker build + metallib + fingerprint | `./setup.sh` | exit 0, 00:01:56, 13 reference hashes verified, 20.1 GiB checkpoint |

Diff size: **31 lines added, 0 removed, 1 file**. Growth 1,495 B against a
262,144 B per-review budget, so the static review has ample headroom.

### 7.2 The scored NAX path is not reachable on this host — measured, not assumed

`steel_matmul_regular_axpby_nax` has exactly **one** call site,
`matmul.cpp:1057`, and it is directly wrapped in `if (use_nax)`. So the claim
"my guard is unreachable on an M4 Pro" reduces to "`use_nax` is false here".
I proved that empirically rather than only from `device.cpp:913-931`, using the
pre-existing ground-truth dispatch trace (`darkbloom_steel_trace()`,
`matmul.cpp:114`), which prints the real kernel base name and grid at
**every** NAX GEMM dispatch (`matmul.cpp:389`, `matmul.cpp:855`):

```
DARKBLOOM_STEEL_TRACE=1  →  0 lines matching '[darkbloom][steel]'
```

Zero NAX dispatches across a full 512-token prefill plus 8 decode steps.
Every GEMM on this host takes a non-`_nax` path. The change is therefore dead
code locally, and **no local timing pair on this machine can carry any signal
about it** — a matched pair would compare two binaries executing identical
instructions.

### 7.3 Upstream-equivalence oracle, with a same-binary base control

Run through `research/run_upstream_equivalence.sh` (the wrapper uses the bare
test-function filter, repairs the debug metallib, and refuses to score a
zero-test invocation as a pass). Both runs reported
`EQUIVALENCE_EXACT_STEPS=8` and executed exactly **1** test, so neither was a
vacuous pass.

The control is `DARKBLOOM_STEEL_REGULAR_SKINNY_TILE=0`. That is a genuine base
control, not a weaker substitute: the guard is the *only* difference between
`BASE_SHA` and the candidate, so disabling it reproduces base tile selection
exactly — and it does so from the **same binary**, which isolates the guard
more tightly than a separate base build could.

| step | candidate (guard on, default) | control (`SKINNY_TILE=0`) | runtime vs upstream token |
| --- | --- | --- | --- |
| prefill | max 0.125 / mean 0.011933609 | max 0.125 / mean 0.011933609 | 5991 == 5991 |
| decode-0 | 0 / 0 | 0 / 0 | 509 == 509 |
| decode-1 | 0 / 0 | 0 / 0 | 902 == 902 |
| decode-2 | 0 / 0 | 0 / 0 | 5991 == 5991 |
| decode-3 | 0 / 0 | 0 / 0 | 509 == 509 |
| decode-4 | 0 / 0 | 0 / 0 | 902 == 902 |
| decode-5 | 0 / 0 | 0 / 0 | 5991 == 5991 |
| decode-6 | 0 / 0 | 0 / 0 | 509 == 509 |
| decode-7 | 0 / 0 | 0 / 0 | 902 == 902 |

**Byte-identical, to all nine significant digits of the prefill mean.** Every
greedy token matches upstream in both arms. `EQUIVALENCE_EXIT=1` in both arms,
solely from the zero-tolerance assertion at
`LagunaCorrectnessTests.swift:249:5` firing on the prefill row.

Reading of that failure: it is **pre-existing non-M5 near-tie drift in the
prefill logits, not a candidate regression.** Three independent facts pin it
down — (a) the guard's only reachable path is never dispatched here (§7.2),
(b) toggling the guard off changes nothing to nine digits, and (c) the
divergence is confined to prefill while all eight decode steps are exact,
which is the wrong signature for a tile-selection bug on a QKV projection that
prefill and decode both use. 0.125 is one bf16 ULP at logit magnitude 16–32,
and it flips no token.

Per `AGENTS.md`, that is the situation `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1`
exists for. I did not set it: it would only relabel a local record and it
relaxes nothing official, and the ranked M5 stack remains the authority for
near-tie behavior.

Raw logs for both arms are committed verbatim:
`research/pr-nax-skinny-logs/equivalence-candidate-guard-on.log` and
`research/pr-nax-skinny-logs/equivalence-control-guard-off.log`. Each ends in
`EQUIVALENCE_EXACT_STEPS=8` / `EQUIVALENCE_EXIT=1` and reports `Test run with 1
test in 0 suites`, so neither is a vacuous zero-test invocation. Grepping the
control log for `[darkbloom][steel]` returns zero lines, which is the §7.2
measurement.

### 7.4 What I deliberately did not run, and why

- **No local `--local-iterate` timing pair.** §7.2 shows it would be pure
  noise. Presenting one as a negative control would be misleading, and
  `AGENTS.md` explicitly warns that an M4 Pro reports Apple GPU generation 16
  and never selects the `_nax` kernels the ranked M5 uses.
- **No 64-step drift tripwire arm.** It exercises the same non-NAX paths the
  oracle already covered with a stricter zero tolerance, and on this host it
  inherits the same pre-existing prefill near-tie drift, so it would need its
  own base control to interpret and still could not touch NAX numerics.

**Net local position: correctness evidence is as strong as this host allows,
and it is bounded. Local runs prove the edit compiles into the scored worker,
respects scope and budget, keeps the AOT/JIT twin consistent, and does not
perturb the non-NAX paths. They prove nothing about NAX numerics or NAX
timing. Only the ranked M5 can resolve either.**

## 8. Independent kernel-source audit, and why Stage 3 was deliberately deferred

### 8.1 Independent adversarial audit of the bit-exactness claim: CONFIRMED

Because the ranked receipt is expensive and the local host cannot check NAX
numerics at all, I had the claim audited independently against the actual kernel
sources, with an explicitly adversarial brief. Verdict: **bit-exactness
CONFIRMED — the guard is a pure launch-geometry change that cannot alter any
in-bounds result bit.** The load-bearing citations, which I re-read myself:

- `steel_gemm_fused_nax.h:150-198` derives `SM = BM/WM = 32`, `SN = BN/WN = 32`,
  `SK = 32`, `TM = TN = 2` for **both** (128,4) and (64,2). The instantiation is
  literally the same.
- `gemm_loop` (`gemm_nax.h:50-93`) is a k-ascending per-simdgroup in-register
  loop with only `mem_none` barriers: zero threadgroup memory, no
  cross-simdgroup exchange. `tile_matmad_nax` (`nax.h:972-1032`) uses a fixed
  `matmul2d` descriptor `(16,32,16)`. Same FP op sequence per output element
  ⇒ identical bits.
- `load_rows` zero-fills out-of-bounds (`nax.h:239-245`), so an `align_*` flag
  flip cannot change any in-bounds bit — the N=1024 edge-tile concern is closed.
- **Guard placement is early enough.** It precedes *every* consumer of `bn`/`wn`:
  kname (271-280), align flags (289-291), kernel getter (313), `tn`/`tm`
  (330-331), swizzle (334-338), `GEMMParams` (340-354), group and grid dims
  (360-361). Nothing downstream retains a stale 128/4.
- The JIT twin `mlx-generated/steel_gemm_fused_nax.cpp` + `gemm_nax.cpp` are
  byte-identical to the headers, and the AOT metallib list **already contains**
  `(64,64,256,2,2)` (`steel_gemm_fused_nax.metal:24`). Corroborates §3.
- Split-K is provably unaffected: split-K admission (`matmul.cpp:1019-1022`)
  returns before the regular path, and its tiles are computed independently
  (720-757).

The audit also independently reproduced my routing table, including the
knife-edge `(512,1024,2048)` staying on the regular path, and independently
confirmed the `tiles_m >= 4` term is what keeps every M=1 decode shape off the
new geometry.

### 8.2 One genuinely new risk the audit surfaced (R2)

**Variable-length prefills also fire the guard.** Beyond the frozen 512-token
window, the TTFT and GPQA gates run prefills with `M ∈ [193, 768]` at N=1024 and
`M ∈ [193, 384]` at N=2048, and those satisfy `tiles_m >= 4` and the tile
ceiling. They are still bit-exact, but their **performance** there is unmeasured
and could differ in sign from the M=512 case — the tile count and therefore the
occupancy ratio move with M. This does not threaten correctness or the scored
window, but it means a TTFT check is a place a regression could hide. I did not
narrow the guard to `M == 512`: that would be fixture specialization, which
`AGENTS.md` forbids. The honest position is that the guard is general and its
off-window performance is unknown.

Two lower risks, recorded for completeness: the equivalence oracle shares the
mutated kernel so it can never catch a NAX regression (R1 — already the §7
conclusion); and a latent AOT lookup gap for non-`s`/`c`/`d` NAX devices
(`bm128_bn64_bk512_wm4_wn2` is absent from the AOT list), which is not ranked
hardware (R3, note only).

### 8.3 No ranked receipt: intentional deferral, with the reason

**I did not dispatch the official M5 submission. This is a deliberate decision,
not an omission, and H2 is therefore unresolved.** Two independent blockers:

**(a) The shared in-flight slot is occupied.** The account-scoped in-flight
limit is 1. At 15:07 UTC `mlxfast submissions` shows `9753441` (15:03) in state
`validating`, so the slot is held by another role.

**(b) The campaign has no known-passing base right now.** The receipt history is
unambiguous:

| window | receipts | meaning |
| --- | --- | --- |
| through ~09:36 | `rejected` with real scores (e.g. `68b66c5` = 2.5520) | gates passed, simply did not beat best |
| 09:59 → 14:43 | **16 consecutive `failed`, score `n/a`** | official run never produced a score |

⚠️ **Update at 15:07 UTC — the outage is not self-healing.** An earlier draft of
this section recorded `400ba6c` (14:43, "Restore Vendor Files to Last Successful
State") as `validating` and treated it as the pending fix. **It has since
resolved to `failed`, score `n/a`.** The base-health repair therefore *failed to
repair the base*, and the unbroken failure run now spans 16 receipts across
nearly five hours. This strengthens rather than changes the deferral: the next
repair attempt is still outstanding, so a ranked slot spent on H2 now would
still return `n/a`, and would additionally queue that repair behind it.

`failed` with `n/a` is categorically different from `rejected`: `rejected` can
mean only "did not beat the current best", whereas these produced no score at
all. The notes on `2cbf31e` and `400ba6c` diagnose it as a vendor `_nax` revert
that landed on a state which is *not* the last-successful one, breaking M5
correctness.

I checked my own base against that diagnosis. `BASE_SHA`
`13f9b6f7960bf1872465f2e7950685d52ccf2e48` (2026-08-07 13:58 UTC) matches
**neither** snapshot:

| marker | last-passing 68b66c5 | bad revert | **my base** |
| --- | --- | --- | --- |
| `darkbloom_expert_bk128` | present | removed | **present** |
| `darkbloom_stage_wide_scale_ok` | present | removed | **absent** |
| `laguna_expert_pairwise_scale_layout` | absent | added | **absent** |
| `kHalvedScales` (vendor) | present | absent | **absent** |
| `lagunaPrefillSharedHalvedEnabled` (LRM) | active | active | **absent entirely** |

My base is self-consistent — it has neither the LRM halved path nor the vendor
`kHalvedScales` support, so it is not the specific broken pairing that was
diagnosed. But "self-consistent" is not "known to pass M5", and no receipt
exists for this vendor combination.

**Why deferring is the correct call and not merely the cautious one:**

1. **A receipt now would carry no information about H2.** If the base fails M5
   for base-health reasons, the receipt is `failed` with `n/a` and there is no
   prefill number to compare against the −1.5/−5 ms prediction. I would have
   spent the campaign's only slot to learn nothing about the hypothesis.
2. **Contending for the slot actively harms the campaign.** Every score depends
   on restoring a passing base. `400ba6c` did **not** fix it, so a further
   repair attempt is still needed and would be queued behind my
   micro-optimization. Restoring the ability to score anything dominates one
   prefill tile experiment.
3. **The base is about to move anyway.** Whatever restores M5 health will change
   the vendor `_nax` files and hence `BASE_SHA`. A receipt taken against the
   current base would be attributed to a base that is being replaced, so H2
   would need re-running regardless. `AGENTS.md` is explicit that stale-frontier
   timing must not be trusted.

**Recommended re-dispatch, unchanged:** the candidate is complete and ready. The
moment a passing base is re-established, rebase this one-file, +31-line guard
onto it and take one paired receipt. Report `prefill_seconds_per_token` and
`decode_seconds_per_token` at full precision for candidate and same-session
baseline, both `0.95` floor verdicts separately, correctness/error status read
separately from ranking status, and the prefill delta in ms against the
predicted −1.5/−5 ms and the 1.35 ms 3σ resolution bar. Also read the TTFT
gate, per R2.

## 9. Honest ceiling and follow-ups

The whole steel prefill class is worth roughly 9-10 ms with a central estimate of
3-6 ms; this arm targets one class inside it. I will not claim more than the
paired M5 receipt measures.

Not implemented, deliberately out of scope:

- **The split-K tie flip.** wk/wv misses NAX split-K by exactly one:
  `max(M,N)=1024 <= 1024` passes but `K > 2*max(M,N)` is `2048 > 2048` = false.
  Relaxing that to `>=` would route 78 GEMMs to split-K instead, a much larger
  behavioural change with FP32 partial accumulation and therefore not bit-exact.
  Worth a separate assignment.
- **Candidate B (32/64/256/2/2).** Doubles re-read traffic and changes the
  template instantiation. Only worth a receipt if A clears the 1.35 ms bar.
- **L39 [K;V] bank at 3.2 TG/core.** Already at the occupancy candidate A
  achieves, so the same reasoning predicts no gain; excluded by the tile ceiling.
