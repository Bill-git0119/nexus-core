"""
The Architect Agent
Analyzes output/manifest.json and logs/performance.log to determine
which domain performs better, then updates config/strategy.json to
guide the Scout's next run. Produces a weekly_pivot.md summary.

Inputs:
  output/manifest.json       — Monetizer build manifest
  logs/performance.log       — Engagement scores (views, clicks, shares)
  config/strategy.json       — Previous strategy (if exists)

Outputs:
  config/strategy.json       — Updated keyword priorities for Scout
  weekly_pivot.md            — Human-readable self-adjustment report
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths (relative to project root)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "output" / "manifest.json"
PERFORMANCE_LOG = PROJECT_ROOT / "logs" / "performance.log"
STRATEGY_PATH = PROJECT_ROOT / "config" / "strategy.json"
PIVOT_REPORT = PROJECT_ROOT / "weekly_pivot.md"

# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------
DOMAIN_KEYS = {
    "Semiconductor/Taiwan Stock Supply Chain": "semiconductor",
    "Longevity/Sports Medicine": "longevity",
}

DOMAIN_ZH = {
    "semiconductor": "半導體／台股供應鏈",
    "longevity": "長壽科學／運動醫學",
}

DEFAULT_KEYWORDS = {
    "semiconductor": [
        "Taiwan semiconductor supply chain news today",
        "TSMC stock market latest",
        "global chip shortage update 2026",
    ],
    "longevity": [
        "longevity science breakthrough 2026",
        "sports medicine latest research",
        "anti-aging clinical trial results",
    ],
}

# Bonus keywords the Architect can inject when a domain is winning
BOOST_KEYWORDS = {
    "semiconductor": [
        "TSMC earnings forecast 2026",
        "AI chip demand supply chain",
        "Taiwan tech stock analysis",
    ],
    "longevity": [
        "NMN NAD+ clinical results 2026",
        "peptide therapy sports recovery",
        "rapamycin longevity human trial",
    ],
}


# ---------------------------------------------------------------------------
# Performance log parser
# ---------------------------------------------------------------------------
def parse_performance_log(log_path: Path) -> list[dict]:
    """
    Parse logs/performance.log into structured records.

    Expected format (one JSON object per line):
    {"date":"2026-04-09","slug":"some-article","domain":"semiconductor",
     "views":1200,"clicks":85,"shares":32}

    Falls back to synthetic scores from manifest if log is missing.
    """
    records: list[dict] = []

    if not log_path.exists():
        print("[Architect] performance.log not found — will use manifest-based estimation")
        return records

    with open(log_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError:
                print(f"[Architect] WARNING: Skipping malformed line {i} in performance.log")

    print(f"[Architect] Loaded {len(records)} performance records")
    return records


# ---------------------------------------------------------------------------
# Engagement scoring
# ---------------------------------------------------------------------------
def compute_engagement(record: dict) -> float:
    """
    Weighted engagement score.
    Formula: views * 1.0 + clicks * 3.0 + shares * 5.0
    """
    views = float(record.get("views", 0))
    clicks = float(record.get("clicks", 0))
    shares = float(record.get("shares", 0))
    return views * 1.0 + clicks * 3.0 + shares * 5.0


def aggregate_by_domain(
    manifest: dict, performance: list[dict]
) -> dict[str, dict[str, Any]]:
    """
    Aggregate engagement scores per domain.
    Returns {domain_key: {total_score, article_count, avg_score, articles:[...]}}.
    """
    # Map slugs → domain keys from manifest
    slug_domain: dict[str, str] = {}
    for article in manifest.get("articles", []):
        raw_domain = article.get("domain", "")
        key = DOMAIN_KEYS.get(raw_domain, raw_domain.lower().replace(" ", "_"))
        slug_domain[article["slug"]] = key

    stats: dict[str, dict[str, Any]] = {}
    for key in DOMAIN_KEYS.values():
        stats[key] = {
            "total_score": 0.0,
            "article_count": 0,
            "avg_score": 0.0,
            "articles": [],
        }

    if performance:
        # Use real performance data
        for record in performance:
            domain = record.get("domain", "")
            if domain not in stats:
                # Try to resolve from slug
                domain = slug_domain.get(record.get("slug", ""), domain)
            if domain not in stats:
                continue

            score = compute_engagement(record)
            stats[domain]["total_score"] += score
            stats[domain]["article_count"] += 1
            stats[domain]["articles"].append(
                {"slug": record.get("slug", ""), "score": score}
            )
    else:
        # Estimate from manifest (citation count as proxy)
        for article in manifest.get("articles", []):
            raw_domain = article.get("domain", "")
            key = DOMAIN_KEYS.get(raw_domain, "")
            if key not in stats:
                continue
            # Proxy score: citations * 100 + 50 base
            proxy = article.get("citations_count", 0) * 100 + 50
            stats[key]["total_score"] += proxy
            stats[key]["article_count"] += 1
            stats[key]["articles"].append(
                {"slug": article["slug"], "score": proxy}
            )

    # Compute averages
    for key in stats:
        count = stats[key]["article_count"]
        stats[key]["avg_score"] = (
            stats[key]["total_score"] / count if count > 0 else 0.0
        )

    return stats


# ---------------------------------------------------------------------------
# Strategy optimizer
# ---------------------------------------------------------------------------
def load_previous_strategy(path: Path) -> dict:
    """Load the previous strategy.json or return defaults."""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def optimize_strategy(
    stats: dict[str, dict[str, Any]], prev_strategy: dict
) -> dict:
    """
    Decide keyword priorities for the next Scout run.

    Rules:
    - The winning domain gets 2 extra boost keywords (60/40 split).
    - The losing domain keeps its defaults (no penalty, maintains coverage).
    - If scores are within 10% → balanced, no changes.
    """
    now = datetime.now(timezone.utc).isoformat()
    run_count = prev_strategy.get("meta", {}).get("run_count", 0) + 1

    # Determine winner
    semi_avg = stats.get("semiconductor", {}).get("avg_score", 0)
    long_avg = stats.get("longevity", {}).get("avg_score", 0)

    if semi_avg == 0 and long_avg == 0:
        verdict = "no_data"
        winner = None
    elif abs(semi_avg - long_avg) / max(semi_avg, long_avg, 1) < 0.10:
        verdict = "balanced"
        winner = None
    elif semi_avg > long_avg:
        verdict = "semiconductor_leads"
        winner = "semiconductor"
    else:
        verdict = "longevity_leads"
        winner = "longevity"

    # Build keyword config
    keywords: dict[str, dict] = {}
    for domain_key in ["semiconductor", "longevity"]:
        base = list(DEFAULT_KEYWORDS[domain_key])
        priority = "normal"
        boost: list[str] = []

        if winner == domain_key:
            boost = BOOST_KEYWORDS[domain_key][:2]
            priority = "high"

        keywords[domain_key] = {
            "priority": priority,
            "base_queries": base,
            "boost_queries": boost,
            "total_queries": len(base) + len(boost),
        }

    strategy = {
        "meta": {
            "updated_at": now,
            "run_count": run_count,
            "verdict": verdict,
            "winner": winner,
            "data_source": (
                "performance.log" if any(s["article_count"] > 0 and PERFORMANCE_LOG.exists()
                                         for s in stats.values())
                else "manifest_estimation"
            ),
        },
        "engagement_summary": {
            domain_key: {
                "avg_score": round(stats[domain_key]["avg_score"], 1),
                "total_score": round(stats[domain_key]["total_score"], 1),
                "article_count": stats[domain_key]["article_count"],
            }
            for domain_key in ["semiconductor", "longevity"]
        },
        "keywords": keywords,
    }

    return strategy


# ---------------------------------------------------------------------------
# Weekly pivot report generator
# ---------------------------------------------------------------------------
def generate_pivot_report(
    strategy: dict, stats: dict[str, dict[str, Any]]
) -> str:
    """Generate weekly_pivot.md — a Traditional Chinese self-adjustment report."""
    meta = strategy["meta"]
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    run_count = meta["run_count"]
    verdict = meta["verdict"]
    winner = meta["winner"]

    # Verdict in Chinese
    verdict_zh_map = {
        "semiconductor_leads": "半導體／台股供應鏈 表現領先",
        "longevity_leads": "長壽科學／運動醫學 表現領先",
        "balanced": "兩大領域表現均衡（差距 <10%）",
        "no_data": "尚無足夠數據進行判斷",
    }
    verdict_zh = verdict_zh_map.get(verdict, verdict)

    # Score table
    semi = strategy["engagement_summary"]["semiconductor"]
    long = strategy["engagement_summary"]["longevity"]

    # Keyword changes
    semi_kw = strategy["keywords"]["semiconductor"]
    long_kw = strategy["keywords"]["longevity"]

    boost_section = ""
    if winner:
        winner_zh = DOMAIN_ZH[winner]
        boost_kw = strategy["keywords"][winner]["boost_queries"]
        if boost_kw:
            boost_list = "\n".join(f"  - `{kw}`" for kw in boost_kw)
            boost_section = f"""
### 關鍵字加權調整

由於 **{winner_zh}** 表現較佳，系統已為該領域增加以下搜尋關鍵字：

{boost_list}

另一領域維持基礎關鍵字不變，確保覆蓋率。
"""
    else:
        boost_section = """
### 關鍵字加權調整

兩大領域表現接近，本週不進行關鍵字調整，維持均衡策略。
"""

    # Top articles
    top_articles = ""
    for domain_key in ["semiconductor", "longevity"]:
        domain_zh = DOMAIN_ZH[domain_key]
        articles = sorted(
            stats.get(domain_key, {}).get("articles", []),
            key=lambda x: x["score"],
            reverse=True,
        )[:3]
        if articles:
            rows = "\n".join(
                f"  | `{a['slug'][:50]}` | {a['score']:.0f} |"
                for a in articles
            )
            top_articles += f"""
**{domain_zh}**

  | 文章 | 分數 |
  |------|------|
{rows}
"""

    report = f"""# Nexus System — 每週策略調整報告

**產生時間**：{now_str}
**累計執行次數**：{run_count}
**資料來源**：{meta['data_source']}

---

## 本週判定結果

> **{verdict_zh}**

## 互動數據摘要

| 領域 | 平均分數 | 總分 | 文章數 |
|------|---------|------|--------|
| 半導體／台股供應鏈 | {semi['avg_score']} | {semi['total_score']} | {semi['article_count']} |
| 長壽科學／運動醫學 | {long['avg_score']} | {long['total_score']} | {long['article_count']} |

**計分公式**：`views * 1.0 + clicks * 3.0 + shares * 5.0`
{boost_section}
## 表現最佳文章
{top_articles}
---

## 系統自我調整邏輯

1. **數據收集**：讀取 `output/manifest.json`（文章元資料）與 `logs/performance.log`（互動數據）。
2. **分數計算**：依加權公式計算每篇文章的互動分數，再按領域聚合平均。
3. **勝出判定**：若兩領域平均分數差距 >10%，判定表現較佳者為「領先」。
4. **關鍵字調整**：為領先領域注入 2 組額外搜尋關鍵字，增加下次 Scout 掃描的深度。
5. **輸出策略**：更新 `config/strategy.json`，供 Scout 下次執行時讀取。

> 本報告由 Nexus System Architect Agent 自動產生，不含任何人工編輯。

---

*Nexus System &copy; 2026 — 零幻覺政策，所有判斷皆基於可驗證數據。*
"""
    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run() -> str:
    """Execute the Architect pipeline. Returns pivot report path."""
    print(f"[Architect] Starting analysis at {datetime.now(timezone.utc).isoformat()}")

    # Load manifest
    if not MANIFEST_PATH.exists():
        print(f"[Architect] ERROR: {MANIFEST_PATH} not found. Run monetizer.py first.")
        raise SystemExit(1)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"[Architect] Loaded manifest: {manifest.get('total_articles', 0)} articles")

    # Load performance log
    performance = parse_performance_log(PERFORMANCE_LOG)

    # Aggregate engagement by domain
    stats = aggregate_by_domain(manifest, performance)

    for key in ["semiconductor", "longevity"]:
        s = stats[key]
        print(
            f"[Architect] {DOMAIN_ZH[key]}: "
            f"avg={s['avg_score']:.1f}, total={s['total_score']:.1f}, "
            f"articles={s['article_count']}"
        )

    # Load previous strategy & optimize
    prev_strategy = load_previous_strategy(STRATEGY_PATH)
    strategy = optimize_strategy(stats, prev_strategy)

    print(f"[Architect] Verdict: {strategy['meta']['verdict']}")
    if strategy["meta"]["winner"]:
        print(f"[Architect] Winner: {DOMAIN_ZH[strategy['meta']['winner']]}")

    # Write strategy.json
    STRATEGY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STRATEGY_PATH, "w", encoding="utf-8") as f:
        json.dump(strategy, f, indent=2, ensure_ascii=False)
    print(f"[Architect] Strategy saved to {STRATEGY_PATH}")

    # Generate weekly pivot report
    report = generate_pivot_report(strategy, stats)
    with open(PIVOT_REPORT, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[Architect] Weekly pivot report saved to {PIVOT_REPORT}")

    return str(PIVOT_REPORT)


if __name__ == "__main__":
    run()
