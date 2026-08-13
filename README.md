# chloealpert.com

Static site, migrated off WordPress. No framework, no npm, no dependencies —
just Python 3 and a build script.

## Build

```bash
python3 build.py
```

Output lands in `dist/`. To preview locally:

```bash
python3 build.py --serve
```

Then open http://localhost:8000.

## Layout

```
content/posts/     one markdown file per essay
content/pages/     about, press-and-awards, newsletter
static/            styles.css, fonts, images — copied to dist/ verbatim
site.json          name, bio, nav, project and investment lists, socials
build.py           the generator
tools/markdown.py  markdown renderer
tools/export_wordpress.py   the one-time WordPress import
```

## Writing a new essay

Add a file to `content/posts/`:

```markdown
---
title: "Your title"
date: "2026-08-13"
slug: "your-title"
description: "One or two sentences, used for search results and RSS."
---

Your first paragraph.

## A heading

- a list item
  - a nested item
```

Then run `python3 build.py`. The essay appears on the homepage, in
`/essays/`, in `rss.xml`, and in `sitemap.xml` automatically. Posts sort by
`date`, newest first.

Supported markdown: headings, paragraphs, `- ` and `1. ` lists (nested with
two-space indents), `> ` quotes, `[links](url)`, `**bold**`, `_italic_`,
`` `code` ``, `![images](/images/x.png)`, and `---` rules. A block starting
with `<!--raw-->` is passed through as raw HTML — that's how the Substack
embed works.

## Editing the homepage

Everything on the homepage outside the essay list comes from `site.json`:
the bio line, the "What I'm building" cards, and the investment list. Add
your LinkedIn/X profiles to the `social` array and they show up in the
footer.

## Deploying

The site is plain static files, so any host works.

- **Netlify / Cloudflare Pages** — `netlify.toml` is already set up. Point it
  at this repo; build command `python3 build.py`, publish directory `dist`.
- **Vercel** — same build command and output directory.
- **GitHub Pages / S3 / anything else** — run `python3 build.py` and upload
  `dist/`.

Set your DNS to the new host when you're ready to cut over from WordPress.

### URLs

Every post and page keeps the exact slug it had on WordPress, so existing
links, shares, and search rankings carry over unchanged. `static/_redirects`
handles the few paths whose shape changed (`/feed` → `/rss.xml`, and the
press page's missing trailing slash).

## Re-importing from WordPress

`python3 tools/export_wordpress.py` re-pulls everything from the live
WordPress REST API and overwrites `content/`. It's kept for reference; once
WordPress is switched off you won't need it again.

## Fonts

Inter, self-hosted from `static/fonts/` (SIL Open Font License 1.1). No
Google Fonts request, so no third-party call on page load.
