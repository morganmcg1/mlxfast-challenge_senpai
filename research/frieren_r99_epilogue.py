"""Research-only generator (not part of the submission surface).

Swaps the `laguna_sliding_fused_attn_ring_v1` merge epilogue between the two
forms that exist in git history:

  soa     - `threadgroup U outputs[4 * BN * BDP]` with a `pair_planes = 2`
            two-pass reduction. This is the promoted-frontier form shipped at
            the current base.
  float4  - `threadgroup float4 outputs4[BN * BDP]` with explicit `acc00..acc13`
            staging. This is the PR #205 / r85-c form that our lineage carried
            until the frontier rebase reverted it
            (`research/maple-r85-c-epilogue-result.md`: -20.98 us/step
            [-22.76, -19.19] on this kernel).

The float4 text is taken verbatim from `e510bb3d` rather than retyped, so the
swap is a git-provable restoration and not a re-derivation. Both forms occupy
the same 4 * BN * BDP floats of threadgroup memory, so threadgroup-memory
occupancy is invariant across the swap by construction.

The epilogue is textually disjoint from the accumulation loop, so this composes
with `research/nezuko_r96_gen4deep.py` to give a depth x epilogue factorial.
Applying depth 4 and then this swap reproduces the `e510bb3d` sliding kernel
byte for byte, which is the codegen control for the pair.

`laguna_full_fused_attn_grow_v1` carries the same two epilogue forms and is
selectable for evidence purposes; the r99-A candidate does not ship a change
to it.

Usage: python3 research/frieren_r99_epilogue.py float4 [kernel] [old-rev]
"""

import subprocess
import sys

PATH = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
SLIDING = "laguna_sliding_fused_attn_ring_v1"
SOA_DECL = "threadgroup U outputs[4 * BN * BDP];"
F4_DECL = "threadgroup float4 outputs4[BN * BDP];"


def literal_span(lines, name):
    """Return (start, end) raw line indices of the kernel's `source` literal."""
    decl = next(i for i, l in enumerate(lines) if 'name: "%s"' % name in l)
    open_i = next(i for i in range(decl, len(lines)) if lines[i].strip() == 'source: """')
    close_i = next(i for i in range(open_i + 1, len(lines))
                   if lines[i].strip() in ('""",', '"""'))
    return open_i + 1, close_i


def split_after_loop(body):
    """Split a kernel body into (head_through_loop, epilogue)."""
    start = next(i for i, l in enumerate(body) if l.startswith("for (; i + "))
    depth = 0
    i = start
    while True:
        depth += body[i].count("{") - body[i].count("}")
        i += 1
        if depth == 0:
            break
    return body[:i], body[i:]


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else "float4"
    kernel = sys.argv[2] if len(sys.argv) > 2 else SLIDING
    old_rev = sys.argv[3] if len(sys.argv) > 3 else "e510bb3d"
    if want != "float4":
        raise SystemExit("soa is the shipped form; restore it with `git checkout`")

    lines = open(PATH).read().split("\n")
    lo, hi = literal_span(lines, kernel)
    body = lines[lo:hi]
    head, _ = split_after_loop(body)

    old = subprocess.run(["git", "show", "%s:%s" % (old_rev, PATH)],
                         capture_output=True, text=True, check=True).stdout.split("\n")
    olo, ohi = literal_span(old, kernel)
    _, epi = split_after_loop(old[olo:ohi])

    n = head.count(SOA_DECL)
    assert n == 1, "expected exactly one `%s` in %s, found %d" % (SOA_DECL, kernel, n)
    head = [F4_DECL if l == SOA_DECL else l for l in head]

    out = lines[:lo] + head + epi + lines[hi:]
    open(PATH, "w").write("\n".join(out))
    print("%s epilogue -> %s (%d body lines, was %d)"
          % (kernel, want, len(head) + len(epi), len(body)))


if __name__ == "__main__":
    main()
