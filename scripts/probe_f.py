import json, sys, time
sys.path.insert(0, "scripts")
import update as U
out = json.load(open("data/live.json"))
t = time.time(); U.fno_results(out); print("took", round(time.time() - t, 1))
s = out["fres"]["s"]; print("stored", len(s))
from collections import Counter; print(Counter(v.get("v") for v in s.values()))
for k in list(s)[:8]: print(k, s[k])
fresh = sorted(((v.get("ts") or 0, k, v) for k, v in s.items()), reverse=True)[:8]
for ts, k, v in fresh: print("recent", k, time.strftime("%d %b %H:%M", time.gmtime(ts + 19800)) if ts else None, v.get("v"), v.get("yp"), v.get("yi"))
print(U.LOG[-3:])
