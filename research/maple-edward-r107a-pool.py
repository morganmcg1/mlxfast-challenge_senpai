#!/usr/bin/env python3
"""Pool independent paired-ABBA blocks into one directory for joint analysis.

Rule 105.7: the confidence interval is the deliverable, so extra replicates of
an already-measured arm outrank a new arm. Each block written by
`maple-frieren-r103a-abba.sh` is a self-contained rotation experiment; pooling
them lets `maple-frieren-r103a-analyze-multi.py` compute one paired contrast
over every repetition instead of leaving two half-width estimates to be
combined by hand.

Pooling is only legitimate when the blocks measure the same thing, so this
refuses unless every block agrees on the worker binaries, the arm list, the
step count and the design. Repetition indices are renumbered and slot tags are
prefixed per block, so `cycles()` still groups by rotation phase and no tag can
collide.

    python3 research/maple-edward-r107a-pool.py OUT BLOCK [BLOCK ...]
"""
import os
import re
import shutil
import sys
from pathlib import Path

# Provenance keys that must agree across blocks for the pool to be meaningful.
# `reps` and `head` are deliberately absent: independent blocks may differ in
# length, and a block recorded at a later commit is still poolable as long as
# its worker binaries and its rule-75 Sources+Vendor digest are identical.
MUST_MATCH = ("steps", "design", "arms", "host", "digest_before")
SHA_LINE = re.compile(r"^([0-9a-f]{64})\s+(\S+)$")


def provenance(block: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Parse abba.sh provenance: `sha  path` lines plus `k=v` pairs.

    Several keys share one whitespace-separated line, but `arms=` values
    themselves contain spaces, so that key takes the rest of its line.
    """
    keys: dict[str, str] = {}
    shas: dict[str, str] = {}
    for raw in (block / "provenance.txt").read_text().splitlines():
        ln = raw.strip()
        m = SHA_LINE.match(ln)
        if m:
            shas[Path(m.group(2)).parent.name] = m.group(1)
            continue
        for whole in ("arms=", "host="):
            if ln.startswith(whole):
                keys[whole[:-1]] = ln[len(whole):].strip()
                break
        else:
            for tok in ln.split():
                if "=" in tok:
                    k, _, v = tok.partition("=")
                    keys[k] = v
    return keys, shas


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    out = Path(sys.argv[1])
    blocks = [Path(p) for p in sys.argv[2:]]
    for b in blocks:
        for need in ("index.tsv", "provenance.txt"):
            if not (b / need).exists():
                print(f"FAIL: {b} has no {need}")
                return 3

    ref_keys, ref_shas = provenance(blocks[0])
    for b in blocks[1:]:
        keys, shas = provenance(b)
        for k in MUST_MATCH:
            if keys.get(k) != ref_keys.get(k):
                print(f"FAIL: {b} disagrees on {k}: "
                      f"{keys.get(k)!r} != {ref_keys.get(k)!r}")
                return 4
        if shas != ref_shas:
            print(f"FAIL: {b} ran different worker binaries than {blocks[0]}")
            return 5

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    lines = ["rep\tposition\tarm\ttag"]
    offset = 0
    per_block: list[tuple[Path, int, int]] = []
    for bi, b in enumerate(blocks):
        reps_here: set[int] = set()
        for ln in (b / "index.tsv").read_text().splitlines()[1:]:
            rep_s, pos_s, arm, tag = ln.split("\t")
            rep = int(rep_s)
            reps_here.add(rep)
            newtag = f"b{bi}-{tag}"
            for ext in ("steps", "log", "err", "tokens"):
                src = b / f"{tag}.{ext}"
                if src.exists():
                    os.symlink(src.resolve(), out / f"{newtag}.{ext}")
            lines.append(f"{rep + offset}\t{pos_s}\t{arm}\t{newtag}")
        per_block.append((b, offset, len(reps_here)))
        offset += (max(reps_here) + 1) if reps_here else 0

    (out / "index.tsv").write_text("\n".join(lines) + "\n")
    # Written in abba.sh's own format so a pooled directory is itself poolable.
    prov = [f"pooled_blocks={len(blocks)} reps={offset}"]
    for k in MUST_MATCH:
        prov.append(f"{k}={ref_keys.get(k)}")
    for name, sha in sorted(ref_shas.items()):
        prov.append(f"{sha}  {name}/mlxfast-runtime-worker")
    for b, off, n in per_block:
        prov.append(f"# block {b} rep_offset={off} reps={n}")
    (out / "provenance.txt").write_text("\n".join(prov) + "\n")

    cks = set()
    for b in blocks:
        p = b / "tokens.cksum"
        if p.exists():
            cks.update(ln.split()[0] for ln in p.read_text().splitlines() if ln.strip())
    (out / "tokens.cksum").write_text("\n".join(sorted(cks)) + "\n")

    print(f"pooled {len(blocks)} block(s) -> {out}")
    print(f"  slots={len(lines) - 1} reps={offset}")
    print(f"  distinct token checksums across blocks: {len(cks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
