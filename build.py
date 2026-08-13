#!/usr/bin/env python3
"""Build the static site into dist/.

    python3 build.py            # build
    python3 build.py --serve    # build, then serve dist/ on :8000

Reads site.json for configuration and content/ for markdown. Output is plain
static files: upload dist/ anywhere, no runtime and no dependencies.
"""

import argparse
import datetime
import html
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))

from markdown import parse_frontmatter, plain_text, render  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
CONTENT = os.path.join(ROOT, "content")
STATIC = os.path.join(ROOT, "static")

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def esc(s):
    return html.escape(str(s), quote=True)


def load_config():
    with open(os.path.join(ROOT, "site.json")) as f:
        return json.load(f)


def load_dir(subdir):
    d = os.path.join(CONTENT, subdir)
    if not os.path.isdir(d):
        return []
    docs = []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(d, name)) as f:
            meta, body = parse_frontmatter(f.read())
        meta.setdefault("slug", name[:-3])
        meta["body"] = body
        docs.append(meta)
    return docs


def fmt_date(iso, long=False):
    try:
        d = datetime.date.fromisoformat(iso)
    except (ValueError, TypeError):
        return iso or ""
    return (
        f"{MONTHS[d.month - 1]} {d.day}, {d.year}" if long else f"{MONTHS[d.month - 1]} {d.year}"
    )


# --- templates --------------------------------------------------------------


def clamp(text, limit):
    """Trim to `limit` chars on a word boundary, preferring a sentence end.

    A meta description Google cuts mid-word looks broken in results, so this
    is a safety net under whatever `description:` a post declares.
    """
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= limit:
        return text
    window = text[: limit + 1]
    stop = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
    if stop >= limit * 0.6:
        return window[: stop + 1].strip()
    return window[: window.rfind(" ")].rstrip(" ,;:—-") + "…"


def abs_url(cfg, path):
    """Absolute URL. Structured data and OG tags must never use relative paths."""
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return cfg["url"].rstrip("/") + "/" + path.lstrip("/")


def person_schema(cfg):
    """The Person entity, referenced by @id from every other schema block."""
    seo = cfg.get("seo", {})
    node = {
        "@type": "Person",
        "@id": cfg["url"].rstrip("/") + "/#person",
        "name": cfg["author"],
        "url": cfg["url"],
        "email": cfg.get("email", ""),
        "description": cfg.get("intro", cfg["description"]),
    }
    if seo.get("job_title"):
        node["jobTitle"] = seo["job_title"]
    if seo.get("works_for"):
        node["worksFor"] = {"@type": "Organization", "name": seo["works_for"]}
    if seo.get("same_as"):
        node["sameAs"] = seo["same_as"]
    if seo.get("knows_about"):
        node["knowsAbout"] = seo["knows_about"]
    if seo.get("default_image"):
        node["image"] = abs_url(cfg, seo["default_image"])
    return {k: v for k, v in node.items() if v}


def json_ld(blocks):
    payload = {"@context": "https://schema.org", "@graph": blocks}
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    # </script> inside a JSON string would close the tag early.
    text = text.replace("<", "\\u003c")
    return f'<script type="application/ld+json">\n{text}\n</script>'


def layout(
    cfg,
    *,
    title,
    body,
    description="",
    path="/",
    extra_class="",
    og_type="website",
    image="",
    schema=None,
    noindex=False,
    published="",
    modified="",
):
    nav = "\n".join(
        f'        <a href="{esc(i["href"])}">{esc(i["label"])}</a>' for i in cfg["nav"]
    )
    social = " · ".join(
        f'<a href="{esc(s["href"])}"'
        + (' target="_blank" rel="noopener"' if s["href"].startswith("http") else "")
        + f">{esc(s['label'])}</a>"
        for s in cfg.get("social", [])
    )
    seo = cfg.get("seo", {})
    canonical = cfg["url"].rstrip("/") + path
    # Only append the site name when there's room inside Google's ~60 char
    # display width; otherwise the suffix just pushes the real title out.
    if title == cfg["title"] or len(title) + len(cfg["title"]) + 3 > 60:
        full_title = title
    else:
        full_title = f"{title} — {cfg['title']}"
    desc = clamp(description or cfg["description"], 158)
    year = datetime.date.today().year
    cls = f' class="{extra_class}"' if extra_class else ""

    img = abs_url(cfg, image or seo.get("default_image", ""))
    tags = []
    if img:
        tags += [
            f'<meta property="og:image" content="{esc(img)}">',
            f'<meta property="og:image:alt" content="{esc(title)}">',
            f'<meta name="twitter:image" content="{esc(img)}">',
        ]
    card = "summary_large_image" if img else "summary"
    tags.append(f'<meta name="twitter:card" content="{card}">')
    if seo.get("twitter"):
        tags += [
            f'<meta name="twitter:site" content="{esc(seo["twitter"])}">',
            f'<meta name="twitter:creator" content="{esc(seo["twitter"])}">',
        ]
    if og_type == "article":
        if published:
            tags.append(
                f'<meta property="article:published_time" content="{esc(published)}">'
            )
        if modified:
            tags.append(
                f'<meta property="article:modified_time" content="{esc(modified)}">'
            )
        tags.append(f'<meta property="article:author" content="{esc(cfg["author"])}">')

    robots = (
        "noindex, nofollow"
        if noindex
        else "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1"
    )
    extra_meta = "\n".join(tags)
    structured = json_ld(schema) if schema else ""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="author" content="{esc(cfg["author"])}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="{esc(og_type)}">
<meta property="og:site_name" content="{esc(cfg["title"])}">
<meta property="og:locale" content="{esc(seo.get("locale", "en_US"))}">
<meta property="og:title" content="{esc(full_title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta name="twitter:title" content="{esc(full_title)}">
<meta name="twitter:description" content="{esc(desc)}">
{extra_meta}
<link rel="alternate" type="application/rss+xml" title="{esc(cfg['title'])}" href="/rss.xml">
<link rel="preload" href="/fonts/inter-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/styles.css">
{structured}
</head>
<body{cls}>
<a class="skip" href="#main">Skip to content</a>
<div class="wrap">
  <header class="site-header">
    <a class="wordmark" href="/">{esc(cfg["title"])}</a>
    <nav>
{nav}
    </nav>
  </header>

  <main id="main">
{body}
  </main>

  <footer class="site-footer">
    <h2 class="section-title">Say hello</h2>
    <p class="footer-links">{social}</p>
    <p class="colophon">© {year} {esc(cfg["author"])}</p>
  </footer>
</div>
</body>
</html>
"""


def essay_list(posts, limit=None):
    rows = []
    for p in posts[:limit] if limit else posts:
        rows.append(
            f'      <li><a href="/{esc(p["slug"])}/">{esc(p["title"])}</a>'
            f'<span class="date">{esc(fmt_date(p.get("date", "")))}</span></li>'
        )
    return '    <ul class="essays">\n' + "\n".join(rows) + "\n    </ul>"


def card_list(items):
    """Render a .cards list. Entries without an href render unlinked."""

    def name(c):
        if c.get("href"):
            return (
                f'<a class="card-name" href="{esc(c["href"])}"'
                f' target="_blank" rel="noopener">{esc(c["name"])}</a>'
            )
        return f'<span class="card-name">{esc(c["name"])}</span>'

    return "\n".join(
        f"""      <li>
        {name(c)}
        <p>{esc(c["blurb"])}</p>
      </li>"""
        for c in items
    )


def home_page(cfg, posts):
    building = card_list(cfg.get("building", []))
    previously = card_list(cfg.get("previously", []))
    investing = " · ".join(
        f'<a href="{esc(i["href"])}" target="_blank" rel="noopener">{esc(i["name"])}</a>'
        + (f' <span class="note">({esc(i["note"])})</span>' if i.get("note") else "")
        for i in cfg.get("investing", [])
    )
    n = cfg.get("homepage_essay_count", 6)
    more = (
        '\n    <p class="more"><a href="/essays/">All essays →</a></p>'
        if len(posts) > n
        else ""
    )

    body = f"""    <section class="intro">
      <h1>{esc(cfg["title"])}</h1>
      <p class="lede">{esc(cfg["intro"])}</p>
    </section>

    <section>
      <h2 class="section-title">What I'm building</h2>
      <ul class="cards">
{building}
      </ul>
    </section>

    <section>
      <h2 class="section-title">Previously</h2>
      <ul class="cards">
{previously}
      </ul>
    </section>

    <section>
      <h2 class="section-title">What I'm backing</h2>
      <p class="inline-list">{investing}</p>
    </section>

    <section>
      <h2 class="section-title">What I'm thinking</h2>
{essay_list(posts, n)}{more}
    </section>"""

    base = cfg["url"].rstrip("/")
    schema = [
        person_schema(cfg),
        {
            "@type": "WebSite",
            "@id": base + "/#website",
            "url": cfg["url"],
            "name": cfg["title"],
            "description": cfg["description"],
            "inLanguage": "en-US",
            "publisher": {"@id": base + "/#person"},
        },
        {
            "@type": "ProfilePage",
            "@id": base + "/#webpage",
            "url": cfg["url"],
            "name": cfg["title"],
            "isPartOf": {"@id": base + "/#website"},
            "about": {"@id": base + "/#person"},
            "mainEntity": {"@id": base + "/#person"},
        },
    ]
    return layout(cfg, title=cfg["title"], body=body, path="/", schema=schema)


def essays_index(cfg, posts):
    body = f"""    <section class="intro">
      <h1>Essays</h1>
      <p class="lede">Operations, AI, and venture capital.</p>
    </section>

    <section>
{essay_list(posts)}
    </section>"""

    base = cfg["url"].rstrip("/")
    schema = [
        {
            "@type": "CollectionPage",
            "@id": base + "/essays/#webpage",
            "url": base + "/essays/",
            "name": "Essays",
            "description": "Essays on operations, AI, and venture capital by "
            + cfg["author"],
            "isPartOf": {"@id": base + "/#website"},
            "author": {"@id": base + "/#person"},
        },
        {
            "@type": "ItemList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i,
                    "url": f"{base}/{p['slug']}/",
                    "name": p["title"],
                }
                for i, p in enumerate(posts, 1)
            ],
        },
        breadcrumbs(cfg, [("Essays", "/essays/")]),
    ]
    return layout(
        cfg,
        title="Essays",
        body=body,
        description=f"Essays on operations, AI, and venture capital by {cfg['author']}.",
        path="/essays/",
        schema=schema,
    )


def breadcrumbs(cfg, trail):
    """trail: [(name, path)] after Home. Helps Google render the URL path."""
    base = cfg["url"].rstrip("/")
    items = [{"@type": "ListItem", "position": 1, "name": "Home", "item": base + "/"}]
    for i, (name, path) in enumerate(trail, 2):
        items.append(
            {"@type": "ListItem", "position": i, "name": name, "item": base + path}
        )
    return {"@type": "BreadcrumbList", "itemListElement": items}


def reading_time(text):
    words = len(plain_text(text).split())
    return max(1, round(words / 225)), words


def related_posts(post, posts, limit=3):
    """Pick the nearest posts by shared keywords, falling back to recency.

    Internal links between related essays are the cheapest ranking signal a
    small site has, so every post gets a few.
    """

    def terms(p):
        stop = {
            "the", "and", "for", "you", "your", "how", "what", "why", "with",
            "this", "that", "are", "our", "its", "was", "can", "will", "from",
            "who", "not", "但", "a", "of", "to", "in", "is", "it", "on", "an",
        }
        text = f"{p.get('title', '')} {p.get('keywords', '')}".lower()
        return {w for w in re.findall(r"[a-z]{3,}", text) if w not in stop}

    mine = terms(post)
    scored = [
        (len(mine & terms(p)), p.get("date", ""), p)
        for p in posts
        if p["slug"] != post["slug"]
    ]
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [p for _, _, p in scored[:limit]]


def post_page(cfg, post, prev_post, next_post):
    nav = []
    if next_post:
        nav.append(
            f'      <a class="prev" href="/{esc(next_post["slug"])}/">← {esc(next_post["title"])}</a>'
        )
    if prev_post:
        nav.append(
            f'      <a class="next" href="/{esc(prev_post["slug"])}/">{esc(prev_post["title"])} →</a>'
        )
    pager = (
        '\n    <nav class="pager">\n' + "\n".join(nav) + "\n    </nav>" if nav else ""
    )

    mins, words = reading_time(post["body"])
    updated = post.get("updated", "")
    meta_line = f'<time datetime="{esc(post.get("date", ""))}">{esc(fmt_date(post.get("date", ""), long=True))}</time>'
    if updated and updated != post.get("date"):
        meta_line += f' · Updated <time datetime="{esc(updated)}">{esc(fmt_date(updated, long=True))}</time>'
    meta_line += f" · {mins} min read"

    related = related_posts(post, post.get("_all", []))
    related_html = ""
    if related:
        links = "\n".join(
            f'        <li><a href="/{esc(r["slug"])}/">{esc(r["title"])}</a>'
            f'<span class="date">{esc(fmt_date(r.get("date", "")))}</span></li>'
            for r in related
        )
        related_html = f"""
    <section class="related">
      <h2 class="section-title">Related</h2>
      <ul class="essays">
{links}
      </ul>
    </section>"""

    body = f"""    <article class="post">
      <header class="post-header">
        <h1>{esc(post["title"])}</h1>
        <p class="date">{meta_line}</p>
      </header>
      <div class="prose">
{render(post["body"])}
      </div>
    </article>{pager}{related_html}"""

    base = cfg["url"].rstrip("/")
    url = f"{base}/{post['slug']}/"
    desc = post.get("description") or plain_text(post["body"], 160)
    image = post.get("image") or cfg.get("seo", {}).get("default_image", "")

    posting = {
        "@type": "BlogPosting",
        "@id": url + "#article",
        "headline": post["title"][:110],
        "description": desc,
        "url": url,
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "datePublished": post.get("date", ""),
        "dateModified": updated or post.get("date", ""),
        "author": {"@id": base + "/#person"},
        "publisher": {"@id": base + "/#person"},
        "isPartOf": {"@id": base + "/#website"},
        "inLanguage": "en-US",
        "wordCount": words,
    }
    if image:
        posting["image"] = abs_url(cfg, image)
    if post.get("keywords"):
        posting["keywords"] = [k.strip() for k in post["keywords"].split(",") if k.strip()]

    schema = [
        posting,
        breadcrumbs(cfg, [("Essays", "/essays/"), (post["title"], f"/{post['slug']}/")]),
    ]

    return layout(
        cfg,
        # `seo_title` lets a long editorial headline keep a short search title.
        title=post.get("seo_title") or post["title"],
        body=body,
        description=desc,
        path=f"/{post['slug']}/",
        extra_class="single",
        og_type="article",
        image=image,
        schema=schema,
        published=post.get("date", ""),
        modified=updated or post.get("date", ""),
        noindex=post.get("noindex", "").lower() in ("true", "yes", "1"),
    )


def page_page(cfg, page):
    extra = ""
    if page["slug"] == "newsletter":
        # The exported page usually carries its own Substack iframe; only add
        # one when it doesn't, so the form never renders twice.
        if "<iframe" not in page["body"]:
            extra += f"""
      <div class="embed">
        <iframe src="{esc(cfg["substack"])}/embed" title="Newsletter signup"
                width="480" height="150" frameborder="0" scrolling="no"></iframe>
      </div>"""
        extra += (
            f'\n      <p class="fallback">Or <a href="{esc(cfg["substack"])}"'
            ' target="_blank" rel="noopener">subscribe on Substack</a>.</p>'
        )
    body = f"""    <article class="post">
      <header class="post-header">
        <h1>{esc(page["title"])}</h1>
      </header>
      <div class="prose">
{render(page["body"])}{extra}
      </div>
    </article>"""
    base = cfg["url"].rstrip("/")
    url = f"{base}/{page['slug']}/"
    desc = page.get("description") or plain_text(page["body"], 160)
    schema = [
        {
            "@type": "AboutPage" if page["slug"] == "about" else "WebPage",
            "@id": url + "#webpage",
            "url": url,
            "name": page["title"],
            "description": desc,
            "isPartOf": {"@id": base + "/#website"},
            "about": {"@id": base + "/#person"},
            "inLanguage": "en-US",
        },
        breadcrumbs(cfg, [(page["title"], f"/{page['slug']}/")]),
    ]
    return layout(
        cfg,
        title=page["title"],
        body=body,
        description=desc,
        path=f"/{page['slug']}/",
        extra_class="single",
        schema=schema,
    )


def rss(cfg, posts):
    items = []
    for p in posts:
        link = f"{cfg['url'].rstrip('/')}/{p['slug']}/"
        try:
            d = datetime.date.fromisoformat(p["date"])
            pub = d.strftime("%a, %d %b %Y 00:00:00 +0000")
        except (ValueError, KeyError):
            pub = ""
        full = render(p["body"]).replace("]]>", "]]]]><![CDATA[>")
        items.append(
            f"""  <item>
    <title>{esc(p["title"])}</title>
    <link>{esc(link)}</link>
    <guid isPermaLink="true">{esc(link)}</guid>
    <pubDate>{pub}</pubDate>
    <dc:creator>{esc(cfg["author"])}</dc:creator>
    <description>{esc(p.get("description") or plain_text(p["body"], 300))}</description>
    <content:encoded><![CDATA[{full}]]></content:encoded>
  </item>"""
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel>
  <title>{esc(cfg["title"])}</title>
  <link>{esc(cfg["url"])}</link>
  <description>{esc(cfg["description"])}</description>
  <language>en-us</language>
  <atom:link href="{esc(cfg["url"].rstrip("/"))}/rss.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
</channel>
</rss>
"""


def sitemap(cfg, entries):
    """entries: [(path, lastmod, priority)]. lastmod tells crawlers what to recheck."""
    base = cfg["url"].rstrip("/")
    rows = []
    for path, lastmod, priority in sorted(set(entries)):
        row = f"  <url>\n    <loc>{esc(base + path)}</loc>"
        if lastmod:
            row += f"\n    <lastmod>{esc(lastmod)}</lastmod>"
        row += f"\n    <priority>{priority}</priority>\n  </url>"
        rows.append(row)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(rows)
        + "\n</urlset>\n"
    )


# --- build ------------------------------------------------------------------


BASE = ""  # set by --base, e.g. "/chloealpert-ms" for GitHub project pages


def write(relpath, text):
    dest = os.path.join(DIST, relpath.lstrip("/"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if BASE and relpath.endswith(".html"):
        # Prefix root-relative links only. Absolute URLs (canonical, og:url,
        # outbound links) start with a scheme and are left alone.
        text = re.sub(r'(href|src)="/(?!/)', rf'\1="{BASE}/', text)
    with open(dest, "w") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true", help="serve dist/ after building")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument(
        "--base",
        default="",
        help="path prefix for hosting in a subdirectory, e.g. /repo-name "
        "for GitHub project pages. Not needed on a custom domain.",
    )
    args = ap.parse_args()

    global BASE
    BASE = args.base.rstrip("/")

    cfg = load_config()
    posts = load_dir("posts")
    pages = load_dir("pages")
    posts.sort(key=lambda p: p.get("date", ""), reverse=True)

    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)

    # Posts need to see each other to compute "Related".
    for p in posts:
        p["_all"] = posts

    newest = posts[0].get("date", "") if posts else ""
    entries = [("/", newest, "1.0"), ("/essays/", newest, "0.9")]
    write("index.html", home_page(cfg, posts))
    write("essays/index.html", essays_index(cfg, posts))

    for i, p in enumerate(posts):
        prev_post = posts[i - 1] if i > 0 else None  # newer
        next_post = posts[i + 1] if i + 1 < len(posts) else None  # older
        write(f"{p['slug']}/index.html", post_page(cfg, p, prev_post, next_post))
        if p.get("noindex", "").lower() not in ("true", "yes", "1"):
            entries.append(
                (f"/{p['slug']}/", p.get("updated") or p.get("date", ""), "0.8")
            )

    for p in pages:
        write(f"{p['slug']}/index.html", page_page(cfg, p))
        entries.append((f"/{p['slug']}/", p.get("updated", ""), "0.7"))

    write("rss.xml", rss(cfg, posts))
    write("sitemap.xml", sitemap(cfg, entries))
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {cfg['url'].rstrip('/')}/sitemap.xml\n")
    write("404.html", layout(
        cfg,
        title="Not found",
        body='    <section class="intro">\n      <h1>Not found</h1>\n'
             '      <p class="lede">That page doesn\'t exist. '
             'Try the <a href="/essays/">essays</a>.</p>\n    </section>',
        path="/404.html",
    ))

    for name in os.listdir(STATIC):
        src = os.path.join(STATIC, name)
        dst = os.path.join(DIST, name)
        shutil.copytree(src, dst) if os.path.isdir(src) else shutil.copy2(src, dst)

    print(f"Built {len(posts)} posts, {len(pages)} pages -> dist/")

    # Surface SEO errors right where you'd notice them, without failing the build.
    try:
        from seo_check import audit

        _, issues = audit()
        errs = sum(1 for v in issues.values() for lvl, _ in v if lvl == "error")
        warns = sum(1 for v in issues.values() for lvl, _ in v if lvl == "warn")
        if errs or warns:
            print(f"SEO: {errs} errors, {warns} warnings — python3 tools/seo_check.py")
        else:
            print("SEO: clean")
    except Exception:  # noqa: BLE001 - the audit must never break a build
        pass

    if args.serve:
        import functools
        import http.server

        os.chdir(DIST)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DIST)
        print(f"Serving http://localhost:{args.port}  (ctrl-c to stop)")
        http.server.ThreadingHTTPServer(("", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
