# M4 strict thermal-window feasibility

Status: **protocol frozen before physical acquisition**.

- Assignment: PR #661, `cedar-thorfinn-strict-thermal-window-feasibility-20260810-r1`
- Required base: `3b5e22b9fd8d1860ff1a33de5b200fe017ac96cf`
- Question: can this M4 Pro produce a reproducible, sustained window under the unchanged strict `<=40 C` local gate with automatic fan control?
- Scope: research-only infrastructure feasibility; no model load, build, setup, correctness, timing, latency, speedup, W&B run, or official submission.

## Frozen protocol

The acquisition implementation is `research/run_m4_strict_thermal_window_feasibility.py` at the pre-acquisition commit. It runs the synthetic controls before reading host telemetry, records host/tree/tool identity, rejects any non-auto fan state or model/Metal/Swift benchmark process, and permits at most three fresh launches of exactly:

```bash
MLXFAST_LOCAL_FAN_PROMPT=0 \
MLXFAST_LOCAL_COOL_GATE_STRICT_TELEMETRY=1 \
./benchmark.sh --local-cool-gate-only
```

Before each launch it collects 600 samples from one persistent `macmon` process at 1000 ms intervals. Each gate is independently launched and bounded at 900 wall seconds. A read-only persistent `macmon` stream and fan/process monitor run alongside the gate only for audit; the harness exit and log remain authoritative. A pass is followed immediately by 60 `macmon` samples at 1000 ms intervals. Attempts are separated by the next fresh 600-sample idle receipt. Total protocol budget is 100 minutes.

The compact retained raw artifact preserves every acquired timestamp and CPU/GPU value plus complete gate logs; the CSV records original stream checksums. Fan mode is read with `tools/fan-control.sh status`; the experiment never invokes fan writes.

## Frozen classifier

A stream is telemetry-valid only when it has the expected sample count, every entry is an object with a parseable strictly increasing UTC timestamp inside its observation window, numeric CPU and GPU temperatures in `(5, 120] C`, and at least two distinct GPU values. For the five-sample classifier:

- valid and final GPU `<=40.0 C` -> `PASS`;
- valid and final GPU `>40.0 C` -> `HOT_FAIL`;
- otherwise -> `TELEMETRY_FAIL`.

The three synthetic five-sample controls exist only in memory and must classify exactly as: changing final `39.9` -> `PASS`; changing final `40.1` -> `HOT_FAIL`; stale timestamps -> `TELEMETRY_FAIL`. Any mismatch ends acquisition.

A real gate is `PASS` only on exit 0 with both the strict persistent confirmation and gate-passed markers. Explicit strict reader/schema/plausibility failures are `TELEMETRY_FAIL`. An unchanged-harness hot/stall/max-wait error, or the 900-second outer bound with continuously valid temperatures above 40 C, is `HOT_FAIL`. Any other exit is operationally inconclusive. Direct audit telemetry never overrides the harness verdict.

## Frozen decision

- `GO`: at least two of three attempts pass and every associated 60-second hold sample remains `<=40 C`.
- `NO-GO`: two consecutive valid hot failures, fewer than two passes after three attempts, or any pass whose hold exceeds 40 C.
- `INCONCLUSIVE`: stale/invalid telemetry, fan not auto, competing process, tree/input drift, unexpected gate exit, or model-process launch.

Stop immediately after the second consecutive hot failure, a hold failure, non-auto/unreadable fan state, process/tree drift, or any model-process launch. Never weaken the threshold, waits, strict mode, or fan policy.

## Results

Pending frozen-protocol acquisition. W&B: N/A.
