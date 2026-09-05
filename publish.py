"""将成品电子书发布到独立 orphan 分支 pages（目录名 = 视频标题）。

只发布三件套：book.html / book.md / images/*.png；不发布 transcript、srt、
tagged 稿等中间物。全程使用 git plumbing + 临时 index/工作树，不切换分支、
不触碰 main 工作区与 output/ 目录。脚本只写本地 ref，推送由执行者显式完成。

用法:
    python publish.py <video_id> [<video_id> ...]
    python publish.py --all
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

BASE = os.path.dirname(os.path.abspath(__file__))
GD = os.path.join(BASE, ".git")
PAGES = "pages"


def run(args, env=None, cwd=BASE, check=True):
    e = os.environ.copy()
    if env:
        e.update(env)
    r = subprocess.run(["git"] + args, cwd=cwd, env=e,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r


def safe_folder(title, bvid):
    """标题 → 文件系统安全目录名：/ → ／，其余非法字符删除，空白折叠。"""
    name = (title or "").strip()
    name = name.replace("/", "／")
    name = re.sub(r'[\\:*?"<>|]', "", name)
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    return name or bvid


def _src_blob_map(src):
    """源目录三件套 -> blob sha（与 add 相同过滤标准）。"""
    rels = ["book.html", "book.md"]
    img = os.path.join(src, "images")
    rels += ["images/" + f for f in sorted(os.listdir(img)) if f.lower().endswith(".png")]
    out = {}
    for rel in rels:
        r = run(["hash-object", "--", os.path.join(src, *rel.split("/"))])
        out[rel] = r.stdout.strip()
    return out


def _pages_blob_map(folder):
    """pages 分支中某目录的 relpath -> blob sha；不存在返回 {}。"""
    if not folder:
        return {}
    r = run(["-c", "core.quotePath=false", "ls-tree", "-r", PAGES, "--", folder], check=False)
    if r.returncode != 0:
        return {}
    m = {}
    for line in r.stdout.splitlines():
        meta, _, path = line.partition("\t")
        m[path[len(folder) + 1:]] = meta.split()[2]
    return m


def pages_tip():
    r = run(["rev-parse", "--verify", "--quiet", f"refs/heads/{PAGES}"], check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def read_title(video_id):
    p = os.path.join(BASE, "output", video_id, "transcript.json")
    try:
        with open(p, encoding="utf-8") as f:
            t = json.load(f).get("title", "")
        return (t or "").strip()
    except (OSError, json.JSONDecodeError):
        return ""


def build_index_html(manifest):
    rows = sorted(manifest.items(), key=lambda kv: kv[1].get("updated", ""), reverse=True)
    items = []
    for vid, meta in rows:
        href = quote(meta["folder"]) + "/book.html"
        items.append(
            f'      <li><a href="{href}">{meta["title"] or vid}</a>'
            f'<span>{meta.get("updated", "")[:10]}</span></li>')
    body = "\n".join(items) or "      <li>暂无成品</li>"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VideoBook 成品书架</title>
<style>
  body {{ background:#14161a; color:#e8eaed; font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
         max-width:760px; margin:0 auto; padding:48px 20px; }}
  h1 {{ font-size:1.5em; font-weight:600; }}
  p.sub {{ color:#9aa0a6; font-size:.9em; }}
  ul {{ list-style:none; padding:0; }}
  li {{ display:flex; justify-content:space-between; gap:16px; padding:14px 4px;
       border-bottom:1px solid #2a2d33; }}
  a {{ color:#8ab4f8; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  span {{ color:#9aa0a6; font-size:.85em; white-space:nowrap; }}
</style>
</head>
<body>
  <h1>VideoBook 成品书架</h1>
  <p class="sub">视频课程 → 图文电子书。点击标题在线阅读（含截图放大与流程图交互）。</p>
  <ul>
{body}
  </ul>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="发布成品电子书到 pages 分支")
    ap.add_argument("video_id", nargs="*", help="要发布的视频 ID（output/ 下的目录名）")
    ap.add_argument("--all", action="store_true", help="发布 output/ 下所有含 book.html 的视频")
    args = ap.parse_args()

    if args.all:
        out = os.path.join(BASE, "output")
        ids = [d for d in sorted(os.listdir(out))
               if os.path.isfile(os.path.join(out, d, "book.html"))]
    else:
        ids = args.video_id
    if not ids:
        sys.exit("没有可发布的视频：请提供 video_id 或使用 --all")

    for vid in ids:
        if not os.path.isfile(os.path.join(BASE, "output", vid, "book.html")):
            sys.exit(f"output/{vid}/book.html 不存在，先完成渲染步骤")

    tip = pages_tip()
    tmp = tempfile.mkdtemp(prefix="videobook_publish_")
    env = {"GIT_INDEX_FILE": tmp + ".index"}  # 索引文件必须在工作树之外，否则会被 add 进提交
    g = lambda *a, **k: run(list(a), env=env, **k)

    try:
        # 1) 临时 index 装载旧 pages 树（若有），并物化到临时工作树
        if tip:
            g("--git-dir", GD, "--work-tree", tmp, "read-tree", PAGES)
            g("--git-dir", GD, "--work-tree", tmp, "checkout-index", "-a", check=False)
        else:
            g("--git-dir", GD, "--work-tree", tmp, "read-tree", "--empty")
        # 清理历史误提交进树的索引残留文件
        for stray in ("index", "index.lock"):
            p = os.path.join(tmp, stray)
            if os.path.isfile(p):
                os.remove(p)

        # 2) 读旧 manifest
        manifest = {}
        if tip:
            r = run(["show", f"{PAGES}:manifest.json"], check=False)
            if r.returncode == 0:
                try:
                    manifest = json.loads(r.stdout)
                except json.JSONDecodeError:
                    manifest = {}

        now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")

        # 3) 规划目录名、处理改名与冲突
        for vid in ids:
            title = read_title(vid)
            folder = safe_folder(title, vid)
            others = {k: v.get("folder") for k, v in manifest.items() if k != vid}
            if folder in others.values():
                folder = f"{folder} ({vid})"
            old = manifest.get(vid, {}).get("folder")
            src = os.path.join(BASE, "output", vid)
            dst = os.path.join(tmp, folder)

            # 4) 内容未变且目录未改名：保持原发布（含原 updated），保证幂等
            if old == folder and _pages_blob_map(old) == _src_blob_map(src):
                manifest[vid] = {"folder": folder, "title": title,
                                 "updated": manifest[vid].get("updated", now)}
                print(f">> {vid}: 内容无变化，保持原发布")
                continue

            if old and old != folder:
                shutil.rmtree(os.path.join(tmp, old), ignore_errors=True)
                print(f">> {vid}: 目录改名 {old} -> {folder}")
            manifest[vid] = {"folder": folder, "title": title, "updated": now}

            # 5) 复制三件套到临时工作树
            shutil.rmtree(dst, ignore_errors=True)
            os.makedirs(os.path.join(dst, "images"))
            shutil.copyfile(os.path.join(src, "book.html"), os.path.join(dst, "book.html"))
            shutil.copyfile(os.path.join(src, "book.md"), os.path.join(dst, "book.md"))
            n = 0
            for fn in sorted(os.listdir(os.path.join(src, "images"))):
                if fn.lower().endswith(".png"):
                    shutil.copyfile(os.path.join(src, "images", fn),
                                    os.path.join(dst, "images", fn))
                    n += 1
            print(f">> {vid}: {n} 张截图 -> {folder}/")

        # 5) 写 manifest 与落地页
        with open(os.path.join(tmp, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        with open(os.path.join(tmp, "index.html"), "w", encoding="utf-8") as f:
            f.write(build_index_html(manifest))

        # 6) 收拢为新树；树未变则跳过提交
        g("-C", tmp, "--git-dir", GD, "--work-tree", tmp, "add", "-A")
        tree = g("--git-dir", GD, "--work-tree", tmp, "write-tree").stdout.strip()
        if tip:
            old_tree = run(["rev-parse", f"{PAGES}^{{tree}}"]).stdout.strip()
            if tree == old_tree:
                print(">> 内容无变化，跳过提交")
                return
        parent = ["-p", tip] if tip else []
        commit = run(["commit-tree", tree] + parent +
                     ["-m", f"publish: {', '.join(ids)}"]).stdout.strip()
        run(["update-ref", f"refs/heads/{PAGES}", commit])
        print(f">> pages 分支已更新: {commit[:8]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            os.remove(tmp + ".index")
        except OSError:
            pass

    print(f"\n完成。推送请执行: git push origin {PAGES}")


if __name__ == "__main__":
    main()




