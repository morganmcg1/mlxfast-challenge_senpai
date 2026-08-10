#!/bin/bash
# Apply Phase B arm T0: DARKBLOOM_ROUTER_WEIGHT_PREFETCH default 1 -> 0.
# Refuses unless line 701 is exactly the shipped `return 1` fallback.
set -u
cd /Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-frieren/workspace/target || exit 1
F=Sources/MLXFastModel/LagunaRuntimeModel.swift

if ! git diff --quiet -- Sources Vendor; then
  echo "REFUSE: dirty Sources/Vendor"; exit 2
fi

before=$(sed -n '701p' "$F")
if [ "$before" != "        return 1" ]; then
  echo "REFUSE: line 701 is not the expected fallback"; printf 'got: [%s]\n' "$before"; exit 3
fi

# guard context: the enclosing declaration must be the prefetch knob
ctx=$(sed -n '696p' "$F")
case "$ctx" in
  *lagunaRouterWeightPrefetch*) : ;;
  *) echo "REFUSE: line 696 is not the prefetch declaration"; printf 'got: [%s]\n' "$ctx"; exit 4 ;;
esac

/usr/bin/sed -i '' '701s/        return 1/        return 0/' "$F"
after=$(sed -n '701p' "$F")
if [ "$after" != "        return 0" ]; then
  echo "FAIL: edit did not apply"; printf 'got: [%s]\n' "$after"; exit 5
fi

git --no-pager diff --numstat -- Sources
cat > /tmp/r105b-commit-t0.txt <<'MSG'
r105-b Phase B arm T0: flip DARKBLOOM_ROUTER_WEIGHT_PREFETCH default to 0

One token, one line: LagunaRuntimeModel.swift:701 `return 1` -> `return 0`.
This is the candidate half of the paired official-receipt A/B; arm T1 (the
shipped default) was submitted from the identical tree immediately before.

Bit-exact: all 144 Phase A timed slots produced byte-identical greedy tokens
across prefetch 0/1/5. Phase A measured prefetch=1 as +28.00 us/step slower
than prefetch=0 on M4 Pro, CI [+22.23,+33.77], 16/16 repetitions positive, and
attributed the cost to the cross-barrier hoist (A1 = V-PLACEMENT) rather than
to the loads.

Co-authored-by: openhands <openhands@all-hands.dev>
MSG
git add "$F"
git commit -F /tmp/r105b-commit-t0.txt -q || exit 6
git --no-pager log --oneline -1
git status --porcelain
echo "T0_APPLIED"
