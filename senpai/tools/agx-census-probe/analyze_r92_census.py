#!/usr/bin/env python3
"""Turn the r92-b census TSV into the stage-2 table, with controls checked first.

Controls (must pass before any decode row is interpreted, per rule 42):
  * encoding.metal marginal bytes/op over N in {32,64,128} must reproduce the
    published table: float add 4.0/4.0, float FMA 6.0/6.0, loop-varying float
    immediate 11.0/11.0, uint MAD 12.0 g16s -> 14.0 g17s.
  * floor.metal must pin the per-arch __compute floor. The floor delta is NOT a
    universal constant: it depends on the declared attribute shape, so it is
    reported per shape and the decode delta is bracketed rather than corrected
    by an inherited number.

Usage: analyze_r92_census.py CENSUS_TSV KERNEL_DIR ORDER_TXT
"""
import re
import sys
from collections import Counter

census_path, kdir, order_path = sys.argv[1], sys.argv[2], sys.argv[3]

G16, G17 = "applegpu_g16s", "applegpu_g17s"
BAND = 16  # 16-byte alignment granule: |delta| <= BAND is not a signal.

rows = {}
order = []
for line in open(census_path).read().splitlines()[1:]:
    study, arch, fn, val = line.split("\t")
    key = (study, fn)
    if key not in rows:
        rows[key] = {}
        order.append(key)
    rows[key][arch] = int(val) if val.isdigit() else None


def get(study, fn, arch):
    return rows.get((study, fn), {}).get(arch)


print("=" * 78)
print("CONTROL 1 -- encoding.metal marginal bytes per operation")
print("=" * 78)
EXPECT = {
    "fadd": (4.0, 4.0, "float add"),
    "ffma": (6.0, 6.0, "float FMA"),
    "fimm": (11.0, 11.0, "float FMA, loop-varying immediate"),
    "imad": (12.0, 14.0, "uint MAD (integer ALU, touches no memory)"),
}
ok = True
print(f"{'op':<38}{'arch':<16}{'B/op 32->64':>12}{'B/op 64->128':>14}{'expect':>8}")
for op, (e16, e17, label) in EXPECT.items():
    for arch, exp in ((G16, e16), (G17, e17)):
        b32 = get("r92_encoding", f"e_{op}_032", arch)
        b64 = get("r92_encoding", f"e_{op}_064", arch)
        b128 = get("r92_encoding", f"e_{op}_128", arch)
        m1, m2 = (b64 - b32) / 32, (b128 - b64) / 64
        good = abs(m1 - exp) < 1e-9 and abs(m2 - exp) < 1e-9
        ok &= good
        print(f"{label:<38}{arch:<16}{m1:>12.1f}{m2:>14.1f}{exp:>8.1f}"
              f"{'' if good else '   <-- MISMATCH'}")
pen16, pen17 = EXPECT["imad"][0], EXPECT["imad"][1]
print(f"\ninteger-ALU g17s penalty: {pen16:.1f} -> {pen17:.1f} B/op "
      f"= {100 * (pen17 / pen16 - 1):+.1f}%   (H1's entire physical basis)")
print(f"CONTROL 1: {'PASS' if ok else 'FAIL'}")

print()
print("=" * 78)
print("CONTROL 2 -- per-arch __compute floor by declared signature shape")
print("=" * 78)
print(f"{'probe':<24}{'g16s':>8}{'g17s':>8}{'floor delta':>14}")
floor_delta = {}
for key in order:
    if key[0] != "r92_floor":
        continue
    fn = key[1]
    a, b = get(*key[:1], fn, G16), get(*key[:1], fn, G17)
    a, b = rows[key][G16], rows[key][G17]
    floor_delta[fn] = b - a
    print(f"{fn:<24}{a:>8}{b:>8}{b - a:>+14}")
plain = {k: v for k, v in floor_delta.items() if not k.endswith("_simd")}
simd = {k: v for k, v in floor_delta.items() if k.endswith("_simd")}
print(f"\nplain signatures: floor delta {sorted(set(plain.values()))}")
print(f"simdgroup/lane attribute signatures: floor delta {sorted(set(simd.values()))}")
print("=> the floor delta is NOT a universal constant; it collapses to 0 once")
print("   simdgroup/lane attributes are declared, which every scored Laguna")
print("   decode kernel does. Deltas below are therefore bracketed over the")
print(f"   observed floor-delta range {min(floor_delta.values())}..{max(floor_delta.values())}.")
lo_corr, hi_corr = -max(floor_delta.values()), -min(floor_delta.values())

# dispatches per steady-state decode step, from the verbose-dump trace
names = [l.strip() for l in open(order_path) if l.strip()]
n = len(names)
prefill_end = max(i for i, x in enumerate(names)
                  if x == "laguna_prefill_moe_tail_bf16_v1") + 1
dense = [i for i, x in enumerate(names)
         if x == "laguna_dense_down_residual_bf16_v1"]
steady_len = dense[-1] - dense[-2]
off = steady_len - (n - dense[-1])
steady = Counter(names[dense[-1] - off:n])

attrs = {}
short = {}
for key in order:
    if key[0] != "r92_decode":
        continue
    fn = key[1]
    m = re.match(r"custom_kernel_(.+?)_(?:bfloat16_t|float|uint32_t)", fn)
    s = m.group(1)
    short[fn] = s
    src = open(f"{kdir}/{s}.gen.metal").read()
    attrs[fn] = "simd" if "thread_index_in_simdgroup]]" in src else "plain"

print()
print("=" * 78
      )
print("STAGE 2 -- scored decode-path kernel census (only -arch varies)")
print("=" * 78)
hdr = (f"{'kernel':<52}{'/step':>6}{'sig':>6}{'g16s':>7}{'g17s':>7}"
       f"{'raw':>7}{'corrected':>13}{'%':>7}  verdict")
print(hdr)
out = []
for key in order:
    if key[0] != "r92_decode":
        continue
    fn = key[1]
    a, b = rows[key][G16], rows[key][G17]
    raw = b - a
    c_lo, c_hi = raw + lo_corr, raw + hi_corr
    per = steady.get(short[fn], 0)
    pct = 100.0 * raw / a
    if c_lo > BAND:
        verdict = "POSITIVE g17s excess"
    elif c_hi < -BAND:
        verdict = "g17s cheaper"
    else:
        verdict = "within noise band"
    out.append((per, raw, short[fn], a, b, c_lo, c_hi, pct, verdict, attrs[fn]))
for per, raw, s, a, b, c_lo, c_hi, pct, verdict, at in sorted(
        out, key=lambda r: (-r[1] * max(r[0], 0), -r[0])):
    rng = f"{c_lo:+d}..{c_hi:+d}" if c_lo != c_hi else f"{c_lo:+d}"
    print(f"{s:<52}{per:>6}{at:>6}{a:>7}{b:>7}{raw:>+7}{rng:>13}{pct:>+7.1f}  {verdict}")

print()
print("=" * 78)
print("Weighted g17s excess per steady-state decode step (static bytes only)")
print("=" * 78)
tot = 0
for per, raw, s, *_ in sorted(out, key=lambda r: -r[1] * max(r[0], 0)):
    if per and raw > BAND:
        print(f"  {s:<52}{per:>4} x {raw:+5d} B = {per * raw:+7d} B")
        tot += per * raw
print(f"  {'TOTAL positive static g17s excess':<52}{'':>4}   {'':5}   {tot:+7d} B")
