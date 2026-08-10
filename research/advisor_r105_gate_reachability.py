import re, subprocess, os
root = "/Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/advisor/workspace/target"
files = subprocess.check_output(
    ["find", os.path.join(root, "Sources"), os.path.join(root, "Vendor"),
     "-name", "*.swift"]).decode().split()
pat = re.compile(r'environment\[\s*"([A-Z0-9_]+)"\s*\]\s*(!=|==)\s*"([^"]*)"', re.S)
on, off, other = {}, {}, {}
for f in files:
    try:
        s = open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    rel = os.path.relpath(f, root)
    for m in pat.finditer(s):
        name, op, val = m.group(1), m.group(2), m.group(3)
        line = s[:m.start()].count("\n") + 1
        key = (name,)
        if op == "!=" and val == "0":
            on.setdefault(name, []).append(f"{rel}:{line}")
        elif op == "==" and val == "1":
            off.setdefault(name, []).append(f"{rel}:{line}")
        else:
            other.setdefault(name, []).append(f"{rel}:{line} ({op}\"{val}\")")
print("default-ON  (!= \"0\") distinct names:", len(on), " sites:", sum(len(v) for v in on.values()))
print("default-OFF (== \"1\") distinct names:", len(off), " sites:", sum(len(v) for v in off.values()))
print("other comparisons distinct names:", len(other), " sites:", sum(len(v) for v in other.values()))
src = sum(1 for n, v in on.items() if any(x.startswith("Sources/") for x in v))
ven = sum(1 for n, v in on.items() if any(x.startswith("Vendor/") for x in v))
print("  default-ON names with a Sources/ site:", src, " with a Vendor/ site:", ven)
print()
print("=== default-ON gate names (sorted) ===")
for n in sorted(on):
    print(f"  {n:52s} {on[n][0]}")
