import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import image_export as ie
from PIL import Image


def _png(path, size):
    Image.new("RGB", size, "white").save(path)


def test_export_web_downscales_to_target_width(tmp_path):
    src = tmp_path / "slide.png"
    _png(src, (3840, 2160))
    out = tmp_path / "images"
    name = ie.export_web(str(src), str(out), "slide_001")
    assert name == "slide_001" + ie.web_ext()
    assert Image.open(out / name).size == (ie.WEB_WIDTH, ie.WEB_WIDTH * 9 // 16)


def test_export_web_does_not_upscale_video_frames(tmp_path):
    """视频截帧通常 <= 1920 宽，不该被放大浪费体积。"""
    src = tmp_path / "shot.png"
    _png(src, (1280, 720))
    out = tmp_path / "images"
    name = ie.export_web(str(src), str(out), "shot_00_00_55")
    assert Image.open(out / name).size == (1280, 720)


def test_export_web_forces_existing_extension(tmp_path):
    """--apply-map 沿用 book.md 已引用的扩展名，避免链接指向不存在的文件。"""
    src = tmp_path / "slide.png"
    _png(src, (3840, 2160))
    out = tmp_path / "images"
    assert ie.export_web(str(src), str(out), "shot_00_00_55", ext=".png") == "shot_00_00_55.png"
    im = Image.open(out / "shot_00_00_55.png")
    assert im.size == (ie.WEB_WIDTH, ie.WEB_WIDTH * 9 // 16)
    assert im.format == "PNG"  # 不能拿 WebP/AVIF 字节冒充 .png


def test_image_path_matches_any_supported_extension(tmp_path):
    assert ie.image_path(str(tmp_path), "slide_001") is None
    (tmp_path / "slide_001.png").write_bytes(b"x")
    assert os.path.basename(ie.image_path(str(tmp_path), "slide_001")) == "slide_001.png"
    (tmp_path / "shot_00_00_55.avif").write_bytes(b"x")
    assert os.path.basename(ie.image_path(str(tmp_path), "shot_00_00_55")) == "shot_00_00_55.avif"
