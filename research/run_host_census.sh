#!/usr/bin/env bash

set -uo pipefail

cd "$(dirname "$0")/.."

raw="research/decode-host-census-raw.log"
rounds="${MLXFAST_HOST_CENSUS_ROUNDS:-5}"

{
  echo "HOST_CENSUS host_model=$(sysctl -n hw.model 2>/dev/null || true) arch=$(uname -m) os=$(sw_vers -productVersion)"
  echo "HOST_CENSUS command=MLXFAST_HOST_CENSUS=1 MLXFAST_HOST_CENSUS_ROUNDS=${rounds} ./benchmark.sh --local-iterate"
  MLXFAST_HOST_CENSUS=1 MLXFAST_HOST_CENSUS_ROUNDS="${rounds}" ./benchmark.sh --local-iterate
} 2>&1 | tee "${raw}"
status=${PIPESTATUS[0]}

if grep -q "HOST_CENSUS complete" "${raw}"; then
  exit 0
fi
exit "${status}"
