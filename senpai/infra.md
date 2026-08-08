# Research infrastructure runbook

This is the operator runbook for research Macs. Research policy lives in
`program.md`; the organizer contract lives in `AGENTS.md`.

Never put credentials, passwords, or host secrets in the repository, logs, or
result archives. An authorized campaign role may run `mlxfast submit` from a
provisioned AWS host, but must never print or commit its submission credentials.

## Host contract

Measured experiments require an Apple Silicon Mac with the Xcode Metal toolchain.
Linux, CUDA, simulators, and projected performance are not evidence.

The 21.6 GB model stays in unified memory. Roughly 36 GiB is the practical
minimum; 64 GiB or more is preferred. Hosts below 64 GiB use the low-memory
profile. Record the chip, memory, OS, Metal architecture, and profile.

Only one model process may run on a host. Do not overlap benchmarks, correctness,
quality evaluation, or direct model commands. `swift test` may run independently.

## Comparing M4 and M5

M4 measurements can choose what to investigate, but cannot predict an M5 gain.
Kernel selection, occupancy, memory pressure, and the low-memory profile can
change the result. The official M5 Max run decides promotion.

Record the Metal architecture and whether the effective kernel is NAX before
interpreting prefill. M4 Pro hosts report `applegpu_g16s` / generation 16 and
do not select the `_nax` prefill kernels used by the ranked M5. A matched M4
prefill result for a fallback kernel is not evidence about its M5 `_nax` twin.
Threadgroup geometry also depends on core-count wave boundaries.

Compare a candidate only with the current promoted frontier measured in the
same cohort, on the same host and startup profile, with the same toolchain, fan
policy, and thermal gates. Never use another host or an older cohort as the
baseline. Rerun both arms after any of those inputs changes.

## Prepare a host

Install the required Xcode and Metal toolchain, provision the pinned checkpoint
and disk space, then run `./setup.sh`. Before assignment, confirm the host
profile, free disk, responsive `macmon`, no live model worker, and that an idle
GPU reaches 40C. Pre-provision weights and build caches. Route one active
student to each physical Mac.

## Thermals and fans

The harness waits for 40C before each timed phase. A wait of several minutes is
normal. If another workload prevents cooling, free or reschedule the host.
Never report a hot-start debug run as performance evidence.

Fan control is operator-owned. If an operator uses `tools/fan-control.sh`, verify
the RPM read-back, keep the policy fixed across both arms, and restore automatic
control. Students must not change it. All hosts still require telemetry and 40C.

## Unattended runs

Before model load, retain a short `macmon pipe` receipt with increasing
timestamps and changing, plausible temperatures. Bound the reader and stop if
telemetry is stale, frozen, invalid, or unavailable. The phase gates still
decide whether prefill and decode may start.

Run the benchmark in a supervised process group. Forward termination signals,
bound cleanup, and leave no model worker after exit or cancellation. Set
`MLXFAST_LOCAL_FAN_PROMPT=0`; never configure unattended fan privileges.

Record host and software profiles, thermal state, repo SHA, exit status, and result paths.

## Official ranked queue

Each official job is measured serially on its M5 host, but the service can
validate multiple submissions concurrently and should not be modeled as one
global queue or one permitted in-flight submission. Do not send duplicate
archives to manufacture capacity. Poll status with `mlxfast submissions`, not
by calling `mlxfast submit` again, and honor server retry guidance. If the
frontier advances, reapply and rebaseline later candidates.

For an existing queued or validating receipt, use the repository's read-only
watcher instead of a terminal polling loop:

```bash
python3 senpai/watch-submission.py --submission <submission-id-or-prefix>
```

It makes authenticated GET requests only, honors API retry guidance, emits one
start record and one compact terminal receipt, and never submits or comments.
Normal checks use a three-minute base interval plus a newly sampled 0-20 second
jitter so concurrent submitters do not synchronize their requests.
An advisor or student submitter can launch the watcher with `run_job`, declaring
it `read_only` and keeping the watcher's timeout below that deployment's process
timeout. Then continue useful work: the automatic terminal monitor resumes the
same conversation when the watcher finishes, fails, is interrupted, or times
out. The role that submitted owns any retry and decides whether its PR needs an
update.

For a deployment with Senpai's 1,800-second supervised-process cap, use a
1,680-second watcher deadline and leave one minute for clean outer supervision:

```text
run_job({
  "spec": {
    "argv": ["python3", "senpai/watch-submission.py",
             "--submission", "<submission-id-or-prefix>",
             "--interval-seconds", "180", "--timeout-seconds", "1680"],
    "cwd": ".",
    "timeout_seconds": 1740,
    "workspace_access": "read_only"
  }
})
```

If the deployed process cap is lower, shorten both deadlines while preserving
the cleanup margin. Do not put the watcher's six-hour standalone default inside
a shorter supervised process.

If a capacity rejection produced no receipt, first inspect `mlxfast
submissions` for an explicitly reported blocking receipt or wait the
server-provided retry interval. Do not infer a global one-submission limit.

Use `--model "senpai"` for every official Senpai submission. Retry once with
the exact underlying provider/model only after an explicit API rejection of
`senpai` as the model value; never infer rejection from a timeout or generic
failure. Record the explicit rejection and fallback fact in the public note,
but do not otherwise copy the underlying provider/model into notes or campaign
metadata.

## AWS Mac campaigns

Prefer `mac-m4max.metal` with 128 GiB. Treat `mac-m4pro.metal` with 48 GiB as a
separate low-memory cohort. Do not use the 24 GiB `mac-m4.metal`. These M4
results are transfer evidence, not promotion evidence.

Each instance consumes a Dedicated Host with a 24-hour minimum. Check quota and
live capacity before committing; allocation starts billing. Tag every resource
and record its earliest release time.

### Prepare once

Separate preparation from timing. Install the toolchain, verify the checkpoint,
run setup and transform, warm the workspace, then write a receipt bound to
those inputs. A timing cohort must not run Homebrew, download weights, perform
full setup, or transform unchanged weights.

Keep one preparation-keyed rolling workspace per host. Share verified,
content-addressed model artifacts. Do not reuse builds across preparation keys;
transform changes require a separate weights tree.

### Run bounded cohorts

Each cohort measures the promoted frontier, then a small candidate set on the
same host. Every retry gets a new result ID and baseline measurement. Reuse the
prepared host and caches, not timing results.

Use a detached macOS service independent of SSH. It verifies the receipt,
selects exact inputs, records host state, runs one cohort, and does not restart.

### Retain results and tear down

On every exit, retain the cohort specification, host record, SHAs, status,
logs, scores, integrity files, hashes, and thermal receipts. Upload the archive
and checksum to private storage through an instance role. Exclude credentials,
model artifacts, and caches. Complete work only after controller validation;
delivery must not depend on SSH.

Maintain a cleanup manifest for every allocated resource and release time.
Verify teardown authority before starting. After validation, terminate
instances, release hosts when allowed, and remove the rest. Terminating an
instance does not stop Dedicated Host billing.
