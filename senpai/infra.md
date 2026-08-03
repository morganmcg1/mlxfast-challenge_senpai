# Research infrastructure runbook

This is the operator runbook for Macs used by the autoresearch program,
including AWS EC2 Mac campaigns. Research policy lives in `program.md`; the
organizer's operational contract remains in `AGENTS.md`.

Never place cloud credentials, sudo passwords, or other host secrets in the
repository, user data, logs, or result archives. Never run `mlxfast submit`
from private AWS experiment hosts.

## Host contract

Measured experiments require macOS on Apple Silicon with the Xcode Metal
toolchain. Linux, CUDA, a simulator, and projected performance are not valid
substitutes. Work without a qualifying Mac must be reported as unmeasured.

The model is about 21.6 GB and fully RAM-resident. Roughly 36 GiB of unified
memory is the practical minimum; 64 GiB or more is preferred. Hosts below
64 GiB use the repository's low-memory startup profile, which changes memory
management rather than the ranked code path. Record the active profile and do
not compare absolute timing across different chips, memory profiles, or host
policies. The official authority is the M5 Max with 128 GB.

Only one model-holding process may run on a physical host. `swift test` does
not load the real model and may run independently, but `benchmark.sh`, direct
correctness commands, quality evaluation, and other real-model commands must
not overlap.

## Prepare a host once

Before assigning experiments:

1. Install and select the required Xcode/Metal toolchain.
2. Provision the exact pinned checkpoint and enough free disk for setup and
   transformed weights.
3. Run `./setup.sh` once, then rerun it only when the toolchain, checkpoint, or
   harness state changes.
4. Confirm the chip, unified memory, OS build, Metal architecture, free disk,
   startup memory profile, and absence of another model worker.
5. Confirm that the pinned `macmon` reader reports plausible, responsive GPU
   telemetry and that the host can reach the 40C gate while quiescent.

Pre-provision the checkpoint, toolchain, and build cache before assigning a
student. Route at most one active student to each physical Mac. A controller
timeout must cover multiple independently bounded thermal stages plus
incremental build, model load, correctness, and timing; do not size it around a
single 900-second allowance. Killing a normal cool-down yields no research
evidence.

## Thermal and fan policy

The local harness waits for the GPU to cool to 40C before each timed phase. A
wait of several minutes is normal and must not be killed. If the gate aborts
because another workload keeps the GPU hot, free or reschedule the host. Never
disable the thermal gate or present a hot-start debug run as performance
evidence.

Fan policy is operator-owned host state, not an experiment variable. Students
must not change fan controls or automate privilege escalation. Record one
policy for an unchanged-baseline/candidate comparison and rerun the baseline
after any policy change.

Manual fan control is optional and capability-verified. Installing an SMC
utility does not prove that a VM or bare-metal guest permits fan writes. On an
exact instance family and macOS build, an operator must verify that
`tools/fan-control.sh boost` changes observed RPM, its read-back passes, and
`tools/fan-control.sh normal` restores automatic control. If any check fails,
leave the fans alone and cool by idling or rescheduling.

The helper's normal bounded policy is:

- default verified boost: 70%;
- optional operator-only fallback after a failed 70% trial:
  `MLXFAST_FAN_BOOST_PERCENT=80 tools/fan-control.sh boost`;
- every other percentage is refused; and
- automatic control must be restored immediately after an 80% campaign.

Never pipe or store a sudo password, grant students broad SMC-write access,
write undocumented SMC keys, exceed 80%, or ignore a failed read-back. A
manual boost is external state and the benchmark does not undo it. The
operator must use `./benchmark.sh --fan-speed-normal` and verify `auto` after a
campaign where it applied a boost. A host reporting unsupported `none` has
nothing to restore; telemetry and the 40C gate still apply.

## Unattended automation

Before loading the model for each exact experiment snapshot, audited
automation must collect and retain a persistent five-sample `macmon pipe`
stream. Require strictly increasing timestamps, plausible CPU/GPU values, and
at least two distinct GPU temperatures. Five fresh one-shot readers are not a
responsiveness test.

Bind the telemetry receipt to the exact rank or submission, commit, attempt,
fan policy, and process launch. Do not reuse it. The receipt supplements rather
than replaces the fresh gates immediately before prefill and decode. Bound
every telemetry reader by a wall-clock deadline and reap its process group on
timeout or interruption; a dead sensor command must fail the arm rather than
hang the campaign. Stop the cohort if the local gate exhausts its transient
invalid-sample retries.

Long-running wrappers must launch the benchmark in an isolated process group,
forward HUP, INT, QUIT, and TERM to the group, and use bounded TERM-to-KILL
escalation. Test cancellation and normal-exit orphan handling with model-free
fixtures. A stopped terminal or agent must not leave a model-holding worker.

Unattended runs cannot accept the benchmark's optional fan prompt. Set
`MLXFAST_LOCAL_FAN_PROMPT=0`; the thermal gate remains active. Do not arrange an
unattended sudo path. Direct fan-helper calls remain attended operator actions.

Record the host identifier, chip, unified memory, OS build, Metal architecture,
startup profile, initial temperature, fan capability and action, cool-down
duration, accepted telemetry, repo SHA, and result paths with every timed arm.

## Official ranked queue

The official M5 runner is one serial queue. Do not dispatch duplicate ranked
submissions in an attempt to create parallel capacity. Queue times have
sometimes reached 6–12 hours; students should continue independent local work
against a recorded frontier rather than wait idle. If an accepted submission
advances the frontier, reapply and rebaseline any later candidate before using
its old timing as promotion evidence.

## AWS EC2 Mac

The remaining sections cover capacity, provisioning, sharding, artifact
retrieval, and teardown for private AWS campaigns.

This is the target design for future campaigns. The 2026-08-03 wrapper
predates it: guards reused Xcode, the checkpoint, and unchanged transformed
weights, but retries reran Brew/setup checks, used new workspace IDs that lost
the `.build-worker` cache, wrote result tarballs only on the instances, and
relied on controller SSH/SCP for retrieval. It did not create a preparation
receipt, use a thin cohort-only launcher, upload result archives to S3, or trap
early bootstrap exits.

## Capacity

Prefer `mac-m4max.metal` (128 GiB). Use `mac-m4pro.metal` (48 GiB and the
low-memory startup profile) only as a separate fallback cohort. Do not use
`mac-m4.metal`: 24 GiB is below the model's practical minimum. AWS currently
offers no EC2 M5 Mac type.

The 2026-08-03 top-15 campaign used five `mac-m4pro.metal` hosts. Treat every
result as part of that 48-GiB low-memory M4 Pro cohort; never compare its
absolute times with M4 Max.

Each Mac instance consumes one On-Demand Dedicated Host with a 24-hour minimum
allocation. Quotas are regional and supported AZs do not guarantee live
capacity; a successful `allocate-hosts` call is the capacity test and starts
billing. Use a unique client token, campaign tags, and allocate one host at a
time:

```bash
aws ec2 describe-instance-type-offerings \
  --region "$REGION" --location-type availability-zone \
  --filters Name=instance-type,Values=mac-m4max.metal,mac-m4pro.metal

aws service-quotas list-service-quotas --service-code ec2 --region "$REGION" \
  --query "Quotas[?contains(QuotaName, 'Running Dedicated mac-m4')].[QuotaName,Value,QuotaCode]"

aws ec2 allocate-hosts --region "$REGION" --availability-zone "$AZ" \
  --instance-type mac-m4max.metal --quantity 1 --auto-placement on \
  --client-token "$CAMPAIGN-$AZ-$N"
```

See AWS's [EC2 Mac guide](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-mac-instances.html),
[instance specifications](https://aws.amazon.com/ec2/instance-types/mac/), and
[Dedicated Host quotas](https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-quotas.html).

## Prepare immutable host state once

Separate fleet preparation from cohort execution. A cohort launcher must never
install or update Homebrew, extract Xcode, download the checkpoint, run a full
`./setup.sh`, or transform unchanged weights. Those operations cost minutes,
and heat the host before timing. In the 2026-08-03 campaign, guards avoided
repeated Xcode extraction and unchanged-weight transform, but retries still
reran package/setup checks and their new workspace IDs discarded the reusable
`.build-worker` cache.

Prefer a versioned ARM macOS image with the selected/licensed Xcode and required
Homebrew packages already installed. Otherwise run one idempotent preparation
wrapper per physical host: install the hash-pinned Xcode archive, require
`xcrun --find metal`, install `cmake`, `jq`, `uv`, and pinned `macmon`, transfer
the full Git bundle, run `./setup.sh`, verify/transform the checkpoint, prepare
the rolling workspace, and only then write a hash-bound preparation receipt.
Set `HOMEBREW_NO_AUTO_UPDATE=1` during preparation and never invoke Brew from a
timing cohort.

Key the receipt by instance family, macOS build, Xcode/Swift version, harness
commit, reference-manifest hash, transform-source hash, and runner contract.
The receipt covers immutable toolchain and model inputs. The rolling workspace
and build caches are intentionally mutable: verify their owner and preparation
key, then rely on source freshness checks to rebuild affected products. Use a
private bucket through an instance role, preferably over a VPC endpoint; never
use public-read objects or embedded credentials, and SHA-256 verify every
bootstrap object.

Prefer a private image or encrypted EBS snapshot for the 21.6 GB checkpoint and
transformed weights; live peer-to-peer checkpoint relay was slower than moving
the shard to an already prepared host.

Each physical Mac keeps one fixed, preparation-keyed rolling workspace with
its `.build`, `.build-worker`, `.build-quality`, package, and Metal caches.
Reference and transformed weights are shared, content-addressed host artifacts,
not copied into each cohort workspace. Never reuse build products across a
different preparation key. A candidate that changes transform sources gets a
separately keyed weights tree and may not overwrite the shared cohort weights.

Before putting a host in the ready queue, confirm chip/memory, Metal
architecture, free disk, responsive five-sample `macmon pipe`, absence of a
model worker, and fan capability. `tools/fan-control.sh status` may honestly be
`none` on EC2; the M4 Pro hosts did not expose guest SMC control. That relaxes
only fan-status equality: responsive telemetry and every 40C gate remain
mandatory. A cohort verifies the receipt and these readiness facts; it does
not repair or update the host.

## Shard and retain results

The schedulable unit is a bounded cohort: one fresh same-host rank-111
comparator followed by one to three candidates. Use a controller-side queue,
not a permanent host-to-shard assignment. A prepared host that finishes early
may take another unclaimed cohort, and a failed or thermally stalled host's
work may move immediately to another prepared host. Every cohort and retry gets
a unique results ID and its own rank-111 measurement, but reuses the physical
host's rolling workspace and verified shared artifacts. Never normalize a
candidate against another host or another retry cohort. The initial five-way
split `112 113 114`, `115 116 117`, `118 119 120`, `121 122 123`, and
`124 125 126` is an example, not a required mapping.

Do not rely on `/usr/bin/nohup` on a headless EC2 Mac; it can refuse to detach
from the SSH console. Run a wrapper through a one-shot system LaunchDaemon with
`RunAtLoad=true`, `KeepAlive=false`, `UserName=ec2-user`, explicit
`ProgramArguments`, `WorkingDirectory`, `PATH`, standard-output/error paths,
`ProcessType=Interactive`, `AbandonProcessGroup=false`, a bounded 60-second
`ExitTimeOut`, and a unique label. Register it with
`sudo launchctl bootstrap system <plist>`; do not use the restart-prone
`launchctl submit` path. The LaunchDaemon runs only a thin cohort wrapper: it
verifies the preparation receipt, exports the fixed reference/weights and
rolling workspace, creates a unique results root, records the fan policy, and
calls `run-study.sh perf-batch ...`. It survives SSH closure and
`KeepAlive=false` prevents failed cohorts from restarting.

Install the exact snapshot before launch cooling. If the coarse stream reaches
40C but the immediately following fresh five-sample receipt rebounds above it,
retry only that fresh, plausible healthy-hot outcome without loading the model,
for at most 900 seconds. Invalid, stale, frozen, unreadable, or
supervision-failed telemetry stops the cohort. This handoff retry does not
replace or relax the strict prefill and decode gates.

Required next-campaign behavior—not implemented by the 2026-08-03 wrapper—is
to package the host record, cohort spec, exit code, launch logs, status,
score/integrity files, hashes, and raw thermal receipts from an EXIT trap,
including nonzero and early-bootstrap exits. Upload the small archive plus
SHA-256 sidecar to a unique private-S3 key through the instance role; never
include weights, checkpoints, credentials, or build caches. The controller
marks a cohort complete only after downloading, hashing, extracting, and
validating it. Result delivery must not depend on SSH: a stale single-IP
allowlist temporarily cut controller access during the 2026-08-03 campaign
while launchd jobs kept running.

Write a cleanup manifest as resources are allocated: hosts, instances,
volumes, addresses, endpoint, bucket, IAM attachments, key pair, network, and
each `host_release_not_before`. Verify cleanup credentials or delegate teardown
to a persistent least-privilege role before starting; an expiring SSO session
must not own delayed host release. After artifacts validate, terminate
instances. At the recorded time release Dedicated Hosts, then remove all
remaining campaign resources. Instance termination alone does not stop
Dedicated Host billing.
