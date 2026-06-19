"""
非洲离网太阳能市场资讯 - 爬虫
=====================================
每周自动抓取 GOGLA、Techpoint Africa、ENGIE 等数据源的
最新行业新闻，输出结构化 JSON 供人工筛选后填入周报模板。

用法:
    python fetch_news.py                     # 抓取全部来源
    python fetch_news.py --source gogla      # 只抓 GOGLA
    python fetch_news.py --days 14           # 只看最近14天的
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

CST = timezone(timedelta(hours=8))

# 数据源定义：每个源一个爬取函数
SOURCES = {
    # ── 行业报告 / 协会 ──
    "gogla": {
        "name": "GOGLA Newsroom",
        "url": "https://newsroom.gogla.org/",
        "type": "html",
        "selector": ".c-card__text-holder",
        "title_sel": "h2.h5.c-card__title",
        "link_sel": "a",
        "date_sel": "time.c-card__time",
        "summary_sel": "p",
    },
    # ── 媒体 / 新闻 ──
    "techpoint": {
        "name": "Techpoint Africa",
        "url": "https://techpoint.africa/tag/climate-tech/",
        "type": "html",
        "selector": ".gb-query-loop-item",
        "title_sel": "h2, h3, .wp-block-post-title",
        "link_sel": "a",
        "date_sel": "time",
        "summary_sel": "p",
    },
    # ── 企业动态 ──
    "engie": {
        "name": "ENGIE / IgniteAccess",
        "url": "https://igniteaccess.com/category/in-the-news/",
        "type": "html",
        "selector": "article, .post, .news-item",
        "title_sel": "h2, h3, .news-title, .entry-title",
        "link_sel": "a",
        "date_sel": "time, .date, .entry-date",
        "summary_sel": "p, .excerpt, .entry-summary",
    },
    # ── RSS 来源 ──
    "pv-magazine": {
        "name": "PV Magazine",
        "url": "https://www.pv-magazine.com/feed/",
        "type": "rss",
        "item_sel": "item",
        "title_sel": "title",
        "link_sel": "link",
        "date_sel": "pubDate",
        "summary_sel": "description",
        # 过滤：标题中含这些关键词才保留
        "keywords": ["africa", "african", "nigeria", "kenya", "ghana", "senegal",
                     "uganda", "tanzania", "rwanda", "ethiopia", "zambia", "mozambique",
                     "sahel", "sahara", "congo", "ivory", "sudan", "angola",
                     "off-grid", "mini-grid", "minigrid", "solar home", "paygo",
                     "gogla", "electrification"],
    },
    # ── 更多 RSS ──
    "afsia": {
        "name": "AFSIA Solar Africa",
        "url": "https://www.afsiasolar.com/feed/",
        "type": "rss",
        "item_sel": "item",
        "title_sel": "title",
        "link_sel": "link",
        "date_sel": "pubDate",
        "summary_sel": "description",
    },
    "lighting-global": {
        "name": "Lighting Global",
        "url": "https://www.lightingglobal.org/feed/",
        "type": "rss",
        "item_sel": "item",
        "title_sel": "title",
        "link_sel": "link",
        "date_sel": "pubDate",
        "summary_sel": "description",
    },
    # ── 企业动态（HTML）──
    "sunking": {
        "name": "Sun King",
        "url": "https://sunking.com/news-and-blog/",
        "type": "html",
        "selector": "article, .post, .blog-entry, div[class*=post]",
        "title_sel": "h2, h3",
        "link_sel": "a",
        "date_sel": "time, .date",
        "summary_sel": "p, .excerpt",
    },
    "m-kopa": {
        "name": "M-KOPA",
        "url": "https://www.m-kopa.com/newsroom",
        "type": "html",
        "selector": "a.w-dyn-item, a.collection-item, .news-item, a[href*='/newsroom/']",
        "title_sel": "h2, h3, .title, .heading",
        "link_sel": "a",
        "date_sel": "time, .date, .published",
        "summary_sel": "p, .summary, .excerpt",
    },
    "dlight": {
        "name": "d.light",
        "url": "https://www.dlight.com/news",
        "type": "html",
        "selector": "article, .post, .news-item, .press-item, div[class*=post]",
        "title_sel": "h2, h3, .entry-title, .card-title",
        "link_sel": "a",
        "date_sel": "time, .date, .entry-date, .published",
        "summary_sel": "p, .excerpt, .entry-summary",
    },
    # ── 新增数据源 ──
    "bgfa": {
        "name": "BGFA (Beyond the Grid)",
        "url": "https://beyondthegrid.africa/feed/",
        "type": "rss",
        "item_sel": "item",
        "title_sel": "title",
        "link_sel": "link",
        "date_sel": "pubDate",
        "summary_sel": "description",
    },
    "energynews-africa": {
        "name": "Energy News Africa",
        "url": "https://energynews.africa/feed/",
        "type": "rss",
        "item_sel": "item",
        "title_sel": "title",
        "link_sel": "link",
        "date_sel": "pubDate",
        "summary_sel": "description",
        "keywords": ["solar", "off-grid", "mini-grid", "minigrid", "renewable",
                     "clean energy", "electrification", "paygo"],
    },
    "africa-newsroom": {
        "name": "Africa Newsroom",
        "url": "https://www.africa-newsroom.com/press/tag/energy",
        "type": "html",
        "selector": "article, .press-item, .news-item, .post",
        "title_sel": "h2, h3, .entry-title, .press-title",
        "link_sel": "a",
        "date_sel": "time, .date, .entry-date",
        "summary_sel": "p, .excerpt, .entry-summary",
        "keywords": ["solar", "off-grid", "offgrid", "energy access", "electrification",
                     "renewable", "mini-grid", "minigrid", "clean energy", "paygo",
                     "solar home", "mission 300", "power africa"],
    },
    "bboxx": {
        "name": "BBOXX",
        "url": "https://www.bboxx.com/feed/",
        "type": "rss",
        "item_sel": "item",
        "title_sel": "title",
        "link_sel": "link",
        "date_sel": "pubDate",
        "summary_sel": "description",
    },
    "techcabal-energy": {
        "name": "TechCabal Energy",
        "url": "https://techcabal.com/tag/energy/feed/",
        "type": "rss",
        "item_sel": "item",
        "title_sel": "title",
        "link_sel": "link",
        "date_sel": "pubDate",
        "summary_sel": "description",
        "keywords": ["solar", "off-grid", "clean energy", "renewable", "mini-grid",
                     "paygo", "energy access", "power", "electric", "grid"],
    },
    # ──────────────────────────────────────────────────────────────
    # 新增数据源（2026-06-19 扩展）
    # ──────────────────────────────────────────────────────────────
    "renewable-energy-world": {
        "name": "Renewable Energy World Solar",
        "url": "https://www.renewableenergyworld.com/solar/feed/",
        "type": "rss",
        "item_sel": "item",
        "title_sel": "title",
        "link_sel": "link",
        "date_sel": "pubDate",
        "summary_sel": "description",
        "keywords": ["africa", "african", "nigeria", "kenya", "ghana", "senegal",
                     "uganda", "tanzania", "rwanda", "ethiopia", "zambia", "mozambique",
                     "off-grid", "mini-grid", "minigrid", "solar home", "paygo",
                     "electrification", "energy access", "sub-saharan"],
    },
    "solar-industry-mag": {
        "name": "Solar Industry Magazine",
        "url": "https://solarindustrymag.com/feed",
        "type": "rss",
        "item_sel": "item",
        "title_sel": "title",
        "link_sel": "link",
        "date_sel": "pubDate",
        "summary_sel": "description",
        "keywords": ["africa", "african", "nigeria", "kenya", "off-grid",
                     "mini-grid", "minigrid", "microgrid", "solar home",
                     "electrification", "energy access", "rural"],
    },
    "freeing-energy": {
        "name": "Freeing Energy",
        "url": "https://freeingenergy.com/feed/",
        "type": "rss",
        "item_sel": "item",
        "title_sel": "title",
        "link_sel": "link",
        "date_sel": "pubDate",
        "summary_sel": "description",
        "keywords": ["africa", "african", "off-grid", "mini-grid", "solar home",
                     "paygo", "electrification", "energy access", "rural",
                     "nigeria", "kenya", "tanzania", "ghana", "ethiopia"],
    },
    "how-we-made-it": {
        "name": "How We Made It In Africa",
        "url": "https://www.howwemadeitinafrica.com/feed/",
        "type": "rss",
        "item_sel": "item",
        "title_sel": "title",
        "link_sel": "link",
        "date_sel": "pubDate",
        "summary_sel": "description",
        "keywords": ["solar", "off-grid", "mini-grid", "renewable", "clean energy",
                     "energy access", "electrification", "power", "electricity",
                     "climate", "green energy"],
    },
    "allafrica-energy": {
        "name": "AllAfrica Energy",
        "url": "https://allafrica.com/energy/",
        "type": "html",
        "selector": ".story-item, .list-item, article, tr.story",
        "title_sel": "a.story-title, a, h2, h3",
        "link_sel": "a",
        "date_sel": ".story-date, .date, time, small",
        "summary_sel": ".story-summary, p, .summary",
        "keywords": ["solar", "off-grid", "mini-grid", "minigrid", "microgrid",
                     "renewable", "clean energy", "electrification", "energy access",
                     "paygo", "solar home", "mission 300", "power africa"],
    },
    "esi-africa": {
        "name": "ESI Africa",
        "url": "https://www.esi-africa.com/",
        "type": "html",
        "selector": "article, .post, .td_module_wrap, .item-details, div[class*=post]",
        "title_sel": "h2, h3, .entry-title, .td-module-title",
        "link_sel": "a",
        "date_sel": "time, .td-post-date, .date, .entry-date",
        "summary_sel": "p, .td-excerpt, .excerpt, .entry-summary",
        "keywords": ["solar", "off-grid", "mini-grid", "minigrid", "renewable",
                     "clean energy", "electrification", "energy access", "microgrid",
                     "pv", "photovoltaic", "energy storage", "battery"],
    },
}

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "raw")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def safe_text(el, default: str = "") -> str:
    """安全提取文本，去空白"""
    if el is None:
        return default
    text = el.get_text(strip=True) if hasattr(el, "get_text") else str(el).strip()
    return text[:800]  # 限制长度


def parse_date(text: str) -> Optional[str]:
    """尝试从文本中解析日期，返回 ISO 格式"""
    if not text:
        return None
    text = text.strip()

    # 尝试 ISO datetime
    for fmt in [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%m/%d/%Y",
        "%d/%m/%Y",
        # RSS pubDate 格式: "Wed, 17 Jun 2026 12:33:44 +000"
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S",
    ]:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text[:10] if len(text) >= 10 else text


def fetch_page(url: str, timeout: int = 15, is_xml: bool = False) -> Optional[BeautifulSoup]:
    """抓取页面，返回 BeautifulSoup 对象"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        if is_xml:
            return BeautifulSoup(resp.text, "lxml-xml")
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"[WARN] 抓取失败 {url}: {e}", file=sys.stderr)
        return None


def extract_articles(soup: BeautifulSoup, cfg: dict, base_url: str) -> list[dict]:
    """从页面中提取文章列表（支持 HTML 和 RSS/XML）"""
    articles = []
    source_type = cfg.get("type", "html")

    # ── RSS / XML 解析 ──
    if source_type == "rss":
        items = soup.select(cfg["item_sel"])
        keywords = [k.lower() for k in cfg.get("keywords", [])]

        for item in items[:15]:
            title_el = item.select_one(cfg["title_sel"])
            title = safe_text(title_el)
            if not title:
                continue

            # 关键词过滤
            if keywords:
                title_lower = title.lower()
                matched = any(kw in title_lower for kw in keywords)
                # 也检查摘要
                if not matched:
                    summary_el = item.select_one(cfg["summary_sel"])
                    if summary_el:
                        matched = any(kw in safe_text(summary_el).lower() for kw in keywords)
                if not matched:
                    continue

            link_el = item.select_one(cfg["link_sel"])
            link = safe_text(link_el) if link_el else ""
            if link_el and link_el.get("href"):
                link = link_el["href"]

            date_el = item.select_one(cfg["date_sel"])
            raw_date = safe_text(date_el)
            parsed_date = parse_date(raw_date)

            summary_el = item.select_one(cfg["summary_sel"])
            summary = safe_text(summary_el)
            # RSS优先取全文 content:encoded，比 description 更长
            full_el = item.select_one("content\\:encoded, encoded")
            if full_el:
                full_text = safe_text(full_el)
                if len(full_text) > len(summary):
                    summary = full_text

            articles.append({
                "title": title,
                "url": link,
                "date": parsed_date,
                "summary": summary,
                "source_name": cfg["name"],
            })
        return articles

    # ── HTML 页面解析 ──
    cards = soup.select(cfg["selector"])
    if not cards:
        cards = soup.select("article, .post, .news-item, .td_module_wrap, .gb-query-loop-item")

    for card in cards[:10]:
        title_el = None
        for sel in cfg["title_sel"].split(", "):
            title_el = card.select_one(sel)
            if title_el:
                break
        title = safe_text(title_el)

        link_el = None
        for sel in cfg["link_sel"].split(", "):
            link_el = card.select_one(sel)
            if link_el:
                break
        link = ""
        if link_el:
            href = link_el.get("href", "")
            link = href if href.startswith("http") else urljoin(base_url, href)

        date_el = None
        for sel in cfg["date_sel"].split(", "):
            date_el = card.select_one(sel)
            if date_el:
                break
        raw_date = ""
        if date_el:
            raw_date = date_el.get("datetime", "") or safe_text(date_el)
        parsed_date = parse_date(raw_date)

        summary_el = None
        for sel in cfg["summary_sel"].split(", "):
            summary_el = card.select_one(sel)
            if summary_el:
                break
        summary = safe_text(summary_el)

        # HTML 关键词过滤
        keywords = [k.lower() for k in cfg.get("keywords", [])]
        if keywords and title:
            title_lower = title.lower()
            summary_lower = summary.lower()
            matched = any(kw in title_lower or kw in summary_lower for kw in keywords)
            if not matched:
                continue

        if title:
            articles.append({
                "title": title,
                "url": link,
                "date": parsed_date or "",
                "summary": summary,
                "source_name": cfg["name"],
            })

    return articles


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def crawl_source(source_key: str) -> list[dict]:
    """爬取单个数据源"""
    cfg = SOURCES[source_key]
    print(f"[INFO] 正在抓取 {cfg['name']} ...")

    is_rss = cfg.get("type") == "rss"
    soup = fetch_page(cfg["url"], is_xml=is_rss)
    if soup is None:
        return []
    articles = extract_articles(soup, cfg, cfg["url"])
    print(f"[INFO] {cfg['name']}: 抓到 {len(articles)} 篇文章")
    return articles


def filter_by_days(articles: list[dict], days: int) -> list[dict]:
    """按天数过滤文章"""
    cutoff = (datetime.now(CST) - timedelta(days=days)).strftime("%Y-%m-%d")
    filtered = [a for a in articles if a["date"] and a["date"] >= cutoff]
    return filtered if filtered else articles  # 没日期就不过滤


def save_output(data: dict, filename: str):
    """保存 JSON 输出"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] 已保存: {filepath}")
    return filepath


def main():
    import argparse

    parser = argparse.ArgumentParser(description="非洲离网太阳能市场周报爬虫")
    parser.add_argument("--source", choices=list(SOURCES.keys()), help="指定单个数据源")
    parser.add_argument("--days", type=int, default=7, help="只看最近 N 天的文章 (默认 7)")
    parser.add_argument("--json-only", action="store_true", help="仅输出 JSON，不写入文件")
    args = parser.parse_args()

    now_cst = datetime.now(CST)
    results = {
        "crawled_at": now_cst.isoformat(),
        "week": f"{now_cst.year}-W{now_cst.isocalendar()[1]:02d}",
        "sources": [],
        "summary": {},
    }

    source_keys = [args.source] if args.source else list(SOURCES.keys())

    total = 0
    for key in source_keys:
        articles = crawl_source(key)
        if args.days:
            articles = filter_by_days(articles, args.days)
        results["sources"].append({
            "key": key,
            "name": SOURCES[key]["name"],
            "articles": articles,
        })
        results["summary"][key] = len(articles)
        total += len(articles)

    results["summary"]["total"] = total

    if args.json_only:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        filename = f"{now_cst.strftime('%Y-%m-%d')}-raw.json"
        save_output(results, filename)

    # 汇总输出
    print(f"\n{'='*50}")
    print(f"爬取完成! 共 {total} 篇文章")
    for k, v in results["summary"].items():
        if k != "total":
            print(f"  {SOURCES[k]['name']}: {v} 篇")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
