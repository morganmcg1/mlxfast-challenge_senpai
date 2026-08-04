#!/usr/bin/env python3
"""PR#37 Part 0 stage A (research-only, not part of the submission).

Reads the real decode lm_head input rows dumped from the runtime worker plus the
bf16 lm_head weight, reproduces the int5 planes exactly as
LagunaLmHeadPrune.buildInt5Planes does, and caches:

  E     [T, V] f32  exact fp32 logits
  C[b]  [T, V] f32  coarse logits from the b-bit truncation of the int5 code
                    (b = 4 is the shipped level-one nibble plane)
  sd    [V, 64] f32 per-32-group power-of-two scale
  M128  [V, 16] f32 per-128-group max |w|  (the level-0 tail-bound plane)

Run: python3 research/maple_fern_pr37_stage_a.py
"""
import json
import os
import struct
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XDUMP = os.environ.get("PR37_XDUMP", "/tmp/lmhead_x.f32")
SHARD = os.path.join(REPO, "weights/model-00005-of-00005.safetensors")
OUT = os.environ.get("PR37_CACHE", "/tmp/pr37")
V, H = 100352, 2048
BITS = (5, 4, 3, 2)


def bf16_to_f32(u16: np.ndarray) -> np.ndarray:
    return (u16.astype(np.uint32) << 16).view(np.float32)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    x = np.fromfile(XDUMP, dtype=np.float32).reshape(-1, H)
    print(f"x rows: {x.shape}")

    with open(SHARD, "rb") as fh:
        hlen = struct.unpack("<Q", fh.read(8))[0]
        header = json.loads(fh.read(hlen))
    info = header["lm_head.weight"]
    assert info["shape"] == [V, H] and info["dtype"] == "BF16", info
    base = 8 + hlen + info["data_offsets"][0]
    raw = np.memmap(SHARD, dtype=np.uint16, mode="r", offset=base, shape=(V, H))

    T = x.shape[0]
    E = np.zeros((T, V), dtype=np.float32)
    C = {b: np.zeros((T, V), dtype=np.float32) for b in BITS}
    sd_all = np.zeros((V, 64), dtype=np.float32)
    m128_all = np.zeros((V, 16), dtype=np.float32)
    n128_all = np.zeros((V, 16), dtype=np.float32)
    rnorm = {b: np.zeros(V, dtype=np.float32) for b in BITS}
    q0_all = np.zeros((V, H), dtype=np.uint8)  # offset-binary code u = q + 16

    chunk = 6272
    t0 = time.time()
    maxcode = 0.0
    for lo in range(0, V, chunk):
        hi = min(lo + chunk, V)
        w = bf16_to_f32(np.asarray(raw[lo:hi]))
        E[:, lo:hi] = x @ w.T

        wg = w.reshape(-1, 64, 32)
        gmax = np.abs(wg).max(axis=2)
        gbits = gmax.view(np.uint32)
        biased = (gbits >> 23).astype(np.int32)
        mant = gbits & np.uint32(0x007F_FFFF)
        bump = (mant >= np.uint32(0x0078_0000)).astype(np.int32)
        sd_byte = np.clip(biased - 3 + bump, 0, 255).astype(np.uint32)
        sd = np.where(
            sd_byte == 0,
            np.float32(np.frombuffer(np.uint32(0x0040_0000).tobytes(), dtype=np.float32)[0]),
            (sd_byte << 23).view(np.float32),
        ).astype(np.float32)
        q = np.rint(wg / sd[:, :, None]).astype(np.int32)
        maxcode = max(maxcode, float(np.abs(q).max()))
        u = (q + 16).astype(np.uint8).reshape(-1, H)
        q0_all[lo:hi] = u
        sd_all[lo:hi] = sd
        m128_all[lo:hi] = gmax.reshape(-1, 16, 4).max(axis=2)
        n128_all[lo:hi] = np.sqrt((w.reshape(-1, 16, 128).astype(np.float64) ** 2).sum(axis=2))

        for b in BITS:
            step = 1 << (5 - b)
            mid = (u >> (5 - b)).astype(np.float32) * step + (step - 1) * 0.5 - 16.0
            what = (mid.reshape(-1, 64, 32) * sd[:, :, None]).reshape(-1, H)
            C[b][:, lo:hi] = x @ what.T
            rnorm[b][lo:hi] = np.sqrt(((w - what).astype(np.float64) ** 2).sum(axis=1))
        del w, wg, what
    print(f"planes+logits in {time.time() - t0:.1f}s, max|q| = {maxcode}")
    assert maxcode <= 15.0

    np.save(f"{OUT}/x.npy", x)
    np.save(f"{OUT}/E.npy", E)
    for b in BITS:
        np.save(f"{OUT}/C{b}.npy", C[b])
    np.save(f"{OUT}/sd.npy", sd_all)
    np.save(f"{OUT}/m128.npy", m128_all)
    np.save(f"{OUT}/n128.npy", n128_all)
    for b in BITS:
        np.save(f"{OUT}/rnorm{b}.npy", rnorm[b])
    np.save(f"{OUT}/q0.npy", q0_all)

    with open(os.path.join(REPO, os.environ.get("PR37_GOLDEN", "correctness_prompts/public_longcopy_gate_english_512_256.json"))) as fh:
        case = json.load(fh)["cases"][0]
    exp = np.array(case["expected_tokens"][: T + 2], dtype=np.int64)
    got = E.argmax(axis=1)
    n = min(len(got), len(exp))
    ok = got[1:n] == exp[1:n]
    print(
        f"VALIDATION: offline argmax vs golden greedy tokens: {int(ok.sum())}/{len(ok)} match"
        f" (dump row 0 is the worker's pre-timing forward: got {got[0]}, golden {exp[0]})"
    )
    return 0 if ok.all() else 1


if __name__ == "__main__":
    sys.exit(main())
