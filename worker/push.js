// MarketVedaPro push alerts: stores browser push subscriptions in KV and sends IPO alerts on a schedule.
// Web Push with VAPID (RFC 8292) and aes128gcm payload encryption (RFC 8291), using only WebCrypto.
// A subscription holds no personal data: just the browser's push address and which alert types are on.

const CAL = "https://marketvedapro.com/ipo-calendar.json";
const LIVE = "https://raw.githubusercontent.com/vanapalliveerasankar427/stockpilot/main/data/live.json";
const SITE = "https://marketvedapro.com/";
const PER_RUN = 40; // stay under the free plan's subrequest limit
const TYPES = ["allot", "open", "close", "list", "am", "pm"];
const HOLIDAYS = ["2026-11-10", "2026-11-24", "2026-12-25"]; // NSE weekday trading holidays still ahead (update each year)

const te = new TextEncoder();
const b64u = buf => { let s = ""; new Uint8Array(buf).forEach(b => s += String.fromCharCode(b)); return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); };
const unb64u = s => { s = s.replace(/-/g, "+").replace(/_/g, "/"); while (s.length % 4) s += "="; return Uint8Array.from(atob(s), c => c.charCodeAt(0)); };
const cat = (...a) => { const n = a.reduce((x, y) => x + y.length, 0), o = new Uint8Array(n); let p = 0; a.forEach(x => { o.set(x, p); p += x.length; }); return o; };
const sha = async s => b64u(await crypto.subtle.digest("SHA-256", te.encode(s))).slice(0, 22);

// ---------- VAPID keys (made once, kept in KV; the private key never leaves the worker) ----------
async function vapid(env) {
  let k = await env.PUSH.get("vapid", "json");
  if (!k) {
    const kp = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
    k = { priv: await crypto.subtle.exportKey("jwk", kp.privateKey), pub: b64u(await crypto.subtle.exportKey("raw", kp.publicKey)) };
    await env.PUSH.put("vapid", JSON.stringify(k));
  }
  return k;
}
async function vapidHeader(env, endpoint) {
  const k = await vapid(env), aud = new URL(endpoint).origin;
  const h = b64u(te.encode(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const p = b64u(te.encode(JSON.stringify({ aud, exp: Math.floor(Date.now() / 1000) + 12 * 3600, sub: SITE })));
  const key = await crypto.subtle.importKey("jwk", k.priv, { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, te.encode(h + "." + p));
  return `vapid t=${h}.${p}.${b64u(sig)}, k=${k.pub}`;
}

// ---------- RFC 8291 payload encryption ----------
async function hkdf(salt, ikm, info, bits) {
  const k = await crypto.subtle.importKey("raw", ikm, "HKDF", false, ["deriveBits"]);
  return new Uint8Array(await crypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt, info }, k, bits));
}
export async function encrypt(sub, text) {
  const uaPub = unb64u(sub.keys.p256dh), auth = unb64u(sub.keys.auth);
  const as = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
  const asPub = new Uint8Array(await crypto.subtle.exportKey("raw", as.publicKey));
  const uaKey = await crypto.subtle.importKey("raw", uaPub, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const shared = new Uint8Array(await crypto.subtle.deriveBits({ name: "ECDH", public: uaKey }, as.privateKey, 256));
  const ikm = await hkdf(auth, shared, cat(te.encode("WebPush: info\0"), uaPub, asPub), 256);
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const cek = await hkdf(salt, ikm, te.encode("Content-Encoding: aes128gcm\0"), 128);
  const nonce = await hkdf(salt, ikm, te.encode("Content-Encoding: nonce\0"), 96);
  const key = await crypto.subtle.importKey("raw", cek, "AES-GCM", false, ["encrypt"]);
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, cat(te.encode(text), new Uint8Array([2]))));
  const rs = new Uint8Array([0, 0, 16, 0]); // record size 4096
  return cat(salt, rs, new Uint8Array([asPub.length]), asPub, ct);
}
async function send(env, sub, msg) {
  const body = await encrypt(sub, JSON.stringify(msg));
  const r = await fetch(sub.endpoint, { method: "POST", body, headers: {
    Authorization: await vapidHeader(env, sub.endpoint), "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
    TTL: "43200", Urgency: "high", Topic: String(msg.tag || "mvp").replace(/[^A-Za-z0-9_-]/g, "").slice(0, 32) } });
  return r.status;
}

// ---------- subscriptions ----------
const okSub = s => s && typeof s.endpoint === "string" && /^https:\/\//.test(s.endpoint) && s.endpoint.length < 1000 && s.keys && typeof s.keys.p256dh === "string" && typeof s.keys.auth === "string";
export async function api(req, env, path, json) {
  if (!env.PUSH) return json({ error: "push storage not set up" }, 503);
  if (path === "/push/key") return json({ key: (await vapid(env)).pub });
  const body = req.method === "POST" ? await req.json().catch(() => ({})) : {};
  if (!okSub(body.sub)) return json({ error: "bad subscription" }, 400);
  const id = "s:" + await sha(body.sub.endpoint);
  if (path === "/push/subscribe") {
    const types = TYPES.filter(t => !body.types || body.types[t] !== 0);
    const old = await env.PUSH.get(id, "json") || {};
    await env.PUSH.put(id, JSON.stringify({ ...old, sub: { endpoint: body.sub.endpoint, keys: { p256dh: body.sub.keys.p256dh, auth: body.sub.keys.auth } }, types, t: Date.now() }));
    if (body.hello) await send(env, body.sub, { t: "Alerts are on", b: "You'll get IPO openings, last days, allotments and listings, even when the app is closed.", u: SITE + "#ipos", tag: "hello" }).catch(() => 0);
    return json({ ok: true });
  }
  if (path === "/push/unsubscribe") { await env.PUSH.delete(id); await idxSet(env, id, false); return json({ ok: true }); }
  if (path === "/push/alerts") { // save this browser's price alerts; returns the ones already sent while the app was closed
    const rec = await env.PUSH.get(id, "json");
    if (!rec) return json({ error: "not subscribed" }, 404);
    const list = (Array.isArray(body.alerts) ? body.alerts : []).slice(0, 20).map(cleanAlert).filter(Boolean);
    const fired = (rec.fired || []).filter(f => Date.now() - f.at < 14 * 864e5);
    const firedIds = new Set(fired.map(f => f.id));
    rec.pa = list.filter(a => !firedIds.has(a.id)); rec.fired = fired.filter(f => list.some(a => a.id === f.id) || Date.now() - f.at < 864e5);
    await env.PUSH.put(id, JSON.stringify(rec));
    await idxSet(env, id, rec.pa.length > 0);
    return json({ ok: true, fired: fired.map(f => ({ id: f.id, at: f.at, p: f.p })) });
  }
  return json({ error: "not found" }, 404);
}


// ---------- price alerts ----------
function cleanAlert(a) {
  if (!a || typeof a !== "object") return null;
  const k = ["s", "g", "a"].includes(a.k) ? a.k : null, op = a.op === "d" ? "d" : a.op === "u" ? "u" : null, v = +a.v;
  if (!k || !op || !(v > 0) || v > 1e9) return null;
  const sym = String(a.sym || "").slice(0, 30), y = String(a.y || "").slice(0, 30);
  if (k === "s" && !/^[A-Za-z0-9^._&=-]{1,30}$/.test(y)) return null;
  return { id: String(a.id || "").replace(/[^A-Za-z0-9_-]/g, "").slice(0, 24) || String(Date.now()), k, sym, y, n: String(a.n || sym).slice(0, 60), op, v };
}
async function idxSet(env, id, on) {
  const idx = await env.PUSH.get("pa:idx", "json") || [];
  const has = idx.includes(id);
  if (on && !has) { idx.push(id); await env.PUSH.put("pa:idx", JSON.stringify(idx)); }
  if (!on && has) await env.PUSH.put("pa:idx", JSON.stringify(idx.filter(x => x !== id)));
}
const inr = v => "₹" + (+v).toLocaleString("en-IN", { maximumFractionDigits: v >= 1000 ? 0 : 2 });
async function metalNow() { // the same headline numbers the website shows (jeweller 24K per gram, silver per kg)
  const m = (await (await fetch(LIVE, { cf: { cacheTtl: 120 } })).json()).metals || {};
  const R = m.retail || {}, B = m.bullion || {}, I = m.ibja || {};
  const g = R.g24 || B.g24 || I.g999, ag = B.ag || R.ag || I.ag;
  return { g: g ? +g : null, a: ag ? +ag * 1000 : null };
}
export async function priceCron(env, quotes) {
  if (!env.PUSH) return 0;
  const idx = await env.PUSH.get("pa:idx", "json") || [];
  if (!idx.length) return 0;
  const recs = [];
  for (const id of idx.slice(0, 300)) { const r = await env.PUSH.get(id, "json"); if (r && r.pa && r.pa.length) recs.push([id, r]); else await idxSet(env, id, false); }
  const ys = [...new Set(recs.flatMap(([, r]) => r.pa.filter(a => a.k === "s").map(a => a.y)))];
  const q = {};
  for (let i = 0; i < ys.length; i += 80) Object.assign(q, await quotes(ys.slice(i, i + 80)).catch(() => ({})));
  let mt = {}; if (recs.some(([, r]) => r.pa.some(a => a.k !== "s"))) { try { mt = await metalNow(); } catch {} }
  let sent = 0;
  for (const [id, r] of recs) {
    const keep = [], hit = [];
    for (const a of r.pa) {
      const p = a.k === "s" ? (q[a.y] && q[a.y][0]) : mt[a.k];
      if (p != null && isFinite(p) && (a.op === "u" ? p >= a.v : p <= a.v)) hit.push([a, +p]); else keep.push(a);
    }
    if (!hit.length) continue;
    let gone = false;
    for (const [a, p] of hit) {
      const unit = a.k === "g" ? " per gram (24K)" : a.k === "a" ? " per kg" : "";
      const code = await send(env, r.sub, { t: `${a.n} ${a.op === "u" ? "crossed above" : "fell below"} ${inr(a.v)}`, b: `Now ${inr(p)}${unit}. Your price alert on MarketVedaPro.`, u: SITE + (a.k === "s" ? "#stock-" + encodeURIComponent(a.sym) : "#metals"), tag: "pa-" + a.id }).catch(() => 0);
      if (code === 404 || code === 410) { gone = true; break; }
      if (code >= 200 && code < 300) sent++;
      (r.fired = r.fired || []).push({ id: a.id, at: Date.now(), p });
    }
    if (gone) { await env.PUSH.delete(id); await idxSet(env, id, false); continue; }
    r.pa = keep; await env.PUSH.put(id, JSON.stringify(r));
    if (!keep.length) await idxSet(env, id, false);
  }
  return sent;
}

// ---------- 8:45 AM outlook and 3:45 PM close digests ----------
const pc = v => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(2) + "%";
export async function digestCron(env, quotes) {
  if (!env.PUSH) return;
  const now = IST(), day = ymd(now), dow = now.getUTCDay(), m = now.getUTCHours() * 60 + now.getUTCMinutes();
  if (dow === 0 || dow === 6 || HOLIDAYS.includes(day)) return;
  let ev = null;
  if (m >= 8 * 60 + 45 && m < 10 * 60) {
    if ((await env.PUSH.get("ev:am-" + day, "json") || {}).done) return;
    const o = (await (await fetch(LIVE, { cf: { cacheTtl: 60 } })).json()).outlook || {};
    const nm = l => (l || []).slice(0, 3).map(x => x.n || x.k).join(", ");
    const cue = (o.cues || [])[0];
    if (!(o.up || []).length && !(o.down || []).length) return;
    ev = { id: "am-" + day, type: "am", t: "Today's outlook · " + now.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" }),
      b: [(o.up || []).length ? "Likely up: " + nm(o.up) : "", (o.down || []).length ? "Likely down: " + nm(o.down) : "", cue || ""].filter(Boolean).join(" · ") + ". Signals, not advice.", u: SITE + "#today" };
  } else if (m >= 15 * 60 + 45 && m < 17 * 60) {
    if ((await env.PUSH.get("ev:pm-" + day, "json") || {}).done) return;
    const q = await quotes(["^NSEI", "^BSESN", "^NSEBANK"]);
    const n = q["^NSEI"], s = q["^BSESN"], b = q["^NSEBANK"];
    if (!n || !n[0] || !n[3] || ymd(new Date(n[3] * 1000 + 330 * 60000)) !== day) return; // market didn't trade today
    let top = ""; try { const L = await (await fetch(LIVE, { cf: { cacheTtl: 60 } })).json(); const g = (L.gainers || [])[0], l = (L.losers || [])[0];
      const f = x => Array.isArray(x) ? `${x[0]} ${pc(+x[2] || +x[1] || 0)}` : x && (x.sym || x.k) ? `${x.sym || x.k} ${pc(+(x.pct ?? x.p ?? 0))}` : "";
      top = [g ? "Top gainer " + f(g) : "", l ? "top loser " + f(l) : ""].filter(Boolean).join(", "); } catch {}
    const fx = v => (+v).toLocaleString("en-IN", { maximumFractionDigits: 0 });
    ev = { id: "pm-" + day, type: "pm", t: `Market closed: Nifty ${fx(n[0])} (${pc(n[1])})`,
      b: [s && s[0] ? `Sensex ${fx(s[0])} (${pc(s[1])})` : "", b && b[0] ? `Bank Nifty ${pc(b[1])}` : "", top].filter(Boolean).join(" · "), u: SITE + "#markets" };
  }
  if (ev) await broadcast(env, ev, PER_RUN);
}

// ---------- what to send, and when ----------
const IST = () => new Date(Date.now() + 330 * 60000);
const ymd = d => d.toISOString().slice(0, 10);
const short = n => String(n).replace(/ (Ltd|Limited)\.?$/i, "");
const band = i => i.lo === i.hi ? `₹${i.hi}` : `₹${i.lo}–${i.hi}`;
async function events(env, companiesOf) {
  const now = IST(), today = ymd(now), tmr = ymd(new Date(now.getTime() + 864e5)), hr = now.getUTCHours() + now.getUTCMinutes() / 60;
  const cal = await (await fetch(CAL, { cf: { cacheTtl: 300 } })).json();
  let live = {}; try { live = (await (await fetch(LIVE, { cf: { cacheTtl: 120 } })).json()).ipo || {}; } catch {}
  const out = [];
  for (const i of cal.ipos || []) {
    const L = live[i.id] || {}, g = L.gmp != null ? L.gmp : i.gmp, gt = g != null && i.hi ? ` · GMP ₹${g} (${(g / i.hi * 100).toFixed(1)}%)` : "";
    const sub = L.sub != null ? ` · ${(+L.sub).toFixed(2)}x subscribed` : "";
    if (hr >= 8 && hr < 22) { // morning alerts go out from 8 AM; anyone who subscribes later in the day still gets them
      if (i.open === today) out.push({ id: `op-${i.id}-${today}`, type: "open", t: `${short(i.name)} IPO opens today`, b: `${i.type} · ${band(i)}${gt}`, u: SITE + "#ipos/" + encodeURIComponent(i.id) });
      if (i.close === today && hr < 17) out.push({ id: `cl-${i.id}-${today}`, type: "close", t: `Last day to apply: ${short(i.name)}`, b: `Bidding closes today. Approve the UPI mandate before 5 PM.${sub}${gt}`, u: SITE + "#ipos/" + encodeURIComponent(i.id) });
      if (i.list === today && hr < 16) out.push({ id: `ls-${i.id}-${today}`, type: "list", t: `${short(i.name)} lists today`, b: `Issue price ₹${i.hi}${gt}. Listing at 10 AM.`, u: SITE + "#ipos/" + encodeURIComponent(i.id) });
      if (i.open === tmr && hr >= 18) out.push({ id: `up-${i.id}-${today}`, type: "open", t: `${short(i.name)} IPO opens tomorrow`, b: `${i.type} · ${band(i)}${gt}`, u: SITE + "#ipos/" + encodeURIComponent(i.id) });
    }
    // allotment: send as soon as the registrar publishes it (checked every 30 minutes), or by 7 PM on allotment day
    if (i.allot && (i.allot === today || i.allot === ymd(new Date(now.getTime() - 864e5))) && hr >= 11) {
      let out_ = hr >= 19 && i.allot === today;
      if (!out_) { try { const cl = await companiesOf(i.reg); const want = norm(i.name); out_ = !!cl && cl.some(c => { const n = norm(c.name); return n && (n.includes(want) || want.includes(n)); }); } catch {} }
      if (out_) out.push({ id: `al-${i.id}`, type: "allot", t: `${short(i.name)} allotment is out`, b: "Tap to check everyone in your family in one go.", u: SITE + "#allot-" + i.id });
    }
  }
  return out;
}
const norm = t => String(t || "").toLowerCase().replace(/\b(limited|ltd|ipo|india|private|pvt|the|and|sme)\b/g, "").replace(/[^a-z0-9]/g, "");

export async function cron(env, companiesOf) {
  if (!env.PUSH) return;
  const regCache = {};
  const companies = async reg => { const k = /mufg|link\s*intime/i.test(reg) ? "mufg" : /kfin/i.test(reg) ? "kfin" : /maashitla/i.test(reg) ? "maashitla" : /bigshare/i.test(reg) ? "bigshare" : /purva/i.test(reg) ? "purva" : /skyline/i.test(reg) ? "skyline" : null; if (!k) return null; return regCache[k] || (regCache[k] = await companiesOf(k)); };
  let budget = PER_RUN;
  for (const ev of await events(env, companies)) { if (budget <= 0) break; budget = await broadcast(env, ev, budget); }
}
export async function broadcast(env, ev, budget) {
  const st = await env.PUSH.get("ev:" + ev.id, "json") || {};
  if (st.done) return budget;
  let cursor = st.cursor, sent = st.sent || 0;
  while (budget > 0) {
    const page = await env.PUSH.list({ prefix: "s:", cursor, limit: Math.min(budget, 1000) });
    for (const k of page.keys) {
      const rec = await env.PUSH.get(k.name, "json"); budget--;
      if (!rec || !(rec.types || TYPES).includes(ev.type)) continue;
      const code = await send(env, rec.sub, { t: ev.t, b: ev.b, u: ev.u, tag: ev.id }).catch(() => 0);
      if (code === 404 || code === 410) await env.PUSH.delete(k.name); else if (code >= 200 && code < 300) sent++;
    }
    cursor = page.list_complete ? null : page.cursor;
    if (page.list_complete) { await env.PUSH.put("ev:" + ev.id, JSON.stringify({ done: true, sent, at: Date.now() }), { expirationTtl: 20 * 86400 }); break; }
    if (budget <= 0) await env.PUSH.put("ev:" + ev.id, JSON.stringify({ cursor, sent }), { expirationTtl: 3 * 86400 });
  }
  return budget;
}
