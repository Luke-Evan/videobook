import os, sys
import pytest

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


def test_web_ext_falls_back_when_encoder_probe_fails(monkeypatch):
    """features.check("avif") 为 True 但编不出来时，web_ext() 必须退回 WebP。"""
    monkeypatch.setattr(ie, "_ext", None)
    monkeypatch.setattr(ie, "_avif_encoder_usable", lambda: False)
    assert ie.web_ext() == ".webp"


def test_export_web_falls_back_to_webp_when_avif_save_fails(tmp_path, monkeypatch):
    """探测通过、实际编码失败时降级 WebP，而不是让整条流水线崩掉。"""
    monkeypatch.setattr(ie, "_ext", ".avif")  # 假装已判定 AVIF 可用
    def boom(im, dst):
        raise OSError("libavif was built without an AV1 encoder")
    monkeypatch.setattr(ie, "_save_avif", boom)
    src = tmp_path / "slide.png"
    _png(src, (3840, 2160))
    out = tmp_path / "images"
    name = ie.export_web(str(src), str(out), "slide_001")
    assert name == "slide_001.webp"
    im = Image.open(out / name)
    assert im.format == "WEBP"
    assert im.size == (ie.WEB_WIDTH, ie.WEB_WIDTH * 9 // 16)
    assert not (out / "slide_001.avif").exists()  # 不留下半截文件
    assert ie.web_ext() == ".webp"  # 结论记住，后续图片不再白试 AVIF


def test_export_web_forced_avif_raises_instead_of_changing_ext(tmp_path, monkeypatch):
    """强制扩展名时不降级：换扩展名会让 book.md 既有链接指空。"""
    monkeypatch.setattr(ie, "_ext", ".avif")
    def boom(im, dst):
        raise OSError("no encoder")
    monkeypatch.setattr(ie, "_save_avif", boom)
    src = tmp_path / "shot.png"
    _png(src, (1280, 720))
    with pytest.raises(OSError):
        ie.export_web(str(src), str(tmp_path / "images"), "shot_00_00_55", ext=".avif")
