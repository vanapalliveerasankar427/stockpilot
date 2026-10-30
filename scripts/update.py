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
        [k + ".NS" for k in EXTRA_LARGE] + ["INR=X", "BZ=F", "GC=F"]
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
    prev_days = sorted(d for d in eod if d < today)
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
    stamp = NOW.strftime("%-d %b, %-I:%M %p")
    try:
        rows = list(table_rows(get("https://www.ipomarket.in/gmp").text))
        for iid, key in IPOS.items():
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
            iid = next((k for k, key in IPOS.items() if key.lower() in title), None)
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
              "priceToBook,trailingAnnualDividendYield,regularMarketTime")

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
                              q.get("regularMarketTime")]
    if len(out) < len(ysyms) * 0.5:
        # fallback: one chart request per NSE symbol (price, change, day range, 52-week range)
        log(f"batch quotes gave {len(out)}; using per-symbol fallback for NSE")
        nse = [s for s in ysyms if s.endswith(".NS") and key_of[s] not in out]

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
    # BSE-only scrips that Yahoo doesn't price: use BSE's official close from its daily price file
    for r in uni.get("s", []):
        if r[0] in out or len(r) < 6 or not r[5] or r[5][0] is None:
            continue
        c, pv, o, h, l, v, day = r[5]
        out[r[0]] = [c, round((c / pv - 1) * 100, 2) if pv else None, pv, o, h, l, None, None, v, None, None, None, None, None, "BSE close " + day]
    return out


def everything(out):
    os.makedirs(OUT_EXTRA, exist_ok=True)
    uni = universe()
    json.dump(uni, open(os.path.join(OUT_EXTRA, "universe.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    q = all_quotes(uni)
    if q:
        json.dump({"updated": NOW.isoformat(timespec="seconds"), "label": NOW.strftime("%-d %b %Y, %-I:%M %p IST"),
                   "cols": ["price", "pct", "prev", "open", "high", "low", "h52", "l52", "vol", "mcapCr", "pe", "eps", "pb", "dy", "t"], "q": q},
                  open(os.path.join(OUT_EXTRA, "quotes.json"), "w"), separators=(",", ":"))
    out["universe"] = {"stocks": len(uni.get("s", [])), "quotes": len(q), "at": NOW.strftime("%-d %b, %-I:%M %p")}


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


def main():
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, "live.json")
    try:
        out = json.load(open(path))
    except Exception:
        out = {}
    fast = "--fast" in sys.argv
    for step in ((markets, nse_movers, mcx) if fast else (markets, nse_movers, metals, ipo, flows, news, everything)):
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
