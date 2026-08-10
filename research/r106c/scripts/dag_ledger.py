#!/usr/bin/env python3
"""R106-C decode serialisation ledger.

Reads the extended dispatch trace (research/r106c/scripts/trace_dag.patch) and
reconstructs the exact runtime dependency graph of one steady decode step:

  * replays MLX's greedy barrier heuristic and checks it against the observed
    barrier column (instrument validation);
  * computes the minimum number of barrier-separated concurrent groups that any
    reordering could achieve (Mirsky: = longest chain in the conflict DAG);
  * reports the headroom in barriers, at buffer-pointer granularity (what MLX
    actually tracks) and at byte-range granularity (what a perfect tracker
    could do).

Usage: dag_ledger.py <dump-dir> [out-dir]
"""
import sys
import os
import json
from collections import Counter, defaultdict

COLS = ["seq", "kernel", "kind", "grid", "group", "args", "barrier", "enc", "ins", "outs"]

# Measured tax coefficients (PR #268, M4 Pro): barrier 1.3003 +/- 0.0597 us.
BARRIER_US = 1.3003
# Decode price board: 1 us/step of decode == 0.015228 % of the composite score.
DECODE_PCT_PER_US = 0.015228
# Stage-3 build gate agreed in the assignment: >= 33 us/step (~ +0.5 % of cs).
STAGE3_GATE_US = 33.0
FAMILY_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "artifacts",
    "fern-r105e",
    "family-bandwidth-ledger.csv",
)


def load_families(path):
    """family -> {label_us_m4, n_dispatches, regime} from the R105-E ledger."""
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path) as f:
        header = f.readline().rstrip("\n").split(",")
        for line in f:
            v = line.rstrip("\n").split(",")
            if len(v) != len(header):
                continue
            d = dict(zip(header, v))
            out[d["family"]] = {
                "label_us_m4": float(d["label_us_m4"] or 0.0),
                "n_dispatches": int(d["n_dispatches"]),
                "regime": d["regime"],
            }
    return out


def family_of(kernel, fams, _cache={}):
    """Longest-substring match so `argmax` cannot capture `..._argmax_stage1`."""
    if kernel in _cache:
        return _cache[kernel]
    hit = None
    for f in sorted(fams, key=len, reverse=True):
        if f in kernel:
            hit = f
            break
    _cache[kernel] = hit
    return hit


def parse_ranges(field):
    out = []
    for tok in field.split():
        ptr, _, rest = tok.partition("+")
        off, _, size = rest.partition(":")
        out.append((ptr, int(off), int(size)))
    return out


def load(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#MARK"):
                continue
            parts = line.split("\t")
            if len(parts) != len(COLS):
                continue
            r = dict(zip(COLS, parts))
            r["seq"] = int(r["seq"])
            r["barrier"] = int(r["barrier"])
            r["enc"] = int(r["enc"])
            r["ins"] = parse_ranges(r["ins"])
            r["outs"] = parse_ranges(r["outs"])
            rows.append(r)
    return rows


def find_period(names, tail=6000, lo=50, hi=1200):
    """Find the repeat period of the decode tail of the name sequence."""
    seq = names[-tail:]
    best = None
    for p in range(lo, min(hi, len(seq) // 3)):
        n = 0
        ok = True
        # compare the last 3 windows of length p
        for k in range(1, 3):
            a = seq[len(seq) - k * p:len(seq) - (k - 1) * p or None]
            b = seq[len(seq) - (k + 1) * p:len(seq) - k * p]
            if a != b:
                ok = False
                break
            n += 1
        if ok:
            best = p
            break
    return best


def key_ptr(r):
    return {p for (p, o, s) in r}


class IntervalSet:
    """Per-buffer interval sets, for byte-range-precise conflict tests."""

    @staticmethod
    def overlaps(a, b):
        for (pa, oa, sa) in a:
            for (pb, ob, sb) in b:
                if pa == pb and oa < ob + sb and ob < oa + sa:
                    return True
        return False


def replay_mlx(step):
    """Replay MLX CommandEncoder::maybeInsertBarrier over the step.

    device.cpp:458-463 clears the hazard sets in end_encoding(), so the first
    dispatch of each command buffer never charges a barrier: cross-encoder
    ordering is carried by the encoder fence instead.
    """
    prev_in, prev_out = set(), set()
    fired = []
    enc = None
    for r in step:
        if r["enc"] != enc:
            enc = r["enc"]
            prev_in, prev_out = set(), set()
        I, O = key_ptr(r["ins"]), key_ptr(r["outs"])
        need = bool(I & prev_out) or bool(O & prev_in)
        fired.append(1 if need else 0)
        if need:
            prev_in, prev_out = set(I), set(O)
        else:
            prev_in |= I
            prev_out |= O
    return fired


def greedy_groups(step, precise):
    """Number of groups produced by MLX's linear greedy grouping."""
    groups = 1
    prev_in, prev_out = [], []
    for r in step:
        I, O = r["ins"], r["outs"]
        if precise:
            need = IntervalSet.overlaps(I, prev_out) or IntervalSet.overlaps(O, prev_in)
        else:
            need = bool(key_ptr(I) & {p for (p, _, _) in prev_out}) or bool(
                key_ptr(O) & {p for (p, _, _) in prev_in}
            )
        if need:
            groups += 1
            prev_in, prev_out = list(I), list(O)
        else:
            prev_in += I
            prev_out += O
    return groups


def conflict_depth(step, precise, anti=True, weights=None):
    """Longest chain in the conflict DAG = minimum antichain levels (Mirsky).

    With `weights`, returns the longest *weighted* chain instead, i.e. the
    duration-weighted critical path through the same DAG.
    """
    n = len(step)
    ins = [r["ins"] for r in step]
    outs = [r["outs"] for r in step]
    if precise:
        conflict = lambda i, j: IntervalSet.overlaps(ins[j], outs[i]) or (
            anti and IntervalSet.overlaps(outs[j], ins[i])
        )
    else:
        pins = [key_ptr(r["ins"]) for r in step]
        pouts = [key_ptr(r["outs"]) for r in step]
        conflict = lambda i, j: bool(pins[j] & pouts[i]) or (
            anti and bool(pouts[j] & pins[i])
        )
    w = weights if weights is not None else [1.0] * n
    level = [0.0] * n
    for j in range(n):
        best = 0.0
        for i in range(j):
            if level[i] > best and conflict(i, j):
                best = level[i]
        level[j] = best + w[j]
    return max(level), level


def main():
    dump = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else dump
    os.makedirs(outdir, exist_ok=True)
    rows = load(os.path.join(dump, "dispatch.tsv"))
    names = [r["kernel"] for r in rows]
    print(f"total dispatch rows: {len(rows)}")
    print(f"encoders (command buffers): {len(set(r['enc'] for r in rows))}")

    period = find_period(names)
    print(f"decode step period (dispatches): {period}")
    if period is None:
        sys.exit("could not find a repeating decode period")

    # take the last complete period as the steady decode step
    step = rows[len(rows) - period:]
    assert len(step) == period

    obs = [r["barrier"] for r in step]
    rep = replay_mlx(step)
    # the first dispatch of the window inherits state from the previous step;
    # compare from index 1 onward.
    mismatch = sum(1 for a, b in zip(obs[1:], rep[1:]) if a != b)
    print(f"observed barriers in step: {sum(obs)}")
    print(f"replayed barriers in step: {sum(rep)}  mismatches(after idx0): {mismatch}")

    ncb = len(set(r["enc"] for r in step))
    print(f"command buffers spanned by the step: {ncb}")

    res = {
        "dispatches_per_step": period,
        "observed_barriers": sum(obs),
        "replayed_barriers": sum(rep),
        "replay_mismatches": mismatch,
        "command_buffers_per_step": ncb,
        "total_rows": len(rows),
    }

    levels_ptr = None
    for precise in (False, True):
        tag = "range" if precise else "ptr"
        g = greedy_groups(step, precise)
        d_anti, lv = conflict_depth(step, precise, anti=True)
        d_raw, _ = conflict_depth(step, precise, anti=False)
        res[f"greedy_groups_{tag}"] = g
        res[f"min_groups_{tag}_with_anti"] = int(d_anti)
        res[f"min_groups_{tag}_raw_only"] = int(d_raw)
        if not precise:
            levels_ptr = lv
        print(
            f"[{tag}] greedy groups={g}  min groups (RAW+WAR)={int(d_anti)}  "
            f"min groups (RAW only)={int(d_raw)}"
        )

    # ---- level-size histogram (how wide is each antichain?) -----------------
    hist = Counter(int(x) for x in levels_ptr)
    sizes = Counter(hist.values())
    res["level_size_histogram"] = sorted(sizes.items())
    res["mean_dispatches_per_level"] = round(period / max(hist), 4)
    res["singleton_levels"] = sizes.get(1, 0)
    res["dispatches_in_singleton_levels"] = sizes.get(1, 0)
    print(f"level sizes: {sorted(sizes.items())}  mean={period / max(hist):.3f}")

    # ---- family attribution and duration-weighted critical path ------------
    fams = load_families(FAMILY_CSV)
    per_disp = {}
    if fams:
        counts = Counter(family_of(r["kernel"], fams) for r in step)
        for f, n in counts.items():
            per_disp[f] = (fams.get(f, {}).get("label_us_m4", 0.0)) / n if n else 0.0
        w = [per_disp.get(family_of(r["kernel"], fams), 0.0) for r in step]
        total_w = sum(w)
        cp_w, _ = conflict_depth(step, False, anti=True, weights=w)
        cp_w_raw, _ = conflict_depth(step, False, anti=False, weights=w)
        res["label_sum_us_m4"] = round(total_w, 2)
        res["label_weighted_critical_path_us_m4"] = round(cp_w, 2)
        res["label_weighted_critical_path_raw_only_us_m4"] = round(cp_w_raw, 2)
        res["label_weighted_cp_frac"] = round(cp_w / total_w, 5) if total_w else None
        res["unattributed_dispatches"] = sum(
            1 for r in step if family_of(r["kernel"], fams) is None
        )
        print(
            f"[labels, DESCRIPTIVE ONLY - Rule 82 inadmissible for pricing] "
            f"sum={total_w:.1f}us  weighted critical path={cp_w:.1f}us "
            f"({100 * cp_w / total_w:.1f}%)"
        )

    # ---- barrier accounting and pricing ------------------------------------
    sep = res["greedy_groups_ptr"] - 1  # hazard separations in the linear order
    charged = sum(obs)
    res["hazard_separations"] = sep
    res["charged_barriers"] = charged
    res["free_at_encoder_boundary"] = sep - charged
    res["encoder_boundaries_in_step"] = ncb - 1

    headroom_groups = res["greedy_groups_ptr"] - res["min_groups_ptr_with_anti"]
    res["headroom_groups"] = headroom_groups
    res["headroom_us_per_step"] = round(headroom_groups * BARRIER_US, 4)
    res["headroom_pct_of_cs"] = round(
        headroom_groups * BARRIER_US * DECODE_PCT_PER_US, 5
    )
    # absolute ceiling: also perfectly align command-buffer boundaries
    ceil_charged = max(res["min_groups_ptr_with_anti"] - 1 - (ncb - 1), 0)
    res["ceiling_charged_barriers_if_cb_aligned"] = ceil_charged
    res["ceiling_headroom_us_per_step"] = round((charged - ceil_charged) * BARRIER_US, 4)
    res["ceiling_headroom_pct_of_cs"] = round(
        (charged - ceil_charged) * BARRIER_US * DECODE_PCT_PER_US, 5
    )
    res["stage3_gate_us_per_step"] = STAGE3_GATE_US
    res["stage3_gate_open"] = res["headroom_us_per_step"] >= STAGE3_GATE_US
    print(
        f"separations={sep}  charged={charged}  free at encoder boundary="
        f"{sep - charged} over {ncb - 1} encoder boundaries"
    )
    print(
        f"headroom={headroom_groups} groups = {res['headroom_us_per_step']} us/step "
        f"= {res['headroom_pct_of_cs']}% of cs   (gate {STAGE3_GATE_US} us) -> "
        f"{'OPEN' if res['stage3_gate_open'] else 'CLOSED'}"
    )
    print(
        f"absolute ceiling (CB boundaries also aligned): "
        f"{res['ceiling_headroom_us_per_step']} us/step = "
        f"{res['ceiling_headroom_pct_of_cs']}% of cs"
    )

    fam = Counter()
    for r in step:
        fam[r["kernel"]] += 1
    res["kernels"] = fam.most_common()

    with open(os.path.join(outdir, "dag_ledger.json"), "w") as f:
        json.dump(res, f, indent=2)

    with open(os.path.join(outdir, "decode_step_dispatches.tsv"), "w") as f:
        f.write("idx\tkernel\tkind\tgrid\tgroup\tbarrier\tenc\tn_in\tn_out\n")
        for i, r in enumerate(step):
            f.write(
                f"{i}\t{r['kernel']}\t{r['kind']}\t{r['grid']}\t{r['group']}\t"
                f"{r['barrier']}\t{r['enc']}\t{len(r['ins'])}\t{len(r['outs'])}\n"
            )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
