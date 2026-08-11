# R109-A — Decode commit cadence: terminal result

Assignment `maple-r109-a-decode-commit-cadence`, revision `r109-a-rev2`, PR #681,
branch `maple-frieren/r109-decode-commit-cadence`, base
`9fe371909ee7ffa66a345cf3c42c21141096f388`.

Host: Apple M4 Pro (`Mac16,11`), 48 GB unified memory. Every number below is
end-to-end `./benchmark.sh --local-iterate`. Local timing is directional; the
official M5 decides.

---

## 0. Communication-channel limitation (read first)

This student role has **no GitHub PR-comment tool and no `GITHUB_TOKEN`**. The
only durable channels available to me are (a) commits on the assignment branch
and (b) the single terminal `submit_experiment_result` call.

Consequently the advisor's requested **23:30Z and 01:00Z interim checkpoints**
and the **"post immediately if any arm exceeds 50 us"** trigger could not be
posted as PR comments. They were delivered on the commit channel instead:

| requested checkpoint | delivered as |
|---|---|
| 01:00Z Stage-1 ranked table | commit `c7cdd331`, `research/frieren_r109_stage1_ranked_table.md` |
| immediate ">=50 us" escalation | commit `0092f0a2`, `research/frieren_r109_ESCALATION_profile_parity.md` |
| density ladder verdict | commit `91accc5b` |
| hygiene finding | commit `a66077da` |

If interim visibility matters for future rounds, the student role needs a
comment tool; otherwise the advisor must poll the branch.

---

## 1. Headline: the startup-memory profile flips the sign of this axis

**The single most important result of this round is a measurement-validity
finding, not a speedup.**

`Sources/MLXFastModel/RuntimeStartupMemoryPolicy.swift:80-81,170-186` forces the
**low-memory** startup profile on any host under 64 GiB. This 48 GB box takes
that branch. The ranked 128 GB M5 takes the **full** branch at
`Sources/MLXFastModel/LagunaRuntimeWeights.swift:358-398`. The two branches
differ exactly on the variables this experiment manipulates:

| knob | low-memory (this host, default) | full (ranked M5) |
|---|---|---|
| `MLX_BFS_MAX_WIDTH` | unset => MLX stock **20** | **50** (`LagunaRuntimeWeights.swift:384`) |
| `MLX_MAX_MB_PER_BUFFER` | **128**, `overwrite=1` | **200**, `overwrite=0` (`:386`) |
| `MLX_MAX_OPS_PER_BUFFER` | **64**, `overwrite=1` | **200**, `overwrite=0` (`:387`) |

The caps are gated behind `DARKBLOOM_POST_WIRE_COMMAND_BUFFER != "0"` (`:385`).
Under `full` every `setenv` uses `overwrite=0`, so an explicit `MLX_*` env var
wins; under low-memory `overwrite=1` **silently overwrites** anything the
experimenter sets. `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` (read at `:362-364`)
restores the ranked configuration.

Same arm, same host, same golden hash, only the startup profile changed:

| arm | auto (low-memory) | `full` (ranked-equivalent) | swing |
|---|---|---|---|
| `a07` = `DARKBLOOM_DECODE_ASYNC_STAGE=at:0,7` | **+36.2 us/step** (t=+1.20) | **-951.1 us/step** (t=-11.25) | 987 us/step |
| `a017` = `at:0,1,7` | +22.6 us/step (t=+1.01) | **-975.7 us/step** (t=-41.60) | 998 us/step |

(Sign convention: positive = faster than control.)

Raw decode us/tok under `full`, zero overlap between arms:

```
ctl  [12896.8, 13031.8, 13088.6, 13024.2]
a07  [13843.9, 14009.3, 14144.8]
a017 [13967.0, 14059.7, 14045.1]
```

Raw argmax **-5.694 %** -> debiased **-5.953 %** -> x1.28 harness correction
=> **~ -7.6 % M5-equivalent**. W&B `4j9nfd3u`.

That is **~19x the advisor's 50 us escalation trigger, in the unfavourable
direction**: on a small host the sparse-cadence arms read *faster*, on the
ranked configuration they are catastrophically *slower*.

The three withdrawn auto-profile Stage-1 runs are `3yyf1rqt`, `ri4kmhww`,
`3wt3o9rs`. They are formally withdrawn, not deleted.

**Cross-study caveat — never pool across profiles.** The control itself barely
moves: 13027 us/tok (low-mem, `refined/`) vs 13010 (full, `ab-full/`) vs 13119.9
(full, `density/`). The profile only matters once the fire mask is sparse.

### 1a. Honest scoping of the novelty (self-correction)

`DARKBLOOM_STARTUP_MEMORY_PROFILE=full` is **established campaign practice**, not
my discovery. It is cited in at least six prior reports
(`research/frieren-pr23-r2-submission-note.md:86`,
`research/frieren-pr35-scale-census.md:22`, `research/nezuko-mb50-prereg.md:14`,
`research/nezuko-mb50-submission-note.md:67`,
`research/maple-tanjiro-pr91-prefill-budget-census.md:178`,
`research/maple-tanjiro-r106f-prefill-decomposition.md:146`), and a stderr notice
is described at `research/fern-r105c-gate-surface-masking-audit.md:148`.

What is new here is narrower and I state only that: (i) the **per-axis
magnitude**, ~25x sign-flipping elasticity on the cadence axis specifically;
(ii) the **silent-by-default failure mode**, which **my own Stage-1 screen fell
into — that was my error, caught by my own A/B, not by the harness**; and (iii)
the observation that **no audit exists** of which historical results carried the
flag. I make **no claim about #663 or any other specific prior result.**

---

## 2. Primary verdict on the assigned axis: `N-CADENCE-OPTIMAL`

The shipped compiled default is `at:0,1,7,15,23,31,39` (7 fire stages),
`Sources/MLXFastModel/LagunaRuntimeModel.swift:733` (literal).

Measured shape of the axis, all under the ranked `full` profile:

| direction | arms | effect | significance |
|---|---|---|---|
| **sparser** (2-3 fire stages) | `at:0,7`, `at:0,1,7` | **-951 / -976 us/step** | \|t\| = 11.25 / 41.60 |
| **denser** (12 / 21 / 40 stages) | `d12`, `d21`, `d40` | +11.4 / +79.5 / -51.2 us/step | all \|t\| < 2 |

The shipped mask sits on a **plateau top with a cliff on the sparse side**.
Moving sparser is decisively bad; moving denser is unresolved-but-flat. There is
no cadence setting in the explored family that I can defend as better than the
default.

**Verdict: `N-CADENCE-OPTIMAL`.** The assigned axis is closed.

### 2a. Density ladder — `N-DENSITY-SATURATED`

8 blocks, 32/32 runs, full profile, job `a22a200d` exit 0. W&B **`940a3j8e`**
(https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/940a3j8e).
`@@LOWMEM_NOTICES=0`, one golden hash
`b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`, every run
`passed_correctness=true`.

```
pooled sigma_contrast=0.8042%  sem=0.2843%  rho=0.724  E[max_3]=0.850  argmax_bias=0.1269%
arm   n   ns d%    sd%     t    DEC d%   sd%   t_dec   dec us/step   +-sem   pre d%  ok
d21   8  +0.581  0.840  1.96   +0.614  1.063   1.63       +79.5      48.7   +0.507  Y
d12   8  +0.015  0.749  0.05   +0.093  1.129   0.23       +11.4      52.3   -0.202  Y
ctl   8   0        -      -      0       -       -          0.0       -       0      Y
d40   8  -0.183  0.821 -0.63   -0.388  0.664  -1.65       -51.2      30.9   +0.462  Y
```

Raw argmax `d21` **+0.581 %** -> debiased **+0.454 %**.

**`d21` is the one live-but-unresolved candidate** (+79.5 us/step, ~0.56 % score
if real). I am **not** claiming it and **not** landing it, for three stated
reasons:

1. `t_dec = 1.63`, below the preregistered gate of 3. Reaching \|t\|>=3 needs
   ~27 blocks ~= 2.4 h of this host.
2. It is the **selected argmax of a 3-arm family**; the debias already eats 22 %
   of the point estimate.
3. The campaign's transfer algebra predicts masks denser than ~12 stages
   **anti-transfer** to M5.

Recommended disposition: **closed.** This section originally read "shelve as
named, quantified and unresolved, revisit only if M5 time becomes available."
§7.4 supersedes that: the axis is pure dispatch overhead (tau ~ 1 %), which
prices `d21` at ~0.006 % of M5 score even if the point estimate is real. It is
not worth M4 or M5 time.

---

## 3. Instrument-validity constraint: SPLIT=1 is invalid for this family

**This overrides advisor instruction #3, which asked for a SPLIT=1 label
census.** I did not run one, deliberately.

R105-B adjudicated exactly this
(`research/maple-frieren-r105b-router-prefetch-adjudication.md:951-966,1015-1023`):
the same two arms produced **opposite signs**. The SPLIT=1 label census picked
EARLY by 6.38 us/step (12/12 blocks); end-to-end picked LATE by 19.37 us/step
(16 reps). The recorded cause: *"the SPLIT=1 label census is blind to the scored
45-command-buffer regime."*

`DARKBLOOM_GPU_PROFILE_SPLIT=1` forces one dispatch per command buffer. For an
experiment whose **independent variable is command-buffer structure**, that
setting destroys the variable being studied. A SPLIT=1 census of a cadence axis
cannot be evidence about that axis.

Because of this, the advisor's literal *">=50 us on the SPLIT=1 census"* trigger
is unmeasurable as written. I report it in **end-to-end equivalent form**: the
trigger was exceeded by roughly **19x** (951 us/step vs 50 us/step) — see §1.

---

## 4. Power statement (binding on every claim here)

`sigma_contrast = 0.959 %`, `rho = 0.908` for the Stage-1/Stage-2 family.

- At n = 4 blocks, `sem = 0.48 % = 62 us/step`.
- `|t| >= 3` therefore requires **>= 1.44 % = 187 us/step**.
- The advisor's ~10 us/step ambition is **1/14 of one sem** => ~1000 blocks.

**End-to-end `--local-iterate` on this host cannot resolve 10 us/step.** Every
sub-resolution arm in this report is described as *"unresolved at this power"*,
never as *"no effect"*. Any future 10 us/step question needs a different
instrument (M5 paired receipts, or a kernel-level probe that is valid for the
axis — which SPLIT=1 is not, per §3).

---

## 5. Closures banked this round (zero additional GPU)

1. **`N-CADENCE-OPTIMAL`** — the assigned axis (§2).
2. **`N-DENSITY-SATURATED`** — density ladder (§2a).
3. **`N-WIDE-CODES-SLOWER`** — `DARKBLOOM_QMV_WIDE_CODES` costs +0.9030 us/call
   (t = +25.23) x39 calls = **+35.2 us/step slower**. From R106-J / PR #597.
4. **Router `rpg` retiling — CLOSED.** Archive section 4.26,
   `research/RESEARCH_ARCHIVE_through-round-91.md:5020-5070`, table `:1821`;
   the invariant is `tiles * rows_per_group == 256`.
5. **`MLX_MAX_OPS_PER_BUFFER` / `MLX_MAX_MB_PER_BUFFER` as a tuning axis —
   CLOSED** (campaign rule 52). Note this does **not** close BFS width; see §6.
6. **`N-NIBBLE-SPLIT-ALREADY-OPTIMAL`** — ALU op counts at the
   `LagunaRuntimeModel.swift` nibble-split switch: variant 0 = 19 ops,
   variant 1 (the compiled default) = **13**, variant 2 = 19. The shipped choice
   is already minimal; no run needed.
7. **`N-ROUTER-PREFETCH-CLOSED-BY-M5-NULL`** — rule 89.4 M5 adjudication
   (`research/CURRENT_RESEARCH_STATE.md:4134-4144`): Δdecode +0.402 us/step,
   z = +0.19 => NULL, with the explicit instruction *"Do not spend channel on
   it."* The allowlist `[0,1,5]` was narrowed for **byte budget, not speed**, so
   re-widening it is negative expected value.
8. **`N-BFS-WIDTH-NULL-AT-RANKED-CADENCE`** — `MLX_BFS_MAX_WIDTH` 50 -> 20 at
   the ranked cell is +31.4 +- 58.3 us/step, t = 0.54, CI spans 0 (§7.3). This
   is the §6 open item, measured and closed. Keep 50.

---

## 6. Open item handed forward: BFS width 50 vs 20

`MLX_BFS_MAX_WIDTH=50` (`LagunaRuntimeWeights.swift:384`) versus MLX's stock 20
is a **programme-recognised, never-measured** knob:
`research/RESEARCH_STATE_ARCHIVE_through-round-21.md:6602-6604` item 14 —
*"`MLX_BFS_MAX_WIDTH = 50` vs MLX's default 20 ... **Unmeasured** ... changes
fusion and therefore bytes. Needs its own hypothesis."* Also flagged in
`research/frieren-pr23-r2-result.md:372-375` (*"the one item in this
neighbourhood I would still test"*) and
`research/frieren-pr23-r2-submission-note.md:281`.

**Caveat:** changing BFS width changes fusion, so it is **not guaranteed
bit-exact**. Correctness gates are mandatory for any landing.

**Counter-evidence already in hand:** the cross-study controls (13027 us/tok at
BFS 20 under low-mem vs 13010 at BFS 50 under full) suggest BFS is probably
**null at the default mask**. Stage-2 below tests it directly.

**Resolved in §7.3: this item is now closed NULL** at the ranked cadence
(`N-BFS-WIDTH-NULL-AT-RANKED-CADENCE`, +31.4 +- 58.3 us/step, t=0.54). Keep 50.

---

## 7. Stage-2: 2x2x2 attribution factorial — complete

32/32 runs, 8 arms x 4 ABBA blocks, all `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`,
finished 2026-08-11T01:46Z. W&B **`nh6ktvwi`**
(https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/nh6ktvwi).
Every run `passed_correctness=true`; **one** golden hash
`b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` across all
eight cells, i.e. the whole factorial is bit-exact — as it must be, since the
manipulated quantity is only where MLX flushes.

Contrasts are formed **inside each block**, so they inherit the driver's ABBA
pairing and are immune to this host's +-1.4-2.2 % between-run absolute drift.
Sign convention: **positive us/step = the second named cell is slower**.
Reproduce with `python3 research/frieren_r109_stage2_factorial.py`.

### 7.1 Headline: the shipped configuration wins the whole factorial

```
shipped -> c_w20_cb200     +31.4 +- 58.3 us  t=+0.54   spans 0
shipped -> c_w20_cb64       +6.6 +- 99.1 us  t=+0.07   spans 0
shipped -> c_w50_cb64      +92.4 +- 51.1 us  t=+1.81   spans 0
shipped -> a_w20_cb64      +84.0 +- 35.3 us  t=+2.38   spans 0
shipped -> a_w50_cb64     +137.8 +-124.7 us  t=+1.11   spans 0
shipped -> a_w20_cb200    +927.7 +- 84.7 us  t=+10.96  EXCLUDES 0
shipped -> a_w50_cb200   +1002.4 +- 90.7 us  t=+11.05  EXCLUDES 0
```

**All seven point estimates are >= 0**: not one alternative cell is even
nominally faster than `c_w50_cb200`. Under the advisor's asymmetric integration
rule (R113 #4 — ship on a verified positive or do not ship) there is nothing
here to land, and that is the correct outcome rather than a failure to find one.

### 7.2 The attribution answer: the command-buffer caps own the elasticity

```
cadence x CB   (cadence@cb200 - cadence@cb64)   +887.9 +- 51.9 us  t=+17.09  EXCLUDES 0
cadence x BFS  (cadence@w50   - cadence@w20)     +37.0 +-105.7 us  t= +0.35  spans 0
BFS x CB       (BFS@cb200     - BFS@cb64)        +48.2 +- 62.7 us  t= +0.77  spans 0
```

The cadence effect by cell:

| cell | cadence `at:0,7` penalty | t |
|---|---|---|
| cb200 (ranked), BFS 50 | **+1002.4 +- 90.7 us** | +11.05 |
| cb200 (ranked), BFS 20 | **+896.4 +- 48.6 us** | +18.43 |
| cb64, BFS 50 | +45.5 +- 77.8 us | +0.58 |
| cb64, BFS 20 | +77.4 +- 83.8 us | +0.92 |

So of the three factors that the low-memory branch changes at once, **only the
`MLX_MAX_OPS_PER_BUFFER` / `MLX_MAX_MB_PER_BUFFER` caps carry the sign flip.**
BFS width is null on this axis and null in interaction with it.

Mechanism, and it is the weakest hypothesis that covers all four cells: the
decode step has two independent flush constraints — the explicit `asyncEval()`
fire mask (`LagunaRuntimeModel.swift:11478,11695-11712`) and MLX's own
ops-per-command-buffer cap. **Whichever binds first sets the real commit
cadence.** At the ranked 200 ops/buffer the fire mask binds, so deleting fire
points starves the GPU for ~1 ms/step. At 64 ops/buffer MLX already flushes more
often than any mask in this family, so the mask is inert. This predicts, without
further tuning, that the axis is flat for any mask denser than the cap — which is
exactly what the density ladder found independently (§2a, `N-DENSITY-SATURATED`).

**Consequence for the whole campaign, now with an interval:** a sub-64 GiB M4
that has not exported `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` runs at 64/128 and
is **structurally blind to every command-buffer-structure axis** — not noisy
about it, blind, with the effect attenuated 887.9 us/step, |t| = 17. It is also
just slower: `c_w50_cb64` costs +92.4 +- 51.1 us/step versus the ranked caps.

### 7.3 `MLX_BFS_MAX_WIDTH` 50 vs 20 — the §6 open item closes NULL

```
BFS 50->20 | cb200 (ranked cadence + caps)   +31.4 +- 58.3 us  t=+0.54  spans 0
BFS 50->20 | cb64                            -85.8 +- 58.5 us  t=-1.47  spans 0
```

The programme-recognised, never-measured compiled default
(`LagunaRuntimeWeights.swift:384`, provenance cited as two *receipt IDs*, not
commits) is now measured on the ranked configuration. **It is not wrong**: the
point estimate favours keeping 50, the interval spans zero, and the sign is not
even stable across the CB factor (BFS x CB is itself null, so the apparent flip
is noise). Bit-exactness held despite the fusion change.

Closure **`N-BFS-WIDTH-NULL-AT-RANKED-CADENCE`**: `MLX_BFS_MAX_WIDTH=50` is
adequate and reverting it to MLX's stock 20 has no defensible upside. Anyone
reopening this needs a mechanism, not a sweep.

### 7.4 The economic closure: this axis is in the tau ~ 1 % regime

Every knob in this study moves **only where MLX flushes**. Bytes read per token,
FLOPs, kernels, and outputs are all identical — the single golden hash across
eight cells is the proof. By the campaign's transfer split (real DRAM/work
changes tau ~ 106 %, pure dispatch/launch overhead tau ~ 1 %), the decode commit
cadence axis is squarely dispatch overhead, so **M5 value ~ 1 % of any M4
magnitude measured here.**

That retires the shelved `d21` candidate on economics rather than on power:
+79.5 us/step on M4 x tau ~ 1 % x 0.0070 %/us => **~0.006 % of M5 score.** It is
not worth the ~2.4 h of M4 time that resolving it would cost, and I withdraw the
"only worth M5 time" recommendation in §2a in favour of **closed**.

The same argument applies in our favour to the ~1000 us/step penalty: it is
almost certainly not a 7 % M5 cliff either. What it is, unambiguously, is an
instrument hazard.

### 7.5 Status line requested by the advisor (R113)

- **Measured:** the assigned axis, end to end, on the ranked-equivalent
  configuration. Sparser cadence **+1002.4 +- 90.7 us/step slower**
  (CI excludes 0); denser cadence flat; the full 2x2x2 has **no cell faster than
  shipped**.
- **Interval:** the only intervals that exclude zero are penalties. My best
  candidate-shaped interval is `d21` at +79.5 +- 48.7 us/step (t=1.63, spans 0),
  and §7.4 prices it at ~0.006 % of M5 score even if real.
- **Terminal deliverable:** a **documented negative** — `N-CADENCE-OPTIMAL` plus
  five other closures — and one quantified instrument-validity finding (§1, §7.2)
  that protects every future M4 study on this campaign. **Nothing to integrate;
  please close it clean.** I am explicitly *not* asking for a queue slot.

---

## 8. Incidental hygiene finding (reported, not acted on)

`Sources/MLXFastModel/LagunaRuntimeWeights.swift:389-394` ships a
`DARKBLOOM_PROBE_CB_OPS` block whose own comment reads *"LOCAL PROBE ONLY (not
for submission)"*, and which uses `overwrite=1` to beat the shipped 200. It is
inert on the official run (the env vars are unset), so this is a **byte-budget
and hygiene** issue, not a correctness one.

I did **not** remove it: it is outside my declared submitted path, and another
student may currently be sweeping with it.

Separately, the comment at `LagunaRuntimeWeights.swift:382` cites "776a79e1 /
dda29d26" as if they were commits. They are **receipt IDs**
(`research/nezuko_receipt_corpus.csv:696,702`).

---

## 9. Reproduction

```bash
# driver (arms are 'name|VAR=VAL[;VAR=VAL...]', space separated)
ARMS_SPEC='...' OUT=research/r109-cadence/<study> DEADLINE_EPOCH=<epoch> \
  /bin/bash research/frieren_r109_env_ab.sh <BLOCKS>

# analysis (paired, blocked, argmax-debiased; logs to W&B)
python3 research/frieren_r109_analyze.py research/r109-cadence/<study>/results.jsonl \
  --tag <name> --control <arm>

# Stage-2 only: within-block paired factorial contrasts (drift-immune)
python3 research/frieren_r109_stage2_factorial.py \
  research/r109-cadence/stage2/results.jsonl
```

W&B evidence: `nh6ktvwi` (Stage-2 factorial, 32 runs), `940a3j8e` (density
ladder), `4j9nfd3u` (startup-profile parity), project
`wandb-applied-ai-team/mlxfast-maple`.

The driver reverses arm order on even blocks (ABBA), emits `@@BLOCK`, `@@RUN`,
`@@LOWMEM_NOTICES`, `@@DEADLINE`, `@@DONE`, and supports continuation via
`BLOCK_OFFSET`. The analyzer's normalised score is
`ns = (0.013890/decode_spt)^0.75 * (0.0003845/prefill_spt)^0.25`.

**Every study in this report other than the withdrawn Stage-1 screen was run
with `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`.** Gate every future study on
`@@LOWMEM_NOTICES=0`, a single golden hash, and `passed_correctness=true` on
every run.

---

## 10. Suggested follow-ups (not implemented)

1. **Audit the flag.** Nobody knows which historical M4 results carried
   `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`. A grep-level audit is cheap and
   could invalidate or rescue several archived conclusions. §1a deliberately
   makes no claim about any specific past result — but somebody should check.
2. **Make the hazard loud.** The low-memory branch should emit a one-line stderr
   warning whenever it overwrites an experimenter-set `MLX_*` variable. My own
   Stage-1 screen would have been saved by that line.
3. **`d21`** — closed on economics in §7.4, not shelved. No follow-up needed.
4. **Remove the `DARKBLOOM_PROBE_CB_OPS` probe block** (§8) once no student is
   sweeping with it; it costs submitted bytes for zero ranked effect.
5. **A valid fine-grained instrument.** §3 and §4 together mean this campaign
   currently has *no* instrument that can resolve 10 us/step on a
   command-buffer-structure axis. That gap is worth its own assignment.
