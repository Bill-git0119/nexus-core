"""
The Monetizer Agent
Transforms verified_data.json into professional Traditional Chinese articles.
Pulls affiliate links from links.csv and inserts them contextually.
Outputs: Notion-ready Markdown + GitHub Pages HTML.

Output files:
  monetizer/output/notion/   — one .md per article (Notion import)
  monetizer/output/ghpages/  — one .html per article + index.html (GitHub Pages)
  monetizer/output/manifest.json — build manifest for Architect
"""

from __future__ import annotations

import csv
import json
import os
import re
import html as html_lib
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERIFIED_INPUT = PROJECT_ROOT / "data" / "verified_data.json"
LINKS_CSV = PROJECT_ROOT / "config" / "links.csv"

OUTPUT_DIR = PROJECT_ROOT / "output"
NOTION_DIR = OUTPUT_DIR / "notion"
GHPAGES_DIR = OUTPUT_DIR / "ghpages"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"

# ---------------------------------------------------------------------------
# Domain → Traditional Chinese mapping
# ---------------------------------------------------------------------------
DOMAIN_LABELS = {
    "Semiconductor/Taiwan Stock Supply Chain": "半導體／台股供應鏈",
    "Longevity/Sports Medicine": "長壽科學／運動醫學",
}

CATEGORY_TAGS = {
    "semiconductor": "半導體",
    "longevity": "長壽科學",
    "sports_medicine": "運動醫學",
}


# ---------------------------------------------------------------------------
# Affiliate link loader
# ---------------------------------------------------------------------------
def load_affiliate_links(csv_path: Path) -> list[dict]:
    """Load keyword→affiliate mappings from CSV."""
    links: list[dict] = []
    if not csv_path.exists():
        print(f"[Monetizer] WARNING: {csv_path} not found. No affiliate links will be inserted.")
        return links

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            links.append(
                {
                    "keyword": row["keyword"].strip(),
                    "url": row["affiliate_url"].strip(),
                    "partner": row["partner"].strip(),
                    "category": row["category"].strip(),
                }
            )
    print(f"[Monetizer] Loaded {len(links)} affiliate link mappings")
    return links


def insert_affiliate_links(text: str, links: list[dict]) -> tuple[str, list[dict]]:
    """
    Scan text for affiliate keywords and insert Markdown links.
    Each keyword is linked at most once per article to avoid spam.
    Returns (modified_text, list of inserted links).
    """
    inserted: list[dict] = []
    used_keywords: set[str] = set()

    # Sort by keyword length descending to match longer phrases first
    sorted_links = sorted(links, key=lambda x: len(x["keyword"]), reverse=True)

    for link in sorted_links:
        kw = link["keyword"]
        if kw in used_keywords:
            continue

        # Case-insensitive match, word boundary aware
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        if pattern.search(text):
            # Replace first occurrence only
            replacement = f"[{kw}]({link['url']})"
            text = pattern.sub(replacement, text, count=1)
            used_keywords.add(kw)
            inserted.append(link)

    return text, inserted


# ---------------------------------------------------------------------------
# Article generator (Traditional Chinese)
# ---------------------------------------------------------------------------
def generate_article(topic: dict) -> dict:
    """
    Transform a verified topic into a structured Traditional Chinese article.
    Returns dict with title_zh, body_md, meta fields.
    """
    title = topic.get("title", "無標題")
    snippet = topic.get("snippet", "")
    source = topic.get("source", "未知來源")
    url = topic.get("url", "")
    date = topic.get("date", "")
    domain = topic.get("domain", "")
    verification = topic.get("verification", {})

    domain_zh = DOMAIN_LABELS.get(domain, domain)

    # Build citation block
    citations = [f"- 原始來源：[{source}]({url})"]
    for src in verification.get("independent_sources", []):
        src_title = src.get("title", "")
        src_url = src.get("url", "")
        if src_url:
            citations.append(f"- 佐證來源：[{src_title}]({src_url})")

    citations_block = "\n".join(citations)

    # Article body in Traditional Chinese
    body = f"""## {title}

**領域**：{domain_zh}
**日期**：{date if date else '未提供'}
**資料驗證狀態**：✅ 已驗證

---

### 摘要

{snippet if snippet else '（無摘要內容）'}

### 深入分析

本篇報導來自 **{source}**，經本系統交叉比對多個獨立來源後確認其可信度。
以下為相關參考資料與佐證來源：

{citations_block}

### 相關資源

> 💡 想深入了解更多 **{domain_zh}** 的最新趨勢與工具？請參考下方推薦連結。

---

*本文由 Nexus System 自動產生，所有資料均經過驗證，符合零幻覺政策。*
*產生時間：{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}*
"""

    return {
        "title": title,
        "domain": domain,
        "domain_zh": domain_zh,
        "date": date,
        "body_md": body,
        "citations_count": len(verification.get("independent_sources", [])),
        "source_url": url,
    }


# ---------------------------------------------------------------------------
# Notion Markdown formatter
# ---------------------------------------------------------------------------
def format_for_notion(article: dict, affiliate_links: list[dict]) -> str:
    """
    Format article as Notion-importable Markdown.
    Notion supports: headings, bold, links, callouts (> blocks), dividers (---).
    """
    body, inserted = insert_affiliate_links(article["body_md"], affiliate_links)

    # Notion metadata header as a database-style frontmatter
    frontmatter = f"""---
title: "{article['title']}"
domain: "{article['domain_zh']}"
date: "{article['date']}"
status: "已發布"
tags: ["{article['domain_zh']}", "Nexus自動產出"]
---

"""
    # Disclosure for affiliate links
    disclosure = ""
    if inserted:
        partner_names = ", ".join(set(l["partner"] for l in inserted))
        disclosure = (
            f"\n\n> ⚠️ **揭露聲明**：本文包含聯盟行銷連結（合作夥伴：{partner_names}）。"
            "透過這些連結購買不會增加您的費用，但我們可能獲得少額佣金。\n"
        )

    return frontmatter + body + disclosure


# ---------------------------------------------------------------------------
# GitHub Pages HTML formatter
# ---------------------------------------------------------------------------
GHPAGES_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #0d1117;
      --fg: #c9d1d9;
      --accent: #58a6ff;
      --card-bg: #161b22;
      --border: #30363d;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--fg);
      line-height: 1.7;
      padding: 2rem;
      max-width: 820px;
      margin: 0 auto;
    }}
    h1 {{ color: var(--accent); font-size: 1.8rem; margin-bottom: 0.5rem; }}
    h2 {{ color: var(--accent); font-size: 1.4rem; margin: 1.5rem 0 0.5rem; }}
    h3 {{ font-size: 1.1rem; margin: 1.2rem 0 0.4rem; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .meta {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 1rem;
      margin: 1rem 0;
      font-size: 0.9rem;
    }}
    .meta span {{ margin-right: 1.5rem; }}
    blockquote {{
      border-left: 3px solid var(--accent);
      padding: 0.8rem 1rem;
      margin: 1rem 0;
      background: var(--card-bg);
      border-radius: 0 6px 6px 0;
    }}
    hr {{ border: none; border-top: 1px solid var(--border); margin: 1.5rem 0; }}
    .disclosure {{
      background: #1c1e26;
      border: 1px solid #e3b341;
      border-radius: 6px;
      padding: 0.8rem 1rem;
      margin-top: 1.5rem;
      font-size: 0.85rem;
      color: #e3b341;
    }}
    footer {{
      margin-top: 2rem;
      font-size: 0.8rem;
      color: #484f58;
      text-align: center;
    }}
    ul {{ padding-left: 1.5rem; margin: 0.5rem 0; }}
    li {{ margin: 0.3rem 0; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <div class="meta">
    <span>📂 {domain_zh}</span>
    <span>📅 {date}</span>
    <span>✅ 已驗證</span>
  </div>
  {body_html}
  {disclosure_html}
  <footer>
    Nexus System &copy; 2026 — 自動產出，所有資料均經過驗證<br>
    <a href="index.html">&larr; 返回首頁</a>
  </footer>
</body>
</html>
"""


def md_to_html(md: str) -> str:
    """Lightweight Markdown→HTML conversion for key elements."""
    lines = md.split("\n")
    html_lines: list[str] = []
    in_blockquote = False
    in_list = False

    for line in lines:
        stripped = line.strip()

        # Close list if we leave it
        if in_list and not stripped.startswith("- "):
            html_lines.append("</ul>")
            in_list = False

        # Close blockquote
        if in_blockquote and not stripped.startswith(">"):
            html_lines.append("</blockquote>")
            in_blockquote = False

        # Headings
        if stripped.startswith("### "):
            html_lines.append(f"<h3>{_inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            html_lines.append(f"<h2>{_inline(stripped[3:])}</h2>")
        # Horizontal rule
        elif stripped == "---":
            html_lines.append("<hr>")
        # Blockquote
        elif stripped.startswith(">"):
            if not in_blockquote:
                html_lines.append("<blockquote>")
                in_blockquote = True
            html_lines.append(f"<p>{_inline(stripped[1:].strip())}</p>")
        # List
        elif stripped.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{_inline(stripped[2:])}</li>")
        # Empty line
        elif not stripped:
            html_lines.append("")
        # Paragraph
        else:
            html_lines.append(f"<p>{_inline(stripped)}</p>")

    if in_list:
        html_lines.append("</ul>")
    if in_blockquote:
        html_lines.append("</blockquote>")

    return "\n".join(html_lines)


def _inline(text: str) -> str:
    """Convert inline Markdown (bold, links) to HTML."""
    # Bold **text**
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Links [text](url)
    text = re.sub(
        r"\[(.+?)\]\((.+?)\)",
        lambda m: f'<a href="{html_lib.escape(m.group(2))}" target="_blank" rel="noopener">{html_lib.escape(m.group(1))}</a>',
        text,
    )
    return text


def format_for_ghpages(
    article: dict, affiliate_links: list[dict]
) -> str:
    """Format article as a standalone GitHub Pages HTML file."""
    body_with_links, inserted = insert_affiliate_links(article["body_md"], affiliate_links)
    body_html = md_to_html(body_with_links)

    disclosure_html = ""
    if inserted:
        partner_names = ", ".join(set(l["partner"] for l in inserted))
        disclosure_html = (
            f'<div class="disclosure">⚠️ 揭露聲明：本文包含聯盟行銷連結'
            f"（合作夥伴：{html_lib.escape(partner_names)}）。"
            f"透過這些連結購買不會增加您的費用，但我們可能獲得少額佣金。</div>"
        )

    return GHPAGES_TEMPLATE.format(
        title=html_lib.escape(article["title"]),
        domain_zh=html_lib.escape(article["domain_zh"]),
        date=html_lib.escape(article.get("date", "N/A")),
        body_html=body_html,
        disclosure_html=disclosure_html,
    )


def generate_index_html(articles: list[dict]) -> str:
    """Generate a GitHub Pages index page listing all articles."""
    rows = ""
    for a in articles:
        slug = a["slug"]
        rows += (
            f'<li><a href="{slug}.html">{html_lib.escape(a["title"])}</a>'
            f' — <span class="tag">{html_lib.escape(a["domain_zh"])}</span></li>\n'
        )

    return f"""\
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Nexus System — 每日趨勢報告</title>
  <style>
    :root {{ --bg: #0d1117; --fg: #c9d1d9; --accent: #58a6ff; --border: #30363d; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           background: var(--bg); color: var(--fg); padding: 2rem; max-width: 820px; margin: 0 auto; }}
    h1 {{ color: var(--accent); }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    ul {{ padding-left: 1.2rem; }}
    li {{ margin: 0.6rem 0; line-height: 1.5; }}
    .tag {{ font-size: 0.8rem; background: #21262d; padding: 2px 8px; border-radius: 12px; }}
    footer {{ margin-top: 2rem; font-size: 0.8rem; color: #484f58; text-align: center; }}
  </style>
</head>
<body>
  <h1>📡 Nexus System — 每日趨勢報告</h1>
  <p>以下為經過驗證的最新趨勢文章：</p>
  <ul>
    {rows}
  </ul>
  <footer>Nexus System &copy; 2026 — 自動產出，資料皆經交叉驗證</footer>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Slug helper
# ---------------------------------------------------------------------------
def slugify(text: str, max_len: int = 60) -> str:
    """Create a URL-safe slug from a title."""
    # Keep alphanumeric, CJK, hyphens
    slug = re.sub(r"[^\w\s-]", "", text)
    slug = re.sub(r"[\s_]+", "-", slug).strip("-").lower()
    return slug[:max_len] if slug else "article"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run() -> str:
    """Execute the Monetizer pipeline. Returns manifest path."""
    print(f"[Monetizer] Starting at {datetime.now(timezone.utc).isoformat()}")

    # Load verified data
    if not VERIFIED_INPUT.exists():
        print(f"[Monetizer] ERROR: {VERIFIED_INPUT} not found. Run critic.py first.")
        raise SystemExit(1)

    with open(VERIFIED_INPUT, "r", encoding="utf-8") as f:
        data = json.load(f)

    topics = data.get("verified_topics", [])
    if not topics:
        print("[Monetizer] No verified topics to process.")
        raise SystemExit(0)

    print(f"[Monetizer] Processing {len(topics)} verified topics")

    # Load affiliate links
    affiliate_links = load_affiliate_links(LINKS_CSV)

    # Prepare output dirs
    NOTION_DIR.mkdir(parents=True, exist_ok=True)
    GHPAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Generate articles
    manifest_entries: list[dict] = []

    for i, topic in enumerate(topics, 1):
        article = generate_article(topic)
        slug = slugify(article["title"])
        # Ensure unique slug
        if any(e["slug"] == slug for e in manifest_entries):
            slug = f"{slug}-{i}"
        article["slug"] = slug

        # --- Notion output ---
        notion_md = format_for_notion(article, affiliate_links)
        notion_path = NOTION_DIR / f"{slug}.md"
        with open(notion_path, "w", encoding="utf-8") as f:
            f.write(notion_md)

        # --- GitHub Pages output ---
        ghpages_html = format_for_ghpages(article, affiliate_links)
        ghpages_path = GHPAGES_DIR / f"{slug}.html"
        with open(ghpages_path, "w", encoding="utf-8") as f:
            f.write(ghpages_html)

        manifest_entries.append(
            {
                "slug": slug,
                "title": article["title"],
                "domain": article["domain"],
                "domain_zh": article["domain_zh"],
                "date": article["date"],
                "notion_file": str(notion_path.relative_to(PROJECT_ROOT)),
                "ghpages_file": str(ghpages_path.relative_to(PROJECT_ROOT)),
                "citations_count": article["citations_count"],
            }
        )

        print(f"[Monetizer] [{i}/{len(topics)}] Generated: {slug}")

    # --- GitHub Pages index ---
    index_html = generate_index_html(manifest_entries)
    with open(GHPAGES_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(index_html)

    # --- Manifest ---
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(VERIFIED_INPUT),
        "total_articles": len(manifest_entries),
        "affiliate_links_loaded": len(affiliate_links),
        "outputs": {
            "notion_dir": str(NOTION_DIR.relative_to(PROJECT_ROOT)),
            "ghpages_dir": str(GHPAGES_DIR.relative_to(PROJECT_ROOT)),
        },
        "articles": manifest_entries,
    }

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"[Monetizer] Done. {len(manifest_entries)} articles generated.")
    print(f"[Monetizer] Notion:  {NOTION_DIR}")
    print(f"[Monetizer] GHPages: {GHPAGES_DIR}")
    print(f"[Monetizer] Manifest: {MANIFEST_PATH}")
    return str(MANIFEST_PATH)


if __name__ == "__main__":
    run()
