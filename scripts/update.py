#!/usr/bin/env python3
"""StockPilot data updater.

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
    with ThreadPoolExecutor(max_workers=12) as ex:
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
        if cells and k in cells[0].lower():
            return cells
    return None


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
        rows = list(table_rows(get("https://www.ipomarket.in/subscription").text))
        for iid, key in IPOS.items():
            c = find_row(rows, key)
            if not c:
                continue
            xs = [x for x in c if re.fullmatch(r"[\d,.]+\s*[x×]", x, re.I)]
            if xs:
                data.setdefault(iid, {}).update(sub=num(re.sub(r"[x×]", "", xs[-1], flags=re.I)), ssrc="IPOMarket", sat=stamp)
    except Exception as e:
        log(f"subscription failed: {e}")
    out["ipo"] = data



# ----------------------------------------------------------------- NSE index constituents (live movers)
def nse_session():
    if not getattr(nse_session, "ok", False):
        S.get("https://www.nseindia.com/", timeout=20)
        nse_session.ok = True


def nse_movers(out):
    """Nifty 50, Midcap 100 and Smallcap 100 movers straight from NSE."""
    names = {"NIFTY 50": "n50", "NIFTY MIDCAP 100": "mid", "NIFTY SMALLCAP 100": "small"}
    for index, key in names.items():
        try:
            nse_session()
            j = get("https://www.nseindia.com/api/equity-stockIndices", params={"index": index},
                    headers={"Referer": "https://www.nseindia.com/market-data/live-equity-market"}).json()
            rows = [r for r in j.get("data", []) if r.get("symbol") and r.get("symbol") != index and r.get("priority", 0) == 0]
            mv = []
            for r in rows:
                try:
                    nm = (r.get("meta") or {}).get("companyName") or r["symbol"]
                    nm = re.sub(r"\s+(Limited|Ltd\.?)$", "", nm)
                    mv.append([r["symbol"], nm, round(float(r["pChange"]), 2), float(r["lastPrice"])])
                except (KeyError, TypeError, ValueError):
                    pass
            if len(mv) < 10:
                log(f"nse {index}: only {len(mv)} rows")
                continue
            mv.sort(key=lambda x: -x[2])
            up = [m for m in mv if m[2] > 0]
            dn = [m for m in reversed(mv) if m[2] < 0]
            stamp = (j.get("timestamp") or NOW.strftime("%d-%b-%Y %H:%M"))
            if key == "n50":
                out["gainers"] = [m[:3] for m in up[:5]]
                out["losers"] = [m[:3] for m in dn[:5]]
                out["breadth"] = {"up": len(up), "n": len(mv), "label": "Nifty 50 stocks"}
                # NSE last price for the 25 stocks on the Stocks page
                st = out.setdefault("stocks", {})
                for m in mv:
                    k = "MM" if m[0] == "M&M" else m[0]
                    if k in STOCKS:
                        st[k] = {"v": m[3], "pct": m[2]}
            else:
                out[key + "g"] = [[m[1], m[2]] for m in up[:5]]
                out[key + "l"] = [[m[1], m[2]] for m in dn[:5]]
            out.setdefault("nse", {})[key] = stamp
        except Exception as e:
            log(f"nse {index} failed: {e}")


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
        if "fii" in f and "dii" in f:
            out["flows"] = f
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
    for step in ((markets, nse_movers, mcx) if fast else (markets, nse_movers, metals, ipo, flows, news)):
        try:
            step(out)
        except Exception as e:
            log(f"{step.__name__} crashed: {e}")
    if fast:
        out["log"] = LOG[-30:]
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
