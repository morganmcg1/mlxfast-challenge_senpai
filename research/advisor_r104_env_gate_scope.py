#!/usr/bin/env python3
"""Classify every runtime env-gate read in Sources/ + Vendor/ by binding scope.

Question: can a gate be flipped WITHIN a live process, or is it frozen at
first-touch (Swift global `let` / C++ function-local `static`)?
"""
import os, re, sys, collections

# repo root = parent of the directory holding this script (research/..)
ROOT = os.environ.get(
    "MLXFAST_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
NAME = re.compile(r'"(DARKBLOOM_[A-Z0-9_]+|MLX_[A-Z0-9_]+|LAGUNA_[A-Z0-9_]+)"')

swift_env = re.compile(r'ProcessInfo\.processInfo\.environment')
c_env = re.compile(r'\bgetenv\s*\(')

def scan(path):
    try:
        lines = open(path, "r", errors="replace").read().split("\n")
    except Exception:
        return []
    out = []
    for i, ln in enumerate(lines):
        if not (swift_env.search(ln) or c_env.search(ln)):
            continue
        # gather the gate name from this line or the next few
        nm = None
        for j in range(i, min(i + 4, len(lines))):
            m = NAME.search(lines[j])
            if m:
                nm = m.group(1)
                break
        if nm is None:
            continue
        out.append((path, i + 1, nm, lines))
    return out

hits = []
for sub in ("Sources", "Vendor"):
    for dirpath, _, files in os.walk(os.path.join(ROOT, sub)):
        for f in files:
            if f.endswith((".swift", ".cpp", ".h", ".hpp", ".c", ".m", ".mm")):
                hits.extend(scan(os.path.join(dirpath, f)))

def classify(path, lineno, lines):
    """Walk backwards to the binding statement; decide freeze-at-first-touch."""
    # find the start of the statement/declaration this read belongs to
    for k in range(lineno - 1, max(-1, lineno - 12), -1):
        s = lines[k]
        st = s.strip()
        if not st:
            continue
        # Swift: global or static let/var
        m = re.match(r'^(private\s+|public\s+|internal\s+|fileprivate\s+)?(static\s+)?(let|var)\s+(\w+)', st)
        if m and (s[0] not in " \t" or m.group(2)):
            indent = len(s) - len(s.lstrip())
            kind = m.group(3)
            if indent == 0 or m.group(2):
                return ("swift-global-" + kind, m.group(4))
            return ("swift-local-" + kind, m.group(4))
        # C++ static
        if re.search(r'\bstatic\b.*=', st) or re.match(r'^\s*static\b', st):
            return ("cpp-static", st[:60])
        if re.match(r'^\s*(inline\s+)?(bool|int|const char\s*\*|std::string|auto)\s+\w+\s*\(', st):
            return ("cpp-function-body", st[:60])
    return ("unclassified", "")

by_kind = collections.Counter()
gate_kind = {}
rows = []
for path, lineno, nm, lines in hits:
    kind, sym = classify(path, lineno, lines)
    by_kind[kind] += 1
    gate_kind.setdefault(nm, set()).add(kind)
    rows.append((os.path.relpath(path, ROOT), lineno, nm, kind, sym))

print("total env-read sites found:", len(rows))
print()
for k, v in by_kind.most_common():
    print(f"  {k:24s} {v}")
print()

# does any gate have a read site that is NOT frozen?
frozen = {"swift-global-let", "cpp-static"}
live = sorted(g for g, ks in gate_kind.items() if not ks <= frozen)
print("distinct gates seen:", len(gate_kind))
print("gates with at least one NON-frozen read site:", len(live))
for g in live:
    print("   ", g, sorted(gate_kind[g]))
print()
print("--- unclassified sites (need eyeball) ---")
for r in rows:
    if r[3] == "unclassified":
        print("   ", r[0], r[1], r[2])
