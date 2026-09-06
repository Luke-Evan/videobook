"""登录态工具：从专用截帧配置（.capture-profile）导出 cookies 供 yt-dlp 等使用。

背景：B 站字幕等接口需要登录态；而 yt-dlp --cookies-from-browser chrome 在
Windows 上因 Chrome 新版 App-Bound 加密（DPAPI v20）无法解密主 Chrome 的 cookies。
本模块改用 Playwright 直接读取专用配置的 cookie jar（登录态一次配置、长期复用），
导出为 Netscape cookies.txt。导出文件默认落在系统临时目录，由调用方用完即删。
"""
import os
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PROFILE_DIR = os.path.join(BASE_DIR, ".capture-profile")

_HOME = {
    "bilibili": "https://www.bilibili.com",
    "youtube": "https://www.youtube.com",
}


def export_cookies(profile_dir=DEFAULT_PROFILE_DIR, out_path=None, platform="bilibili"):
    """以无头 Chrome 打开平台首页激活 cookie，导出为 Netscape 格式文件。

    返回 cookies 文件路径（调用方负责删除）。若 profile 未初始化或无登录态，
    仍会导出（可能为空壳），由调用方校验关键字段（如 SESSDATA）。
    """
    from playwright.sync_api import sync_playwright

    if out_path is None:
        fd, out_path = tempfile.mkstemp(prefix="videobook_cookies_", suffix=".txt")
        os.close(fd)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile_dir, channel="chrome", headless=True)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(_HOME.get(platform, _HOME["bilibili"]),
                      wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1500)
            cookies = ctx.cookies()
        finally:
            ctx.close()

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for c in cookies:
            dom = c.get("domain", "")
            f.write("\t".join([
                dom,
                "TRUE" if dom.startswith(".") else "FALSE",
                c.get("path", "/"),
                "TRUE" if c.get("secure") else "FALSE",
                str(int(c["expires"])) if c.get("expires", -1) > 0 else "0",
                c["name"],
                c["value"],
            ]) + "\n")
    return out_path


def has_login_cookie(cookies_path, key="SESSDATA"):
    """粗略校验导出的 cookies 是否包含登录态关键字段。"""
    try:
        with open(cookies_path, encoding="utf-8") as f:
            return any("\t" + key + "\n" in line or line.rstrip().endswith(key) or f"\t{key}\t" in line for line in f)
    except OSError:
        return False
