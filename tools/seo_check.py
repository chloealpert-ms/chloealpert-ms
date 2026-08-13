#!/usr/bin/env python3
"""Audit the built site in dist/ for the SEO problems that actually cost traffic.

    python3 tools/seo_check.py           # report
    python3 tools/seo_check.py --strict  # exit 1 on any error (for CI)

Checks each page for title and description length, a single H1, image alt
text, canonical and structured data, thin content, and orphan pages, plus
duplicate titles and descriptions across the whole site.
"""

import argparse
import html
import json
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")

# Google truncates around these widths; they're guidance, not hard rules.
TITLE_MIN, TITLE_MAX = 15, 60
DESC_MIN, DESC_MAX = 70, 160
THIN_CONTENT = 300

RED, YELLOW, GREEN, DIM, RESET = (
    "\033[31m", "\033[33m", "\033[32m", "\033[2m", "\033[0m"
)
if not sys.stdout.isatty():
    RED = YELLOW = GREEN = DIM = RESET = ""


def text_of(fragment):
    fragment = re.sub(r"<(script|style)\b.*?</\1>", " ", fragment, flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def meta(doc, name=None, prop=None):
    if name:
        m = re.search(
            rf'<meta\s+name="{name}"\s+content="([^"]*)"', doc, flags=re.I
        )
    else:
        m = re.search(
            rf'<meta\s+property="{prop}"\s+content="([^"]*)"', doc, flags=re.I
        )
    return html.unescape(m.group(1)) if m else ""


def audit():
    pages = {}
    for r, _, fs in os.walk(DIST):
        for f in fs:
            if f != "index.html" and not f.endswith(".html"):
                continue
            path = os.path.join(r, f)
            url = "/" + os.path.relpath(path, DIST).replace("index.html", "")
            url = url.replace("//", "/")
            pages[url] = open(path).read()

    issues = defaultdict(list)  # url -> [(level, message)]
    titles, descs = defaultdict(list), defaultdict(list)
    inbound = defaultdict(int)

    for url, doc in pages.items():
        if url.endswith("404.html"):
            continue
        add = lambda lvl, msg: issues[url].append((lvl, msg))

        title_m = re.search(r"<title>(.*?)</title>", doc, flags=re.S)
        title = html.unescape(title_m.group(1)).strip() if title_m else ""
        if not title:
            add("error", "no <title>")
        else:
            titles[title].append(url)
            if len(title) > TITLE_MAX:
                add("warn", f"title is {len(title)} chars, over {TITLE_MAX} — Google will truncate it")
            elif len(title) < TITLE_MIN:
                add("warn", f"title is only {len(title)} chars")

        desc = meta(doc, name="description")
        if not desc:
            add("error", "no meta description")
        else:
            descs[desc].append(url)
            if len(desc) > DESC_MAX:
                add("warn", f"description is {len(desc)} chars, over {DESC_MAX} — will be cut off")
            elif len(desc) < DESC_MIN:
                add("warn", f"description is only {len(desc)} chars, thin for a snippet")

        h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", doc, flags=re.S | re.I)
        if len(h1s) == 0:
            add("error", "no <h1>")
        elif len(h1s) > 1:
            add("error", f"{len(h1s)} <h1> tags — there should be exactly one")

        if 'rel="canonical"' not in doc:
            add("error", "no canonical link")

        if "application/ld+json" not in doc:
            add("warn", "no structured data (JSON-LD)")
        else:
            for block in re.findall(
                r'<script type="application/ld\+json">(.*?)</script>', doc, flags=re.S
            ):
                try:
                    json.loads(block.replace("\\u003c", "<"))
                except json.JSONDecodeError as e:
                    add("error", f"structured data is not valid JSON: {e}")

        if not meta(doc, prop="og:image"):
            add("warn", "no og:image — shared links will render without a preview card")

        main = re.search(r"<main\b[^>]*>(.*?)</main>", doc, flags=re.S | re.I)
        body_text = text_of(main.group(1) if main else doc)
        wc = len(body_text.split())
        if wc < THIN_CONTENT:
            add("info", f"only {wc} words — thin for ranking")

        for img in re.findall(r"<img\b[^>]*>", doc, flags=re.I):
            alt = re.search(r'alt="([^"]*)"', img, flags=re.I)
            if not alt or not alt.group(1).strip():
                src = re.search(r'src="([^"]*)"', img, flags=re.I)
                add("warn", f"image has no alt text: {src.group(1) if src else '?'}")

        for href in re.findall(r'href="(/[^"#?]*)"', doc):
            if href != url:
                inbound[href] += 1

    for url in pages:
        if url in ("/", "/404.html") or url.endswith("404.html"):
            continue
        if inbound.get(url, 0) == 0:
            issues[url].append(("warn", "orphan page — nothing on the site links to it"))

    for title, urls in titles.items():
        if len(urls) > 1:
            for u in urls:
                issues[u].append(("error", f"duplicate title shared with {len(urls) - 1} other page(s)"))
    for desc, urls in descs.items():
        if len(urls) > 1:
            for u in urls:
                issues[u].append(("error", f"duplicate meta description shared with {len(urls) - 1} other page(s)"))

    return pages, issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="exit 1 if any error found")
    ap.add_argument("--quiet", action="store_true", help="only print problems")
    args = ap.parse_args()

    if not os.path.isdir(DIST):
        print("dist/ not found — run: python3 build.py")
        return 1

    pages, issues = audit()
    errors = warns = 0

    for url in sorted(pages):
        found = issues.get(url, [])
        errs = [i for i in found if i[0] == "error"]
        wrs = [i for i in found if i[0] == "warn"]
        errors += len(errs)
        warns += len(wrs)
        if not found:
            if not args.quiet:
                print(f"{GREEN}ok{RESET}   {url}")
            continue
        print(f"{RED if errs else YELLOW}{'FAIL' if errs else 'warn'}{RESET} {url}")
        for lvl, msg in found:
            colour = RED if lvl == "error" else (YELLOW if lvl == "warn" else DIM)
            print(f"       {colour}{lvl:<5}{RESET} {msg}")

    print()
    print(f"{len(pages)} pages · {RED}{errors} errors{RESET} · {YELLOW}{warns} warnings{RESET}")
    return 1 if (args.strict and errors) else 0


if __name__ == "__main__":
    sys.exit(main())
