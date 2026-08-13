#!/usr/bin/env python3
"""Scaffold a new post with SEO frontmatter already filled in.

    python3 tools/new_post.py "Why smaller AI models win"

Creates content/posts/<slug>.md, dated today, with every SEO field present
and commented so nothing gets forgotten. Then write the body and run
`python3 build.py`.
"""

import argparse
import datetime
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS = os.path.join(ROOT, "content", "posts")

STOPWORDS = {"a", "an", "the", "and", "or", "of", "to", "in", "is", "it", "for", "on"}


def slugify(title):
    s = title.lower().replace("&", "and")
    s = re.sub(r"['’]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    # Keep slugs short and keyword-dense; drop filler words from the tail.
    words = [w for w in s.split("-") if w]
    while len("-".join(words)) > 60 and len(words) > 4:
        for i in range(len(words) - 1, -1, -1):
            if words[i] in STOPWORDS:
                words.pop(i)
                break
        else:
            words.pop()
    return "-".join(words)


TEMPLATE = """---
title: "{title}"
date: "{date}"
slug: "{slug}"
description: "{desc}"
keywords: "{keywords}"
seo_title: "{seo_title}"
image: ""
---

Open with the answer, not a windup. The first two sentences are what Google
shows and what decides whether anyone keeps reading.

## A descriptive H2 that contains the phrase people search for

Body text. Link to your own related posts where it's natural — internal links
are the strongest ranking lever a small site has:
[how dilution works](/how-to-model-ownership-dilution-and-how-pro-rata-works-in-venture-capital-deals/).

## Another section

- a list item
  - a nested item

> A pull quote, if useful.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("title", help="the post title")
    ap.add_argument("--slug", help="override the generated slug")
    ap.add_argument("--date", help="YYYY-MM-DD (defaults to today)")
    args = ap.parse_args()

    slug = args.slug or slugify(args.title)
    date = args.date or datetime.date.today().isoformat()
    path = os.path.join(POSTS, f"{slug}.md")

    if os.path.exists(path):
        print(f"error: {path} already exists")
        return 1

    seo_title = args.title if len(args.title) <= 45 else ""
    body = TEMPLATE.format(
        title=args.title.replace('"', '\\"'),
        date=date,
        slug=slug,
        desc="",
        keywords="",
        seo_title=seo_title.replace('"', '\\"'),
    )
    os.makedirs(POSTS, exist_ok=True)
    with open(path, "w") as f:
        f.write(body)

    rel = os.path.relpath(path, ROOT)
    print(f"Created {rel}\n")
    print("Before you publish, fill in:")
    print("  description  one or two sentences, 70-158 chars — this is your search snippet")
    print("  keywords     comma-separated topics this post should rank for")
    if not seo_title:
        print(f"  seo_title    a short title (<=45 chars); '{args.title}' is long for search results")
    print("  image        optional 1200x630 social card in static/images/")
    print("\nThen:")
    print("  python3 build.py && python3 tools/seo_check.py")
    print(f"\nIt will publish at /{slug}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
