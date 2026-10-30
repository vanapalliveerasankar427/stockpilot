#!/usr/bin/env python3
"""Download each listed company's own logo (from its official website) and store it as a
96x96 PNG in ./logos/<key>.png, plus logos/index.json listing which keys have a logo.

Order of preference for each company website:
  1. apple-touch-icon (usually 180x180)   2. the largest <link rel="icon"> PNG/ICO
  3. Google's favicon service for that domain (only if it returns at least 48 px)
Runs after history.py (needs hist/profiles.json for company websites).
"""
import io
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import requests
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "logos_out")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
LIMIT = int(os.environ.get("LOGO_BATCH", "6000"))
stats = {"ok": 0, "fail": 0, "skip": 0}


def fetch(url, timeout=12):
    r = requests.get(url, headers=UA, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r


def to_png(data, min_px=48):
    im = Image.open(io.BytesIO(data))
    if getattr(im, "n_frames", 1) > 1 or im.format == "ICO":  # pick the largest frame / icon size
        try:
            sizes = sorted(im.ico.sizes(), key=lambda s: s[0] * s[1]) if im.format == "ICO" else []
            if sizes:
                im.size = sizes[-1]
        except Exception:
            pass
    im = im.convert("RGBA")
    if max(im.size) < min_px:
        return None
    im.thumbnail((96, 96), Image.LANCZOS)
    canvas = Image.new("RGBA", (96, 96), (255, 255, 255, 0))
    canvas.paste(im, ((96 - im.width) // 2, (96 - im.height) // 2), im)
    buf = io.BytesIO()
    canvas.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def candidates(site):
    try:
        page = fetch(site).text[:400000]
        base = site
    except Exception:
        return []
    out = []
    for tag in re.findall(r"<link\b[^>]*>", page, re.I):
        rel = (re.search(r'rel=["\']([^"\']+)', tag, re.I) or [None, ""])[1].lower()
        href = (re.search(r'href=["\']([^"\']+)', tag, re.I) or [None, ""])[1]
        if not href or "icon" not in rel or href.lower().endswith(".svg"):
            continue
        size = re.search(r'sizes=["\'](\d+)x', tag, re.I)
        score = (1000 if "apple" in rel else 0) + (int(size.group(1)) if size else 32)
        out.append((score, urljoin(base, href)))
    out.sort(reverse=True)
    return [u for _, u in out] + [urljoin(base, "/apple-touch-icon.png"), urljoin(base, "/favicon.ico")]


def logo_for(key, domain):
    site = "https://" + domain
    for u in candidates(site)[:5]:
        try:
            png = to_png(fetch(u).content)
            if png:
                return png
        except Exception:
            continue
    try:
        r = fetch(f"https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&url={site}&size=128")
        return to_png(r.content)
    except Exception:
        return None


def main():
    os.makedirs(OUT, exist_ok=True)
    prof = json.load(open(os.path.join(ROOT, "hist", "profiles.json")))
    domains = prof.get("logo", {})
    try:
        idx = json.load(open(os.path.join(OUT, "index.json")))
    except Exception:
        idx = {"have": [], "tried": {}}
    have, tried = set(idx.get("have", [])), dict(idx.get("tried", {}))
    todo = [(k, d) for k, d in domains.items() if k not in have and tried.get(k) != d][:LIMIT]

    def work(kd):
        k, d = kd
        png = logo_for(k, d)
        tried[k] = d
        if png:
            with open(os.path.join(OUT, k.replace("/", "_") + ".png"), "wb") as f:
                f.write(png)
            have.add(k)
            stats["ok"] += 1
        else:
            stats["fail"] += 1

    with ThreadPoolExecutor(max_workers=48) as ex:
        list(ex.map(work, todo))
    json.dump({"have": sorted(have), "tried": tried}, open(os.path.join(OUT, "index.json"), "w"), separators=(",", ":"))
    print(json.dumps(stats), "total logos:", len(have))


if __name__ == "__main__":
    sys.exit(main())
