"""PNG 母版 -> 适合网页分发的 2K AVIF（Pillow 缺 AVIF 编码时退回 WebP）。

流水线内部一律以 PNG 为母版：感知哈希比对（course_assets.dhash）、幻灯片
重跑保护、人工核对都依赖无损原图。只有最终落到 images/ 的那一份按这里的
目标宽度重新编码：4K PNG 单页常有 0.4–1.2 MB，而书里正文容器宽度只有
780px，同内容的 1920px AVIF 通常只有 30–130 KB。

调用方用 web_ext() 拿实际扩展名，不要硬编码 ".avif"；用 image_path()
按「茎名」找现有图片，这样旧书里遗留的 .png 依然能被识别。
"""
import glob
import io
import os

# PIL 故意延迟到函数内导入：publish.py 只需要 IMG_EXTS，不该为一个纯 git
# 脚本拉进 Pillow。

# 书里图片显示宽度约 716px（容器 780px - 左右 padding），1920 已是 2.7 倍
WEB_WIDTH = 1920
AVIF_QUALITY = 63
AVIF_SPEED = 6
WEBP_QUALITY = 80

# images/ 里可能出现的扩展名；.png 为历史遗留（旧书、--apply-map 沿用）
IMG_EXTS = (".png", ".avif", ".webp")
# 正则里的扩展名交替组，调用方别自己再列一遍
EXT_ALT = "|".join(e.lstrip(".") for e in IMG_EXTS)

_ext = None


def _avif_encoder_usable() -> bool:
    """Pillow 能 import avif 模块 != 能编码：libavif 若没带 AV1 编码器，
    features.check() 仍是 True 而 save() 会抛异常。真编一张 8x8 试出来：
    首次约几十毫秒（libavif 初始化），之后 1ms 级，且每进程只做一次。"""
    try:
        from PIL import Image, features

        if not features.check("avif"):
            return False
        sink = io.BytesIO()
        Image.new("RGB", (8, 8), "white").save(
            sink, "AVIF", quality=AVIF_QUALITY, speed=AVIF_SPEED)
        return sink.tell() > 0
    except Exception:
        return False


def web_ext() -> str:
    """可发布图片的扩展名：AVIF 优先，Pillow 编不出 AVIF 时退回 WebP。"""
    global _ext
    if _ext is None:
        _ext = ".avif" if _avif_encoder_usable() else ".webp"
    return _ext


def image_path(directory: str, stem: str):
    """directory 下 stem 对应的现有图片（任意受支持扩展名），没有则 None。"""
    for ext in IMG_EXTS:
        path = os.path.join(directory, stem + ext)
        if os.path.exists(path):
            return path
    return None


def list_images(directory: str, prefix: str) -> list:
    """directory 下 prefix* 的所有图片，忽略 .tmp.png 这类中间文件。"""
    return sorted(p for ext in IMG_EXTS
                  for p in glob.glob(os.path.join(directory, prefix + "*" + ext))
                  if ".tmp." not in os.path.basename(p))


def _save_avif(im, dst: str) -> None:
    # 幻灯片多为纯色文字，4:4:4 避免色边
    im.save(dst, "AVIF", quality=AVIF_QUALITY, speed=AVIF_SPEED,
            subsampling="4:4:4")


def _save_webp(im, dst: str) -> None:
    im.save(dst, "WEBP", quality=WEBP_QUALITY, method=6)


def export_web(src: str, dst_dir: str, stem: str, width: int = WEB_WIDTH,
               ext: str = None) -> str:
    """src（PNG 母版）-> dst_dir/<stem><ext>，等比缩到 width 宽，返回文件名。

    width=None 表示保留原尺寸（视频帧本来就不比 1920 大时走这条）。
    ext 不为 None 时强制用该扩展名——--apply-map 用它沿用 book.md 已引用的
    扩展名，避免升级后链接指向不存在的文件。

    未强制扩展名时，若 AVIF 运行时编码失败（探测通过但实际编不出来），
    自动降级 WebP 并记住该结论；强制扩展名时不降级——换扩展名会让
    book.md 的既有链接指空，宁可报错。
    """
    global _ext
    from PIL import Image

    forced = ext is not None
    ext = ext or web_ext()
    os.makedirs(dst_dir, exist_ok=True)
    with Image.open(src) as im:
        im = im.convert("RGB")
        if width and im.width > width:
            h = max(1, round(im.height * width / im.width))
            im = im.resize((width, h), Image.LANCZOS)
        dst = os.path.join(dst_dir, stem + ext)
        if ext == ".avif":
            try:
                _save_avif(im, dst)
            except Exception:
                if forced:
                    raise
                _ext = ".webp"  # 本机编不出 AVIF，后续别每张图都白试一次
                ext = ".webp"
                if os.path.exists(dst):
                    os.remove(dst)  # 失败时可能留下半截文件
                dst = os.path.join(dst_dir, stem + ext)
                _save_webp(im, dst)
        elif ext == ".webp":
            _save_webp(im, dst)
        else:
            # 旧书沿用 .png（--apply-map）：保持真 PNG，不拿别的编码冒充
            im.save(dst, "PNG", optimize=True)
    return os.path.basename(dst)
