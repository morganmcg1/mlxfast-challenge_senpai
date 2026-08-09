#!/usr/bin/env python3
"""Remove the trailing `// senpai-r93-*` replicate marker from the scored file.

Used at the end of the experiment to return
Sources/MLXFastModel/LagunaRuntimeModel.swift to its BASE_SHA content, and as a
check that the marker really is the only difference.
"""
import subprocess

PATH = 'Sources/MLXFastModel/LagunaRuntimeModel.swift'

lines = open(PATH).read().rstrip('\n').split('\n')
keep = list(lines)
while keep and (keep[-1].startswith('// senpai-r93-') or not keep[-1].strip()):
    keep.pop()
open(PATH, 'w').write('\n'.join(keep) + '\n')
print('removed %d trailing line(s); now ends with: %r'
      % (len(lines) - len(keep), keep[-1]))

base = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True,
                      text=True).stdout.strip()
print('HEAD', base)
