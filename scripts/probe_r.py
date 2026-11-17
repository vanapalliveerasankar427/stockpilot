import requests, json, time
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36", "Accept": "application/json,*/*", "Referer": "https://www.nseindia.com/"})
S.get("https://www.nseindia.com/", timeout=20)
for sym in ("KALYANKJIL", "HDFCBANK", "MAXHEALTH"):
    t = time.time(); j = S.get(f"https://www.nseindia.com/api/top-corp-info?symbol={sym}&market=equities", timeout=25).json()
    print("==", sym, round(time.time()-t, 2), list(j.keys()))
    print(json.dumps(j.get("financial_results"), indent=0)[:2500])
