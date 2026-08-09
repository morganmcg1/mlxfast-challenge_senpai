import re
import sys
from collections import Counter

sys.path.insert(0, '/tmp/r103b')
from comment_strip_diff import strip, blob  # noqa: E402


def norm_lines(t):
    return [re.sub(r'\s+', ' ', l).strip() for l in strip(t).split('\n') if l.strip()]


old = (norm_lines(blob('30f752df', 'Sources/MLXFastModel/LagunaRuntimeModel.swift'))
       + norm_lines(blob('30f752df', 'Sources/MLXFastModel/LagunaRuntimeLayers.swift')))
new = norm_lines(blob('0f6862d0', 'Sources/MLXFastModel/LagunaRuntimeModel.swift'))
co, cn = Counter(old), Counter(new)
added, removed = cn - co, co - cn
print(f"OLD lines(LRM+Layers, stripped)={len(old)}  NEW lines(LRM, stripped)={len(new)}")
print(f"multiset ADDED={sum(added.values())}  REMOVED={sum(removed.values())}")
print("\n===== ADDED (NEW only) =====")
for l, c in added.most_common():
    print(f"[{c}] {l}")
print("\n===== REMOVED (OLD only) =====")
for l, c in removed.most_common():
    print(f"[{c}] {l}")
