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
