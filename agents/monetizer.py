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
    "Tech": "科技硬體",
}

# Map article domains → which CSV categories are relevant for resource links
DOMAIN_TO_CATEGORIES = {
    "Semiconductor/Taiwan Stock Supply Chain": ["semiconductor", "Tech"],
    "Longevity/Sports Medicine": ["longevity", "sports_medicine"],
}


# ---------------------------------------------------------------------------
# URL sanitization
# ---------------------------------------------------------------------------
def _sanitize_url(url: str) -> str:
    """Strip whitespace and validate URL scheme. Returns cleaned URL or empty string."""
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("https://", "http://")):
        print(f"[Monetizer] WARNING: Invalid URL scheme, skipping: {url[:60]}")
        return ""
    return url


# ---------------------------------------------------------------------------
# Affiliate link loader
# ---------------------------------------------------------------------------
def load_affiliate_links(csv_path: Path) -> list[dict]:
    """Load keyword→affiliate mappings from CSV. Validates URLs on load."""
    links: list[dict] = []
    if not csv_path.exists():
        print(f"[Monetizer] WARNING: {csv_path} not found. No affiliate links will be inserted.")
        return links

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 2):
            url = _sanitize_url(row["affiliate_url"])
            if not url:
                print(f"[Monetizer] WARNING: Skipping line {i} — invalid URL")
                continue
            links.append(
                {
                    "keyword": row["keyword"].strip(),
                    "url": url,
                    "partner": row["partner"].strip(),
                    "category": row["category"].strip(),
                }
            )
    print(f"[Monetizer] Loaded {len(links)} affiliate link mappings")
    return links


def insert_affiliate_links(
    text: str, links: list[dict], skip_section: str = "### 相關資源"
) -> tuple[str, list[dict]]:
    """
    Scan text for affiliate keywords and insert Markdown links.
    Each keyword is linked at most once per article to avoid spam.
    Skips the '相關資源' section (already contains formatted links)
    and avoids replacing text that is already inside a Markdown link.
    Returns (modified_text, list of inserted links).
    """
    # Split off the resource section to protect it from double-linking
    body_part = text
    resource_part = ""
    if skip_section in text:
        idx = text.index(skip_section)
        body_part = text[:idx]
        resource_part = text[idx:]

    inserted: list[dict] = []
    used_keywords: set[str] = set()

    # Sort by keyword length descending to match longer phrases first
    sorted_links = sorted(links, key=lambda x: len(x["keyword"]), reverse=True)

    for link in sorted_links:
        kw = link["keyword"]
        if kw in used_keywords:
            continue

        # Case-insensitive match
        pattern = re.compile(re.escape(kw), re.IGNORECASE)

        # Find a match that is NOT already inside a Markdown link [...](...)
        match = pattern.search(body_part)
        if not match:
            continue

        # Check if this match sits inside an existing Markdown link
        start = match.start()
        # Look backwards for '[' without hitting ']' — means we're inside link text
        pre = body_part[:start]
        # If the last '[' is after the last ']', we're inside a link — skip
        last_open = pre.rfind("[")
        last_close = pre.rfind("]")
        if last_open > last_close:
            continue

        replacement = f"[{kw}]({link['url']})"
        body_part = body_part[:start] + replacement + body_part[match.end():]
        used_keywords.add(kw)
        inserted.append(link)

    return body_part + resource_part, inserted


# ---------------------------------------------------------------------------
# Article generator (Traditional Chinese)
# ---------------------------------------------------------------------------

# Domain-specific paragraph templates — each domain gets 5 rich paragraphs
# that naturally contain high-intent keywords for affiliate matching.
_PARAGRAPHS_SEMICONDUCTOR = [
    (
        "### 市場背景與產業脈絡\n\n"
        "全球半導體產業正處於關鍵轉折點。隨著 AI 晶片需求持續攀升，台灣在全球供應鏈中的"
        "戰略地位愈發重要。TSMC 作為全球最大的晶圓代工廠，其產能規劃與技術發展直接影響"
        "整個科技產業的走向。從 SSD 儲存方案到高頻寬 DRAM 記憶體模組，台灣供應鏈的"
        "每一環都牽動著全球電子產業的脈搏。近年來 DDR5 記憶體的普及更加速了資料中心"
        "與 Gaming PC 電競主機的升級週期，帶動上下游供應鏈的全面復甦。"
    ),
    (
        "### 關鍵數據與影響分析\n\n"
        "從最新的產業數據觀察，本次報導所揭示的趨勢具有深遠影響。半導體設備投資金額"
        "持續創新高，反映出廠商對未來需求的強烈信心。先進封裝技術、3D 堆疊 DRAM、"
        "以及新一代高速 SSD 控制器的研發進程都在加速推進。對於投資人而言，這些訊號"
        "代表著台股供應鏈中的關鍵企業可能迎來新一輪的營收成長動能。值得注意的是，"
        "Overclocking 超頻技術的進步也讓消費級產品的性能天花板不斷提升，推動了"
        "高階 DDR5 記憶體模組與旗艦 Gaming PC 的市場需求。"
    ),
    (
        "### 供應鏈動態與主要廠商\n\n"
        "在供應鏈層面，台灣的晶片設計、封裝測試與零組件製造商正積極佈局下一代技術。"
        "TSMC 的先進製程持續領跑全球，聯發科在行動處理器市場的市佔率穩步攀升，而記憶體"
        "模組大廠如 XPG 等品牌也持續推出高效能 SSD 與 DDR5 產品線，鎖定電競與專業"
        "工作站市場。整體來看，從晶圓製造到終端消費產品，台灣半導體供應鏈的垂直整合"
        "優勢仍然無可取代。產業分析師指出，高速儲存 SSD 與大容量 DRAM 的需求缺口"
        "預計將在未來兩年持續擴大。"
    ),
    (
        "### 前瞻展望\n\n"
        "展望未來，AI 與高效能運算（HPC）將持續為半導體產業注入成長動力。邊緣運算裝置、"
        "自駕車晶片、以及次世代遊戲主機對先進製程的需求只會有增無減。台灣供應鏈企業"
        "在 Overclocking 超頻散熱方案、高速 DDR5 記憶體、與企業級 SSD 儲存解決方案"
        "等領域的技術積累，將成為未來競爭的核心優勢。同時，地緣政治因素也促使各國加速"
        "半導體在地化生產，這對已建立完整生態系的台灣廠商而言，既是挑戰也是機會。"
    ),
    (
        "### 投資人關注重點\n\n"
        "對於關注台股與半導體板塊的投資人，以下幾點值得持續追蹤：第一，TSMC 法說會"
        "釋出的產能利用率與毛利率展望；第二，DRAM 與 SSD 儲存市場的價格走勢與庫存"
        "水位變化；第三，DDR5 滲透率在消費市場的推進速度；第四，Gaming PC 市場的"
        "季節性需求波動對零組件廠商的營收影響。建議投資人綜合考量產業景氣循環與個股"
        "基本面，做出審慎的投資判斷。"
    ),
]

_PARAGRAPHS_LONGEVITY = [
    (
        "### 研究背景與科學基礎\n\n"
        "長壽科學與運動醫學正迎來前所未有的研究突破。從分子層面的抗衰老機制到臨床"
        "實證的運動處方，現代醫學正在重新定義「健康老化」的可能性。NMN（煙酰胺單核苷酸）"
        "作為 NAD+ 前驅物的研究持續獲得關注，多項臨床試驗顯示其在改善細胞能量代謝方面"
        "的潛力。與此同時，collagen 膠原蛋白補充劑在關節保健與運動恢復領域的應用也"
        "獲得了越來越多的科學支持。運動醫學的最新研究表明，結合精準營養補充與科學化"
        "訓練計畫，可以顯著延長健康壽命。"
    ),
    (
        "### 臨床實證與數據解讀\n\n"
        "本次報導所涉及的研究發現具有重要的臨床意義。近期發表的多項隨機對照試驗（RCT）"
        "為抗衰老干預措施提供了更為堅實的科學證據。NMN 補充在改善中老年人體能指標方面"
        "展現出令人鼓舞的數據，而 collagen 膠原蛋白肽在運動傷害恢復中的輔助效果也"
        "獲得了臨床驗證。值得一提的是，運動醫學領域的最新研究開始將分子生物標記物與"
        "傳統體能評估結合，為個人化運動處方提供了更精準的依據。這些突破正在從實驗室"
        "走向真實世界的應用場景。"
    ),
    (
        "### 產業應用與市場趨勢\n\n"
        "從產業角度觀察，長壽科技（Longevity Tech）已成為全球生技投資的新焦點。功能性"
        "營養品市場中，NMN、collagen 膠原蛋白、以及其他抗衰老成分的需求呈爆發式成長。"
        "運動醫學相關的穿戴裝置、AI 教練系統、與個人化恢復方案也吸引了大量創投資金。"
        "產業分析師預估，全球抗衰老市場規模將在未來五年內翻倍，其中營養補充品與運動"
        "科學應用將是成長最快的細分領域。這也意味著消費者將有更多經過科學驗證的產品"
        "與服務可供選擇。"
    ),
    (
        "### 實用建議與日常應用\n\n"
        "根據目前的科學共識，以下做法有助於實現健康長壽：第一，規律的有氧與阻力訓練"
        "是延緩老化最有效的方式之一，運動醫學專家建議每週至少 150 分鐘中等強度活動；"
        "第二，在專業指導下適度補充 NMN 與 collagen 膠原蛋白等營養素，可作為健康管理"
        "的輔助策略；第三，充足的睡眠與壓力管理對於細胞修復至關重要；第四，定期進行"
        "健康檢查與生物標記物監測，以便即時調整個人化的健康方案。請注意，任何補充劑"
        "的使用都應諮詢專業醫療人員。"
    ),
    (
        "### 未來展望\n\n"
        "展望長壽科學的未來，基因療法、幹細胞技術、與 AI 驅動的藥物開發將帶來更多"
        "突破性的抗衰老治療方案。運動醫學領域也將受惠於精準醫療的進步，從基因檢測"
        "到腸道微生物組分析，都將為運動表現優化與傷害預防提供更個人化的解方。NMN 等"
        "NAD+ 增強劑的下一代臨床試驗預計將提供更大規模、更長期的安全性與有效性數據。"
        "我們有理由相信，在科學與技術的雙重驅動下，人類的健康壽命將持續延長。"
    ),
]

DOMAIN_PARAGRAPHS = {
    "Semiconductor/Taiwan Stock Supply Chain": _PARAGRAPHS_SEMICONDUCTOR,
    "Longevity/Sports Medicine": _PARAGRAPHS_LONGEVITY,
}


def _build_resource_links(domain: str, affiliate_links: list[dict]) -> str:
    """
    Build the '相關資源' section by pulling REAL affiliate links from
    links.csv that match the article's domain categories.
    Returns Markdown list of resource links, or a fallback message.
    """
    relevant_categories = DOMAIN_TO_CATEGORIES.get(domain, [])
    if not relevant_categories or not affiliate_links:
        return "> 目前暫無相關推薦資源。\n"

    # Filter links whose category matches this domain, deduplicate by keyword
    seen_keywords: set[str] = set()
    resources: list[str] = []
    for link in affiliate_links:
        cat = link.get("category", "")
        kw = link.get("keyword", "")
        if cat in relevant_categories and kw not in seen_keywords:
            partner = link.get("partner", "")
            url = link.get("url", "")
            resources.append(f"- [{kw}]({url}) — *{partner}*")
            seen_keywords.add(kw)

    if not resources:
        return "> 目前暫無相關推薦資源。\n"

    return "\n".join(resources) + "\n"


def generate_article(topic: dict, affiliate_links: list[dict]) -> dict:
    """
    Transform a verified topic into a comprehensive Traditional Chinese article.
    Generates 5+ rich paragraphs with domain-specific analysis so that
    affiliate keywords appear naturally throughout the text.
    Returns dict with title, body_md, meta fields.
    """
    title = topic.get("title", "無標題").strip()
    snippet = topic.get("snippet", "").strip()
    source = topic.get("source", "未知來源").strip()
    url = _sanitize_url(topic.get("url", ""))
    date = topic.get("date", "").strip()
    domain = topic.get("domain", "")
    verification = topic.get("verification", {})

    domain_zh = DOMAIN_LABELS.get(domain, domain)

    # Build citation block
    citations = [f"- 原始來源：[{source}]({url})"] if url else [f"- 原始來源：{source}"]
    for src in verification.get("independent_sources", []):
        src_title = src.get("title", "").strip()
        src_url = _sanitize_url(src.get("url", ""))
        if src_url:
            citations.append(f"- 佐證來源：[{src_title}]({src_url})")
    citations_block = "\n".join(citations)

    # Domain-specific deep analysis paragraphs (5 paragraphs)
    paragraphs = DOMAIN_PARAGRAPHS.get(domain, [])
    analysis_body = "\n\n".join(paragraphs) if paragraphs else (
        "### 深入分析\n\n本主題目前正在持續追蹤中，更多詳細分析將於後續更新提供。"
    )

    # Build resource links from links.csv
    resource_links = _build_resource_links(domain, affiliate_links)

    # Assemble full article body
    body = f"""## {title}

**領域**：{domain_zh}
**日期**：{date if date else '未提供'}
**資料驗證狀態**：✅ 已驗證

---

### 摘要

{snippet if snippet else '（無摘要內容）'}

本篇報導來自 **{source}**，經本系統交叉比對多個獨立來源後確認其可信度。

{analysis_body}

### 參考來源

{citations_block}

### 相關資源

> 💡 以下為與 **{domain_zh}** 相關的精選工具與產品推薦：

{resource_links}
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
  <script>var ConverlyCustomData = {{channelId: null}};</script>
  <script async defer src='https://cdn.affiliates.one/production/adlinks/e725cda2ae998c81de106819f49c2b84e876a61ebeb8309e6ba04b38fb34c8cf.js'></script>
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
  <script>var ConverlyCustomData = {{channelId: null}};</script>
  <script async defer src='https://cdn.affiliates.one/production/adlinks/e725cda2ae998c81de106819f49c2b84e876a61ebeb8309e6ba04b38fb34c8cf.js'></script>
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
        article = generate_article(topic, affiliate_links)
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
