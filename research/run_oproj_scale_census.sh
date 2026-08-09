#!/usr/bin/env bash

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RAW_DIR="${ROOT}/.agent_tmp/oproj-scale-census-raw"

rm -rf "${RAW_DIR}"
mkdir -p "${RAW_DIR}"

export DARKBLOOM_OPROJ_CENSUS_DIR="${RAW_DIR}"
exec "${ROOT}/benchmark.sh" --local-iterate
