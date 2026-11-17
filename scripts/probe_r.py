import requests, json, time
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36", "Accept": "application/json,*/*", "Referer": "https://www.nseindia.com/"})
S.get("https://www.nseindia.com/companies-listing/corporate-filings-financial-results", timeout=20)
for u in ["https://www.nseindia.com/api/results-comparision?symbol=KALYANKJIL",
          "https://www.nseindia.com/api/results-comparision?index=equities&symbol=MAXHEALTH",
          "https://www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly",
          "https://www.nseindia.com/api/top-corp-info?symbol=KALYANKJIL&market=equities"]:
    try:
        r = S.get(u, timeout=25); print("==", u, r.status_code, len(r.text)); print(r.text[:2500])
    except Exception as e:
        print("==", u, "ERR", e)
    time.sleep(1)
