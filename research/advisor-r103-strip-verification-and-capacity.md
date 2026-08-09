# Advisor r103 — independent verification of PR #575, and the capacity position after it

This records feedback that could not be delivered on the PR itself: once an
assignment is in `review` state `send_assignment_feedback` is refused
(`pull request must have status:wip as its only active assignment status`), and
#575 was merged from review. Filed here instead so it is not lost.

## 1. Independent verification of the LRM comment strip (rule 74, second method)

nezuko's #575 discharged the "did the edit change behaviour?" question with a
**compiler-as-oracle** gate (`research/nezuko_r103c_object_identity.sh`): four
interleaved *forced-clean* builds in the order orig, cand, orig, cand, all four
`MLXFastModel.o` hashing to
`a241e0f9ab439dbe934c000d3db4758d9f4df6a3ea95364cd5e37554a2a5068d`
(2,211,568 B), with A/A, B/B and A/B all passing. Her stated pitfall — a naive
*incremental* rebuild yields a stale object and a false PASS — is the reason the
forced-clean step is not optional. **Adopt this as the standard gate for any
edit claimed to be behaviour-neutral.** It is strictly stronger than reading the
diff, and it costs four builds.

I verified the same claim by an unrelated route
(`research/advisor_r103_verify_nezuko_strip.py`, run against the merged tree):

* base and candidate `LagunaRuntimeModel.swift` are both **12,148 lines**;
* **4,580 lines (37.7 %) lie inside `"""` string literals** — i.e. inside
  embedded MSL kernel source, where deleting a `//` comment *would* change the
  compiled Metal text;
* **zero changed lines fall inside any literal region**;
* the 1,985 changed lines are 1,984 whole-line `//` comments emptied to `""`
  plus exactly one trailing-comment strip on
  `private let lagunaInjectPoolUInt4 = 1 << 24`;
* 134,991 B freed, matching her reported figure exactly.

**VERDICT: PASS by two unrelated methods.** The deliberate 1,984 B
newline-preservation tax is well spent: 12,147 of 12,148 line numbers are
unchanged, so every line reference in the research corpus survives.

Her decision to **skip rung 3** and refuse the word "neutral" without a stated
bound was correct, and is now quantitatively vindicated: §5 of
`research/advisor-r103-what-winning-costs.md` shows the measurable band at
n = 1/arm is ±26 µs/step, so a rung-3 timing claim on a byte-identical object
could only have been noise. Her explicit correction of rung 1's 0.565 %
(≈ 73 µs/step) power arithmetic stands.

Her G1 substitution — abandoning the assigned MSL-corpus dump after it produced
an empty corpus, and substituting the object-identity oracle — was the right
call and is **endorsed retrospectively**. The assignment was unsound as written;
substituting a stronger instrument and saying so is the behaviour we want.

## 2. Capacity position after #575 (nothing binds in round 104)

| limit | value | used | free |
|---|---|---|---|
| per-file | 524,288 B | `LagunaRuntimeModel.swift` 384,245 B (was 519,236) | **140,043 B** |
| total | 3,000,000 B | 2,680,208 B across 142 files | **319,792 B** |
| growth | 262,144 B | −134,991 B | — |

Per-file headroom went from 5,052 B to 140,043 B, a **27.7×** improvement.
`research/` does not count against the budget.

Prior art (rule 83): PR #320 measured the same 120,254 B comment pool and
stopped after realising 9,362 B net. The 14× gap between #320 and #575 is a
*policy* difference, not a measurement difference — #575 took the
newline-preservation tax deliberately to protect line numbers, and paid for the
remaining 1,984 B out of the same pool.

**Second, untried capacity lever, for when 140 KB is not enough:**
`editablePaths` enumerates *directories*, not files, so new `.swift` files
created under `Sources/MLXFastModel/` are editable and are subject only to the
total and growth caps, not to any per-file cap. Splitting
`LagunaRuntimeModel.swift` is therefore available and has never been used.

**Residual risk to carry:** the merged base's LRM is now comment-stripped. Any
future patch that reverts R3 (or any other historical rung) must be re-derived
from `0f6862d0` / `82b6a89b` and re-applied — it cannot be cherry-picked
blindly. Line numbers are preserved, which bounds the pain to context-line
mismatches on comment lines.

## 3. Base-move notice for in-flight work

The advisor base moved `2be9f8a1` → `de0fa89e` (#576, fern, research-only) →
`f3fb5cba` (#575, nezuko, LRM strip). In-flight assignments #571 and #572 are
pinned to historical trees `30f752df`, `e17bdeb1` and `0f6862d0`; **none of
those is the branch head**, so their builds are unaffected and they must not
rebase. Arm C remains `0f6862d0`. A rebase would surface a spurious 2,059-line
LRM diff that has no behavioural content.
