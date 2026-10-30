# Allotment relay (Cloudflare Worker)

Lets MarketVedaPro check IPO allotment by PAN right on the site, for registrars that accept a PAN without a captcha (MUFG Intime, KFintech, Maashitla). The worker does not store or log PANs. Browsers can't call registrar sites directly, so this small relay is needed.

## One-tap setup (works from a phone)
[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/vanapalliveerasankar427/stockpilot/tree/main/worker)

Tap the button, sign in or sign up (free), allow GitHub, tap **Deploy**. Copy the `…workers.dev` address it shows.

## Manual setup (about 5 minutes, free)
1. Sign up at https://dash.cloudflare.com/sign-up (free plan).
2. **Workers & Pages → Create → Create Worker** → name it `mvp-allot` → **Deploy**.
3. **Edit code** → delete everything → paste all of `allotment.js` → **Deploy**.
4. Copy the address shown, e.g. `https://mvp-allot.<your-name>.workers.dev`, and set it as `ALLOT_API` in `index.html`.
