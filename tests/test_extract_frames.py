import os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import extract_frames as ef


def fake_ffmpeg(cmd, check=True):
    """代替 ffmpeg：在 -y 指定的路径上落一张假 PNG。"""
    with open(cmd[-1], "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")


def test_extract_one_removes_tmp_after_encode(tmp_path, monkeypatch):
    """编码期间临时文件还在（导出要用它），编码完成后必须删掉。"""
    monkeypatch.setattr(ef.subprocess, "run", fake_ffmpeg)
    seen = {}

    def fake_export(src, dst_dir, stem):
        seen["src"] = src
        seen["exists_during_encode"] = os.path.exists(src)
        out = os.path.join(dst_dir, stem + ".webp")
        with open(out, "wb") as f:
            f.write(b"x")
        return os.path.basename(out)

    monkeypatch.setattr(ef, "export_web", fake_export)
    name = ef.extract_one("ffmpeg", "video.mp4", 5, "00:00:05", str(tmp_path))
    assert name == "shot_00_00_05.webp"
    assert seen["src"].endswith("shot_00_00_05.tmp.png")
    assert seen["exists_during_encode"] is True
    assert [p.name for p in tmp_path.iterdir()] == ["shot_00_00_05.webp"]


def test_extract_one_removes_tmp_when_encode_fails(tmp_path, monkeypatch):
    """编码抛异常也要删临时文件，否则 .tmp.png 会被 publish 当成成品发布。"""
    monkeypatch.setattr(ef.subprocess, "run", fake_ffmpeg)

    def boom(src, dst_dir, stem):
        raise RuntimeError("encoder exploded")

    monkeypatch.setattr(ef, "export_web", boom)
    with pytest.raises(RuntimeError):
        ef.extract_one("ffmpeg", "video.mp4", 5, "00:00:05", str(tmp_path))
    assert list(tmp_path.iterdir()) == []
