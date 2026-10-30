#!/usr/bin/env python3
"""MarketVedaPro daily history job.

After the close, collects for every listed stock:
  * 2 years of daily closing prices (for the in-site chart)
  * quarterly and annual revenue, net profit and EPS, plus sector, industry and website
    (refreshed in rolling batches so each stock is updated about once a week)
Writes one small file per stock to hist/h/<key>.json and an index hist/profiles.json,
published to the repository's "hist" branch.
"""
import datetime as dt
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "hist")
H = os.path.join(OUT, "h")
RAW = "https://raw.githubusercontent.com/vanapalliveerasankar427/stockpilot/"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
NOW = dt.datetime.now(IST)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
S = requests.Session()
S.headers.update(UA)
BATCH = int(os.environ.get("FUND_BATCH", "6000"))
BSEH = {}
stats = {"chart_ok": 0, "chart_fail": 0, "fund_ok": 0, "fund_fail": 0, "prof_ok": 0}


def get(url, **kw):
    for attempt in range(4):
        r = S.get(url, timeout=25, **kw)
        if r.status_code == 429:
            time.sleep(4 * (attempt + 1) + random.random() * 3)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()


def crumb():
    S.get("https://fc.yahoo.com", timeout=20)
    c = S.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=20).text.strip()
    if not c or "<" in c:
        raise RuntimeError("no crumb")
    return c


def chart(ysym):
    j = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(ysym)}", params={"range": "2y", "interval": "1d"}).json()
    r = j["chart"]["result"][0]
    ts, cl = r.get("timestamp") or [], r["indicators"]["quote"][0].get("close") or []
    pts = [(t, c) for t, c in zip(ts, cl) if c]
    if len(pts) < 5:
        return None
    d0 = pts[0][0] // 86400
    return {"d0": d0, "d": [t // 86400 - d0 for t, _ in pts], "c": [round(c, 2) for _, c in pts]}


def intraday(ysym):
    j = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(ysym)}", params={"range": "5d", "interval": "15m"}).json()
    r = j["chart"]["result"][0]
    ts, cl = r.get("timestamp") or [], r["indicators"]["quote"][0].get("close") or []
    pts = [(t, c) for t, c in zip(ts, cl) if c]
    if len(pts) < 5:
        return None
    t0 = pts[0][0]
    return {"t0": t0, "t": [(t - t0) // 60 for t, _ in pts], "c": [round(c, 2) for _, c in pts]}


# BSE-only scrips: Yahoo has little history for them, so build it from BSE's own daily price files
def bse_closes(keys):
    path = os.path.join(OUT, "bse_closes.json")
    try:
        store = json.load(open(path))
    except Exception:
        store = {}
    codes = {k[1:] for k in keys}
    day = NOW.date()
    fetched = 0
    days = [day - dt.timedelta(days=b) for b in range(0, 380)]
    days = [d for d in days if d.weekday() < 5 and d.isoformat() not in store and not (d == day and NOW.hour < 19)]

    def one(d):
        url = f"https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV"
        try:
            r = S.get(url, timeout=25, headers={"Referer": "https://www.bseindia.com/"})
            if r.status_code != 200 or "FinInstrmId" not in r.text[:400]:
                return d, {}
            lines = [l.split(",") for l in r.text.strip().splitlines()]
            h = lines[0]
            ci, cc = h.index("FinInstrmId"), h.index("ClsPric")
            return d, {x[ci]: float(x[cc]) for x in lines[1:] if len(x) > cc and x[ci] in codes and x[cc]}
        except Exception:
            return d, None
    with ThreadPoolExecutor(max_workers=8) as ex:
        for d, v in ex.map(one, days):
            if v is not None:
                store[d.isoformat()] = v
                fetched += bool(v)
    keep = sorted(store)[-300:]
    store = {k: store[k] for k in keep}
    json.dump(store, open(path, "w"), separators=(",", ":"))
    print("bse files fetched:", fetched, "days stored:", len(store))
    series = {}
    for d in sorted(store):
        di = dt.date.fromisoformat(d).toordinal() - dt.date(1970, 1, 1).toordinal()
        for code, c in store[d].items():
            series.setdefault("B" + code, []).append((di, c))
    out = {}
    for k, pts in series.items():
        if len(pts) >= 5:
            d0 = pts[0][0]
            out[k] = {"d0": d0, "d": [x - d0 for x, _ in pts], "c": [round(c, 2) for _, c in pts], "src": "BSE"}
    return out


FUND_TYPES = ["quarterlyTotalRevenue", "quarterlyNetIncome", "quarterlyBasicEPS", "annualTotalRevenue", "annualNetIncome", "annualBasicEPS"]


def fundamentals(ysym):
    p2 = int(time.time())
    j = get(f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{requests.utils.quote(ysym)}",
            params={"type": ",".join(FUND_TYPES), "period1": p2 - 6 * 365 * 86400, "period2": p2, "merge": "false"}).json()
    f = {}
    for res in j.get("timeseries", {}).get("result", []):
        typ = (res.get("meta", {}).get("type") or [None])[0]
        rows = res.get(typ) or []
        vals = [[x["asOfDate"], x["reportedValue"]["raw"]] for x in rows if x and x.get("reportedValue")]
        if vals:
            div = 1 if "EPS" in typ else 1e7  # rupees -> crore
            f[typ] = [[d, round(v / div, 2)] for d, v in vals][-8:]
    return f or None


def profile(ysym, cr):
    j = get(f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{requests.utils.quote(ysym)}",
            params={"modules": "assetProfile", "crumb": cr}).json()
    p = (j.get("quoteSummary", {}).get("result") or [{}])[0].get("assetProfile") or {}
    out = {k: p.get(k) for k in ("sector", "industry", "website", "fullTimeEmployees", "city") if p.get(k)}
    if out.get("website"):
        out["website"] = out["website"].replace("http://", "https://")
    return out


def main():
    os.makedirs(H, exist_ok=True)
    uni = get(RAW + "data/universe.json").json()["s"]
    try:  # the workflow checks out the previous "hist" branch into ./hist
        old_prof = json.load(open(os.path.join(OUT, "profiles.json")))
    except Exception:
        old_prof = {}
    prof = dict(old_prof.get("p", {}))
    fund_day = dict(old_prof.get("fd", {}))

    def old_file(key):
        try:
            return json.load(open(os.path.join(H, key.replace("/", "_") + ".json")))
        except Exception:
            return {}

    global BSEH
    BSEH = bse_closes([r[0] for r in uni if r[2] == "BSE"])
    # rolling batch for fundamentals/profile: never-done first, then oldest
    try:  # biggest companies first among those never done
        qq = get(RAW + "data/quotes.json").json()
        mcap = {k: (v[9] or 0) for k, v in qq["q"].items()}
    except Exception:
        mcap = {}
    order = sorted(uni, key=lambda r: (fund_day.get(r[0], "0000"), -mcap.get(r[0], 0)))
    due = {r[0] for r in order[:BATCH]}
    try:
        cr = crumb()
    except Exception as e:
        print("crumb failed:", e)
        cr = None

    def work(r):
        key, ysym = r[0], r[3]
        rec = {}
        try:
            c = chart(ysym)
            if c:
                rec["p"] = c
                stats["chart_ok"] += 1
            else:
                stats["chart_fail"] += 1
        except Exception:
            stats["chart_fail"] += 1
        if "p" not in rec and key in BSEH:
            rec["p"] = BSEH[key]
            stats["bse_hist"] = stats.get("bse_hist", 0) + 1
        try:
            it = intraday(ysym)
            if it:
                rec["i"] = it
        except Exception:
            pass
        if key in due:
            try:
                f = fundamentals(ysym)
                if f:
                    rec["f"] = f
                    stats["fund_ok"] += 1
                fund_day[key] = NOW.strftime("%Y-%m-%d")
            except Exception:
                stats["fund_fail"] += 1
            if cr:
                try:
                    pr = profile(ysym, cr)
                    if pr:
                        prof[key] = pr
                        stats["prof_ok"] += 1
                except Exception:
                    pass
        else:
            o = old_file(key)
            if o.get("f"):
                rec["f"] = o["f"]
        if key in prof:
            rec["a"] = prof[key]
        if rec:
            rec["u"] = NOW.strftime("%-d %b %Y")
            with open(os.path.join(H, key.replace("/", "_") + ".json"), "w") as fh:
                json.dump(rec, fh, separators=(",", ":"))

    with ThreadPoolExecutor(max_workers=int(os.environ.get("WORKERS", "32"))) as ex:
        list(ex.map(work, uni))
    # small index for logos and sector tags across the site
    idx = {k: {"w": v.get("website", "").split("//")[-1].split("/")[0].removeprefix("www."), "s": v.get("sector", ""), "i": v.get("industry", "")}
           for k, v in prof.items() if v}
    json.dump({"updated": NOW.isoformat(timespec="seconds"), "p": prof, "fd": fund_day, "logo": {k: v["w"] for k, v in idx.items() if v["w"]},
               "sec": {k: [v["s"], v["i"]] for k, v in idx.items() if v["s"]}},
              open(os.path.join(OUT, "profiles.json"), "w"), separators=(",", ":"))
    print(json.dumps(stats), "files:", len(os.listdir(H)))


if __name__ == "__main__":
    sys.exit(main())
