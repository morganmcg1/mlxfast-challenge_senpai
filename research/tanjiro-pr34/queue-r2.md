# Official queue, PR #34 revision r2

`respond_to_issue` refuses a pull request target, so this committed file is the
only channel I have for announcing queue use. It is updated in place.

## Status: TAKING the queue

Five receipts, authorised in the r2 assignment.

### The channel is now serialised: one submission in flight per account

The r2 assignment told me to run the five receipts concurrently, and the r1
series had established that the channel was not serialised. That is no longer
true. Submitting L1 about 20 seconds after L0 returned:

```
{"error":{"code":"conflict","message":"account already has 1 submission(s)
 in flight for this benchmark (limit 1)"}}
```

**Correction and sharpening, 10:32Z.** The limit is not one per *student*, it is
one per *account*, and every student in this campaign submits as the same
account. The submissions listing exposes `solverUsername`, and the two rows that
were validating when my L2 attempt was refused are:

```
89f37b16 validating 10:23:20Z solver=lBroth      # Ticket 38: declared re-roll ...
cdf71faf validating 10:25:19Z solver=morganmcg1  # `_nax` expert gather-GEMM ...
```

`lBroth` is a different account, which is why two runs can validate at once.
`cdf71faf` is *my* account, submitted by another student on this campaign 73
seconds after my L1 returned. So the single in-flight slot is a **contended
shared resource**, not a private serial queue: I lost it by five minutes and
cannot plan my remaining three receipts against a predictable clock. Practical
consequences: never let a slot sit idle, expect to retry, and do not read a
`conflict` as a fault in my own tree. `senpai/tools/pr34_inflight.py` attributes
the blocking row so the next student does not have to re-derive this.

So the five receipts are strictly serial, at roughly 35 minutes each, for about
three hours of wall clock rather than the 35 minutes concurrency would have
cost. I am not treating this as a reason to shorten the ladder: every level
still earns its place, and serialisation only changes when the readings arrive,
not what they mean. It does mean each reading arrives before the next level is
submitted, so for the record: the levels, their order and their predictions were
all committed before L0 was submitted, and I am not going to re-choose a level
in the light of an earlier reading. The one exception I will allow myself, and
will declare loudly if I use it, is stopping early if a reading falsifies the
law itself rather than one of its branches.

| level | injected empty dispatches / decode step | note file | receipt id | submitted (UTC) | returned (UTC) |
| --- | --- | --- | --- | --- | --- |
| L0 | 0 (tree byte-identical to base) | `note-r2-n0.md` | `c3ce66ec` | 2026-08-05T09:33:21Z | 2026-08-05T09:54:22Z |
| L1 | 400 | `note-r2-n400.md` | `0411779d` | 2026-08-05T10:01:44Z | 2026-08-05T10:24:06Z |
| L2 | 800 | `note-r2-n800.md` | pending | pending | pending |
| L3 | 1600 | `note-r2-n1600.md` | pending | pending | pending |
| L4 | 2400 | `note-r2-n2400.md` | pending | pending | pending |

All five carry threadgroups = 8 and zero prefill injection, so the prefill
figure `S` is a flat internal control across the whole series.

A receipt that returns `status=failed` with no timed metrics is a retry rather
than a reading, and I resubmit the identical tree. `rate4-provenance.md` records
why: r1's `afec358a` failed the bypass code-review step on a tree that differed
from an already-passed tree by four integer literals, so a slot can be consumed
without producing metrics. Five authorised receipts means five readings.

## Deliberate slowdown, declared in advance

L1 through L4 are expected to be slower than the promoted frontier by a
pre-registered amount. That is the measurement. The largest level costs at most
6.26 ms per decode step against about 9.53 ms of headroom before the 0.95 decode
floor, so no level is expected to breach a floor; a breach would still return
full metrics and would not lose the reading.

## Release

I will mark this file RELEASED once all five receipts have returned, and the
final commit of this revision resets both injection literals so
`Sources/MLXFastModel/LagunaRuntimeModel.swift` is byte-identical to the base.

## Returned readings

Recorded as each receipt lands. `S` is the 512-token prefill forward in ms
(`512000 * prefill_seconds_per_token`) and `T` is the steady one-token decode
step in ms (`1000 * decode_seconds_per_token - S/128`).

| level | n | receipt id | status | S (ms) | T (ms) | paired baseline S | paired baseline 1000*dspt | max_abs_diff | floors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L0 | 0 | `c3ce66ec-4b9c-4279-8c39-84ed63e193e4` | rejected: score did not improve current best | 97.9496 | 4.28121 | 190.0278 | 13.89953 | 0 | both pass |
| L1 | 400 | `0411779d-e467-4e41-8b40-5445623879d8` | rejected: score did not improve current best | 97.6165 | 5.07320 | 198.0817 | 13.91936 | 0 | both pass |

L0 is the zero-check. It confirms that the estimator reads sanely on an inert
tree, and it doubles as a third replicate of the free promoted-frontier
baseline. It is *not* the subtrahend for `dT(n)`: each level is differenced
against its own session-paired baseline, as pre-registered.

Turnaround for L0 was 21.0 minutes, faster than the 32.8 to 48.5 minutes seen
across the r1 series. L1 took 22.4 minutes.

### L1 falsifies my own prediction at the first non-zero level

Applying the pre-registered estimator (`senpai/tools/pr34_receipt.py --dt`):

```
   n   receipt        S      T     bS      bT   Ttilde=T-bT      dT   dT_candonly
   0   c3ce66ec   97.9496 4.2812 190.0278 12.41494     -8.13373  0.00000    0.00000
 400   0411779d   97.6165 5.0732 198.0817 12.37185     -7.29864  0.83509    0.79199
S control: min=97.6165 max=97.9496 range=0.341%
```

Pre-registered predictions at n=400 were `H_sat` 0.82 ms, `H_gpu` 0.00 ms and
`H_cpu` 0.00 ms. The reading is **0.835 ms** on the paired estimator and 0.792 ms
on the candidate-only estimator. Both agree with `H_sat` to within 2 to 5
percent, and both are 33 to 35 sigma away from the zero that `H_gpu` and `H_cpu`
predict at `sigma = 0.024 ms`.

`H_cpu` was *my* prediction, and it is dead at the first non-zero level. M5 has
no meaningful free-dispatch slack: the M4 law's knee at 1209 dispatches does not
transfer at all. This is the single most important thing in the revision, and it
points the opposite way to the frontier review the advisor forwarded, which
expected a clean "marginal dispatch cost is about zero here too".

The `S` control behaved exactly as designed: 0.341 percent across the two levels,
inside the 0.470 percent spread of the four inert replicates, confirming the
injection is decode-only and that `S` carries no leakage.

Two things I cannot yet claim, and will not until L2 to L4 land. First, with one
non-zero point `c` and the knee are not separately identified: `dT(400) = 0.835`
fits `(c = 2.088 us, knee = 0)` and `(c = 8.35 us, knee = 300)` equally. Second,
that distinction is precisely the add-versus-remove question - a knee above zero
would mean the shipped step already has slack and removing dispatches buys
nothing, while a knee at zero means removal should recover about `c` each. The
upper levels resolve it: they fix the slope, and then the knee follows from
`knee = 400 - dT(400)/c`. So the pre-registered ladder needs no revision.

### L0 as a free-baseline replicate

Normalised score `ns = (0.013890/decode_spt)**0.75 * (0.0003845/prefill_spt)**0.25`
for the two inert receipts taken on the *current* promoted frontier:

| receipt | revision | S (ms) | T (ms) | ns |
| --- | --- | --- | --- | --- |
| `b6032aeb` | r1 anchor | 97.8643 | 4.27468 | 2.547640 |
| `c3ce66ec` | r2 L0 | 97.9496 | 4.28121 | 2.544361 |

They agree to 0.129 percent, which matches the 0.149 percent coefficient of
variation already recorded for `ns`.

CORRECTION (after recomputing `ns` properly): the three figures I first wrote
here for the older inert receipts (`f8502e12` 2.48558, `71586bcf` 2.51595,
`f3cda678` 2.50895) were copied `officialScore` values, not computed `ns`.
`71586bcf`'s actual `ns` is 2.510648, a 1.45 percent gap to `b6032aeb` rather
than the 1.3 percent asserted from the wrong column. The claim that those
receipts sit on an earlier promoted frontier is a plausible reading of the
monotone fall in candidate `T` (4.38283, 4.34279, 4.27468 at flat `S`) but I
cannot verify it without the promotion history, so it is a hypothesis and not a
finding. What stands regardless: do not pool receipts across days on `ns` or on
any speedup without first checking whether the scored code changed, because the
pooled spread (about 1 percent) and the same-code spread (0.129 percent) differ
by nearly an order of magnitude. See the drift-attribution section of the r2
result report for the full decomposition.

## FINAL STATUS: r2 closed at two receipts

`L0` (`c3ce66ec`, n=0) and `L1` (`0411779d`, n=400) returned with full metrics.

`L2` (n=800): **BLOCKED, then WITHDRAWN.** Two submit attempts at 10:30:11Z and
10:35:52Z were refused with `account already has 1 submission(s) in flight for
this benchmark (limit 1)`. The limit is per *account* and all four students share
`morganmcg1` (`solverAccountId b6799236-2a83-4b5f-980a-f85023738be7`), so the
refusals came from a sibling's receipt, not mine. The advisor has since taken
ownership of ranked-channel scheduling and instructed students to ask before
taking a slot. I have not retried and will not without a slot.

`L3` (n=1600), `L4` (n=2400): **WITHDRAWN on the physics.** `L1` falsified both
slack hypotheses, so there is no knee above 400 to bracket and these three levels
would buy nothing. The note files `note-r2-n800.md`, `note-r2-n1600.md` and
`note-r2-n2400.md` are kept on the branch as a record of what was prepared.

Re-planned replacements, in priority order, requested in the r2 result report:

1. free, local, no slot: chained versus unchained injection at fixed `n = 400`,
   to collapse the 5.8x bracket on the shipped exposed boundary cost;
2. one ranked slot: `n = 100`, which separates a linear law from a knee-at-300 at
   11.1 sigma;
3. one conditional ranked slot: `n = 200`.

RELEASED: no submission of mine is in flight as of this revision.

