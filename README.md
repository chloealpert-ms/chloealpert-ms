# chloealpert.com

Static site, migrated off WordPress. No framework, no npm, no dependencies —
just Python 3 and a build script.

## Preview it

```bash
python3 build.py --serve
```

Then open **http://localhost:8000**. That's the whole preview loop — edit a
file, re-run, refresh.

To build without serving (output lands in `dist/`):

```bash
python3 build.py
```

### Why GitHub Pages showed nothing

Pages serves from the repo root or `/docs`, never from `dist/`, so there was
nothing for it to publish. `.github/workflows/deploy.yml` fixes that: it
builds on every push to `main` and deploys `dist/` to Pages.

To turn it on, in the repo: **Settings → Pages → Source → GitHub Actions.**

One catch. Until a custom domain is attached, the site lives at
`chloealpert-ms.github.io/chloealpert-ms/`, and every root-relative link
(`/styles.css`) resolves to the wrong place. Set a repo variable
**Settings → Secrets and variables → Actions → Variables**, named
`BASE_PATH`, value `/chloealpert-ms`. The workflow passes it to
`--base` and the links resolve.

When you point `www.chloealpert.com` at Pages, delete that variable and add a
`CNAME` file containing `www.chloealpert.com` to `static/`. Don't add it
before DNS is ready — Pages will redirect the github.io URL to a domain that
isn't serving yet, and you'll lose the preview.

## Layout

```
content/posts/     one markdown file per essay
content/pages/     about, press-and-awards, newsletter
static/            styles.css, fonts, images — copied to dist/ verbatim
site.json          name, bio, nav, project and investment lists, socials, SEO defaults
build.py           the generator
tools/new_post.py  scaffolds a new post with SEO frontmatter
tools/seo_check.py audits the built site
tools/markdown.py  markdown renderer
tools/export_wordpress.py   the one-time WordPress import
```

## Publishing a new essay

```bash
python3 tools/new_post.py "Why smaller AI models win"
```

That creates `content/posts/why-smaller-ai-models-win.md`, dated today, with
every SEO field stubbed out. Fill in the frontmatter, write the body, then:

```bash
python3 build.py && python3 tools/seo_check.py
```

The essay appears on the homepage, in `/essays/`, in `rss.xml`, and in
`sitemap.xml` automatically. Posts sort by `date`, newest first.

### The frontmatter fields

| field | what it does |
| --- | --- |
| `title` | the H1 and the link text in listings |
| `date` | `YYYY-MM-DD`. Drives sort order and `datePublished` |
| `slug` | the URL. Keep it short and keyword-bearing; don't change it after publishing |
| `description` | **your search snippet.** 70–158 chars. The single highest-leverage field |
| `keywords` | comma-separated topics. Feeds schema and the "Related" picker |
| `seo_title` | short title for search results when the headline is long |
| `image` | 1200×630 social card. Falls back to `seo.default_image` |
| `updated` | `YYYY-MM-DD` if you revise it. Shows as "Updated" and sets `dateModified` |
| `noindex` | `"true"` to keep a page out of Google and the sitemap |

Supported markdown: headings, paragraphs, `- ` and `1. ` lists (nested with
two-space indents), `> ` quotes, `[links](url)`, `**bold**`, `_italic_`,
`` `code` ``, `![images](/images/x.png)`, and `---` rules. A block starting
with `<!--raw-->` is passed through as raw HTML — that's how the Substack
embed works.

## The SEO machinery

Every page ships with a canonical URL, Open Graph and Twitter card tags, and
JSON-LD structured data — `BlogPosting` plus `BreadcrumbList` on essays,
`Person` and `WebSite` sitewide, so Google can attach the writing to you as
an author entity. Titles drop the site-name suffix rather than overflow 60
characters, and descriptions are trimmed at a sentence boundary rather than
cut mid-word. Posts link to related posts automatically, which is the
cheapest ranking signal a small site has.

`sitemap.xml` carries `lastmod` and priorities; `rss.xml` carries full post
content.

### The audit

```bash
python3 tools/seo_check.py
```

Checks every built page for title and description length, a single H1, image
alt text, canonical tags, valid structured data, thin content, orphan pages,
and duplicate titles or descriptions. `--strict` exits non-zero on errors, so
CI fails a bad deploy — the workflow already runs it that way.

`build.py` prints a one-line summary of the same audit on every build.

### The one thing left to do

There's no social share image yet, which is why the audit warns on every
page. Make one 1200×630 PNG, drop it at `static/images/og-default.png`, and
set `seo.default_image` in `site.json` to `/images/og-default.png`. Every
warning clears, and shared links start rendering a preview card instead of a
bare URL. Individual posts can override it with their own `image`.

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
