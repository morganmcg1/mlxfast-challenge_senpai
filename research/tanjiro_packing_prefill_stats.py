import glob
import os
import re
import statistics as st
import sys

d = sys.argv[1]
rows = []
for p in sorted(glob.glob(os.path.join(d, "*.log"))):
    b = int(os.path.basename(p)[1:3])
    lab = os.path.basename(p).split("_")[2].split(".")[0]
    m = re.search(r"prefill 512 tokens: ([0-9.]+) ms", open(p).read())
    rows.append((b, lab, float(m.group(1))))

scored = [r for r in rows if r[0] > 0]
print("warm-up discarded:", [r for r in rows if r[0] == 0])
for lab in ("0", "R"):
    v = [r[2] for r in scored if r[1] == lab]
    print("arm %s: n=%d mean=%.3f ms sd=%.3f vals=%s" % (lab, len(v), st.mean(v), st.stdev(v), v))

diffs = []
for b in sorted({r[0] for r in scored}):
    a = [r[2] for r in scored if r[0] == b and r[1] == "0"]
    c = [r[2] for r in scored if r[0] == b and r[1] == "R"]
    if a and c:
        diffs.append(st.mean(c) - st.mean(a))
        print("block %d: 0=%.3f R=%.3f diff=%+.3f" % (b, st.mean(a), st.mean(c), diffs[-1]))
print("block-paired R-0 = %+.3f ms (sd %.3f, n=%d)" % (st.mean(diffs), st.stdev(diffs), len(diffs)))

a = [r[2] for r in scored if r[1] == "0"]
c = [r[2] for r in scored if r[1] == "R"]
var = (st.variance(a) + st.variance(c)) / 2.0
pooled = var ** 0.5
se = pooled * (2.0 / len(a)) ** 0.5
delta = st.mean(c) - st.mean(a)
print("unpaired R-0 = %+.3f ms, pooled sd %.3f, se %.3f, 95%%CI +-%.3f" % (delta, pooled, se, 2.447 * se))
print("relative: %+.4f %% of prefill" % (delta / st.mean(a) * 100.0))
print("per-token: %+.3f us/token" % (delta * 1000.0 / 512.0))
