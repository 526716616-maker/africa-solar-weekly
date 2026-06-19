"""
非洲离网太阳能市场资讯 - HTML 生成器
=====================================
将结构化新闻数据 + 点评渲染为资讯 HTML 页面。

输入格式 (data.json):
{
  "week": "2026-W24",
  "date": "2026-06-08",
  "issue": 23,
  "highlights": [
    {"num": "1000万+", "label": "年销售套数"},
    {"num": "1.5亿", "label": "累计服务人口"}
  ],
  "sections": [
    {
      "title": "一、行业动态",
      "items": [
        {
          "tag": "GOGLA · 市场报告",
          "title": "...",
          "summary": "...",
          "bullets": ["...", "..."],
          "source": "GOGLA Newsroom",
          "source_url": "https://...",
          "date": "2026-06-03"
        }
      ]
    },
    {
      "title": "二、重点企业动态",
      "companies": [
        {
          "icon": "MY",
          "name": "MySol / ENGIE Energy Access",
          "description": "..."
        }
      ]
    }
  ]
}

用法:
    python generate_html.py data.json > weekly.html
    python generate_html.py data.json -o output/week23.html
"""

import json
import os
import sys
from datetime import datetime


CSS = """\
/* ===== 非洲离网太阳能市场资讯 - 样式 ===== */
:root {
  --bg: #f8f9fa;
  --card: #ffffff;
  --text: #1a1a2e;
  --text-secondary: #555770;
  --text-tertiary: #8e8ea0;
  --border: #e8e8ee;
  --green-dark: #0F6E56;
  --green-light: #1D9E75;
  --green-bg: #E1F5EE;
  --green-tag-bg: rgba(15,110,86,0.08);
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, "Noto Sans SC", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.7;
  -webkit-font-smoothing: antialiased;
}

.container {
  max-width: 780px;
  margin: 0 auto;
  padding: 32px 24px 56px;
}

/* ===== Header ===== */
.header {
  background: var(--green-dark);
  color: #fff;
  padding: 36px 32px 28px;
  border-radius: var(--radius-lg);
  margin-bottom: 28px;
}
.header h1 {
  font-size: 22px;
  font-weight: 700;
  margin-bottom: 4px;
  letter-spacing: -0.01em;
}
.header .subtitle {
  font-size: 15px;
  opacity: 0.78;
  font-weight: 400;
}
.header .meta {
  display: flex;
  gap: 10px;
  margin-top: 18px;
  flex-wrap: wrap;
}
.header .meta span {
  background: rgba(255,255,255,0.15);
  border-radius: var(--radius-sm);
  padding: 4px 12px;
  font-size: 13px;
  letter-spacing: 0.02em;
}

/* ===== Stats Row ===== */
.section-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin: 36px 0 14px;
}
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 10px;
}
.stat-box {
  background: var(--card);
  border: 0.5px solid var(--border);
  border-radius: var(--radius-md);
  padding: 18px 16px;
  text-align: center;
}
.stat-box .num {
  font-size: 26px;
  font-weight: 800;
  color: var(--green-dark);
  margin-bottom: 6px;
}
.stat-box .lbl {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}
@media (max-width: 560px) {
  .stats-row { grid-template-columns: repeat(2, 1fr); }
}

/* ===== News Card ===== */
.news-card {
  background: var(--card);
  border: 0.5px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 22px 24px;
  margin-bottom: 16px;
  transition: border-color 0.15s;
}
.news-card:hover { border-color: var(--green-light); }
.news-card .tag {
  display: inline-block;
  background: var(--green-tag-bg);
  color: var(--green-dark);
  font-size: 12px;
  font-weight: 500;
  padding: 3px 12px;
  border-radius: 100px;
}
.news-card .card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.news-card .card-date {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
}
.news-card h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text);
}
/* ===== 通用：卡片内列表 & 段落样式 ===== */
.news-card .summary,
.company-card .summary {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 12px;
  line-height: 1.7;
}
.news-card .bullets,
.company-card .bullets {
  list-style: none;
  margin-bottom: 12px;
}
.news-card .bullets li,
.company-card .bullets li {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 3px 0 3px 18px;
  position: relative;
  word-break: break-word;
}
.news-card .bullets li::before,
.company-card .bullets li::before {
  content: "";
  position: absolute;
  left: 2px;
  top: 10px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--green-light);
}
.news-card .mb,
.company-card .mb { margin-bottom: 10px; }
.news-card .bullets,
.company-card .bullets { margin-bottom: 0; }
.news-card .source {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
}
.news-card .source a {
  color: var(--green-dark);
  text-decoration: none;
}
.news-card .source a:hover { text-decoration: underline; }

/* ===== Company Card ===== */
.company-card {
  background: var(--card);
  border: 0.5px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 22px 24px;
  margin-bottom: 16px;
  transition: border-color 0.15s;
}
.company-card:hover { border-color: var(--green-light); }
.company-card .tag {
  display: inline-block;
  background: var(--green-tag-bg);
  color: var(--green-dark);
  font-size: 12px;
  font-weight: 500;
  padding: 3px 12px;
  border-radius: 100px;
}
.company-card .card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.company-card .card-date {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
}
.company-card h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text);
}
.company-card .source {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 10px;
}
.company-card .source a {
  color: var(--green-dark);
  text-decoration: none;
}
.company-card .source a:hover { text-decoration: underline; }

/* ===== Archive Nav ===== */
.nav-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.nav-bar a {
  font-size: 14px;
  color: var(--green-dark);
  text-decoration: none;
  padding: 4px 0;
  font-weight: 500;
}
.nav-bar a:hover { text-decoration: underline; }

/* ===== Archive Page ===== */
.archive-list {
  list-style: none;
}
.archive-item {
  background: var(--card);
  border: 0.5px solid var(--border);
  border-radius: var(--radius-md);
  padding: 18px 22px;
  margin-bottom: 12px;
  transition: border-color 0.15s;
}
.archive-item:hover { border-color: var(--green-light); }
.archive-item a {
  text-decoration: none;
  color: var(--text);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.archive-item .issue-title {
  font-size: 16px;
  font-weight: 600;
}
.archive-item .issue-meta {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-top: 6px;
}
.archive-item .issue-count {
  font-size: 14px;
  color: var(--green-dark);
  font-weight: 500;
  white-space: nowrap;
}

/* ===== Footer ===== */
.footer {
  text-align: center;
  font-size: 13px;
  color: var(--text-tertiary);
  border-top: 0.5px solid var(--border);
  padding-top: 24px;
  margin-top: 40px;
}
"""


def generate_html(data: dict) -> str:
    """根据数据字典生成完整 HTML"""

    week = data.get("week", "")
    date_str = data.get("date", "")
    issue = data.get("issue", "")
    highlights = data.get("highlights", [])
    sections = data.get("sections", [])

    # 拼装统计卡片
    stats_html = ""
    for h in highlights:
        stats_html += f'<div class="stat-box"><div class="num">{h["num"]}</div><div class="lbl">{h["label"]}</div></div>'

    # 拼装各板块
    sections_html = ""
    for sec in sections:
        sections_html += f'<div class="section-title">{sec["title"]}</div>\n'

        # 行业新闻卡片
        for item in sec.get("items", []):
            tag = item.get("tag", "")
            title = item.get("title", "")
            summary = item.get("summary", "")
            # 描述与标题重复则隐藏
            item_title = item.get("title", "")
            if summary and item_title and (summary == item_title or summary[:30] == item_title[:30]):
                summary = ""
            bullets = item.get("bullets", [])
            source = item.get("source", "")
            source_url = item.get("source_url", "")
            item_date = item.get("date", "")

            bullets_html = ""
            if bullets:
                bullets_html = '<ul class="bullets">'
                for b in bullets:
                    bullets_html += f"<li>{b}</li>"
                bullets_html += "</ul>"

            source_line = ""
            if source:
                if source_url:
                    source_line = f'<div class="source">来源：<a href="{source_url}" target="_blank" rel="noopener">{source}</a></div>'
                else:
                    source_line = f'<div class="source">来源：{source}</div>'

            tag_html = f'<span class="tag">{tag}</span>' if tag else ""
            date_html = f'<span class="card-date">{item_date}</span>' if item_date else '<span class="card-date" style="color:#aaa">日期未知</span>'

            # 准备摘要HTML（空则不渲染）
            summary_html = f'<div class="summary">{summary}</div>' if summary else ''
            
            sections_html += f"""\
<div class="news-card">
  <div class="card-top">
    {tag_html}
    {date_html}
  </div>
  <h3>{title}</h3>
  {summary_html}
  {bullets_html}
  {source_line}
</div>
"""

        # 企业卡片
        for company in sec.get("companies", []):
            name = company.get("name", "")
            desc = company.get("description") or ""
            # 描述与标题重复则隐藏
            if desc and (desc == name or desc[:30] == name[:30]):
                desc = ""
            tag = company.get("tag", "企业动态")
            source = company.get("source", "")
            source_url = company.get("source_url", "")
            comp_date = company.get("date", "")
            date_html = f'<span class="card-date">{comp_date}</span>' if comp_date else '<span class="card-date" style="color:#aaa">日期未知</span>'
            source_line = ""
            if source and source_url:
                source_line = f'<div class="source">来源：<a href="{source_url}" target="_blank" rel="noopener">{source}</a></div>'
            elif source:
                source_line = f'<div class="source">来源：{source}</div>'

            desc_html = f'<div class="summary">{desc}</div>' if desc else ''
            
            sections_html += f"""\
<div class="company-card">
  <div class="card-top">
    <span class="tag">{tag}</span>
    {date_html}
  </div>
  <h3>{name}</h3>
  {desc_html}
  {source_line}
</div>
"""

    issue_info = f"第 {issue} 期" if issue else ""
    date_info = date_str

    return f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>非洲离网太阳能市场资讯 {date_info} {issue_info}</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">

  <div class="nav-bar">
    <a href="archive.html">← 查看往期</a>
    <span style="font-size:13px;color:var(--text-tertiary)">{issue_info}</span>
  </div>

  <div class="header">
    <h1>Africa Off-Grid Solar Market News</h1>
    <p class="subtitle">非洲离网太阳能市场资讯</p>
    <div class="meta">
      <span>{issue_info}</span>
      <span>{date_info}</span>
      <span>行业动态 · 企业跟踪</span>
    </div>
  </div>

  <div class="section-title">本期数据亮点</div>
  <div class="stats-row">{stats_html}</div>

  {sections_html}

  <div class="footer">
    Africa Solar News · {date_info} · 每日更新
  </div>

</div>
</body>
</html>"""


def generate_archive_html(issues: list) -> str:
    """生成往期目录页面"""
    items_html = ""
    for iss in issues:
        fname = iss["file"]
        issue = iss.get("issue", "?")
        date_str = iss.get("date", "")
        industry = iss.get("industry", 0)
        company = iss.get("company", 0)
        items_html += f"""\
  <li class="archive-item">
    <a href="{fname}">
      <div>
        <div class="issue-title">第 {issue} 期 · {date_str}</div>
        <div class="issue-meta">行业 {industry} 篇 · 企业 {company} 篇</div>
      </div>
      <div class="issue-count">{industry + company} 篇</div>
    </a>
  </li>
"""
    return f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>非洲离网太阳能市场资讯 - 往期目录</title>
<style>{CSS}
.archive-header {{ text-align:center; padding:24px 0 8px; }}
.archive-header h1 {{ font-size:22px; color:var(--green-dark); }}
.archive-header p {{ font-size:14px; color:var(--text-tertiary); margin-top:6px; }}
</style>
</head>
<body>
<div class="container">

  <div class="archive-header">
    <h1>📚 往期资讯目录</h1>
    <p>Africa Off-Grid Solar Market News Archive</p>
  </div>

  <ul class="archive-list">
{items_html}
  </ul>

  <div class="footer">
    共 {len(issues)} 期 · 每日更新
  </div>

</div>
</body>
</html>"""


def main():
    import argparse

    parser = argparse.ArgumentParser(description="周报 HTML 生成器")
    parser.add_argument("data", help="JSON 数据文件路径")
    parser.add_argument("-o", "--output", help="输出 HTML 文件路径")
    parser.add_argument("--stdout", action="store_true", help="输出到 stdout")
    args = parser.parse_args()

    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)

    html = generate_html(data)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[OK] 已生成: {args.output}")
    else:
        print(html)


if __name__ == "__main__":
    main()
