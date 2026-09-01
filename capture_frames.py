"""Primary frame materialization: screenshots taken directly from the platform
player in a logged-in browser (high quality, from the platform).

Usage:
    python capture_frames.py --setup-profile
    python capture_frames.py <video_id> [video_url] [--method auto|dedicated]
                             [--materialize-only] [--profile-dir PATH]

Capture method (project policy, Chrome >= 136 compatible):
  dedicated  Playwright launches Chrome with a DEDICATED user-data-dir
             (<repo>/.capture-profile by default). Chrome forbids any remote
             debugging (port or pipe) on the DEFAULT user-data-dir since
             v136, so this profile is initialized once via --setup-profile:
             log in to the platforms (bilibili / YouTube) one time and the
             cookies persist for unattended captures afterwards. The dedicated
             directory does not conflict with your daily Chrome (both can run
             at the same time).

Deliberately excluded (project policy): the Codex/ChatGPT in-app browser
(separate profile, not logged in), a clean Playwright-managed Chromium
(not logged in), win32 screen capture (takes over the screen), and any remote
debugging against the DEFAULT Chrome profile (blocked by Chrome >= 136). When
running inside the Codex desktop app, prefer the ChatGPT browser extension
(@Chrome) over this script; see instructions.md.

No video or audio file is downloaded by any browser method.

After capturing, the SCREENSHOT placeholders in book.md are materialized into
images/shot_HH_MM_SS.png links (same naming post_process.py expects), and the
original tagged draft is kept as book.tagged.md.
"""
import argparse
import os
import re
import subprocess
import sys

from extract_frames import materialize

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROFILE_DIR = os.path.join(BASE_DIR, ".capture-profile")


def detect_platform(video_id: str, video_url: str) -> str:
    if video_url:
        if "youtube.com" in video_url or "youtu.be" in video_url:
            return "youtube"
        if "bilibili.com" in video_url:
            return "bilibili"
    if video_id.startswith("BV"):
        return "bilibili"
    return ""


def build_url(platform: str, video_id: str, sec: int) -> str:
    if platform == "bilibili":
        return (f"https://player.bilibili.com/player.html?bvid={video_id}"
                f"&t={sec}&autoplay=1&high_quality=1&danmaku=0")
    return f"https://www.youtube.com/embed/{video_id}?start={sec}&autoplay=1"


def parse_timestamps(source_md: str):
    with open(source_md, encoding="utf-8") as f:
        content = f.read()
    return sorted(set(re.findall(r"SCREENSHOT:(\d{2}:\d{2}:\d{2})", content)))


def shots_spec(timestamps, platform, video_id):
    """Build [seconds, image-name, player-url] rows."""
    shots = []
    for ts in timestamps:
        h, m, s = (int(x) for x in ts.split(":"))
        sec = h * 3600 + m * 60 + s
        shots.append([sec, "shot_" + ts.replace(":", "_"),
                      build_url(platform, video_id, sec)])
    return shots


def frames_missing(timestamps, imgdir):
    return [ts for ts in timestamps
            if not os.path.exists(os.path.join(imgdir, "shot_" + ts.replace(":", "_") + ".png"))]


def find_chrome_exe():
    candidates = []
    if sys.platform == "win32":
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    elif sys.platform == "darwin":
        candidates.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    else:
        import shutil
        for name in ("google-chrome", "google-chrome-stable"):
            exe = shutil.which(name)
            if exe:
                return exe
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def setup_profile(profile_dir: str, open_url: str = "https://www.bilibili.com") -> None:
    """One-time init: open Chrome with the dedicated profile for manual login."""
    exe = find_chrome_exe()
    if not exe:
        sys.exit("Chrome executable not found")
    os.makedirs(profile_dir, exist_ok=True)
    print("opening Chrome with the dedicated capture profile ...")
    print("log in to the platforms you need (bilibili / YouTube) in that window,")
    print("then CLOSE the window to finish setup.")
    subprocess.run([exe, f"--user-data-dir={profile_dir}", open_url])
    print("setup finished; cookies are persisted in", profile_dir)


def try_dedicated(shots, imgdir, profile_dir):
    """Capture with the dedicated logged-in profile via Playwright."""
    if not os.path.isdir(profile_dir) or not os.listdir(profile_dir):
        return "unavailable: capture profile not initialized (run: python capture_frames.py --setup-profile)"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "unavailable: Playwright not installed (python -m pip install playwright)"
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                profile_dir, channel="chrome", headless=False,
                args=["--start-maximized"], no_viewport=True)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    for sec, name, url in shots:
                        page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(4000)
                        page.screenshot(path=os.path.join(imgdir, name + ".png"))
                        print("saved", name + ".png")
                finally:
                    try:
                        page.close()
                    except Exception:
                        pass
            finally:
                context.close()
        return None
    except Exception as e:
        return f"failed: {e}"


METHOD_ORDER = ["dedicated"]
METHOD_DESC = {
    "dedicated": "dedicated capture profile (Playwright + one-time login)",
}


def main() -> None:
    ap = argparse.ArgumentParser(description="Capture frames directly from the platform player")
    ap.add_argument("video_id", nargs="?")
    ap.add_argument("video_url", nargs="?", default=None)
    ap.add_argument("--method", default="auto", choices=["auto"] + METHOD_ORDER)
    ap.add_argument("--materialize-only", action="store_true",
                    help="skip capture; materialize placeholders from existing images only")
    ap.add_argument("--setup-profile", action="store_true",
                    help="one-time: open Chrome with the dedicated profile to log in")
    ap.add_argument("--profile-dir", default=DEFAULT_PROFILE_DIR,
                    help="dedicated Chrome user-data-dir (default: <repo>/.capture-profile)")
    args = ap.parse_args()

    if args.setup_profile:
        setup_profile(args.profile_dir)
        return

    if not args.video_id:
        ap.error("video_id is required (unless using --setup-profile)")

    platform = detect_platform(args.video_id, args.video_url)
    if not platform:
        sys.exit("unsupported platform: pass the video url as 2nd arg")

    vdir = os.path.join(BASE_DIR, "output", args.video_id)
    book = os.path.join(vdir, "book.md")
    tagged = os.path.join(vdir, "book.tagged.md")
    imgdir = os.path.join(vdir, "images")
    os.makedirs(imgdir, exist_ok=True)

    source_md = tagged if os.path.exists(tagged) else book
    if not os.path.exists(source_md):
        sys.exit("no book markdown found: " + source_md)
    timestamps = parse_timestamps(source_md)
    if not timestamps:
        sys.exit("no SCREENSHOT placeholders found in " + source_md)

    if args.materialize_only:
        missing = frames_missing(timestamps, imgdir)
        if missing:
            print("warning: missing frames for:", ", ".join(missing))
        materialize(book, tagged, imgdir)
        return

    shots = shots_spec(timestamps, platform, args.video_id)
    order = METHOD_ORDER if args.method == "auto" else [args.method]
    used = None
    for name in order:
        print(f"\n>>> trying [{name}] {METHOD_DESC[name]}")
        err = try_dedicated(shots, imgdir, args.profile_dir)
        if err is None:
            missing = frames_missing(timestamps, imgdir)
            if not missing:
                used = name
                print(f"<<< [{name}] OK: captured {len(timestamps)} frames")
                break
            err = "finished but missing: " + ", ".join(missing)
        print(f"<<< [{name}] {err}")

    if used is None:
        sys.exit("\nAll browser capture methods failed. Use the fallback:\n"
                 f'  python extract_frames.py {args.video_id} "{args.video_url or ""}"')

    materialize(book, tagged, imgdir)


if __name__ == "__main__":
    main()