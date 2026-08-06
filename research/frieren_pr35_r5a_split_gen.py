#!/usr/bin/env python3
"""Split the MLX `verbose: true` dumps captured by frieren_pr35_r5a_dump.sh into
one .metal artifact per generated kernel. Research-only; not part of the submission.

MLX prints each generated kernel as

    Generated source code for `<name>`:
    ```
    <exact text handed to makeLibrary, minus the metal::utils() preamble>
    ```

so the artifacts below are byte-exact MLX output with the fence and banner
removed. research/frieren_pr35_lanemajor_bitwise.swift compiles them verbatim,
which is why it never has to re-derive MLX's write_signature.

  python3 research/frieren_pr35_r5a_split_gen.py /tmp/pr35_r5a research/r5a_kernels
"""
import os
import re
import sys

BANNER = re.compile(r"^Generated source code for `([^`]+)`:$")


def split(path):
    out = []
    lines = open(path).read().split("\n")
    i = 0
    while i < len(lines):
        m = BANNER.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        assert lines[i + 1] == "```", repr(lines[i + 1])
        j = i + 2
        body = []
        while lines[j] != "```":
            body.append(lines[j])
            j += 1
        out.append((name, "\n".join(body) + "\n"))
        i = j + 1
    return out


def main():
    src_dir, dst_dir = sys.argv[1], sys.argv[2]
    os.makedirs(dst_dir, exist_ok=True)
    total = 0
    for heads in (48, 64):
        for name, body in split(os.path.join(src_dir, f"gen_h{heads}.txt")):
            arm = "lanemajor" if "_lm1_" in name else "wide"
            dst = os.path.join(dst_dir, f"{arm}_h{heads}.metal")
            with open(dst, "w") as fh:
                fh.write(body)
            print(f"{dst}  {len(body)} B  kernel={name}")
            total += 1
    print(f"{total} artifacts")
    return 0 if total == 4 else 1


if __name__ == "__main__":
    sys.exit(main())
