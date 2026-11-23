import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import post_process as pp

URL = "https://www.bilibili.com/video/BV1xx/"


def test_bilibili_page_param_in_embed():
    html = pp.make_video_card("bilibili", "BV1xx", URL + "?p=2", "00:01:00", "desc")
    assert "page=2" in html and "t=60" in html


def test_open_url_keeps_query_and_overrides_t():
    html = pp.make_video_card("bilibili", "BV1xx", URL + "?p=3&t=5", "00:02:00", "desc")
    assert "p=3" in html and "t=120" in html and "t=5&" not in html


def test_screenshot_card_keeps_anchor():
    html = pp.make_video_card("bilibili", "BV1xx", URL, "00:00:55", "d",
                              image_rel="images/shot_00_00_55.png")
    assert "images/shot_00_00_55.png" in html and "回到原视频 (00:00:55)" in html


def test_slide_card_without_anchor_has_no_link():
    html = pp.make_video_card("bilibili", "BV1xx", URL, None, "d",
                              image_rel="images/slide_005.png")
    assert "images/slide_005.png" in html and "<a " not in html


def test_replace_screenshots_shot_and_slide(tmp_path):
    img = tmp_path / "images"
    img.mkdir()
    (img / "shot_00_01_00.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (img / "slide_007.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    md = "![a](SCREENSHOT:00:01:00)\n\n![b](images/slide_007.png)\n"
    out = pp.replace_screenshots_with_embeds(md, URL, images_dir=str(img))
    assert "shot_00_01_00.png" in out and "🖼️ b" in out


def test_missing_slide_image_keeps_markdown(tmp_path):
    md = "![b](images/slide_009.png)\n"
    out = pp.replace_screenshots_with_embeds(md, URL, images_dir=str(tmp_path))
    assert out == md


def test_render_template_supports_system_dark_mode():
    html = pp.md_to_html("# 书名", "书名")
    assert "color-scheme: light dark;" in html
    assert "@media (prefers-color-scheme: dark)" in html
    assert "color: var(--text-strong);" in html
    assert "theme: prefersDark ? 'dark' : 'default'" in html


def test_meta_section_warning():
    """「后记 / 本书是如何生成的」这类元信息章节要能被识别出来（只告警，不自动删）。"""
    md = ("# 书名\n\n## 1. 第一章\n\n正文\n\n## 后记：本书是如何生成的\n\n本书由 B 站 AI 字幕…\n")
    assert pp.find_meta_sections(md) == ["后记：本书是如何生成的"]
    assert pp.find_meta_sections("# 书名\n\n## 附：官方参考与延伸阅读\n\n- 链接\n") == []


def test_ensure_footer_appends_once():
    """文末固定许可页脚（铁律 7）由流水线兜底：缺失则补，已有则不动（幂等）。"""
    md = "# 书名\n\n## 1. 第一章\n\n正文\n"
    fixed, changed = pp.ensure_footer(md)
    assert changed and "本电子书由" in fixed and fixed.endswith("*\n")
    again, changed2 = pp.ensure_footer(fixed)
    assert again == fixed and changed2 is False
