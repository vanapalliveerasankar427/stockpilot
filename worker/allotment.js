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
  throw new Error("unsupported registrar");
}

export default {
  async scheduled(event, env, ctx) { ctx.waitUntil(pushCron(env, companies)); },
  async fetch(req, env) {
    if (req.method === "OPTIONS") return new Response(null, { headers: cors(req) });
    const url = new URL(req.url);
    try {
      if (url.pathname.startsWith("/push/")) return await pushApi(req, env, url.pathname, (b, s) => json(req, b, s));
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
