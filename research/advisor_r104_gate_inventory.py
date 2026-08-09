#!/usr/bin/env python3
"""Inventory every runtime env gate on the executed path, with:

  * default polarity  -- OFF (dormant code), ON (kill switch), or a dial default
  * the symbol it binds and how many times that symbol is USED
  * how many research/ files ever mention the gate  (rule-83 prior-work check)

The prize column is DORMANT-AND-UNMEASURED: default-OFF gates guarding
already-written code that no research note has ever touched.

Scope note: we deliberately EXCLUDE Vendor test / server-CLI / jaccl
distributed code, which this benchmark never enters. See §9.1 of
research/advisor-r104-the-receipt-is-the-instrument.md.
"""
import os, re, sys, collections, json

ROOT = os.environ.get(
    "MLXFAST_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

SCAN_DIRS = [
    "Sources",
    "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend",
    "Vendor/mlx-swift/Source/Cmlx/mlx/mlx",
    "Vendor/mlx-swift/Source/MLX",
    "Vendor/mlx-swift-lm/Libraries/MLXLMCommon",
]
EXCLUDE = ("/Tests/", "/CLI/", "/distributed/", "/jaccl/", "/tests/")

NAME = re.compile(r'"(DARKBLOOM_[A-Z0-9_]+|MLX_[A-Z0-9_]+|LAGUNA_[A-Z0-9_]+)"')
ENV = re.compile(r'ProcessInfo\.processInfo\.environment|\bgetenv\s*\(')

SRC_EXT = (".swift", ".cpp", ".h", ".hpp", ".c", ".m", ".mm")


def source_files():
    seen = set()
    for sub in SCAN_DIRS:
        base = os.path.join(ROOT, sub)
        for dp, _, fs in os.walk(base):
            if any(x in dp + "/" for x in EXCLUDE):
                continue
            for f in fs:
                if f.endswith(SRC_EXT):
                    p = os.path.join(dp, f)
                    if p not in seen:
                        seen.add(p)
                        yield p


def polarity(block: str, gate: str):
    """Classify the default the code takes when the variable is ABSENT."""
    b = " ".join(block.split())
    # Swift boolean idioms
    if re.search(re.escape(gate) + r'"\s*\]\s*==\s*"1"', b):
        return ("OFF", "== \"1\"")
    if re.search(re.escape(gate) + r'"\s*\]\s*!=\s*"0"', b):
        return ("ON", "!= \"0\"")
    if re.search(re.escape(gate) + r'"\s*\]\s*==\s*"0"', b):
        return ("OFF", "== \"0\"")
    if re.search(re.escape(gate) + r'"\s*\]\s*!=\s*"1"', b):
        return ("ON", "!= \"1\"")
    # guard/else fallback -> a dial
    m = re.search(r'else\s*\{?\s*return\s+([^\s};]+)', b)
    if m:
        return ("DIAL", "default " + m.group(1))
    m = re.search(r'\?\?\s*([^\s};,)]+)', b)
    if m:
        return ("DIAL", "?? " + m.group(1))
    # C++ getenv idioms
    if "value == nullptr ||" in b or "== nullptr ||" in b:
        return ("ON", "nullptr -> true")
    if re.search(r'\breturn\s+e\s*&&', b) or re.search(r'&&\s*atoi', b):
        return ("OFF", "nullptr -> false")
    return ("?", b[:70])


def bound_symbol(block: str):
    m = re.search(r'\b(?:let|var)\s+(\w+)', block)
    if m:
        return m.group(1)
    m = re.search(r'\bstatic\s+\w+\s+(\w+)\s*\(', block)
    if m:
        return m.group(1)
    m = re.search(r'\bstatic\s+\w+\s+(\w+)\s*=', block)
    if m:
        return m.group(1)
    return None


# ---- pass 1: find gate read sites -------------------------------------------
sites = {}   # gate -> list of dict
for path in source_files():
    try:
        text = open(path, "r", errors="replace").read()
    except Exception:
        continue
    if "DARKBLOOM_" not in text and "MLX_" not in text and "LAGUNA_" not in text:
        continue
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if not ENV.search(ln):
            continue
        block = "\n".join(lines[max(0, i - 4): i + 8])
        m = NAME.search(block)
        if not m:
            continue
        gate = m.group(1)
        pol, ev = polarity(block, gate)
        sym = bound_symbol(block)
        sites.setdefault(gate, []).append(
            dict(file=os.path.relpath(path, ROOT), line=i + 1,
                 polarity=pol, evidence=ev, symbol=sym)
        )

# ---- pass 2: how often is the bound symbol actually used? -------------------
all_src = {}
for path in source_files():
    try:
        all_src[path] = open(path, "r", errors="replace").read()
    except Exception:
        pass

def symbol_uses(sym):
    if not sym:
        return -1
    pat = re.compile(r'\b' + re.escape(sym) + r'\b')
    return sum(len(pat.findall(t)) for t in all_src.values())

# ---- pass 3: prior research mentions (rule 83) ------------------------------
# IMPORTANT: this script writes an artifact into research/, and the note that
# interprets it quotes gate names verbatim. Both must be excluded or a re-run
# reports its own output as prior work. Source patches and raw logs are also
# excluded: a gate name appearing in a diff hunk is not a measurement.
SELF = (
    "research/artifacts/advisor-r104-gate-inventory.json",
    "research/advisor_r104_gate_inventory.py",
    "research/advisor-r104-the-receipt-is-the-instrument.md",
)
NOT_WRITEUP = (".patch", ".diff", ".log", ".json", ".csv", ".out")

research_dir = os.path.join(ROOT, "research")
research_text = {}
for dp, _, fs in os.walk(research_dir):
    for f in fs:
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, ROOT)
        if rel in SELF or rel.endswith(NOT_WRITEUP):
            continue
        try:
            if os.path.getsize(p) > 4_000_000:
                continue
            research_text[rel] = open(p, "r", errors="replace").read()
        except Exception:
            pass

def research_hits(gate):
    n_files = sum(1 for t in research_text.values() if gate in t)
    # docs only (exclude scripts/shell) = "has anyone written it up in prose?"
    n_docs = sum(1 for k, t in research_text.items()
                 if gate in t and k.endswith(".md"))
    return n_files, n_docs


rows = []
for gate, ss in sites.items():
    pol = ss[0]["polarity"]
    for s in ss:
        if s["polarity"] != "?":
            pol = s["polarity"]
            break
    sym = next((s["symbol"] for s in ss if s["symbol"]), None)
    nf, nd = research_hits(gate)
    rows.append(dict(
        gate=gate, polarity=pol,
        evidence=next((s["evidence"] for s in ss if s["polarity"] == pol), ""),
        site=f'{ss[0]["file"]}:{ss[0]["line"]}',
        symbol=sym, uses=symbol_uses(sym),
        research_files=nf, research_docs=nd,
    ))

rows.sort(key=lambda r: (r["research_docs"], r["research_files"], -r["uses"]))

print(f"executed-path env gates: {len(rows)}")
print()
counts = collections.Counter(r["polarity"] for r in rows)
for k in ("OFF", "ON", "DIAL", "?"):
    if counts[k]:
        print(f"  default {k:5s} {counts[k]}")
print()

dormant = [r for r in rows
           if r["polarity"] == "OFF" and r["research_docs"] == 0
           and r["uses"] >= 2]
print(f"=== SHORTLIST: default-OFF, never written up, symbol actually used "
      f"({len(dormant)}) ===")
print(f'{"gate":46s} {"uses":>4s} {"rfiles":>6s}  site')
for r in dormant:
    print(f'{r["gate"]:46s} {r["uses"]:4d} {r["research_files"]:6d}  {r["site"]}')
print()

kill = [r for r in rows
        if r["polarity"] == "ON" and r["uses"] >= 2]
print(f"=== KILL SWITCHES (default ON -> usable as positive controls) "
      f"({len(kill)}) ===")
for r in kill[:40]:
    print(f'{r["gate"]:46s} {r["uses"]:4d} {r["research_docs"]:3d}docs  {r["site"]}')
print()

dials = [r for r in rows if r["polarity"] == "DIAL" and r["uses"] >= 2]
print(f"=== DIALS (non-binary default) ({len(dials)}) ===")
for r in dials[:40]:
    print(f'{r["gate"]:46s} {r["evidence"]:22s} {r["uses"]:4d} '
          f'{r["research_docs"]:3d}docs  {r["site"]}')
print()

dead = [r for r in rows if r["uses"] in (0, 1)]
print(f"=== BOUND BUT NEVER USED (symbol occurs <=1x => dead gate) ({len(dead)}) ===")
for r in dead[:30]:
    print(f'{r["gate"]:46s} sym={r["symbol"]}  {r["site"]}')

out = os.path.join(ROOT, "research", "artifacts", "advisor-r104-gate-inventory.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w") as fh:
    json.dump(rows, fh, indent=1, sort_keys=True)
print()
print("wrote", os.path.relpath(out, ROOT))
