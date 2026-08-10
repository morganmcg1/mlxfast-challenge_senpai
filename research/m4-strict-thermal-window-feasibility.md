# M4 strict thermal-window feasibility

Status: **THERMAL-WINDOW GO** — two of three fresh strict gate invocations qualified and both associated 60-second holds stayed `<=40 C`.

This is research-only infrastructure evidence. It authorizes only consideration of a future short M4 probe; it is not scored timing evidence and makes no M5 claim.

## Identity and controls

- Assignment: PR #661, revision `cedar-thorfinn-strict-thermal-window-feasibility-20260810-r1`.
- Required base: `3b5e22b9fd8d1860ff1a33de5b200fe017ac96cf` (verified ancestor; advisor explicitly said continue without rebasing).
- Physical acquisition implementation: `ac7fe56a1fb5f5c2deafff0916267d68e1350678`. A1 used clean head `0a6466fff61f336e5ea86adeaf985e679d81a8bb`; A2/A3 used clean head `ac7fe56...`. The typed terminal result records the final result commit SHA because a commit cannot embed its own SHA.
- Host: Apple M4 Pro, `Mac16,11`, 20 GPU cores, generation 16, 48 GiB (`51539607552` bytes); macOS 26.5.2 (25F84); Xcode 26.6; Swift 6.3.3; `macmon` 0.8.2. Ambient is N/A because the gate schema exposes no ambient sensor.
- Fan mode was `auto` before, during, and after every attempt and at protocol end. No fan-control write was issued.
- The launch receipts found no model, Metal, Swift build/test, correctness, worker, or full benchmark process. A2/A3 process checks were clear and the final process list was empty.

The frozen five-sample classifier SHA-256 was `854bcdea6029851e7cf70187687271045c720bb4950cc9c2efcc33a284eb5544`. Its pre-physical in-memory controls all matched: changing stream ending `39.9 C` -> `PASS`; changing stream ending `40.1 C` -> `HOT_FAIL`; frozen timestamps -> `TELEMETRY_FAIL`.

## Exact method

Every physical gate invocation was exactly:

```bash
MLXFAST_LOCAL_FAN_PROMPT=0 \
MLXFAST_LOCAL_COOL_GATE_STRICT_TELEMETRY=1 \
./benchmark.sh --local-cool-gate-only
```

Each fresh invocation followed 600 read-only `macmon` samples at 1000 ms intervals and had a 900-second outer bound. A harness pass required exit 0 plus strict-persistent and gate-passed log markers; audit telemetry could not override it. Each counted pass was followed immediately by 60 read-only 1 Hz samples. The threshold, wait, strict mode, and fan policy were unchanged.

The supervisor itself ran only through `run_job`:

- `5cabf39a-c52e-42c3-bed0-edfe9127e20c`: `python3 research/run_m4_strict_thermal_window_feasibility.py` (A1).
- `5070481c-42d8-494e-bded-f4265a92c2f5`: `python3 research/run_m4_strict_thermal_window_feasibility.py --resume-after-a1-monitor-fix` (A2/A3).

No setup, build, model/weight load, inference, correctness, `--local-iterate`, `--local-submit`, worker, official submission, or GPU workload was run.

## Results

| Attempt | 600-s idle wall; CPU/GPU range; GPU final (C) | Gate wall; exit; audit GPU range; authoritative final (C) | 60-s hold GPU range (C) | Outcome |
|---|---|---|---|---|
| A1 | 607.675 s; 23.684–42.943 / 38.291–39.139; 38.317 | 7.687 s; 0; 38.389–38.432; 38.4 | not collected | INCONCLUSIVE, not counted |
| A2 | 607.512 s; 22.175–40.382 / 38.419–39.062; 38.420 | 7.749 s; 0; 38.493–38.601; 38.5 | 38.403–38.584, all `<=40` | PASS |
| A3 | 607.687 s; 22.084–40.583 / 38.347–39.172; 38.842 | 7.652 s; 0; 38.961–39.049; 39.0 | 38.901–39.028, all `<=40` | PASS |

A1's harness itself passed at `38.4 C`, but the first supervisor incorrectly treated its own three `benchmark.sh --local-cool-gate-only` descendants as competing processes. It stopped without a hold, so A1 remains operationally inconclusive and contributes no pass. The monitor was narrowed to exclude only the owned process tree; the classifier, exact gate command, threshold, fan policy, and harness were unchanged. A2 and A3 then independently satisfied every qualification.

**Decision: GO.** Exactly three allowed gate invocations were consumed; two qualified. There were no hot failures, hold failures, invalid telemetry streams, non-auto fan states, model launches, or tree/base drift. The supervised jobs used 1972.938 seconds total (32m52.938s), below the 100-minute budget. Peak model memory and latency are N/A because no model ran. W&B: N/A by assignment.

## Evidence and limitations

- `m4-strict-thermal-window-feasibility.csv` contains all three attempt summaries and SHA-256 receipts for every complete original idle, gate, audit, and hold stream.
- `m4-strict-thermal-window-feasibility-raw.log.gz` is 13,907 bytes, SHA-256 `e4f9dde7b958f5195a580f66907ca6ea99c59d05993f65158d42a375b4c2c579`. Its first gzip member retains all A1 idle/gate samples; its second retains every fifth A2/A3 idle sample plus all gate and hold samples and complete authoritative gate markers. Original full-stream hashes remain in the CSV.
- Durable job logs are under the role state `training/<job-id>.log`; they record host identity, clean-tree proof, controls, attempts, final fan/process state, and `model_or_benchmark_run: false`.
- The temporary acquisition supervisor was deleted; only the three size-bounded deliverables remain.

This demonstrates a strict thermal window on one M4 Pro session, not repeatability across days, ambient conditions, M4 hosts, or M5 hardware. Suggested follow-up, not run here: if authorized separately, repeat gate-only feasibility in another ambient/session before any short model timing probe.
