import json, os, sys, time
sys.path.insert(0, "scripts")
import update as U
out = {}
U.fno(out)
print("fno syms", len((out.get("fno") or {}).get("syms") or {}))
t = time.time(); U.option_chains(out); print("took", round(time.time() - t, 1))
oc = json.load(open(os.path.join(U.OUT_EXTRA, "oc.json")))
print("stored", len(oc["s"]), "ilot", oc.get("ilot"), list(oc["s"])[:10])
for k in ("NIFTY", "RELIANCE"):
    e = oc["s"].get(k)
    if e: print(k, json.dumps({x: e[x] for x in e if x != "r"}), e["r"][7:10])
print(U.LOG[-5:]); print("size", os.path.getsize(os.path.join(U.OUT_EXTRA, "oc.json")))
