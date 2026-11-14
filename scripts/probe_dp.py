import requests, re
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36"})
for u in ["https://www.dpgold.com/", "https://dpgold.com/"]:
    try:
        r = S.get(u, timeout=30); t = r.text
        print("==", u, r.status_code, r.url, len(t))
        print("SCRIPTS", re.findall(r'<script[^>]+src="([^"]+)"', t)[:40])
        print("URLS", sorted(set(re.findall(r'(?:https?:)?//[\w.-]+(?::\d+)?/[^\s"\'<>)]*', t)))[:80])
        for m in re.finditer(r'(?i)(socket|bcast|broadcast|rate|liverate|signalr|\.ashx|\.php|api)[^\n]{0,160}', t):
            print("HIT", m.group(0)[:200])
        print(t[:3000])
        break
    except Exception as e:
        print(u, "ERR", e)
