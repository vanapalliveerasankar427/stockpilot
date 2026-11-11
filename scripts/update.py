#!/usr/bin/env python3
"""MarketVedaPro data updater.

Runs on GitHub Actions on a schedule. Collects fresh market figures from public
sources and writes data/live.json and data/live.js, which index.html loads.
Every source is independent: if one fails, the previous good values are kept.
"""
import datetime as dt
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests









ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
NOW = dt.datetime.now(IST)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "en-IN,en;q=0.9"}
S = requests.Session()
S.headers.update(UA)
LOG = []


def log(msg):
    LOG.append(msg)
    print(msg, flush=True)


def get(url, **kw):
    r = S.get(url, timeout=25, **kw)
    r.raise_for_status()
    return r


def num(s):
    return float(str(s).replace(",", "").replace("₹", "").strip())


def text_of(h):
    return html.unescape(re.sub(r"<[^>]+>", " ", h)).replace("\xa0", " ")


# ----------------------------------------------------------------- Yahoo Finance
def yahoo(sym, rng="5d", interval="1d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(sym)}"
    j = get(url, params={"range": rng, "interval": interval}).json()
    return j["chart"]["result"][0]


def quote(sym):
    r = yahoo(sym, "1d", "5m")
    m = r["meta"]
    v = m["regularMarketPrice"]
    prev = m.get("chartPreviousClose") or m.get("previousClose")
    q = r.get("indicators", {}).get("quote", [{}])[0]
    opens = [x for x in (q.get("open") or []) if x]
    out = {"v": round(v, 2), "prev": round(prev, 2), "ch": round(v - prev, 2),
           "pct": round((v / prev - 1) * 100, 2),
           "high": round(m.get("regularMarketDayHigh") or v, 2),
           "low": round(m.get("regularMarketDayLow") or v, 2),
           "open": round(opens[0], 2) if opens else None,
           "t": m.get("regularMarketTime")}
    return out


# Official closes for the day before this updater started keeping its own record
EOD_SEED = {"2026-10-29": {"NIFTY": 22936.75, "SENSEX": 74151.04, "BANKNIFTY": 54909.65, "MIDCAP": 57841.65,
                           "SMALLCAP": 18811.35, "VIX": 15.11}}
INDICES = {"NIFTY": "^NSEI", "SENSEX": "^BSESN", "BANKNIFTY": "^NSEBANK",
           "MIDCAP": "NIFTY_MIDCAP_100.NS", "SMALLCAP": "^CNXSC", "VIX": "^INDIAVIX"}
SECTORS = [("Bank", "^NSEBANK"), ("IT", "^CNXIT"), ("FMCG", "^CNXFMCG"), ("Auto", "^CNXAUTO"),
           ("Pharma", "^CNXPHARMA"), ("Metal", "^CNXMETAL"), ("Realty", "^CNXREALTY"),
           ("Energy", "^CNXENERGY"), ("PSU Bank", "^CNXPSUBANK"), ("Fin. Services", "NIFTY_FIN_SERVICE.NS"),
           ("Media", "^CNXMEDIA"), ("Infra", "^CNXINFRA")]
# The 25 stocks on the Stocks page (site symbol -> Yahoo symbol)
STOCKS = {"RELIANCE": "RELIANCE.NS", "BHARTIARTL": "BHARTIARTL.NS", "HDFCBANK": "HDFCBANK.NS",
          "ICICIBANK": "ICICIBANK.NS", "TCS": "TCS.NS", "SBIN": "SBIN.NS", "BAJFINANCE": "BAJFINANCE.NS",
          "LT": "LT.NS", "INFY": "INFY.NS", "KOTAKBANK": "KOTAKBANK.NS", "HINDUNILVR": "HINDUNILVR.NS",
          "ADANIPORTS": "ADANIPORTS.NS", "SUNPHARMA": "SUNPHARMA.NS", "TITAN": "TITAN.NS",
          "AXISBANK": "AXISBANK.NS", "HCLTECH": "HCLTECH.NS", "MARUTI": "MARUTI.NS", "MM": "M&M.NS",
          "ADANIENT": "ADANIENT.NS", "ITC": "ITC.NS", "ULTRACEMCO": "ULTRACEMCO.NS",
          "ETERNAL": "ETERNAL.NS", "JSWSTEEL": "JSWSTEEL.NS", "NTPC": "NTPC.NS", "BAJAJ-AUTO": "BAJAJ-AUTO.NS"}
EXTRA_LARGE = {"POWERGRID": "Power Grid", "ONGC": "ONGC", "COALINDIA": "Coal India", "TATASTEEL": "Tata Steel",
               "HINDALCO": "Hindalco", "GRASIM": "Grasim", "ASIANPAINT": "Asian Paints", "NESTLEIND": "Nestle India",
               "CIPLA": "Cipla", "DRREDDY": "Dr Reddy's", "APOLLOHOSP": "Apollo Hospitals", "WIPRO": "Wipro",
               "TECHM": "Tech Mahindra", "SBILIFE": "SBI Life", "HDFCLIFE": "HDFC Life", "BAJAJFINSV": "Bajaj Finserv",
               "SHRIRAMFIN": "Shriram Finance", "EICHERMOT": "Eicher Motors", "HEROMOTOCO": "Hero MotoCorp",
               "TRENT": "Trent", "BEL": "Bharat Electronics", "TATACONSUM": "Tata Consumer", "JIOFIN": "Jio Financial",
               "INDUSINDBK": "IndusInd Bank"}
NAMES = {"RELIANCE": "Reliance Industries", "BHARTIARTL": "Bharti Airtel", "HDFCBANK": "HDFC Bank",
         "ICICIBANK": "ICICI Bank", "TCS": "TCS", "SBIN": "State Bank of India", "BAJFINANCE": "Bajaj Finance",
         "LT": "Larsen & Toubro", "INFY": "Infosys", "KOTAKBANK": "Kotak Mahindra Bank",
         "HINDUNILVR": "Hindustan Unilever", "ADANIPORTS": "Adani Ports", "SUNPHARMA": "Sun Pharma",
         "TITAN": "Titan", "AXISBANK": "Axis Bank", "HCLTECH": "HCL Tech", "MARUTI": "Maruti Suzuki",
         "MM": "Mahindra & Mahindra", "ADANIENT": "Adani Enterprises", "ITC": "ITC", "ULTRACEMCO": "UltraTech Cement",
         "ETERNAL": "Eternal", "JSWSTEEL": "JSW Steel", "NTPC": "NTPC", "BAJAJ-AUTO": "Bajaj Auto"}


def quotes(symbols):
    """Fetch many Yahoo quotes in parallel. Returns {symbol: quote}."""
    def one(sym):
        try:
            return sym, quote(sym)
        except Exception as e:
            log(f"quote {sym} failed: {e}")
            return sym, None
    with ThreadPoolExecutor(max_workers=16) as ex:
        return {s: q for s, q in ex.map(one, symbols) if q}


def markets(out):
    syms = list(INDICES.values()) + [s for _, s in SECTORS] + list(STOCKS.values()) + \
        [k + ".NS" for k in EXTRA_LARGE] + ["INR=X", "BZ=F", "GC=F", "^DJI", "^GSPC", "^IXIC", "^N225", "^HSI", "^FTSE", "^TNX"]
    Q = quotes(syms)
    global quote
    _q = quote
    quote = lambda sym: Q[sym] if sym in Q else _q(sym)
    idx = {}
    for k, sym in INDICES.items():
        if sym in Q:
            idx[k] = Q[sym]
    # Previous close: Yahoo's is sometimes a day stale for indices, so keep our own record of each day's close.
    eod = out.setdefault("eod", {})
    for d, vals in EOD_SEED.items():
        eod.setdefault(d, vals)
    today = NOW.strftime("%Y-%m-%d")
    # compare with the close of the day before the quote's own trading day (on weekends that is Thursday, not Friday)
    ts = next((q.get("t") for q in idx.values() if q.get("t")), None)
    qday = dt.datetime.fromtimestamp(ts, IST).strftime("%Y-%m-%d") if ts else today
    prev_days = sorted(d for d in eod if d < min(today, qday))
    if prev_days:
        last = eod[prev_days[-1]]
        for k, q in idx.items():
            if k in last and last[k]:
                p = last[k]
                q.update(prev=p, ch=round(q["v"] - p, 2), pct=round((q["v"] / p - 1) * 100, 2))
    if NOW.weekday() < 5 and NOW.time() >= dt.time(15, 35) and idx:
        eod[today] = {k: q["v"] for k, q in idx.items()}
    for d in sorted(eod)[:-10]:
        eod.pop(d)
    if idx:
        out["idx"] = {**out.get("idx", {}), **idx}
        if "NIFTY" in idx and idx["NIFTY"].get("t"):
            t = dt.datetime.fromtimestamp(idx["NIFTY"]["t"], IST)
            open_now = (NOW.weekday() < 5 and dt.time(9, 15) <= NOW.time() <= dt.time(15, 30)
                        and (NOW - t).total_seconds() < 1800)
            out["state"] = "open" if open_now else "closed"
    try:
        r = yahoo("^NSEI", "1mo", "1d")
        closes = [(dt.datetime.fromtimestamp(ts, IST).strftime("%-d %b"), round(c, 2))
                  for ts, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c]
        if len(closes) >= 3:
            out["nifty8"] = closes[-8:]
    except Exception as e:
        log(f"nifty history failed: {e}")
    glob = []
    for name, sym in (("Dow Jones", "^DJI"), ("S&P 500", "^GSPC"), ("Nasdaq", "^IXIC"), ("Nikkei 225", "^N225"),
                      ("Hang Seng", "^HSI"), ("FTSE 100", "^FTSE"), ("US 10Y yield", "^TNX")):
        try:
            q = quote(sym)
            glob.append([name, q["v"], q["pct"], q.get("t")])
        except Exception as e:
            log(f"global {name} failed: {e}")
    if glob:
        out["global"] = glob
    for key, sym in (("usdinr", "INR=X"), ("brent", "BZ=F"), ("goldSpot", "GC=F")):
        try:
            out[key] = quote(sym)
        except Exception as e:
            log(f"{key} failed: {e}")
    sec = []
    for name, sym in SECTORS:
        try:
            sec.append([name, quote(sym)["pct"]])
        except Exception as e:
            log(f"sector {name} failed: {e}")
    if len(sec) >= 5:
        out["sectors"] = sorted(sec, key=lambda x: -x[1])[:9]
    st, movers = {}, []
    for k, sym in STOCKS.items():
        try:
            q = quote(sym)
            st[k] = {"v": q["v"], "pct": q["pct"]}
            movers.append([k, NAMES[k], q["pct"]])
        except Exception as e:
            log(f"stock {k} failed: {e}")
    for k, name in EXTRA_LARGE.items():
        try:
            movers.append([k, name, quote(k + ".NS")["pct"]])
        except Exception as e:
            log(f"stock {k} failed: {e}")
    if st:
        out["stocks"] = {**out.get("stocks", {}), **st}
    if len(movers) >= 20:
        movers.sort(key=lambda x: -x[2])
        out["gainers"] = [m for m in movers if m[2] > 0][:5]
        out["losers"] = [m for m in reversed(movers) if m[2] < 0][:5]
        out["breadth"] = {"up": sum(1 for m in movers if m[2] > 0), "n": len(movers), "label": "large-cap stocks"}


# ----------------------------------------------------------------- gold & silver
# IBJA = official Indian benchmark (ibjarates.com); MCX futures via bullions.co.in; jeweller retail via Goodreturns
def metals(out):
    m = dict(out.get("metals") or {})
    ib = dict(m.get("ibja") or {})
    try:
        t = text_of(get("https://ibjarates.com/").text)
        t = re.sub(r"\s+", " ", t)
        for pur, val in re.findall(r"(999|995|916|750|585) Purity\s*#*\s*([\d,.]+)\s*\(1 Gram\)", t):
            ib["g" + pur] = num(val)
        def ampm(label):
            r = re.search(label + r"\s*999\D{0,40}?([\d,]{5,9}(?:\.\d+)?)(?:[^\d]{1,20}([\d,]{1,9}(?:\.\d+)?))?", t)
            if not r:
                return None, None
            am = num(r.group(1))
            pm = num(r.group(2)) if r.group(2) and num(r.group(2)) > 1000 else 0
            return am, pm
        gam, gpm = ampm("Gold")
        sam, spm = ampm("Silver")
        rows = re.findall(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{5,7})\s+(\d{5,7})\s+(\d{5,7})\s+(\d{5,7})\s+(\d{4,7})\s+(\d{5,7})", t)
        hist = {}
        for d, mo, y, g999, *_rest, ag in rows:
            day = dt.date(int(y), int(mo), int(d))
            hist[day] = [day.strftime("%-d %b"), int(g999), int(ag)]
        days = sorted(hist)
        cur_g = gpm or gam
        cur_s = spm or sam
        if cur_g is None and ib.get("g999") and days:
            # AM/PM table is drawn by script on that site; use the per-gram 999 card instead
            if abs(ib["g999"] * 10 - hist[days[-1]][1]) > 15:
                cur_g = ib["g999"] * 10
        sess = "PM" if (gpm or spm) else ("AM" if (gam or sam) else "")
        if days:
            last = hist[days[-1]]
            # Is the AM/PM table showing the last history day, or a newer session?
            same = cur_g is None or abs((cur_g or 0) - last[1]) < 1 and abs((cur_s or 0) - last[2]) < 1
            if same:
                cur_day = days[-1]
                prev = hist[days[-2]] if len(days) > 1 else None
                cur_g, cur_s = cur_g or last[1], cur_s or last[2]
            else:
                cur_day = NOW.date() if NOW.weekday() < 5 else days[-1]
                prev = last
            if prev:
                ib["p999"] = round(prev[1] / 10)
                ib["pag"] = round(prev[2] / 1000, 2)
            ib["sess"] = cur_day.strftime("%-d %b") + (f" · {sess}" if sess else "")
            if cur_g and cur_s:
                hist[cur_day] = [cur_day.strftime("%-d %b"), round(cur_g), round(cur_s)]
            old = {x[0]: x for x in (m.get("hist") or [])}
            for k in sorted(hist):
                old[hist[k][0]] = hist[k]
            m["hist"] = sorted(old.values(), key=lambda x: dt.datetime.strptime(f"{x[0]} {NOW.year}", "%d %b %Y"))[-30:]
        if cur_g:
            ib["g999_10"] = cur_g
            ib.setdefault("g999", round(cur_g / 10))
        if cur_s:
            ib["ag"] = round(cur_s / 1000, 2)
        if ib.get("g999") and ib.get("ag"):
            m["ibja"] = ib
        else:
            log("ibja: no gold figure found")
    except Exception as e:
        log(f"ibja failed: {e}")
    mcx_rates(m)
    rt = dict(m.get("retail") or {})
    try:
        t = text_of(get("https://www.goodreturns.in/gold-rates/").text)
        g = re.search(r"₹\s*([\d,]+)\s*per gram for 24 karat.*?₹\s*([\d,]+)\s*per gram for 22 karat.*?₹\s*([\d,]+)\s*per gram for 18 karat", t, re.S)
        if g:
            rt.update(g24=num(g.group(1)), g22=num(g.group(2)), g18=num(g.group(3)))
        t = text_of(get("https://www.goodreturns.in/silver-rates/").text)
        a = re.search(r"price of silver in India today is\s*₹\s*([\d,.]+)\s*per gram", t)
        if a:
            rt["ag"] = num(a.group(1))
        rt["src"] = "Goodreturns"
    except Exception as e:
        log(f"retail metals failed: {e}")
    m["retail"] = rt
    m["date"] = NOW.strftime("%-d %b %Y, %-I:%M %p")
    out["metals"] = m


def mcx(out):
    m = dict(out.get("metals") or {})
    mcx_rates(m)
    m["date"] = NOW.strftime("%-d %b %Y, %-I:%M %p")
    out["metals"] = m


def mcx_rates(m):
    try:
        t = re.sub(r"\s+", " ", text_of(get("https://bullions.co.in/").text))
        mcx = dict(m.get("mcx") or {})
        for key, name in (("gold", "Gold - India MCX"), ("silver", "Silver - India MCX")):
            r = re.search(re.escape(name) + r"\s*\([^)]*\)\s*([\d,.]+)\s*([-+]?[\d,.]+)\s*([-+]?[\d.]+)\s*%", t)
            if r:
                mcx[key] = {"v": num(r.group(1)), "ch": num(r.group(2)), "pct": float(r.group(3)), "t": NOW.strftime("%-d %b, %-I:%M %p")}
            else:
                log(f"mcx {key}: pattern not found")
        if mcx:
            m["mcx"] = mcx
        # spot bullion rates in India (same page): "Gold 24 Karat (Rs ₹) 13,883 138,830 ..." and "Silver 999 Fine (Rs ₹) 179 1,794 17,943 179,430"
        bu = dict(m.get("bullion") or {})
        g = re.search(r"Gold 24 Karat \(Rs[^)]*\)\s*([\d,.]+)\s*([\d,.]+)", t)
        s = re.search(r"Silver 999 Fine \(Rs[^)]*\)\s*([\d,.]+)\s*([\d,.]+)\s*([\d,.]+)\s*([\d,.]+)", t)
        if g:
            bu.update(g24=num(g.group(1)), g24_10=num(g.group(2)))
        if s:
            bu.update(ag_kg=num(s.group(4)), ag=round(num(s.group(4)) / 1000, 2))
        if g or s:
            bu["t"] = NOW.strftime("%-d %b, %-I:%M %p")
            m["bullion"] = bu
        else:
            log("bullion rates: pattern not found")
    except Exception as e:
        log(f"mcx failed: {e}")


# ----------------------------------------------------------------- IPO GMP & subscription
IPOS = {"mksons": "M.K.Sons", "bombaycoated": "Bombay Coated", "sfc": "SFC Environmental", "bls": "BLS Polymers",
        "eaaa": "EAAA", "jio": "Jio Platforms", "hdfire": "HD Fire", "carver": "Carver Roboweld",
        "ajwa": "Ajwa Projects", "antala": "Antala", "maxwell": "Maxwell Engineering", "johnsoncab": "Johnsoncab",
        "vectras": "Vectras", "hgs": "HGS", "wiscon": "Wiscon", "vedant": "Vedant Poly"}


def table_rows(page):
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I):
        cells = [text_of(c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if cells:
            yield cells


def find_row(rows, key):
    k = key.lower()
    for cells in rows:
        if any(k in c.lower() for c in cells[:3]):
            return cells
    return None


def xval(c):
    m = re.match(r"\s*([\d,.]+)\s*[x×]", c or "", re.I)
    return num(m.group(1)) if m else None


def ipo(out):
    data = dict(out.get("ipo") or {})
    known = {k.lower() for k in IPOS.values()}
    names = dict(IPOS)
    for v in out.get("ipocal") or []:
        short_ = re.sub(r"\b(limited|ltd|india)\b", "", v["name"], flags=re.I).strip()
        if v["id"] not in names and not any(k in v["name"].lower() for k in known):
            names[v["id"]] = short_[:28]
    stamp = NOW.strftime("%-d %b, %-I:%M %p")
    try:
        rows = list(table_rows(get("https://www.ipomarket.in/gmp").text))
        for iid, key in names.items():
            c = find_row(rows, key)
            if not c:
                continue
            band = next((n for n, x in enumerate(c) if "–" in x or " - " in x), None)
            if band is None:
                continue
            after = c[band + 1:]
            g = next((x for x in after if re.fullmatch(r"₹\s*-?[\d,.]+", x)), None)
            if g is not None:
                data.setdefault(iid, {}).update(gmp=num(g), gsrc="IPOMarket", gat=stamp)
    except Exception as e:
        log(f"gmp failed: {e}")
    try:
        html_ = get("https://www.ipomarket.in/subscription").text
        cards = html_.split("<article")[1:]
        found, seen = 0, set()
        for card in cards:
            card = card.split("Last updated")[0]  # stop before any footer text
            t = re.sub(r"\s+", " ", text_of(card))
            title = re.search(r'<a[^>]*href="/ipo/[^"]*"[^>]*>(.*?)</a>', card, re.S)
            title = text_of(title.group(1)).strip().lower() if title else t[:120].lower()
            iid = next((k for k, key in names.items() if key.lower() in title), None)
            if not iid or iid in seen:
                continue
            seen.add(iid)
            def cat(label):
                m = re.search(label + r"(?:\s*\([^)]*\))?[^0-9—]{0,20}?([\d,.]+)\s*[x×]", t, re.I)
                return num(m.group(1)) if m else None
            tot = cat(r"\bTotal\b") or cat(r"\bOverall\b")
            if tot is None:
                continue
            q, bn, sn, rt = cat(r"\bQIB\b"), cat(r"\bbNII\b"), cat(r"\bsNII\b"), cat(r"\b(?:Retail|RII)\b")
            nii = cat(r"\bNII\b") if bn is None and sn is None else round(((bn or 0) * 2 + (sn or 0)) / 3, 2)
            data.setdefault(iid, {}).update(sub=tot, sq=q, snii=nii, sr=rt, ssrc="IPOMarket", sat=stamp)
            found += 1
        log(f"subscription: {found} IPOs from {len(cards)} cards")
    except Exception as e:
        log(f"subscription failed: {e}")
    # day-wise GMP history (one reading per day, latest wins)
    day = NOW.strftime("%-d %b")
    for iid, q in data.items():
        if q.get("gmp") is None or not str(q.get("gat", "")).startswith(day):
            continue
        h = [x for x in (q.get("ghist") or []) if x[0] != day]
        h.append([day, q["gmp"]])
        q["ghist"] = h[-30:]
    out["ipo"] = data



# ----------------------------------------------------------------- city-wise gold & silver (jeweller rates), every 30 minutes
CITIES = [("Hyderabad", "hyderabad", 17.385, 78.487), ("Vijayawada", "vijayawada", 16.506, 80.648), ("Visakhapatnam", "visakhapatnam", 17.687, 83.219),
          ("Chennai", "chennai", 13.083, 80.271), ("Bangalore", "bangalore", 12.972, 77.595), ("Mumbai", "mumbai", 19.076, 72.878),
          ("Delhi", "delhi", 28.614, 77.209), ("Kolkata", "kolkata", 22.573, 88.364), ("Pune", "pune", 18.520, 73.857),
          ("Ahmedabad", "ahmedabad", 23.023, 72.571), ("Jaipur", "jaipur", 26.912, 75.787), ("Lucknow", "lucknow", 26.847, 80.946),
          ("Kerala", "kerala", 9.931, 76.267), ("Coimbatore", "coimbatore", 11.017, 76.956), ("Madurai", "madurai", 9.925, 78.120),
          ("Mysore", "mysore", 12.296, 76.639), ("Mangalore", "mangalore", 12.915, 74.856), ("Nagpur", "nagpur", 21.146, 79.088),
          ("Nashik", "nashik", 19.998, 73.790), ("Surat", "surat", 21.170, 72.831), ("Vadodara", "vadodara", 22.307, 73.181),
          ("Patna", "patna", 25.594, 85.138), ("Bhubaneswar", "bhubaneswar", 20.296, 85.825), ("Chandigarh", "chandigarh", 30.733, 76.779)]


def city_metals(out):
    m = out.setdefault("metals", {})
    old = m.get("city") or {}
    if old.get("at_ts") and NOW.timestamp() - old["at_ts"] < 1800 and old.get("v") == 2:
        return

    def one(c):
        name, slug, lat, lon = c
        rec = {"lat": lat, "lon": lon}
        try:
            t = re.sub(r"\s+", " ", text_of(get(f"https://www.goodreturns.in/gold-rates/{slug}.html").text))
            # the city's own sentence ("price of gold in Chennai today is ₹... per gram for 24 karat ..."), not the national one
            g = re.search(re.escape(name) + r"[^₹]{0,80}₹\s*([\d,]+(?:\.\d+)?)\s*per gram for 24 (?:karat|carat)[^₹]{0,40}₹\s*([\d,]+(?:\.\d+)?)\s*per gram for 22 (?:karat|carat)(?:[^₹]{0,40}₹\s*([\d,]+(?:\.\d+)?)\s*per gram for 18 (?:karat|carat))?", t, re.I)
            if g:
                rec.update(g24=num(g.group(1)), g22=num(g.group(2)), g18=num(g.group(3)) if g.group(3) else None)
        except Exception as e:
            log(f"city gold {slug}: {e}")
        try:
            t = re.sub(r"\s+", " ", text_of(get(f"https://www.goodreturns.in/silver-rates/{slug}.html").text))
            a = re.search(r"silver in " + re.escape(name) + r"[^₹]{0,40}₹\s*([\d,.]+)\s*per gram", t, re.I)
            if a:
                rec["ag"] = num(a.group(1))
        except Exception as e:
            log(f"city silver {slug}: {e}")
        return name, rec

    res = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for name, rec in ex.map(one, CITIES):
            if rec.get("g24") or rec.get("ag"):
                res[name] = rec
            elif old.get("v") == 2 and name in (old.get("rates") or {}):
                res[name] = old["rates"][name]
    if res:
        m["city"] = {"v": 2, "rates": res, "at": NOW.strftime("%-d %b, %-I:%M %p"), "at_ts": NOW.timestamp(), "src": "Goodreturns"}
        log(f"city metals: {len(res)} cities")


# ----------------------------------------------------------------- IPO calendar: discovers new IPOs automatically
MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


def _pdate(s):
    m = re.match(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})", s.strip())
    return dt.date(int(m.group(3)), MON[m.group(2).lower()], int(m.group(1))) if m else None


def _next_workday(d, n=1):
    while n:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def ipo_calendar(out):
    """New IPOs from IPOMarket's monthly calendar (last month, this month, next month)."""
    today = NOW.date()
    months = [(today.replace(day=1) - dt.timedelta(days=1)).replace(day=1), today.replace(day=1), (today.replace(day=28) + dt.timedelta(days=4)).replace(day=1)]
    found = {}
    for m in months:
        try:
            page = get(f"https://www.ipomarket.in/ipo-calendar/{MONTH_NAMES[m.month - 1]}-{m.year}").text
        except Exception as e:
            log(f"ipo calendar {m:%b %Y} failed: {e}")
            continue
        # IPOMarket marks SME issues in the link itself (".../xyz-sme-ipo"), which is more reliable than headings
        for part, typ in ((page, None),):
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", part, re.S | re.I):
                link = re.search(r'href="(?:https://www\.ipomarket\.in)?/ipo/([^"]+)"', tr)
                cells = [text_of(c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
                if not link or len(cells) < 6:
                    continue
                name, o, c, price, lot, lst = cells[:6]
                od, cd, ld = _pdate(o), _pdate(c), _pdate(lst)
                pr = [num(x) for x in re.findall(r"[\d,.]+", price)]
                if not od or not cd or not pr:
                    continue
                slug = link.group(1)
                typ = "SME" if "-sme-" in slug or slug.endswith("-sme") else "Mainboard"
                key = re.sub(r"-(sme-)?ipo$", "", slug).replace("-", "")[:24]
                found[key] = {"id": key, "name": name, "type": typ, "open": od.isoformat(), "close": cd.isoformat(),
                              "allot": _next_workday(cd).isoformat(), "refund": _next_workday(cd, 2).isoformat(),
                              "list": (ld or _next_workday(cd, 3)).isoformat(), "lo": pr[0], "hi": pr[-1], "lot": int(num(lot) or 0), "src": slug}
    if found or months:
        keep = [v for v in found.values() if v["list"] >= (today - dt.timedelta(days=21)).isoformat()]
        out["ipocal"] = sorted(keep, key=lambda v: v["open"])
        log(f"ipo calendar: {len(keep)} IPOs")


# ----------------------------------------------------------------- NSE index constituents (live movers)
INDEX_FILES = {"n50": "ind_nifty50list.csv", "mid": "ind_niftymidcap100list.csv", "small": "ind_niftysmallcap100list.csv"}


def constituents(out, key):
    """Official index members from NSE's published CSV (cached, refreshed once a day)."""
    cache = out.setdefault("members", {})
    c = cache.get(key)
    if c and c.get("day") == NOW.strftime("%Y-%m-%d") and len(c.get("list", [])) > 20:
        return c["list"]
    for base in ("https://nsearchives.nseindia.com/content/indices/", "https://www.niftyindices.com/IndexConstituent/"):
        try:
            txt = get(base + INDEX_FILES[key]).text
            lines = [l.split(",") for l in txt.strip().splitlines()]
            head = [h.strip().lower() for h in lines[0]]
            si, ni = head.index("symbol"), head.index("company name")
            lst = [[r[si].strip(), re.sub(r"\s+(Limited|Ltd\.?)$", "", r[ni].strip())] for r in lines[1:] if len(r) > max(si, ni)]
            if len(lst) > 20:
                cache[key] = {"day": NOW.strftime("%Y-%m-%d"), "list": lst}
                return lst
        except Exception as e:
            log(f"members {key} from {base[:30]} failed: {e}")
    return (c or {}).get("list", [])


def nse_movers(out):
    """Nifty 50, Midcap 100 and Smallcap 100 movers: NSE member lists + live prices."""
    lists = {k: constituents(out, k) for k in INDEX_FILES}
    syms = sorted({s for l in lists.values() for s, _ in l})
    Q = quotes([s + ".NS" for s in syms])
    for key, lst in lists.items():
        mv = [[s, n, Q[s + ".NS"]["pct"], Q[s + ".NS"]["v"]] for s, n in lst if s + ".NS" in Q]
        if len(mv) < 10:
            log(f"movers {key}: only {len(mv)} prices")
            continue
        mv.sort(key=lambda x: -x[2])
        up = [m for m in mv if m[2] > 0]
        dn = [m for m in reversed(mv) if m[2] < 0]
        if key == "n50":
            out["gainers"] = [m[:3] for m in up[:5]]
            out["losers"] = [m[:3] for m in dn[:5]]
            out["breadth"] = {"up": len(up), "n": len(mv), "label": "Nifty 50 stocks"}
        else:
            out[key + "g"] = [[m[1], m[2]] for m in up[:5]]
            out[key + "l"] = [[m[1], m[2]] for m in dn[:5]]
        out.setdefault("nse", {})[key] = NOW.strftime("%-d %b, %-I:%M %p")


def nse_session():
    S.get("https://www.nseindia.com/", timeout=20)



# ----------------------------------------------------------------- every listed stock (NSE + BSE)
OUT_EXTRA = os.path.join(ROOT, "out")  # published to the separate "data" branch, not committed to main
RAW_DATA = "https://raw.githubusercontent.com/vanapalliveerasankar427/stockpilot/data/"


def universe():
    """All listed equities: NSE main board + NSE SME + BSE-only. Refreshed once a day."""
    try:
        old = get(RAW_DATA + "universe.json").json()
        if old.get("day") == NOW.strftime("%Y-%m-%d") and len(old.get("s", [])) > 1000 and (old.get("bse") or old.get("tries", 0) >= 3) and old.get("v") == 2:
            return old
    except Exception:
        old = {}
    rows, isins = [], set()
    for fname, ex in (("EQUITY_L.csv", "NSE"), ("SME_EQUITY_L.csv", "NSE SME")):
        try:
            txt = get("https://nsearchives.nseindia.com/content/equities/" + fname).text
            lines = [l.split(",") for l in txt.strip().splitlines()]
            head = [h.strip().upper() for h in lines[0]]
            si, ni = head.index("SYMBOL"), head.index("NAME OF COMPANY")
            ii = next((n for n, h in enumerate(head) if "ISIN" in h), None)
            for r in lines[1:]:
                if len(r) <= max(si, ni):
                    continue
                sym, name = r[si].strip(), re.sub(r"\s+(Limited|Ltd\.?)$", "", r[ni].strip().strip('"'), flags=re.I)
                rows.append([sym, name, ex, sym + ".NS"])
                if ii is not None and ii < len(r):
                    isins.add(r[ii].strip())
        except Exception as e:
            log(f"nse list {fname} failed: {e}")
    try:
        S.get("https://www.bseindia.com/", timeout=20)
        j = get("https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active",
                headers={"Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"}).json()
        for r in j if isinstance(j, list) else j.get("Table", []):
            isin = (r.get("ISIN_NUMBER") or "").strip()
            if isin and isin in isins:
                continue
            code = str(r.get("SCRIP_CD") or "").strip()
            name = re.sub(r"\s+(Limited|Ltd\.?)$", "", (r.get("Scrip_Name") or r.get("Issuer_Name") or "").strip(), flags=re.I)
            if code and name:
                rows.append(["B" + code, name, "BSE", code + ".BO", (r.get("scrip_id") or r.get("Scrip_id") or "").strip()])
    except Exception as e:
        log(f"bse list failed: {e}")
        # fallback: BSE's daily price file (bhavcopy) lists every traded scrip with code, ISIN and name
        for back in range(1, 8):
            d = NOW.date() - dt.timedelta(days=back)
            if d.weekday() >= 5:
                continue
            url = f"https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV"
            try:
                txt = get(url, headers={"Referer": "https://www.bseindia.com/"}).text
                lines = [l.split(",") for l in txt.strip().splitlines()]
                head = [h.strip() for h in lines[0]]
                ci, ii, ni, ti = head.index("FinInstrmId"), head.index("ISIN"), head.index("FinInstrmNm"), head.index("TckrSymb")
                si = head.index("SctySrs") if "SctySrs" in head else None
                n0 = len(rows)
                for r in lines[1:]:
                    if len(r) <= max(ci, ii, ni, ti) or r[ii].strip() in isins:
                        continue
                    if si is not None and r[si].strip() not in ("A", "B", "T", "X", "XT", "M", "MT", "Z", "ZP", "MS", "P", "R", "W"):
                        continue
                    nm = re.sub(r"\s+(Limited|Ltd\.?)$", "", r[ni].strip(), flags=re.I)
                    eod = None
                    try:
                        g = lambda col: float(r[head.index(col)]) if col in head and r[head.index(col)].strip() else None
                        eod = [g("ClsPric"), g("PrvsClsgPric"), g("OpnPric"), g("HghPric"), g("LwPric"), g("TtlTradgVol"), d.strftime("%-d %b")]
                    except (ValueError, IndexError):
                        pass
                    rows.append(["B" + r[ci].strip(), nm, "BSE", r[ci].strip() + ".BO", r[ti].strip(), eod])
                log(f"bse bhavcopy {d}: {len(rows) - n0} BSE-only scrips")
                break
            except Exception as e2:
                log(f"bse bhavcopy {d} failed: {e2}")
    if len(rows) < 1000:
        log(f"universe: only {len(rows)} stocks, keeping previous list")
        return old or {"s": rows}
    nb = sum(1 for r in rows if r[2] == "BSE")
    tries = (old.get("tries", 0) + 1) if old.get("day") == NOW.strftime("%Y-%m-%d") and not nb else 0
    return {"day": NOW.strftime("%Y-%m-%d"), "s": rows, "bse": nb, "tries": tries, "v": 2}


def bse_eod():
    """Latest BSE daily price file (bhavcopy): scrip code -> [close, prev close, open, high, low, volume, day]."""
    for back in range(0, 8):
        d = NOW.date() - dt.timedelta(days=back)
        if d.weekday() >= 5 or (back == 0 and NOW.hour < 19):
            continue
        url = f"https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV"
        try:
            txt = get(url, headers={"Referer": "https://www.bseindia.com/"}).text
            lines = [l.split(",") for l in txt.strip().splitlines()]
            head = [h.strip() for h in lines[0]]
            ci = head.index("FinInstrmId")
            g = lambda r, col: float(r[head.index(col)]) if col in head and r[head.index(col)].strip() else None
            res = {}
            for r in lines[1:]:
                try:
                    res[r[ci].strip()] = [g(r, "ClsPric"), g(r, "PrvsClsgPric"), g(r, "OpnPric"), g(r, "HghPric"), g(r, "LwPric"), g(r, "TtlTradgVol"), d.strftime("%-d %b")]
                except (ValueError, IndexError):
                    pass
            if len(res) > 1000:
                log(f"bse eod {d}: {len(res)} scrips")
                return res
        except Exception as e:
            log(f"bse eod {d} failed: {e}")
    return {}


def yahoo_crumb():
    S.get("https://fc.yahoo.com", timeout=20, allow_redirects=True)
    c = S.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=20).text.strip()
    if not c or "<" in c or len(c) > 40:
        raise RuntimeError("no crumb")
    return c


def all_quotes(uni):
    """Live quote for every listed stock, 100 symbols per request."""
    ysyms = [r[3] for r in uni.get("s", [])]
    key_of = {r[3]: r[0] for r in uni.get("s", [])}
    out, crumb = {}, None
    try:
        crumb = yahoo_crumb()
    except Exception as e:
        log(f"yahoo crumb failed: {e}")
    fields = ("regularMarketPrice,regularMarketChangePercent,regularMarketPreviousClose,regularMarketOpen,regularMarketDayHigh,"
              "regularMarketDayLow,fiftyTwoWeekHigh,fiftyTwoWeekLow,regularMarketVolume,marketCap,trailingPE,epsTrailingTwelveMonths,"
              "priceToBook,trailingAnnualDividendYield,regularMarketTime,averageDailyVolume3Month,averageDailyVolume10Day")

    def batch(chunk):
        r = S.get("https://query1.finance.yahoo.com/v7/finance/quote", timeout=30,
                  params={"symbols": ",".join(chunk), "crumb": crumb, "fields": fields})
        r.raise_for_status()
        return r.json().get("quoteResponse", {}).get("result", [])

    def safe_batch(c):
        try:
            return batch(c)
        except Exception as e:
            log(f"quote batch failed: {e}")
            return []

    if crumb:
        chunks = [ysyms[i:i + 100] for i in range(0, len(ysyms), 100)]
        with ThreadPoolExecutor(max_workers=6) as ex:
            for res in ex.map(lambda c: safe_batch(c), chunks):
                for q in res or []:
                    k = key_of.get(q.get("symbol"))
                    p = q.get("regularMarketPrice")
                    if not k or p is None:
                        continue
                    g = lambda f, nd=2: round(q[f], nd) if isinstance(q.get(f), (int, float)) else None
                    mc = q.get("marketCap")
                    out[k] = [g("regularMarketPrice"), g("regularMarketChangePercent"), g("regularMarketPreviousClose"), g("regularMarketOpen"),
                              g("regularMarketDayHigh"), g("regularMarketDayLow"), g("fiftyTwoWeekHigh"), g("fiftyTwoWeekLow"),
                              q.get("regularMarketVolume"), round(mc / 1e7, 1) if isinstance(mc, (int, float)) else None,
                              g("trailingPE"), g("epsTrailingTwelveMonths"), g("priceToBook"),
                              round(q["trailingAnnualDividendYield"] * 100, 2) if isinstance(q.get("trailingAnnualDividendYield"), (int, float)) else None,
                              q.get("regularMarketTime"), q.get("averageDailyVolume3Month"), q.get("averageDailyVolume10Day")]
    if crumb:  # second pass for batches Yahoo dropped (rate limits): smaller chunks, one at a time
        miss = [s for s in ysyms if s.endswith(".NS") and key_of[s] not in out]
        if miss:
            got0 = len(out)
            for i in range(0, len(miss), 40):
                for q in safe_batch(miss[i:i + 40]):
                    k, p = key_of.get(q.get("symbol")), q.get("regularMarketPrice")
                    if k and p is not None:
                        g = lambda f, nd=2: round(q[f], nd) if isinstance(q.get(f), (int, float)) else None
                        mc = q.get("marketCap")
                        out[k] = [g("regularMarketPrice"), g("regularMarketChangePercent"), g("regularMarketPreviousClose"), g("regularMarketOpen"),
                                  g("regularMarketDayHigh"), g("regularMarketDayLow"), g("fiftyTwoWeekHigh"), g("fiftyTwoWeekLow"),
                                  q.get("regularMarketVolume"), round(mc / 1e7, 1) if isinstance(mc, (int, float)) else None,
                                  g("trailingPE"), g("epsTrailingTwelveMonths"), g("priceToBook"),
                                  round(q["trailingAnnualDividendYield"] * 100, 2) if isinstance(q.get("trailingAnnualDividendYield"), (int, float)) else None,
                                  q.get("regularMarketTime"), q.get("averageDailyVolume3Month"), q.get("averageDailyVolume10Day")]
            log(f"quotes retry: +{len(out) - got0} of {len(miss)} missing NSE")
    nse_miss = [s for s in ysyms if s.endswith(".NS") and key_of[s] not in out]
    if nse_miss and (len(out) < len(ysyms) * 0.5 or len(nse_miss) <= 600):
        # fallback: one chart request per missing NSE symbol (price, change, day range, 52-week range)
        log(f"per-symbol fallback for {len(nse_miss)} NSE stocks")
        nse = nse_miss

        def one(sym):
            try:
                m = yahoo(sym, "1d", "1d")["meta"]
                v, pv = m["regularMarketPrice"], m.get("chartPreviousClose") or m.get("previousClose")
                return sym, [round(v, 2), round((v / pv - 1) * 100, 2) if pv else None, pv, None, m.get("regularMarketDayHigh"), m.get("regularMarketDayLow"),
                             m.get("fiftyTwoWeekHigh"), m.get("fiftyTwoWeekLow"), m.get("regularMarketVolume"), None, None, None, None, None, m.get("regularMarketTime")]
            except Exception:
                return sym, None
        with ThreadPoolExecutor(max_workers=24) as ex:
            for sym, row in ex.map(one, nse):
                if row:
                    out[key_of[sym]] = row
    # split / bonus day: Yahoo's previous close isn't adjusted, so the day change is wrong; drop it
    for k, r in out.items():
        if r[1] is not None and abs(r[1]) > 25 and r[2] and r[3] and abs(r[3] / r[2] - 1) > 0.25:
            r[1] = None
    # BSE-only scrips that Yahoo doesn't price: use BSE's official close from its daily price file
    eod = bse_eod() if sum(1 for r in uni.get("s", []) if r[2] == "BSE" and r[0] not in out) > 200 else {}
    for r in uni.get("s", []):
        if r[0] not in out and r[2] == "BSE" and (len(r) < 6 or not r[5]) and r[0][1:] in eod:
            c, pv, o, h, l, v, day = eod[r[0][1:]]
            if c is not None:
                out[r[0]] = [c, round((c / pv - 1) * 100, 2) if pv else None, pv, o, h, l, None, None, v, None, None, None, None, None, "BSE close " + day]
    for r in uni.get("s", []):
        if r[0] in out or len(r) < 6 or not r[5] or r[5][0] is None:
            continue
        c, pv, o, h, l, v, day = r[5]
        out[r[0]] = [c, round((c / pv - 1) * 100, 2) if pv else None, pv, o, h, l, None, None, v, None, None, None, None, None, "BSE close " + day]
    return out


# ----------------------------------------------------------------- results calendar (NSE + BSE), refreshed hourly
def results_cal(out):
    old = out.get("rescal") or {}
    if old.get("ts") and time.time() - old["ts"] < 3600 and old.get("items"):
        return
    items, seen = [], set()
    def add(sym, name, d, src):
        key = (sym, d)
        if sym and d and key not in seen:
            seen.add(key); items.append({"k": sym, "n": name, "d": d, "src": src})
    def ddate(v):
        v = str(v or "").strip()[:11]
        for f in ("%d-%b-%Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return dt.datetime.strptime(v, f).date().isoformat()
            except ValueError:
                pass
    try:  # NSE board meetings for financial results (NSE symbols)
        nse_session()
        j = get("https://www.nseindia.com/api/event-calendar", headers={**UA, "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar"}).json()
        for r in (j if isinstance(j, list) else j.get("data") or []):
            purpose = f"{r.get('purpose', '')} {r.get('bm_desc', '')}".lower()
            if "result" in purpose:
                add(str(r.get("symbol", "")).upper(), r.get("company", ""), ddate(r.get("date")), "NSE")
    except Exception as e:
        log(f"results cal nse: {e}")
    try:  # BSE forthcoming results (adds BSE-only companies)
        S.get("https://www.bseindia.com/", timeout=20)
        j = get("https://api.bseindia.com/BseIndiaAPI/api/Corpforthresults/w", headers={"Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"}).json()
        rows = j if isinstance(j, list) else (j.get("Table") or next((v for v in j.values() if isinstance(v, list)), []))
        for r in rows:
            low = {k.lower(): v for k, v in r.items()}
            code = str(low.get("scrip_code") or low.get("scrip_cd") or "").strip()
            add("B" + code if code else "", low.get("long_name") or low.get("short_name") or "", ddate(low.get("meeting_date")), "BSE")
        if rows and not any(i["src"] == "BSE" for i in items):
            log(f"results cal bse sample: {json.dumps(rows[0])[:240]}")
    except Exception as e:
        log(f"results cal bse: {e}")
    if items:
        today = NOW.date().isoformat()
        out["rescal"] = {"ts": time.time(), "at": NOW.strftime("%-d %b, %-I:%M %p"), "items": sorted([i for i in items if i["d"] >= today], key=lambda i: i["d"])[:1500]}
        log(f"results cal: {len(out['rescal']['items'])} upcoming ({sum(i['src']=='NSE' for i in items)} NSE)")


# ----------------------------------------------------------------- Tomorrow's watch: stocks with a reason to move next session
RESULT_WORDS = re.compile(r"\b(q[1-4]|quarter|results?|profit|net income|pat|ebitda|revenue|earnings)\b", re.I)
def tomorrow_watch(out, uni, q):
    names = {r[0]: r[1] for r in uni.get("s", [])}
    fno = (out.get("fno") or {}).get("syms") or {}
    today = NOW.date()
    hm = NOW.hour * 60 + NOW.minute
    live_today = sum(1 for r in q.values() if isinstance(r[14], (int, float)) and dt.datetime.fromtimestamp(r[14], IST).date() == today) > 500
    tw = out.get("tw") or {}
    hist = tw.get("hist") or []
    snap = tw.get("snap")
    # 1) score yesterday's (or the last) snapshot once the next session has closed
    if snap and snap.get("d") != today.isoformat() and live_today and hm >= 15 * 60 + 35 and not any(h.get("d") == snap["d"] for h in hist):
        res = []
        for k, p0 in snap.get("px", {}).items():
            r = q.get(k)
            if r and r[0] and p0:
                res.append([k, round((r[0] / p0 - 1) * 100, 2)])
        if res:
            res.sort(key=lambda x: -x[1])
            hist.insert(0, {"d": snap["d"], "on": today.isoformat(), "n": len(res), "up": sum(1 for _, v in res if v > 0),
                            "avg": round(sum(v for _, v in res) / len(res), 2), "best": res[:3], "worst": res[-2:], "all": res})
            hist = hist[:30]
    # 2) build today's lists
    nxt = today + dt.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += dt.timedelta(days=1)
    cal = (out.get("rescal") or {}).get("items") or []
    due_days = {today.isoformat(), nxt.isoformat()} if hm >= 9 * 60 else {today.isoformat()}
    rows = {}
    def row(k):
        r = q.get(k)
        if not r or not r[0]:
            return None
        if k not in rows:
            vx = (r[8] / r[16]) if r[8] and len(r) > 16 and r[16] else None
            rows[k] = {"k": k, "n": names.get(k, k), "p": r[0], "pct": r[1], "vx": round(vx, 1) if vx else None, "fo": k in fno, "why": [], "s": 0.0}
        return rows[k]
    for x in (out.get("outlook") or {}).get("up", []):  # results and positive news (already scored by the outlook)
        news = [w for w in x.get("why", []) if w.get("k") == "news"]
        if news and (x.get("pct") or 0) > -1:
            o = row(x["k"])
            if o:
                res = any(RESULT_WORDS.search(w.get("t", "")) for w in news)
                o["why"].append({"t": "results" if res else "news", "x": news[0].get("t", "")[:160], "u": news[0].get("u", "")})
                o["s"] += x.get("s", 0) * (1.4 if res else 1.0)
    for i in cal:  # results due after today's close / before the next open
        if i["d"] in due_days:
            o = row(i["k"])
            if o:
                o["why"].append({"t": "due", "x": "Results " + ("today" if i["d"] == today.isoformat() else "on " + dt.date.fromisoformat(i["d"]).strftime("%-d %b"))})
                o["s"] += 4 + (2 if o["fo"] else 0)
    for k, r in q.items():  # strong close: up 2%+, near the day's high, on 2x+ normal volume, ₹1 Cr+ traded
        try:
            p, pct, hi, vol = r[0], r[1], r[4], r[8]
            av = r[16] if len(r) > 16 else None
            if not (p and pct and hi and vol and av) or pct < 2 or pct > 19.9 or p < hi * 0.985 or vol < 2 * av or p * vol < 1e7:
                continue
            o = row(k)
            o["why"].append({"t": "momentum", "x": f"Up {pct:.1f}%, closing near the day's high on {vol / av:.1f}× normal volume"})
            o["s"] += pct * min(vol / av, 5) / 2
        except Exception:
            continue
    L = [o for o in rows.values() if o["why"]]
    L.sort(key=lambda o: -o["s"])
    picks = [o for o in L if any(w["t"] in ("results", "news", "momentum") for w in o["why"])][:25]
    fo = [o for o in L if o["fo"] and any(w["t"] in ("results", "news", "momentum") for w in o["why"])][:12]
    due = [o for o in L if any(w["t"] == "due" for w in o["why"]) and not any(w["t"] in ("results", "news") for w in o["why"])][:25]
    for o in L:
        o["s"] = round(o["s"], 1)
    phase = "pre" if hm < 9 * 60 + 15 else "live" if hm < 15 * 60 + 15 else "close" if hm < 19 * 60 else "evening"
    # 3) freeze the list from 3:15 PM (and refresh it after the evening results), scored next session
    if live_today and phase in ("close", "evening") and (not snap or snap.get("d") != today.isoformat() or phase == "evening"):
        sel = (picks[:15] + [o for o in fo if o not in picks[:15]])[:20]
        snap = {"d": today.isoformat(), "phase": phase, "px": {o["k"]: o["p"] for o in sel}}
    tw = {"at": NOW.strftime("%-d %b, %-I:%M %p"), "phase": phase, "for": nxt.strftime("%a %-d %b") if hm >= 15 * 60 + 15 else today.strftime("%a %-d %b"),
          "picks": picks, "fo": fo, "due": due, "snap": snap, "hist": hist}
    out["tw"] = tw


def everything(out):
    os.makedirs(OUT_EXTRA, exist_ok=True)
    uni = universe()
    json.dump(uni, open(os.path.join(OUT_EXTRA, "universe.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    q = all_quotes(uni)
    if q:
        json.dump({"updated": NOW.isoformat(timespec="seconds"), "label": NOW.strftime("%-d %b %Y, %-I:%M %p IST"),
                   "cols": ["price", "pct", "prev", "open", "high", "low", "h52", "l52", "vol", "mcapCr", "pe", "eps", "pb", "dy", "t", "av3m", "av10"], "q": q},
                  open(os.path.join(OUT_EXTRA, "quotes.json"), "w"), separators=(",", ":"))
    out["universe"] = {"stocks": len(uni.get("s", [])), "quotes": len(q), "at": NOW.strftime("%-d %b, %-I:%M %p")}
    if q:  # whole-market movers (every NSE stock + BSE-only stocks) for the market pushes
        try:
            names = {r[0]: r[1] for r in uni.get("s", [])}
            rows = [[k, names.get(k, k), r[1]] for k, r in q.items() if r[1] is not None and isinstance(r[14], (int, float)) and not re.match(r"^B\d+$", k)]
            bm = out.get("bse_movers") or {}
            for side in ("g", "l"):
                for code, nm, ltp, pct, *_ in bm.get(side, []):
                    if "B" + code in names:
                        rows.append(["B" + code, names["B" + code], pct])
            rows.sort(key=lambda x: x[2])
            out["allmov"] = {"at": NOW.strftime("%-d %b, %-I:%M %p"), "g": [x for x in rows[::-1] if x[2] > 0][:10], "l": [x for x in rows if x[2] < 0][:10]}
        except Exception as e:
            log(f"allmov: {e}")
    if q:  # stocks at a 52-week high / low (₹2,000 Cr+), for the midday push and the site
        try:
            hi, lo = [], []
            for k, r in q.items():
                p, pc, h52, l52, mc = r[0], r[1], r[6], r[7], r[9]
                if not p or not r[8] or not isinstance(r[14], (int, float)):  # every stock that traded today, any size
                    continue
                if h52 and p >= h52 * 0.998:
                    hi.append((mc, k, pc))
                elif l52 and p <= l52 * 1.002:
                    lo.append((mc, k, pc))
            hi.sort(key=lambda x: x[0] or 0, reverse=True); lo.sort(key=lambda x: x[0] or 0, reverse=True)
            out["hilo"] = {"at": NOW.strftime("%-d %b, %-I:%M %p"), "hi": [[k, pc] for _, k, pc in hi[:40]], "lo": [[k, pc] for _, k, pc in lo[:40]], "nhi": len(hi), "nlo": len(lo)}
        except Exception as e:
            log(f"hilo: {e}")
    if q:
        try:
            outlook(out, uni, q)
        except Exception as e:
            log(f"outlook crashed: {e}")
        try:
            tomorrow_watch(out, uni, q)
        except Exception as e:
            log(f"tomorrow watch crashed: {e}")


# ----------------------------------------------------------------- today's outlook (likely up / likely down)
POS = [(r"\b(surges?|soars?|jumps?|rall(y|ies)|zooms?|skyrockets?|spurts?|climbs?|gains?|rises?|up \d+(\.\d+)?%|hits? (record|52[- ]week) high|upper circuit)\b", 2),
       (r"\b(order|contract|deal|project)s? (win|worth|from|of)\b|\b(wins?|bags?|secures?|bagged|won|receives?) (an? )?(order|contract|deal|project|approval|nod)", 3),
       (r"\b(profit|net income|pat|revenue|ebitda|earnings)\b[^.]{0,30}\b(rises?|jumps?|surges?|grows?|up|soars?|doubles?|beats?|higher)\b", 3),
       (r"\b(beats? (estimates|expectations)|strong (results|quarter|numbers|q[1-4]))\b", 2),
       (r"\b(upgrades?|upgraded|raises? target|target (price )?(raised|hiked)|buy (rating|call)|initiates? (coverage )?with (a )?buy|overweight|outperform)\b", 2),
       (r"\b(usfda|fda|dcgi|sebi|rbi|cci) (nod|approval|approves)|gets? (usfda|fda|regulatory) (nod|approval)\b", 2),
       (r"\b(bonus|buyback|special dividend|stock split|record date)\b", 1),
       (r"\b(acquires?|acquisition|stake (buy|hike)|raises? stake|partnership|joint venture|ties? up|launch(es)?|expansion|capex|new plant)\b", 1)]
NEG = [(r"\b(falls?|slumps?|plunges?|crash(es)?|tumbles?|tanks?|sinks?|slides?|drops?|declines?|dips?|down \d+(\.\d+)?%|hits? 52[- ]week low|lower circuit|sell-?off)\b", 2),
       (r"\b(profit|net income|pat|revenue|ebitda|earnings|margin)s?\b[^.]{0,30}\b(falls?|drops?|declines?|slumps?|plunges?|down|lower|misses?|shrinks?|contracts?)\b|\b(net )?loss widens|\bposts? (a )?(net )?loss\b", 3),
       (r"\b(misses? (estimates|expectations)|weak (results|quarter|numbers|q[1-4]|guidance))\b", 2),
       (r"\b(downgrades?|downgraded|cuts? target|target (price )?(cut|lowered|slashed)|sell (rating|call)|underweight|underperform|reduce rating)\b", 2),
       (r"\b(probe|raid|penalty|fined?|fraud|scam|show[- ]cause|sebi order|ban(ned)?|default(s|ed)?|insolvency|resigns?|resignation|pledge|downgrade by (icra|crisil|care)|fire at|strike at|recall)\b", 3),
       (r"\b(block deal|promoter (sells?|offloads?)|stake sale|ofs\b|dilution)\b", 1)]
OUTLOOK_Q = ["shares surge India", "shares jump NSE", "stock rallies after", "shares fall India", "shares slump NSE", "Q2 results net profit shares",
             "bags order shares", "wins contract shares", "stocks to watch today", "brokerage target price shares", "upper circuit stock", "SEBI order company shares"]


def _clean_name(n):
    n = re.sub(r"\b(limited|ltd|ltd\.|the|co|company|corporation|corp)\b\.?", " ", n.lower().replace("&", "and"))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", n)).strip()


def outlook(out, uni, q):
    try:
        prof = get("https://raw.githubusercontent.com/vanapalliveerasankar427/stockpilot/hist/profiles.json").json().get("sec", {})
    except Exception:
        prof = {}
    names = {r[0]: r[1] for r in uni.get("s", [])}
    pool = {k: v for k, v in q.items() if v and v[0] and v[0] >= 20 and ((v[9] or 0) >= 500 or (v[9] is None and (v[0] or 0) * (v[8] or 0) >= 2e7))}
    # name aliases for matching headlines
    alias = {}
    for k in sorted(pool, key=lambda k: -(pool[k][9] or 0)):  # bigger companies claim shared short names first
        n = _clean_name(names.get(k, k))
        if len(n) >= 6:
            alias.setdefault(n, k)
            n2 = n.replace("pharmaceuticals", "pharma").replace("pharmaceutical", "pharma").replace(" industries", "").replace(" india", "")
            if len(n2) >= 6:
                alias.setdefault(n2, k)
            w = n.split()
            if len(w) >= 3 and len(" ".join(w[:2])) >= 9:
                alias.setdefault(" ".join(w[:2]), k)
    # drop ambiguous two-word aliases that several companies share
    cnt = {}
    for k in pool:
        w = _clean_name(names.get(k, k)).split()
        if len(w) >= 2:
            cnt[" ".join(w[:2])] = cnt.get(" ".join(w[:2]), 0) + 1
    for a in [a for a in alias if cnt.get(a, 1) > 1 and alias[a] and _clean_name(names.get(alias[a], "")) != a]:
        alias.pop(a, None)
    pats = sorted(alias, key=len, reverse=True)
    rx = re.compile(r"\b(" + "|".join(re.escape(a) for a in pats) + r")\b") if pats else None
    syms = {k for k in pool if len(k) >= 3 and k.isalpha()}

    heads, seen = [], set()
    def feed(qs):
        try:
            x = get("https://news.google.com/rss/search", params={"q": qs + " when:1d", "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}).content
            res = []
            for it in ET.fromstring(x).iter("item"):
                t = it.findtext("title") or ""; src = it.findtext("source") or ""
                if src and t.endswith(" - " + src):
                    t = t[: -len(src) - 3]
                res.append((t, src, it.findtext("link") or ""))
            return res
        except Exception as e:
            log(f"outlook news '{qs}' failed: {e}")
            return []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for res in ex.map(feed, OUTLOOK_Q):
            for t, src, link in res:
                key = re.sub(r"\W", "", t.lower())[:80]
                if key not in seen:
                    seen.add(key); heads.append((t, src, link))

    score, why = {}, {}
    def add(k, s, kind, txt, url=None, src=None):
        score[k] = score.get(k, 0) + s
        why.setdefault(k, []).append({"k": kind, "t": txt, "s": s, **({"u": url} if url else {}), **({"src": src} if src else {})})
    for t, src, link in heads:
        low = t.lower().replace("&", "and")
        hit = set()
        if rx:
            for m in rx.finditer(re.sub(r"[^a-z0-9 ]", " ", low)):
                hit.add(alias[m.group(1)])
        for w in re.findall(r"\b[A-Z][A-Z0-9]{2,}\b", t):
            if w in syms and w not in ("IPO", "NSE", "BSE", "SEBI", "RBI", "GST", "USD", "INR", "FII", "DII", "LIC", "GDP"):
                hit.add(w)
        # a symbol that is just the first word of another matched company (NTPC in "NTPC Green Energy") is not a separate hit
        for k in list(hit):
            if any(o != k and _clean_name(names.get(o, "")).split()[:1] == [k.lower()] for o in hit):
                hit.discard(k)
        # brokerages quoted as the source of a view ("Motilal Oswal says...", "JM Financial downgrades X") are not the subject
        BROKERS = {"MOTILALOFS", "JMFINANCIL", "IIFL", "ANGELONE", "NUVAMA", "ICICISEC", "GEOJITFSL", "EMKAY", "ANANDRATHI", "SHAREINDIA", "PRUDENT"}
        if len(hit) > 1:
            hit -= BROKERS
        hit = {k for k in hit if not re.search(re.escape(_clean_name(names.get(k, k)).split()[0]) + r"\w* (securities|institutional|research|capital markets|broking)\b", low)} or hit
        if not hit or len(hit) > 2:
            continue  # skip lists like "stocks to watch: A, B, C"
        p = sum(w for r, w in POS if re.search(r, low)); n = sum(w for r, w in NEG if re.search(r, low))
        s = max(-4, min(4, p - n))
        if s == 0:
            continue
        for k in hit:
            if sum(1 for x in why.get(k, []) if x["k"] == "news") < 3:
                add(k, s * 2, "news", t, link, src)
    # price action in the latest session
    for k, v in pool.items():
        price, pct, prev, op, hi, lo, h52, l52, vol = v[:9]
        av = (v[16] if len(v) > 16 else None) or (v[15] if len(v) > 15 else None)
        vr = vol / av if vol and av else None
        pos = (price - lo) / (hi - lo) if hi and lo and hi > lo else None
        if pct is None:
            continue
        if pct >= 2 and (vr or 0) >= 1.5 and (pos or 0) >= 0.7:
            add(k, 1.5 + min(1.5, (vr - 1.5) / 2), "price", f"Closed strong: {pct:+.1f}% on {vr:.1f}× usual volume, near the day's high")
        elif pct <= -2 and (vr or 0) >= 1.5 and pos is not None and pos <= 0.3:
            add(k, -1.5 - min(1.5, (vr - 1.5) / 2), "price", f"Closed weak: {pct:+.1f}% on {vr:.1f}× usual volume, near the day's low")
        if h52 and price >= h52 * 0.995 and pct > 0.5:
            add(k, 1, "price", "Trading at a 52-week high")
        elif l52 and price <= l52 * 1.005 and pct < -0.5:
            add(k, -1, "price", "Trading at a 52-week low")
    # global cues for sectors
    G = {n: p for n, v, p, *_ in out.get("global", [])}
    nas = G.get("Nasdaq"); cues = []
    if nas is not None and abs(nas) >= 1:
        cues.append(f"US tech (Nasdaq) {'rose' if nas > 0 else 'fell'} {abs(nas):.1f}% in the last session")
        for k in score:
            sec = (prof.get(k) or [""])[0]
            if sec == "Technology":
                add(k, 1 if nas > 0 else -1, "global", f"Nasdaq {nas:+.1f}% overnight; IT stocks often follow")
    br = out.get("brent") or {}
    if isinstance(br, dict) and br.get("pct") is not None and abs(br["pct"]) >= 2:
        cues.append(f"Brent crude {'up' if br['pct'] > 0 else 'down'} {abs(br['pct']):.1f}%")
    for n in ("Dow Jones", "S&P 500", "Nikkei 225", "Hang Seng"):
        if G.get(n) is not None and abs(G[n]) >= 0.8:
            cues.append(f"{n} {G[n]:+.1f}%")

    def item(k):
        v = pool[k]; s = round(score[k], 1); r = sorted(why[k], key=lambda x: -abs(x["s"]))[:4]
        has_news = any(x["k"] == "news" for x in r)
        conf = "High" if abs(s) >= 6 and has_news else "Medium" if abs(s) >= 3.5 else "Low"
        return {"k": k, "n": names.get(k, k), "s": s, "conf": conf, "p": v[0], "pct": v[1], "mc": v[9], "sec": (prof.get(k) or [""])[0], "why": r}
    news_k = {k for k in why if any(x["k"] == "news" for x in why[k])}
    ranked = sorted((k for k in score if k in pool), key=lambda k: -(score[k] + (1.5 if k in news_k else 0) * (1 if score[k] > 0 else -1)))
    # "likely up" only lists stocks that are actually up; "likely down" only those that are down
    up = [item(k) for k in ranked if score[k] >= 2.5 and (pool[k][1] or 0) > 0][:25]
    dn = [item(k) for k in reversed(ranked) if score[k] <= -2.5 and (pool[k][1] or 0) < 0][:25]
    out["outlook"] = {"at": NOW.strftime("%-d %b, %-I:%M %p"), "headlines": len(heads), "screened": len(pool), "cues": cues, "up": up, "down": dn}
    log(f"outlook: {len(heads)} headlines, {len(up)} up, {len(dn)} down")


# ----------------------------------------------------------------- FII / DII (NSE)
def flows(out):
    try:
        nse_session()
        j = get("https://www.nseindia.com/api/fiidiiTradeReact", headers={"Referer": "https://www.nseindia.com/"}).json()
        f = {}
        for row in j:
            cat = row.get("category", "").upper()
            if "FII" in cat or "FPI" in cat:
                f["fii"] = num(row["netValue"])
            elif "DII" in cat:
                f["dii"] = num(row["netValue"])
            f["date"] = row.get("date", f.get("date"))
        for row in j:
            cat = row.get("category", "").upper()
            key = "fii" if ("FII" in cat or "FPI" in cat) else "dii" if "DII" in cat else None
            if key:
                for fld, nm in (("buyValue", "buy"), ("sellValue", "sell")):
                    try:
                        f[f"{key}_{nm}"] = num(row[fld])
                    except (KeyError, ValueError, TypeError):
                        pass
        if "fii" in f and "dii" in f:
            f["fetched"] = NOW.strftime("%-d %b, %-I:%M %p")
            f["src"] = "NSE (provisional)"
            hist = {h["date"]: h for h in (out.get("flows") or {}).get("hist", [])}
            hist[f["date"]] = {"date": f["date"], "fii": f["fii"], "dii": f["dii"]}
            f["hist"] = sorted(hist.values(), key=lambda h: dt.datetime.strptime(h["date"], "%d-%b-%Y"))[-10:]
            out["flows"] = f
        else:
            log(f"fii/dii: unexpected response {str(j)[:200]}")
    except Exception as e:
        log(f"fii/dii failed: {e}")


# ----------------------------------------------------------------- news (Google News RSS)
def news(out):
    feeds = [("Markets", "Sensex Nifty stock market"), ("IPO", "IPO GMP subscription India"),
             ("Results", "quarterly results NSE"), ("Economy", "RBI rupee India economy")]
    items = []
    for tag, q in feeds:
        try:
            x = get("https://news.google.com/rss/search", params={"q": q + " when:2d", "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}).content
            for it in ET.fromstring(x).iter("item"):
                title = it.findtext("title") or ""
                src = it.findtext("source") or ""
                if src and title.endswith(" - " + src):
                    title = title[: -len(src) - 3]
                pub = it.findtext("pubDate") or ""
                try:
                    d = dt.datetime.strptime(pub[:25], "%a, %d %b %Y %H:%M:%S").replace(tzinfo=dt.timezone.utc).astimezone(IST)
                except ValueError:
                    d = NOW
                items.append({"tag": tag, "t": title, "s": src, "d": d.strftime("%-d %b, %-I:%M %p"), "u": it.findtext("link"), "_ts": d.timestamp()})
                if sum(1 for i in items if i["tag"] == tag) >= 4:
                    break
        except Exception as e:
            log(f"news {tag} failed: {e}")
    if len(items) >= 4:
        items.sort(key=lambda i: -i["_ts"])
        for i in items:
            i.pop("_ts")
        out["news"] = items[:14]


# ----------------------------------------------------------------- F&O stock list (refreshed once a day)
FNO_IDX = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "SENSEX", "BANKEX"}
def fno(out):
    old = out.get("fno") or {}
    if old.get("date") == NOW.strftime("%Y-%m-%d") and len(old.get("syms") or {}) > 100:
        return
    syms = {}
    for url in ("https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv", "https://archives.nseindia.com/content/fo/fo_mktlots.csv"):
        try:
            txt = get(url, headers={**UA, "Referer": "https://www.nseindia.com/"}).text
            for line in txt.splitlines():
                c = [x.strip() for x in line.split(",")]
                if len(c) < 3 or not c[1] or c[1].upper() in ("SYMBOL", "") or c[1].upper() in FNO_IDX or c[1].upper().startswith("NIFTY"):
                    continue
                lot = next((int(float(x)) for x in c[2:] if re.fullmatch(r"\d+(\.0+)?", x or "")), None)
                if re.fullmatch(r"[A-Z0-9&\-]{2,20}", c[1].upper()) and lot:
                    syms[c[1].upper()] = lot
            if len(syms) > 100:
                break
        except Exception as e:
            log(f"fno csv {url.split('/')[2]}: {e}")
    if len(syms) < 100:  # fallback: NSE's underlying list (no lot sizes)
        try:
            nse_session()
            j = get("https://www.nseindia.com/api/underlying-information", headers={**UA, "Referer": "https://www.nseindia.com/products-services/equity-derivatives-list-underlyings-information"}).json()
            for r in (j.get("data") or {}).get("UnderlyingList") or []:
                sy = str(r.get("symbol") or "").upper()
                if sy and sy not in FNO_IDX:
                    syms.setdefault(sy, (old.get("syms") or {}).get(sy) or 0)
        except Exception as e:
            log(f"fno api: {e}")
    if len(syms) > 100:
        out["fno"] = {"date": NOW.strftime("%Y-%m-%d"), "syms": syms}
    else:
        log(f"fno: only {len(syms)} symbols, keeping previous list")


# ----------------------------------------------------------------- BSE all-market gainers & losers (live, includes BSE-only stocks)
def bse_movers(out):
    res, sample = {}, None
    for gl in ("gainer", "loser"):
        try:
            S.get("https://www.bseindia.com/", timeout=20)
            j = get(f"https://api.bseindia.com/BseIndiaAPI/api/MktRGainerLoserData/w?GLtype={gl}&IndxGrp=AllMkt&IndxGrpval=AllMkt&orderby=all",
                    headers={"Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"}).json()
            rows = j if isinstance(j, list) else (j.get("Table") or j.get("table") or next((v for v in j.values() if isinstance(v, list)), []))
            if rows and sample is None:
                sample = {k: rows[0][k] for k in list(rows[0])[:14]}
            def pick(r, *names):
                for k in r:
                    kl = k.lower().replace("_", "")
                    if any(n in kl for n in names):
                        return r[k]
            lst = []
            for r in rows[:60]:
                code = str(pick(r, "scripcd", "scripcode", "scrip_cd") or "").strip()
                name = str(pick(r, "longname") or pick(r, "scripname", "shortname", "companyname") or "").strip()
                if re.search(r"-RE\d*$", str(r.get("scripname", ""))) or str(r.get("scrip_grp", "")).upper() in ("RE",):
                    continue  # rights entitlements, not shares
                try:
                    ltp = float(str(pick(r, "ltradert", "ltp", "lastrate", "currrate", "close") or "").replace(",", ""))
                    pct = float(str(pick(r, "changepercent", "perchg", "pctchange", "chgper", "percent") or "").replace(",", ""))
                except ValueError:
                    continue
                if code and name:
                    try:
                        pv = float(str(pick(r, "prevdayclose", "prevclose") or "").replace(",", "")) or None
                    except ValueError:
                        pv = None
                    lst.append([code, re.sub(r"\s+(Limited|Ltd\.?)$", "", name, flags=re.I), ltp, pct, pv])
            res["g" if gl == "gainer" else "l"] = lst
        except Exception as e:
            log(f"bse movers {gl}: {e}")
    if res.get("g") or res.get("l"):
        out["bse_movers"] = {"at": NOW.strftime("%-d %b, %-I:%M %p"), **res}
    elif sample is None:
        log("bse movers: empty")
    if sample is not None and not (res.get("g") or res.get("l")):
        log(f"bse movers sample: {json.dumps(sample)[:300]}")


def main():
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, "live.json")
    try:
        out = json.load(open(path))
    except Exception:
        out = {}
    fast = "--fast" in sys.argv
    for step in ((markets, nse_movers, mcx, bse_movers) if fast else (markets, nse_movers, bse_movers, metals, city_metals, ipo_calendar, ipo, flows, news, fno, results_cal, everything)):
        try:
            step(out)
        except Exception as e:
            log(f"{step.__name__} crashed: {e}")
    if not fast:
        out["fulllog"] = LOG[-30:]
    logos_dir = os.path.join(ROOT, "logos")
    out["logos"] = sorted(f[:-4] for f in os.listdir(logos_dir) if f.lower().endswith(".png")) if os.path.isdir(logos_dir) else []
    out["updated"] = NOW.isoformat(timespec="seconds")
    out["label"] = NOW.strftime("%-d %b %Y, %-I:%M %p IST")
    out["log"] = LOG[-30:]
    json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)
    open(os.path.join(DATA, "live.js"), "w").write("window.LIVE=" + json.dumps(out, ensure_ascii=False) + ";\n")
    print(f"wrote data, {len(LOG)} warnings")


if __name__ == "__main__":
    sys.exit(main())
