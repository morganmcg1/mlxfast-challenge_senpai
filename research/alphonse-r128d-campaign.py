#!/usr/bin/env python3
"""R128-D: run the instrument-overhead ladder serially, one worker at a time.

Each config re-invokes alphonse-r128d-probe.py in a fresh process so the child
sees exactly the intended DARKBLOOM_* environment and the intended worker
binary. Configs run strictly one after another: only one model-holding process
is ever alive.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "alphonse-r128d-probe.py")

# (name, worker, extra env, runs, steps, rtt)
CONFIGS = [
    ("hook-off", "/tmp/w-hook", {}, 6, 1023, 200),
    ("hook-on", "/tmp/w-hook", {"DARKBLOOM_GPU_PROFILE": "1"}, 6, 1023, 200),
    ("hook-split", "/tmp/w-hook",
     {"DARKBLOOM_GPU_PROFILE": "1", "DARKBLOOM_GPU_PROFILE_SPLIT": "1"},
     2, 200, 50),
]


def main() -> int:
    only = sys.argv[1:]
    for name, worker, extra, runs, steps, rtt in CONFIGS:
        if only and name not in only:
            continue
        env = dict(os.environ)
        env["DECODE_PROBE_WORKER"] = worker
        env.pop("DARKBLOOM_GPU_PROFILE", None)
        env.pop("DARKBLOOM_GPU_PROFILE_SPLIT", None)
        env.update(extra)
        print(f"\n########## CONFIG {name} worker={worker} extra={extra} "
              f"runs={runs} steps={steps}", flush=True)
        rc = subprocess.call(
            [sys.executable, PROBE, "--runs", str(runs), "--steps", str(steps),
             "--rtt", str(rtt),
             "--stderr-prefix", f"/tmp/r128d-{name}.worker",
             "--out", f"/tmp/r128d-{name}.json"],
            env=env, stdout=sys.stdout, stderr=subprocess.STDOUT,
        )
        print(f"########## CONFIG {name} rc={rc}", flush=True)
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
