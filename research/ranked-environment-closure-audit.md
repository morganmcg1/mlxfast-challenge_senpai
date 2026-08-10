# Ranked feature-selector environment closure audit

**Status: `RANKED_ENVIRONMENT_CLOSURE_INDETERMINATE`**

**Decision: NO-GO.** Repository evidence proves that the final runtime-worker boundary treats ranked feature selectors consistently, but it does not prove which selector values reach that boundary on the deployed M5. A defect is not established because the unavailable host launcher may construct a clean environment. Closure is therefore indeterminate, not pass and not defect.

## Scope and method

This is a static, research-only audit at controller-recorded base `ac0e7cf6f283c8ac655af955d7ccf57c5141185e`. The pinned baseline is `15852ee52858def42ddd4f32bca7e59d275e020e`. No local `main` or `origin/main` ref exists in this assignment checkout, so the recorded base is the authoritative current-main snapshot for this result.

I searched every submitted Swift/C++/Metal source under `benchmark.json`'s editable surface for concrete `DARKBLOOM_` and scored-backend `MLX_` reads, then traced initialization, trusted CLI, runtime-worker construction, and ranked workflow launch sites. The complete 148-row census is in `ranked-environment-closure-audit.json`; every row records selector, source line, parser/default profile, ranked reach, ownership, and snapshot provenance. It includes operational `MLX_*` values whose `setenv(..., overwrite: 0)` behavior lets inherited parent values win.

Parser semantics prevent treating “unset” as “disabled”: common Swift `raw != "0"` and false-list parsers default on; exact-`1` and integer controls generally default off/zero; truth-list parsers accept only `1,true,yes,on`; `MLX_ENABLE_TF32` uses `atoi` (absent 1, zero false, nonzero true, garbage zero). Selector-specific invalid behavior and fallback are explicit in JSON.

The M5 has 128 GiB, so absent `DARKBLOOM_STARTUP_MEMORY_PROFILE` resolves from `auto` to `full` (`RuntimeStartupMemoryPolicy.swift:35-36`). Clean full startup sets `MLX_BFS_MAX_WIDTH=50` and, when post-wire command-buffer policy is on, `MLX_MAX_MB_PER_BUFFER=200` and `MLX_MAX_OPS_PER_BUFFER=200`, all without overwrite (`LagunaRuntimeWeights.swift:358-395`). An inherited value can therefore change ranked dispatch.

## Selector ownership and forwarding

The decisive in-repository boundary is `Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:1993-2024`. It builds a child environment by copying every parent key with a `DARKBLOOM_` or `MLX_` prefix (also selected Metal/DYLD keys), then forces only `MLXFAST_USE_RUNTIME_WORKER=0`. Runtime-worker spawns at lines 1559-1588 and 1680-1708 use this builder. The public/official CLI requires the sandboxed worker but adds no feature-selector scrub (`Sources/MLXFastCLI/main.swift:1239-1319`).

Thus the worker policy is internally consistent but is **preservation**, not clean-environment closure. If a selector reaches the trusted CLI parent, it reaches the scored child.

## Ranked launch truth table

| Phase | Repository-visible launch chain | Final worker behavior | Missing proof | Closure |
|---|---|---|---|---|
| Public correctness | workflow → `/opt/bench/bench-exec.sh` → trusted CLI → worker | copies all parent `DARKBLOOM_*`/`MLX_*` | effective external launcher/sudo environment | not proven |
| Hidden gates | workflow `sudo bench-exec` → `/usr/bin/env` assignments → trusted CLI → worker | same copy policy | `/usr/bin/env` is not `env -i`; external scrub is unavailable | not proven |
| Baseline timed | `/opt/bench-runner/measure-job.sh` → pinned tree → worker | pinned worker has the same broad-prefix copy policy | effective `measure-job` environment | not proven |
| Candidate timed | `/opt/bench-runner/measure-job.sh` → current tree → worker | same copy policy | effective `measure-job` environment | not proven |

The workflow states an intended `sudo env_reset` and clean `env -i` box bridge (`.github/workflows/benchmark.yml:53-72,268-275`). Hidden-gate launches at lines 1500-1532 and timed launches at lines 1776-1812 ultimately depend on external `/opt/bench/bench-exec.sh`, `/opt/bench-runner/measure-job.sh`, and host sudo policy. Those protected artifacts are not present. The post-job protected-surface check at lines 1981-1995 authenticates files, but its repository form does not attest the effective environment of the four scored process classes.

## Cross-process consistency

Candidate public correctness, hidden gates, and timed work all converge on the same current trusted-worker filter. Baseline timed work uses the pinned tree; inspection shows the same broad-prefix preservation policy. That proves **policy-shape parity downstream**.

It does not prove parent-environment parity. Public correctness and hidden gates have distinct workflow commands, while baseline and candidate timing are delegated to the unavailable measurement wrapper. No repository artifact records selector absence, an allowlisted selector map, or equal selector-environment hashes for all four processes. The existing phase-equivalence test assumes identical allowlisted host values; it does not challenge the broad feature-selector prefixes.

## Provenance and novelty

Relevant history was inspected rather than inferring intent from comments:

- `01dacdb` introduced runtime-worker grading-environment sanitation.
- `67adea2` blocked split gate/timing phase variables.
- `461bd2b` converted the worker filter to a strict allowlist, whose broad `DARKBLOOM_`/`MLX_` prefix entries still preserve feature selectors.
- `451f12d` aligned low-memory compiled-decode behavior with the ranked path.
- `0a8b7d7` audited M5 selector and generated-kernel path identity.

The pinned-to-current diff replaces substantial older selector families with the current `DARKBLOOM_*` surface; current defaults must therefore be read from the recorded base, not assumed from the pinned baseline. Repository-wide novelty search found no prior deployed environment-closure attestation. `docs/private-benchmark-security.md:84-89` states clean-environment intent but supplies no effective host environment or phase hash. The earlier path-identity audit proves which implementation a chosen selector state reaches, not that ranked launchers choose the same state.

`DARKBLOOM_GATHER_XMAJOR` is excluded because no environment read exists and the implementation hard-returns false; `MLX_METAL_NO_NAX` is a compile definition, not an environment read. The eight real dynamic `DARKBLOOM_INJECT_*` reads default, in census order, to `0,1,0,0,0,1,160,1`; the nearby “all default zero” comment is stale. The semantic source also overrides stale comments for `NVFP4_QMV_SIGN_CARRY`, `NVFP4_QMV_SEED_ELIDE`, `NVFP4_SCALE_DEFER`, and `PREFILL_SORTED_MOE_TAIL`. `COMPILED_DECODE`, `COMPILED_TIERED_ATTENTION`, `FAST_BATCH_ROTATING_KV`, and `MLX_COMPILED_DECODE` are ranked-unreachable; `FUSED_NORM_AFFINE_QKV` and `TAIL_NVFP4_SCALE_FOLD` are dormant/fallback rows.

## In-memory positive controls

A read-only validator expanded the compact JSON rows and checked declaration count, uniqueness, parser profiles, launch phases, and dynamic-key closure. Four mutations were applied only to copied Python objects:

1. Mutate a copied `!= "0"` comparator to `== "1"` → parser/profile mismatch detected.
2. Inject a copied `DARKBLOOM_*` override into the modeled launch map → clean-parent closure violation detected.
3. Delete one selector row → declared-count/name closure mismatch detected.
4. Alter one dynamically constructed selector key → resolved-key census mismatch detected.

All four controls were detected. No process environment was changed.

## Single unavailable evidence item

The one item required to resolve this result is:

> **A deployed ranked-launch environment attestation covering the exact effective environment construction and selector-environment hash for public correctness, hidden gates, baseline timed, and candidate timed processes.**

It must bind the effective behavior of host sudo policy, `/opt/bench/bench-exec.sh`, and `/opt/bench-runner/measure-job.sh`, and show either selector absence or an intentional identical selector map/hash at the trusted-CLI parent for all four process classes. This is one host attestation, not a request for multiple code artifacts.

Until that attestation exists, repository statements about `env_reset`/`env -i` cannot establish deployed closure, so promotion on environment-closure grounds is NO-GO.

## Negative fence and reproducibility

No production, vendor, workflow, harness, benchmark, or test file changed. No build, inference, timing, GPU work, environment mutation, official receipt access, or official submission occurred. W&B: N/A. Validation is limited to JSON parsing, source/history inspection, byte/count checks, and the four in-memory controls.

Reproduce the static artifact checks from the final result commit:

```bash
python3 -m json.tool research/ranked-environment-closure-audit.json >/dev/null
python3 -c 'import json;d=json.load(open("research/ranked-environment-closure-audit.json"));r=d["rows"];assert len(r)==d["selector_count"]==len({x[0] for x in r})'
wc -c research/ranked-environment-closure-audit.md research/ranked-environment-closure-audit.json
git diff --check
```

The artifacts embed the recorded base and pinned-baseline SHAs; guarded typed submission binds this tree to the final result commit SHA. Both artifacts remain below their assignment caps (JSON ≤16 KiB; Markdown ≤10 KiB).
