"""Final pre-close channel read, 2026-08-11 16:27Z (close is 17:00Z).

Source: one read-only `mlxfast submissions` listing, colour-stripped, 178 account rows.
This file holds the numbers verbatim so the reading survives without the terminal.

What the poll is for: at 16:06Z I published "slot FREE, bar unchanged" (manifest 10(vi)).
This re-reads the same three things 21 minutes later so the handoff's last line is not a
21-minute-old memory: (a) is anything in flight, (b) did a new adjudication land, (c) does
the bar implied by the newest rows still agree with 2.6195531094824.
"""

BAR_PUBLISHED = 2.6195531094824

# status column, 178 rows (header excluded)
STATUS_COUNTS = {"failed": 70, "rejected": 107, "promoted": 1}

# (submission, score, printed diff (RAW units), created)
NEWEST = [
    ("4be372f", 2.57671436417547, -0.042839, "8/11/26 09:20"),
    ("5fae2f1", 2.57521511377556, -0.044338, "8/11/26 12:16"),
    ("c06b1b6", 2.58896632157301, -0.030587, "8/11/26 13:51"),
]

print(__doc__)
n = sum(STATUS_COUNTS.values())
print("rows: %d  (%s)" % (n, ", ".join("%s=%d" % kv for kv in sorted(STATUS_COUNTS.items()))))
print()
print("(a) IN FLIGHT: no row carries a pending/running/queued status -> nothing of ours is")
print("    being adjudicated, so the account is not holding the slot busy at 16:27Z.")
print("(b) NEWEST ADJUDICATION: c06b1b6, created 13:51, still the newest row. The 16:06Z read")
print("    saw the same newest row, so NO new row was created in 16:06Z -> 16:27Z, by us or")
print("    on our behalf. 178 rows now vs 177 at 12:54Z = exactly the one 13:51 row.")
print("(c) ACCEPTANCES: 0. 107 rejected + 70 failed + 1 promoted (the promoted row is the")
print("    baseline 97a5090, not a win). Nobody on this account has ever cleared the bar.")
print()
print("bar implied by each of the three newest adjudicated rows (bar = score - diff):")
worst = 0.0
for sub, score, diff, when in NEWEST:
    implied = score - diff
    err = abs(implied - BAR_PUBLISHED)
    worst = max(worst, err)
    print("  %-8s %s  score %.14f  diff %+.6f  -> bar %.8f   |dev| %.2e"
          % (sub, when, score, diff, implied, err))
print()
print("published bar                       %.13f" % BAR_PUBLISHED)
print("worst deviation of the three reads  %.2e  (diff is printed to 6 dp, so +/-5e-7 is" % worst)
print("                                    pure print rounding: this is agreement, not drift)")
spread = max(s - d for _, s, d, _ in NEWEST) - min(s - d for _, s, d, _ in NEWEST)
print("spread across the three reads       %.2e" % spread)
print()
print("CONCLUSION at 16:27Z: slot FREE, bar UNCHANGED at 2.6195531094824 across 09:20->13:51,")
print("no acceptance on the account, nothing in flight. Same verdict as 16:06Z, 21 min fresher.")
print()
print("THE ONE CAVEAT, unchanged (rule 23, and manifest 10(vi)): this bar is derived from the")
print("`diff` column of OUR rows, so it is only as fresh as the newest ADJUDICATION -- 13:51Z.")
print("A competitor could have taken the crown at 14:00Z and this listing would look identical.")
print("What the poll does prove is the half that matters for firing: our slot is free now.")
