import requests, io, zipfile, csv
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36", "Referer": "https://www.nseindia.com/"})
for d in ("20261112", "20261111"):
    for u in (f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d}_F_0000.csv.zip",):
        try:
            r = S.get(u, timeout=30); print(u, r.status_code, len(r.content))
            if r.ok:
                z = zipfile.ZipFile(io.BytesIO(r.content)); n = z.namelist()[0]; t = z.read(n).decode()
                L = t.splitlines(); print(n, len(L)); print(L[0]); [print(x) for x in L[1:4]]
                rows = list(csv.DictReader(io.StringIO(t)))
                print([x for x in rows if x.get("TckrSymb") == "RELIANCE" and x.get("OptnTp") == "CE"][:2])
                import collections; print(collections.Counter(x.get("FinInstrmTp") for x in rows))
        except Exception as e:
            print(u, "ERR", e)
