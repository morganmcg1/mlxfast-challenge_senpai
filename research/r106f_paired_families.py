#!/usr/bin/env python3
"""R106-F' Stage 1: paired per-family prefill decomposition, baseline vs candidate.

Reads two `research/prefill_probe.py --profile` logs produced back to back in one
session (pinned baseline tree and candidate tree) and emits a single table whose
two ms columns each sum to their own tree's wall, with nothing in `other`.

Three attribution corrections are applied and each is reported separately:
  1. MIXED command-buffer brackets are redistributed to the families the raw
     table already assigns them to, proportional to raw bracket ms.
  2. `other` members are folded into the functional stage they belong to.
  3. `arangeuint32` is a null-work bracket (0.016 MB/call, 0.0 GB/s) whose
     bracket time is pure gather-launch shadow; a sensitivity credits its
     fair share back to routed_gather_gemm.
"""
import re
import sys

STAGES = [
    ("A dense BF16 attn proj (q,k,v,o,g)", ["steel_gemm_bf16"]),
    ("B NVFP4 expert GEMM + epilogue", ["routed_gather_gemm", "nvfp4_dense_qmm", "moe_tail"]),
    ("C routing (sort/scatter/gather)", ["sort_scatter", "router"]),
    ("D attention core (SDPA)", ["attention_core"]),
    ("E norm + RoPE", ["rms_norm", "qk_norm_rope"]),
    ("F elementwise glue", ["elementwise"]),
    ("G lm_head + argmax", ["lm_head"]),
    ("I GPU idle (unattributed)", ["GPU-idle"]),
]
OTHER_ROUTES = [
    (re.compile(r"^gemv"), "lm_head"),
    (re.compile(r"routed_shared|shared_nvfp4"), "nvfp4_dense_qmm"),
]
NEAR_LO, NEAR_HI = 0.85, 1.18
NUM = r"[-+]?\d+(?:\.\d+)?"


def parse(path):
    txt = open(path).read()
    out = {"path": path}
    for key, pat in (
        ("wall", r"wall\s+(" + NUM + r")\s+ms/request"),
        ("busy_sum", r"gpu busy \(sum\)\s+(" + NUM + r")\s+ms"),
        ("busy_union", r"gpu busy \(union\)\s+(" + NUM + r")\s+ms"),
        ("cbs", r"command buffers\s+(" + NUM + r")"),
        ("dispatches", r"dispatches\s+(" + NUM + r")\s*/request"),
        ("gib", r"bound bytes\s+(" + NUM + r")\s+GiB"),
        ("median", r"prefill warm median:\s+(" + NUM + r")\s+ms"),
    ):
        m = re.search(pat, txt)
        out[key] = float(m.group(1)) if m else None

    raw = []
    row = re.compile(r"^\s*(\S+)\s+((?:" + NUM + r"\s+){6}" + NUM + r")\s+(\S+)\s*$")
    in_raw = False
    for line in txt.splitlines():
        if re.match(r"^\s*dispatch\s+.*\bn/req\b", line):
            in_raw = True
            continue
        if in_raw:
            if re.match(r"^\s*family\s+n/req", line):
                in_raw = False
                continue
            m = row.match(line)
            if m:
                v = [float(x) for x in m.group(2).split()]
                raw.append({"name": m.group(1), "n": v[0], "ms": v[2], "mb": v[4],
                            "gbs": v[5], "family": m.group(3)})
    out["raw"] = raw

    fair, excl, gb, in_fair = {}, {}, {}, False
    for line in txt.splitlines():
        if line.strip().startswith("family") and "fair ms" in line:
            in_fair = True
            continue
        if in_fair:
            s = line.strip()
            if s.startswith("TOTAL"):
                out["fair_total"] = float(s.split()[1])
                break
            m = re.match(r"^(\S+(?: \(unattrib\.\))?)\s+(" + NUM + r")\s+" + NUM
                         + r"(?:\s+(" + NUM + r")\s+" + NUM + r"\s+" + NUM
                         + r"\s+(" + NUM + r"))?", s)
            if m:
                f = m.group(1).replace(" (unattrib.)", "")
                fair[f] = float(m.group(2))
                if m.group(3) is not None:
                    excl[f] = float(m.group(3))
                    gb[f] = float(m.group(4))
    out["fair"], out["excl"], out["gb"] = fair, excl, gb
    return out


def resolve(t):
    fam = dict(t["fair"])
    notes = []
    mixed = fam.pop("MIXED", 0.0)
    if mixed > 0:
        w = {}
        for r in t["raw"]:
            if r["name"].startswith("MIXED:"):
                w[r["family"]] = w.get(r["family"], 0.0) + r["ms"]
        tot = sum(w.values())
        if tot <= 0:
            raise SystemExit("MIXED fair time with no MIXED raw brackets in " + t["path"])
        for f, wt in sorted(w.items(), key=lambda kv: -kv[1]):
            add = mixed * wt / tot
            fam[f] = fam.get(f, 0.0) + add
            notes.append(f"  MIXED total {mixed:8.3f} ms -> {f:<20s} +{add:8.3f} ms "
                         f"(raw bracket weight {wt:8.3f} ms)")
    oth = fam.pop("other", 0.0)
    if oth > 0:
        members = [r for r in t["raw"] if r["family"] == "other"]
        tot = sum(r["ms"] for r in members)
        for r in sorted(members, key=lambda r: -r["ms"]):
            dest = next((d for pat, d in OTHER_ROUTES if pat.search(r["name"])), None)
            if dest is None:
                raise SystemExit("unrouted `other` member: " + r["name"])
            add = oth * r["ms"] / tot
            fam[dest] = fam.get(dest, 0.0) + add
            notes.append(f"  other  {r['name'][:56]:<56s} -> {dest:<20s} +{add:8.3f} ms")
    return fam, notes


def arange_shift(t, fam):
    ar = [r for r in t["raw"] if r["name"] == "arangeuint32"]
    if not ar:
        return dict(fam), 0.0
    ar = ar[0]
    sib = sum(r["ms"] for r in t["raw"]
              if r["family"] == ar["family"] and not r["name"].startswith("MIXED:"))
    share = t["fair"].get(ar["family"], 0.0) * ar["ms"] / sib if sib else 0.0
    out = dict(fam)
    out[ar["family"]] -= share
    out["routed_gather_gemm"] += share
    return out, share


def stagify(fam):
    st, seen = {}, set()
    for label, fams in STAGES:
        st[label] = sum(fam.get(f, 0.0) for f in fams)
        seen |= set(fams)
    left = set(fam) - seen
    if left:
        raise SystemExit("probe families not mapped to a stage: " + repr(sorted(left)))
    return st


def table(base, cand, bst, cst, title):
    bw, cw = base["wall"], cand["wall"]
    print("\n" + title)
    print(f"  {'functional stage':<38s} {'base ms':>9s} {'base %':>7s} "
          f"{'cand ms':>9s} {'cand %':>7s} {'ratio':>7s}")
    near = 0.0
    for label, b in sorted(bst.items(), key=lambda kv: -kv[1]):
        c = cst[label]
        r = b / c if c > 0 else float("inf")
        flag = "  <-- ~1.0x" if NEAR_LO <= r <= NEAR_HI else ""
        print(f"  {label:<38s} {b:9.3f} {100*b/bw:7.2f} {c:9.3f} {100*c/cw:7.2f} {r:7.3f}{flag}")
        if NEAR_LO <= r <= NEAR_HI:
            near += b
    print(f"  {'TOTAL':<38s} {sum(bst.values()):9.3f} {100*sum(bst.values())/bw:7.2f} "
          f"{sum(cst.values()):9.3f} {100*sum(cst.values())/cw:7.2f} {bw/cw:7.3f}")
    print(f"  ledger closure: base {sum(bst.values())-bw:+.3f} ms, cand {sum(cst.values())-cw:+.3f} ms")
    print(f"  HEADLINE share of BASELINE prefill time in stages with speedup ~1.0x "
          f"({NEAR_LO}-{NEAR_HI}x): {100*near/bw:.2f} %  ({near:.3f} of {bw:.3f} ms)")
    return near


def main(base_path, cand_path):
    base, cand = parse(base_path), parse(cand_path)
    print("=" * 104)
    print("R106-F' Stage 1 - paired M4 Pro prefill family decomposition (512-token forward)")
    print("=" * 104)
    for t, tag in ((base, "BASELINE 15852ee5"), (cand, "CANDIDATE HEAD  ")):
        print(f"\n{tag}  ({t['path']})")
        print(f"  warm median {t['median']:.3f} ms   instrumented wall {t['wall']:.3f} ms   "
              f"busy union {t['busy_union']:.3f} ({100*t['busy_union']/t['wall']:.1f} % of wall)")
        print(f"  command buffers {t['cbs']:.0f}   dispatches {t['dispatches']:.0f}   "
              f"bound {t['gib']:.3f} GiB")

    print("\nWORK-IDENTITY TEST (Stage 2 input)")
    print(f"  dispatches      base {base['dispatches']:.0f}  cand {cand['dispatches']:.0f}  "
          f"delta {cand['dispatches']-base['dispatches']:+.0f} "
          f"({100*(cand['dispatches']/base['dispatches']-1):+.1f} %)")
    print(f"  command buffers base {base['cbs']:.0f}  cand {cand['cbs']:.0f}  "
          f"delta {cand['cbs']-base['cbs']:+.0f} ({100*(cand['cbs']/base['cbs']-1):+.1f} %)")
    print(f"  bound bytes     base {base['gib']:.3f}  cand {cand['gib']:.3f} GiB  "
          f"delta {100*(cand['gib']/base['gib']-1):+.1f} %")
    for f in ("steel_gemm_bf16", "attention_core", "routed_gather_gemm"):
        bn = sum(r["n"] for r in base["raw"] if r["family"] == f)
        cn = sum(r["n"] for r in cand["raw"] if r["family"] == f)
        print(f"  {f:<20s} dispatches base {bn:6.0f}  cand {cn:6.0f}  ({100*(cn/bn-1):+.1f} %)")

    bfam, bnotes = resolve(base)
    cfam, cnotes = resolve(cand)
    print("\nATTRIBUTION REPAIRS - baseline")
    print("\n".join(bnotes) or "  none")
    print("ATTRIBUTION REPAIRS - candidate")
    print("\n".join(cnotes) or "  none")

    bst, cst = stagify(bfam), stagify(cfam)
    table(base, cand, bst, cst, "PRIMARY TABLE (fair-share; MIXED and other resolved), sorted by baseline ms")

    b2, bsh = arange_shift(base, bfam)
    c2, csh = arange_shift(cand, cfam)
    print(f"\nSENSITIVITY: null-work `arangeuint32` fair share credited to routed_gather_gemm "
          f"(base {bsh:.3f} ms, cand {csh:.3f} ms)")
    table(base, cand, stagify(b2), stagify(c2), "SENSITIVITY TABLE")

    print("\nFAIR-SHARE-FREE CROSS-CHECK (per probe family; excl = time with no concurrent "
          "sibling, raw = summed bracket time)")
    print(f"  {'probe family':<22s} {'b excl':>9s} {'c excl':>9s} {'e ratio':>8s} "
          f"{'b raw':>9s} {'c raw':>9s} {'r ratio':>8s} {'b GB':>7s} {'c GB':>7s}")
    for f in sorted(set(base["fair"]) | set(cand["fair"])):
        if f in ("MIXED", "GPU-idle"):
            continue
        be, ce = base["excl"].get(f, 0.0), cand["excl"].get(f, 0.0)
        br = sum(r["ms"] for r in base["raw"] if r["family"] == f)
        cr = sum(r["ms"] for r in cand["raw"] if r["family"] == f)
        er = be / ce if ce > 0 else float("inf")
        rr = br / cr if cr > 0 else float("inf")
        print(f"  {f:<22s} {be:9.3f} {ce:9.3f} {er:8.3f} {br:9.3f} {cr:9.3f} {rr:8.3f} "
              f"{base['gb'].get(f, 0.0):7.3f} {cand['gb'].get(f, 0.0):7.3f}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: r106f_paired_families.py BASE.log CAND.log")
    main(sys.argv[1], sys.argv[2])
