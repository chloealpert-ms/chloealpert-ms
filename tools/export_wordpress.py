#!/usr/bin/env python3
"""One-time export of chloealpert.com from the WordPress REST API into
markdown files under content/. Re-runnable: it overwrites what it writes.

Usage: python3 tools/export_wordpress.py
"""

import html
import json
import os
import re
import urllib.parse
import urllib.request

SITE = "https://chloealpert.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(ROOT, "content", "posts")
PAGES_DIR = os.path.join(ROOT, "content", "pages")
IMG_DIR = os.path.join(ROOT, "static", "images")


# The host rejects urllib's default user agent with a 406.
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) chloealpert-site-export"


def _get(url):
    return urllib.request.Request(url, headers={"User-Agent": UA})


def fetch_json(path):
    with urllib.request.urlopen(_get(f"{SITE}/wp-json/wp/v2/{path}")) as r:
        return json.load(r)


# --- HTML -> markdown -------------------------------------------------------
# The source content only uses a small tag vocabulary (p, h2-h4, ul/ol/li, a,
# strong, em, br, blockquote, figure/img, iframe). We convert that subset and
# pass anything else through as raw HTML, which the renderer also allows.

BLOCK_RE = re.compile(r"<(p|h[1-6]|ul|ol|blockquote|figure|div|center)\b", re.I)


def unwrap(text):
    """Inline HTML -> markdown."""
    t = text
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</?(strong|b)>", "**", t, flags=re.I)
    t = re.sub(r"</?(em|i|cite)>", "_", t, flags=re.I)
    t = re.sub(
        r'<a\b[^>]*?href="([^"]*)"[^>]*>(.*?)</a>',
        lambda m: f"[{unwrap(m.group(2)).strip()}]({m.group(1)})",
        t,
        flags=re.I | re.S,
    )
    t = re.sub(r"</?span\b[^>]*>", "", t, flags=re.I)
    t = re.sub(r"</?sup>", "", t, flags=re.I)
    t = html.unescape(t)
    # Collapse the runs of whitespace WordPress leaves behind, but keep the
    # newlines we just made out of <br>.
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def list_items(chunk):
    """Split a <ul>/<ol> body into <li> contents, respecting nested lists.

    A naive non-greedy regex stops at the first </li>, which for WordPress's
    nested markup (<li>text<ul><li>sub</li></ul></li>) swallows the structure
    and leaks literal tags into the output. So track depth instead.
    """
    items = []
    depth = 0
    start = None
    for m in re.finditer(r"<(/?)(li|ul|ol)\b[^>]*>", chunk, flags=re.I):
        closing, tag = m.group(1) == "/", m.group(2).lower()
        if tag == "li":
            if not closing:
                if depth == 0:
                    start = m.end()
                depth += 1
            else:
                depth -= 1
                if depth == 0 and start is not None:
                    items.append(chunk[start : m.start()])
                    start = None
        elif not closing and depth > 0:
            # entering a nested list: its <li>s belong to the parent item
            depth += 1
        elif closing and depth > 0:
            depth -= 1
    if start is not None:  # unclosed final <li>
        items.append(chunk[start:])
    return items


def render_list(inner, ordered, indent=0):
    """Emit markdown list lines, recursing into nested <ul>/<ol>."""
    lines = []
    pad = "  " * indent
    for i, li in enumerate(list_items(inner), 1):
        nested = list(re.finditer(r"<(ul|ol)\b[^>]*>(.*)</\1>", li, flags=re.I | re.S))
        own = re.sub(r"<(ul|ol)\b[^>]*>.*</\1>", "", li, flags=re.I | re.S)
        body = unwrap(own).replace("\n", " ").strip()
        marker = f"{i}." if ordered else "-"
        if body:
            lines.append(f"{pad}{marker} {body}")
        for n in nested:
            lines.extend(
                render_list(
                    n.group(2),
                    n.group(1).lower() == "ol",
                    indent + (1 if body else 0),
                )
            )
    return lines


def clean_iframe(tag):
    """Rebuild an <iframe> from its src, dropping WordPress's malformed
    attributes (the Substack embed ships width="350 "max-width="580")."""
    src = re.search(r'src="([^"]*)"', tag, flags=re.I)
    if not src:
        return tag
    url = html.unescape(src.group(1))
    height = re.search(r'height="(\d+)', tag, flags=re.I)
    h = height.group(1) if height else "150"
    title = "Newsletter signup" if "substack" in url else "Embedded content"
    return (
        f'<iframe src="{url}" title="{title}" width="480" height="{h}" '
        'frameborder="0" scrolling="no" loading="lazy"></iframe>'
    )


def iter_blocks(content):
    """Yield (tag, inner_html) for each top-level block.

    Uses depth tracking rather than a non-greedy regex: a lazy match on
    <ul>(.*?)</ul> terminates at the first nested </ul> and truncates the
    item, which is exactly the shape WordPress emits for sub-lists.
    """
    tags = "p|h[1-6]|ul|ol|blockquote|figure|div|center"
    pos = 0
    while True:
        m = re.compile(f"<({tags})\\b[^>]*>", re.I).search(content, pos)
        if not m:
            return
        tag = m.group(1).lower()
        depth = 1
        scan = m.end()
        close = re.compile(f"<(/?){re.escape(tag)}\\b[^>]*>", re.I)
        while depth:
            c = close.search(content, scan)
            if not c:
                yield tag, content[m.end() :]
                return
            depth += -1 if c.group(1) else 1
            scan = c.end()
        yield tag, content[m.end() : scan - len(c.group(0))]
        pos = scan


def to_markdown(content, image_map):
    out = []
    for tag, inner in iter_blocks(content):
        if tag == "p":
            body = unwrap(inner)
            if body:
                out.append(body)
        elif re.fullmatch(r"h[1-6]", tag):
            level = int(tag[1])
            body = unwrap(inner)
            if body:
                out.append("#" * level + " " + body)
        elif tag in ("ul", "ol"):
            lines = render_list(inner, tag == "ol")
            if lines:
                out.append("\n".join(lines))
        elif tag == "blockquote":
            body = unwrap(re.sub(r"</?p\b[^>]*>", "\n", inner, flags=re.I))
            lines = [l.strip() for l in body.split("\n") if l.strip()]
            if lines:
                out.append("\n".join("> " + l for l in lines))
        elif tag in ("figure", "div", "center"):
            img = re.search(r'<img\b[^>]*?src="([^"]*)"[^>]*>', inner, flags=re.I)
            iframe = re.search(r"<iframe\b.*?</iframe>", inner, flags=re.I | re.S)
            cap = re.search(
                r"<figcaption\b[^>]*>(.*?)</figcaption>", inner, flags=re.I | re.S
            )
            if img:
                src = image_map.get(img.group(1), img.group(1))
                alt = re.search(r'alt="([^"]*)"', img.group(0), flags=re.I)
                alt = html.unescape(alt.group(1)) if alt else ""
                caption = unwrap(cap.group(1)) if cap else ""
                out.append(f"![{alt}]({src})" + (f"\n*{caption}*" if caption else ""))
            elif iframe:
                out.append("<!--raw-->\n" + clean_iframe(iframe.group(0).strip()))
    return "\n\n".join(out) + "\n"


def download_images(docs):
    """Pull every uploaded image local so the site has no wp-content deps."""
    os.makedirs(IMG_DIR, exist_ok=True)
    mapping = {}
    urls = set()
    for d in docs:
        for src in re.findall(
            r'<img\b[^>]*?src="([^"]*)"', d["content"]["rendered"], flags=re.I
        ):
            urls.add(html.unescape(src))
    for url in sorted(urls):
        name = os.path.basename(urllib.parse.urlparse(url).path)
        dest = os.path.join(IMG_DIR, name)
        if not os.path.exists(dest):
            try:
                with urllib.request.urlopen(_get(url)) as r, open(dest, "wb") as f:
                    f.write(r.read())
                print(f"  image {name}")
            except Exception as e:  # noqa: BLE001 - report and keep the remote URL
                print(f"  FAILED {url}: {e}")
                continue
        mapping[url] = f"/images/{name}"
    return mapping


def frontmatter(fields):
    lines = ["---"]
    for k, v in fields.items():
        v = str(v).replace('"', '\\"')
        lines.append(f'{k}: "{v}"')
    lines.append("---")
    return "\n".join(lines)


def main():
    posts = fetch_json("posts?per_page=100&orderby=date&order=desc")
    pages = fetch_json("pages?per_page=100")
    os.makedirs(POSTS_DIR, exist_ok=True)
    os.makedirs(PAGES_DIR, exist_ok=True)

    print("Downloading images...")
    image_map = download_images(posts + pages)

    for p in posts:
        title = html.unescape(re.sub(r"<[^>]+>", "", p["title"]["rendered"]))
        excerpt = html.unescape(
            re.sub(r"<[^>]+>", "", p["excerpt"]["rendered"])
        ).strip()
        excerpt = re.sub(r"\s+", " ", excerpt).replace(" […]", "…")
        body = to_markdown(p["content"]["rendered"], image_map)
        fm = frontmatter(
            {
                "title": title,
                "date": p["date"][:10],
                "slug": p["slug"],
                "description": excerpt,
            }
        )
        path = os.path.join(POSTS_DIR, f"{p['slug']}.md")
        with open(path, "w") as f:
            f.write(fm + "\n\n" + body)
        print(f"  post  {p['slug']}.md")

    for p in pages:
        title = html.unescape(re.sub(r"<[^>]+>", "", p["title"]["rendered"]))
        body = to_markdown(p["content"]["rendered"], image_map)
        fm = frontmatter({"title": title, "slug": p["slug"]})
        path = os.path.join(PAGES_DIR, f"{p['slug']}.md")
        with open(path, "w") as f:
            f.write(fm + "\n\n" + body)
        print(f"  page  {p['slug']}.md")


if __name__ == "__main__":
    main()
