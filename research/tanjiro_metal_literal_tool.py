#!/usr/bin/env python3
"""Research-only offline tool for maple-tanjiro PR #81 (metal-literal byte reclaim).

NOT part of the challenge runtime and NOT on the submitted surface.

Subcommands
-----------
census FILE
    Re-derive the literal census: block count, byte pools, top literals,
    hazard checks.

dump FILE OUTDIR
    Materialise, for every Swift multi-line string literal in FILE, the exact
    *dedented body* that the Swift compiler will hand to the string-literal
    lowering step (Swift strips the closing delimiter's indentation from every
    content line).  Interpolations are left as opaque source text, so a
    byte-identical dump proves the emitted MSL is byte-identical for *any*
    interpolation value.  Also dumps every single-line `"..."` literal that is
    part of a `+ "...\\n"` MSL concatenation chain.

dedent FILE
    Apply tier T1 in place: shift each literal body *and its closing `\"\"\"`*
    left by the closing delimiter's indentation.  Idempotent.

verify FILE
    Assert the parser round-trips FILE byte-for-byte.

strip FILE
    Apply tier T2 in place: delete `//` line comments that sit inside literal
    bodies.  Refuses to touch a `\\`-continued macro body, a Swift
    newline-continuation line, or a forbidden region.  Idempotent.

certify BASEDIR CANDDIR
    T2 certificate.  For every dumped string, either the candidate is
    byte-identical to the base, or an *independent* C-style comment stripper
    applied to the base reproduces the candidate byte-for-byte.  Any other
    outcome is reported as UNEXPLAINED and exits non-zero.
"""

from __future__ import annotations

import collections
import hashlib
import os
import re
import sys

TRIPLE = '"""'


class Block:
    __slots__ = ("open_line", "close_line", "indent", "label")

    def __init__(self, open_line, close_line, indent, label):
        self.open_line = open_line      # 1-based line index of the opening """
        self.close_line = close_line    # 1-based line index of the closing """
        self.indent = indent            # closing-delimiter indentation width
        self.label = label              # nearest enclosing Swift identifier

    @property
    def body(self):
        return range(self.open_line + 1, self.close_line)


LABEL_RE = re.compile(
    r"(?:let|var|func)\s+([A-Za-z_][A-Za-z0-9_]*)"
    r"|^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*\"\"\"\s*$"
    r"|^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\"\"\"\s*$"
    r"|^\s*return\s+\"\"\"\s*$"
)


def read_lines(path):
    raw = open(path, "rb").read()
    if b"\r" in raw:
        raise SystemExit("CR byte found; parser assumes LF only")
    if b"\t" in raw:
        raise SystemExit("tab character found; parser assumes spaces only")
    text = raw.decode("utf-8")
    trailing_nl = text.endswith("\n")
    lines = text.split("\n")
    if trailing_nl:
        lines.pop()
    return lines, trailing_nl


def join_lines(lines, trailing_nl):
    out = "\n".join(lines)
    if trailing_nl:
        out += "\n"
    return out


def label_for(lines, open_idx):
    """Nearest identifier at or above the opening delimiter line."""
    for i in range(open_idx, max(-1, open_idx - 12), -1):
        line = lines[i]
        m = re.search(r"(?:let|var|func)\s+([A-Za-z_][A-Za-z0-9_]*)", line)
        if m:
            return m.group(1)
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(?:\?\s*)?\"\"\"\s*$", line)
        if m:
            return m.group(1)
    return "?"


def parse(lines):
    """Return the list of multi-line literal blocks.

    Uses a strict alternating scan and asserts the Swift shape of every
    delimiter, so a nested literal, an unbalanced delimiter, a single-line
    `\"\"\"..\"\"\"`, or a `\"\"\"` inside a comment all raise instead of
    silently corrupting the file.
    """
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        cnt = line.count(TRIPLE)
        if cnt == 0:
            i += 1
            continue
        if cnt != 1:
            raise SystemExit(f"line {i+1}: {cnt} triple-quote tokens on one line")
        # An opening delimiter must be the last non-whitespace on its line.
        if not line.rstrip().endswith(TRIPLE):
            raise SystemExit(f"line {i+1}: unexpected triple-quote shape: {line!r}")
        # Walk to the closing delimiter.
        j = i + 1
        close = None
        while j < n:
            cand = lines[j]
            if TRIPLE in cand:
                if cand.count(TRIPLE) != 1:
                    raise SystemExit(f"line {j+1}: {cand.count(TRIPLE)} triple tokens")
                m = re.match(r"^( *)\"\"\"", cand)
                if not m:
                    raise SystemExit(
                        f"line {j+1}: triple-quote inside literal body is not a "
                        f"closing delimiter (nested literal?): {cand!r}"
                    )
                close = j
                indent = len(m.group(1))
                break
            j += 1
        if close is None:
            raise SystemExit(f"line {i+1}: unterminated multi-line literal")
        blocks.append(Block(i + 1, close + 1, indent, label_for(lines, i)))
        i = close + 1
    return blocks


def dedented_body(lines, blk):
    """Exact content Swift produces for the literal, before escape/interp lowering."""
    k = blk.indent
    out = []
    for ln in blk.body:
        line = lines[ln - 1]
        if line.strip() == "":
            out.append(line[k:] if len(line) > k else "")
        else:
            if not line.startswith(" " * k):
                raise SystemExit(
                    f"line {ln}: content line has less indentation ({len(line) - len(line.lstrip())}) "
                    f"than the closing delimiter ({k}); Swift would reject this"
                )
            out.append(line[k:])
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# census
# --------------------------------------------------------------------------- #

def cmd_census(path):
    lines, _ = read_lines(path)
    raw = open(path, "rb").read()
    blocks = parse(lines)

    body_bytes = 0
    delim_bytes = 0
    t1_savings = 0
    per_block = []
    for b in blocks:
        bb = sum(len(lines[l - 1]) + 1 for l in b.body)
        body_bytes += bb
        delim_bytes += len(lines[b.open_line - 1]) + len(lines[b.close_line - 1]) + 2
        save = 0
        for l in b.body:
            line = lines[l - 1]
            save += min(b.indent, len(line)) if line.strip() == "" else b.indent
        save += b.indent  # the closing delimiter line
        t1_savings += save
        per_block.append((bb, save, b))

    in_lit = set()
    for b in blocks:
        in_lit.update(b.body)

    # comment pool outside literals
    comment_bytes = 0
    for i, line in enumerate(lines, 1):
        if i in in_lit:
            continue
        s = line.strip()
        if s.startswith("//"):
            comment_bytes += len(line) + 1
    # comments inside literals (T2 pool)
    lit_comment_bytes = 0
    lit_comment_lines = 0
    for b in blocks:
        for l in b.body:
            s = lines[l - 1].strip()
            if s.startswith("//"):
                lit_comment_bytes += len(lines[l - 1]) + 1
                lit_comment_lines += 1

    concat = [(i, l) for i, l in enumerate(lines, 1)
              if re.search(r'\+\s*"(?:[^"\\]|\\.)*"\s*$', l) and i not in in_lit]

    print(f"file:           {path}")
    print(f"size:           {len(raw)} B   lines: {len(lines)}")
    print(f'""" delimiters: {raw.count(TRIPLE.encode())}')
    print(f"blocks:         {len(blocks)}")
    print(f"literal bodies: {body_bytes} B = {100.0*body_bytes/len(raw):.1f} % of file")
    print(f"+ delimiters:   {body_bytes + delim_bytes} B")
    print(f"T1 savings:     {t1_savings} B")
    print(f"T2 pool (// inside literals): {lit_comment_bytes} B on {lit_comment_lines} lines")
    print(f"comment pool OUTSIDE literals: {comment_bytes} B")
    print(f'`+ "..."` concat lines outside literals: {len(concat)}, '
          f'{sum(len(l)+1 for _, l in concat)} B')
    print(f"tabs: {raw.count(bytes([9]))}  CR: {raw.count(bytes([13]))}  "
          f"trailing-ws lines: {sum(1 for l in lines if l != l.rstrip())}")
    print()
    print("top literals by body bytes:")
    for bb, save, b in sorted(per_block, reverse=True, key=lambda t: t[0])[:8]:
        print(f"  {b.label:<52} L{b.open_line}-{b.close_line} "
              f"lines={b.close_line-b.open_line-1:>4} bytes={bb:>6} indent={b.indent:>2} t1={save:>5}")
    print()
    print("indent histogram (closing delimiter width -> blocks):")
    for k, v in sorted(collections.Counter(b.indent for b in blocks).items()):
        print(f"  {k:>3}: {v}")


# --------------------------------------------------------------------------- #
# dump
# --------------------------------------------------------------------------- #

def cmd_dump(path, outdir):
    lines, _ = read_lines(path)
    blocks = parse(lines)
    os.makedirs(outdir, exist_ok=True)
    manifest = []
    for idx, b in enumerate(blocks):
        body = dedented_body(lines, b)
        name = f"{idx:03d}_{b.label}.msl"
        with open(os.path.join(outdir, name), "w") as fh:
            fh.write(body)
        manifest.append((name, len(body.encode()), hashlib.sha256(body.encode()).hexdigest()))

    in_lit = set()
    for b in blocks:
        in_lit.update(b.body)
    concat = []
    for i, line in enumerate(lines, 1):
        if i in in_lit:
            continue
        for m in re.finditer(r'\+\s*("(?:[^"\\]|\\.)*")\s*$', line):
            concat.append(m.group(1))
    blob = "\n".join(concat)
    with open(os.path.join(outdir, "zzz_single_line_concat.msl"), "w") as fh:
        fh.write(blob)
    manifest.append(("zzz_single_line_concat.msl", len(blob.encode()),
                     hashlib.sha256(blob.encode()).hexdigest()))

    with open(os.path.join(outdir, "MANIFEST.txt"), "w") as fh:
        for name, nb, h in manifest:
            fh.write(f"{h}  {nb:>7}  {name}\n")
    print(f"dumped {len(blocks)} multi-line literals + 1 concat blob to {outdir}")


# --------------------------------------------------------------------------- #
# dedent (T1)
# --------------------------------------------------------------------------- #

def excluded_ranges(lines):
    """Line ranges (1-based, inclusive) that PR #81 forbids editing.

    A multi-line literal is dedented all-or-nothing: shifting only part of a
    body would change the emitted string.  So any block overlapping one of
    these ranges is skipped entirely.

    - the #27 M5 hardware-constant injection instrument (§3.1, T0 VETOED):
      from its BEGIN marker to EOF;
    - `lagunaTailNVFP4QMVHeader`, which contains the multi-line Swift
      interpolation at L4656-4660 that §5.3 excludes from every tier.
    """
    ranges = []
    for i, line in enumerate(lines, 1):
        if "BEGIN M5 HARDWARE-CONSTANT INSTRUMENT" in line:
            ranges.append((i, len(lines)))
            break
    else:
        raise SystemExit("T0 BEGIN marker not found; refusing to edit")
    for i, line in enumerate(lines, 1):
        if re.match(r"\s*private let lagunaTailNVFP4QMVHeader = \"\"\"\s*$", line):
            ranges.append((i, i))
            break
    else:
        raise SystemExit("lagunaTailNVFP4QMVHeader not found; refusing to edit")
    return ranges


def is_excluded(blk, ranges):
    lo, hi = blk.open_line, blk.close_line
    return any(not (hi < a or lo > b) for a, b in ranges)


def cmd_dedent(path):
    lines, trailing_nl = read_lines(path)
    blocks = parse(lines)
    ranges = excluded_ranges(lines)
    before = join_lines(lines, trailing_nl).encode()
    # Sanity: every body line must satisfy the Swift indentation rule first.
    for b in blocks:
        dedented_body(lines, b)
    out = list(lines)
    saved = 0
    touched = 0
    skipped = []
    for b in blocks:
        k = b.indent
        if k == 0:
            continue
        if is_excluded(b, ranges):
            skipped.append(b)
            continue
        touched += 1
        for l in b.body:
            line = lines[l - 1]
            if line.strip() == "":
                new = line[k:] if len(line) > k else ""
            else:
                new = line[k:]
            saved += len(line) - len(new)
            out[l - 1] = new
        cl = lines[b.close_line - 1]
        out[b.close_line - 1] = cl[k:]
        saved += k
    after = join_lines(out, trailing_nl).encode()
    open(path, "wb").write(after)
    print(f"T1: {touched}/{len(blocks)} blocks dedented, "
          f"{len(before) - len(after)} bytes removed "
          f"(accounted {saved}), new size {len(after)} B")
    for b in skipped:
        cost = sum(min(b.indent, len(lines[l - 1])) if lines[l - 1].strip() == ""
                   else b.indent for l in b.body) + b.indent
        print(f"  skipped (forbidden region): {b.label} L{b.open_line}-{b.close_line} "
              f"indent={b.indent} foregone={cost} B")


# --------------------------------------------------------------------------- #
# strip (T2) - remove `//` line comments that sit inside literal bodies
# --------------------------------------------------------------------------- #

TRAILING_BS = re.compile(r"(\\+)$")


def swift_comment_at(line):
    """Index of the `//` that opens a Metal line comment, or None.

    Scans the *Swift source* text of one literal body line.  Raises on any
    shape the scanner does not model, so an unexpected construct stops the
    tool instead of silently corrupting a kernel.
    """
    if "/*" in line or "*/" in line:
        raise SystemExit(f"block comment inside literal: {line!r}")
    m = TRAILING_BS.search(line)
    if m and len(m.group(1)) % 2 == 1:
        # Swift newline-continuation escape: the line boundary is significant.
        return None
    n = len(line)
    i = 0
    in_str = False
    while i < n:
        c = line[i]
        if in_str:
            if c == "\\":
                i += 2
            elif c == '"':
                in_str = False
                i += 1
            else:
                i += 1
            continue
        if c == "\\":
            if i + 1 < n and line[i + 1] == "(":
                depth = 1
                j = i + 2
                while j < n and depth:
                    if line[j] == "(":
                        depth += 1
                    elif line[j] == ")":
                        depth -= 1
                    elif line[j] == '"':
                        j += 1
                        while j < n and line[j] != '"':
                            j += 2 if line[j] == "\\" else 1
                    j += 1
                if depth:
                    raise SystemExit(f"interpolation not closed on its line: {line!r}")
                i = j
                continue
            i += 2
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if line.startswith("//", i):
            return i
        i += 1
    if in_str:
        raise SystemExit(f"unterminated Metal string literal on one line: {line!r}")
    return None


def macro_body_lines(lines, body_range):
    """Body lines that belong to a `\\`-continued preprocessor macro."""
    out = set()
    for l in body_range:
        m = TRAILING_BS.search(lines[l - 1])
        if m:
            out.add(l)
            out.add(l + 1)
    return out


def cmd_strip(path):
    lines, trailing_nl = read_lines(path)
    blocks = parse(lines)
    ranges = excluded_ranges(lines)
    before = join_lines(lines, trailing_nl).encode()
    out = list(lines)
    drop = set()
    deleted = truncated = 0
    skipped = []
    for b in blocks:
        if is_excluded(b, ranges):
            skipped.append(b)
            continue
        macro = macro_body_lines(lines, b.body)
        for l in b.body:
            line = lines[l - 1]
            at = swift_comment_at(line)
            if at is None:
                continue
            if l in macro:
                raise SystemExit(
                    f"line {l}: comment inside a `\\`-continued macro body; "
                    f"§5.2 forbids touching these: {line!r}"
                )
            prefix = line[:at]
            if prefix.strip() == "":
                drop.add(l)
                deleted += 1
            else:
                new = prefix.rstrip()
                m = TRAILING_BS.search(new)
                if m and len(m.group(1)) % 2 == 1:
                    raise SystemExit(f"line {l}: truncation would create a continuation escape")
                out[l - 1] = new
                truncated += 1
    for l in sorted(drop):
        prev = l - 1
        m = TRAILING_BS.search(lines[prev - 1])
        if m and len(m.group(1)) % 2 == 1:
            raise SystemExit(f"line {l}: deleting a line after a continuation escape")
    kept = [s for i, s in enumerate(out, 1) if i not in drop]
    after = join_lines(kept, trailing_nl).encode()
    open(path, "wb").write(after)
    print(f"T2: {deleted} comment-only lines deleted, {truncated} trailing comments cut, "
          f"{len(before) - len(after)} bytes removed, new size {len(after)} B")
    for b in skipped:
        pool = 0
        for l in b.body:
            line = lines[l - 1]
            try:
                at = swift_comment_at(line)
            except SystemExit:
                continue  # a shape the scanner refuses; it is excluded anyway
            if at is not None:
                pool += (len(line) + 1) if line[:at].strip() == "" else (len(line) - len(line[:at].rstrip()))
        print(f"  skipped (forbidden region): {b.label} L{b.open_line}-{b.close_line} "
              f"comment bytes foregone={pool}")


# --------------------------------------------------------------------------- #
# certify (T2) - independent comment stripper applied to the base MSL dumps
# --------------------------------------------------------------------------- #

def strip_comments_msl(text, skip_interpolations=False):
    """Remove `//` comments from a Metal source string.

    Deliberately a *separate, simpler* implementation from `swift_comment_at`:
    a plain C-like scanner over the emitted text.  Agreement between the two
    is the T2 certificate.
    """
    res = []
    for line in text.split("\n"):
        n = len(line)
        i = 0
        in_str = False
        in_char = False
        at = None
        while i < n:
            c = line[i]
            if in_str or in_char:
                if c == "\\":
                    i += 2
                    continue
                if (c == '"' and in_str) or (c == "'" and in_char):
                    in_str = in_char = False
                i += 1
                continue
            if skip_interpolations and c == "\\" and i + 1 < n and line[i + 1] == "(":
                depth = 1
                j = i + 2
                while j < n and depth:
                    if line[j] == "(":
                        depth += 1
                    elif line[j] == ")":
                        depth -= 1
                    j += 1
                i = j
                continue
            if c == '"':
                in_str = True
            elif c == "'":
                in_char = True
            elif line.startswith("//", i):
                at = i
                break
            i += 1
        if at is None:
            res.append(line)
            continue
        prefix = line[:at]
        if prefix.strip() == "":
            continue
        res.append(prefix.rstrip())
    return "\n".join(res)


def cmd_certify(basedir, canddir):
    names = sorted(f for f in os.listdir(basedir) if f.endswith(".msl"))
    cand_names = sorted(f for f in os.listdir(canddir) if f.endswith(".msl"))
    if names != cand_names:
        raise SystemExit(f"dump sets differ: {set(names) ^ set(cand_names)}")
    identical = differ = matched = failed = 0
    failures = []
    for name in names:
        base = open(os.path.join(basedir, name)).read()
        cand = open(os.path.join(canddir, name)).read()
        if base == cand:
            identical += 1
            continue
        differ += 1
        if strip_comments_msl(base) == cand:
            matched += 1
        elif strip_comments_msl(base, skip_interpolations=True) == cand:
            matched += 1
            failures.append((name, "matched only with interpolation-skipping scanner"))
        else:
            failed += 1
            failures.append((name, "UNEXPLAINED"))
    print(f"certify: {len(names)} strings compared; {identical} byte-identical; "
          f"{differ} differ; {matched} explained as pure comment removal; {failed} UNEXPLAINED")
    for name, why in failures:
        print(f"  {name}: {why}")
    if failed:
        raise SystemExit("T2 certificate FAILED")


def cmd_verify(path):
    lines, trailing_nl = read_lines(path)
    raw = open(path, "rb").read()
    if join_lines(lines, trailing_nl).encode() != raw:
        raise SystemExit("round-trip FAILED")
    blocks = parse(lines)
    for b in blocks:
        dedented_body(lines, b)
    residual = sum(b.indent for b in blocks)
    print(f"round-trip OK, {len(blocks)} blocks, residual closing indent total = {residual}")


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "census":
        cmd_census(path)
    elif cmd == "dump":
        cmd_dump(path, sys.argv[3])
    elif cmd == "dedent":
        cmd_dedent(path)
    elif cmd == "verify":
        cmd_verify(path)
    elif cmd == "strip":
        cmd_strip(path)
    elif cmd == "certify":
        cmd_certify(path, sys.argv[3])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
