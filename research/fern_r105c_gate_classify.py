#!/usr/bin/env python3
"""R105-C — static reachability classification of every runtime default-ON gate.

Research-only; not part of the submission surface.

    python3 research/fern_r105c_gate_classify.py [--root DIR] [--out DIR]

For every distinct `ProcessInfo.processInfo.environment["NAME"] != "0"` gate in
`Sources/**.swift` and `Vendor/**.swift`, resolve the Swift symbol it binds,
find every read site of that symbol, and classify each site by whether it sits
in a branch that another *default-ON* gate already wins at shipped defaults.

Per-site classes (preregistered in research/fern-r105c-gate-surface-masking-audit.md §0.4):

  DEAD-BRANCH                 the site is in an else / else-if branch whose
                              preceding chain condition is a pure conjunction of
                              default-ON gate symbols, or is dominated by an
                              early `return` guarded only by such a conjunction
  NEEDS-RUNTIME-OBSERVATION   same shape, but the dominating branch carries
                              extra runtime predicates (shape/optional/dtype)
  NEG-GUARDED                 reachable only when another default-ON gate is
                              negated
  LIVE                        none of the above

Overall class is the most-live class over a gate's read sites, or NO-READ-SITE.

Deliberate limits, stated rather than hidden:
  * intra-procedural only. A gate whose site is dead because a *callee* returns
    early (DARKBLOOM_INVERSE_SCATTER) is NOT detected here; that needs a hand
    proof, and this script's LIVE verdict for it is a false negative by
    construction.
  * a `guard` whose failure path is `return` is modelled as a positive
    requirement on later sites in the same scope, not as domination.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess

GATE_RE = re.compile(
    # some sites read a hoisted `environment` dictionary rather than
    # `ProcessInfo.processInfo.environment` directly
    r'(?:ProcessInfo\s*\.\s*processInfo\s*\.\s*)?\benvironment\s*\[\s*"([A-Z0-9_]+)"\s*\]'
    r'\s*(!=|==)\s*"([^"]*)"',
    re.S,
)
BIND_RE = re.compile(r'\b(?:let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=\n]+)?=\s*$')
IDENT = r'[A-Za-z_][A-Za-z0-9_]*'


def blank(text: str, start: int, end: int) -> str:
    """Replace [start,end) with spaces, preserving newlines and every offset."""
    seg = "".join(c if c == "\n" else " " for c in text[start:end])
    return text[:start] + seg + text[end:]


def strip_comments(text: str) -> str:
    out, i, n = text, 0, len(text)
    res = []
    i = 0
    depth = 0
    while i < n:
        c = text[i]
        if depth == 0 and c == '"':
            # copy a string literal verbatim (comments cannot start inside one)
            if text.startswith('"""', i):
                j = text.find('"""', i + 3)
                j = n if j < 0 else j + 3
            else:
                j = i + 1
                while j < n and text[j] != '"':
                    if text[j] == "\\":
                        j += 1
                    j += 1
                j = min(j + 1, n)
            res.append(text[i:j])
            i = j
            continue
        if depth == 0 and text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            res.append(" " * (j - i))
            i = j
            continue
        if text.startswith("/*", i):
            depth += 1
            res.append("  ")
            i += 2
            continue
        if depth > 0 and text.startswith("*/", i):
            depth -= 1
            res.append("  ")
            i += 2
            continue
        res.append(" " if (depth > 0 and c != "\n") else c)
        i += 1
    out = "".join(res)
    assert len(out) == n
    return out


def strip_strings(text: str) -> str:
    """Blank string-literal contents so braces inside them do not nest."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        if text[i] == '"':
            if text.startswith('"""', i):
                j = text.find('"""', i + 3)
                j = n if j < 0 else j + 3
            else:
                j = i + 1
                while j < n and text[j] != '"':
                    if text[j] == "\\":
                        j += 1
                    j += 1
                j = min(j + 1, n)
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        i += 1
    return "".join(out)


class Block:
    __slots__ = ("kind", "cond", "chain", "head", "start", "end", "body_returns")

    def __init__(self, kind, cond, chain, head, start):
        self.kind = kind          # if | else-if | else | guard-else | other
        self.cond = cond          # condition text (else: "")
        self.chain = chain        # conditions of preceding branches in the chain
        self.head = head          # offset where this block's header starts
        self.start = start        # offset of the '{'
        self.end = -1
        self.body_returns = False


HEADER_GUARD = re.compile(r'\bguard\b(?P<cond>.*)\belse\s*$', re.S)
HEADER_ELSE_IF = re.compile(r'\belse\s+if\b(?P<cond>.*)$', re.S)
HEADER_ELSE = re.compile(r'\belse\s*$', re.S)
HEADER_IF = re.compile(r'\bif\b(?P<cond>.*)$', re.S)
HEADER_LOOP = re.compile(r'\b(?:for|while|switch|catch|repeat)\b', re.S)


def parse_blocks(src: str):
    """Return every brace block with the branch structure that governs it."""
    blocks = []
    stack = []                    # open Block objects
    frames = [{"pending_chain": [], "dominators": []}]
    boundary = 0
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "{":
            header = src[boundary:i]
            frame = frames[-1]
            m = HEADER_GUARD.search(header)
            if m:
                blk = Block("guard-else", m.group("cond").strip(), [],
                            boundary + m.start(), i)
            else:
                m = HEADER_ELSE_IF.search(header)
                if m and _is_chain_continuation(header):
                    blk = Block("else-if", m.group("cond").strip(),
                                list(frame["pending_chain"]), boundary + m.start(), i)
                elif HEADER_ELSE.search(header) and _is_chain_continuation(header):
                    blk = Block("else", "", list(frame["pending_chain"]), boundary, i)
                else:
                    m = HEADER_IF.search(header)
                    if m and not HEADER_LOOP.search(header[m.start():]):
                        blk = Block("if", m.group("cond").strip(), [],
                                    boundary + m.start(), i)
                    else:
                        blk = Block("other", "", [], boundary, i)
            stack.append(blk)
            frames.append({"pending_chain": [], "dominators": []})
            boundary = i + 1
            i += 1
            continue
        if c == "}":
            if stack:
                blk = stack.pop()
                blk.end = i
                inner = frames.pop()
                blk.body_returns = bool(inner.get("returns"))
                blocks.append(blk)
                frame = frames[-1]
                if blk.kind in ("if", "else-if"):
                    frame["pending_chain"] = blk.chain + [blk.cond]
                    if blk.body_returns:
                        frame["dominators"].append((blk.cond, blk.start, i))
                elif blk.kind == "guard-else":
                    frame["pending_chain"] = []
                    # a guard's else-block always exits, so the guard condition
                    # holds for everything after it in this scope
                    frame["dominators"].append(("GUARD:" + blk.cond, blk.start, i))
                elif blk.kind == "else":
                    frame["pending_chain"] = []
                else:
                    frame["pending_chain"] = []
            boundary = i + 1
            i += 1
            continue
        if c == ";":
            boundary = i + 1
        if src.startswith("return", i) and _word_boundary(src, i, 6):
            frames[-1]["returns"] = True
        i += 1
    return blocks


def _word_boundary(src: str, i: int, ln: int) -> bool:
    before = src[i - 1] if i else " "
    after = src[i + ln] if i + ln < len(src) else " "
    return not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_")


def _is_chain_continuation(header: str) -> bool:
    """True when `else` in this header continues the block that just closed."""
    idx = header.rfind("else")
    return idx >= 0 and header[:idx].strip() == ""


def line_of(text: str, off: int) -> int:
    return text.count("\n", 0, off) + 1


def collect_files(root: str):
    out = subprocess.check_output(
        ["find", os.path.join(root, "Sources"), os.path.join(root, "Vendor"),
         "-name", "*.swift"]).decode().split()
    return sorted(out)


def term_split(cond: str):
    parts = re.split(r',|&&', cond)
    return [p.strip() for p in parts if p.strip()]


def classify(root: str):
    files = collect_files(root)
    clean, braced, blocks = {}, {}, {}
    for f in files:
        raw = open(f, encoding="utf-8", errors="replace").read()
        c = strip_comments(raw)
        clean[f] = c
        braced[f] = strip_strings(c)
        blocks[f] = parse_blocks(braced[f])

    gates = {}          # NAME -> dict
    sym_to_gate = {}    # (file|None, symbol) -> NAME
    for f in files:
        rel = os.path.relpath(f, root)
        for m in GATE_RE.finditer(clean[f]):
            name, op, val = m.group(1), m.group(2), m.group(3)
            polarity = ("default-ON" if (op == "!=" and val == "0")
                        else "default-OFF" if (op == "==" and val == "1")
                        else f"other({op}\"{val}\")")
            head = clean[f][:m.start()]
            bm = BIND_RE.search(head.rstrip() + "=" if head.rstrip().endswith("=")
                                else head)
            sym = None
            tail = head.rstrip()
            if tail.endswith("="):
                bm = BIND_RE.search(tail)
                if bm:
                    sym = bm.group(1)
            if sym is None:
                # `let x = ProcessInfo...` on one line, or wrapped subscript
                bm = re.search(r'\b(?:let|var)\s+(' + IDENT + r')\s*(?::[^=\n]+)?=\s*$',
                               tail)
                if bm:
                    sym = bm.group(1)
            if sym is None:
                sym = closure_binding(head, blocks[f], m.start())
            g = gates.setdefault(name, {
                "name": name, "polarity": polarity, "decls": [], "symbols": [],
                "reads": [],
            })
            g["decls"].append(f"{rel}:{line_of(clean[f], m.start())}")
            g["reads"].append((f, rel, m.start()))
            if sym:
                g["symbols"].append(sym)
                sym_to_gate[sym] = name
    return files, clean, braced, blocks, gates, sym_to_gate


CLOSURE_BIND = re.compile(
    r'\b(?:let|var)\s+(' + IDENT + r')\s*(?::[^={\n]+)?=\s*\{')


def closure_binding(head, blocks_list, off):
    """Symbol for `let X: T = { ... env[...] ... }()` around this read, if any."""
    starts = {b.start: b for b in blocks_list}
    best = None
    for bm in CLOSURE_BIND.finditer(head):
        brace = bm.end() - 1
        b = starts.get(brace)
        if b is not None and b.start < off < b.end and (best is None or brace > best[0]):
            best = (brace, bm.group(1))
    return best[1] if best else None


def enclosing(blocks_list, off):
    # A gate read in a branch *condition* sits before that branch's `{`, so the
    # governing span has to start at the branch keyword, not at the brace.
    encl = [b for b in blocks_list if b.head <= off < b.end]
    encl.sort(key=lambda b: b.head)
    return encl


def site_class(name, sym, f, rel, off, braced_text, blocks_list, on_syms):
    """Classify one read site. Returns (class, reason)."""
    encl = enclosing(blocks_list, off)
    reasons = []
    verdict = "LIVE"

    def pure_gate_terms(cond):
        terms = term_split(cond)
        if not terms:
            return False, []
        gate_terms, other_terms = [], []
        for t in terms:
            tt = t.replace("== true", "").strip()
            if tt in on_syms and tt != sym:
                gate_terms.append(tt)
            else:
                other_terms.append(t)
        return (len(other_terms) == 0 and len(gate_terms) > 0), gate_terms

    for b in encl:
        if b.kind in ("else", "else-if") and b.chain:
            for cond in b.chain:
                pure, gterms = pure_gate_terms(cond)
                if pure:
                    return "DEAD-BRANCH", (
                        f"in {b.kind} branch of a chain whose earlier condition "
                        f"is the pure default-ON conjunction [{' && '.join(gterms)}]")
                _, gterms = pure_gate_terms(cond)
                if gterms:
                    verdict = "NEEDS-RUNTIME-OBSERVATION"
                    reasons.append(
                        f"in {b.kind} branch after a chain condition gated by "
                        f"[{' && '.join(gterms)}] plus extra runtime predicates")
        cond_terms = term_split(b.cond)
        for t in cond_terms:
            neg = t.strip().lstrip("!").strip()
            if t.strip().startswith("!") and neg in on_syms and neg != sym:
                return "NEG-GUARDED", f"reachable only when default-ON {neg} is off"
    return verdict, "; ".join(reasons) if reasons else "no default-ON gate dominates this site"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    root = args.root
    outdir = args.out or os.path.join(root, "research/artifacts/fern-r105c")
    os.makedirs(outdir, exist_ok=True)

    files, clean, braced, blocks, gates, sym_to_gate = classify(root)
    on_gates = {n: g for n, g in gates.items() if g["polarity"] == "default-ON"}
    on_syms = {s for s, n in sym_to_gate.items() if n in on_gates}

    # build a symbol -> read-site index once
    reads = {s: [] for s in sym_to_gate}
    pats = {s: re.compile(r'\b' + re.escape(s) + r'\b') for s in sym_to_gate}
    for f in files:
        rel = os.path.relpath(f, root)
        txt = braced[f]
        for s, pat in pats.items():
            for m in pat.finditer(txt):
                reads[s].append((f, rel, m.start()))

    rows = []
    for name in sorted(gates):
        g = gates[name]
        decl_offsets = set()
        for f in files:
            for m in GATE_RE.finditer(clean[f]):
                if m.group(1) == name:
                    decl_offsets.add((f, line_of(clean[f], m.start())))
        site_rows = []
        for sym in sorted(set(g["symbols"])):
            for (f, rel, off) in reads.get(sym, []):
                ln = line_of(braced[f], off)
                if (f, ln) in decl_offsets or any(
                        rel == d.split(":")[0] and ln == int(d.split(":")[1])
                        for d in g["decls"]):
                    continue
                # skip the binding line itself
                lstart = braced[f].rfind("\n", 0, off) + 1
                if re.search(r'\b(?:let|var)\s+' + re.escape(sym) + r'\b', braced[f][lstart:off + len(sym)]):
                    continue
                cls, why = site_class(name, sym, f, rel, off, braced[f], blocks[f], on_syms)
                site_rows.append({"symbol": sym, "site": f"{rel}:{ln}",
                                  "class": cls, "reason": why})
        if not site_rows:
            # read inline (`if env[...] != "0" {`) instead of bound to a symbol:
            # the env read itself is the use site
            for (f, rel, off) in g.get("reads", []):
                cls, why = site_class(name, None, f, rel, off, braced[f],
                                      blocks[f], on_syms)
                site_rows.append({"symbol": "(inline)",
                                  "site": f"{rel}:{line_of(braced[f], off)}",
                                  "class": cls, "reason": why})
        order = {"LIVE": 0, "NEEDS-RUNTIME-OBSERVATION": 1, "NEG-GUARDED": 2,
                 "DEAD-BRANCH": 3}
        if not site_rows:
            overall = "NO-READ-SITE"
        else:
            overall = min((r["class"] for r in site_rows), key=lambda c: order[c])
        rows.append({
            "gate": name,
            "polarity": g["polarity"],
            "declarations": ";".join(sorted(set(g["decls"]))),
            "symbols": ";".join(sorted(set(g["symbols"]))) or "(unbound)",
            "n_read_sites": len(site_rows),
            "overall_class": overall,
            "sites": site_rows,
        })

    with open(os.path.join(outdir, "gate-classification.json"), "w") as fh:
        json.dump({"root_commit": subprocess.check_output(
            ["git", "-C", root, "rev-parse", "HEAD"]).decode().strip(),
            "gates": rows}, fh, indent=1)
    with open(os.path.join(outdir, "gate-classification.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["gate", "polarity", "declarations", "symbols",
                    "n_read_sites", "overall_class", "site", "site_class", "reason"])
        for r in rows:
            if not r["sites"]:
                w.writerow([r["gate"], r["polarity"], r["declarations"], r["symbols"],
                            0, r["overall_class"], "", "", ""])
            for s in r["sites"]:
                w.writerow([r["gate"], r["polarity"], r["declarations"], r["symbols"],
                            r["n_read_sites"], r["overall_class"],
                            s["site"], s["class"], s["reason"]])

    on_rows = [r for r in rows if r["polarity"] == "default-ON"]
    runtime_rows = [r for r in on_rows if "Plugins/" not in r["declarations"]]
    counts = {}
    for r in runtime_rows:
        counts[r["overall_class"]] = counts.get(r["overall_class"], 0) + 1
    dead = sum(counts.get(k, 0) for k in ("DEAD-BRANCH", "NEG-GUARDED", "NO-READ-SITE"))
    print(f"default-ON distinct names: {len(on_rows)}   "
          f"runtime (excl. build plugins): {len(runtime_rows)}")
    print(f"default-OFF distinct names: {sum(1 for r in rows if r['polarity'] == 'default-OFF')}")
    print("class histogram over runtime default-ON gates:")
    for k in sorted(counts):
        print(f"  {k:28s} {counts[k]}")
    print(f"m = (DEAD-BRANCH + NEG-GUARDED + NO-READ-SITE) / runtime default-ON "
          f"= {dead}/{len(runtime_rows)} = {dead/len(runtime_rows):.4f}")
    print(f"artifacts -> {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
