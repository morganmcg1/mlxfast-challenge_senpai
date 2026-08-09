#!/bin/bash
# Set the source-constant empty-dispatch ladder rung and rebuild the scored
# worker. The ranked host never sees our environment, so K must be a source
# constant, not an env var.
#
# usage: set_ladder.sh <K> [<threadgroups>]
set -u

ROOT="$(pwd)"
SRC="Sources/MLXFastModel/LagunaRuntimeModel.swift"
K="${1:?K required}"
TG="${2:-8}"
OUT="/tmp/r93"
mkdir -p "$OUT"

python3 - "$SRC" "$K" "$TG" <<'PY'
import re, sys
path, k, tg = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(path).read()
s, n1 = re.subn(r'("DARKBLOOM_INJECT_DECODE_EMPTY", )\d+\)', r'\g<1>%s)' % k, s)
s, n2 = re.subn(r'("DARKBLOOM_INJECT_EMPTY_TG", )\d+\)', r'\g<1>%s)' % tg, s)
assert n1 == 1 and n2 == 1, (n1, n2)
open(path, "w").write(s)
print(f"patched DECODE_EMPTY={k} EMPTY_TG={tg}")
PY

git --no-pager diff --stat -- "$SRC"
git --no-pager diff -- "$SRC" | grep '^[-+].*DARKBLOOM_INJECT'

mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${ROOT}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker \
    > "${OUT}/build-K${K}.log" 2>&1
echo "build rc=$?"
tail -1 "${OUT}/build-K${K}.log"
shasum -a 256 .build-worker/release/mlxfast-runtime-worker
git checkout -- Package.resolved 2>/dev/null
