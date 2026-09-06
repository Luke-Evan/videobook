"""Fallback frame extraction: download the video source, ffmpeg extract.

Prefer capture_frames.py, which screenshots the platform player directly in
the logged-in browser (full quality, no media downloads). Use this script
only when browser capture is not possible (no Chrome, remote/headless
environment).

Usage: python extract_frames.py <video_id> [video_url]

Reads output/<video_id>/book.tagged.md (preferred, when it exists) or
book.md for SCREENSHOT:HH:MM:SS placeholders and renders each timestamp
from output/<video_id>/video_source.mp4 into
output/<video_id>/images/shot_HH_MM_SS.png (the naming post_process.py expects).

If video_source.mp4 is missing and a video_url is given, the source is
downloaded automatically with yt-dlp (best avc1 tier available without
login; pre-download a higher-quality file under the same name to skip).

After extraction the markdown is materialized: every placeholder in book.md
is replaced with a native image link ![desc](images/shot_HH_MM_SS.png), and
the original tagged draft is kept once as book.tagged.md.

The downloaded video source is a fallback-only media file. It stays on disk
after extraction so failed frames can be retried; at the end of the whole
workflow the agent asks the user whether to delete such large media files.
"""
import os
import re
import shutil
import subprocess
import sys

import imageio_ffmpeg

PLACEHOLDER = re.compile(r'!\[([^\]]*)\]\(SCREENSHOT:(\d{2}:\d{2}:\d{2})(?:\.\d+)?\)')

# 未登录可用的最高 avc1 档；登录态高清晰度可预先自行下载同名文件
DEFAULT_FORMAT = "bv*[vcodec^=avc1]/b[vcodec^=avc1]/b"


def ensure_source(src: str, video_url: str) -> None:
    """Download the video source with yt-dlp when missing."""
    if os.path.exists(src):
        return
    if not video_url:
        sys.exit(f"missing video source: {src} (pass the video url as 2nd arg to auto-download)")
    cmd = [sys.executable, "-m", "yt_dlp", "-f", DEFAULT_FORMAT, "--no-part", "-o", src, video_url]
    print("downloading video source ...")
    subprocess.run(cmd, check=True)


def materialize(book: str, tagged: str, imgdir: str) -> None:
    """Replace SCREENSHOT placeholders in book.md with image links."""
    with open(book, encoding="utf-8") as f:
        content = f.read()

    def repl(m):
        desc, ts = m.group(1), m.group(2)
        fname = "shot_" + ts.replace(":", "_") + ".png"
        if os.path.exists(os.path.join(imgdir, fname)):
            return f"![{desc}](images/{fname})"
        return m.group(0)

    new_content, n = PLACEHOLDER.subn(repl, content)
    if n == 0:
        print("materialize: book.md has no remaining placeholders")
        return
    if not os.path.exists(tagged):
        shutil.copyfile(book, tagged)
        print("backup created:", os.path.basename(tagged))
    with open(book, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_content)
    print(f"materialize: replaced {n} placeholders with image links")


def main() -> None:
    video_id = sys.argv[1] if len(sys.argv) > 1 else "BV1pb8o6yE8f"
    video_url = sys.argv[2] if len(sys.argv) > 2 else None
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vdir = os.path.join(base, "output", video_id)
    book = os.path.join(vdir, "book.md")
    tagged = os.path.join(vdir, "book.tagged.md")
    src = os.path.join(vdir, "video_source.mp4")
    imgdir = os.path.join(vdir, "images")
    os.makedirs(imgdir, exist_ok=True)

    ensure_source(src, video_url)

    source_md = tagged if os.path.exists(tagged) else book
    with open(source_md, encoding="utf-8") as f:
        content = f.read()
    timestamps = sorted(set(re.findall(r"SCREENSHOT:(\d{2}:\d{2}:\d{2})", content)))
    if not timestamps:
        sys.exit("no SCREENSHOT placeholders found in " + source_md)

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    for ts in timestamps:
        h, m, s = (int(x) for x in ts.split(":"))
        sec = h * 3600 + m * 60 + s
        out = os.path.join(imgdir, "shot_" + ts.replace(":", "_") + ".png")
        cmd = [
            ff, "-hide_banner", "-loglevel", "error",
            "-ss", str(sec), "-i", src,
            "-frames:v", "1", "-y", out,
        ]
        subprocess.run(cmd, check=True)
        print("saved", os.path.basename(out))
    print(f"DONE: {len(timestamps)} frames")

    materialize(book, tagged, imgdir)


if __name__ == "__main__":
    main()
