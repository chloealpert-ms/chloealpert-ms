"""A small markdown renderer covering exactly the subset used in content/.

Supported: ATX headings, paragraphs (single newlines become <br>), unordered
and ordered lists, blockquotes, images with optional italic captions, links,
**bold**, _italic_, `code`, --- rules, and raw HTML blocks flagged with an
opening `<!--raw-->` line.

Deliberately not a general markdown implementation. If you start writing
content that needs more than this, the renderer is the thing to extend.
"""

import html
import re

__all__ = ["render", "parse_frontmatter", "plain_text"]


def parse_frontmatter(text):
    """Split a `---` delimited key: "value" header off the top of a document."""
    meta = {}
    if not text.startswith("---"):
        return meta, text
    end = text.find("\n---", 3)
    if end == -1:
        return meta, text
    head = text[3:end]
    body = text[end + 4 :].lstrip("\n")
    for line in head.strip().splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = v[1:-1].replace('\\"', '"')
        meta[k.strip()] = v
    return meta, body


# --- inline ----------------------------------------------------------------

_TOKEN = "\x00%d\x00"


def _inline(text):
    """Escape, then apply inline markdown. Code spans are shielded first."""
    shielded = []

    def shield(m):
        shielded.append(m.group(1))
        return _TOKEN % (len(shielded) - 1)

    text = re.sub(r"`([^`]+)`", shield, text)
    text = html.escape(text, quote=False)

    # Links: [label](href). Labels may contain bold/italic, handled after.
    def link(m):
        label, href = m.group(1), m.group(2)
        href = html.escape(href, quote=True)
        ext = href.startswith("http") or href.startswith("mailto:")
        attrs = ' target="_blank" rel="noopener"' if href.startswith("http") else ""
        return f'<a href="{href}"{attrs}>{label}</a>'

    text = re.sub(r"\[([^\]]*)\]\(([^)\s]+)\)", link, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text, flags=re.S)
    text = re.sub(r"(?<![\w\\])_(.+?)_(?![\w])", r"<em>\1</em>", text, flags=re.S)

    for i, code in enumerate(shielded):
        text = text.replace(
            _TOKEN % i, "<code>" + html.escape(code, quote=False) + "</code>"
        )
    return text


def _para(block):
    """Single newlines inside a paragraph are hard breaks (WordPress <br>)."""
    lines = [_inline(l.strip()) for l in block.split("\n") if l.strip()]
    return "<p>" + "<br>\n".join(lines) + "</p>"


# --- block -----------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_ULI = re.compile(r"^(\s*)[-*]\s+(.*)$")
_OLI = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
_IMG = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)$")


def _parse_items(lines):
    """Lines -> [(indent_level, ordered, text)], joining wrapped lines."""
    items = []
    for line in lines:
        mo, mu = _OLI.match(line), _ULI.match(line)
        if mo:
            items.append([len(mo.group(1)) // 2, True, mo.group(3).strip()])
        elif mu:
            items.append([len(mu.group(1)) // 2, False, mu.group(2).strip()])
        elif items and line.strip():
            items[-1][2] += " " + line.strip()
    return items


def _render_items(items, pos, level):
    """Render items at `level`, recursing into deeper ones. Returns (html, pos)."""
    ordered = items[pos][1]
    tag = "ol" if ordered else "ul"
    parts = [f"<{tag}>"]
    open_li = False
    while pos < len(items):
        indent, _, text = items[pos]
        if indent < level:
            break
        if indent > level:
            nested, pos = _render_items(items, pos, indent)
            if open_li:
                parts[-1] = parts[-1][: -len("</li>")] + "\n" + nested + "</li>"
            else:
                parts.append(f"<li>{nested}</li>")
            continue
        parts.append(f"  <li>{_inline(text)}</li>")
        open_li = True
        pos += 1
    parts.append(f"</{tag}>")
    return "\n".join(parts), pos


def _slugify(text):
    s = re.sub(r"<[^>]+>", "", text).lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    return re.sub(r"[\s-]+", "-", s).strip("-")


def render(text):
    """Markdown -> HTML string."""
    out = []
    blocks = re.split(r"\n[ \t]*\n", text.strip())
    for block in blocks:
        block = block.strip("\n")
        if not block.strip():
            continue
        lines = block.split("\n")

        if lines[0].strip() == "<!--raw-->":
            out.append("\n".join(lines[1:]).strip())
            continue

        if re.fullmatch(r"-{3,}|\*{3,}", block.strip()):
            out.append("<hr>")
            continue

        m = _HEADING.match(lines[0])
        if m and len(lines) == 1:
            level = len(m.group(1))
            body = _inline(m.group(2).strip())
            # Headings are often wrapped in ** in the exported content; the
            # weight comes from the heading itself, so unwrap it.
            body = re.sub(r"^<strong>(.*)</strong>$", r"\1", body, flags=re.S)
            out.append(f'<h{level} id="{_slugify(body)}">{body}</h{level}>')
            continue

        m = _IMG.match(lines[0])
        if m:
            alt = html.escape(m.group(1), quote=True)
            src = html.escape(m.group(2), quote=True)
            cap = ""
            rest = "\n".join(lines[1:]).strip()
            if rest.startswith("*") and rest.endswith("*"):
                cap = f"<figcaption>{_inline(rest.strip('*'))}</figcaption>"
            out.append(
                f'<figure><img src="{src}" alt="{alt}" loading="lazy">{cap}</figure>'
            )
            continue

        if all(l.strip().startswith(">") for l in lines):
            inner = "\n".join(re.sub(r"^\s*>\s?", "", l) for l in lines)
            out.append(f"<blockquote>{_para(inner)}</blockquote>")
            continue

        if _ULI.match(lines[0]) or _OLI.match(lines[0]):
            items = _parse_items(lines)
            if items:
                body, _ = _render_items(items, 0, items[0][0])
                out.append(body)
            continue

        out.append(_para(block))

    return "\n\n".join(out)


def plain_text(markdown, limit=None):
    """Strip markup for use in meta descriptions and RSS summaries."""
    t = re.sub(r"^#{1,6}\s+", "", markdown, flags=re.M)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[*_`>]", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if limit and len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "…"
    return t
