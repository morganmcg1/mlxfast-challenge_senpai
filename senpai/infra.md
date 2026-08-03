# AWS EC2 Mac campaign runbook

This is the operator runbook for private, local-only MLXFast experiments on
EC2 Mac. Never run `mlxfast submit` from these hosts, and never place AWS
credentials in the repository, user data, logs, or result archives.

## Capacity

Prefer `mac-m4max.metal` (128 GiB). Use `mac-m4pro.metal` (48 GiB and the
low-memory startup profile) only as a separate fallback cohort. Do not use
`mac-m4.metal`: 24 GiB is below the model's practical minimum. AWS currently
offers no EC2 M5 Mac type.

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
AWS's stock AMI has Command Line Tools but not full Xcode or the Metal compiler;
install a compatible full Xcode plus its Metal toolchain. Also install Homebrew
`jq` and `uv`, and the pinned `~/bin/macmon`. A normal clone is insufficient:
fetch every commit named by the top-15 manifest, or transfer a full Git bundle.
Stage the verified transformed `weights/`, a reference directory containing
`config.json`, and `quality-results/baseline-quick-weave-v3-m4-20260730/`.

Run `run-study.sh prepare` once, then confirm the chip/memory, Metal
architecture, responsive five-sample `macmon pipe`, free disk, and absence of
another model worker. Do not repeat this readiness pass for every shard.
`tools/fan-control.sh status` may be `none` on EC2 because AWS does not promise
guest SMC control; record that honestly and set `MLXFAST_TOP15_FAN_POLICY=none`.
The temperature gate remains mandatory. Never falsify `auto` or disable it.

## Shard and retain results

Every physical host must measure its own fresh rank-111 comparator. Keep a
unique workspace and results root per host; never normalize a candidate with a
baseline from another host. Five hosts can cover the cohort as
`112 113 114`, `115 116 117`, `118 119 120`, `121 122 123`, and
`124 125 126`.

Do not rely on `/usr/bin/nohup` on a headless EC2 Mac; it can refuse to detach
from the SSH console. Run a wrapper through a one-shot system LaunchDaemon with
`RunAtLoad=true`, `KeepAlive=false`, `UserName=ec2-user`, explicit
`ProgramArguments`, `WorkingDirectory`, `PATH`, and standard-output/error
paths. Register it with `sudo launchctl bootstrap system <plist>`. The wrapper
exports the unique results/workspace paths and observed fan policy, then calls
`run-study.sh perf-batch ...`. Launchd preserves the process after SSH closes
without restarting a failed experiment.

Capture instance ID, host ID, AMI, chip, memory profile, Metal architecture,
repo SHA, runner/manifest hashes, and the entire per-host result tree. On a
retry use a new workspace/results ID so rank 111 is measured again. Retrieve
artifacts before terminating the instance; release the Dedicated Host only
after AWS's 24-hour minimum and host-scrub state permit it.
