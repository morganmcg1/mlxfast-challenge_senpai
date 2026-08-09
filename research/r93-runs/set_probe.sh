#!/usr/bin/env bash
# Arm C: set the R93-C stall probe spec as a SOURCE CONSTANT and rebuild the
# scored worker. The upstream probe (#498) is env-var driven; env vars do not
# reach the ranked host, so the knob has to live in the submitted file.
#
#   ./set_probe.sh ""                # probe off (byte-identical behaviour)
#   ./set_probe.sh routed:fma:24     # routed kernel, float ladder, n = 24
set -euo pipefail
cd "$(dirname "$0")/../.."

SPEC="${1-}"
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift

python3 - "$SRC" "$SPEC" <<'PY'
import re, sys
path, spec = sys.argv[1], sys.argv[2]
text = open(path).read()
pat = r'(// senpai-r93-armc-spec: "" \| "<target>:<kind>:<n>"\n    let raw = )"[^"]*"'
new, n = re.subn(pat, lambda m: m.group(1) + '"%s"' % spec, text)
assert n == 1, "probe spec anchor not found (n=%d)" % n
open(path, "w").write(new)
print("probe spec ->", repr(spec))
PY

swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker
git checkout -- Package.resolved 2>/dev/null || true
shasum -a 256 .build-worker/release/mlxfast-runtime-worker
