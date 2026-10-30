# MarketVedaPro

**Know More. Invest Smarter.**

Financial markets and investment information for Indian and global market followers: stock market prices and trends, IPOs (upcoming, open, GMP, subscription, allotment and listing), daily gold and silver rates, market news and market insights.

**Live site:** https://marketvedapro.com/

## How the data updates
`.github/workflows/data.yml` runs `scripts/update.py` every 5 minutes during NSE hours (Mon–Fri, 9:10 AM–3:45 PM IST) and every 2 hours otherwise. Open pages read `data/live.json` straight from this repository every 2 minutes, so new figures appear without republishing. It collects:

| Data | Source |
|---|---|
| Nifty, Sensex, Bank Nifty, Midcap, Smallcap, VIX, sectors, stock prices | NSE/BSE via Yahoo Finance |
| USD/INR, Brent crude, world gold | Yahoo Finance |
| Gold and silver (official benchmark) | IBJA (ibjarates.com) |
| Gold and silver MCX futures | India Bullions |
| Jeweller retail rates | Goodreturns |
| IPO GMP and subscription | IPOMarket |
| FII / DII flows | NSE |
| News | Google News |

The results go to `data/live.json` / `data/live.js`, which the page loads. If a source fails, the last good values stay. Open pages reload themselves when newer figures arrive.

Run it by hand any time: **Actions → Update data → Run workflow**.

New IPOs (dates, price band, lot size) are added in `index.html` (`IPOS_RAW`).
