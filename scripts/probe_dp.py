import requests
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36", "Referer": "https://www.dpgold.com/", "Origin": "https://www.dpgold.com"})
for t in ("dpgold", "dpgoldcoins"):
    for host in ("statewisebcast.dpgold.in", "bcast.dpgold.co.in"):
        u = f"https://{host}:7768/VOTSBroadcastStreaming/Services/xml/GetLiveRateByTemplateID/{t}"
        try:
            r = S.get(u, timeout=20); print("==", u, r.status_code, len(r.text), dict((k, v) for k, v in r.headers.items() if k.lower().startswith("access-control")))
            print(r.text[:2500].replace("\t", " | "))
        except Exception as e:
            print("==", u, "ERR", e)
r = S.get("https://www.dpgold.com/js/LiveRates_New.js", timeout=30).text
i = r.find("function OnSuccess1"); print("== FN"); print(r[i:i+9000])
