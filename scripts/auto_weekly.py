"""全自动：抓取 raw JSON → 翻译为中文 → 生成资讯 HTML"""
import json
import os
import sys
import re
import time
import requests
from datetime import datetime, timezone
from deep_translator import GoogleTranslator

CST = timezone(__import__('datetime').timedelta(hours=8))

# ── 翻译 ──
_translator = None
_cache = {}

def get_translator():
    global _translator
    if _translator is None:
        _translator = GoogleTranslator(source='auto', target='zh-CN')
    return _translator

def translate_text(text: str, retries: int = 3) -> str:
    """翻译文本为中文，短文本跳过，失败返回原文（带重试+日志）"""
    if not text or len(text.strip()) < 5:
        return text
    if text in _cache:
        return _cache[text]
    # 纯中文/数字跳过
    if re.match(r'^[\u4e00-\u9fff\d\s\.\,\;\:\!\?\-\+]+$', text.strip()):
        return text
    for attempt in range(retries + 1):
        try:
            result = get_translator().translate(text)
            if result and result != text:
                _cache[text] = result
                return result
        except Exception as e:
            if attempt < retries:
                print(f"  [retry] 翻译重试 {attempt+1}/{retries}: {e}", file=sys.stderr)
                time.sleep(3 * (attempt + 1))  # 指数退避
            else:
                print(f"  [warn] 翻译失败 ({type(e).__name__}): {str(e)[:80]}", file=sys.stderr)
                return text


# ── AI 精读 ──
QWEN_KEY = os.environ.get('QWEN_API_KEY', '') or 'sk-f0d5f80034794f048e82c936ec3556f0'
QWEN_API = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'

DEEP_PROMPT = """你是非洲离网太阳能分析师。请用中文撰写一篇精读简报，严格使用以下格式，每组之间用一个空行分隔：

第一段：地点，核心事件概述。注明来源和项目名称。

📍 背景：
- 背景1（事实陈述或面临的问题，含具体数据）
- 背景2
- 背景3

📌 方案：
- 举措1（含具体数据）
- 举措2（含具体数据）
- 举措3（含具体数据）

💡 价值：
- 价值1
- 价值2
- 价值3

📈 趋势：一句话总结趋势。

要求：
- 使用 - 符号开头列表项，每组之间空行分隔
- 每个列表项不超过25字
- 提取具体数字（MW、金额、户数、百分比等）
- 总字数300-500字

参考示例（同一天的多篇文章可能共用相同背景）：

示例1 - 行业报告类：
---
地点：南非开普敦。GOGLA 2025年离网太阳能投资报告显示全球投资达3亿美元。
📍 背景：
- 离网太阳能需求激增
- 资金分配不均加剧
- 新兴企业融资困难
📌 方案：
- 投资额达3.0亿美元
- 混合融资弥补210亿缺口
- 本地货币证券化创新
💡 价值：
- 加速能源普及覆盖
- 推动可持续发展
- 提升企业融资能力
📈 趋势：离网太阳能市场正从初创阶段向成熟阶段过渡。

示例2 - 企业动态类：
---
地点：赞比亚。Ignite Power启动离网太阳能推广计划。
📍 背景：
- 80%人口无电力供应
- 农村电力覆盖率极低
- 柴油发电成本高昂
📌 方案：
- 安装1.2MW太阳能系统
- 服务500户家庭
- 建立社区充电网络
💡 价值：
- 提升生活质量和教育
- 创造本地就业
- 降低碳排放
📈 趋势：离网太阳能正成为非洲电气化的关键路径。

示例3 - 政策分析类：
---
地点：西非。ECOWAS宣布2030年可再生能源目标48%。
📍 背景：
- 1.9亿人无电力供应
- 农村通电率仅12%
- 电力损失率高达35%
📌 方案：
- 可再生能源占比48%
- 电力损失降至35%以下
- 区域电网互联互通
💡 价值：
- 推动清洁能源转型
- 提升农村经济发展
- 促进区域能源整合
📈 趋势：西非正通过政策与合作加速能源变革。
---"""

def deep_read_light(title, summary_text, source_name):
    """用RSS摘要（无正文）直接调Qwen做轻量结构化改写"""
    if not summary_text or len(summary_text) < 30:
        return None
    prompt = f"""你是非洲离网太阳能快讯编辑。根据以下标题和摘要，用中文生成一段150-200字的精简短讯，提取关键数据和事实。
格式：地点/来源 + 核心事实 + 1-2个关键数字（如有）。不要编造数据，只基于给定内容。

标题：{title}
来源：{source_name}
摘要：{summary_text[:800]}"""
    
    try:
        resp = requests.post(QWEN_API, headers={
            'Authorization': f'Bearer {QWEN_KEY}',
            'Content-Type': 'application/json'
        }, json={
            'model': 'qwen-turbo',
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.5,
            'max_tokens': 400,
        }, timeout=30)
        result = resp.json()
        if 'choices' in result:
            return result['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f'  [warn] 轻量精读失败: {e}', file=sys.stderr)
    return None


def deep_read(title, source_url, source_name, retries=1):
    """获取文章全文并调用Qwen精读改写"""
    content = ''
    # Google News 链接是重定向页，没有正文内容，直接跳过
    if 'news.google.com' in source_url:
        return None

    try:
        resp = requests.get(source_url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; AfricaSolarNews/1.0)'
        }, timeout=15)
        if resp.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                tag.decompose()
            for sel in ['article', 'main', '.post-content', '.entry-content', '.content', 'body']:
                el = soup.select_one(sel)
                if el:
                    content = el.get_text(separator="\n", strip=True)
                    break
            content = content[:4000]
    except Exception as e:
        print(f'  [warn] 抓取原文失败 {source_url}: {e}', file=sys.stderr)

    if not content or len(content) < 300:
        return None

    # 关键词密度检测：内容太泛（广告/导航文字）则跳过精读
    solar_keywords = ["solar", "energy", "power", "electrification", "off.grid",
                      "mini.grid", "renewable", "electricity", "grid", "africa",
                      "sun", "pv", "photovoltaic", "battery", "storage",
                      "climate", "emission", "carbon", "clean energy", "green",
                      "rural", "offgrid", "paygo", "pay-as-you-go", "kwh",
                      "kilowatt", "megawatt", "gigawatt", "generator", "diesel",
                      "subsidy", "tariff", "utility", "distribution", "household"]
    text_lower = content.lower()
    kw_count = sum(1 for kw in solar_keywords if kw in text_lower)
    density = kw_count / max(len(text_lower.split()), 1)
    if density < 0.01:  # 1%阈值（网页含大量导航/页脚稀释）
        print(f'  [warn] 关键词密度 {density:.1%} 过低，跳过精读', file=sys.stderr)
        return None

    for attempt in range(retries + 1):
        try:
            resp = requests.post(QWEN_API, headers={
                'Authorization': f'Bearer {QWEN_KEY}',
                'Content-Type': 'application/json'
            }, json={
                'model': 'qwen-turbo',
                'messages': [
                    {'role': 'system', 'content': DEEP_PROMPT},
                    {'role': 'user', 'content': f"标题：{title}\n来源：{source_name}\n\n正文：\n{content}"}
                ],
                'temperature': 0.7,
                'max_tokens': 1200,
            }, timeout=60)
            result = resp.json()
            if 'choices' not in result:
                err_msg = result.get('error', {}).get('message', str(result))
                print(f'  [warn] Qwen API 返回错误: {err_msg}', file=sys.stderr)
                return None
            return result['choices'][0]['message']['content'].strip()
        except Exception as e:
            if attempt < retries:
                print(f'  [retry] Qwen精读重试 {attempt+1}: {e}', file=sys.stderr)
                time.sleep(3)
            else:
                print(f'  [warn] Qwen精读失败: {e}', file=sys.stderr)
                return None

# ── 读取 raw JSON（自动找最新的） ──
raw_dir = os.path.join(os.path.dirname(__file__), "..", "output", "raw")
raw_dir = os.path.abspath(raw_dir)
raw_files = sorted([
    f for f in os.listdir(raw_dir)
    if f.endswith("-raw.json") and not f.startswith("latest")
], reverse=True)
if not raw_files:
    print("[ERROR] 没有找到 raw JSON 文件", file=sys.stderr)
    sys.exit(1)
raw_path = os.path.join(raw_dir, raw_files[0])
print(f"[INFO] 读取: {raw_files[0]}")
with open(raw_path, "r", encoding="utf-8") as f:
    raw = json.load(f)

# ── 自动计算期号（基于不同日期计数，不是文件数或max issue） ──
raw_dir_abs = os.path.abspath(raw_dir)
now = datetime.now(CST)

# 收集所有已有周刊的日期（去重）
seen_dates = set()
for f in os.listdir(raw_dir_abs):
    if f.endswith("-weekly.json") and not f.startswith("latest"):
        try:
            with open(os.path.join(raw_dir_abs, f), "r", encoding="utf-8") as fp:
                d = json.load(fp)
            dt = d.get("date", "")[:10]  # YYYY-MM-DD
            if dt:
                seen_dates.add(dt)
        except Exception:
            pass

today = now.strftime("%Y-%m-%d")
# 如果今天已有周刊，复用期号；否则用唯一日期数+1
if today in seen_dates:
    seen_dates.discard(today)  # 不算今天
    # 尝试读取已有期号
    existing = [f for f in os.listdir(raw_dir_abs) if f.startswith(today) and f.endswith("-weekly.json")]
    if existing:
        try:
            with open(os.path.join(raw_dir_abs, existing[0]), "r", encoding="utf-8") as fp:
                d = json.load(fp)
            issue_num = d.get("issue", len(seen_dates) + 1)
        except:
            issue_num = len(seen_dates) + 1
    else:
        issue_num = len(seen_dates) + 1
else:
    issue_num = len(seen_dates) + 1

# ── 清洗工具 ──
def clean_summary(text: str, max_len: int = 600) -> str:
    """清洗 RSS/HTML 摘要：去标签、去垃圾文字、截断"""
    if not text:
        return ""
    # Google News RSS: 摘要被 <a href="..."> 包裹，提取 a 标签内文本
    a_match = re.search(r'<a\s[^>]*href="[^"]*"[^>]*>(.*?)</a>', text, re.DOTALL)
    if a_match and len(a_match.group(1).strip()) > 10:
        text = a_match.group(1).strip()
    # 去掉 HTML 标签
    text = re.sub(r'<[^>]+>', ' ', text)
    # 解码 HTML 实体
    text = text.replace('&#038;', '&').replace('&#38;', '&')
    text = text.replace('&#8217;', "'").replace('&#8216;', "'")
    text = text.replace('&#8220;', '"').replace('&#8221;', '"')
    text = text.replace('&#8230;', '...').replace('&#8211;', '-')
    text = text.replace('&amp;', '&').replace('&nbsp;', ' ')
    # 去掉多余空白
    text = re.sub(r'\s+', ' ', text).strip()
    # 去掉 RSS 尾巴文字
    text = re.sub(r'The post .*? appeared first on .*?\.?$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'The post .*?$', '', text, flags=re.IGNORECASE)
    # 去掉 [...] 截断标记
    text = re.sub(r'\s*\[\.\.\.\]\s*$', '', text)
    # 去掉结尾不完整的句子（截断在非句末处）
    text = text.strip()
    if text and text[-1] not in '.。!！?？':
        # 找最后一个完整句号
        last_period = max(text.rfind('. '), text.rfind('。'), text.rfind('! '), text.rfind('? '))
        if last_period > len(text) * 0.5:  # 至少过半
            text = text[:last_period+1]
    return text[:max_len].strip()

from format_rich import format_rich

def extract_numbers(text):
    """从文本中提取有意义的数字+单位，返回列表"""
    nums = []
    patterns = [
        # 带显式单位
        r'(\d+[\d,.]*\s*(?:MW|GW|kW|kWh|MWh|GWh))',
        r'(\d+[\d,.]*\s*(?:million|billion|trillion))',
        r'(\d+[\d,.]*\s*(?:people|households|families|customers|users|homes))',
        # 货币
        r'(\$[\d,.]+\s*(?:million|billion)?)',
        r'([\d,.]+%\s*(?:of)?)',
        # 无单位大数（千及以上）
        r'(\d{1,3}(?:,\d{3})+(?:\s*people|\s*homes|\s*units|\s*kits)?)',
    ]
    seen = set()
    for pat in patterns:
        for m in re.findall(pat, text, re.IGNORECASE):
            clean = m.strip().rstrip('.').rstrip(',')
            # 过滤纯年份和过小的数
            if re.match(r'^\d{4}$', clean.replace(',','')):
                continue
            num_part = re.search(r'[\d,.]+', clean)
            if num_part:
                val_str = num_part.group().replace(',','')
                try:
                    val = float(val_str)
                except ValueError:
                    continue
                if val < 1 and '%' not in clean:
                    continue
            if clean not in seen:
                nums.append(clean)
                seen.add(clean)
    return nums

def num_value(s):
    """提取数字大小用于排序（单位换算）"""
    s_clean = s.replace("$", "").replace(",", "").replace("%", "").strip()
    parts = s_clean.split()
    try:
        val = float(parts[0]) if parts else 0
    except (ValueError, IndexError):
        return 0
    unit = " ".join(parts[1:]).lower() if len(parts) > 1 else ""
    if unit in ("billion", "trillion"):
        val *= 1000
    if "people" in unit or "households" in unit or "families" in unit or "homes" in unit or "customers" in unit or "users" in unit:
        val *= 100  # 人口类数字加权
    return val

def smart_label(num_str, article_title, source_name):
    """为数字生成简短标签"""
    # 尝试从标题中提取关键词组
    title_clean = re.sub(r'[\\U0001F600-\\U0001FFFF]', '', article_title)
    title_clean = re.sub(r'[-–—|·•]', ' ', title_clean)
    words = [w.strip() for w in re.split(r'[:\s,，、]+', title_clean) if len(w.strip()) >= 2]
    # 过滤掉数字开头的词、纯数字
    words = [w for w in words if not re.match(r'^[\d\$]', w) and len(w) >= 2]
    # 取前3个有意义的词
    if words:
        label = ' '.join(words[:3])
        if len(label) > 20:
            label = label[:20]
        return label
    return source_name[:20]

# ── 智能亮点提取（从已分类的文章中提取具体数字）──
# 注意：此段必须在文章处理之后才能拿到 AI 精读后的 summary

# ── 防重：读取已有周刊文章标题，跳过已出现的 ──
seen_titles = set()
for fname in os.listdir(raw_dir_abs):
    if fname.endswith("-weekly.json") and not fname.startswith("latest"):
        # 跳过今天自己的文件（允许本期覆盖）
        if fname.startswith(now.strftime("%Y-%m-%d")):
            continue
        try:
            with open(os.path.join(raw_dir_abs, fname), "r", encoding="utf-8") as fp:
                old = json.load(fp)
            for sec in old.get("sections", []):
                for item in sec.get("items", []):
                    t = item.get("title", "")
                    if t:
                        # 取前 60 字做模糊匹配（翻译后可能略有差异）
                        seen_titles.add(t[:60].lower().strip())
                for comp in sec.get("companies", []):
                    n = comp.get("name", "")
                    if n:
                        seen_titles.add(n[:60].lower().strip())
        except Exception:
            pass
dedup_skipped = 0

# ── 分配文章到板块 ──
policy_items = []      # 一、政策规划
investment_items = []  # 二、投资数据
industry_items = []    # 三、行业动态
company_items = []     # 四、企业动态

# 子类目关键词
policy_keywords = [
    "policy", "regulation", "target", "goal", "plan", "strategy", "roadmap",
    "commitment", "initiative", "agreement", "treaty", "accord", "framework",
    "law", "decree", "mandate", "standard", "code", "act", "bill",
    "政策", "规划", "目标", "路线图", "协议", "承诺", "法律", "法规",
    "国家自主贡献", "ndc", "paris agreement", "unfccc", "cop",
    "evisa", "ecowas", "african union", "au", "world bank", "undp",
    "sustainable development", "sdg", "mission 300", "power africa",
]
investment_keywords = [
    "investment", "funding", "grant", "loan", "financing", "capital",
    "million", "billion", "usd", "euro", "fund", "investor", "equity",
    "debt", "securitization", "bond", "credit", "microfinance", "paygo",
    "subsidy", "aid", "dFC", "development finance", "climate finance",
    "green bond", "blended finance", "grant", "私募", "融资", "投资",
    "资金", "信贷", "债务", "证券化", "基金",
    "market size", "market growth", "revenue", "valuation", "series",
    "million", "billion", "trillion",
]

# 记录每个源已分配的文章数（无日期的源限制3篇）
source_count = {}

for src in raw["sources"]:
    for a in src["articles"]:
        title = a["title"]

        # 防重：已在往期出现过的文章跳过
        if title[:60].lower().strip() in seen_titles:
            dedup_skipped += 1
            continue

        raw_summary = a.get("summary", "") or ""
        summary = clean_summary(raw_summary)  # 清洗HTML/Google News链接
        url = a.get("url", "")
        date = a.get("date", "")

        # 只保留最近7天的资讯（无日期的保留，有日期但超7天则过滤）
        cutoff_7d = (datetime.now(CST) - __import__('datetime').timedelta(days=7)).strftime("%Y-%m-%d")
        if date and date < cutoff_7d:
            continue
        # 无日期的源每源最多3篇
        src_key = src["key"]
        if not date:
            source_count.setdefault(src_key, 0)
            if source_count[src_key] >= 3:
                continue
            source_count[src_key] += 1
        # 过滤无关内容
        skip_keywords = ["south asia", "flutterwave", "series e"]
        if any(kw in title.lower() for kw in skip_keywords):
            continue

        # AI 精读：抓原文+Qwen改写（失败则用RSS摘要做轻量精读，再失败回退原摘要）
        deep_succeeded = False
        deep_text = ""
        if url:
            print(f"  [deep] 精读: {title[:60]}...")
            deep = deep_read(title, url, src["name"])
            if deep:
                deep_text = translate_text(deep[:1000])
                deep_succeeded = True
                print(f"  [deep] OK ({len(deep_text)}字)")
            elif summary and len(summary) >= 30:
                # 正文抓取失败 → 用RSS摘要做轻量精读
                print(f"  [light] 轻量精读...")
                light = deep_read_light(title, summary, src["name"])
                if light:
                    deep_text = translate_text(light[:600])
                    deep_succeeded = True
                    print(f"  [light] OK ({len(deep_text)}字)")
                else:
                    print(f"  [deep] 回退原摘要")
            else:
                print(f"  [deep] 回退原摘要")

        # 根据来源分类
        company_sources = {"engie", "sunking", "bboxx", "m-kopa"}
        company_keywords = [
            "ignite power", "ignite energy", "sun king", "sunking",
            "bboxx", "m-kopa", "mkopa",
            "zola electric", "husk power", "nuru energy",
            "easy solar", "greenlight planet", "azuri tech",
            "solarnow", "one power", "mobisol", "fenix intl",
        ]

        is_company_article = (
            src["key"] in company_sources
            or any(kw in title.lower() for kw in company_keywords)
            or any(kw in summary.lower() for kw in company_keywords)
        )

        if is_company_article:
            # 企业动态 tag
            if src["key"] == "engie":
                tag_prefix = "企业动态 · Ignite Power"
            elif src["key"] == "sunking":
                tag_prefix = "企业动态 · Sun King"
            elif src["key"] == "bboxx":
                tag_prefix = "企业动态 · BBOXX"
            elif src["key"] == "m-kopa":
                tag_prefix = "企业动态 · M-KOPA"
                tag_prefix = "企业动态"
            # 精简描述（最多200字纯文本，不用AI精读格式）
            company_desc = ""
            if deep_succeeded and deep_text:
                # 摘取AI精读第一段（地点+概述），去掉后续分段和分隔符
                cleaned = (deep_text or "").strip()
                # 去掉开头的 --- 分隔线
                if cleaned.startswith('---'):
                    cleaned = cleaned[3:].strip()
                # 取第一段（双换行分隔）或第一行
                first_para = cleaned.split('\n\n')[0] if '\n\n' in cleaned else cleaned.split('\n')[0]
                # 去掉emoji标记
                for emoji in ['\U0001F4CD', '\U0001F4CC', '\U0001F4A1', '\U0001F4C8']:
                    first_para = first_para.replace(emoji, '')
                company_desc = first_para.strip()[:200]
            elif summary:
                company_desc = summary[:200]
            else:
                company_desc = title[:200]
            # 安全兜底：确保不为None或空
            company_desc = (company_desc or title[:200] or "暂无描述")
            company_items.append({
                "tag": tag_prefix,
                "name": title[:100],
                "description": company_desc,
                "source": src["name"],
                "source_url": url,
                "date": date,
            })
        else:
            # 行业动态 → 细分到政策/投资/行业
            tag_map = {
                "gogla": "GOGLA · 行业报告",
                "pv-magazine": "PV Magazine · 太阳能",
                "afsia": "AFSIA · 非洲太阳能",
                "lighting-global": "Lighting Global · 离网照明",
                "bgfa": "BGFA · 离网基金",
                "techcabal-energy": "TechCabal · 能源科技",
                "how-we-made-it": "How We Made It · 非洲商业",
                "solarafrica": "SolarAfrica · 太阳能洞察",
                "amda": "AMDA · 迷你电网",
            }
            tag = tag_map.get(src["key"], src["name"])

            # 行业类文章：AI精读成功后用 format_rich 格式化
            industry_summary = summary  # 默认用原摘要
            if deep_succeeded and deep_text:
                industry_summary = format_rich(deep_text)

            item = {
                "tag": tag,
                "title": title[:120],
                "summary": industry_summary,
                "bullets": [],
                "source": src["name"],
                "source_url": url,
                "date": date,
            }

            # 按关键词划分子类目
            text = f"{title} {summary}".lower()
            if any(kw in text for kw in policy_keywords):
                item["sub_category"] = "policy"
                policy_items.append(item)
            elif any(kw in text for kw in investment_keywords):
                item["sub_category"] = "investment"
                investment_items.append(item)
            else:
                industry_items.append(item)

# 如果企业动态不够，从 ENGIE 文章中也加到行业动态
# 不重复添加

# ── 智能亮点：从已分类文章中提取具体数字 ──
context_pairs = []
seen = set()

# 收集所有已分类文章的文字
def collect_highlight_texts():
    texts = []
    for item in policy_items + investment_items + industry_items:
        texts.append((item.get("title", ""), item.get("summary", ""), item.get("source", "")))
    for c in company_items:
        texts.append((c.get("name", ""), c.get("description", ""), c.get("source", "")))
    return texts

for title, summary, source in collect_highlight_texts():
    full_text = (title or "") + " " + (summary or "")
    nums = extract_numbers(full_text)
    for n in nums:
        n_key = re.sub(r'[\s,\.\$\%]', '', n).lower()
        if n_key not in seen and len(n_key) >= 2:
            seen.add(n_key)
            label = smart_label(n, title or source, source or "")
            context_pairs.append((n, label))

context_pairs.sort(key=lambda x: num_value(x[0]), reverse=True)
highlights = []
for n, label in context_pairs[:4]:
    highlights.append({"num": n, "label": label})

# 兜底：如果提取不到数字，用分类统计
if len(highlights) < 2:
    highlights = [
        {"num": str(len(industry_items) + len(policy_items) + len(investment_items)), "label": "本期行业动态"},
        {"num": str(len(company_items)), "label": "本期企业动态"},
    ][:4]

# ── 翻译为中文 ──
all_industry_items = policy_items + investment_items + industry_items
total_to_translate = len(all_industry_items) + len(company_items)
print(f"[INFO] 正在翻译 {total_to_translate} 篇文章为中文...")

def translate_summary_html(html_text: str) -> str:
    """翻译 HTML 摘要：提取纯文本翻译后放回"""
    if not html_text:
        return ""
    if "<" not in html_text:
        return translate_text(html_text)
    # 保留HTML结构，只翻译纯文本部分
    import re
    parts = re.split(r'(<[^>]+>)', html_text)
    for i, part in enumerate(parts):
        if not part.startswith('<'):
            translated = translate_text(part.strip())
            if translated and translated != part.strip():
                parts[i] = translated
    return ''.join(parts)

for item in all_industry_items:
    item["title"] = translate_text(item["title"])
    item["summary"] = translate_summary_html(item["summary"])

for item in company_items:
    item["name"] = translate_text(item["name"])
    item["description"] = translate_summary_html(item.get("description") or "") or item["name"]

# 翻译亮点标签
for h in highlights:
    h["label"] = translate_text(h["label"])
print("[INFO] 翻译完成")

# ── 组装 curated JSON ──
curated = {
    "week": raw["week"],
    "date": now.strftime("%Y-%m-%d"),
    "issue": issue_num,
    "highlights": highlights,
    "sections": [],
}

if policy_items:
    curated["sections"].append({
        "title": "一、政策规划",
        "items": policy_items,
    })

if investment_items:
    curated["sections"].append({
        "title": "二、投资数据",
        "items": investment_items,
    })

if industry_items:
    curated["sections"].append({
        "title": "三、行业动态",
        "items": industry_items,
    })

if company_items:
    curated["sections"].append({
        "title": "四、重点企业动态",
        "companies": company_items,  # 不限数量，全显示
    })

# ── 保存 curated JSON ──
curated_path = os.path.join(os.path.dirname(__file__), "..", "output", "raw", f"{now.strftime('%Y-%m-%d')}-weekly.json")
curated_path = os.path.abspath(curated_path)
with open(curated_path, "w", encoding="utf-8") as f:
    json.dump(curated, f, ensure_ascii=False, indent=2)
print(f"[OK] curated JSON: {curated_path}")
print(f"  政策规划: {len(policy_items)} 条")
print(f"  投资数据: {len(investment_items)} 条")
print(f"  行业动态: {len(industry_items)} 条")
print(f"  企业动态: {len(company_items)} 条")
if dedup_skipped:
    print(f"  防重跳过: {dedup_skipped} 篇")

# ── 生成 HTML ──
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from generate_html import generate_html
html = generate_html(curated)

html_path = os.path.join(os.path.dirname(__file__), "..", "output", "html", f"week-{issue_num:02d}-{now.strftime('%Y-%m-%d')}.html")
html_path = os.path.abspath(html_path)
with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"[OK] HTML: {html_path}")

# ── 同步更新 index.html（自动跳转最新期） ──
latest_name = f"week-{issue_num:02d}-{now.strftime('%Y-%m-%d')}.html"
index_path = os.path.join(os.path.dirname(__file__), "..", "output", "html", "index.html")
index_path = os.path.abspath(index_path)
index_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>非洲离网太阳能市场资讯</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f8f9fa;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}}
.card{{background:#fff;border-radius:14px;padding:40px 32px;text-align:center;max-width:400px;box-shadow:0 1px 3px rgba(0,0,0,0.06)}}
h1{{font-size:18px;color:#0F6E56;margin:0 0 8px}}
p{{font-size:13px;color:#555770;margin:0 0 24px}}
a.btn{{display:inline-block;background:#0F6E56;color:#fff;text-decoration:none;padding:10px 28px;border-radius:8px;font-size:14px;margin:6px}}
a.btn.outline{{background:transparent;color:#0F6E56;border:1px solid #0F6E56}}
</style>
<meta http-equiv="refresh" content="3; url={latest_name}">
</head>
<body>
<div class="card">
  <h1>🌍 非洲离网太阳能市场资讯</h1>
  <p>Africa Off-Grid Solar Market News</p>
  <a class="btn" href="{latest_name}">📰 查看最新期</a>
  <br>
  <a class="btn outline" href="archive.html">📚 查看往期</a>
  <p style="font-size:11px;color:#8e8ea0;margin-top:20px">3 秒后自动跳转...</p>
</div>
</body>
</html>"""
with open(index_path, "w", encoding="utf-8") as f:
    f.write(index_content)
print(f"[OK] index.html: {index_path}")

# ── 同步更新 archive.html（往期目录） ──
from generate_html import generate_archive_html
archive_path = os.path.join(os.path.dirname(__file__), "..", "output", "html", "archive.html")
archive_path = os.path.abspath(archive_path)

# 扫描所有期号 JSON，提取元数据
issues = []
for fname in sorted(os.listdir(os.path.abspath(raw_dir))):
    if not fname.endswith("-weekly.json") or fname.startswith("latest"):
        continue
    path = os.path.join(os.path.abspath(raw_dir), fname)
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    date_str = d.get("date", fname[:10])
    issue_num_2 = d.get("issue", 0)
    ind_count = 0
    comp_count = 0
    for sec in d.get("sections", []):
        ind_count += len(sec.get("items", []))
        comp_count += len(sec.get("companies", []))
    html_file = f"week-{issue_num_2:02d}-{date_str}.html"
    issues.append({
        "file": html_file,
        "issue": issue_num_2,
        "date": date_str,
        "industry": ind_count,
        "company": comp_count,
    })
# 按日期倒序
issues.sort(key=lambda x: x["date"], reverse=True)

archive_html = generate_archive_html(issues)
with open(archive_path, "w", encoding="utf-8") as f:
    f.write(archive_html)
print(f"[OK] archive.html: {archive_path} ({len(issues)} 期)")
