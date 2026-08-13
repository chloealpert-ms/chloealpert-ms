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


def layout(cfg, *, title, body, description="", path="/", extra_class=""):
    nav = "\n".join(
        f'        <a href="{esc(i["href"])}">{esc(i["label"])}</a>' for i in cfg["nav"]
    )
    social = " · ".join(
        f'<a href="{esc(s["href"])}"'
        + (' target="_blank" rel="noopener"' if s["href"].startswith("http") else "")
        + f">{esc(s['label'])}</a>"
        for s in cfg.get("social", [])
    )
    canonical = cfg["url"].rstrip("/") + path
    full_title = title if title == cfg["title"] else f"{title} — {cfg['title']}"
    desc = description or cfg["description"]
    year = datetime.date.today().year
    cls = f' class="{extra_class}"' if extra_class else ""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(full_title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="application/rss+xml" title="{esc(cfg['title'])}" href="/rss.xml">
<link rel="preload" href="/fonts/inter-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/styles.css">
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


def home_page(cfg, posts):
    building = "\n".join(
        f"""      <li>
        <a class="card-name" href="{esc(b["href"])}" target="_blank" rel="noopener">{esc(b["name"])}</a>
        <p>{esc(b["blurb"])}</p>
      </li>"""
        for b in cfg.get("building", [])
    )
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
      <h2 class="section-title">What I'm thinking</h2>
{essay_list(posts, n)}{more}
    </section>

    <section>
      <h2 class="section-title">What I'm backing</h2>
      <p class="inline-list">{investing}</p>
    </section>"""
    return layout(cfg, title=cfg["title"], body=body, path="/")


def essays_index(cfg, posts):
    body = f"""    <section class="intro">
      <h1>Essays</h1>
      <p class="lede">Operations, AI, and venture capital.</p>
    </section>

    <section>
{essay_list(posts)}
    </section>"""
    return layout(cfg, title="Essays", body=body, path="/essays/")


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
    body = f"""    <article class="post">
      <header class="post-header">
        <h1>{esc(post["title"])}</h1>
        <p class="date">{esc(fmt_date(post.get("date", ""), long=True))}</p>
      </header>
      <div class="prose">
{render(post["body"])}
      </div>
    </article>{pager}"""
    return layout(
        cfg,
        title=post["title"],
        body=body,
        description=post.get("description") or plain_text(post["body"], 160),
        path=f"/{post['slug']}/",
        extra_class="single",
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
    return layout(
        cfg,
        title=page["title"],
        body=body,
        description=plain_text(page["body"], 160),
        path=f"/{page['slug']}/",
        extra_class="single",
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
        items.append(
            f"""  <item>
    <title>{esc(p["title"])}</title>
    <link>{esc(link)}</link>
    <guid isPermaLink="true">{esc(link)}</guid>
    <pubDate>{pub}</pubDate>
    <description>{esc(p.get("description") or plain_text(p["body"], 300))}</description>
  </item>"""
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
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


def sitemap(cfg, paths):
    base = cfg["url"].rstrip("/")
    urls = "\n".join(
        f"  <url><loc>{esc(base + p)}</loc></url>" for p in sorted(set(paths))
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n</urlset>\n"
    )


# --- build ------------------------------------------------------------------


def write(relpath, text):
    dest = os.path.join(DIST, relpath.lstrip("/"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true", help="serve dist/ after building")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    cfg = load_config()
    posts = load_dir("posts")
    pages = load_dir("pages")
    posts.sort(key=lambda p: p.get("date", ""), reverse=True)

    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)

    paths = ["/", "/essays/"]
    write("index.html", home_page(cfg, posts))
    write("essays/index.html", essays_index(cfg, posts))

    for i, p in enumerate(posts):
        prev_post = posts[i - 1] if i > 0 else None  # newer
        next_post = posts[i + 1] if i + 1 < len(posts) else None  # older
        write(f"{p['slug']}/index.html", post_page(cfg, p, prev_post, next_post))
        paths.append(f"/{p['slug']}/")

    for p in pages:
        write(f"{p['slug']}/index.html", page_page(cfg, p))
        paths.append(f"/{p['slug']}/")

    write("rss.xml", rss(cfg, posts))
    write("sitemap.xml", sitemap(cfg, paths))
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

    if args.serve:
        import functools
        import http.server

        os.chdir(DIST)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DIST)
        print(f"Serving http://localhost:{args.port}  (ctrl-c to stop)")
        http.server.ThreadingHTTPServer(("", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
