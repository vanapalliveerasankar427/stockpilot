"""Growth screen: companies with steady revenue and profit growth at a sensible valuation,
with a 1-year and 2-year price scenario if that growth continues. Runs once a day.

Reads the "hist" snapshot (./hist/h/*.json: reported results) and the all-stock quotes,
writes data/growth.json."""
import datetime as dt, glob, json, os, sys
import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
NOW = dt.datetime.now(IST)
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = "https://raw.githubusercontent.com/vanapalliveerasankar427/stockpilot/data/"


def cagr(a, b, years):
    if a is None or b is None or a <= 0 or b <= 0 or years <= 0:
        return None
    return (b / a) ** (1 / years) - 1


def last(f, k):
    return [v for _, v in sorted(f.get(k) or [])]


def main():
    q = requests.get(RAW + "quotes.json", timeout=60).json()
    cols = q["cols"]; ci = {c: i for i, c in enumerate(cols)}
    uni = {r[0]: r for r in requests.get(RAW + "universe.json", timeout=60).json()["s"]}
    try:
        sec = json.load(open(os.path.join(ROOT, "hist", "profiles.json"))).get("sec", {})
    except Exception:
        sec = {}
    tnum = lambda v: v if isinstance(v, (int, float)) else 0
    newest = max(tnum(v[ci["t"]]) for v in q["q"].values())
    items, screened = [], 0
    for path in glob.glob(os.path.join(ROOT, "hist", "h", "*.json")):
        key = os.path.basename(path)[:-5]
        try:
            j = json.load(open(path))
        except Exception:
            continue
        f = j.get("f") or {}
        row = q["q"].get(key)
        if not f or not row or key not in uni:
            continue
        px, mc, t = row[ci["price"]], row[ci["mcapCr"]], tnum(row[ci["t"]])
        if not px or not mc or newest - t > 5 * 86400:
            continue
        screened += 1
        QR, QN = last(f, "quarterlyTotalRevenue"), last(f, "quarterlyNetIncome")
        AR, AN = last(f, "annualTotalRevenue"), last(f, "annualNetIncome")
        if len(QN) < 4 or len(AR) < 3 or len(AN) < 3:
            continue
        ttm = sum(QN[-4:])
        if ttm <= 0 or min(QN[-4:]) <= 0:
            continue                       # profitable every one of the last four quarters
        n = min(len(AR), len(AN), 4) - 1   # up to 3 years of growth
        rg, pg = cagr(AR[-n - 1], AR[-1], n), cagr(AN[-n - 1], AN[-1], n)
        if rg is None or pg is None or rg < 0.15 or pg < 0.20:
            continue                       # revenue +15%/yr and profit +20%/yr over the period
        if min(AN[-n - 1:]) <= 0:
            continue
        qrg = QR[-1] / QR[-5] - 1 if len(QR) >= 5 and QR[-5] > 0 else None
        qpg = QN[-1] / QN[-5] - 1 if len(QN) >= 5 and QN[-5] > 0 else None
        if (qrg is not None and qrg < 0.10) or (qpg is not None and qpg < 0.0):
            continue                       # growth still going in the latest quarter
        pe = mc / ttm
        g = min(0.30, 0.5 * min(rg, 0.6) + 0.5 * min(pg, 0.6))  # growth used for the scenario: one-off jumps damped, capped at 30%/yr
        peg = pe / (g * 100)
        if pe > 60 or peg > 1.5 or mc < 50:
            continue                       # not already priced for perfection; skip tiny shells
        eq, debt, ocf = last(f, "annualStockholdersEquity"), last(f, "annualTotalDebt"), last(f, "annualOperatingCashFlow")
        roe = AN[-1] / eq[-1] if eq and eq[-1] > 0 else None
        de = debt[-1] / eq[-1] if debt and eq and eq[-1] > 0 else None
        if (de is not None and de > 1.0) or (roe is not None and roe < 0.12):
            continue
        cash_ok = ocf[-1] > 0 if ocf else None
        # quality score: growth, cheapness vs growth, returns, consistency
        score = (min(g, 0.3) / 0.3) * 40 + max(0, 1.5 - peg) / 1.5 * 25 + (min(roe, 0.35) / 0.35 * 15 if roe else 7) \
            + (10 if all(b > a for a, b in zip(AR[-n - 1:], AR[-n:])) else 0) + (10 if cash_ok else 5 if cash_ok is None else 0)
        proj = lambda yrs: [round(px * (1 + g * 0.5) ** yrs * 0.85, 2), round(px * (1 + g) ** yrs, 2), round(px * (1 + min(g * 1.25, 0.4)) ** yrs * 1.1, 2)]
        u = uni[key]
        items.append({"k": key, "n": u[1], "x": u[2], "px": px, "mc": round(mc), "pe": round(pe, 1), "peg": round(peg, 2),
                      "rg": round(rg * 100, 1), "pg": round(pg * 100, 1), "yrs": n,
                      "qrg": round(qrg * 100, 1) if qrg is not None else None, "qpg": round(qpg * 100, 1) if qpg is not None else None,
                      "roe": round(roe * 100, 1) if roe is not None else None, "de": round(de, 2) if de is not None else None,
                      "cash": cash_ok, "g": round(g * 100, 1), "p1": proj(1), "p2": proj(2), "s": round(score),
                      "sec": (sec.get(key) or ["", ""])[0], "ttm": round(ttm, 1)})
    items.sort(key=lambda x: -x["s"])
    out = {"at": NOW.isoformat(timespec="seconds"), "label": NOW.strftime("%-d %b %Y"), "screened": screened, "items": items}
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "data", "growth.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"screened {screened}, passed {len(items)}")


if __name__ == "__main__":
    sys.exit(main())
