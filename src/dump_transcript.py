import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from skills.scraper import get_transcript
from config import get_video_dir
from login_utils import export_cookies


def _to_sec(ts):
    try:
        h, m, s = (int(x) for x in str(ts).split(":"))
        return h * 3600 + m * 60 + s
    except ValueError:
        return 0


def main():
    parser = argparse.ArgumentParser(description="提取视频字幕并输出为文本信息集")
    parser.add_argument("url", help="视频的 URL (YouTube 或 Bilibili 等)")
    parser.add_argument("--cookies-from", default=None, help="从浏览器如 chrome 中获取 cookie（Windows 主 Chrome 通常因新加密不可用）")
    parser.add_argument("--cookies-file", default=None, help="Netscape cookies 文件路径")
    parser.add_argument("--cookies-from-profile", default=None,
                        help="从专用截帧配置导出 cookies（默认 .capture-profile），如: --cookies-from-profile .capture-profile")
    args = parser.parse_args()

    cookies_file = args.cookies_file
    temp_cookies = None
    if args.cookies_from_profile:
        # 反思项 2：导出到系统临时目录，用完即删
        temp_cookies = export_cookies(args.cookies_from_profile)
        cookies_file = temp_cookies

    try:
        result = get_transcript(args.url, args.cookies_from, cookies_file)
    finally:
        if temp_cookies and os.path.exists(temp_cookies):
            os.remove(temp_cookies)

    if not result:
        print("执行失败，未能获取有效数据。")
        sys.exit(1)

    # 反思项 4：字幕覆盖率自检
    segs = result.get("segments") or []
    dur = float(result.get("duration") or 0)
    if segs and dur > 0:
        coverage = _to_sec(segs[-1]["end"]) / dur
        print(f">> 字幕覆盖率自检: {coverage:.1%}（{len(segs)} 段 / 时长 {dur:.0f}s）")
        if coverage < 0.5:
            print("❌ 覆盖率过低，疑似抓取不全（登录态缺失或字幕异常）。")
            print("   可尝试: python dump_transcript.py <url> --cookies-from-profile .capture-profile")
            sys.exit(3)

    video_id = result["video_id"]
    out_dir = get_video_dir(video_id)
    out_file = os.path.join(out_dir, "transcript.json")

    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 成功获取视频信息，Video ID: {video_id}")
    if result.get("chapters"):
        print(f"✅ 官方章节 {len(result['chapters'])} 个已写入，可供排版对齐")
    print(f"✅ 字幕数据已保存至: {out_file}")
    print(f"\nAI Agent，你可以阅读上述 JSON 文件并根据 prompts/stitcher_system.md 重新排版生成指南啦。")


if __name__ == "__main__":
    main()
