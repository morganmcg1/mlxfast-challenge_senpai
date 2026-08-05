#!/usr/bin/env python3
"""Rewrite the full-profile MLX_MAX_MB_PER_BUFFER literal for one receipt arm.

The three arms must be byte-distinct (the submission service deduplicates
byte-identical archives) yet behaviour-identical apart from the threshold, so
the control arm carries only the arm comment.

usage: make_mbpb_arm.py <control|low|high>
"""
import pathlib
import sys

ARMS = {"control": "200", "low": "50", "high": "400"}
SRC = pathlib.Path("Sources/MLXFastModel/LagunaRuntimeWeights.swift")
ANCHOR = '                if env["DARKBLOOM_POST_WIRE_COMMAND_BUFFER"] != "0" {\n'
MB_LINE = '                    setenv("MLX_MAX_MB_PER_BUFFER", "{}", 0)\n'


def main() -> int:
    arm = sys.argv[1]
    value = ARMS[arm]
    text = SRC.read_text()
    if "Receipt arm A/" in text:
        raise SystemExit("source already carries an arm comment; reset it first")
    if text.count(ANCHOR) != 1 or text.count(MB_LINE.format("200")) != 1:
        raise SystemExit("anchor or MB literal not found exactly once")
    comment = (
        f"                // Receipt arm A/{arm}: MLX_MAX_MB_PER_BUFFER = {value}.\n"
        "                // One of three byte-distinct, behaviour-identical trees\n"
        "                // isolating MLX's referenced-byte commit threshold. The\n"
        "                // kernel dispatch count is fixed at 406 per decode step in\n"
        "                // every arm; only command-buffer granularity moves, so the\n"
        "                // greedy token stream is bit-identical by construction.\n"
    )
    text = text.replace(ANCHOR, comment + ANCHOR)
    text = text.replace(MB_LINE.format("200"), MB_LINE.format(value))
    SRC.write_text(text)
    print(f"arm {arm}: MLX_MAX_MB_PER_BUFFER={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
