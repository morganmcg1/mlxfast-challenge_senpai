#!/usr/bin/env python3
"""One-shot: correct a now-false honesty claim in the P1 note, atomically.

The first P1 draw was killed by a pending SIGTERM before it fired, so the note
is being resubmitted after the companion P0 receipt resolved. The paragraph
claiming P0 was still `validating` is no longer true and is retracted in place.
The rename keeps the swap atomic in case the drawer reads the file concurrently.
"""
import os
import tempfile

P = "research/maple-frieren-r105b-note-p1.md"

OLD = """Recorded here, in the note body, so that it carries this submission's
server-side timestamp. At the moment this receipt is accepted, the companion
P0 receipt (`6fc8abf`) is still `validating` and has published no metrics, so
the rule below cannot be a post-hoc rationalisation of the result.
"""

NEW = """Recorded here, in the note body, so that it carries this submission's
server-side timestamp.

Scope of the claim, stated exactly. The companion P0 receipt (`6fc8abf`) had
already resolved when this note was finalised and its metrics were known to the
author: `T(P0) = 4159.285 us/step`. This is therefore a one-sided
preregistration, not a blind one. What it does fix, before the governed
quantity can exist, is the rule for reading `dT = T(P0) - T(P1)`: that contrast
is not computable from one arm, and the P1 half of it is the receipt this note
accompanies. The thresholds, the sign convention and the stop/continue decision
below are committed before any value of `dT` is observable. An earlier draft of
this paragraph asserted that P0 was still `validating` with no metrics; the
draw it was written for was killed before it fired, the note is being
resubmitted later, and that assertion is retracted here rather than quietly
deleted.
"""


def main() -> int:
    s = open(P).read()
    if OLD not in s:
        print("nothing to do: paragraph already corrected or absent")
        return 0
    assert s.count(OLD) == 1
    s = s.replace(OLD, NEW)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(P) or ".")
    with os.fdopen(fd, "w") as fh:
        fh.write(s)
    os.replace(tmp, P)
    print("bytes", len(s.encode()),
          "marker", s.count("R105-B Phase B, arm P1"),
          "retraction", s.count("retracted here"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
