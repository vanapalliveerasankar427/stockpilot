// MarketVedaPro allotment relay — a Cloudflare Worker.
// Passes a PAN lookup from the MarketVedaPro site to the IPO registrar and returns the result.
// It does not store or log PANs. Registrars that require a captcha are not queried.
// Registrar request formats follow the MIT-licensed IPO-Allotment-Status-Bot (github.com/AbGisHere/IPO-Allotment-Status-Bot).

import { api as pushApi, cron as pushCron } from "./push.js";

const ALLOWED = ["https://marketvedapro.com", "https://www.marketvedapro.com", "https://vanapalliveerasankar427.github.io"];
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36";
const MUFG = "https://in.mpms.mufg.com/Initial_Offer/";
const KFIN_PAGE = "https://ipostatus.kfintech.com/";
const KFIN_API = "https://0uz601ms56.execute-api.ap-south-1.amazonaws.com/prod/api/query";
const MAASH_LIST = "https://api.maashitla.com/api/company-directory";
const MAASH_API = "https://pnjbvxj6md.execute-api.ap-south-1.amazonaws.com/prod/check/";
const BIG_PAGE = "https://ipo.bigshareonline.com/IPO_Status.html";
const BIG_API = "https://ipo.bigshareonline.com/Data.aspx/FetchIpodetails";
const PURVA_PAGE = "https://www.purvashare.com/investor-service/ipo-query";
const SKY_PAGE = "https://www.skylinerta.com/ipo.php";
const SKY_FORM = "https://www.skylinerta.com/display_application.php";
const PAN_RE = /^[A-Z]{5}[0-9]{4}[A-Z]$/;

function cors(req) {
  const o = req.headers.get("Origin") || "";
  return { "Access-Control-Allow-Origin": ALLOWED.includes(o) ? o : ALLOWED[0], "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
           "Access-Control-Allow-Headers": "Content-Type", "Vary": "Origin", "Cache-Control": "no-store" };
}
const json = (req, body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...cors(req) } });

// ---------- tiny XML helpers (MUFG returns XML inside JSON) ----------
const tables = (xml, tag) => [...xml.matchAll(new RegExp(`<${tag}>([\\s\\S]*?)</${tag}>`, "g"))].map(m => m[1]);
const field = (block, name) => { const m = block.match(new RegExp(`<${name}>([\\s\\S]*?)</${name}>`)); return m ? m[1].trim() : ""; };
const int = v => parseInt(String(v || "").replace(/[^\d]/g, "").split(".")[0] || "0", 10) || 0;

async function aesB64(text) { // MUFG page encrypts its token with AES-128-CBC, key = iv = "8080808080808080"
  const k = new TextEncoder().encode("8080808080808080");
  const key = await crypto.subtle.importKey("raw", k, { name: "AES-CBC" }, false, ["encrypt"]);
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-CBC", iv: k }, key, new TextEncoder().encode(text)));
  let s = ""; ct.forEach(b => s += String.fromCharCode(b)); return btoa(s);
}


// ---------- HTML helpers (Bigshare, Purva and Skyline list companies in a <select>) ----------
const ent = s => s.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;|&#039;/g, "'").replace(/&nbsp;/g, " ");
const htext = s => ent(String(s).replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
function options(page, id) {
  const m = page.match(new RegExp(`<select[^>]*\\b(?:id|name)="${id}"[^>]*>([\\s\\S]*?)</select>`, "i"));
  if (!m) throw new Error("company list not found");
  return [...m[1].matchAll(/<option[^>]*value="([^"]*)"[^>]*>([\s\S]*?)<\/option>/gi)].map(o => ({ id: o[1].trim(), name: htext(o[2]) })).filter(o => o.id && o.id !== "0");
}
// tiny cookie jar for form sites that need a session
function jar() { const c = {}; return {
  take(r) { (r.headers.getSetCookie ? r.headers.getSetCookie() : [r.headers.get("set-cookie") || ""]).forEach(s => { const m = s.match(/^([^=;\s]+)=([^;]*)/); if (m) c[m[1]] = m[2]; }); return r; },
  get hdr() { return Object.entries(c).map(([k, v]) => k + "=" + v).join("; "); } }; }
function summarize(records, reg) {
  const find = (rec, wants, avoid = []) => { for (const w of wants) for (const [k0, v] of Object.entries(rec)) { const k = k0.toLowerCase(); if (new RegExp(w).test(k) && !avoid.some(a => new RegExp(a).test(k))) return v; } return null; };
  const q = "(share|qty|quantity)";
  const allotted = r => find(r, [`allot.*${q}|${q}.*allot`, "allot"], ["date", "basis", "status"]);
  const applied = r => find(r, [`appl.*${q}|${q}.*appl|^applied`, "appl|bid"], ["allot", "name", "appl\\w*\\.?\\s*(no|num)", "\\bid\\b"]);
  const hits = records.filter(r => allotted(r) != null);
  if (!hits.length) throw new Error(reg + ": couldn't read the result");
  return { found: true, applied: hits.reduce((a, r) => a + int(applied(r)), 0), allotted: hits.reduce((a, r) => a + int(allotted(r)), 0), category: String(find(hits[0], ["categ"]) || "").trim() };
}

// ---------- company lists (an IPO appears once its allotment is out) ----------
async function companies(reg) {
  if (reg === "mufg") {
    const r = await fetch(MUFG + "IPO.aspx/GetDetails", { method: "POST", body: "{}", headers: { "Content-Type": "application/json; charset=utf-8", Referer: MUFG + "public-issues.html", "User-Agent": UA } });
    const xml = (await r.json()).d;
    return tables(xml, "Table").map(t => ({ id: field(t, "company_id"), name: field(t, "companyname") }));
  }
  if (reg === "kfin") {
    const page = await (await fetch(KFIN_PAGE, { headers: { "User-Agent": UA } })).text();
    const m = page.match(/src="\.?\/?(static\/js\/main\.[0-9a-f]+\.js)"/);
    if (!m) throw new Error("KFintech list not found");
    const js = await (await fetch(KFIN_PAGE + m[1], { headers: { Referer: KFIN_PAGE, "User-Agent": UA } })).text();
    const m2 = js.match(/JSON\.parse\('(\[\{"clientId".*?\])'\)/);
    if (!m2) throw new Error("KFintech list not found");
    return JSON.parse(m2[1]).map(c => ({ id: c.clientId, name: String(c.name).trim() }));
  }
  if (reg === "maashitla") {
    const d = await (await fetch(MAASH_LIST, { headers: { Origin: "https://maashitla.com", "User-Agent": UA } })).json();
    return (d.companies || []).map(c => ({ id: c.company_slug, name: String(c.company_name).trim() }));
  }
  if (reg === "bigshare") return options(await (await fetch(BIG_PAGE, { headers: { "User-Agent": UA } })).text(), "ddlCompany");
  if (reg === "purva") return options(await (await fetch(PURVA_PAGE, { headers: { "User-Agent": UA } })).text(), "company_id");
  if (reg === "skyline") return options(await (await fetch(SKY_PAGE, { headers: { "User-Agent": UA } })).text(), "company");
  throw new Error("unsupported registrar");
}

// ---------- one PAN ----------
async function check(reg, cid, pan) {
  if (reg === "mufg") {
    const h = { "Content-Type": "application/json; charset=utf-8", Referer: MUFG + "public-issues.html", "User-Agent": UA };
    const tok = (await (await fetch(MUFG + "IPO.aspx/generateToken", { method: "POST", body: "{}", headers: h })).json()).d;
    const body = JSON.stringify({ clientid: cid, PAN: pan, IFSC: "", CHKVAL: "1", token: await aesB64(String(tok)) });
    const xml = (await (await fetch(MUFG + "IPO.aspx/SearchOnPan", { method: "POST", body, headers: h })).json()).d;
    const msg = (tables(xml, "Table1")[0] || ""); if (field(msg, "Msg")) throw new Error(field(msg, "Msg"));
    const rows = tables(xml, "Table");
    if (!rows.length) return { found: false };
    return { found: true, applied: rows.reduce((a, r) => a + int(field(r, "SHARES")), 0), allotted: rows.reduce((a, r) => a + int(field(r, "ALLOT")), 0), category: field(rows[0], "PEMNDG") };
  }
  if (reg === "kfin") {
    const r = await fetch(KFIN_API + "?type=pan", { headers: { reqparam: pan, client_id: cid, Origin: "https://ipostatus.kfintech.com", Referer: KFIN_PAGE, "User-Agent": UA } });
    if (r.status === 404 || r.status === 204) return { found: false };
    if (!r.ok) throw new Error("KFintech " + r.status);
    const t = await r.text(); if (!t.trim()) return { found: false };
    const d = JSON.parse(t); let rows = d && d.data !== undefined ? d.data : d; rows = (Array.isArray(rows) ? rows : rows ? [rows] : []).filter(x => x && typeof x === "object" && ("App_Shares" in x || "All_Shares" in x));
    if (!rows.length || rows.every(x => !int(x.App_Shares))) return { found: false };
    return { found: true, applied: rows.reduce((a, x) => a + int(x.App_Shares), 0), allotted: rows.reduce((a, x) => a + int(x.All_Shares), 0), category: String(rows[0].category || "") };
  }
  if (reg === "maashitla") {
    const d = await (await fetch(MAASH_API + encodeURIComponent(cid) + "?pan=" + pan, { headers: { Origin: "https://maashitla.com", "User-Agent": UA } })).json();
    if (d.name == null) return { found: false };
    return { found: true, applied: int(d.shares_applied), allotted: int(d.shares_allotted), category: "" };
  }
  if (reg === "bigshare") {
    const body = JSON.stringify({ Applicationno: "", Company: cid, SelectionType: "PN", PanNo: pan, txtcsdl: "", txtDPID: "", txtClId: "", ddlType: "0", lang: "en" });
    const d = (await (await fetch(BIG_API, { method: "POST", body, headers: { "Content-Type": "application/json; charset=utf-8", Referer: BIG_PAGE, Origin: "https://ipo.bigshareonline.com", "User-Agent": UA } })).json()).d || {};
    if (d.Status === "NOTFOUND") return { found: false };
    if (d.Status && d.Status !== "OK") throw new Error("Bigshare: " + (d.Message || d.Status));
    const rows = d.Records || [d];
    const applied = rows.reduce((a, r) => a + int(r.APPLIED), 0);
    if (!applied && !rows.some(r => r.ALLOTED != null)) return { found: false };
    return { found: true, applied, allotted: rows.reduce((a, r) => a + int(r.ALLOTED), 0), category: "" };
  }
  if (reg === "purva") {
    const j = jar(), first = await (await fetch(PURVA_PAGE, { headers: { "User-Agent": UA } }).then(r => j.take(r))).text();
    const tok = first.match(/name="csrfmiddlewaretoken" value="([^"]+)"/); if (!tok) throw new Error("Purva: form token missing");
    const form = new URLSearchParams({ csrfmiddlewaretoken: tok[1], company_id: cid, applicationNumber: "", panNumber: pan });
    const page = await (await fetch(PURVA_PAGE, { method: "POST", body: form, headers: { "Content-Type": "application/x-www-form-urlencoded", Referer: PURVA_PAGE, Cookie: j.hdr, "User-Agent": UA } })).text();
    if (/no record found/i.test(page)) return { found: false };
    const t = page.match(/<table[^>]*results-table[\s\S]*?<\/table>/); if (!t) throw new Error("Purva: couldn't read the result");
    const heads = [...t[0].matchAll(/<th[^>]*>([\s\S]*?)<\/th>/g)].map(m => htext(m[1])); const recs = [], pairs = {};
    for (const tr of t[0].matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/g)) {
      const ths = [...tr[1].matchAll(/<th[^>]*>([\s\S]*?)<\/th>/g)].map(m => htext(m[1])), tds = [...tr[1].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map(m => htext(m[1]));
      if (ths.length === 1 && tds.length === 1) pairs[ths[0]] = tds[0]; else if (tds.length) recs.push(Object.fromEntries(heads.map((h, k) => [h, tds[k]])));
    }
    return summarize(recs.length ? recs : [pairs], "Purva");
  }
  if (reg === "skyline") {
    const j = jar();
    const fp = await (await fetch(SKY_FORM, { method: "POST", body: new URLSearchParams({ company: cid }), headers: { "Content-Type": "application/x-www-form-urlencoded", Referer: SKY_PAGE, "User-Agent": UA } }).then(r => j.take(r))).text();
    const tok = fp.match(/name="csrf_token"[^>]*value="([^"]+)"/); if (!tok) throw new Error("Skyline: form token missing");
    const form = new URLSearchParams({ client_id: "", application_no: "", pan, csrf_token: tok[1], company: cid, action: "search" });
    const page = await (await fetch(SKY_FORM, { method: "POST", body: form, headers: { "Content-Type": "application/x-www-form-urlencoded", Referer: SKY_FORM, Cookie: j.hdr, "User-Agent": UA } })).text();
    if (/no record found/i.test(page)) return { found: false };
    const blk = page.match(/class="[^"]*resultsec[\s\S]*?(?=<form|<footer)/); if (!blk) throw new Error("Skyline: couldn't read the result");
    const pairs = {};
    for (const li of blk[0].matchAll(/<li[^>]*>([\s\S]*?)<\/li>/g)) { const parts = li[1].split(/<[^>]+>/).map(htext).filter(Boolean); if (parts.length >= 2) pairs[parts[0].replace(/:$/, "")] = parts.slice(1).join(" "); }
    return summarize([pairs], "Skyline");
  }
  throw new Error("unsupported registrar");
}


// ---------- live gold & silver spot (for the per-second ticker), cached at the edge for 2 seconds ----------
async function spot(req) {
  const cache = caches.default, key = new Request("https://mvp.cache/spot");
  const hit = await cache.match(key); if (hit) { const r = new Response(hit.body, hit); Object.entries(cors(req)).forEach(([k, v]) => r.headers.set(k, v)); r.headers.set("Cache-Control", "no-store"); return r; }
  const g = async s => { const r = await fetch("https://api.gold-api.com/price/" + s, { headers: { "User-Agent": UA } }); const d = await r.json(); return { p: +d.price, t: d.updatedAt || null }; };
  const fx = async () => { try { const d = await (await fetch("https://query1.finance.yahoo.com/v8/finance/chart/USDINR=X?range=1d&interval=1m", { headers: { "User-Agent": UA } })).json(); return +d.chart.result[0].meta.regularMarketPrice; } catch { return null; } };
  const [xau, xag, usdinr] = await Promise.all([g("XAU"), g("XAG"), fx()]);
  const body = JSON.stringify({ xau: xau.p, xag: xag.p, usdinr, t: xau.t, at: Date.now() });
  await cache.put(key, new Response(body, { headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=2" } }));
  return json(req, JSON.parse(body));
}

export default {
  async scheduled(event, env, ctx) { ctx.waitUntil(pushCron(env, companies)); },
  async fetch(req, env) {
    if (req.method === "OPTIONS") return new Response(null, { headers: cors(req) });
    const url = new URL(req.url);
    try {
      if (url.pathname.startsWith("/push/")) return await pushApi(req, env, url.pathname, (b, s) => json(req, b, s));
      if (url.pathname === "/spot") return await spot(req);
      if (url.pathname === "/companies") return json(req, { companies: await companies(url.searchParams.get("reg")) });
      if (url.pathname === "/check" && req.method === "POST") {
        const { reg, cid, pans } = await req.json();
        if (!reg || !cid || !Array.isArray(pans) || !pans.length || pans.length > 20) return json(req, { error: "bad request" }, 400);
        const out = [];
        for (const p of pans) { // one at a time, to be gentle on the registrar
          const pan = String(p).toUpperCase().trim();
          if (!PAN_RE.test(pan)) { out.push({ pan, error: "invalid PAN" }); continue; }
          try { out.push({ pan, ...(await check(reg, cid, pan)) }); } catch (e) { out.push({ pan, error: String(e.message || e).slice(0, 120) }); }
        }
        return json(req, { results: out });
      }
      if (url.pathname === "/") return json(req, { ok: true, service: "MarketVedaPro allotment relay" });
      return json(req, { error: "not found" }, 404);
    } catch (e) {
      return json(req, { error: String(e.message || e).slice(0, 160) }, 502);
    }
  }
};
