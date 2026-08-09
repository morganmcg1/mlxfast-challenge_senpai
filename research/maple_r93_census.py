#!/usr/bin/env python3
"""R93-C stall-structure census driver (research-only, not submitted).

Runs a list of `NEZUKO_R93_PROBE` arms through `research/decode_probe.py` under
`DARKBLOOM_GPU_PROFILE_SPLIT=1`, parses the per-kernel table, and appends one
JSON record per arm to `<outdir>/census.jsonl`.

  python3 research/maple_r93_census.py OUTDIR ARMSPEC_FILE [STEPS]

`ARMSPEC_FILE` holds one arm per line: either `off` or `<target>:<kind>:<n>`.
Repeating the file's arms is the caller's job (write them out however many
times, in whatever interleaving, is wanted).

Every arm's teacher-forced divergence count is recorded; a non-zero value means
the probe was not bit-exact and the arm must be discarded.
"""
import json
import os
import re
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Kernel families the census is about; matched as substrings of the shortened
# name that `decode_probe.py` prints.
TRACKED = {
    "qkv": "laguna_decode_nvfp4_qkv_",
    "oproj": "laguna_oproj_act_",
    "routed": "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2",
}

ROW = re.compile(
    r"^\s*([0-9.]+)\s+([0-9.]+)%\s+([0-9.]+)\s+([0-9.]+)\s\s+(.*)$")
STEP = re.compile(
    r"per steady step: wall=([0-9.]+) ms gpu_busy_sum=([0-9.]+) ms "
    r"gpu_busy_union=([0-9.]+) ms gap=([0-9.]+) ms")
DIV = re.compile(r"teacher-forced greedy tokens: (\d+) divergence")
MEAN = re.compile(r"decode steps=\d+ mean=([0-9.]+) ms median=([0-9.]+) ms")


def parse(text: str) -> dict:
    out = {"rows": {}, "raw_rows": []}
    m = STEP.search(text)
    if m:
        out["wall_ms"] = float(m.group(1))
        out["busy_sum_ms"] = float(m.group(2))
        out["busy_union_ms"] = float(m.group(3))
        out["gap_ms"] = float(m.group(4))
    m = DIV.search(text)
    if m:
        out["divergences"] = int(m.group(1))
    m = MEAN.search(text)
    if m:
        out["mean_ms"] = float(m.group(1))
        out["median_ms"] = float(m.group(2))
    for line in text.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        us, share, npc, uscall, kernel = m.groups()
        rec = {
            "us_per_step": float(us), "share_pct": float(share),
            "n_per_step": float(npc), "us_per_call": float(uscall),
            "kernel": kernel.strip(),
        }
        out["raw_rows"].append(rec)
        for tag, needle in TRACKED.items():
            if needle in kernel:
                cur = out["rows"].setdefault(
                    tag, {"us_per_step": 0.0, "n_per_step": 0.0, "names": []})
                cur["us_per_step"] += rec["us_per_step"]
                cur["n_per_step"] += rec["n_per_step"]
                cur["names"].append(rec["kernel"])
    return out


def main() -> int:
    outdir = sys.argv[1]
    armfile = sys.argv[2]
    steps = int(sys.argv[3]) if len(sys.argv) > 3 else 80
    os.makedirs(outdir, exist_ok=True)
    arms = [l.strip() for l in open(armfile) if l.strip()
            and not l.startswith("#")]
    sink = os.path.join(outdir, "census.jsonl")
    for i, arm in enumerate(arms):
        env = dict(os.environ)
        env["DARKBLOOM_GPU_PROFILE"] = "1"
        env["DARKBLOOM_GPU_PROFILE_SPLIT"] = "1"
        env.pop("NEZUKO_R93_PROBE", None)
        if arm != "off":
            env["NEZUKO_R93_PROBE"] = arm
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, os.path.join(REPO, "research/decode_probe.py"),
             "--steps", str(steps), "--profile", "--profile-top", "250",
             "--stderr", os.path.join(outdir, "worker.err")],
            cwd=REPO, env=env, capture_output=True, text=True)
        rec = parse(proc.stdout)
        rec.update({
            "arm": arm, "index": i, "steps": steps,
            "returncode": proc.returncode, "seconds": round(time.time() - t0, 1),
            "stderr_tail": proc.stderr[-2000:] if proc.returncode else "",
        })
        with open(sink, "a") as f:
            f.write(json.dumps(rec) + "\n")
        got = {k: round(v["us_per_step"], 1) for k, v in rec["rows"].items()}
        print(f"[{i+1}/{len(arms)}] {arm:>16} rc={proc.returncode} "
              f"div={rec.get('divergences')} busy={rec.get('busy_sum_ms')} "
              f"{got}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
