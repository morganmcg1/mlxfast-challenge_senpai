#!/usr/bin/env python3
"""Research-only barrier-SITE census for one default decode step (PR #268 r2).

r1 established that the ~1.4 us decode chain-link tax is a BARRIER tax
(+1.3003 +/- 0.0597 us per MLX memoryBarrier) and not a dispatch tax
(+0.1231 +/- 0.0481 us). That prices a barrier but does not say where the
barriers are, so it cannot yet price a specific fusion.

This driver runs the unmodified decode path under
research/fern_tax_sitetrace.patch, which dumps every compute dispatch in
encode order with its command-buffer index, whether MLX inserted a
memoryBarrier in front of it, and which earlier dispatch produced the resource
that forced it. It then reduces that trace to:

  * the barrier-site map of one steady-state decode step;
  * the per-layer barrier template, by layer class; and
  * the producer->consumer edge that each barrier pays for.

Usage (worker must be built with the patch applied, and must be the only
model-holding process on the host):

  python3 research/fern_tax_sitetrace.py --steps 6 --out research/artifacts/fern_sites

Nothing here is submitted.
"""
import argparse
import collections
import json
import os
import re
import subprocess
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER = os.path.join(REPO, ".build-worker/release/mlxfast-runtime-worker")
GOLDEN = os.path.join(
    REPO, "correctness_prompts/public_longcopy_gate_english_512_256.json"
)
SITE_RE = re.compile(r"^DBSITE (.*)$")


def parse(path):
    """-> (epochs, cbs) where epochs[i] is the dispatch list of epoch i."""
    epochs = collections.defaultdict(list)
    with open(path, "rb") as fh:
        for raw in fh:
            line = raw.decode("utf-8", "replace").strip()
            m = SITE_RE.match(line)
            if not m:
                continue
            rec = {}
            for item in m.group(1).split():
                if "=" not in item:
                    continue
                k, v = item.split("=", 1)
                rec[k] = int(v) if v.lstrip("-").isdigit() else v
            epochs[rec["ep"]].append(rec)
    return epochs


def run_worker(steps, weights, trace_path):
    with open(GOLDEN) as fh:
        case = json.load(fh)["cases"][0]
    prompt, expected = case["prompt_tokens"], case["expected_tokens"]
    env = dict(os.environ)
    env.setdefault("MLXFAST_WEIGHTS_PATH", weights)
    env["DBTAX_SITE_TRACE"] = trace_path
    errfh = open(trace_path + ".worker.err", "wb")
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        [WORKER, "runtime-worker", "--weights", weights],
        cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=errfh, env=env, bufsize=1, text=True,
    )
    rid = 1000

    def send(req):
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise SystemExit("worker closed stdout; see " + trace_path + ".worker.err")
        resp = json.loads(line)
        if not resp.get("ok", False):
            raise SystemExit("worker error: " + json.dumps(resp))
        return resp

    hello = json.loads(proc.stdout.readline())
    print(f"worker up in {time.perf_counter()-t0:.1f}s ok={hello.get('ok')}", flush=True)
    rid += 1
    send({"id": rid, "kind": "decode_begin", "seed_tokens": prompt})
    for i in range(steps):
        rid += 1
        send({"id": rid, "kind": "decode_step", "token": expected[i]})
    proc.stdin.close()
    proc.wait(timeout=120)
    errfh.close()


def steady_epoch(epochs):
    """Pick the last epoch whose dispatch count equals the modal count."""
    counts = collections.Counter(len(v) for v in epochs.values())
    modal, _ = counts.most_common(1)[0]
    cands = [e for e, v in sorted(epochs.items()) if len(v) == modal]
    return cands[-1], modal, counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=6)
    ap.add_argument("--weights", default="weights")
    ap.add_argument("--out", required=True)
    ap.add_argument("--trace", default=None)
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    trace = args.trace or (args.out + ".trace")
    if not args.trace:
        run_worker(args.steps, args.weights, trace)

    epochs = parse(trace)
    if not epochs:
        raise SystemExit("no DBSITE records in " + trace)
    ep, modal, counts = steady_epoch(epochs)
    rows = epochs[ep]
    print(f"epochs={len(epochs)} dispatch-count histogram={dict(counts)}")
    print(f"steady epoch={ep} dispatches={modal}")

    bars = sum(r["bar"] for r in rows)
    cbs = len({r["cb"] for r in rows})
    print(f"barriers={bars} command_buffers={cbs}")

    ordmap = {r["ord"]: r for r in rows}

    def kname(o):
        r = ordmap.get(o)
        return r["k"] if r else f"<ord {o} outside epoch>"

    with open(args.out + ".sitemap.tsv", "w") as fh:
        fh.write("idx\tcb\tord\tbar\tgap\tkernel\tgrid\traw_producers\twar_producers\n")
        for i, r in enumerate(rows):
            raws = "|".join(
                kname(int(x)) if x != "x" else "x" for x in str(r["raw"]).split(",")
            ) if r["raw"] != "-" else "-"
            wars = "|".join(
                kname(int(x)) if x != "x" else "x" for x in str(r["war"]).split(",")
            ) if r["war"] != "-" else "-"
            fh.write(
                f"{i}\t{r['cb']}\t{r['ord']}\t{r['bar']}\t{r['gap']}\t{r['k']}\t"
                f"{r['grid']}\t{raws}\t{wars}\n"
            )

    per_kernel = collections.Counter()
    per_kernel_bar = collections.Counter()
    for r in rows:
        per_kernel[r["k"]] += 1
        per_kernel_bar[r["k"]] += r["bar"]
    with open(args.out + ".perkernel.tsv", "w") as fh:
        fh.write("kernel\tdispatches\tbarriers\tbarrier_rate\n")
        for k, n in per_kernel.most_common():
            fh.write(f"{k}\t{n}\t{per_kernel_bar[k]}\t{per_kernel_bar[k]/n:.3f}\n")

    edges = collections.Counter()
    for r in rows:
        if not r["bar"]:
            continue
        srcs = []
        if r["raw"] != "-":
            srcs += [("RAW", x) for x in str(r["raw"]).split(",")]
        if r["war"] != "-":
            srcs += [("WAR", x) for x in str(r["war"]).split(",")]
        if not srcs:
            edges[("?", "-", r["k"])] += 1
        for kind, x in srcs:
            edges[(kind, kname(int(x)) if x != "x" else "x", r["k"])] += 1
    with open(args.out + ".edges.tsv", "w") as fh:
        fh.write("kind\tproducer\tconsumer\tcount\n")
        for (kind, p, c), n in edges.most_common():
            fh.write(f"{kind}\t{p}\t{c}\t{n}\n")

    print("wrote", args.out + ".sitemap.tsv", args.out + ".perkernel.tsv",
          args.out + ".edges.tsv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
