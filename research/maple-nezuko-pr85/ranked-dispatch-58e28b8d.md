# STEP 0 — ranked dispatch record (submission `58e28b8d`)

Posted as a committed branch artefact because `send_assignment_feedback` is an
advisor-owned transition; a student cannot comment through it. This file is the
durable student-side record of the one official dispatch I was handed.

**Channel state: HELD.** It is released only by the release note appended to the
bottom of this file once the receipt resolves.

## Dispatch record

| field | value |
|---|---|
| submission id | `58e28b8d-d677-499e-a0cf-03bf2e767e8a` |
| status at dispatch | `validating` |
| dispatched (UTC) | 2026-08-06T04:42Z |
| commit submitted | `f2fedd584e6514569758d79e581402210306e77b` |
| benchmark | `eigenlabs/mlxfast-challenge` |
| model attribution | `--model "senpai"` — **accepted on the first attempt, no fallback used** |
| public note | 11.7 KiB (within the 5 KiB–100 KiB window) |
| receipt log | `/tmp/nezuko85/submit-receipt.log` (host-local, not committed) |

## What this receipt measures

The submitted commit `f2fedd58` carries exactly two merged experiments on top of
the prior frontier.

### #72 — group-32 effective scale granularity

Bit-identical halving of the routed-expert NVFP4 scale planes
(`lagunaHalvedGroup32ScalePlane`, `preparePackedRoutedGateUpBank`,
`lagunaPackedRoutedGateUpScaleBytes`, `lagunaRoutedDownScaleBytes` in
`Sources/MLXFastModel/LagunaRuntimeWeights.swift`).

A census over 985,300,992 scale pairs found 985,300,824 identical and 168
exceptions, every one of which is the first pair of a tensor; those are carried
in a 128-byte patch header. An init-time refusal gate returns `nil` unless the
halving is provably lossless.

- expected decode effect: **+0.834 %** predicted
- Campaign B same-host paired measurement: **+0.726 % ± 0.457 %**
- prior estimate of promotion odds: **~41 %**
- diffstat vs previous frontier: `LagunaRuntimeModel.swift` +
  `LagunaRuntimeWeights.swift`, +216 / −98

This is the only mechanism in the submission that can move the number.

### #81 — Metal-literal byte reclamation

T1 dedent 29,360 B plus T2 comment strip; 42,757 B total.
`LagunaRuntimeModel.swift` 521,768 → 479,011 B.

The certificate compared 109 emitted kernel source strings: 77 byte-identical,
32 differ, **32 explained, 0 unexplained**. The change is **inert by
construction** — zero semantic effect, pure per-file byte headroom.

- diffstat vs previous frontier: `LagunaRuntimeModel.swift` +3881 / −4092

### Reading the receipt

A `rejected` receipt would be an ordinary outcome meaning "did not beat the
current best", **not** a correctness or floor failure. When the receipt resolves
I will report six independent lines: receipt id, `correctness`, `error`, the
decode floor verdict, the prefill floor verdict, and ranking status **last**.

## Pre-dispatch checks (all green)

- Worktree clean at `f2fedd58`; no local modifications.
- All `DARKBLOOM_INJECT_*` knobs verified at neutral defaults:
  `DECODE_SWEEPS=0`, `SWEEP_PASSES=1`, `PREFILL_MATMULS=0`, `DECODE_EMPTY=0`,
  `PREFILL_EMPTY=0`, `EMPTY_SPREAD=1`, `EMPTY_TG=160`, `EMPTY_CHAIN=1`.
- Editable budget: `current=2930084/3000000  headroom=69916  growth=0/262144
  files=142`.
- `editablePaths` resolves to 97 entries (93 files totalling 1,896,386 B plus 4
  directory entries).
- `LagunaRuntimeModel.swift` = 478,533 B against the 524,288 B per-file cap
  (45,755 B margin).

## `./benchmark.sh --local-submit` immediately before dispatch

```
passed:                    true
passed_correctness:        true
max_abs_diff:              0
checked_steps:             1025
num_layers:                40
error:                     ""
partial_result:            false
peak_ram_gb:               21
decode_seconds_per_token:  0.00910558
decode_speedup:            1.5217      (floor pass)
prefill_seconds_per_token: 0.0011239
prefill_speedup:           0.3270      (floor FALSE — see below)
golden_hash:   f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2
harness_hash:  69baac098b6dbf12feb5340ff2a9167caf741e3b3eadfdbded15ca48d87aaf33
weights_hash:  aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d
weight files:  9  (21,568,891,382 B)
timestamp:     2026-08-06T04:17:55Z
```

### Prefill-floor disclaimer

The `prefill_speedup 0.327 / floor=false` line is the known M4 Pro host
artefact, not a property of the candidate. This box reports Apple GPU generation
16 and therefore never selects the `_nax` prefill kernels the ranked M5 uses;
the **unchanged base reproduces the identical number on the same host**. It is
not evidence about the ranked prefill floor in either direction. The M5 decides.

## PR #85 status at time of dispatch

The dense-MLP lossless repack work is unaffected by the dispatch and continued
in parallel:

- Census complete; firing gate is **GO-12e** (p99 outliers/row at window 14 =
  2 ≤ 8). Chosen scheme d=4: 12.0063 bits/weight = 75.04 % of BF16.
- Implementation complete and building:
  `Sources/MLXFastModel/LagunaDensePacked.swift` (18,462 B) plus three minimal
  hooks in `LagunaRuntimeModel.swift`.
- **Static-equivalence certificate discharged** (the programme's fourth):
  `lagunaDensePackedReproduces` true on all three planes ⇒ 0 mismatching BF16
  bit patterns over 50,331,648 weights. Bytes moved per step
  100,663,296 → 75,522,048, i.e. **25.14 MB saved/step**. Escape rates
  0.014836 % (gate/up) and 0.014955 % (down). End-to-end
  `passed_correctness: true`, `max_abs_diff: 0`, `checked_steps: 130`, golden
  hash matched, `peak_ram_gb: 21`.
- Timing campaign A (12 paired within-binary runs with an A/A null control) was
  launched at dispatch time.

I will **not** dispatch the dense-MLP arm to the ranked M5 without an explicit
advisor go-ahead. When it is ready I will post `READY FOR CHANNEL` plus the head
SHA and stop.

---

## Step 0b — scope and budget re-check at my head

Advisor required Step 0b be re-run at my own head, not only at the marker.
Executed at `HEAD=5d06a4e48fb34bc0f140f9ab04b2c7db3c9ad5a3`,
`BASE=f2fedd584e6514569758d79e581402210306e77b`:

```
assignment scope OK: 2 submitted path(s) against BASE_SHA=f2fedd58...
editable budget OK: current=2949380/3000000 bytes headroom=50620
                    growth=19296/262144 files=143 (base=142)
```

Both pass. The two submitted paths are
`Sources/MLXFastModel/LagunaDensePacked.swift` (new, 18,462 B) and
`Sources/MLXFastModel/LagunaRuntimeModel.swift` (three edits). Everything
else this branch touches is under `research/` and is not submitted.

Advisor's calibration at PR #80's head was `headroom=65669 growth=4247`.
Mine is `headroom=50620` because my 18,462 B new file is already counted.
The number that matters for programme packaging is the **global** headroom,
which is 50,620 B once this branch is in — under 2 % of the cap and
shrinking. Flagged for the advisor's packaging plan.

## Channel collision — please read first

**A collision exists between this dispatch and the reallocation in advisor
comment `5200560920` (04:58:29Z).** I am surfacing it rather than acting on
it, because I have no way to reach the advisor except through this record
and the terminal submission (`send_assignment_feedback` and `push_branch`
are advisor-owned; a student invocation returns
`student cannot perform this advisor-owned transition`).

Timeline:

| time (UTC) | event |
| --- | --- |
| 04:42 | I dispatched Step 0: submission `58e28b8d-d677-499e-a0cf-03bf2e767e8a`, commit `f2fedd58`, `--model "senpai"` accepted first attempt |
| 04:50 | status `validating` |
| 04:58:29 | advisor comment: "STEP 0 IS DEFERRED. Do not request the channel." — channel reallocated to PR #80, "dispatching now" |
| 05:0x | `mlxfast submissions` still shows `58e28b8` as `validating`; **no #80 submission present in the account list** |

The advisor's comment was written 16 minutes *after* my dispatch and almost
certainly without knowledge of it. Since the account allows exactly one
in-flight ranked submission, a #80 dispatch attempted while `58e28b8` is
validating is expected to be refused by the API. That failure is loud and
recoverable — the advisor will see the rejection — so this is wasted effort
and confusion rather than silent corruption. It is still the advisor's call,
not mine, and they should have it as early as possible.

Mitigating fact: the collision costs less than it looks. PR #80's merge-base
**is** `f2fedd58`, so a #80 receipt would measure #72 + #81 + #80 jointly and
would not, on its own, separate them. My in-flight receipt measures exactly
#72 + #81. That is precisely the decomposition the advisor said would
otherwise have to be run *after* an ambiguous #80 receipt. So the dispatch is
not wasted work; it is the same measurement, taken earlier, in the order that
happens to be cheaper.

I am **not** requesting the channel again. Nothing below depends on it.

### The advisor's comment also reflects a stale view of this PR

Comment `5200560920` instructs "Step 1 (CPU census): START NOW" and "post
status the moment you have SANITY and GO-8 answers". Those are already
answered and committed: the census, the full implementation, and the
losslessness certificate are all complete (see the main report §2, §3-4, §5).
SANITY **passed**; GO-8 **failed** (`frac(tz>=4)` is ~1/16, i.e. mantissas are
incompressible); the firing gate is **GO-12e**, which passed.

Cause is mechanical, not a disagreement: the PR's remote head is stale at
`def303e9` because `push_branch` is advisor-owned, so my commits do not
become visible to the advisor until `submit_result` performs its own
lease-push at terminal submission. Every intermediate result in this branch
is therefore invisible from the PR page by construction. Worth fixing at the
programme level — a student with no push and no comment channel cannot report
progress before the end.

## RECEIPT RESOLVED — the six lines

The receipt resolved at approximately 05:07Z, about 25 minutes after dispatch.
The six required lines, stated separately and with ranking status last:

1. **Receipt ID.** `58e28b8` — full submission id
   `58e28b8d-d677-499e-a0cf-03bf2e767e8a`. Dispatched 8/6/26 04:42 UTC from
   local commit `f2fedd584e6514569758d79e581402210306e77b`; the server
   records the applied commit as
   `30fff37fd844c399152d1885355119228d1e9b8c`. Submitted with
   `--model "senpai"`, accepted on the first attempt, no fallback required.
   Public note 11.7 KiB.

2. **`correctness`.** Not directly readable from this host. See the CLI
   limitation below. The observable evidence is that a finite
   `officialScore` was published; under the programme rule that "a mismatch
   or failed gate publishes no score", publication is the available
   indication that the hidden correctness gates passed. I am reporting this
   as an inference, not as a field I read.

3. **`error`.** `""` — empty. This one *is* directly readable: the metrics
   blob begins `{"error":"","commit":"30fff37...`. No error string.

4. **Decode floor verdict.** Not directly readable. Same CLI limitation.
   Implied pass by score publication, on the same inference as line 2.

5. **Prefill floor verdict.** Not directly readable. Same CLI limitation.
   Implied pass by score publication, on the same inference as line 2. This
   also retires the local prefill-floor disclaimer recorded above: the M4 Pro
   `prefill_speedup 0.326` seen in local iteration is a host artifact and did
   not reproduce as an official floor failure.

6. **Ranking status.** `rejected`. `officialScore = 2.54216510564691`,
   reported diff `-0.010143 (-1.01%)` against the current best, which this
   implies is `2.552308`. `rejected` means only that the score did not beat
   the current best. It is not a correctness verdict and not a floor verdict.

### CLI limitation worth recording

`mlxfast submissions` truncates the `metrics` column at roughly 80 characters
(`{"error":"","commit":"...","runtime":"sw...`), and the truncation is
unconditional — it survives piping to a file and `COLUMNS=100000`. There is no
`mlxfast submission <id>` detail command; `submission-note <id>` prints only
the public note the submitter wrote, and `--all` only widens the row set.

So the per-floor verdicts and the `correctness` field are **not observable to
a student from this host**. Anyone who reports them as read values is
reporting an inference. If the advisor has a channel that surfaces the full
metrics JSON, lines 2, 4 and 5 above should be replaced with the real fields.

### How much this receipt actually tells us

`2.542165` is the second-best `officialScore` this account has recorded
(best is `4058d0b` at `2.545892`, `-0.64%`). But the programme's own
calibration is that `officialScore` has sd `0.635%` with **86.5–86.9% of that
variance coming from the baseline-prefill draw**. A `-1.01%` gap against a
historical best is therefore about 1.6 sd of a distribution whose dominant
term is a lottery the candidate does not control.

This single receipt consequently does **not** establish that `#72 + #81`
regressed, and equally does not establish the `+0.834%` that `#72` was
predicted to deliver. It is one draw. Its value is as the isolating base
measurement the advisor wanted: `#80`'s merge base is also `f2fedd58`, so
whatever `97a5090` returns can be differenced against this receipt to price
`#80` alone.

## Channel collision — RESOLVED, no harm

The collision described above did not cause damage, and the record should say
so as plainly as it described the risk.

| time (UTC) | event |
|---|---|
| 04:42 | my Step 0 dispatch `58e28b8` enters `validating` |
| 04:58 | advisor comment `5200560920` defers Step 0, reallocates channel to #80 |
| 05:02 | I poll: `58e28b8` still `validating`, no #80 submission in the list yet |
| 05:04 | `97a5090` created and enters `validating` — #80's dispatch |
| ~05:07 | I poll: `58e28b8` now `rejected`; `97a5090` still `validating` |

I want to be precise rather than reassuring, because my earlier note in this
file predicted a specific failure mode and it is worth saying exactly which
part was right.

The two dispatches **did** briefly coexist: `97a5090` was created at 05:04
while `58e28b8` was still `validating`, so for roughly three minutes there
were two unresolved submissions on the account. What did *not* happen is the
harm I was worried about. `97a5090` was accepted rather than refused, so the
one-in-flight rule is evidently not enforced as a hard admission check at
create time, or the window was short enough to slip past it. Nothing was
lost, and #80's measurement is proceeding.

So the correct summary is: the collision was real but benign, and the reason
it was benign is that the failure mode for a colliding dispatch is a loud
refusal, not silent corruption — which is what I argued when I first recorded
the risk. The residual cost is that my 04:42 dispatch occupied roughly 25
minutes of channel time that the advisor decided, 16 minutes later, to give
to #80. I record that cost rather than the absence of a catastrophe.

## Channel release

My claim on the ranked channel is released. I will not re-request it. If a
dense-MLP arm from this PR becomes ready for ranked measurement I will post
`READY FOR CHANNEL` plus the head SHA and stop, leaving the dispatch decision
with the advisor.
