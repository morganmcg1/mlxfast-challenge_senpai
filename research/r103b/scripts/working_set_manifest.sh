#!/bin/bash
# Rung 0: sha256 working-set digests for the OLD/NEW differential trees.
set -u
ROOT="/Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-tanjiro/workspace/target"
OLDWT="${ROOT}/.mlxfast-private/r103b-old"
NEWWT="${ROOT}/.mlxfast-private/r103b-new"
OUT=/tmp/r103b/working-set-manifest.tsv

{
  printf 'component\trevision\tsha256\tbytes\tpath\n'

  # 1. Aggregate digest of the whole submitted surface (editablePaths) per tree.
  for pair in "OLD:${OLDWT}" "NEW:${NEWWT}"; do
    rev="${pair%%:*}"; wt="${pair#*:}"
    agg=$(cd "$wt" && git ls-files -s -- Sources Vendor Package.swift benchmark.json | shasum -a 256 | cut -d' ' -f1)
    printf 'git-index-tree\t%s\t%s\t-\tSources+Vendor+Package.swift+benchmark.json\n' "$rev" "$agg"
  done

  # 2. Per-file digests of every file that differs between the two revisions.
  for f in $(cd "$OLDWT" && git diff --name-only 30f752df 0f6862d0 -- Sources Vendor Package.swift benchmark.json); do
    for pair in "OLD:30f752df" "NEW:0f6862d0"; do
      rev="${pair%%:*}"; sha="${pair#*:}"
      blob=$(cd "$OLDWT" && git cat-file -p "${sha}:${f}" 2>/dev/null | shasum -a 256 | cut -d' ' -f1)
      sz=$(cd "$OLDWT" && git cat-file -p "${sha}:${f}" 2>/dev/null | wc -c | tr -d ' ')
      [ -z "$blob" ] && blob="<absent>" && sz=0
      printf 'source\t%s\t%s\t%s\t%s\n' "$rev" "$blob" "$sz" "$f"
    done
  done

  # 3. Shared binary working set actually executed.
  for p in \
    "cli:${ROOT}/.build/release/mlxfast-swift" \
    "metallib:${ROOT}/.build-worker/arm64-apple-macosx/release/mlx.metallib" \
    "metallib-fingerprint:${ROOT}/.build-worker/arm64-apple-macosx/release/mlx.metallib.fingerprint" \
    "worker-OLD:${OLDWT}/.build-worker/arm64-apple-macosx/release/mlxfast-runtime-worker" \
    "worker-NEW:${NEWWT}/.build-worker/arm64-apple-macosx/release/mlxfast-runtime-worker" \
    "metallib-OLD:${OLDWT}/.build-worker/arm64-apple-macosx/release/mlx.metallib" \
    "metallib-NEW:${NEWWT}/.build-worker/arm64-apple-macosx/release/mlx.metallib" \
    "golden:${ROOT}/correctness_prompts/public_longcopy_gate_english_512_256.json" \
    "weights-index:${ROOT}/weights/model.safetensors.index.json" \
    "weights-config:${ROOT}/weights/config.json" \
  ; do
    lbl="${p%%:*}"; path="${p#*:}"
    if [ -f "$path" ]; then
      h=$(shasum -a 256 "$path" | cut -d' ' -f1)
      s=$(stat -f %z "$path")
      printf 'binary\t%s\t%s\t%s\t%s\n' "$lbl" "$h" "$s" "${path#${ROOT}/}"
    else
      printf 'binary\t%s\t<absent>\t0\t%s\n' "$lbl" "${path#${ROOT}/}"
    fi
  done

  # 4. Weight shards: one shared path for both arms; size+mtime is sufficient
  #    identity because neither run can write there.
  for f in "${ROOT}"/weights/*.safetensors; do
    s=$(stat -f %z "$f"); m=$(stat -f %m "$f")
    printf 'weights\tshared-path\tmtime-%s\t%s\t%s\n' "$m" "$s" "${f#${ROOT}/}"
  done
} > "$OUT"

wc -l "$OUT"
