#!/bin/bash
# __compute section byte count for one .metal file, per architecture.
# Matched-null use only: compare arms compiled with identical flags.
set -u
FN=laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6
cd /tmp/r107f || exit 1
for f in "$@"; do
  b="${f%.metal}"
  xcrun metal -std=metal4.0 -fno-fast-math -c "$f" -o "$b.air" 2>/dev/null || { echo "$b COMPILE_FAIL"; continue; }
  xcrun metallib "$b.air" -o "$b.metallib" 2>/dev/null || { echo "$b METALLIB_FAIL"; continue; }
  printf '{ "pipelines": { "compute_pipelines": [ { "compute_function": "%s" } ] } }\n' "$FN" > "s_$b.mtlp-json"
  line="$b"
  for arch in applegpu_g16s applegpu_g17s; do
    if xcrun applegpu-nt -arch "$arch" -platform_version macos 26.0 26.5 -N "s_$b.mtlp-json" "$b.metallib" -o "$b.$arch.bin" >/dev/null 2>&1; then
      bytes=$(xcrun metal-size -m "$b.$arch.bin" 2>/dev/null | awk '/Section __compute:/ {print $NF; exit}')
      line="$line $arch=${bytes:-NA}"
    else
      line="$line $arch=NT_FAIL"
    fi
  done
  echo "$line"
done
