import argparse
import os
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(description="VideoBook Agent 工作流向导")
    parser.add_argument("url", help="视频的 URL (YouTube 或 Bilibili 等)")
    parser.add_argument("--cookies-from", default=None, help="从浏览器如 chrome 中获取 cookie")
    args = parser.parse_args()

    print(f"\n==========================================")
    print(f"🎬 VideoBook Agent - 启动工作流")
    print(f"==========================================\n")

    print(f"[阶段 1] 抓取字幕文件...")
    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "dump_transcript.py"), args.url]
    if args.cookies_from:
        cmd.extend(["--cookies-from", args.cookies_from])
    
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\n❌ 抓取字幕失败，流程终止。")
        sys.exit(result.returncode)

    print(f"\n==========================================")
    print(f"🤖 [阶段 2] 等待 AI Agent 进行整理排版")
    print(f"==========================================")
    print(f"1. AI 助手将读取生成的 transcript.json")
    print(f"2. 根据 prompts/stitcher_system.md 将内容重新构建为 Markdown 技术指南")
    print(f"3. AI 将结果写入到 output/xxxx/book.md 文件中")
    print(f"\n如果您是直接在交互式窗口下，请指挥您的 AI 助手 (如 Claude 或 Antigravity) 去完成这步。")
    print(f"完成之后，请手动运行：")
    print(f"  python post_process.py \"{args.url}\" output/你的视频ID/book.md")

if __name__ == "__main__":
    main()
