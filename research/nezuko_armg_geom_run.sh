#!/bin/bash
# Build + run the offline gate_sp geometry probe. GPU work goes through run_job.
set -u
cd "$(dirname "$0")/.."
out=/tmp/nezgeom
rm -f "$out"
echo "== build =="
xcrun swiftc -O research/nezuko_armg_gate_geom_probe.swift -o "$out" || exit 1
echo "== run =="
"$out"
echo "== rc=$? =="
