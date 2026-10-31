// Builds crawlable static pages for search engines: IPO pages, GMP, allotment, gold/silver, share prices, market today,
// plus sitemap.xml and robots.txt. Runs in the publish workflow. Every page links to the live app.
// Usage: node scripts/seo.js <site-dir>
const fs = require("fs"), path = require("path");
process.on("uncaughtException", e => { console.log("::error::seo " + (e.stack || e).toString().replace(/\n/g, " | ")); process.exitCode = 0; });
process.on("unhandledRejection", e => { console.log("::error::seo " + (e && e.stack || e).toString().replace(/\n/g, " | ")); process.exitCode = 0; });
const ROOT = process.argv[2] || ".";
const SITE = "https://marketvedapro.com";
const RAW = "https://raw.githubusercontent.com/vanapalliveerasankar427/stockpilot/";
const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
const live = JSON.parse(fs.readFileSync(path.join(ROOT, "data/live.json"), "utf8"));
const NOW = new Date(Date.now() + 330 * 60000);
const TODAY = NOW.toISOString().slice(0, 10);
const LABEL = NOW.toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

const evalArr = (start) => { const s = html.indexOf(start); if (s < 0) return []; const e = html.indexOf("\n];", s); return Function('"use strict";return ' + html.slice(s + start.length - 1, e + 2))(); };
const IPOS = evalArr("const IPOS_RAW=[");
const PAST = evalArr("const PAST_RAW=[").map(([id, name, type, open, close, allot]) => ({ id, name, type, open, close, allot, past: true }));
const L = live.ipo || {};

const esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const inr = (n, d = 0) => n == null || isNaN(n) ? "—" : "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
const d2 = s => s ? new Date(s + "T00:00:00Z").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "TBA";
const slug = s => String(s).toLowerCase().replace(/&/g, "and").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const short = n => String(n).replace(/ (Ltd|Limited)\.?$/i, "");
const pct = n => n == null || isNaN(n) ? "" : `<span class="${n >= 0 ? "u" : "d"}">${n >= 0 ? "+" : ""}${Number(n).toFixed(2)}%</span>`;
const pages = [];

const CSS = `*{box-sizing:border-box;margin:0}body{font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:linear-gradient(160deg,#ffefe5,#f3ecff 50%,#e7f7ef);color:#0b0b0f;line-height:1.55;min-height:100vh}
a{color:#0a7a5a}header{position:sticky;top:0;z-index:5;background:rgba(255,255,255,.82);backdrop-filter:blur(16px);border-bottom:1px solid rgba(0,0,0,.06)}
.hw{max-width:1100px;margin:0 auto;display:flex;align-items:center;gap:14px;padding:12px 18px;flex-wrap:wrap}.lo{display:flex;align-items:center;gap:9px;font:800 19px system-ui;color:#0b0b0f;text-decoration:none;letter-spacing:-.02em}
.mk{width:32px;height:32px;border-radius:10px;background:linear-gradient(135deg,#12B886,#0A4D55);display:grid;place-items:center}.pro{font-size:12px;padding:2px 6px;border-radius:6px;background:linear-gradient(135deg,#F5B833,#E8590C);color:#fff;margin-left:2px}
nav.n{display:flex;gap:4px;flex-wrap:wrap;margin-left:auto}nav.n a{padding:7px 11px;border-radius:999px;color:#555;text-decoration:none;font-size:14px;font-weight:600}nav.n a:hover{background:#0b0b0f;color:#fff}
main{max-width:1100px;margin:0 auto;padding:22px 18px 60px}h1{font:800 clamp(28px,5vw,44px)/1.1 system-ui;letter-spacing:-.03em;margin:8px 0 10px}h2{font:800 22px system-ui;letter-spacing:-.02em;margin:28px 0 10px}
.sub{color:#555;font-size:16px;max-width:760px}.ey{font-size:13px;color:#666;font-weight:600}.card{background:rgba(255,255,255,.85);border:1px solid rgba(0,0,0,.06);border-radius:20px;padding:16px;margin-top:14px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14.5px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid rgba(0,0,0,.06);white-space:nowrap}th{font-size:12.5px;color:#666;text-transform:uppercase;letter-spacing:.04em}
.u{color:#059669;font-weight:700}.d{color:#e11d48;font-weight:700}.cta{display:inline-flex;align-items:center;gap:8px;margin-top:16px;padding:13px 20px;border-radius:999px;background:#0b0b0f;color:#fff;text-decoration:none;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}.kv{background:rgba(255,255,255,.85);border:1px solid rgba(0,0,0,.06);border-radius:16px;padding:12px}.kv span{display:block;font-size:12.5px;color:#666}.kv b{font-size:18px}
.faq details{background:rgba(255,255,255,.85);border:1px solid rgba(0,0,0,.06);border-radius:14px;padding:12px 14px;margin-top:8px}.faq summary{font-weight:700;cursor:pointer}.faq p{margin-top:8px;color:#444}
.links{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.links a{padding:6px 11px;border-radius:999px;background:rgba(255,255,255,.85);border:1px solid rgba(0,0,0,.07);text-decoration:none;font-size:13.5px;color:#222}
footer{max-width:1100px;margin:0 auto;padding:24px 18px 50px;color:#666;font-size:13px}.crumb{font-size:13px;color:#666}.crumb a{color:#666}`;

function page(rel, { title, desc, h1, sub, body, ld = [], crumbs = [] }) {
  const url = SITE + "/" + rel + (rel ? "/" : "");
  const bc = { "@context": "https://schema.org", "@type": "BreadcrumbList", itemListElement: [{ name: "MarketVedaPro", url: SITE + "/" }, ...crumbs].map((c, i) => ({ "@type": "ListItem", position: i + 1, name: c.name, item: c.url })) };
  const doc = `<!doctype html><html lang="en-IN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title><meta name="description" content="${esc(desc)}"><link rel="canonical" href="${url}">
<meta name="robots" content="index,follow,max-image-preview:large"><meta name="theme-color" content="#0A4D55">
<meta property="og:type" content="website"><meta property="og:site_name" content="MarketVedaPro"><meta property="og:title" content="${esc(title)}"><meta property="og:description" content="${esc(desc)}">
<meta property="og:url" content="${url}"><meta property="og:image" content="${SITE}/icons/og-image.png"><meta property="og:locale" content="en_IN"><meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/icons/favicon-64.png"><link rel="apple-touch-icon" href="/icons/apple-touch-icon.png"><link rel="manifest" href="/manifest.webmanifest">
<script type="application/ld+json">${JSON.stringify([bc, ...ld])}</script><style>${CSS}</style></head><body>
<header><div class="hw"><a class="lo" href="/"><span class="mk"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l6-6 4 3 8-8"/><path d="M15 6h6v6"/></svg></span>MarketVeda<span class="pro">Pro</span></a>
<nav class="n"><a href="/stock-market-today/">Market today</a><a href="/ipo/">IPOs</a><a href="/ipo-gmp/">IPO GMP</a><a href="/ipo-allotment-status/">Allotment</a><a href="/gold-rate-today/">Gold</a><a href="/silver-rate-today/">Silver</a></nav></div></header>
<main>${crumbs.length ? `<p class="crumb"><a href="/">Home</a>${crumbs.map(c => ` › <a href="${c.url}">${esc(c.name)}</a>`).join("")}</p>` : ""}
<p class="ey">Updated ${esc(LABEL)}</p><h1>${esc(h1)}</h1>${sub ? `<p class="sub">${sub}</p>` : ""}${body}</main>
<footer><p><b>MarketVedaPro</b> · Know More. Invest Smarter. · <a href="/#terms">Terms</a> · <a href="/#privacy">Privacy</a></p>
<p style="margin-top:6px">Information only, not investment advice. MarketVedaPro is not registered with SEBI. Prices may be delayed; GMP is unofficial. Confirm on NSE, BSE, the registrar or your broker before acting.</p></footer></body></html>`;
  const dir = path.join(ROOT, rel);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "index.html"), doc);
  pages.push({ url, pri: rel.split("/").length <= 1 ? "0.9" : "0.7" });
}
const faq = qa => ({ "@context": "https://schema.org", "@type": "FAQPage", mainEntity: qa.map(([q, a]) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })) });
const faqHTML = qa => `<h2>Frequently asked questions</h2><div class="faq">${qa.map(([q, a]) => `<details><summary>${esc(q)}</summary><p>${esc(a)}</p></details>`).join("")}</div>`;

// ---------------------------------------------------------------- IPOs
const status = i => { const t = TODAY; if (t < i.open) return "Upcoming"; if (t <= i.close) return "Open"; if (i.list && t >= i.list) return "Listed"; if (i.allot && t >= i.allot) return "Allotment out"; return "Closed"; };
const gmpOf = i => (L[i.id] && L[i.id].gmp != null) ? L[i.id].gmp : (i.gmp ? i.gmp.v : null);
const subOf = i => (L[i.id] && L[i.id].sub != null) ? L[i.id].sub : (i.sub ? i.sub.total : null);
const ipoSlug = i => slug(short(i.name)) + "-ipo";
const allIpos = [...IPOS, ...PAST];

function ipoPage(i) {
  const g = gmpOf(i), s = subOf(i), st = status(i), n = short(i.name), gp = g != null && i.hi ? g / i.hi * 100 : null;
  const est = g != null && i.lot ? g * i.lot * (i.minLots || 1) : null;
  const qa = [
    [`What is the ${n} IPO GMP today?`, g != null ? `The ${n} IPO grey market premium (GMP) is ₹${g} as of ${LABEL}${gp != null ? `, about ${gp.toFixed(1)}% over the upper price band of ₹${i.hi}` : ""}. GMP is unofficial and changes often.` : `GMP for the ${n} IPO is not available yet.`],
    [`When is the ${n} IPO allotment date?`, `The basis of allotment for the ${n} IPO is expected on ${d2(i.allot)}.${i.reg ? ` The registrar is ${i.reg}.` : ""}`],
    [`How do I check ${n} IPO allotment status?`, `Open MarketVedaPro's allotment page, save your family's PANs once and check everyone in one tap. You can also check on the registrar${i.reg ? ` (${i.reg})` : ""} or BSE website using your PAN.`],
    ...(i.list ? [[`When will ${n} shares list?`, `${n} shares are expected to list on ${d2(i.list)} on ${i.exch || (i.type === "SME" ? "the SME platform" : "BSE and NSE")}.`]] : []),
    ...(i.hi ? [[`What is the ${n} IPO price band and lot size?`, `The price band is ₹${i.lo}–${i.hi} per share${i.lot ? ` with a lot size of ${i.lot} shares (minimum ${inr(i.lot * i.hi * (i.minLots || 1))} at the upper band)` : ""}.`]] : []),
  ];
  const kv = [["Status", st], ["Price band", i.hi ? (i.lo === i.hi ? inr(i.hi) : `₹${i.lo}–${i.hi}`) : "—"], ["GMP", g != null ? `₹${g}${gp != null ? ` (${gp.toFixed(1)}%)` : ""}` : "—"], ["Subscription", s != null ? Number(s).toFixed(2) + "×" : "—"],
    ["Lot size", i.lot ? i.lot + " shares" : "—"], ["Issue size", i.size ? "₹" + i.size + " Cr" : "—"], ["Type", i.type || "—"], ["Registrar", i.reg || "—"]];
  const tl = [["Opens", i.open], ["Closes", i.close], ["Allotment", i.allot], ["Refund", i.refund], ["Listing", i.list]].filter(x => x[1]);
  page("ipo/" + ipoSlug(i), {
    title: `${n} IPO GMP Today, Allotment Status, Price Band & Listing Date | MarketVedaPro`,
    desc: `${n} IPO${g != null ? ` GMP ₹${g} today` : ""}, price band ${i.hi ? `₹${i.lo}–${i.hi}` : "TBA"}, lot size, subscription, allotment date ${d2(i.allot)} and listing date. Check ${n} IPO allotment status for your whole family.`,
    h1: `${n} IPO: GMP, allotment status and dates`,
    sub: `${esc(n)} ${i.type === "SME" ? "SME" : "mainboard"} IPO${i.sector ? ` (${esc(i.sector)})` : ""}. Status: <b>${st}</b>.${est != null ? ` Estimated listing gain per application at today's GMP: <b>${inr(est)}</b> (unofficial).` : ""}`,
    crumbs: [{ name: "IPOs", url: SITE + "/ipo/" }, { name: n + " IPO", url: SITE + "/ipo/" + ipoSlug(i) + "/" }],
    ld: [faq(qa)],
    body: `${i.hi ? `<div class="grid" style="margin-top:16px">${kv.map(([k, v]) => `<div class="kv"><span>${k}</span><b>${esc(v)}</b></div>`).join("")}</div>` : ""}
      <h2>${esc(n)} IPO dates</h2><div class="card"><table><tr><th>Event</th><th>Date</th></tr>${tl.map(([k, v]) => `<tr><td>${k}</td><td>${d2(v)}</td></tr>`).join("")}</table></div>
      <h2>Check ${esc(n)} IPO allotment status</h2><p class="sub">Save your family's PANs once in MarketVedaPro and check everyone's allotment in one tap. PANs stay on your phone.</p>
      <a class="cta" href="/#allot-${esc(i.id)}">Check allotment for my family →</a>
      ${faqHTML(qa)}
      <h2>More IPOs</h2><div class="links">${allIpos.filter(x => x.id !== i.id).slice(0, 24).map(x => `<a href="/ipo/${ipoSlug(x)}/">${esc(short(x.name))} IPO</a>`).join("")}</div>`
  });
}
allIpos.forEach(ipoPage);

const ipoRow = i => { const g = gmpOf(i); return `<tr><td><a href="/ipo/${ipoSlug(i)}/">${esc(short(i.name))}</a></td><td>${i.type === "SME" ? "SME" : "Mainboard"}</td><td>${i.hi ? (i.lo === i.hi ? inr(i.hi) : `₹${i.lo}–${i.hi}`) : "—"}</td><td>${g != null ? `₹${g}${i.hi ? ` <small>(${(g / i.hi * 100).toFixed(1)}%)</small>` : ""}` : "—"}</td><td>${d2(i.open)}–${d2(i.close)}</td><td>${status(i)}</td></tr>`; };
const ipoTable = list => `<div class="card"><table><tr><th>IPO</th><th>Type</th><th>Price</th><th>GMP</th><th>Dates</th><th>Status</th></tr>${list.map(ipoRow).join("")}</table></div>`;
const cur = IPOS.slice().sort((a, b) => (a.close < b.close ? 1 : -1));
page("ipo", {
  title: `Upcoming IPO ${NOW.getUTCFullYear()}: Current IPOs, GMP, Dates & Allotment | MarketVedaPro`,
  desc: `All open and upcoming IPOs in India (mainboard and SME) with live GMP, price band, lot size, subscription, allotment and listing dates. Updated ${LABEL}.`,
  h1: "IPOs today: open, upcoming and listed",
  sub: "Every current mainboard and SME IPO in India with GMP, price band, dates and status.",
  crumbs: [{ name: "IPOs", url: SITE + "/ipo/" }],
  body: ipoTable(cur) + `<a class="cta" href="/#ipos">Open live IPO tracker →</a><h2>Recent allotments</h2>` + ipoTable(PAST.slice(0, 40))
});
page("ipo-gmp", {
  title: `IPO GMP Today: Live Grey Market Premium of Upcoming IPOs | MarketVedaPro`,
  desc: `Latest IPO GMP (grey market premium) today for all mainboard and SME IPOs, with estimated listing gain, subscription and dates. Updated ${LABEL}.`,
  h1: "IPO GMP today",
  sub: "Grey market premium for every current IPO, with the % over the upper price band. GMP is unofficial and changes through the day.",
  crumbs: [{ name: "IPO GMP", url: SITE + "/ipo-gmp/" }],
  ld: [faq([["What is IPO GMP?", "GMP (grey market premium) is the unofficial premium at which IPO shares trade before listing. It hints at expected listing gains but is not guaranteed."], ["Is GMP reliable?", "No. GMP is unregulated and can change sharply. Use it only as one signal along with subscription and fundamentals."]])],
  body: ipoTable(cur.filter(i => status(i) !== "Listed")) + `<a class="cta" href="/#ipo-gmp">Open live GMP board →</a>` + faqHTML([["What is IPO GMP?", "GMP (grey market premium) is the unofficial premium at which IPO shares trade before listing. It hints at expected listing gains but is not guaranteed."], ["Is GMP reliable?", "No. GMP is unregulated and can change sharply. Use it only as one signal along with subscription and fundamentals."]])
});
const aq = [["How do I check IPO allotment status by PAN?", "On MarketVedaPro, save your family's PANs once, open the IPO under Allotment and every PAN is checked with the registrar automatically."], ["Which registrars are supported?", "KFintech, MUFG Intime (Link Intime), Bigshare, Maashitla, Purva and Skyline are checked automatically. Cameo needs a captcha, so we link you to its site."], ["Is my PAN safe?", "PANs are saved only on your device and sent only to the registrar for each lookup. They are never stored on our servers."]];
page("ipo-allotment-status", {
  title: `IPO Allotment Status: Check by PAN for Your Whole Family | MarketVedaPro`,
  desc: `Check IPO allotment status by PAN for KFintech, MUFG Intime (Link Intime), Bigshare, Maashitla and more. Save family PANs once and check everyone in one tap.`,
  h1: "IPO allotment status",
  sub: "Check allotment for every family member at once. Supports KFintech, MUFG Intime, Bigshare, Maashitla, Purva and Skyline.",
  crumbs: [{ name: "IPO allotment status", url: SITE + "/ipo-allotment-status/" }],
  ld: [faq(aq)],
  body: `<a class="cta" href="/#ipo-allot">Check allotment now →</a><h2>IPOs with allotment out</h2>` + `<div class="card"><table><tr><th>IPO</th><th>Type</th><th>Allotment date</th><th></th></tr>${allIpos.filter(i => i.allot && i.allot <= TODAY).sort((a, b) => a.allot < b.allot ? 1 : -1).slice(0, 80).map(i => `<tr><td><a href="/ipo/${ipoSlug(i)}/">${esc(short(i.name))}</a></td><td>${i.type === "SME" ? "SME" : "Mainboard"}</td><td>${d2(i.allot)}</td><td><a href="/#allot-${esc(i.id)}">Check status</a></td></tr>`).join("")}</table></div>` + faqHTML(aq)
});

// ---------------------------------------------------------------- gold & silver
const M = live.metals || {}, I = M.ibja || {}, R = M.retail || {}, X = M.mcx || {};
const gq = [["What is the gold rate today in India?", `On ${LABEL}, 24K gold is about ${inr(R.g24)} per gram and 22K about ${inr(R.g22)} per gram at jewellers (national average). The IBJA benchmark for 999 gold is ${inr(I.g999_10)} per 10 grams.`], ["Why do jewellers charge more than the gold rate?", "Jewellers add a local premium, 3% GST and making charges on top of the benchmark rate."]];
page("gold-rate-today", {
  title: `Gold Rate Today in India: 24K & 22K Gold Price per Gram (${LABEL}) | MarketVedaPro`,
  desc: `Gold rate today in India: 24K ${inr(R.g24)}/g, 22K ${inr(R.g22)}/g, 18K ${inr(R.g18)}/g. IBJA benchmark, live MCX gold and history. Updated ${LABEL}.`,
  h1: `Gold rate today in India (${LABEL})`,
  sub: "Jeweller retail rates, the official IBJA benchmark and live MCX gold futures, updated through the day.",
  crumbs: [{ name: "Gold rate today", url: SITE + "/gold-rate-today/" }],
  ld: [faq(gq)],
  body: `<div class="grid" style="margin-top:16px">${[["24K gold (1 g)", inr(R.g24)], ["22K gold (1 g)", inr(R.g22)], ["18K gold (1 g)", inr(R.g18)], ["24K gold (10 g)", inr(R.g24 * 10)], ["IBJA 999 (10 g)", inr(I.g999_10)], ["MCX gold (10 g)", inr(X.gold && X.gold.v)]].map(([k, v]) => `<div class="kv"><span>${k}</span><b>${v}</b></div>`).join("")}</div>
   <h2>IBJA gold rates</h2><div class="card"><table><tr><th>Purity</th><th>Per gram</th><th>Per 10 g</th></tr>${[["999 (24K)", I.g999], ["995", I.g995], ["916 (22K)", I.g916], ["750 (18K)", I.g750], ["585 (14K)", I.g585]].filter(x => x[1]).map(([k, v]) => `<tr><td>${k}</td><td>${inr(v)}</td><td>${inr(v * 10)}</td></tr>`).join("")}</table></div>
   <h2>Gold price last few days</h2><div class="card"><table><tr><th>Date</th><th>IBJA 999 (10 g)</th></tr>${(M.hist || []).slice().reverse().map(h => `<tr><td>${esc(h[0])}</td><td>${inr(h[1])}</td></tr>`).join("")}</table></div>
   <a class="cta" href="/#metals">See live gold price →</a>` + faqHTML(gq)
});
const sq = [["What is the silver rate today in India?", `On ${LABEL}, silver is about ${inr(R.ag, 2)} per gram (${inr(R.ag * 1000)} per kg) at jewellers. MCX silver futures are at ${inr(X.silver && X.silver.v)} per kg.`]];
page("silver-rate-today", {
  title: `Silver Rate Today in India: Silver Price per Kg & Gram (${LABEL}) | MarketVedaPro`,
  desc: `Silver rate today in India: ${inr(R.ag, 2)}/g, ${inr(R.ag * 1000)}/kg. IBJA silver benchmark and live MCX silver. Updated ${LABEL}.`,
  h1: `Silver rate today in India (${LABEL})`,
  sub: "Retail silver rate, IBJA benchmark and live MCX silver futures.",
  crumbs: [{ name: "Silver rate today", url: SITE + "/silver-rate-today/" }],
  ld: [faq(sq)],
  body: `<div class="grid" style="margin-top:16px">${[["Silver (1 g)", inr(R.ag, 2)], ["Silver (1 kg)", inr(R.ag * 1000)], ["IBJA silver (1 kg)", inr(I.ag ? I.ag * 1000 : null)], ["MCX silver (1 kg)", inr(X.silver && X.silver.v)]].map(([k, v]) => `<div class="kv"><span>${k}</span><b>${v}</b></div>`).join("")}</div>
   <h2>Silver price last few days</h2><div class="card"><table><tr><th>Date</th><th>IBJA silver (1 kg)</th></tr>${(M.hist || []).slice().reverse().filter(h => h[2]).map(h => `<tr><td>${esc(h[0])}</td><td>${inr(h[2])}</td></tr>`).join("")}</table></div>
   <a class="cta" href="/#metals">See live silver price →</a>` + faqHTML(sq)
});

// ---------------------------------------------------------------- market today + share prices (needs quote data from the data branch)
(async () => {
  let Q = {}, U = [], P = {};
  try { Q = (await (await fetch(RAW + "data/quotes.json")).json()).q || {}; } catch (e) { console.log("quotes unavailable", e.message); }
  try { U = (await (await fetch(RAW + "data/universe.json")).json()).s || []; } catch (e) { console.log("universe unavailable"); }
  try { P = (await (await fetch(RAW + "hist/profiles.json")).json()).p || {}; } catch (e) { console.log("profiles unavailable"); }
  const IDX = live.idx || {}, O = live.outlook || {};
  const row = x => `<tr><td><a href="/share-price/${slug(x.k)}/">${esc(x.n)}</a></td><td>${inr(x.p, 2)}</td><td>${pct(x.pct)}</td><td>${esc((x.why[0] || {}).t || "")}</td></tr>`;
  page("stock-market-today", {
    title: `Stock Market Today: Nifty, Sensex & Stocks in Focus (${LABEL}) | MarketVedaPro`,
    desc: `Stock market today: Nifty ${IDX.NIFTY ? IDX.NIFTY.v : ""}, Sensex ${IDX.SENSEX ? IDX.SENSEX.v : ""}. Stocks with positive and negative signals from results and news, global cues and top movers. Updated ${LABEL}.`,
    h1: `Stock market today (${LABEL})`,
    sub: "Nifty and Sensex, global cues, and stocks in focus today based on results, news and price action. Signals, not advice.",
    crumbs: [{ name: "Stock market today", url: SITE + "/stock-market-today/" }],
    body: `<div class="grid" style="margin-top:16px">${[["Nifty 50", IDX.NIFTY], ["Sensex", IDX.SENSEX], ["Bank Nifty", IDX.BANKNIFTY], ["Nifty Midcap 100", IDX.MIDCAP], ["Nifty Smallcap 100", IDX.SMALLCAP], ["India VIX", IDX.VIX]].filter(x => x[1]).map(([k, v]) => `<div class="kv"><span>${k}</span><b>${Number(v.v).toLocaleString("en-IN")}</b> ${pct(v.pct)}</div>`).join("")}</div>
     ${(O.cues || []).length ? `<p class="sub" style="margin-top:14px">Global cues: ${O.cues.map(esc).join(" · ")}</p>` : ""}
     <h2>Stocks with positive signals today</h2><div class="card"><table><tr><th>Stock</th><th>Price</th><th>Change</th><th>Why</th></tr>${(O.up || []).slice(0, 20).map(row).join("")}</table></div>
     <h2>Stocks with negative signals today</h2><div class="card"><table><tr><th>Stock</th><th>Price</th><th>Change</th><th>Why</th></tr>${(O.down || []).slice(0, 20).map(row).join("")}</table></div>
     <a class="cta" href="/#today">Open live outlook →</a>`
  });
  // share price pages for the biggest companies
  const names = Object.fromEntries(U.map(r => [r[0], r[1]]));
  const must = new Set(Object.keys(live.stocks || {}));
  const size = (k, v) => must.has(k) ? 1e12 : v[9] || ((v[0] || 0) * (v[8] || 0) > 5e8 ? 5e4 : 0);
  const top = Object.entries(Q).filter(([k, v]) => v && v[0] && names[k] && !k.startsWith("B") && size(k, v) > 0).sort((a, b) => size(...b) - size(...a)).slice(0, 900);
  for (const [k, v] of top) {
    const [price, pc, prev, open, high, low, h52, l52, vol, mc, pe, eps, pb, dy] = v, n = names[k], pr = P[k] || {};
    const qa = [[`What is ${n} share price today?`, `${n} (${k}) last traded at ₹${price} on NSE${pc != null ? `, ${pc >= 0 ? "up" : "down"} ${Math.abs(pc).toFixed(2)}%` : ""}, as of ${LABEL}.`],
      [`What is the 52-week high and low of ${n}?`, `The 52-week high is ₹${h52} and the 52-week low is ₹${l52}.`],
      ...(mc ? [[`What is the market cap of ${n}?`, `${n} has a market capitalisation of about ₹${Number(mc).toLocaleString("en-IN")} crore.`]] : [])];
    page("share-price/" + slug(k), {
      title: `${n} Share Price Today | ${k} Live NSE Price, Chart & News | MarketVedaPro`,
      desc: `${n} (${k}) share price today ₹${price}${pc != null ? ` (${pc >= 0 ? "+" : ""}${Number(pc).toFixed(2)}%)` : ""}. ${mc ? `Market cap ₹${Number(mc).toLocaleString("en-IN")} Cr` : "Live NSE price"}${pe ? `, P/E ${pe}` : ""}, 52-week high ₹${h52}, low ₹${l52}. Live chart and financials.`,
      h1: `${n} share price today`,
      sub: `${esc(k)} on NSE${pr.sector ? ` · ${esc(pr.sector)}${pr.industry ? " · " + esc(pr.industry) : ""}` : ""}.`,
      crumbs: [{ name: "Share prices", url: SITE + "/stock-market-today/" }, { name: n, url: SITE + "/share-price/" + slug(k) + "/" }],
      ld: [faq(qa)],
      body: `<div class="grid" style="margin-top:16px">${[["Price", inr(price, 2) + " " + (pc != null ? (pc >= 0 ? "▲" : "▼") + Math.abs(pc).toFixed(2) + "%" : "")], ["Previous close", inr(prev, 2)], ["Day range", `${inr(low, 2)} – ${inr(high, 2)}`], ["52-week range", `${inr(l52, 2)} – ${inr(h52, 2)}`], ["Market cap", mc ? "₹" + Number(mc).toLocaleString("en-IN") + " Cr" : "—"], ["P/E", pe || "—"], ["EPS (TTM)", eps != null ? inr(eps, 2) : "—"], ["Price/Book", pb || "—"], ["Dividend yield", dy != null ? dy + "%" : "—"]].map(([a, b]) => `<div class="kv"><span>${a}</span><b>${esc(b)}</b></div>`).join("")}</div>
        <a class="cta" href="/#stock-${encodeURIComponent(k)}">Live price, chart &amp; financials →</a>${faqHTML(qa)}`
    });
  }
  // sitemap + robots
  const extra = [{ url: SITE + "/", pri: "1.0" }];
  fs.writeFileSync(path.join(ROOT, "sitemap.xml"), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${[...extra, ...pages].map(p => `<url><loc>${p.url}</loc><lastmod>${TODAY}</lastmod><changefreq>daily</changefreq><priority>${p.pri}</priority></url>`).join("\n")}\n</urlset>\n`);
  fs.writeFileSync(path.join(ROOT, "robots.txt"), `User-agent: *\nAllow: /\nDisallow: /data/\nDisallow: /worker/\nDisallow: /scripts/\nSitemap: ${SITE}/sitemap.xml\n`);
  console.log("SEO pages:", pages.length);
})();
