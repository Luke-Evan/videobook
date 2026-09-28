"""Fetch official course assets (lecture notes + slide deck) and render slides.

Some courses publish their own wiki next to the video recordings (e.g.
https://jyywiki.cn/GSE/2026/): every lecture has a written note page
(`lectN.md`, rendered by the wiki) and a self-contained HTML slide deck
(`slidesN.html`). Both are strictly better sources than the video stream:

  * the notes are the lecturer's own written description -> authoritative
    terminology, section structure and reference links for the book;
  * the slides render as crisp vector-quality PNGs -> far sharper than any
    frame captured from the platform player.

Usage:
    python src/course_assets.py <video_id> --course-url https://jyywiki.cn/GSE/2026/
                            [--lecture N] [--list] [--no-render]
                            [--width 1920 --height 1080 --scale 2] [--force]
                            [--match-shots] [--apply-map FILE]

Outputs (all under output/<video_id>/course/):
    index.json            lecture list parsed from the course home page
    lect<N>.html          raw wiki page of the lecture notes
    lect<N>.notes.md      notes converted to readable Markdown (for the agent)
    slides<N>.html        raw slide deck (kept for provenance)
    slides.json           per-slide HTML payload extracted from the deck
    slides_text.md        per-slide plain text (title + bullets) for the agent
    slides/slide_NNN.png  crisp renders of every slide (width x height @scale)
    slide_map.json        provenance: which placeholder used which slide
    shot_slide_proposals.json   (--match-shots) shot -> slide candidates

--match-shots compares every images/shot_*.png against the rendered slides
(perceptual hash of the slide pane) and writes ranked candidates; the agent
confirms them and feeds the result back through --apply-map, which swaps the
blurry video frame for the crisp slide render (originals kept in
images/video_frames/).
"""
import argparse
import glob
import html as htmllib
import json
import os
import re
import shutil
import sys
import urllib.request
from html.parser import HTMLParser

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UA = {"User-Agent": "Mozilla/5.0 (videobook course-asset fetcher)"}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


# ─────────────────────────────────────────────
# course index / lecture resolution
# ─────────────────────────────────────────────

def parse_index(html_text: str):
    """Lecture rows: (n, title, notes_href, slides_href)."""
    lects = {}
    for m in re.finditer(r'href="(lect(\d+)\.md)"[^>]*>([^<]+)</a>', html_text):
        lects[int(m.group(2))] = {"n": int(m.group(2)), "title": m.group(3).strip(),
                                  "notes": m.group(1), "slides": None}
    for m in re.finditer(r'href="(slides(\d+)\.html)"', html_text):
        n = int(m.group(2))
        lects.setdefault(n, {"n": n, "title": f"(lecture {n})", "notes": None})
        lects[n]["slides"] = m.group(1)
    return [lects[k] for k in sorted(lects)]


def norm_title(t: str) -> str:
    t = re.sub(r"\[.*?\]", "", t)          # drop "[06-Raw/26生成式软件工程/NJU]"
    return re.sub(r"\s+", "", t).lower()


def resolve_lecture(lectures, video_title: str, wanted: int = None):
    if wanted:
        for l in lectures:
            if l["n"] == wanted:
                return l
        sys.exit(f"lecture {wanted} not found on the course page")
    target = norm_title(video_title or "")
    for l in lectures:
        if norm_title(l["title"]) == target:
            return l
    return None


# ─────────────────────────────────────────────
# wiki notes -> markdown (stdlib only)
# ─────────────────────────────────────────────

class NotesToMarkdown(HTMLParser):
    BLOCK = {"p", "div", "section", "blockquote", "table", "tr", "pre"}
    SKIP = {"script", "style", "nav", "header", "footer", "svg", "form"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.skip = 0
        self.in_wiki = 0
        self.list_stack = []
        self.href = None
        self.link_text = []
        self.in_code = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "div" and "wiki" in (a.get("class") or ""):
            self.in_wiki += 1
            return
        if not self.in_wiki:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self.out.append("\n" + "  " * len(self.list_stack) + "- ")
        elif tag in ("ul", "ol"):
            self.list_stack.append(tag)
        elif tag in self.BLOCK:
            self.out.append("\n\n" + ("> " if tag == "blockquote" else ""))
        elif tag == "a" and a.get("href"):
            self.href = a["href"]
            self.link_text = []
        elif tag == "code":
            self.in_code += 1
            self.out.append("`")
        elif tag == "br":
            self.out.append("\n")
        elif tag == "img":
            self.out.append(f'![img]({a.get("src", "")})')

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "div" and self.in_wiki and not self.list_stack:
            pass
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote", "pre", "table", "tr"):
            self.out.append("\n")
        elif tag in ("ul", "ol") and self.list_stack:
            self.list_stack.pop()
            self.out.append("\n")
        elif tag == "code" and self.in_code:
            self.in_code -= 1
            self.out.append("`")
        elif tag == "a" and self.href is not None:
            text = "".join(self.link_text).strip()
            self.out.append(f"[{text}]({self.href})" if text else self.href)
            self.href = None

    def handle_data(self, data):
        if self.skip or not self.in_wiki:
            return
        if self.href is not None:
            self.link_text.append(data)
        else:
            self.out.append(data)

    def text(self):
        s = "".join(self.out)
        s = re.sub(r"\n{3,}", "\n\n", s)
        return s.strip() + "\n"


def strip_tags(fragment: str) -> str:
    """Slide HTML fragment -> readable plain text."""
    s = re.sub(r"<(br|/li|/p|/h[1-6]|/div|/tr)>", "\n", fragment)
    s = re.sub(r"<li[^>]*>", "\n- ", s)
    s = re.sub(r"<h([1-6])[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = htmllib.unescape(s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def slide_title(fragment: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", fragment, re.S | re.I)
    return strip_tags(m.group(1)).replace("\n", " ").strip() if m else ""


# ─────────────────────────────────────────────
# slide rendering (headless Chrome via Playwright)
# ─────────────────────────────────────────────

RENDER_CSS = ("#pager{display:none!important}"
              ".slide{animation:none!important}"
              ".slide.leaving{display:none!important}")


def render_slides(slides_url: str, out_dir: str, width: int, height: int,
                  scale: int, force: bool) -> list:
    from playwright.sync_api import sync_playwright
    os.makedirs(out_dir, exist_ok=True)
    done = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": height},
                                    device_scale_factor=scale)
            page.goto(slides_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_function("document.querySelectorAll('.slide').length > 0",
                                   timeout=30000)
            page.add_style_tag(content=RENDER_CSS)
            page.evaluate("window.MathJax && MathJax.typesetPromise && MathJax.typesetPromise()")
            page.evaluate("document.fonts && document.fonts.ready")
            total = page.evaluate("document.querySelectorAll('.slide').length")
            for n in range(total):
                out = os.path.join(out_dir, f"slide_{n + 1:03d}.png")
                if os.path.exists(out) and not force:
                    done.append(out)
                    continue
                page.evaluate("n => { show(n); fitSlides(); }", n)
                page.wait_for_timeout(220)
                page.evaluate("fitSlides()")
                page.wait_for_timeout(80)
                page.screenshot(path=out)
                done.append(out)
                print(f"  rendered slide {n + 1}/{total}")
        finally:
            browser.close()
    return done


# ─────────────────────────────────────────────
# perceptual-hash matching (shots <-> slides)
# ─────────────────────────────────────────────

def dhash(path: str, size: int = 16):
    from PIL import Image
    im = Image.open(path).convert("L").resize((size + 1, size), Image.LANCZOS)
    px = list(im.getdata())
    bits = []
    for y in range(size):
        for x in range(size):
            bits.append(px[y * (size + 1) + x] < px[y * (size + 1) + x + 1])
    return bits


def hamming(a, b):
    return sum(1 for x, y in zip(a, b) if x != y)


def shot_slide_candidates(shot: str, slide_hashes, crops=((0.42, 0.0, 1.0, 1.0),
                                                           (0.5, 0.0, 1.0, 1.0),
                                                           (0.0, 0.0, 1.0, 1.0))):
    """The deck usually occupies the right pane of the lecture stream; try a
    few crops and keep the best (slide_index, distance)."""
    from PIL import Image
    im = Image.open(shot).convert("L")
    w, h = im.size
    best = None
    for (x0, y0, x1, y1) in crops:
        bits = dhash_from_image(im.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1))))
        for idx, sb in slide_hashes:
            d = hamming(bits, sb)
            if best is None or d < best[1]:
                best = (idx, d)
    return best


def dhash_from_image(im, size: int = 16):
    from PIL import Image
    im = im.convert("L").resize((size + 1, size), Image.LANCZOS)
    px = list(im.getdata())
    return [px[y * (size + 1) + x] < px[y * (size + 1) + x + 1]
            for y in range(size) for x in range(size)]


# ─────────────────────────────────────────────
# main
# ─────────────────────────────────────────────

SLIDE_PLACEHOLDER = re.compile(r'!\[([^\]]*)\]\(SLIDE:(\d+)(?:@(\d{2}:\d{2}:\d{2}))?\)')



# ─────────────────────────────────────────────
# slide timeline / audit / weave
# ("every official slide exactly once" guarantee)
# ─────────────────────────────────────────────

FIGURE_LINE = re.compile(r'^!\[([^\]]*)\]\(([^)]+)\)\s*$')
MARKER_LINE = re.compile(r'^\*\(参考时间: (\d{1,2}:\d{2}(?::\d{2})?)\)\*\s*$')


def _ts_sec(ts: str) -> int:
    parts = [int(x) for x in ts.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _sec_ts(sec: int) -> str:
    return f"{sec // 3600:02d}:{sec // 60 % 60:02d}:{sec % 60:02d}"


def load_file_slide_map(cdir: str) -> dict:
    """image basename -> slide index (materialized SLIDE placeholders + upgrades)."""
    m = {}
    for name in ("slide_map.json", "slide_upgrade_map.json"):
        path = os.path.join(cdir, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                m[k if "." in k else k + ".png"] = int(v)
    return m


def figure_slide(target: str, fmap: dict):
    """Which slide a book.md figure target shows (None = demo/non-slide frame)."""
    m = re.search(r"slide_(\d+)\.png$", target)
    if m:
        return int(m.group(1))
    base = os.path.basename(target)
    return fmap.get(base)


def scan_figures(book: str, fmap: dict):
    """[(line_idx, desc, target, slide_or_None)] for every standalone figure line."""
    out = []
    with open(book, encoding="utf-8") as f:
        for i, line in enumerate(f.read().split("\n")):
            m = FIGURE_LINE.match(line)
            if not m:
                continue
            desc, target = m.group(1), m.group(2)
            sm = re.match(r"SLIDE:(\d+)", target)
            slide = int(sm.group(1)) if sm else figure_slide(target, fmap)
            out.append((i, desc, target, slide))
    return out


def _sanitize(shot_anchors: dict, probe_anchors: dict, n_slides: int):
    """Keep shot anchors (reliable) and only those probe anchors that fit the
    monotonic slide order between their neighbouring shot anchors."""
    seq = sorted(shot_anchors.items(), key=lambda kv: kv[1])
    clean = {}
    last = 0
    for sl, t in seq:
        if sl > last:
            clean[sl] = t
            last = sl
    bounds = [(0, 0, 0)] + [(sl, t, t) for sl, t in sorted(clean.items(), key=lambda kv: kv[1])] \
        + [(n_slides + 1, 10 ** 9, 10 ** 9)]
    for (s_p, t_p, _), (s_n, t_n, _) in zip(bounds, bounds[1:]):
        cand = sorted(((t, sl) for sl, t in probe_anchors.items()
                       if s_p < sl < s_n and t_p <= t < t_n))
        last_s = s_p
        for t, sl in cand:
            if sl > last_s:
                clean[sl] = t
                last_s = sl
    return clean


def locate_slides(vdir: str, cdir: str, imgdir: str, step: int, threshold: int) -> None:
    """Find the first-appearance timestamp of every slide by sampling the gaps
    between already-matched anchors (probe frames land in course/_probe_frames/)."""
    import capture_frames as cf
    tj = os.path.join(vdir, "transcript.json")
    with open(tj, encoding="utf-8") as f:
        meta = json.load(f)
    duration = int(meta.get("duration") or 0)
    video_url = meta.get("video_url", "")
    platform = cf.detect_platform(os.path.basename(vdir), video_url)

    fmap = load_file_slide_map(cdir)
    n_slides = len(json.load(open(os.path.join(cdir, "slides.json"), encoding="utf-8")))
    shot_anchors, probe_anchors = {}, {}
    for stem, slide in fmap.items():
        m = re.match(r"shot_(\d{2})_(\d{2})_(\d{2})\.png", stem)
        if m and slide:
            shot_anchors.setdefault(int(slide), _ts_sec(":".join(m.group(i) for i in (1, 2, 3))))
    tl_path = os.path.join(cdir, "slide_timeline.json")
    if os.path.exists(tl_path):
        for row in json.load(open(tl_path, encoding="utf-8")):
            if row.get("first_ts") and row["source"] == "probe":
                probe_anchors.setdefault(row["slide"], _ts_sec(row["first_ts"]))

    anchors = _sanitize(shot_anchors, probe_anchors, n_slides)
    seq = sorted(anchors.items(), key=lambda kv: kv[1])
    bounds = [(0, 0)] + list(seq) + [(n_slides + 1, duration or 0)]
    samples = []
    for (s_a, t_a), (s_b, t_b) in zip(bounds, bounds[1:]):
        if s_b - s_a <= 1 or t_b <= t_a:
            continue
        samples.extend(range(t_a + step, t_b, step))
    probe_dir = os.path.join(cdir, "_probe_frames")
    os.makedirs(probe_dir, exist_ok=True)
    todo = [sec for sec in sorted(set(samples))
            if not os.path.exists(os.path.join(probe_dir, f"probe_{sec:05d}.png"))]
    print(f">> {len(todo)} probe frame(s) to capture (step {step}s)")
    if todo:
        shots = [[sec, f"probe_{sec:05d}", cf.build_url(platform, os.path.basename(vdir), sec),
                  cf.build_main_url(platform, os.path.basename(vdir), sec)] for sec in todo]
        err = cf.try_dedicated(shots, probe_dir, cf.DEFAULT_PROFILE_DIR,
                               os.path.basename(vdir), platform)
        if err:
            sys.exit(f"probe capture failed: {err}")

    slide_files = sorted(glob.glob(os.path.join(cdir, "slides", "slide_*.png")))
    slide_hashes = [(int(re.search(r"slide_(\d+)", os.path.basename(x)).group(1)), dhash(x))
                    for x in slide_files]
    for path in sorted(glob.glob(os.path.join(probe_dir, "probe_*.png"))):
        sec = int(re.search(r"probe_(\d+)", os.path.basename(path)).group(1))
        idx, dist = shot_slide_candidates(path, slide_hashes)
        if dist <= threshold:
            probe_anchors.setdefault(idx, sec)
    anchors = _sanitize(shot_anchors, probe_anchors, n_slides)

    rows = []
    for n in range(1, n_slides + 1):
        sec = anchors.get(n)
        src = "none"
        if sec is not None:
            src = "shot" if n in shot_anchors and sec == shot_anchors[n] else "probe"
        rows.append({"slide": n, "first_ts": _sec_ts(sec) if sec is not None else None,
                     "source": src})
    with open(tl_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    shown = [r for r in rows if r["first_ts"]]
    print(f">> timeline: {len(shown)}/{n_slides} slides located; "
          f"not shown on video: {[r['slide'] for r in rows if not r['first_ts']]}")


def audit(book: str, cdir: str) -> int:
    fmap = load_file_slide_map(cdir)
    n_slides = len(json.load(open(os.path.join(cdir, "slides.json"), encoding="utf-8")))
    counts = {n: 0 for n in range(1, n_slides + 1)}
    demo = 0
    for _, desc, target, slide in scan_figures(book, fmap):
        if slide is None:
            demo += 1
        elif slide in counts:
            counts[slide] += 1
    bad = 0
    for n in range(1, n_slides + 1):
        if counts[n] != 1:
            bad += 1
            print(f"  slide {n:>2}: {'x' + str(counts[n]) if counts[n] else 'MISSING'}")
    print(f">> audit: {n_slides - bad}/{n_slides} slides appear exactly once; "
          f"{demo} demo frame(s); {'FAIL' if bad else 'PASS'}")
    return 1 if bad else 0


def weave(book: str, cdir: str, imgdir: str) -> None:
    """Repair book.md so every official slide appears exactly once:
    drop duplicate slide figures (keep the first), insert missing ones at the
    section whose 参考时间 covers the slide's first appearance; slides never
    shown on video go to a closing appendix."""
    fmap = load_file_slide_map(cdir)
    slides = json.load(open(os.path.join(cdir, "slides.json"), encoding="utf-8"))
    n_slides = len(slides)
    tl = {}
    tl_path = os.path.join(cdir, "slide_timeline.json")
    if os.path.exists(tl_path):
        tl = {r["slide"]: r["first_ts"] for r in json.load(open(tl_path, encoding="utf-8"))}

    with open(book, encoding="utf-8") as f:
        lines = f.read().split("\n")
    figs = scan_figures(book, fmap)
    seen, drop = set(), set()
    for i, desc, target, slide in figs:
        if slide is None:
            continue
        if slide in seen:
            drop.add(i)
        seen.add(slide)

    markers = []
    for i, line in enumerate(lines):
        m = MARKER_LINE.match(line)
        if m:
            markers.append((i, _ts_sec(m.group(1))))
    inserts = {}
    appendix = []
    for n in range(1, n_slides + 1):
        if n in seen:
            continue
        title = slide_title(slides[n - 1]) or "(无标题)"
        alt = f"第 {n} 页幻灯片 · {title}"
        ts = tl.get(n)
        ph = f"![{alt}](SLIDE:{n}@{ts})" if ts else f"![{alt}](SLIDE:{n})"
        if not ts:
            appendix.append(ph)
            continue
        sec = _ts_sec(ts)
        pos = None
        for i, msec in markers:
            if msec <= sec:
                pos = i
        if pos is None:
            pos = 0
        inserts.setdefault(pos, []).append(ph)

    out = []
    for i, line in enumerate(lines):
        if i in drop:
            continue
        out.append(line)
        for ph in inserts.get(i, []):
            out.append(ph)
    if appendix:
        out += ["", "---", "", "## 附录：课堂未展示的幻灯片", ""]
        out += appendix
    with open(book, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out))
    print(f">> weave: dropped {len(drop)} duplicate figure(s), "
          f"inserted {sum(len(v) for v in inserts.values())} in body, "
          f"{len(appendix)} in appendix")
    materialize_slides(book, os.path.join(cdir, "slides"), imgdir, cdir)


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch + render official course assets")
    ap.add_argument("video_id")
    ap.add_argument("--course-url", help="course home page, e.g. https://jyywiki.cn/GSE/2026/")
    ap.add_argument("--lecture", type=int, help="lecture number (default: match video title)")
    ap.add_argument("--list", action="store_true", help="only list lectures of the course")
    ap.add_argument("--no-render", action="store_true", help="skip PNG rendering of slides")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--scale", type=int, default=2, help="device scale factor (2 => 4K png)")
    ap.add_argument("--force", action="store_true", help="re-render existing slide pngs")
    ap.add_argument("--match-shots", action="store_true",
                    help="propose shot -> slide matches for existing captures")
    ap.add_argument("--apply-map", metavar="FILE",
                    help='json {"shot_00_00_55": 1, ...}: replace shots with crisp slides')
    ap.add_argument("--locate-slides", action="store_true",
                    help="sample video gaps to find every slide's first-appearance timestamp")
    ap.add_argument("--step", type=int, default=20, help="probe sampling step in seconds")
    ap.add_argument("--threshold", type=int, default=55, help="dHash distance threshold")
    ap.add_argument("--audit", action="store_true",
                    help="verify every official slide appears exactly once in book.md")
    ap.add_argument("--weave", action="store_true",
                    help="repair book.md: dedup slide figures + insert missing slides")
    args = ap.parse_args()

    vdir = os.path.join(BASE_DIR, "output", args.video_id)
    cdir = os.path.join(vdir, "course")
    imgdir = os.path.join(vdir, "images")
    os.makedirs(cdir, exist_ok=True)

    if args.audit:
        sys.exit(audit(os.path.join(vdir, "book.md"), cdir))
    if args.weave:
        weave(os.path.join(vdir, "book.md"), cdir, imgdir)
        sys.exit(audit(os.path.join(vdir, "book.md"), cdir))
    if args.locate_slides:
        locate_slides(vdir, cdir, imgdir, args.step, args.threshold)
        sys.exit(audit(os.path.join(vdir, "book.md"), cdir))

    if args.apply_map:
        apply_map(args.apply_map, cdir, imgdir)
        return

    if not args.course_url:
        sys.exit("--course-url is required (e.g. https://jyywiki.cn/GSE/2026/)")
    base = args.course_url.rstrip("/") + "/"
    index_html = fetch(base).decode("utf-8", "replace")
    lectures = parse_index(index_html)
    with open(os.path.join(cdir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(lectures, f, ensure_ascii=False, indent=2)
    if args.list:
        for l in lectures:
            print(f"  {l['n']:>2}  {l['title']:<28} notes={l['notes']} slides={l['slides']}")
        return

    title = ""
    tj = os.path.join(vdir, "transcript.json")
    if os.path.exists(tj):
        with open(tj, encoding="utf-8") as f:
            title = json.load(f).get("title", "")
    lect = resolve_lecture(lectures, title, args.lecture)
    if not lect:
        print("video title:", title)
        print("course lectures:")
        for l in lectures:
            print(f"  {l['n']:>2}  {l['title']}")
        sys.exit("could not match the video to a lecture; pass --lecture N")
    print(f">> lecture {lect['n']}: {lect['title']}")

    # 1) lecture notes
    if lect.get("notes"):
        notes_url = base + lect["notes"]
        raw = fetch(notes_url).decode("utf-8", "replace")
        with open(os.path.join(cdir, lect["notes"] + ".html"), "w", encoding="utf-8") as f:
            f.write(raw)
        parser = NotesToMarkdown()
        parser.feed(raw)
        notes_md = parser.text()
        # 站内相对链接 -> 绝对链接，方便 Agent / 读者直接跳转
        notes_md = re.sub(r'\]\(/', '](https://' + base.split('//',1)[1].split('/',1)[0] + '/', notes_md)
        notes_out = os.path.join(cdir, re.sub(r"\.md$", "", lect["notes"]) + ".notes.md")
        with open(notes_out, "w", encoding="utf-8", newline="\n") as f:
            f.write(notes_md)
        print(f">> notes: {os.path.basename(notes_out)} ({len(notes_md)} chars)")

    # 2) slide deck payload
    slides_url = base + lect["slides"] if lect.get("slides") else None
    slides = []
    if slides_url:
        deck = fetch(slides_url).decode("utf-8", "replace")
        with open(os.path.join(cdir, lect["slides"]), "w", encoding="utf-8") as f:
            f.write(deck)
        m = re.search(r'<script id="slides-data" type="application/json">(.*?)</script>',
                      deck, re.S)
        if m:
            slides = json.loads(m.group(1))
        with open(os.path.join(cdir, "slides.json"), "w", encoding="utf-8") as f:
            json.dump(slides, f, ensure_ascii=False, indent=1)
        lines = []
        for i, s in enumerate(slides, 1):
            lines.append(f"## Slide {i}: {slide_title(s) or '(no title)'}\n")
            lines.append(strip_tags(s) + "\n")
        with open(os.path.join(cdir, "slides_text.md"), "w", encoding="utf-8",
                  newline="\n") as f:
            f.write("\n".join(lines))
        print(f">> slides: {len(slides)} pages -> slides_text.md")

    # 3) crisp renders
    slide_dir = os.path.join(cdir, "slides")
    if slides_url and not args.no_render:
        print(">> rendering slides with headless Chrome ...")
        render_slides(slides_url, slide_dir, args.width, args.height, args.scale, args.force)
        print(f">> {len(glob.glob(os.path.join(slide_dir, 'slide_*.png')))} slide pngs")

    # 4) materialize SLIDE placeholders in book.md
    book = os.path.join(vdir, "book.md")
    if os.path.exists(book):
        materialize_slides(book, slide_dir, imgdir, cdir)

    # 5) optional shot -> slide proposals
    if args.match_shots:
        match_shots(imgdir, slide_dir, cdir)


def materialize_slides(book: str, slide_dir: str, imgdir: str, cdir: str) -> None:
    with open(book, encoding="utf-8") as f:
        content = f.read()
    prov = {}
    os.makedirs(imgdir, exist_ok=True)

    def repl(m):
        desc, n, ts = m.group(1), int(m.group(2)), m.group(3)
        src = os.path.join(slide_dir, f"slide_{n:03d}.png")
        if not os.path.exists(src):
            print(f"  warning: slide {n} not rendered; placeholder kept")
            return m.group(0)
        if ts:
            dst = os.path.join(imgdir, "shot_" + ts.replace(":", "_") + ".png")
            shutil.copyfile(src, dst)
            prov[os.path.basename(dst)] = n
            return f"![{desc}](images/{os.path.basename(dst)})"
        dst = os.path.join(imgdir, f"slide_{n:03d}.png")
        shutil.copyfile(src, dst)
        prov[os.path.basename(dst)] = n
        return f"![{desc}](images/slide_{n:03d}.png)"

    new, count = SLIDE_PLACEHOLDER.subn(repl, content)
    if count:
        with open(book, "w", encoding="utf-8", newline="\n") as f:
            f.write(new)
        merged = {}
        map_path = os.path.join(cdir, "slide_map.json")
        if os.path.exists(map_path):
            merged = json.load(open(map_path, encoding="utf-8"))
        merged.update(prov)
        with open(map_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        print(f">> materialized {count} SLIDE placeholder(s)")
    else:
        print(">> no SLIDE placeholders in book.md")


def match_shots(imgdir: str, slide_dir: str, cdir: str) -> None:
    slide_files = sorted(glob.glob(os.path.join(slide_dir, "slide_*.png")))
    if not slide_files:
        sys.exit("no rendered slides; run without --no-render first")
    slide_hashes = [(int(re.search(r"slide_(\d+)", os.path.basename(p)).group(1)),
                     dhash(p)) for p in slide_files]
    proposals = {}
    for shot in sorted(glob.glob(os.path.join(imgdir, "shot_*.png"))):
        idx, dist = shot_slide_candidates(shot, slide_hashes)
        proposals[os.path.basename(shot)[:-4]] = {"slide": idx, "distance": dist}
        print(f"  {os.path.basename(shot):<22} -> slide {idx:>2}  d={dist}")
    out = os.path.join(cdir, "shot_slide_proposals.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(proposals, f, ensure_ascii=False, indent=2)
    print(">> proposals written to", os.path.relpath(out, BASE_DIR))


def apply_map(map_file: str, cdir: str, imgdir: str) -> None:
    with open(map_file, encoding="utf-8") as f:
        mapping = json.load(f)
    backup = os.path.join(imgdir, "video_frames")
    os.makedirs(backup, exist_ok=True)
    n = 0
    for shot_stem, slide_n in mapping.items():
        src = os.path.join(cdir, "slides", f"slide_{int(slide_n):03d}.png")
        dst = os.path.join(imgdir, shot_stem + ".png")
        if not os.path.exists(src) or not os.path.exists(dst):
            print("  skip (missing):", shot_stem, "->", slide_n)
            continue
        shutil.copyfile(dst, os.path.join(backup, shot_stem + ".png"))
        shutil.copyfile(src, dst)
        n += 1
        print("  upgraded", shot_stem, "<- slide", slide_n)
    print(f">> {n} shot(s) upgraded to official slide renders "
          f"(originals in images/video_frames/)")


if __name__ == "__main__":
    main()
