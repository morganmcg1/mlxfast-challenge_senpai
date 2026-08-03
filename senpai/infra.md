# AWS EC2 Mac campaign runbook

This is the operator runbook for private, local-only MLXFast experiments on
EC2 Mac. Never run `mlxfast submit` from these hosts, and never place AWS
credentials in the repository, user data, logs, or result archives.

## Capacity

Prefer `mac-m4max.metal` (128 GiB). Use `mac-m4pro.metal` (48 GiB and the
low-memory startup profile) only as a separate fallback cohort. Do not use
`mac-m4.metal`: 24 GiB is below the model's practical minimum. AWS currently
offers no EC2 M5 Mac type.

The 2026-08-03 top-15 campaign uses five `mac-m4pro.metal` hosts. Treat every
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

## Prepare each host once

Use a current ARM macOS AMI and an encrypted 150--200 GiB gp3 root volume.
The stock macOS 26.5.2 ARM AMI is insufficient by itself: install the
hash-pinned full Xcode 26.6 archive, select it with `xcode-select`, accept its
license, run first-launch setup, and require `xcrun --find metal` before
`./setup.sh`. Also install Homebrew `cmake`, `jq`, and `uv`, plus the pinned
`~/bin/macmon`.

A normal clone is insufficient: fetch every commit named by the top-15
manifest, or transfer a full Git bundle. The current private-S3 bootstrap
stages the hash-pinned full repository bundle, quality-baseline tarball,
`macmon`, and Xcode archive; `./setup.sh` then downloads and verifies the pinned
checkpoint and transforms weights independently on each host. Use a private
bucket through a VPC endpoint or instance role, never public-read objects or
embedded AWS credentials, and SHA-256 verify every bootstrap object.

Run `run-study.sh prepare` once, then confirm the chip/memory, Metal
architecture, responsive five-sample `macmon pipe`, free disk, and absence of
another model worker. Do not repeat this readiness pass for every shard.
`tools/fan-control.sh status` may be `none` on EC2 because AWS does not promise
guest SMC control; record that honestly and set `MLXFAST_TOP15_FAN_POLICY=none`.
The current M4 Pro hosts report `none`. This override relaxes only the fan-status
equality check: `macmon` and the temperature gate remain mandatory. Never
falsify `auto` or disable cooling telemetry.

## Shard and retain results

Every physical host must measure its own fresh rank-111 comparator. Keep a
unique workspace and results root per host; never normalize a candidate with a
baseline from another host. Five hosts can cover the cohort as
`112 113 114`, `115 116 117`, `118 119 120`, `121 122 123`, and
`124 125 126`.

Do not rely on `/usr/bin/nohup` on a headless EC2 Mac; it can refuse to detach
from the SSH console. Run a wrapper through a one-shot system LaunchDaemon with
`RunAtLoad=true`, `KeepAlive=false`, `UserName=ec2-user`, explicit
`ProgramArguments`, `WorkingDirectory`, `PATH`, standard-output/error paths,
`ProcessType=Interactive`, `AbandonProcessGroup=false`, a bounded 60-second
`ExitTimeOut`, and a unique label. Register it with
`sudo launchctl bootstrap system <plist>`; do not use the restart-prone
`launchctl submit` path. The LaunchDaemon runs the complete hash-verifying
bootstrap wrapper, which exports unique results/workspace paths and the
observed fan policy before calling `run-study.sh perf-batch ...`. It survives
SSH closure without restarting a failed experiment.

Capture instance ID, host ID, AMI, chip, memory profile, Metal architecture,
repo SHA, runner/manifest hashes, and the entire per-host result tree. On a
retry use a new workspace/results ID so rank 111 is measured again. Retrieve
artifacts before terminating the instance. Termination does not release the
billed Dedicated Host: issue `release-hosts` at the recorded
`host_release_not_before` UTC time once scrubbing permits it. Set root EBS
`DeleteOnTermination=true`, and remove any retained volumes, snapshots,
endpoints, public addresses, and campaign network resources.
