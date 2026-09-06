import json
import os
import re
import subprocess
import sys
import urllib.parse as urlparse
import urllib.request
import glob
import shutil
from typing import Dict, Any, List
import webvtt

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None

# 避免 Windows gbk 控制台打印 emoji/中文时崩溃（反思项 3）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

try:
    from login_utils import export_cookies, DEFAULT_PROFILE_DIR, has_login_cookie
except ImportError:  # 作为 skills 包被导入时兜底
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from login_utils import export_cookies, DEFAULT_PROFILE_DIR, has_login_cookie

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def extract_youtube_id(url: str) -> str:
    """从 YouTube URL 中提取 Video ID"""
    parsed = urlparse.urlparse(url)
    if "youtube.com" in parsed.netloc:
        qs = urlparse.parse_qs(parsed.query)
        return qs.get("v", [None])[0]
    elif "youtu.be" in parsed.netloc:
        return parsed.path[1:]
    return None


def fetch_via_transcript_api(video_id: str) -> List[Dict[str, Any]]:
    """使用 youtube-transcript-api 获取字幕（兼容新版实例化 API）"""
    if not YouTubeTranscriptApi:
        raise ImportError("youtube-transcript-api is not installed")

    ytt_api = YouTubeTranscriptApi()
    try:
        transcript = ytt_api.fetch(video_id, languages=['zh-CN', 'zh', 'zh-Hans', 'zh-Hant', 'en', 'en-US'])
        return transcript.to_raw_data()
    except Exception:
        pass
    try:
        transcript = ytt_api.fetch(video_id)
        return transcript.to_raw_data()
    except Exception as e:
        raise ValueError(f"无法获取任何可用字幕，详情: {e}")


def convert_vtt_to_json(vtt_file: str) -> List[Dict[str, Any]]:
    """解析 VTT 内容到统一 JSON 格式"""
    results = []
    for caption in webvtt.read(vtt_file):
        text = caption.text.strip().replace('\n', ' ')
        if not text:
            continue
        results.append({"start": caption.start, "end": caption.end, "text": text})
    return results


def convert_srt_to_json(srt_file: str) -> List[Dict[str, Any]]:
    """原生解析 SRT（反思项 5：不再依赖 ffmpeg 做 vtt 转换）"""
    def ts(t):
        h, m, rest = t.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    results = []
    blocks = re.split(r"\n\s*\n", open(srt_file, encoding="utf-8-sig").read().strip())
    for b in blocks:
        lines = [l.strip() for l in b.splitlines() if l.strip()]
        if len(lines) < 3:
            continue
        m = re.match(r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})", lines[1])
        if not m:
            continue
        results.append({
            "start": format_timestamp(ts(m.group(1))),
            "end": format_timestamp(ts(m.group(2))),
            "text": " ".join(lines[2:]),
        })
    return results


def _lang_zh(path):
    b = os.path.basename(path)
    return any(k in b for k in (".zh", "-zh", "ai-zh", "zh-", "zh_Hans", "zh_CN"))


def _lang_en(path):
    b = os.path.basename(path)
    return any(k in b for k in (".en", "-en", "ai-en", "en-", "en_US"))


def _ffmpeg_location():
    """venv 里装了 imageio-ffmpeg 时自动提供 ffmpeg 路径（反思项 5）"""
    try:
        import imageio_ffmpeg
        return os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return None


def fetch_via_ytdlp(video_url: str, cookies_from: str = None, cookies_file: str = None) -> List[Dict[str, Any]]:
    """使用 yt-dlp 作为兜底方案获取字幕（支持 B 站等）"""
    tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp_subs")
    if os.path.exists(tmp_dir):  # 防止残留旧字幕造成假阳性
        shutil.rmtree(tmp_dir, ignore_errors=True)
    os.makedirs(tmp_dir, exist_ok=True)

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", "en.*,zh.*,ai-zh,ai-en",
        "--skip-download",
        "--sub-format", "vtt/best",
        "--no-check-certificates",
        "--ignore-errors",
        "-o", os.path.join(tmp_dir, "%(id)s.%(ext)s"),
        video_url
    ]
    loc = _ffmpeg_location()
    if loc:
        cmd.extend(["--ffmpeg-location", loc])
    if cookies_from:
        cmd.extend(["--cookies-from-browser", cookies_from])
    if cookies_file:
        cmd.extend(["--cookies", cookies_file])

    print(f">> 正在使用 yt-dlp 获取字幕...")
    sub_files = []
    proc = None
    for attempt in (1, 2):
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        sub_files = glob.glob(os.path.join(tmp_dir, "*.vtt")) + glob.glob(os.path.join(tmp_dir, "*.srt"))
        if any(_lang_zh(f) for f in sub_files) or not sub_files:
            break
        print(">> 未得到中文字幕，重试一次（瞬时错误可能被 --ignore-errors 吞掉）...")

    if not sub_files:
        stderr_msg = proc.stderr.strip() if proc.stderr else "未知错误"
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ValueError(f"yt-dlp 未能获取到任何字幕文件: {stderr_msg}")

    target = sub_files[0]
    for sf in sub_files:  # 中文优先，其次英文
        if _lang_zh(sf):
            target = sf
            break
    else:
        for sf in sub_files:
            if _lang_en(sf):
                target = sf
                break

    print(f">> 找到字幕文件: {os.path.basename(target)}")
    try:
        if target.endswith(".srt"):
            segments = convert_srt_to_json(target)
        else:
            segments = convert_vtt_to_json(target)
    finally:
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return segments


def format_timestamp(seconds_float):
    """把秒数格式化成 HH:MM:SS 字符串，便于展示"""
    try:
        seconds_float = float(seconds_float)
    except ValueError:
        return seconds_float  # 如果已经是字符串，比如来自 VTT

    m, s = divmod(int(seconds_float), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _http_json(url: str):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_chapters(video_url: str, video_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """官方章节信息（反思项 6）：YouTube 用 yt-dlp chapters；B 站用 player/v2 view_points。"""
    chs = video_info.get("chapters") or []
    if chs:
        return [{"start": format_timestamp(c.get("start_time", 0)),
                 "end": format_timestamp(c.get("end_time", 0)),
                 "title": c.get("title", "")} for c in chs]
    m = re.search(r"(BV\w+)", video_url)
    if not m:
        return []
    bvid = m.group(1)
    try:
        view = _http_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
        cid = view["data"]["cid"]
        pv = _http_json(f"https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}")
        vps = (pv.get("data") or {}).get("view_points") or []
        out = []
        for i, vp in enumerate(vps):
            out.append({
                "start": format_timestamp(vp.get("from", 0)),
                "end": format_timestamp(vps[i + 1]["from"]) if i + 1 < len(vps) else "",
                "title": vp.get("content", ""),
            })
        return out
    except Exception:
        return []


def get_transcript(video_url: str, cookies_from: str = None, cookies_file: str = None) -> Dict[str, Any]:
    """主入口：获取视频字幕并统一输出格式。

    cookies_from: yt-dlp --cookies-from-browser 的浏览器名（Windows 主 Chrome 通常不可用）。
    cookies_file: Netscape cookies 文件路径（推荐，见 login_utils.export_cookies）。
    反思项 1：B 站元数据与字幕均需登录态；未显式提供 cookies 且 .capture-profile
    可用时，预先导出临时 cookies（系统临时目录，finally 中删除）供全流程使用。
    """
    yt_id = extract_youtube_id(video_url)
    segments = None

    temp_cookies = None
    is_bili = ("bilibili.com" in video_url) or bool(re.search(r"BV\w+", video_url))
    profile_ready = (os.path.isdir(DEFAULT_PROFILE_DIR) and bool(os.listdir(DEFAULT_PROFILE_DIR)))
    if is_bili and not cookies_from and not cookies_file and profile_ready:
        try:
            temp_cookies = export_cookies()
            if has_login_cookie(temp_cookies):
                cookies_file = temp_cookies
                print(">> 已从 .capture-profile 自动导出登录态 cookies（临时文件，用完即删）")
            else:
                print(">> 专用配置无登录态，请先运行: python capture_frames.py --setup-profile")
        except Exception as e:
            print(f">> 自动导出 cookies 失败: {e}")
        if temp_cookies and not cookies_file:
            try:
                os.remove(temp_cookies)
            except OSError:
                pass
            temp_cookies = None

    try:
        def _cookie_args(extra):
            args = list(extra)
            if cookies_from:
                args.extend(["--cookies-from-browser", cookies_from])
            if cookies_file:
                args.extend(["--cookies", cookies_file])
            return args

        # 获取视频基础信息 (用 yt-dlp)
        cmd_info = [sys.executable, "-m", "yt_dlp", "-j"] + _cookie_args([]) + [video_url]
        print(f">> 正在拉取视频元数据...")
        info_proc = subprocess.run(cmd_info, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
        video_info = {}
        if info_proc.returncode == 0:
            try:
                video_info = json.loads(info_proc.stdout.splitlines()[0])
            except Exception:
                pass

        # 策略 1: YouTube 专用 API (最快)
        if yt_id:
            try:
                print(f">> 尝试使用 youtube-transcript-api 抓取...")
                raw_segments = fetch_via_transcript_api(yt_id)
                segments = []
                for seg in raw_segments:
                    segments.append({
                        "start": format_timestamp(seg['start']),
                        "end": format_timestamp(seg['start'] + seg['duration']),
                        "text": seg['text'].replace('\n', ' ')
                    })
            except Exception as e:
                print(f">> youtube-transcript-api 失败: {e}")
                segments = None

        # 策略 2: yt-dlp (B站和 YT 兜底)
        if not segments:
            try:
                segments = fetch_via_ytdlp(video_url, cookies_from, cookies_file)
            except ValueError as e:
                print(f"❌ 抓取失败: 该视频可能未提供字幕 ({e})")
                return None

        return {
            "video_url": video_url,
            "title": video_info.get("title", "Unknown Title"),
            "video_id": video_info.get("id", "Unknown_ID"),
            "duration": video_info.get("duration", 0),
            "chapters": fetch_chapters(video_url, video_info),
            "segments": segments,
        }
    finally:
        if temp_cookies and os.path.exists(temp_cookies):
            os.remove(temp_cookies)



