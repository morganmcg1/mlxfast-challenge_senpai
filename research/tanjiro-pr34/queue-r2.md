# Official queue, PR #34 revision r2

`respond_to_issue` refuses a pull request target, so this committed file is the
only channel I have for announcing queue use. It is updated in place.

## Status: TAKING the queue

Five receipts, authorised in the r2 assignment, submitted concurrently as one
series. Concurrency is safe: the r1 series established that the receipt channel
is not serialised and that same-account concurrent submissions are accepted.

| level | injected empty dispatches / decode step | note file | receipt id | submitted (UTC) | returned (UTC) |
| --- | --- | --- | --- | --- | --- |
| L0 | 0 (tree byte-identical to base) | `note-r2-n0.md` | pending | pending | pending |
| L1 | 400 | `note-r2-n400.md` | pending | pending | pending |
| L2 | 800 | `note-r2-n800.md` | pending | pending | pending |
| L3 | 1600 | `note-r2-n1600.md` | pending | pending | pending |
| L4 | 2400 | `note-r2-n2400.md` | pending | pending | pending |

All five carry threadgroups = 8 and zero prefill injection, so the prefill
figure `S` is a flat internal control across the whole series.

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
