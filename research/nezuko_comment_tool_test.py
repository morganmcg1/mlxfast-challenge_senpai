#!/usr/bin/env python3
"""Adversarial self-test for nezuko_comment_tool.

Every case asserts two things at once:
  * canonicalisation is invariant under the stripper, and
  * substrings that must survive really do survive.

The negative controls matter more than the positives: they prove the canonical
hash is not vacuous, i.e. it *does* move when code, literal text, or macro line
splicing changes.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nezuko_comment_tool as N  # noqa: E402

CASES = [
    ("c", 'const char* u = "http://ex.com/x"; // kill\nint a=1;\n', ["http://ex.com/x"]),
    ("c", "char c = '/'; // kill\nint b;\n", ["'/'"]),
    ("c", 'auto s = R"raw(a // b /* c */)raw"; // kill\n', ["a // b /* c */"]),
    ("c", "#define A x \\\n  // c\n  y\n", ["// c"]),
    ("c", "#define B z \\\n  q // trail \\\n  w\n", ["// trail"]),
    ("c", "/* block */ int k; /* tail */\n", ["int k;"]),
    ("c", "// Copyright 2024 Apple Inc.\nint z;\n", ["Copyright"]),
    ("c", "int q; // \xc2\xa9 not ascii\n", []),
    ("swift", 'let s = "a // b"  // kill\n', ['"a // b"']),
    ("swift", 'let m = """\n  metal // inner\n  """  // kill\n', ["metal // inner"]),
    ("swift", 'let r = #"raw // no"#  // kill\n', ["raw // no"]),
    ("swift", 'let i = "v=\\(x /* q */)"  // kill\n', ["\\(x /* q */)"]),
    ("swift", 'let n = "o\\("i//j")p"  // kill\n', ['i//j']),
    ("swift", "/* outer /* nested */ still */ let q = 1\n", ["let q = 1"]),
    # Adjacent-space artifact: the canonical form must still compare equal.
    ("c", "void f(\n    int ndim /* = -1 */,\n    int bm) {}\n", ["int ndim ,"]),
    ("swift", "/// doc\nfunc f() {}\n", ["func f() {}"]),
]

NEGATIVE = [
    ("code change", "c", "int a = 1; // c\n", "int a = 2; // c\n"),
    ("literal change", "c", 'char*s="x//y";\n', 'char*s="x";\n'),
    ("macro splice", "c", "#define A x \\\n  // c\n  y\n", "#define A x \\\n  y\n"),
    ("swift literal", "swift", 'let a = """\nk // z\n"""\n', 'let a = """\nk\n"""\n'),
]


def main():
    bad = 0
    for mode, text, survive in CASES:
        new, freed, skipped = N.strip_text(text, mode)
        same = N.digest(text, mode) == N.digest(new, mode)
        kept = [s for s in survive if s not in new]
        if not same or kept:
            bad += 1
            print(f"FAIL {mode} {text!r} -> {new!r} hash_eq={same} missing={kept}")
        else:
            print(f"ok freed={freed:3d} kept={skipped} | {text!r:56.56} -> {new!r:40.40}")

    print()
    for name, mode, a, b in NEGATIVE:
        moved = N.digest(a, mode) != N.digest(b, mode)
        print(f"{'ok ' if moved else 'FAIL'} negative control: {name} detected={moved}")
        bad += not moved

    print("\nFAILURES:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
