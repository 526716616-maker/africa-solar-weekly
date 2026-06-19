"""Qwen精读输出 → HTML格式化"""
import re


def _make_list(title: str, items: list) -> str:
    if not items:
        return '<p class="mb"><strong>' + title + '</strong></p>'
    html = '<p class="mb"><strong>' + title + '</strong></p>\n<ul class="bullets">\n'
    for item in items:
        html += '<li>' + item + '</li>\n'
    html += '</ul>'
    return html


def _split_clean(text: str) -> list:
    """将一段文本拆成列表项"""
    items = [x.strip() for x in re.split(r'[，,、；;]\s*|\s{2,}', text) if len(x.strip()) >= 2]
    if len(items) <= 1:
        items = [x.strip() for x in text.split() if len(x.strip()) >= 2]
    return items


def format_rich(text: str) -> str:
    # === 第0步：统一 emoji 标记 → 中文标记 ===
    for emoji in ['\U0001F4CD', '\U0001F4CC', '\U0001F4A1', '\U0001F4C8']:
        text = text.replace(emoji, '')
    text = re.sub(r'(?<!\w)背景[：:]', '\n【问题】\n', text)
    text = re.sub(r'(?<!\w)方案[：:]', '\n【方案】\n', text)
    text = re.sub(r'(?<!\w)价值[：:]', '\n【价值】\n', text)
    text = re.sub(r'(?<!\w)趋势[：:]\s*(?!总结)', '\n【趋势】\n', text)

    # === 第1步：统一标记 ===
    text = re.sub(r'【问题】\s*', '\n【问题】\n', text)
    text = re.sub(r'【方案】\s*', '\n【方案】\n', text)
    text = re.sub(r'【价值】\s*', '\n【价值】\n', text)
    text = re.sub(r'【趋势】\s*', '\n【趋势】\n', text)
    text = re.sub(r'(背景[：:]|该地区长期面临[：:])', '\n【问题】\n', text)
    text = re.sub(r'(方案[：:]|可实[现行][：:]|已实[现行][：:])', '\n【方案】\n', text)
    text = re.sub(r'(价值[：:]|项目重点价值[：:]|项目价值[：:])', '\n【价值】\n', text)
    text = re.sub(r'(趋势总结|行业趋势|趋势[：:]|该案例代表)', '\n【趋势】\n', text)

    # === 第2步：分行为列表 ===
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return '<p class="mb">' + text + '</p>'

    # === 第3步：- / ● bullet 格式 ===
    if any(l.startswith('- ') or l.startswith('\u25cf ') for l in lines):
        result = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith('- ') or line.startswith('\u25cf '):
                prefix_len = 2
                items = []
                while i < len(lines) and lines[i].startswith(line[0] + ' '):
                    items.append(lines[i][prefix_len:])
                    i += 1
                result.append('<ul class="bullets">')
                for item in items:
                    result.append('<li>' + item + '</li>')
                result.append('</ul>')
            else:
                # 如果下一行是 bullet，当前行可能是 section header → 切换中文标题
                if i + 1 < len(lines) and lines[i+1][:2] in ('- ', '\u25cf '):
                    title_labels = {
                        '【问题】': '该地区长期面临：',
                        '【方案】': '解决方案：',
                        '【价值】': '项目价值：',
                        '【趋势】': '行业趋势：',
                        '背景：': '该地区长期面临：',
                        '方案：': '解决方案：',
                        '价值：': '项目价值：',
                        '趋势总结：': '行业趋势：',
                    }
                    label = title_labels.get(line, line)
                    result.append('<p class="mb"><strong>' + label + '</strong></p>')
                else:
                    result.append('<p class="mb">' + line + '</p>')
                i += 1
        return '\n'.join(result)

    # === 第4步：【标记】格式——相邻行合并 ===
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # 检查是否标记行
        marker = None
        for m in ['【问题】', '【方案】', '【价值】', '【趋势】']:
            if m in line:
                marker = m
                break

        if marker:
            # 提取内容：标记行剩余部分 + 可能的下一行
            content = line.replace(marker, '').strip()
            # 如果下一行非标记行，作为内容的一部分
            if not content and i + 1 < len(lines) and not any(m2 in lines[i+1] for m2 in ['【问题】', '【方案】', '【价值】', '【趋势】']):
                content = lines[i+1]
                i += 1  # 消费下一行

            if marker == '【趋势】':
                content = content.lstrip('：: ').strip()
                if content:
                    result.append('<p class="mb"><strong>行业趋势：</strong></p>')
                    result.append('<p class="mb">' + content + '</p>')
            else:
                title_map = {
                    '【问题】': '该地区长期面临：',
                    '【方案】': '解决方案：',
                    '【价值】': '项目价值：',
                }
                title = title_map[marker]
                if content:
                    items = _split_clean(content)
                    result.append(_make_list(title, items))
                else:
                    result.append('<p class="mb"><strong>' + title + '</strong></p>')
        else:
            result.append('<p class="mb">' + line + '</p>')
        i += 1

    return '\n'.join(result)
