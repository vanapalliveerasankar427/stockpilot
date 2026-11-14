import requests, re
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36", "Referer": "https://www.dpgold.com/"})
t = S.get("https://www.dpgold.com/", timeout=30).text
i = t.find("BCast"); print("CFG", t[max(0, i-1500):i+1500])
for js in ["js/LiveRates_New.js", "js/TemplateID.Chirayu.js", "js/LiveRateMessage.Chirayu.js"]:
    r = S.get("https://www.dpgold.com/" + js, timeout=30); print("== JS", js, r.status_code, len(r.text)); print(r.text[:3500])
