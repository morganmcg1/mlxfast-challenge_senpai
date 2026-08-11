#!/usr/bin/env python3
"""Final bar re-read, 2026-08-11 16:06Z, from a live `mlxfast submissions` poll.

Method (fern #745 / manifest 6.7, extended by me at 15:53Z): the CLI `diff` column is
    diff = score - bar_at_adjudication
in RAW score units (the printed percent is a units bug: |diff| / 1.003405).  So EVERY
terminal row is a timestamped bar reading, and a set of rows is a set of *independent*
readings of the bar at different instants.

At 15:53Z I used two rows.  The 16:06Z poll lets me use six, which is what turns
"the bar has not moved" from an assertion into a measurement with a resolution attached.

Print resolution: diff is printed to 6 decimals, so each implied bar carries +/-5e-7.
Rule 20: never compare implied bars at finer precision than that.
"""

PRINT_RES = 5e-7  # half of the last printed digit of `diff`
BAR_0934Z = 2.6195531094824  # set by ggu77wt 09:34:06Z 8/11 (independent source)
BAR_0810 = 2.6165037         # the previous era's bar, from e27f1ce at 15:53Z

# (label, score, diff as printed, fire time UTC) -- from the 16:06Z poll
ROWS = [
    ("e27f1ce", 2.60664969895906, -0.009854, "08-10 08:18Z"),
    ("3275a9b", 2.56700577278022, -0.049498, "08-11 07:01Z"),
    ("f2b2345", 2.59327989948884, -0.023224, "08-11 07:26Z"),
    ("7eca997", 2.57667619821086, -0.039827, "08-11 07:57Z"),
    ("4be372f", 2.57671436417547, -0.042839, "08-11 09:20Z"),
    ("5fae2f1", 2.57521511377556, -0.044338, "08-11 12:16Z"),
    ("c06b1b6", 2.58896632157301, -0.030587, "08-11 13:51Z"),
]

print("=" * 78)
print("FINAL BAR RE-READ  (live poll 2026-08-11 16:06Z, 7 terminal rows)")
print("=" * 78)
print(f"{'row':10s} {'fired':14s} {'score':18s} {'diff':11s} {'implied bar':16s} era")
old, new = [], []
for label, score, diff, t in ROWS:
    bar = score - diff
    era = "pre-09:34" if bar < 2.618 else "CURRENT"
    (old if bar < 2.618 else new).append(bar)
    print(f"{label:10s} {t:14s} {score:<18.14f} {diff:+.6f}  {bar:<16.8f} {era}")

print("\n--- current-era readings (the only ones that price a fire today) ---")
print(f"n = {len(new)}, spanning fires 09:20Z -> 13:51Z")
print(f"  min {min(new):.8f}   max {max(new):.8f}   spread {max(new)-min(new):.2e}")
print(f"  independent value (ggu77wt 09:34:06Z): {BAR_0934Z:.13f}")
print(f"  max |reading - independent| = {max(abs(b-BAR_0934Z) for b in new):.2e}")
ok = (max(new) - min(new)) <= 2 * PRINT_RES
print(f"  spread within +/-{PRINT_RES:.0e} print resolution? {'YES' if ok else 'NO'}")

print("\n--- era step (a real bar move, for contrast with 'no move') ---")
print(f"  pre-09:34 readings: n={len(old)}, mean {sum(old)/len(old):.8f} (cf. {BAR_0810})")
step = sum(new)/len(new) - sum(old)/len(old)
print(f"  step at 09:34:06Z = {step:+.8f} raw = {step/(sum(old)/len(old))*100:+.4f} %")
print("  ^ THIS is what a competitor advance looks like in this instrument:")
print("    ~3.0e-3 raw, i.e. ~6000x the print resolution.  It is unmissable.")

print("\n--- VERDICT ---")
print("Bar UNCHANGED across three independent readings spanning 09:20Z -> 13:51Z fires.")
print("No competitor advance has been adjudicated in that window.")
print("Newest terminal row is still c06b1b6 (fired 13:51Z): the slot has been FREE")
print("since its adjudication, and NO new row exists on this account at 16:06Z.")
print("Caveat (rule 20): the newest reading is only as fresh as the newest ADJUDICATION.")
print("A bar move after c06b1b6 cleared would not yet be visible here.")
