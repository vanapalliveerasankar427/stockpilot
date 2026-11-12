import requests, json, time
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
                  "Accept": "application/json,text/plain,*/*", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/option-chain"})
print(S.get("https://www.nseindia.com/option-chain", timeout=20).status_code)
for u in ["https://www.nseindia.com/api/option-chain-equities?symbol=RELIANCE",
          "https://www.nseindia.com/api/option-chain-contract-info?symbol=RELIANCE",
          "https://www.nseindia.com/api/option-chain-v3?type=Equity&symbol=RELIANCE",
          "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
          "https://www.nseindia.com/api/option-chain-contract-info?symbol=NIFTY"]:
    try:
        r = S.get(u, timeout=20); t = r.text
        print("==", u, r.status_code, len(t)); print(t[:700])
    except Exception as e:
        print("==", u, "ERR", e)
    time.sleep(1)
try:
    ci = S.get("https://www.nseindia.com/api/option-chain-contract-info?symbol=RELIANCE", timeout=20).json()
    ex = ci.get("expiryDates", [None])[0]; print("expiry", ex)
    r = S.get(f"https://www.nseindia.com/api/option-chain-v3?type=Equity&symbol=RELIANCE&expiry={ex}", timeout=20)
    j = r.json(); print(r.status_code, list(j.keys()), list(j.get("records", {}).keys()))
    d = j["records"]["data"]; print(len(d)); print(json.dumps(d[len(d)//2])[:1500]); print(json.dumps({k:v for k,v in j["records"].items() if k!="data"})[:500])
    print(json.dumps(j.get("filtered", {}))[:300])
except Exception as e:
    print("v3 ERR", e)
