# StockPilot

Indian stocks and IPOs: market overview, gold and silver, IPO GMP, subscription, allotment and application tracking.

**Live site:** https://vanapalliveerasankar427.github.io/stockpilot/

## How the data updates
`.github/workflows/update.yml` runs `scripts/update.py` every 10 minutes during NSE hours (Mon–Fri, 9:00 AM–4:00 PM IST) and every 2 hours otherwise. It collects:

| Data | Source |
|---|---|
| Nifty, Sensex, Bank Nifty, Midcap, Smallcap, VIX, sectors, stock prices | NSE/BSE via Yahoo Finance |
| USD/INR, Brent crude, world gold | Yahoo Finance |
| Gold 24K/22K/18K, silver | Goodreturns |
| IPO GMP and subscription | IPOMarket |
| FII / DII flows | NSE |
| News | Google News |

The results go to `data/live.json` / `data/live.js`, which the page loads. If a source fails, the last good values stay. Open pages reload themselves when newer figures arrive.

Run it by hand any time: **Actions → Update data and publish → Run workflow**.

New IPOs (dates, price band, lot size) are added in `index.html` (`IPOS_RAW`).
