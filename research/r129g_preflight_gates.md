# R129-G: a pre-flight gate script that has been observed to fail

```
PREFLIGHT SCRIPT: research/tools/preflight_gates.sh
GATES IMPLEMENTED: 8  OBSERVED-TO-FAIL: 8  UNVERIFIABLE: 0
RUN IT LIKE THIS: DARKBLOOM_STARTUP_MEMORY_PROFILE=full bash research/tools/preflight_gates.sh --base-sha <BASE_SHA>
RUNTIME: 3-4 s (negative-control suite: 21 s)
KNOWN NUMBER I COULD NOT REPRODUCE: budget 2681206/3000000 headroom=318794 files=142 -> actual today 2712490/3000000 headroom=287510 files=143
```

Three corrections that matter before the next fire, then the gate table.

## 1. The brief's budget number is stale by 31,284 bytes

`senpai/check-editable-budget.sh` against the assignment base:

```
$ bash senpai/check-editable-budget.sh 9f7cafdad608993ea97b901aa2f87d3dcb2d7d5f
editable budget OK: current=2712490/3000000 bytes headroom=287510 growth=0/262144 files=143 (base=143)
```

The brief's `2681206 / headroom 318794 / files 142` was correct at the older
frontier `adfca1e5`. Running the same tool with `adfca1e5` as the base yields
`growth=31284`, `base=142`, and `2712490 - 31284 = 2681206` exactly. The single
file added between the two is
`Sources/MLXFastModel/LagunaOProjGeometry.swift`
(`git diff --diff-filter=A --name-only adfca1e5 HEAD -- Sources Vendor`).

Consequence: planning against 318,794 bytes of headroom overstates the real
figure by 31,284 bytes. The `budget` gate reads the number from the trusted
script at run time rather than pinning a constant, so it cannot go stale the
same way.

## 2. `golden hash b9509697...` is an input-fixture hash, not an output hash

Full value, from `research/pr270-logs/f1-iterate.on.json`:

```
b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63
```

`.github/scripts/verify-correctness-golden.sh` shasums the fixture file
`correctness_golden.json` and compares it to
`MLXFAST_EXPECTED_CORRECTNESS_GOLDEN_SHA256` / `_BYTES` (plus `_STEPS: "64"`,
`.github/workflows/benchmark.yml:212`). And the workflow *computes* that
expected hash from the fixture it just generated
(`.github/workflows/benchmark.yml:1435-1439`) rather than comparing against an
organizer-pinned constant.

So a matching `golden_hash` proves the harness consumed the fixture we think it
did. It does **not** prove correctness passed, and it is not a hash of model
output. Two useful consequences:

- The gate is a `shasum -a 256` on one file: cheap, no build, no weights.
- Nobody should read a matching golden hash in a receipt as evidence that the
  64-step drift tripwire agreed with anything.

## 3. `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` is only mandatory below 64 GiB

`Sources/MLXFastModel/RuntimeStartupMemoryPolicy.swift`: unset or `auto`
resolves to low **iff** `physicalMemory < fullProfileMinimumPhysicalMemoryBytes`
(64 GiB). `full` and `low` force the choice. Any other value hits
`preconditionFailure` and aborts the process.

So a naive "the variable must be set to `full`" gate would wrongly block a
128 GiB M5 where unset already resolves to full, and would miss the real hazard
on a small host: unset silently resolving to LOW. The gate therefore asserts the
*resolved* profile for this host's actual RAM, and separately rejects an illegal
value. On this 48 GiB host, unset is a FAIL.

## Gate table

Every gate is static: no `swift build`, no metallib, no model load, no GPU. All
eight FAIL lines below were produced by an actual injected defect, not reasoned
about. Defects were injected into a detached `git worktree` scratch tree
(`research/tools/preflight_negative_controls.sh`), never into the branch; full
transcript in `research/r129g-controls.log`.

| # | gate | what it asserts | injected defect | exit |
|---|------|-----------------|-----------------|------|
| 1 | `budget` | trusted budget script passes vs `--base-sha` | 400,000 B editable file | 1 |
| 2 | `perfile` | no packaged file >= 524,288 B | 600,000 B editable file | 1 |
| 3 | `tree_clean` | packaged surface == HEAD, nothing uncommitted/untracked | appended a comment to `LagunaRuntimeModel.swift` | 1 |
| 4 | `refuted` | no `REFUTED_DO_NOT_LAND` file or marker in the surface | added a refuted `.patch` under `Sources/MLXFastModel/` | 1 |
| 5 | `startup_profile` | resolved profile is `full` and the value is legal | `=low`; `=ful`; unset on 48 GiB | 1 |
| 6 | `qmv_fused` | the known-regressing flag is off | `DARKBLOOM_SHARED_ROUTED_QMV_FUSED=1` | 1 |
| 7 | `nax` | `_nax` reachability matches the host's GPU generation | script copy forced to report M5-class family | 1 |
| 8 | `golden` | `correctness_golden.json` sha256 == expected | flipped one byte of the fixture | 1 |

### PASS run (8/8), unmodified tree

The real fixture and weights do not exist on this host (`setup.sh` has not run
since the disk was replaced), so `golden` was pointed at a stand-in file to
demonstrate the PASS path:

```
$ G=$TMPDIR/r129g-golden-good.json; printf '{"correctness_gates":{}}\n' > "$G"; GS=$(shasum -a 256 "$G"|awk '{print $1}')
$ DARKBLOOM_STARTUP_MEMORY_PROFILE=full MLXFAST_CORRECTNESS_GOLDEN_PATH="$G" \
  MLXFAST_EXPECTED_CORRECTNESS_GOLDEN_SHA256="$GS" \
  bash research/tools/preflight_gates.sh --base-sha 9f7cafdad608993ea97b901aa2f87d3dcb2d7d5f
GATE budget: PASS editable budget OK: current=2712490/3000000 bytes headroom=287510 growth=0/262144 files=143 (file count is diagnostic only; base=143)
GATE perfile: PASS largest packaged file Sources/MLXFastModel/LagunaRuntimeModel.swift 396910 B < cap 524288 B (files=143)
GATE tree_clean: PASS packaged surface matches HEAD 4dbfd025, no uncommitted or untracked packaged files
GATE refuted: PASS no REFUTED_DO_NOT_LAND file or marker in 143 packaged files
GATE startup_profile: PASS override=full -> full profile on a 48 GiB host
GATE qmv_fused: PASS DARKBLOOM_SHARED_ROUTED_QMV_FUSED=<unset> (off; on costs +55.2 us/step, #733)
GATE nax: PASS Apple M4 Pro = GPU gen 16, macOS 26.5.2: is_nax_available() false, no _nax kernels selected
GATE golden: PASS <golden> sha256=<sha> matches the expected fixture
PREFLIGHT: PASS (8/8)
```

Idempotent: two consecutive runs produced byte-identical output, rc=0, 4 s and
3 s (`research/r129g-run1.log`, `research/r129g-run2.log`, sanitised).

On a slot-holding host with weights present the invocation is just
`DARKBLOOM_STARTUP_MEMORY_PROFILE=full bash research/tools/preflight_gates.sh --base-sha <BASE_SHA>`;
`correctness_golden.json` and its expected sha256 are picked up from the repo
and the environment respectively.

### Observed FAIL lines, one per gate

Copied verbatim from `research/r129g-controls.log`. The `PREFLIGHT: FAIL (n/8)`
counts in that log are lower than 7/8 because the scratch worktree also trips
collateral gates (an injected file is untracked, so `tree_clean` fails too, and
no fixture is configured for controls 1-7, so `golden` fails). What matters per
control is that the *targeted* gate flipped from PASS to FAIL and the exit code
was nonzero.

1 `budget` (400,000 B file injected; note `perfile` still passes on the same
tree, so the two gates are not redundant):

```
GATE budget: FAIL rc=1 editable budget: surface is at least 3032887 bytes; total limit is 3000000
GATE perfile: PASS largest packaged file Sources/MLXFastModel/InjectedBudget.swift 400000 B < cap 524288 B (files=144)
PREFLIGHT: FAIL (5/8)
exit=1
```

2 `perfile` (600,000 B file):

```
GATE perfile: FAIL Sources/MLXFastModel/InjectedBig.swift is 600000 B >= cap 524288 B (files=144)
```

3 `tree_clean`:

```
GATE tree_clean: FAIL 1 uncommitted change(s) in the packaged surface:  M Sources/MLXFastModel/LagunaRuntimeModel.swift
```

4 `refuted`:

```
GATE refuted: FAIL refuted patch present in packaged surface: named=[Sources/MLXFastModel/REFUTED_DO_NOT_LAND_tg256_swiglu_qmv.patch ] marker=[]
```

5 `startup_profile`, three separate defects:

```
GATE startup_profile: FAIL override=low forces the low-memory profile; ranked behavior needs full
GATE startup_profile: FAIL illegal value 'ful': resolve() preconditionFailure will abort the run (legal: auto|full|low)
GATE startup_profile: FAIL override=<unset> resolves to LOW on this 48 GiB host; export DARKBLOOM_STARTUP_MEMORY_PROFILE=full
```

6 `qmv_fused`:

```
GATE qmv_fused: FAIL DARKBLOOM_SHARED_ROUTED_QMV_FUSED=1 enables the measured +55.2 us/step regression (#733)
```

7 `nax` — the chip cannot be changed, so the defect is a one-line edit to a
scratch *copy* of the script that reports the M-series family as 5:

```
GATE nax: FAIL Apple M4 Pro is GPU gen 17 on macOS 26.5.2: is_nax_available() is TRUE, so _nax kernels are selected and this is not the gen-16 student-host regime
```

8 `golden`:

```
GATE golden: FAIL <golden> sha256=83e2f1a8... != expected 286108ef...
```

(the two hashes here are the stand-in fixture before and after the byte flip,
not the organizer value quoted in section 2)

## What is deliberately not gated

- **No slow correctness gate.** A real token/golden check needs the 21.6 GB
  checkpoint plus a `--local-iterate` run. Neither exists on this host and both
  would blow the 3-4 s budget that makes the script worth running in the minute
  before a fire. The `golden` gate covers the cheap half of that surface
  (fixture identity) and is honest about covering only that.
- **`_nax` runtime *selection*.** The gate derives reachability from
  `is_nax_available()`'s inputs (macOS >= 26.2 and Apple GPU generation >= 17,
  where gen = 12 + M-series family, so M4 Pro = 16). Asserting that the
  dispatcher actually picked a `_nax` variant requires a model-holding run;
  that is out of scope for a fast static script and is called out in the
  script's header comment rather than silently approximated.
- **No defect-injection harness in the product.** `preflight_gates.sh` has no
  test hooks, no `--simulate`, no injection flags. The negative-control script
  is a separate research file that mutates a throwaway worktree.

## Current state of this host

Running the gates on the real tree with no fixture present gives
`PREFLIGHT: FAIL (6/8)`: `golden` fails with
`correctness golden missing or empty at correctness_golden.json`, and
`startup_profile` fails when the override is unset. That is the correct verdict
—  this 48 GiB host cannot run any correctness gate until `setup.sh` regenerates
the checkpoint and fixture — and it is a useful demonstration that the script
refuses to bless a host that merely looks quiet.

## Advisor's open question (0/40 clean record) — not answered

The advisor asked whether the clean 0-failures-in-40-fires record reflects easy
packaging or active checking, and pointed at
`research/receipts/account_submissions_1254Z.tsv` with reducer
`research/tools/account_draw_record.py`. Neither path exists at the assignment
base `9f7cafda` (no `research/receipts/` directory at all), so there is no local
data to reduce, and I did not query the submission API for it. The question is
left open rather than guessed at.

What the eight gates do say about it: five of the eight defects I injected
(`budget`, `perfile`, `tree_clean`, `refuted`, `golden`) are packaging or
identity errors that the trusted tooling already refuses, which is consistent
with "easy packaging" as the explanation. The three that no trusted tool
catches — `startup_profile`, `qmv_fused`, `nax` — are all *environment* errors
that would silently produce a valid-looking but mistimed run rather than a
rejected receipt. That is where a clean receipt record would be uninformative,
and that is the part of the surface this script is actually worth running for.

## Files

- `research/tools/preflight_gates.sh` — the deliverable. bash 3.2 safe, BSD
  `sed`, no `mapfile`, no `timeout`. `--base-sha <40-hex>` defaults to HEAD.
  Honours `MLXFAST_CORRECTNESS_GOLDEN_PATH` and
  `MLXFAST_EXPECTED_CORRECTNESS_GOLDEN_SHA256`.
- `research/tools/preflight_negative_controls.sh` — research-only; injects one
  defect per gate into a detached worktree and records the FAIL line.
- `research/r129g-controls.log` — full negative-control transcript.
- `research/r129g-run1.log`, `research/r129g-run2.log` — idempotency evidence.

No packaged (`editablePaths`) file was modified by this arm.
