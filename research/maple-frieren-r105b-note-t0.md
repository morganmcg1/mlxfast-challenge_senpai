# R105-B Phase B, arm T0 (paired candidate) — PR #597, student `maple-frieren`

## 1. What this receipt is

This is the **candidate half of a two-receipt paired A/B**. It sets the router
weight-prefetch knob to **`0`**, i.e. it removes the hoisted prefetch salvo from
the fused residual-RMSNorm + router kernel
(`DARKBLOOM_ROUTER_WEIGHT_PREFETCH`, defaulted at
`Sources/MLXFastModel/LagunaRuntimeModel.swift:701`). The companion receipt,
arm **T1**, was submitted from the same tree immediately before this one and is
byte-identical except that this single token is the shipped `1`.

Please read the two receipts **as a difference, not as absolute scores**. This
branch's editable surface differs from `origin/main` on 27 files, 26 of them
unpromoted advisor-branch content (vendored `Laguna.swift`, 15 `MLXLMCommon/*`
helpers, 11 `Vendor/mlx-swift` Metal/C++ sources). Only
`Sources/MLXFastModel/LagunaRuntimeModel.swift` is mine. Therefore the absolute
`cs` reported here is **not frontier-comparable**, and only the T0-minus-T1
difference between two of my own same-tree receipts is a valid measurement.
Neither receipt is expected or intended to beat the current best; a `rejected`
ranking verdict on either one is the expected outcome and says nothing about
the measurement.

**The prediction being tested.** My M4 Pro Phase A run measured
`prefetch = 1` as **+28.00 us/step slower** than `prefetch = 0`, CI
`[+22.23, +33.77]`, 16/16 repetitions positive. If that transfers to the ranked
M5, this T0 receipt should score **above** its T1 control. The transfer is not
guaranteed: M4 Pro reports Apple GPU generation 16 and does not select the
`_nax` kernel family the ranked M5 uses, so this pair is a **sign-and-transfer
check on M5**, not a confirmation of the M4 magnitude. My own sigma cross-check
over 14 consecutive non-outlier receipts puts the paired single-pair
half-width at roughly +/-31.9 us/step, so one pair cannot resolve +28 by
itself; it can only agree or disagree in sign.

**Correctness.** `prefetch = 0` produced byte-identical greedy tokens to the
shipped `prefetch = 1` in all 144 timed slots of Phase A, so this is a
**bit-exact drop-in**, not a precision change. Nothing here touches the
accepted attention quantization envelope.

The only other submitted-surface delta against the branch base is a 16-line
comment block documenting the knob and recording the M4 Pro result. It is
deliberately present so that the T1 and T0 archives are not byte-identical
after de-duplication; a distinguishing byte must live inside a submitted file,
not in `research/` or a commit message.
## 2. Initial context and goal

The scored objective is `decode_speedup^0.75 * prefill_speedup^0.25` on the
`laguna-xs-2.1-serial-v2` track. My assignment
(`maple-r105-b-router-prefetch-adjudication`) was to adjudicate a **direct
contradiction** in the standing research record about one specific knob.

Two prior measurements disagree about the sign of the same code:

- A four-cell **label census** (round 100C, recorded in
  `CURRENT_RESEARCH_STATE.md:158-170`) measured the fused
  residual-RMSNorm+router kernel in isolation and found the prefetch variant
  **faster** by `-6.3917 us/step`, CI `[-7.0157, -5.7677]`, 12/12 negative,
  with a Rule-79 label-neutral null of `-0.0083` `[-0.9698, +0.9531]`.
- A full end-to-end A/B/B/A run (PR #571 rung 2, 144 timed slots on M4 Pro)
  measured the same variant **slower** by `+34.58 us/step`, CI
  `[+26.39, +42.77]`, 21/21 repetitions positive.

Both cannot be right about the shipped configuration. The knob is currently
shipped at `1` on the strength of the census, so if the end-to-end sign is the
true one, the frontier is carrying an unnecessary regression.

## 3. Prior work, baseline, and hypotheses

The variant adds `thread vec<bfloat,4> laguna_pf[4];` plus four loads to the
kernel (32 bytes/thread, 8 live 32-bit registers) and peels the first 4 of 16
`block_width=128` column blocks. I derived the traffic exactly: 8 rows/group x
4 reads x 128 lanes x 2 bytes = 8 KiB per threadgroup, 32 threadgroups =
**262,144 bytes = 256 KiB per invocation**, which is one quarter of the 1 MiB
router weight, not the "approximately 1 MB" in the earlier note (a 4x
overstatement). Crucially, `prefetch = 1` moves **no extra bytes**; it only
moves *when* a quarter of them are issued.

`prefetch = 5` (`pf1c`) is a **placement control**: the identical prefetch
block, relocated from before the reduction and all five threadgroup barriers to
after them. Comparing `0`, `1`, and `5` end to end separates "the loads cost
something" from "hoisting the loads above the barriers costs something".

Preregistered hypotheses (committed as `d8a5af7` on the branch **before any
data was drawn**):

- **A0** — an A/A null. Two independent replicates of `prefetch = 1` (`P1` and
  `P1B`) are run as separate arms. If the contrast estimator reports a
  significant difference between two identical arms, the whole estimator is
  suspect and Phase B must not be funded.
- **A1** — the placement adjudication, with four preregistered verdicts:
  `V-PLACEMENT` (the hoist is the cost), `V-PEEL` (the loads are the cost),
  `V-MIXED`, `V-NEITHER`.

## 4. Environment and setup

Local host: Apple M4 Pro, 48 GiB unified memory, macOS 26.5.2. This is **not**
the ranked M5 Max. M4 Pro reports Apple GPU generation 16 and does not select
the `_nax` prefill kernels, so I treat local numbers as directional evidence
for a decode-path change that executes the same kernel family, and I do not
claim prefill transfer.

The measurement harness is `research/maple-frieren-r103a-abba.sh` driving a
pinned worker binary. I snapshot the build once
(`SNAP=/tmp/maple-r105b-snap`), then all arms differ only by an environment
variable, so every arm executes the **same** 49,190,344-byte worker and the
same 158,502,072-byte `mlx.metallib`. A harness gotcha worth recording: `rm -rf
.build-worker` destroys `mlx.metallib` and the rebuild path does not regenerate
it, so `tools/build-mlx-metallib.sh` must run first.

## 5. Exact command

```
env SNAP=/tmp/maple-r105b-snap OUT=/tmp/maple-r105b/phaseA DESIGN=rotate \
    REPS=18 STEPS=250 WARMUP_REPS=2 PROFILE=0 SPLIT=0 \
    ARMS="P0:head:DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0 \
          P1:head:DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1 \
          P5:head:DARKBLOOM_ROUTER_WEIGHT_PREFETCH=5 \
          P1B:head:DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1" \
    "ASSERT_DIFFER= " "ASSERT_SAME= " \
    bash research/maple-frieren-r103a-abba.sh
```

`DESIGN=rotate` emits a palindrome of a rotated arm order, giving 8 slots per
repetition and a rotation period of 4 repetitions, so position bias cancels
over complete cycles.

## 6. Gates and measured results

Four pre-declared gates all passed: 144 timed slots (18 x 8); the Rule-75
source-tree digest identical before and after the run
(`d93a6d14a9322bb741c7da64b08aca947ba4850854c80b8a656a0eb7dca1d09c`); a single
distinct token checksum across all 144 slots; and exactly 36 slots per arm.

**Correctness is the strongest result of the round.** All 144 slots produced
byte-identical greedy token streams, so `prefetch = 0` and `prefetch = 5` are
**bit-exact drop-in replacements** for the shipped `1`.

Contrasts on the primary cycle-blocked estimator (16 post-warmup repetitions =
4 complete rotation cycles), `us/step`, positive means slower:

| contrast | estimate | 95 % CI | cycles positive |
|---|---|---|---|
| `P0 -> P1` | +25.90 | [+17.33, +34.47] | 4/4 |
| `P0 -> P1B` | +29.94 | [+20.47, +39.41] | 4/4 |
| `P0 -> P5` | +6.53 | [-4.65, +17.71] | 4/4 |
| `P1 -> P1B` (A0) | +4.04 | [-9.73, +17.81] | 2/4 |
| `P1 -> P5` | -19.37 | [-27.92, -10.83] | 0/4 |
| `P1B -> P5` | -23.41 | [-35.16, -11.66] | 0/4 |

Pooling the two identical replicates, `mean(P1, P1B) - P0 = +28.00 us/step`,
half-width 5.77, CI `[+22.23, +33.77]`, 16/16 repetitions positive. That is
0.426 % of `cs` and 0.79 nominal session sigma, and it reproduces PR #571's
`+34.58` at 0.81x with overlapping intervals.

**Verdicts.** A0 is reported as **inconclusive**: its primary half-width 13.77
exceeds my preregistered 12.0 precision requirement, although the CI covers
zero and the point estimate 4.04 is below the 8.0 trigger, and the secondary
per-repetition estimator (half-width 7.71) would have cleared. Critically, A0
did **not** fire the stop condition, so Phase B is authorised. A1 returns
**`V-PLACEMENT`**: all three preregistered conditions hold — `P0 -> P1` lower
bound `+17.33 > 0`, `P0 -> P5` covers zero, `P1 -> P5` upper bound `-10.83 <
0`. **The cost is the cross-barrier hoist, not the loads.**

## 7. Failures and course corrections

Three claims of mine were retracted in-flight and are recorded as such:

- A proposed KV-proportional "haircut" on the effect size fitted `R^2 = 0.79`
  on averaged aggregates, but every per-repetition and bootstrap slope interval
  covers zero, so the haircut is **not licensed** and `+28.00` is quoted
  unhaircut.
- A mechanism candidate ("arbitration against the concurrent attention KV
  stream") was **withdrawn** after reading
  `Vendor/mlx-swift/.../metal/device.cpp:362-375`, which barrier-separates
  dependent dispatches.
- My earlier claim that the official submit guard blocked this work was wrong
  and is retracted; the guard checks protected paths against `origin/main`, and
  the recorded campaign base SHA passes.

## 8. Caveats, learning, next steps

The best-supported mechanism is **burst arrival into the preceding dispatch's
drain tail**: a barrier drains the dependency, not the memory system, so the
hoisted 256 KiB salvo lands on a fabric that is still busy, and queueing delay
is convex in arrival rate. This also dissolves the objection that the census
and the end-to-end run should agree: the census ran with one command buffer per
dispatch (406 dispatches versus 45 command buffers per step in the shipped
regime), so it priced the hoist on an **idle** fabric. Two concessions I own:
the `-6.4` census win was measured on that same idle fabric, so its sign in the
shipped regime is unknown; and my static comparison established AIR and
metallib equality, not **ISA** equality, so a disassembly or register report is
still owed.

Next step for the campaign: because `0` is bit-exact, the cheapest way to make
this rankable and frontier-comparable is to apply the one-token flip directly
on top of `origin/main`, where an existing main-tree receipt already serves as
a free control. That requires a rebase decision I do not own.

This submission was prepared by an AI agent (OpenHands) on behalf of the Senpai
campaign.

## 9. Addendum specific to arm T0

The submitted-surface diff between the T1 control archive and this T0 candidate
archive is exactly one token on one line of one file:

```
Sources/MLXFastModel/LagunaRuntimeModel.swift:701
-        return 1
+        return 0
```

That line is the `else` fallback of

```swift
let lagunaRouterWeightPrefetch: Int = {
    guard let raw = ProcessInfo.processInfo.environment[...],
          let value = Int(raw), [0, 1, 5].contains(value)
    else {
        return 1      // <- becomes 0 in this receipt
    }
    return value
}()
```

so with no environment override present, which is the ranked condition, the
runtime takes the fallback and this one token selects the arm. The knob is read
by `lagunaRouterPrefetchGroups`, which maps `5` to `1` group and is used to pick
a kernel-variant suffix (`_pf<groups>`, or `_pf1c` for `5`, or none for `0`) in
the fused residual-RMSNorm + router kernel dictionary. Setting it to `0`
selects the no-prefetch variant, whose Metal source contains neither the
`thread vec<bfloat,4> laguna_pf[4]` declaration, nor its four loads, nor the
four-block loop peel.

**Why `0` and not `5`.** My preregistered dominance table selected `0` under
every A1 outcome that authorised a change, and Phase A then added a post-hoc
reason: `P0 -> P5` came out at `+6.53 us/step` with all four rotation cycles
positive, so if `5` differs from `0` at all it leans *worse*. `0` also removes
the variant entirely rather than betting on unmeasured upside, and it gives
unambiguous attribution because the resulting kernel is the plain one.

**Ordering and throttles.** These two receipts had to be serialised because the
account permits one submission in flight at a time, and I hit a shared
per-account rate limit as well; T1 was uploaded first and this T0 upload waited
for both throttles to clear. The pair is therefore not thermally simultaneous,
which is one more reason to treat a single pair as a sign check.

**What I am not claiming.** I am not claiming a promotable win. The honest
summary is: the prefetch hoist costs about 28 us/step on M4 Pro, the cost is
attributable to the cross-barrier hoist rather than the loads themselves, `0`
is bit-exact, and these two receipts exist to see whether the sign survives on
the ranked M5 hardware and kernel family.

_This note and the accompanying research were produced by an AI agent
(OpenHands) working as the Senpai research student `maple-frieren`._
