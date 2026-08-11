#!/usr/bin/env python3
"""R122-A: turn the paired split-arm cell logs into per-role busy tables.

    research/maple-alphonse-r122a-attrib.py OUT_DIR [CSV_OUT]

Kernel rows are matched by ROLE (substring on the family), never by exact
name, because the o_proj pipelines are name-suffixed per geometry (`_rps2ns2`).
Every SPLIT=1 number is read raw: the additive per-dispatch SPLIT=1 overhead is
identical across arms at equal dispatch count and cancels in the paired
difference.
"""
import csv
import glob
import os
import random
import re
import statistics
import sys

ROLES = [
    ("oproj_h64", "oproj_act_h64"),
    ("oproj_h48", "oproj_act_h48"),
    ("K2_qkv_h64", "decode_nvfp4_qkv_gate_h64"),
    ("K2_qkv_h48", "decode_nvfp4_qkv_gate_h48"),
    ("K1_routed_swiglu", "swiglu_qmv_packed_top8keys"),
    ("K4_shared_down", "shared_nvfp4_down_residual"),
    ("sliding_attn", "sliding_fused_attn_ring"),
    ("full_attn", "full_fused_attn_grow"),
]

STEADY = re.compile(
    r"per steady step: wall=([\d.]+) ms gpu_busy_sum=([\d.]+) ms "
    r"gpu_busy_union=([\d.]+) ms gap=([-\d.]+) ms \(([-\d.]+)% of wall\) "
    r"cbs=([\d.]+) dispatches=([\d.]+)")
ROW = re.compile(r"^\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s\s+(.*)$")
DIV = re.compile(r"teacher-forced greedy tokens: (\d+) divergences")


def parse_cell(path):
    tag = os.path.basename(path)[:-4]
    idx, arm, split, profile = tag.split("-")
    cell = {"tag": tag, "idx": int(idx), "arm": arm,
            "split": split[1:], "profile": profile}
    text = open(path, errors="replace").read()
    m = STEADY.search(text)
    if not m:
        cell["void"] = "no steady-step line"
        return cell
    (cell["wall_ms"], cell["busy_sum_ms"], cell["busy_union_ms"],
     cell["gap_ms"], cell["gap_pct"], cell["cbs"],
     cell["dispatches"]) = (float(x) for x in m.groups())
    d = DIV.search(text)
    cell["divergences"] = int(d.group(1)) if d else -1
    for role, _ in ROLES:
        cell[role + "_us"] = 0.0
        cell[role + "_n"] = 0.0
        cell[role + "_names"] = ""
    cell["multi_kernel_us"] = 0.0
    for line in text.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        us, _share, npc, _uspc, name = m.groups()
        # A record whose key names several kernels is one command buffer that
        # batched them; it cannot be attributed to a role. Under SPLIT=1 these
        # should be absent, and their size is reported as an attribution
        # residual rather than folded into any role.
        if "|" in name or name.startswith("["):
            cell["multi_kernel_us"] += float(us)
            continue
        for role, needle in ROLES:
            if needle in name:
                cell[role + "_us"] += float(us)
                cell[role + "_n"] += float(npc)
                names = set(filter(None, cell[role + "_names"].split(";")))
                names.add(name)
                cell[role + "_names"] = ";".join(sorted(names))
    cell["oproj_family_us"] = cell["oproj_h64_us"] + cell["oproj_h48_us"]
    err = path[:-4] + ".err.gz"
    cell["cb_env"] = ""
    if os.path.exists(err):
        import gzip
        with gzip.open(err, "rt", errors="replace") as fh:
            for line in fh:
                if "cb-env:" in line:
                    cell["cb_env"] = line.split("cb-env:")[1].strip()
                    break
    return cell


def boot_ci(values, reps=20000, seed=17):
    rng = random.Random(seed)
    n = len(values)
    meds = sorted(statistics.median(
        [values[rng.randrange(n)] for _ in range(n)]) for _ in range(reps))
    return meds[int(0.025 * reps)], meds[int(0.975 * reps)]


def summarize(cells, field, out):
    arms = sorted({c["arm"] for c in cells})
    per = {a: [c[field] for c in cells if c["arm"] == a] for a in arms}
    for a in arms:
        v = per[a]
        out.append(f"  {field:20s} arm {a}: n={len(v)} "
                   f"mean={statistics.mean(v):9.2f} med={statistics.median(v):9.2f} "
                   f"sd={statistics.pstdev(v):7.2f} "
                   f"raw={[round(x, 1) for x in v]}")
    if "C" in per and "R" in per:
        d = statistics.mean(per["R"]) - statistics.mean(per["C"])
        dm = statistics.median(per["R"]) - statistics.median(per["C"])
        out.append(f"  {field:20s} R-C: mean_delta={d:+9.2f} med_delta={dm:+9.2f}")
    return per


def main():
    outdir = sys.argv[1]
    csvout = sys.argv[2] if len(sys.argv) > 2 else None
    cells = [parse_cell(p) for p in sorted(glob.glob(os.path.join(outdir, "*.log")))
             if not p.endswith("build.log")]
    cells = [c for c in cells if "wall_ms" in c]
    if csvout:
        keys = sorted({k for c in cells for k in c})
        with open(csvout, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            for c in cells:
                w.writerow(c)
    for split in ("1", "0"):
        sub = [c for c in cells if c["split"] == split]
        if not sub:
            continue
        print(f"\n===== SPLIT={split}  n_cells={len(sub)} "
              f"profiles={sorted({c['profile'] for c in sub})}")
        for c in sub:
            print(f"  {c['tag']}  wall={c['wall_ms']:.3f} busy={c['busy_sum_ms']:.3f} "
                  f"gap={c['gap_ms']:.3f} cbs={c['cbs']:.1f} disp={c['dispatches']:.1f} "
                  f"div={c['divergences']} oproj64={c['oproj_h64_us']:.1f}"
                  f"@n={c['oproj_h64_n']:.2f} oproj48={c['oproj_h48_us']:.1f}"
                  f"@n={c['oproj_h48_n']:.2f}")
            print(f"      names64={c['oproj_h64_names']}")
            print(f"      cb-env={c['cb_env']}")
        out = []
        fields = ["oproj_h64_us", "oproj_h48_us", "oproj_family_us",
                  "busy_sum_ms", "busy_union_ms", "wall_ms", "gap_ms",
                  "cbs", "dispatches", "multi_kernel_us"] + [r + "_us" for r, _ in ROLES[2:]]
        for f in fields:
            summarize(sub, f, out)
        print("\n".join(out))
        # adjacent paired deltas, R - C, in file order
        for f in ("oproj_family_us", "busy_sum_ms", "wall_ms", "gap_ms"):
            deltas = []
            for a, b in zip(sub, sub[1:]):
                if {a["arm"], b["arm"]} == {"C", "R"} and a["idx"] % 2 == 1:
                    r = a if a["arm"] == "R" else b
                    c = b if a["arm"] == "R" else a
                    deltas.append((r[f] - c[f], f"{c['tag']}->{r['tag']}"))
            if not deltas:
                continue
            vals = [d for d, _ in deltas]
            lo, hi = boot_ci(vals) if len(vals) > 2 else (float("nan"),) * 2
            print(f"\n  paired R-C {f}: n={len(vals)} "
                  f"med={statistics.median(vals):+9.3f} "
                  f"mean={statistics.mean(vals):+9.3f} "
                  f"boot95=[{lo:+.3f}, {hi:+.3f}]")
            for d, lbl in deltas:
                print(f"      {d:+9.3f}  {lbl}")


if __name__ == "__main__":
    main()
