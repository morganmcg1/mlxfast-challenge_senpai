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
| L1 | 400 | `note-r2-n400.md` | `0411779d` | 2026-08-05T10:01:40Z | pending |
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

L0 is the zero-check. It confirms that the estimator reads sanely on an inert
tree, and it doubles as a third replicate of the free promoted-frontier
baseline. It is *not* the subtrahend for `dT(n)`: each level is differenced
against its own session-paired baseline, as pre-registered.

Turnaround for L0 was 21.0 minutes, faster than the 32.8 to 48.5 minutes seen
across the r1 series.

### L0 as a free-baseline replicate

Normalised score `ns = (0.013890/decode_spt)**0.75 * (0.0003845/prefill_spt)**0.25`
for the two inert receipts taken on the *current* promoted frontier:

| receipt | revision | S (ms) | T (ms) | ns |
| --- | --- | --- | --- | --- |
| `b6032aeb` | r1 anchor | 97.8643 | 4.27468 | 2.547640 |
| `c3ce66ec` | r2 L0 | 97.9496 | 4.28121 | 2.544361 |

They agree to 0.129 percent, which matches the 0.149 percent coefficient of
variation already recorded for `ns`. The three older inert receipts I have on
file (`f8502e12` 2.48558, `71586bcf` 2.51595, `f3cda678` 2.50895) sit about 1.3
percent lower and must **not** be pooled with these two: they were taken on an
earlier promoted frontier, so their lower `ns` is a real level shift in the
base rather than session noise. Pooling all five would have inflated the
apparent replicate spread from 0.13 percent to about 1 percent and made every
subsequent comparison look untrustworthy.
