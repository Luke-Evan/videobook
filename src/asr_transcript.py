"""本地 ASR 兜底管线：当平台没有 CC / AI 字幕时，用 faster-whisper 转写音频。

产出的 transcript.json 与 scraper.get_transcript 完全同构
（video_url / title / video_id / duration / chapters / segments[{start,end,text}]），
因此后续排版、截帧、渲染各步无需任何改动。

用法:
  python src/asr_transcript.py <video_id|url> [选项]

常用选项:
  --model large-v3            whisper 模型（默认 large-v3）
  --device cuda               cuda / cpu（默认自动探测）
  --compute-type int8_float16 GPU 显存 <=4GB 时推荐
  --language zh               默认 zh
  --initial-prompt "..."      领域术语提示，抑制同音错词并让中文输出带标点
  --sample-start 60 --sample-dur 120   只试跑一段，用于评估质量与速度
  --no-words                  关闭词级时间戳（更快，分段更粗）

特性:
  - 音频已存在则复用（output/<id>/audio.m4a），否则用 yt-dlp + .capture-profile
    登录态下载（cookies 写在 output/<id>/_cookies.txt，output/ 已被 gitignore）。
  - 断点续跑：进度实时落盘 output/<id>/_asr_progress.jsonl，重跑自动从末尾续接。
"""
import argparse
import io
import json
import re
import os
import subprocess
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "src"))

from config import get_video_dir  # noqa: E402

DEFAULT_MODEL = "large-v3"
SR = 16000


def setup_cuda_dlls():
    """让 ctranslate2 找到 pip 版 CUDA 运行库（nvidia-cublas-cu12 / nvidia-cudnn-cu12）。

    Windows 下这些 DLL 装在 site-packages/nvidia/*/bin，不在系统 PATH 上，
    直接 import 会报 "Library cublas64_12.dll is not found"。必须在
    import ctranslate2 之前调用。
    """
    import glob
    import site

    cands = []
    for base in list(getattr(site, "getsitepackages", lambda: [])()) + [
        os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "Lib", "site-packages")
    ]:
        cands += glob.glob(os.path.join(base, "nvidia", "*", "bin"))
    added = []
    for d in dict.fromkeys(cands):
        if not os.path.isdir(d):
            continue
        try:
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(d)
        except OSError:
            pass
        added.append(d)
    if added:
        os.environ["PATH"] = os.pathsep.join(added) + os.pathsep + os.environ.get("PATH", "")
        print(f">> 已注册 {len(added)} 个 CUDA 运行库目录")
    return added


def hhmmss(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def norm_id(arg: str) -> str:
    """从 BVxxxx 或完整 URL 中取出视频 id。"""
    import re
    m = re.search(r"(BV[0-9A-Za-z]{10})", arg)
    if m:
        return m.group(1)
    m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", arg)
    if m:
        return m.group(1)
    return arg.strip().rstrip("/")


def video_url_of(vid: str) -> str:
    if vid.startswith("BV") or vid.startswith("av"):
        return f"https://www.bilibili.com/video/{vid}"
    return f"https://www.youtube.com/watch?v={vid}"


def ensure_cookies(out_dir: str) -> str:
    from login_utils import export_cookies, has_login_cookie
    path = os.path.join(out_dir, "_cookies.txt")
    try:
        export_cookies(out_path=os.path.abspath(path))
        if has_login_cookie(path):
            print(">> 已导出 .capture-profile 登录态 cookies")
            return path
    except Exception as e:  # noqa: BLE001
        print(f">> cookies 导出失败（继续匿名下载）: {e}")
    return None


def ensure_audio(out_dir: str, url: str) -> str:
    for ext in (".m4a", ".webm", ".opus", ".mp3", ".wav", ".mp4"):
        p = os.path.join(out_dir, "audio" + ext)
        if os.path.exists(p) and os.path.getsize(p) > 1024:
            print(f">> 复用已有音频: {p}")
            return p
    ck = ensure_cookies(out_dir)
    tpl = os.path.join(out_dir, "audio.%(ext)s")
    cmd = [sys.executable, "-m", "yt_dlp", "-f", "bestaudio", "--no-playlist", "-o", tpl]
    if ck:
        cmd += ["--cookies", ck]
    cmd.append(url)
    print(">> 下载音频（仅音频，不下载视频流）...")
    subprocess.run(cmd, check=True)
    for ext in (".m4a", ".webm", ".opus", ".mp3", ".wav"):
        p = os.path.join(out_dir, "audio" + ext)
        if os.path.exists(p):
            return p
    raise SystemExit("音频下载失败")


def fetch_meta(out_dir: str, url: str) -> dict:
    p = os.path.join(out_dir, "_info.json")
    if not os.path.exists(p):
        ck = ensure_cookies(out_dir)
        cmd = [sys.executable, "-m", "yt_dlp", "-j", "--no-playlist"]
        if ck:
            cmd += ["--cookies", ck]
        cmd.append(url)
        with open(p, "w", encoding="utf-8") as f:
            subprocess.run(cmd, stdout=f, check=True)
    d = json.load(open(p, encoding="utf-8"))
    chapters = []
    for c in d.get("chapters") or []:
        chapters.append({
            "start": hhmmss(c.get("start_time") or 0),
            "end": hhmmss(c.get("end_time") or 0),
            "title": (c.get("title") or "").strip(),
        })
    return {"title": d.get("title") or "", "duration": float(d.get("duration") or 0),
            "chapters": chapters}


_CJK = "\\u4e00-\\u9fff\\u3400-\\u4dbf\\u3000-\\u303f\\uff00-\\uffef"
_HALF2FULL = {",": "\uff0c", ";": "\uff1b", ":": "\uff1a", "?": "\uff1f", "!": "\uff01"}


def fix_punct(text: str) -> str:
    """把中文语境下的半角标点转为全角；英文术语、文件名、版本号内部标点保持原样。

    Whisper 输出中文时习惯用半角逗号，直接进电子书观感较差。判定规则是
    该标点至少有一侧紧邻 CJK 字符（句号还要求右侧不是字母数字，
    以免把 hello.c / v1.2 之类改坏）。
    """
    cjk = re.compile("[" + _CJK + "]")
    out = []
    for i, ch in enumerate(text):
        repl = _HALF2FULL.get(ch)
        if ch == ".":
            nxt = text[i + 1] if i + 1 < len(text) else ""
            prev = text[i - 1] if i else ""
            if cjk.match(prev) and not (nxt.isalnum()):
                repl = "\u3002"
        if repl:
            prev = text[i - 1] if i else ""
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if cjk.match(prev) or cjk.match(nxt):
                out.append(repl)
                continue
        out.append(ch)
    return "".join(out)


def rechunk(seg, words, max_sec=8.0, max_chars=60):
    """把一个 whisper 长段按标点 / 时长 / 字数切成接近平台字幕粒度的小段。"""
    text = (seg.text or "").strip()
    if not words or len(text) <= max_chars:
        return [{"start": seg.start, "end": seg.end, "text": text}]

    out, buf, buf_start, last_end = [], [], None, seg.start
    for w in words:
        wt = (w.word or "").strip()
        if not wt:
            continue
        if buf_start is None:
            buf_start = w.start
        buf.append(wt)
        cur = "".join(buf)
        last_end = w.end
        hard = (w.end - buf_start) >= max_sec or len(cur) >= max_chars
        soft = cur[-1] in "。！？；，、,.!?;:："
        if hard or (soft and len(cur) >= max_chars * 0.55):
            out.append({"start": buf_start, "end": last_end, "text": cur.strip()})
            buf, buf_start = [], None
    if buf:
        out.append({"start": buf_start, "end": last_end, "text": "".join(buf).strip()})
    return [c for c in out if c["text"]]


def main():
    ap = argparse.ArgumentParser(description="faster-whisper 本地转写兜底")
    ap.add_argument("video", help="video_id 或视频 URL")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--compute-type", default=None)
    ap.add_argument("--language", default="zh")
    ap.add_argument("--initial-prompt", default=None)
    ap.add_argument("--initial-prompt-file", default=None,
                    help="领域术语提示文件；缺省时自动读取 output/<id>/_asr_prompt.txt")
    ap.add_argument("--beam-size", type=int, default=5)
    ap.add_argument("--sample-start", type=float, default=None)
    ap.add_argument("--sample-dur", type=float, default=None)
    ap.add_argument("--no-words", action="store_true")
    ap.add_argument("--restart", action="store_true", help="忽略已有进度，从头转写")
    args = ap.parse_args()

    vid = norm_id(args.video)
    url = video_url_of(vid)
    out_dir = get_video_dir(vid)
    os.makedirs(out_dir, exist_ok=True)

    prompt = args.initial_prompt
    if not prompt:
        pf = args.initial_prompt_file or os.path.join(out_dir, "_asr_prompt.txt")
        if os.path.exists(pf):
            prompt = io.open(pf, encoding="utf-8-sig").read().strip()
            print(f">> 使用领域术语提示: {pf}（{len(prompt)} 字）")

    audio = ensure_audio(out_dir, url)
    meta = fetch_meta(out_dir, url)
    duration = meta["duration"]
    print(f">> 标题: {meta['title']}  时长: {duration:.0f}s ({hhmmss(duration)})")
    print(f">> 官方章节: {len(meta['chapters'])} 个")

    setup_cuda_dlls()
    from faster_whisper import WhisperModel, decode_audio
    import ctranslate2

    device = args.device
    if device == "auto":
        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    ctype = args.compute_type or ("int8_float16" if device == "cuda" else "int8")

    print(f">> 加载模型 {args.model} @ {device}/{ctype} ...")
    t0 = time.time()
    model = WhisperModel(args.model, device=device, compute_type=ctype)
    print(f">> 模型就绪，用时 {time.time() - t0:.1f}s")

    wav = decode_audio(audio, sampling_rate=SR)
    total = len(wav) / SR
    print(f">> 音频解码完成，实际时长 {total:.0f}s")

    prog = os.path.join(out_dir, "_asr_progress.jsonl")
    resume_at = 0.0
    if args.sample_start is not None or args.restart:
        if os.path.exists(prog):
            os.remove(prog)
    elif os.path.exists(prog):
        with open(prog, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
        if rows:
            resume_at = float(rows[-1]["end"])
            print(f">> 检测到进度，从 {hhmmss(resume_at)} 续跑（已有 {len(rows)} 段）")

    lo = args.sample_start if args.sample_start is not None else resume_at
    hi = (lo + args.sample_dur) if (args.sample_start is not None and args.sample_dur) else duration
    clip = wav[int(lo * SR):int(hi * SR)]
    print(f">> 转写区间 {hhmmss(lo)} -> {hhmmss(min(hi, total))}"
          f"（{(min(hi, total) - lo) / 60:.1f} 分钟音频）")

    kw = dict(language=args.language, beam_size=args.beam_size, vad_filter=True,
              vad_parameters={"min_silence_duration_ms": 400},
              condition_on_previous_text=False,
              word_timestamps=not args.no_words)
    if prompt:
        kw["initial_prompt"] = prompt

    t1 = time.time()
    segments, info = model.transcribe(clip, **kw)
    n = 0
    fh = open(prog, "a", encoding="utf-8")
    try:
        for seg in segments:
            for c in rechunk(seg, seg.words if not args.no_words else None):
                c["text"] = fix_punct(c["text"])
                rec = {"start": round(c["start"] + lo, 3), "end": round(c["end"] + lo, 3),
                       "text": c["text"]}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
            fh.flush()
            if n and n % 40 == 0:
                el = time.time() - t1
                done = seg.end
                rate = el / max(done, 1e-6)
                eta = rate * ((hi - lo) - done)
                print(f"   [{hhmmss(seg.end + lo)}] {n} 段  "
                      f"{rate:.2f}x 耗时  ETA {eta / 60:.1f} 分钟", flush=True)
    finally:
        fh.close()
    print(f">> 本轮转写完成: {n} 段，用时 {(time.time() - t1) / 60:.1f} 分钟")

    if args.sample_start is not None:
        print(">> 试跑模式：不写 transcript.json。抽样结果：")
        with open(prog, encoding="utf-8") as f:
            for line in list(f)[:12]:
                r = json.loads(line)
                print(f"   [{hhmmss(r['start'])}] {r['text']}")
        return

    rows = [json.loads(x) for x in open(prog, encoding="utf-8") if x.strip()]
    rows.sort(key=lambda r: r["start"])
    segs = [{"start": hhmmss(r["start"]), "end": hhmmss(r["end"]), "text": r["text"]}
            for r in rows if r["text"]]

    result = {"video_url": url, "title": meta["title"], "video_id": vid,
              "duration": duration or total, "chapters": meta["chapters"],
              "segments": segs, "asr": {"model": args.model, "device": device,
                                        "compute_type": ctype, "language": args.language}}

    with open(os.path.join(out_dir, "transcript.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "transcript.txt"), "w", encoding="utf-8") as f:
        for s in segs:
            f.write(f"[{s['start']}] {s['text']}\n")

    cov = rows[-1]["end"] / (duration or total) if rows else 0
    print(f"\n✅ transcript.json 已写入 {out_dir}（{len(segs)} 段）")
    print(f">> 字幕覆盖率自检: {cov:.1%}")
    if cov < 0.5:
        print("❌ 覆盖率过低，重跑本命令可自动续写剩余部分。")
        sys.exit(3)


if __name__ == "__main__":
    main()
