#!/usr/bin/env bash
# PR35 narrow attention scale planes: interleaved per-step decode screen.
#
# Three arms, run in both orders so thermal drift cannot masquerade as effect:
#   off  DARKBLOOM_ATTN_SCALE_NARROW=0        stock 32 B/32 groups
#   qkv  DARKBLOOM_ATTN_SCALE_NARROW_OPROJ=0  narrow q/k/v only
#   on   (defaults)                            narrow q/k/v + o_proj
# Research-only; not part of the submission surface.
set -u
cd "$(dirname "$0")/.."
steps="${STEPS:-256}"

run() {
    local name="$1"
    shift
    echo "=== ARM ${name} ==="
    env DARKBLOOM_STARTUP_MEMORY_PROFILE=full "$@" \
        python3 research/decode_probe.py --steps "${steps}" \
        --stderr "/tmp/pr35_${name}.err" 2>&1 |
        grep -E "decode steps|divergences|diagnostics after decode"
    grep -h "narrow-scales" "/tmp/pr35_${name}.err" | sort -u
}

for round in 1 2; do
    if [ "${round}" = 1 ]; then order="off qkv on"; else order="on qkv off"; fi
    for arm in ${order}; do
        case "${arm}" in
        off) run "off_r${round}" DARKBLOOM_ATTN_SCALE_NARROW=0 ;;
        qkv) run "qkv_r${round}" DARKBLOOM_ATTN_SCALE_NARROW_OPROJ=0 ;;
        on) run "on_r${round}" ;;
        esac
    done
done
