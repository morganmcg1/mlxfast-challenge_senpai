"""R128-P: paired timed-prefill vs decode-seed-forward statistics on H-M4B.

Reads research/artifacts/r128p/cold-warm.tsv plus the mean_step_seconds printed
by the final decode progress line of each iterate log, and reports the paired
delta, spread, and the detection floor actually achieved at the n that ran.
"""

import csv
import pathlib
import re
import statistics as st
import sys

ART = pathlib.Path(__file__).resolve().parent / "artifacts" / "r128p"
PROMPT_TOKENS = 512
DECODE_STEPS = 128
H_M5_PREFILL_MS = 97.95

STEP_RE = re.compile(r"decode 128/128 tokens .*mean_step_seconds=([0-9.]+)")


def mean_step_seconds(log: pathlib.Path) -> float:
    for line in log.read_text().splitlines():
        m = STEP_RE.search(line)
        if m:
            return float(m.group(1))
    raise SystemExit(f"no final decode progress line in {log}")


def main(tsv_name: str, log_prefix: str) -> None:
    rows = list(csv.DictReader((ART / tsv_name).open(), delimiter="\t"))
    prefill_ms, seed_ms, delta_ms = [], [], []
    for row in rows:
        run = row["run"]
        step = mean_step_seconds(ART / f"{log_prefix}-{run}.log")
        a = float(row["cold_s_per_tok"]) * PROMPT_TOKENS * 1000.0
        b = (float(row["decode_s_per_tok"]) - step) * DECODE_STEPS * 1000.0
        prefill_ms.append(a)
        seed_ms.append(b)
        delta_ms.append(a - b)
        print(
            f"run {run}: timed_prefill={a:.3f} ms  decode_seed={b:.3f} ms  "
            f"delta={a - b:+.3f} ms ({(a - b) / b * 100:+.3f} %)"
        )

    n = len(rows)
    for name, xs in (("timed_prefill", prefill_ms), ("decode_seed", seed_ms), ("delta", delta_ms)):
        mean, sd = st.mean(xs), st.stdev(xs)
        print(f"{name}: mean={mean:.3f} sd={sd:.3f} sem={sd / n**0.5:.3f} cv={sd / mean * 100:.3f}%")

    # t(0.975, 4) = 2.776, t(0.80, 4) = 0.941 -> two-sided alpha .05, power .80.
    t_alpha, t_power = 2.776, 0.941
    mean_d, sd_d = st.mean(delta_ms), st.stdev(delta_ms)
    half = t_alpha * sd_d / n**0.5
    print(f"\npaired delta 95% CI: {mean_d:+.3f} +/- {half:.3f} ms -> [{mean_d - half:+.3f}, {mean_d + half:+.3f}]")
    mde_paired = (t_alpha + t_power) * sd_d / n**0.5
    mean_a, sd_a = st.mean(prefill_ms), st.stdev(prefill_ms)
    mde_single = (t_alpha + t_power) * sd_a / n**0.5
    print(f"paired MDE   (alpha .05 two-sided, power .80, n={n}): {mde_paired:.3f} ms = {mde_paired / mean_a * 100:.3f} % of the timed prefill")
    print(f"unpaired MDE (same test, timed prefill alone, n={n}): {mde_single:.3f} ms = {mde_single / mean_a * 100:.3f} %")
    print(f"H-M5-equivalent unpaired MDE at the same relative floor: {mde_single / mean_a * H_M5_PREFILL_MS:.3f} ms")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "cold-warm.tsv",
         sys.argv[2] if len(sys.argv) > 2 else "iterate")
