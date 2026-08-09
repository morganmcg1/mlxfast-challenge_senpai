#!/usr/bin/env python3
"""Verbatim carve of the Laguna MLP/MoE/decoder-layer region into a new file."""

src = 'Sources/MLXFastModel/LagunaRuntimeModel.swift'
dst = 'Sources/MLXFastModel/LagunaRuntimeLayers.swift'
raw = open(src, 'rb').read()
lines = raw.split(b'\n')

START, END = 8693, 11279
moved = lines[START - 1:END]
assert moved[0].startswith(b'final class LagunaRuntimeMLP'), moved[0][:60]
assert moved[-1] == b'}', moved[-1][:60]
assert lines[END] == b'', repr(lines[END])
assert lines[END + 1].startswith(b'/// The Laguna text tower'), lines[END + 1][:40]

header = b"""import Foundation
import MLX
import MLXFast
import MLXLMCommon
import MLXNN

// Laguna feed-forward, routing, and decoder-layer declarations, split verbatim
// out of `LagunaRuntimeModel.swift` so neither file approaches the per-file
// submission cap. Same module and target; text and declaration order unchanged.

"""

moved_text = b'\n'.join(moved) + b'\n'
open(dst, 'wb').write(header + moved_text)
open(src, 'wb').write(b'\n'.join(lines[:START - 1] + lines[END + 1:]))

print('moved content bytes', len(moved_text))
print('header bytes', len(header))
print('new file bytes', len(header) + len(moved_text))
