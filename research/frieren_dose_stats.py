"""Drift-cancelled contrasts for the position-balanced sub-layer rung dose screen.

Positions 1..9 = off, ab, abc, abc, off, ab, ab, abc, off; each level's positions
sum to 15, so a linear position/drift trend cancels exactly.
"""

import statistics as s

ARMS = {
    "off": [8.9961, 9.1119, 9.0951],
    "ab": [9.0729, 9.0260, 9.0605],
    "abc": [9.2404, 9.2511, 9.2353],
}

for name, vals in ARMS.items():
    m = s.mean(vals)
    se = s.stdev(vals) / len(vals) ** 0.5
    print(f"{name:4s} mean={m:.4f} sd={s.stdev(vals):.4f} se={se:.4f} ({100*se/m:.3f} pct)")

base = s.mean(ARMS["off"])
se_base = s.stdev(ARMS["off"]) / 3 ** 0.5
print()
for name in ("ab", "abc"):
    m = s.mean(ARMS[name])
    se = s.stdev(ARMS[name]) / 3 ** 0.5
    d = m - base
    sed = (se_base ** 2 + se ** 2) ** 0.5
    print(
        f"{name:4s} vs off: {d:+.4f} ms ({100*d/base:+.3f} pct) "
        f"+/- {100*sed/base:.3f} pct  t={d/sed:+.2f}"
    )

warm = s.mean(ARMS["off"][1:])
print()
print(f"dropping cold position-1 off arm: off={warm:.4f}")
for name in ("ab", "abc"):
    print(f"  {name:4s} {100*(s.mean(ARMS[name])-warm)/warm:+.3f} pct")
