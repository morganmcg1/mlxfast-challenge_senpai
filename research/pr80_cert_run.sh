#!/bin/bash
# PR #80 bitwise logit certificate runner (research-only).
#
# Runs one arm per invocation line, strictly sequentially, so only one process
# ever holds the ~21.6 GB model. Each arm re-execs the same worker binary with a
# different DARKBLOOM_* selection; the driver digests the exact logit bit
# patterns so arms can be compared byte for byte.
#
#   research/pr80_cert_run.sh OUTDIR STEPS "label|ENV=V ENV2=V" ...
set -u
outdir="$1"; shift
steps="$1"; shift
mkdir -p "$outdir"
rc=0
for spec in "$@"; do
  label="${spec%%|*}"
  envs="${spec#*|}"
  [ "$envs" = "$label" ] && envs=""
  echo "=== ARM $label  env: ${envs:-<defaults>} ==="
  # shellcheck disable=SC2086
  /usr/bin/env MLXFAST_WEIGHTS_PATH=weights $envs \
    python3 research/frieren_pr80_logit_bitwise.py \
      --label "$label" --steps "$steps" --out "$outdir/$label.json" \
    || rc=1
done
exit "$rc"
