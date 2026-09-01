"""
post_process.py
将 AI 生成的 book.md 转换为精美的 book.html，
并将 SCREENSHOT 占位符替换为嵌入式视频播放器卡片。
"""
import argparse
import os
import re
import urllib.parse as urlparse
import markdown

# ─────────────────────────────────────────────
# 平台检测与 ID 提取
# ─────────────────────────────────────────────

def detect_platform(video_url: str) -> str:
    """检测视频来源平台"""
    if "youtube.com" in video_url or "youtu.be" in video_url:
        return "youtube"
    elif "bilibili.com" in video_url:
        return "bilibili"
    return "unknown"

def extract_youtube_id(url: str) -> str:
    parsed = urlparse.urlparse(url)
    if "youtube.com" in parsed.netloc:
        return urlparse.parse_qs(parsed.query).get("v", [None])[0]
    elif "youtu.be" in parsed.netloc:
        return parsed.path[1:]
    return None

def extract_bilibili_bvid(url: str) -> str:
    match = re.search(r'(BV[a-zA-Z0-9]+)', url)
    return match.group(1) if match else None

def timestamp_to_seconds(ts: str) -> int:
    """将 HH:MM:SS 或 HH:MM:SS.xxx 转为整数秒"""
    ts = ts.split('.')[0]  # 去掉毫秒
    parts = ts.split(':')
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return 0

# ─────────────────────────────────────────────
# 嵌入式视频卡片生成
# ─────────────────────────────────────────────

def make_video_card(platform: str, video_id: str, video_url: str, timestamp: str, description: str, image_rel: str = None) -> str:
    """根据平台生成嵌入式视频播放器 HTML 卡片"""
    seconds = timestamp_to_seconds(timestamp)

    # 若已提供页内截图，则渲染静态截图卡片（真·截图模式）
    if image_rel:
        return f'''<div class="video-card screenshot-card">
  <img src="{image_rel}" alt="{description}" loading="lazy">
  <p class="video-caption">📷 {description}<br><a href="{video_url}?t={seconds}" target="_blank" rel="noopener">在 B 站中打开 ({timestamp})</a></p>
</div>'''

    if platform == "youtube":
        # 使用 nocookie 域名 + 清洁参数，尽可能隐藏悬浮 UI
        embed_url = f"https://www.youtube-nocookie.com/embed/{video_id}?start={seconds}&rel=0&modestbranding=1&iv_load_policy=3&showinfo=0&controls=1&playsinline=1&cc_load_policy=0"
        open_url = f"https://www.youtube.com/watch?v={video_id}&t={seconds}s"
        return f'''<div class="video-card youtube-card">
  <div class="video-wrapper">
    <iframe src="{embed_url}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen loading="lazy"></iframe>
  </div>
  <p class="video-caption">▶ {description}<br><a href="{open_url}" target="_blank" rel="noopener">在 YouTube 中打开 ({timestamp})</a></p>
</div>'''

    elif platform == "bilibili":
        embed_url = f"https://player.bilibili.com/player.html?bvid={video_id}&t={seconds}&autoplay=0&high_quality=1"
        return f'''<div class="video-card">
  <div class="video-wrapper">
    <iframe src="{embed_url}" frameborder="0" allowfullscreen scrolling="no" loading="lazy"></iframe>
  </div>
  <p class="video-caption">▶ {description}<br><a href="{video_url}?t={seconds}" target="_blank" rel="noopener">在 B 站中打开 ({timestamp})</a></p>
</div>'''

    # 未知平台，返回纯文本提示
    return f'<div class="video-card fallback"><p>⚠️ 视频参考：{description}（{timestamp}）—— <a href="{video_url}" target="_blank">{video_url}</a></p></div>'


# ─────────────────────────────────────────────
# Markdown → HTML 转换
# ─────────────────────────────────────────────

def replace_screenshots_with_embeds(md_content: str, video_url: str, images_dir: str = None) -> str:
    """将 Markdown 中的 ![desc](SCREENSHOT:HH:MM:SS) 替换为 HTML 视频卡片"""
    platform = detect_platform(video_url)
    video_id = None
    if platform == "youtube":
        video_id = extract_youtube_id(video_url)
    elif platform == "bilibili":
        video_id = extract_bilibili_bvid(video_url)

    # 匹配 ![任意描述](SCREENSHOT:HH:MM:SS) 或 ![任意描述](SCREENSHOT:HH:MM:SS.xxx)
    # 匹配两种形态：
    #   1) 占位符 ![描述](SCREENSHOT:HH:MM:SS[.xxx])
    #   2) 已物化图片链接 ![描述](images/shot_HH_MM_SS.png) 或 ![描述](shot_HH_MM_SS.png)
    pattern = (
        r'!\[([^\]]*)\]\('
        r'(?:SCREENSHOT:(\d{2}:\d{2}:\d{2}(?:\.\d+)?)'
        r'|(?:images/)?shot_(\d{2})_(\d{2})_(\d{2})\.png'
        r')\)'
    )

    def replacer(match):
        desc = match.group(1)
        if match.group(2):
            ts = match.group(2).split('.')[0]
        else:
            ts = ":".join(match.group(i) for i in (3, 4, 5))
        image_rel = None
        if images_dir:
            fname = "shot_" + ts.split('.')[0].replace(":", "_") + ".png"
            if os.path.exists(os.path.join(images_dir, fname)):
                image_rel = "images/" + fname
        return make_video_card(platform, video_id, video_url, ts, desc, image_rel=image_rel)

    return re.sub(pattern, replacer, md_content)


def md_to_html(md_content: str, title: str) -> str:
    """将 Markdown 内容转为完整的 HTML 页面"""
    # 先将 markdown 转为 HTML 片段
    body_html = markdown.markdown(
        md_content,
        extensions=['tables', 'fenced_code', 'codehilite', 'toc'],
        extension_configs={
            'codehilite': {'css_class': 'highlight', 'guess_lang': False}
        }
    )

    return HTML_TEMPLATE.replace("{title}", title).replace("{content}", body_html)


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────

def process_markdown(video_url: str, md_file: str):
    if not os.path.exists(md_file):
        print(f"[ERR] 找不到文件: {md_file}")
        return

    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 从 MD 第一行提取标题
    title_match = re.search(r'^#\s+(.+)', content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "VideoBook"

    # 1) 将 SCREENSHOT 占位符替换为嵌入式视频卡片 HTML
    print(">> 正在将截图占位符替换为嵌入式视频播放器...")
    screenshot_pattern = (
        r'!\[[^\]]*\]\((?:SCREENSHOT:\d{2}:\d{2}:\d{2}(?:\.\d+)?'
        r'|(?:images/)?shot_\d{2}_\d{2}_\d{2}\.png)\)'
    )
    count = len(re.findall(screenshot_pattern, content))

    if count > 0:
        content = replace_screenshots_with_embeds(content, video_url, images_dir=os.path.join(os.path.dirname(os.path.abspath(md_file)), "images"))
        print(f">> 已替换 {count} 处截图为视频播放器卡片")
    else:
        print(">> 未发现截图占位符，直接转换")

    # 2) 将 Markdown 转为精美的 HTML
    print(">> 正在生成 HTML 电子书...")
    html_output = md_to_html(content, title)

    # 3) 保存 HTML 文件
    html_file = md_file.replace('.md', '.html')
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_output)

    print(f"\n[OK] 电子书已生成: {html_file}")
    print(f"   请在浏览器中打开此文件阅读！")


def main():
    parser = argparse.ArgumentParser(description="将 book.md 转换为精美的 book.html 电子书")
    parser.add_argument("video_url", help="原始视频的 URL")
    parser.add_argument("md_file", help="待转换的 Markdown 文件路径")
    args = parser.parse_args()

    process_markdown(args.video_url, args.md_file)


# ─────────────────────────────────────────────
# HTML 模板与 CSS 样式
# ─────────────────────────────────────────────

HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Serif+SC:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        /* ── 基础重置 ── */
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --bg-primary: #0f0f11;
            --bg-secondary: #1a1a1f;
            --bg-card: #22222a;
            --bg-code: #2a2a35;
            --text-primary: #e8e6e3;
            --text-secondary: #9a9a9f;
            --text-muted: #6a6a6f;
            --accent: #6c8cff;
            --accent-glow: rgba(108, 140, 255, 0.15);
            --border: #2e2e36;
            --border-subtle: #252530;
            --radius: 12px;
            --shadow: 0 4px 24px rgba(0,0,0,0.3);
        }

        html {
            scroll-behavior: smooth;
        }

        body {
            font-family: 'Inter', 'Noto Serif SC', -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.8;
            font-size: 16px;
            -webkit-font-smoothing: antialiased;
        }

        /* ── 文章容器 ── */
        .book-content {
            max-width: 780px;
            margin: 0 auto;
            padding: 60px 32px 120px;
        }

        /* ── 标题 ── */
        h1 {
            font-size: 2.2em;
            font-weight: 700;
            margin: 0 0 12px;
            background: linear-gradient(135deg, #6c8cff 0%, #a78bfa 50%, #f472b6 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            letter-spacing: -0.02em;
        }

        h2 {
            font-size: 1.5em;
            font-weight: 600;
            color: var(--text-primary);
            margin: 56px 0 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid var(--border);
        }

        h3 {
            font-size: 1.2em;
            font-weight: 600;
            color: var(--accent);
            margin: 36px 0 12px;
        }

        /* ── 段落与文字 ── */
        p {
            margin: 0 0 16px;
            color: var(--text-primary);
        }

        strong {
            color: #fff;
            font-weight: 600;
        }

        em {
            color: var(--text-secondary);
            font-style: italic;
        }

        a {
            color: var(--accent);
            text-decoration: none;
            border-bottom: 1px solid transparent;
            transition: border-color 0.2s;
        }
        a:hover {
            border-bottom-color: var(--accent);
        }

        /* ── 引用 ── */
        blockquote {
            margin: 24px 0;
            padding: 16px 20px;
            background: var(--bg-secondary);
            border-left: 3px solid var(--accent);
            border-radius: 0 var(--radius) var(--radius) 0;
            color: var(--text-secondary);
        }
        blockquote p { margin: 0; }

        /* ── 列表 ── */
        ul, ol {
            margin: 12px 0 20px 24px;
            color: var(--text-primary);
        }
        li {
            margin: 6px 0;
        }

        /* ── 分割线 ── */
        hr {
            border: none;
            height: 1px;
            background: linear-gradient(90deg, transparent, var(--border), transparent);
            margin: 48px 0;
        }

        /* ── 表格 ── */
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            margin: 24px 0;
            border-radius: var(--radius);
            overflow: hidden;
            box-shadow: var(--shadow);
        }
        thead {
            background: var(--bg-card);
        }
        th {
            padding: 12px 16px;
            font-weight: 600;
            text-align: left;
            color: var(--accent);
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        td {
            padding: 12px 16px;
            border-top: 1px solid var(--border-subtle);
        }
        tbody tr {
            background: var(--bg-secondary);
            transition: background 0.15s;
        }
        tbody tr:hover {
            background: var(--bg-card);
        }

        /* ── 代码 ── */
        code {
            font-family: 'JetBrains Mono', monospace;
            background: var(--bg-code);
            padding: 2px 7px;
            border-radius: 5px;
            font-size: 0.88em;
            color: #e0b0ff;
        }

        pre {
            margin: 20px 0;
            padding: 20px 24px;
            background: var(--bg-code);
            border-radius: var(--radius);
            overflow-x: auto;
            border: 1px solid var(--border);
        }
        pre code {
            background: none;
            padding: 0;
            font-size: 0.9em;
            color: var(--text-primary);
        }

        /* ── 视频嵌入卡片 ── */
        .video-card {
            margin: 32px 0;
            border-radius: var(--radius);
            overflow: hidden;
            background: var(--bg-card);
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .video-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
        }

        .video-wrapper {
            position: relative;
            padding-bottom: 56.25%; /* 16:9 */
            height: 0;
            overflow: hidden;
        }
        .video-wrapper iframe {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
        }

        .video-card img {
            width: 100%;
            display: block;
        }

        .video-caption {
            padding: 12px 16px;
            font-size: 0.88em;
            color: var(--text-secondary);
            text-align: center;
            line-height: 1.6;
            margin: 0;
        }
        .video-caption a {
            color: var(--accent);
        }

        .video-card.fallback {
            padding: 20px;
            text-align: center;
        }

        /* ── Lightbox：截图点击放大 ── */
        .screenshot-card img { cursor: zoom-in; transition: opacity 0.15s; }
        .screenshot-card img:hover { opacity: 0.9; }
        .lightbox {
            position: fixed; inset: 0; z-index: 999;
            display: none; align-items: center; justify-content: center;
            background: rgba(5, 5, 8, 0.92); backdrop-filter: blur(4px);
            cursor: zoom-out; padding: 24px;
        }
        .lightbox.open { display: flex; }
        .lightbox img {
            max-width: 96vw; max-height: 90vh;
            border-radius: 8px; box-shadow: 0 12px 60px rgba(0,0,0,0.7);
        }
        .lightbox-caption {
            position: absolute; bottom: 14px; left: 0; right: 0;
            text-align: center; color: var(--text-secondary); font-size: 0.85em;
        }

        /* ── 顶部信息栏 ── */
        .book-content > blockquote:first-of-type {
            background: var(--accent-glow);
            border-left-color: var(--accent);
            border-radius: var(--radius);
            margin-bottom: 32px;
        }

        /* ── 图表居中 ── */
        .mermaid {
            display: flex;
            justify-content: center;
            margin: 32px 0;
            overflow-x: auto;
        }

        /* ── 滚动条 ── */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

        /* ── 响应式 ── */
        @media (max-width: 640px) {
            .book-content { padding: 32px 16px 80px; }
            h1 { font-size: 1.7em; }
            h2 { font-size: 1.3em; }
        }
    </style>
</head>
<body>
    <article class="book-content">
        {content}
    </article>

    <!-- Mermaid 图表引擎初始化 -->
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.min.js"></script>
    <script>
        document.addEventListener("DOMContentLoaded", function() {
            mermaid.initialize({ startOnLoad: false, theme: 'dark' });
            
            // 兼容普通代码块以及丢失 language-mermaid 类名的情况 (CodeHilite 干扰)
            const codeNodes = document.querySelectorAll('pre code, .highlight code');
            codeNodes.forEach(function(node) {
                const text = node.textContent.trim();
                // 匹配常见的 mermaid 图表前缀
                if (text.startsWith('graph ') || text.startsWith('sequenceDiagram') || text.startsWith('gantt') || text.startsWith('pie') || text.startsWith('classDiagram') || text.startsWith('stateDiagram') || text.startsWith('mindmap')) {
                    const tempDiv = document.createElement('div');
                    tempDiv.className = 'mermaid';
                    tempDiv.textContent = text;
                    
                    // 获取需要替换的最外层父节点 (比如 div.highlight 或者 pre)
                    const wrapper = node.closest('.highlight') || node.parentNode;
                    wrapper.replaceWith(tempDiv); 
                }
            });
            
            // 所有节点转换完成，统一进行图表动态绘制
            mermaid.run();
        });
    </script>
    <!-- Lightbox：截图点击放大 -->
    <script>
        document.addEventListener("DOMContentLoaded", function() {
            const lightbox = document.createElement('div');
            lightbox.className = 'lightbox';
            lightbox.innerHTML = '<img alt=""><div class="lightbox-caption"></div>';
            document.body.appendChild(lightbox);
            const lbImg = lightbox.querySelector('img');
            const lbCap = lightbox.querySelector('.lightbox-caption');
            function openLightbox(src, alt) {
                lbImg.src = src; lbImg.alt = alt || '';
                lbCap.textContent = alt || '';
                lightbox.classList.add('open');
                document.body.style.overflow = 'hidden';
            }
            function closeLightbox() {
                lightbox.classList.remove('open');
                lbImg.src = '';
                document.body.style.overflow = '';
            }
            document.querySelectorAll('.screenshot-card img').forEach(function(img) {
                img.addEventListener('click', function() { openLightbox(img.src, img.alt); });
            });
            lightbox.addEventListener('click', closeLightbox);
            document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeLightbox(); });
        });
    </script>
</body>
</html>
'''

if __name__ == "__main__":
    main()
