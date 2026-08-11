"""Extract the last senpai-result:v1 summary for a given PR from the get_prs artifact."""
import json
import re
import sys

PATH = ("/Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/advisor/"
        "state/openhands_state/github/pull-requests-7f745577aa5bd713b977.md")

want = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 3000

text = open(PATH).read()
blocks = re.findall(r"<!-- senpai-result:v1 (\{.*?\}) -->", text, re.S)
hits = []
for b in blocks:
    try:
        d = json.loads(b)
    except Exception:
        continue
    if str(d["assignment"]["pr_number"]) == want:
        hits.append(d)

print(f"PR #{want}: {len(hits)} result block(s)")
for d in hits[-1:]:
    print("status:", d.get("status"), " commit:", d.get("commit_sha"))
    print("metric:", json.dumps(d.get("primary_metric")))
    print("runs:", [r.get("run_id") for r in d.get("runs", [])])
    print("---SUMMARY---")
    print(d.get("summary", "")[:limit])
