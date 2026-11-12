"""Daily closing prices for every option contract (nearest expiries) from NSE's F&O bhavcopy.

Writes opt/o/<SYMBOL>.json for the "opt" branch:
  {"u": "13 Nov 2026", "d": [epoch-day, ...], "x": {"2026-11-23": {"1060C": [close|null, ...], ...}, ...}}
Prices line up with "d" (null = no trade data that day). Used for the per-strike price charts."""
import csv, datetime as dt, io, json, os, sys, zipfile
from concurrent.futures import ThreadPoolExecutor
import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
NOW = dt.datetime.now(IST)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "opt", "o")
DAYS = 45          # trading days kept (about two months)
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36", "Referer": "https://www.nseindia.com/"})


def day_file(d):
    u = f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
    for _ in range(3):
        try:
            r = S.get(u, timeout=40)
            if r.status_code == 404:
                return d, None
            r.raise_for_status()
            z = zipfile.ZipFile(io.BytesIO(r.content))
            return d, z.read(z.namelist()[0]).decode("utf-8", "replace")
        except Exception:
            continue
    return d, None


def main():
    os.makedirs(OUT, exist_ok=True)
    cands = [(NOW - dt.timedelta(days=i)).date() for i in range(0, 75)]
    cands = [d for d in cands if d.weekday() < 5]
    with ThreadPoolExecutor(8) as ex:
        got = [x for x in ex.map(day_file, cands) if x[1]]
    got.sort()
    got = got[-DAYS:]
    if not got:
        print("no bhavcopy files")
        return 1
    days = [d for d, _ in got]
    latest = got[-1][1]
    # contracts to keep: the two nearest expiries per symbol (three for index weeklies), strikes within 30% of the price
    keep, und = {}, {}
    for r in csv.DictReader(io.StringIO(latest)):
        if r["FinInstrmTp"] not in ("STO", "IDO") or r["OptnTp"] not in ("CE", "PE"):
            continue
        sy = r["TckrSymb"]
        und[sy] = float(r["UndrlygPric"] or 0)
        keep.setdefault(sy, set()).add(r["XpryDt"])
    for sy in keep:
        keep[sy] = set(sorted(keep[sy])[:3 if sy in ("NIFTY", "BANKNIFTY") else 2])
    ix = {d: i for i, d in enumerate(days)}
    data = {}
    for d, txt in got:
        i = ix[d]
        for r in csv.DictReader(io.StringIO(txt)):
            if r["FinInstrmTp"] not in ("STO", "IDO") or r["OptnTp"] not in ("CE", "PE"):
                continue
            sy, ex = r["TckrSymb"], r["XpryDt"]
            if ex not in keep.get(sy, ()):
                continue
            k = float(r["StrkPric"])
            u = und.get(sy) or 0
            if u and abs(k / u - 1) > 0.3:
                continue
            c = float(r["ClsPric"] or 0)
            traded = float(r["TtlTradgVol"] or 0) > 0 or float(r["OpnIntrst"] or 0) > 0
            if not c or not traded:
                continue
            key = (f"{k:g}") + r["OptnTp"][0]
            data.setdefault(sy, {}).setdefault(ex, {}).setdefault(key, [None] * len(days))[i] = round(c, 2)
    ep = [int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() // 86400) for d in days]
    n = 0
    for sy, exs in data.items():
        json.dump({"u": days[-1].strftime("%-d %b %Y"), "d": ep, "x": exs}, open(os.path.join(OUT, sy.replace("&", "_") + ".json"), "w"), separators=(",", ":"))
        n += 1
    print(f"{len(days)} trading days ({days[0]} to {days[-1]}), {n} symbols")


if __name__ == "__main__":
    sys.exit(main())
