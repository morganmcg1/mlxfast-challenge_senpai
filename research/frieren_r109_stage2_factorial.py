"""Paired within-block factorial contrasts for the R109-A Stage-2 2x2x2 study.

Every contrast is formed inside a block, so it inherits the ABBA pairing of the
driver and is immune to the +-1.4-2.2 % between-run absolute drift of this host.
Sign convention: positive us/step = the SECOND named cell is slower.
"""

import json
import sys

import numpy as np

PATH = sys.argv[1] if len(sys.argv) > 1 else "research/r109-cadence/stage2/results.jsonl"

rows = [json.loads(l) for l in open(PATH) if l.strip()]
blk: dict[int, dict[str, float]] = {}
for r in rows:
    blk.setdefault(r["block"], {})[r["arm"]] = r["decode_spt"] * 1e6
blocks = sorted(blk)

T95 = {3: 3.182, 4: 2.353, 5: 2.132, 6: 2.015, 7: 1.943, 8: 1.895}[len(blocks) - 1]


def d(a: str, b: str) -> np.ndarray:
    return np.array([blk[k][b] - blk[k][a] for k in blocks])


def rep(name: str, v: np.ndarray) -> None:
    m = v.mean()
    sem = v.std(ddof=1) / np.sqrt(len(v))
    lo, hi = m - T95 * sem, m + T95 * sem
    verdict = "EXCLUDES 0" if lo * hi > 0 else "spans 0"
    print(
        f"{name:41s} {m:+9.1f} +-{sem:6.1f} us  t={m/sem:+6.2f}  "
        f"ci95=[{lo:+8.1f},{hi:+8.1f}]  {verdict}"
    )


print(f"blocks={blocks}  sign: positive us/step = SECOND cell slower\n")
print("-- cadence at:0,7 vs compiled mask, within each (BFS, CB) cell --")
rep("cadence | w50 cb200  (RANKED CELL)", d("c_w50_cb200", "a_w50_cb200"))
rep("cadence | w20 cb200", d("c_w20_cb200", "a_w20_cb200"))
rep("cadence | w50 cb64", d("c_w50_cb64", "a_w50_cb64"))
rep("cadence | w20 cb64", d("c_w20_cb64", "a_w20_cb64"))

print("\n-- MLX_BFS_MAX_WIDTH 50 -> 20, compiled cadence --")
rep("BFS 50->20 | cb200  (RANKED CELL)", d("c_w50_cb200", "c_w20_cb200"))
rep("BFS 50->20 | cb64", d("c_w50_cb64", "c_w20_cb64"))

print("\n-- command-buffer caps 200/200 -> 64/128, compiled cadence --")
rep("CB 200->64 | w50  (RANKED CELL)", d("c_w50_cb200", "c_w50_cb64"))
rep("CB 200->64 | w20", d("c_w20_cb200", "c_w20_cb64"))

print("\n-- the attribution contrast --")
cad200 = (d("c_w50_cb200", "a_w50_cb200") + d("c_w20_cb200", "a_w20_cb200")) / 2
cad64 = (d("c_w50_cb64", "a_w50_cb64") + d("c_w20_cb64", "a_w20_cb64")) / 2
bfsc = (d("c_w50_cb200", "c_w20_cb200") + d("a_w50_cb200", "a_w20_cb200")) / 2
bfs64 = (d("c_w50_cb64", "c_w20_cb64") + d("a_w50_cb64", "a_w20_cb64")) / 2
rep("cadence x CB   (cadence@200 - cadence@64)", cad200 - cad64)
rep("cadence x BFS  (cadence@w50 - cadence@w20)", (d("c_w50_cb200", "a_w50_cb200") + d("c_w50_cb64", "a_w50_cb64")) / 2 - (d("c_w20_cb200", "a_w20_cb200") + d("c_w20_cb64", "a_w20_cb64")) / 2)
rep("BFS x CB       (BFS@200 - BFS@64)", bfsc - bfs64)

print("\n-- every cell vs the shipped ranked configuration c_w50_cb200 --")
for arm in sorted(blk[blocks[0]]):
    if arm != "c_w50_cb200":
        rep(f"shipped -> {arm}", d("c_w50_cb200", arm))
