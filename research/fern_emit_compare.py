#!/usr/bin/env python3
"""Compare the emitted release code of the MLXFastModel module across two builds.

Usage:
    fern_emit_compare.py dump   <MLXFastModel.build dir> <out.json>
    fern_emit_compare.py diff   <base.json> <cand.json>

Whole-module optimization lets the compiler place any symbol in any per-file
object output, so a behaviour-neutral source split must preserve the
module-wide section byte totals and the module-wide defined-symbol multiset
even though individual .o files move around.

Swift mangles a file-private declaration with a discriminator derived from the
file name, so moving a `private` decl to another file renames its symbol
without changing its code. Symbol names are therefore compared both raw and
with those discriminators normalised away.
"""

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

PRIVATE_DISCRIMINATOR = re.compile(r"\d+_[0-9A-Fa-f]{32}LL")
SECTION = re.compile(r"^\s*Section \((__\w+), (__\w+)\): (\d+)")
LINKED_SEGMENT = re.compile(r"^Segment (__\w+):")
LINKED_SECTION = re.compile(r"^\s+Section (__\w+): (\d+)")


def _xcrun(tool: str) -> str:
    return subprocess.run(
        ["xcrun", "--find", tool], capture_output=True, text=True, check=True
    ).stdout.strip()


def dump(target: Path, out_path: Path) -> None:
    nm = _xcrun("llvm-nm")
    size = _xcrun("size")
    if target.is_dir():
        objects = sorted(target.glob("*.o"))
        if not objects:
            raise SystemExit(f"no object files under {target}")
    else:
        objects = [target]

    sections: Counter[str] = Counter()
    symbols: Counter[str] = Counter()
    per_object: dict[str, dict[str, int]] = {}

    for obj in objects:
        text = subprocess.run(
            [size, "-m", str(obj)], capture_output=True, text=True, check=True
        ).stdout
        obj_sections: Counter[str] = Counter()
        segment = "?"
        for line in text.splitlines():
            match = SECTION.match(line)
            if match:
                obj_sections[f"{match.group(1)},{match.group(2)}"] += int(match.group(3))
                continue
            match = LINKED_SEGMENT.match(line)
            if match:
                segment = match.group(1)
                continue
            match = LINKED_SECTION.match(line)
            if match:
                obj_sections[f"{segment},{match.group(1)}"] += int(match.group(2))
        sections.update(obj_sections)

        names = subprocess.run(
            [nm, "--defined-only", "-j", str(obj)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        symbols.update(name for name in names if name)
        per_object[obj.name] = {
            "text": obj_sections.get("__TEXT,__text", 0),
            "symbols": len(names),
        }

    normalised = Counter(
        PRIVATE_DISCRIMINATOR.sub("<PRIV>", name) for name in symbols.elements()
    )
    payload = {
        "build_dir": str(target),
        "objects": [obj.name for obj in objects],
        "sections": dict(sections),
        "symbols": dict(symbols),
        "symbols_normalised": dict(normalised),
        "per_object": per_object,
    }
    out_path.write_text(json.dumps(payload, indent=1, sort_keys=True))
    print(f"objects={len(objects)} symbols={sum(symbols.values())}")
    for key in sorted(sections):
        print(f"  {key} = {sections[key]}")


def _counter_diff(base: Counter[str], cand: Counter[str]) -> tuple[Counter, Counter]:
    return cand - base, base - cand


def diff(base_path: Path, cand_path: Path) -> int:
    base = json.loads(base_path.read_text())
    cand = json.loads(cand_path.read_text())

    print("== section byte totals (__DWARF debug sections excluded) ==")
    keys = sorted(set(base["sections"]) | set(cand["sections"]))
    section_delta = 0
    for key in keys:
        if key.startswith("__DWARF"):
            continue
        b = base["sections"].get(key, 0)
        c = cand["sections"].get(key, 0)
        flag = "" if b == c else "   <-- DIFF"
        if key == "__TEXT,__text":
            section_delta = c - b
        print(f"  {key:28s} base={b:9d} cand={c:9d} delta={c - b:+d}{flag}")

    print("\n== defined symbols, raw mangled names ==")
    added, removed = _counter_diff(
        Counter(base["symbols"]), Counter(cand["symbols"])
    )
    print(f"  base={sum(base['symbols'].values())} cand={sum(cand['symbols'].values())}")
    print(f"  only-in-cand={sum(added.values())} only-in-base={sum(removed.values())}")

    print("\n== defined symbols, private discriminators normalised ==")
    # Assembler-local constant-pool labels (lCPI*, Ltmp*) are placement noise.
    def _named(payload: dict[str, int]) -> Counter[str]:
        return Counter({k: v for k, v in payload.items() if k.startswith("_$") or k.startswith("__")})

    n_added, n_removed = _counter_diff(
        _named(base["symbols_normalised"]), _named(cand["symbols_normalised"])
    )
    print(f"  only-in-cand={sum(n_added.values())} only-in-base={sum(n_removed.values())}")
    for name in sorted(n_added)[:40]:
        print(f"    + {name}")
    for name in sorted(n_removed)[:40]:
        print(f"    - {name}")

    print("\n== per-object __text ==")
    names = sorted(set(base["per_object"]) | set(cand["per_object"]))
    for name in names:
        b = base["per_object"].get(name, {}).get("text", 0)
        c = cand["per_object"].get(name, {}).get("text", 0)
        if b != c:
            print(f"  {name:40s} base={b:8d} cand={c:8d} delta={c - b:+d}")

    neutral = section_delta == 0 and not n_added and not n_removed
    print(f"\nVERDICT: {'code-identical' if neutral else 'code CHANGED'}")
    return 0 if neutral else 1


def _symbol_sizes(binary: Path) -> dict[str, int]:
    """Per-symbol byte length, derived from address gaps in a linked image.

    Mach-O carries no symbol sizes, so the length of each symbol is the gap to
    the next defined symbol address.
    """
    nm = _xcrun("llvm-nm")
    out = subprocess.run(
        [nm, "-n", "--defined-only", str(binary)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    entries: list[tuple[int, str, str]] = []
    for line in out.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[0].strip():
            entries.append((int(parts[0], 16), parts[1], parts[2]))
    sizes: dict[str, int] = {}
    for index, (addr, kind, name) in enumerate(entries):
        if kind.upper() != "T":
            continue
        nxt = next((a for a, _, _ in entries[index + 1 :] if a > addr), addr)
        sizes[PRIVATE_DISCRIMINATOR.sub("<PRIV>", name)] = nxt - addr
    return sizes


def compare_sizes(base_bin: Path, cand_bin: Path, needle: str) -> int:
    base = _symbol_sizes(base_bin)
    cand = _symbol_sizes(cand_bin)
    keys = {k for k in set(base) | set(cand) if needle in k}
    changed = []
    for key in sorted(keys):
        b, c = base.get(key), cand.get(key)
        if b != c:
            changed.append((key, b, c))
    print(f"text symbols matching {needle!r}: base={len([k for k in base if needle in k])} cand={len([k for k in cand if needle in k])}")
    print(f"size-identical: {len(keys) - len(changed)}   size-changed-or-missing: {len(changed)}")
    for key, b, c in changed[:60]:
        print(f"  {b} -> {c}  {key[:150]}")
    return 0 if not changed else 1


ADDR = re.compile(r"0x[0-9a-f]+")
IMM = re.compile(r"#-?\d+")
OPERAND_SYM = re.compile(r"<[^>]*>")
BLOCK_HEADER = re.compile(r"^[0-9a-f]+ <(.+)>:$")


def _disassemble(binary: Path, symbols: list[str]) -> dict[str, list[str]]:
    objdump = _xcrun("llvm-objdump")
    out = subprocess.run(
        [
            objdump,
            "-d",
            "--no-show-raw-insn",
            f"--disassemble-symbols={','.join(symbols)}",
            str(binary),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    blocks: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in out.splitlines():
        header = BLOCK_HEADER.match(line)
        if header:
            current = []
            blocks[PRIVATE_DISCRIMINATOR.sub("<PRIV>", header.group(1))] = current
            continue
        if current is None or ":" not in line:
            continue
        insn = line.split(":", 1)[1].strip()
        if not insn:
            continue
        insn = ADDR.sub("HEX", OPERAND_SYM.sub("SYM", insn))
        current.append(IMM.sub("#IMM", insn).split(";")[0].strip())
    return blocks


def _text_symbol_names(binary: Path, needle: str) -> list[str]:
    out = subprocess.run(
        [_xcrun("llvm-nm"), "-n", "--defined-only", str(binary)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    names = []
    for line in out.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[1].upper() == "T" and needle in parts[2]:
            names.append(parts[2])
    return names


def compare_asm(base_bin: Path, cand_bin: Path, needle: str) -> int:
    # Each side must be looked up with its own raw mangled names: moving a
    # file-private declaration changes its file discriminator.
    raw = _text_symbol_names(base_bin, needle)
    base = _disassemble(base_bin, raw)
    cand = _disassemble(cand_bin, _text_symbol_names(cand_bin, needle))

    identical, island_only, differing, missing = 0, [], [], []
    for name in sorted(set(base) | set(cand)):
        b, c = base.get(name), cand.get(name)
        if b is None or c is None:
            missing.append(name)
            continue
        if b == c:
            identical += 1
            continue
        # A linker branch island parked in inter-function padding appears as
        # extra trailing unconditional branches beyond the real body.
        trim_b = list(b)
        trim_c = list(c)
        while trim_b and trim_b[-1].startswith("b\t"):
            trim_b.pop()
        while trim_c and trim_c[-1].startswith("b\t"):
            trim_c.pop()
        if trim_b == trim_c:
            island_only.append(name)
        else:
            differing.append((name, len(b), len(c)))

    print(f"symbols disassembled: base={len(base)} cand={len(cand)} (requested {len(raw)})")
    print(f"  body-identical            : {identical}")
    print(f"  identical modulo islands  : {len(island_only)}")
    print(f"  body-DIFFERENT            : {len(differing)}")
    print(f"  present on one side only  : {len(missing)}")
    for name in island_only:
        print(f"    [island] {name[:130]}")
    for name, nb, nc in differing:
        print(f"    [DIFF] {nb}->{nc} insns  {name[:130]}")
    for name in missing:
        print(f"    [one-side] {name[:130]}")
    return 0 if not differing else 1


def main() -> int:
    if len(sys.argv) == 5 and sys.argv[1] == "sizes":
        return compare_sizes(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
    if len(sys.argv) == 5 and sys.argv[1] == "asm":
        return compare_asm(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    mode, first, second = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    if mode == "dump":
        dump(first, second)
        return 0
    if mode == "diff":
        return diff(first, second)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
