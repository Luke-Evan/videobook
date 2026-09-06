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

  v2 pipeline layers (see README "截帧管线 v2"):
    A 启动层   headless 优先，失败回退 headful；不弹窗打扰。
    B 探针层   抓取前查询 playurl，取顶档原生分辨率，viewport 1:1 设置（不自嗨放大）。
    C 流锁定层 路由拦截 playurl 响应，只保留顶档最高码率变体（优先 AVC），
              根除"自动档从 360P 起播、暂停冻结升档"导致的糊图。
    D 页面层   默认嵌入播放器 player.html（轻量）；video 选择器超时自动降级主站观看页。
    E 截帧层   seek(t) -> await seeked -> pause -> <video> 元素截图；
              visibility CSS 隐藏一切非 video 元素（顶栏/控制栏/引流条/推荐层/黑边 UI）。
    F QA 层    截图文件过小视为黑帧，偏移 +2s 自动重试一次。

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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PROFILE_DIR = os.path.join(BASE_DIR, ".capture-profile")

# E 层：除 <video> 外全部隐藏（visibility 保留布局，通杀各遮挡层）
HIDE_CSS = ("body *{visibility:hidden!important}"
            "video, video *{visibility:visible!important}")

# F 层：纯黑/空帧 PNG 压缩后极小，真实 lecture 帧通常 > 50KB
MIN_SHOT_BYTES = 10000


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


def build_main_url(platform: str, video_id: str, sec: int) -> str:
    """D 层兜底页面：主站观看页。"""
    if platform == "bilibili":
        return f"https://www.bilibili.com/video/{video_id}/?t={sec}"
    return f"https://www.youtube.com/watch?v={video_id}&t={sec}s"


def parse_timestamps(source_md: str):
    with open(source_md, encoding="utf-8") as f:
        content = f.read()
    return sorted(set(re.findall(r"SCREENSHOT:(\d{2}:\d{2}:\d{2})", content)))


def shots_spec(timestamps, platform, video_id):
    """Build [seconds, image-name, embed-url, main-url] rows."""
    shots = []
    for ts in timestamps:
        h, m, s = (int(x) for x in ts.split(":"))
        sec = h * 3600 + m * 60 + s
        shots.append([sec, "shot_" + ts.replace(":", "_"),
                      build_url(platform, video_id, sec),
                      build_main_url(platform, video_id, sec)])
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
        candidates.append("/Applications/Google Chrome.app/Contents/Google Chrome")
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


# ─────────────────────────────────────────────
# v2 pipeline internals
# ─────────────────────────────────────────────

def _force_top_quality(page):
    """C 层：拦截 playurl，只留顶档最高码率变体（优先 AVC 兼容性）。"""
    def handle(route):
        resp = route.fetch()
        try:
            j = resp.json()
            vids = j["data"]["dash"]["video"]
            top = max(v["id"] for v in vids)
            cands = [v for v in vids if v["id"] == top]
            avc = [v for v in cands if v["codecs"].startswith("avc")] or cands
            j["data"]["dash"]["video"] = [max(avc, key=lambda v: v["bandwidth"])]
            route.fulfill(response=resp, json=j)
        except Exception:
            route.fulfill(response=resp)
    page.route("**/*playurl*", handle)


def _probe_native_size(page, video_id):
    """B 层：查询顶档原生分辨率 [w,h]，用于 1:1 viewport。"""
    try:
        return page.evaluate("""async (bvid) => {
            const cid = (await (await fetch('https://api.bilibili.com/x/web-interface/view?bvid=' + bvid)).json()).data.cid;
            const d = (await (await fetch('https://api.bilibili.com/x/player/playurl?bvid=' + bvid + '&cid=' + cid + '&qn=120&fnval=4048', {credentials:'include'})).json()).data;
            const vids = ((d || {}).dash || {}).video || [];
            if (!vids.length) return null;
            const top = Math.max.apply(null, vids.map(v => v.id));
            const v = vids.filter(x => x.id === top).sort((a, b) => b.bandwidth - a.bandwidth)[0];
            return [v.width, v.height];
        }""", video_id)
    except Exception:
        return None


def _shoot(page, sec, name, imgdir, urls):
    """D+E+F 层：embed 优先/主站兜底；精确 seek+pause；元素截图；黑帧重试。"""
    loaded = False
    for url in urls:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_selector("video", timeout=20000)
            loaded = True
            break
        except Exception:
            continue
    if not loaded:
        return False
    page.add_style_tag(content=HIDE_CSS)
    page.evaluate("""async (sec) => {
        const v = document.querySelector('video');
        v.muted = true;
        await new Promise(r => (v.readyState >= 2) ? r() : v.addEventListener('loadeddata', r, {once:true}));
        v.currentTime = sec;
        await new Promise(r => v.addEventListener('seeked', r, {once:true}));
        v.pause();
    }""", sec)
    page.wait_for_timeout(500)
    page.add_style_tag(content=HIDE_CSS)
    path = os.path.join(imgdir, name + ".png")
    page.locator("video").screenshot(path=path)
    if os.path.getsize(path) < MIN_SHOT_BYTES:
        print("  QA: black frame detected, retry at +2s")
        page.evaluate("""async (sec) => {
            const v = document.querySelector('video');
            v.currentTime = sec + 2;
            await new Promise(r => v.addEventListener('seeked', r, {once:true}));
            v.pause();
        }""", sec)
        page.wait_for_timeout(500)
        page.locator("video").screenshot(path=path)
    print("saved", name + ".png")
    return True


def _run_capture(p, shots, imgdir, profile_dir, video_id, platform, headless):
    ctx = p.chromium.launch_persistent_context(
        profile_dir, channel="chrome", headless=headless,
        viewport={"width": 1280, "height": 720},
        args=["--autoplay-policy=no-user-gesture-required"])
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _force_top_quality(page)
        if platform == "bilibili":
            page.goto("https://www.bilibili.com", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1000)
            dims = _probe_native_size(page, video_id)
            if dims:
                print(f">> native stream size: {dims[0]}x{dims[1]} (viewport 1:1)")
                page.set_viewport_size({"width": dims[0], "height": dims[1]})
        ok_all = True
        for sec, name, embed, main in shots:
            if not _shoot(page, sec, name, imgdir, [embed, main]):
                print("  warning: capture failed for", name)
                ok_all = False
        return ok_all
    finally:
        ctx.close()


def try_dedicated(shots, imgdir, profile_dir, video_id="", platform=""):
    """Capture with the dedicated logged-in profile via Playwright (v2 pipeline)."""
    if not os.path.isdir(profile_dir) or not os.listdir(profile_dir):
        return "unavailable: capture profile not initialized (run: python capture_frames.py --setup-profile)"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "unavailable: Playwright not installed (python -m pip install playwright)"
    last_err = None
    for headless in (True, False):  # A 层：headless 优先，回退 headful
        try:
            with sync_playwright() as p:
                _run_capture(p, shots, imgdir, profile_dir, video_id, platform, headless)
            return None
        except Exception as e:
            last_err = f"headless={headless} failed: {e}"
    return last_err


METHOD_ORDER = ["dedicated"]
METHOD_DESC = {
    "dedicated": "dedicated capture profile (v2: headless, forced top quality, native size, precise seek)",
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

    if args.video_id:
        platform = detect_platform(args.video_id, args.video_url)
        if not platform:
            sys.exit("unsupported platform: pass the video url as 2nd arg")
    else:
        platform = ""

    if not args.video_id:
        ap.error("video_id is required (unless using --setup-profile)")

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

    missing = frames_missing(timestamps, imgdir)
    if not missing:
        print("all frames present; nothing to capture")
        materialize(book, tagged, imgdir)
        return
    shots = shots_spec(missing, platform, args.video_id)
    print(f">> {len(missing)} frame(s) to capture")
    order = METHOD_ORDER if args.method == "auto" else [args.method]
    used = None
    for name in order:
        print(f"\n>>> trying [{name}] {METHOD_DESC[name]}")
        err = try_dedicated(shots, imgdir, args.profile_dir, args.video_id, platform)
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

