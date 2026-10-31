// Writes ipo-calendar.json (IPO dates for push alerts) from the IPO list in index.html.
const fs = require("fs");
const html = fs.readFileSync(process.argv[2] || "index.html", "utf8");
const s = html.indexOf("const IPOS_RAW=[");
if (s < 0) throw new Error("IPOS_RAW not found");
const e = html.indexOf("\n];", s);
const list = Function('"use strict";return ' + html.slice(s + "const IPOS_RAW=".length, e + 2))();
let live = {}; try { live = JSON.parse(fs.readFileSync(require("path").join(require("path").dirname(process.argv[2] || "index.html"), "data/live.json"), "utf8")); } catch {}
const nn = t => String(t).toLowerCase().replace(/\b(limited|ltd|india|the|and)\b/g, "").replace(/[^a-z0-9]/g, "");
for (const c of live.ipocal || []) if (!list.some(r => nn(r.name).includes(nn(c.name)) || nn(c.name).includes(nn(r.name)))) list.push({ ...c, reg: "" });
const out = list.map(i => ({ id: i.id, name: i.name, type: i.type, reg: i.reg || "", lo: i.lo, hi: i.hi, lot: i.lot,
  open: i.open, close: i.close, allot: i.allot, list: i.list, gmp: i.gmp ? i.gmp.v : null }));
fs.writeFileSync(process.argv[3] || "ipo-calendar.json", JSON.stringify({ updated: new Date().toISOString(), ipos: out }));
console.log("ipo-calendar.json:", out.length, "IPOs");
