"""由 transcript.json 生成 AI 修正版字幕对照稿 transcript.corrected.txt。

原则（用户约定）：逐段保留讲师原始字词与顺序，不合并、不改写为书面语；
仅做两类修改——(1) ASR 错词替换（MAP）；(2) 口癖清理（纯语气词整段删除、
句尾语气词剥离、单字口吃叠词折叠）。MAP 可按视频扩充。

用法: python make_corrected.py <video_id> [<video_id> ...] | --all
"""
import argparse
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ASR 错词 -> 正确词（按长度降序应用，避免子串误伤）
MAP = {
    "深圳市软件工程": "生成式软件工程",
    "英拉SEMBLY": "内联汇编",
    "英外SAMBLY": "内联汇编",
    "inline sembly": "内联汇编",
    "英line sembly": "内联汇编",
    "chain of salt": "chain of thought",
    "chal thought": "chain of thought",
    "chef s": "chain of thought",
    "chap out": "chain of thought",
    "chp out": "chain of thought",
    "CHAPSP": "chain of thought",
    "test time skilling": "test-time scaling",
    "试time skilling": "test-time scaling",
    "cloud opo4.5": "Claude Opus 4.5",
    "MANUEL伯纳姆": "Manuel Blum",
    "hugin face": "Hugging Face",
    "open street map": "OpenStreetMap",
    "home brew": "Homebrew",
    "exterminate js": "xterm.js",
    "xterm js": "xterm.js",
    "deep sv4flash": "DeepSeek",
    "deep sick with the flash": "DeepSeek",
    "deep pick": "DeepSeek",
    "deep chick": "DeepSeek",
    "D4C": "DeepSeek",
    "DIVSK": "DeepSeek",
    "KIMIK3": "Kimi K3",
    "GPT5.6": "GPT-5.6",
    "GBT5.6": "GPT-5.6",
    "GPP5.6": "GPT-5.6",
    "GP5.6": "GPT-5.6",
    "GPT56": "GPT-5.6",
    "cheat gp d": "ChatGPT",
    "CHEGBT": "ChatGPT",
    "拆GBT": "ChatGPT",
    "拆GPT": "ChatGPT",
    "拆GPA": "ChatGPT",
    "terry machine": "Turing machine",
    "church tcs": "Church-Turing 论题",
    "habalton pass": "哈密顿路径",
    "ham alton": "哈密顿",
    "three reset": "3-SAT",
    "justin time": "just-in-time",
    "include pass": "include path",
    "yo mode": "YOLO mode",
    "low list": "allowlist",
    "AI slap": "AI slop",
    "passer": "parser",
    "sober": "solver",
    "agents点MD": "agents.md",
    "AGENTS点MD": "agents.md",
    "agent4点MD": "agents.md",
    "agency md": "agents.md",
    "H4点MD": "agents.md",
    "卢卡": "LUCA",
    "杠I": "-I",
    "在ID里": "在 IDE 里",
    "ID里面": "IDE 里面",
    "ID的": "IDE 的",
    "GBT": "ChatGPT",
    "威尔法尔": "verifier",
    "威尔法": "verifier",
    "VERIFILE": "verifier",
    "VERIFI": "verifier",
    "WIFI": "verifier",
    "linux": "Linux",
}
_MAP_ITEMS = sorted(MAP.items(), key=lambda kv: -len(kv[0]))

# 整段即为口癖 -> 删除该段
FILLER_ONLY = {"呃", "嗯", "啊", "哦", "啧", "哎", "哎呀", "哈哈", "哈哈哈", "嘿嘿",
               "对", "对吧", "对啊", "好啊", "好", "好的", "然后", "任何", "额",
               "anyway", "Anyway", "ANYWAY", "呃呃", "嗯嗯", "啊哈", "呜", "喂", "yes", "no"}

# 句尾口癖 -> 剥离
TAIL_FILLER = re.compile(r"(?:对吧|对不对|是吧|是不是|嘛|呀|哦|呃|嗯|哈哈|哈|啊|呢)+$")

# 单字口吃叠词折叠：我我我->我 等
STUTTER = re.compile(r"(我|你|他|它|就|是|有|去|来|啊|呃|嗯|对|但|那|这|也|都|还|又|再|很|太|会|要|想|说|看|做|搞|弄|写|读|问|答|学|教|玩|用|给|把|被|让|使|等)\1+")


def correct(text: str):
    for old, new in _MAP_ITEMS:
        if old in text:
            text = text.replace(old, new)
    text = text.replace("呃", "").replace("嗯", "")
    text = STUTTER.sub(r"\1", text)
    text = TAIL_FILLER.sub("", text).strip()
    return text


def main():
    ap = argparse.ArgumentParser(description="生成 AI 修正版字幕对照稿")
    ap.add_argument("video_id", nargs="*")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    ids = args.video_id or [d for d in sorted(os.listdir(os.path.join(BASE, "output")))
                            if os.path.isfile(os.path.join(BASE, "output", d, "transcript.json"))]
    for vid in ids:
        src = os.path.join(BASE, "output", vid, "transcript.json")
        segs = json.load(open(src, encoding="utf-8"))["segments"]
        out_lines, dropped, fixed = [], 0, 0
        for seg in segs:
            raw = seg["text"].strip()
            if raw in FILLER_ONLY:
                dropped += 1
                continue
            txt = correct(raw)
            if txt != raw:
                fixed += 1
            if not txt:
                dropped += 1
                continue
            h, m, s = seg["start"].split(":")
            mm = int(h) * 60 + int(m)
            out_lines.append(f"[{mm:02d}:{s}] {txt}")
        dst = os.path.join(BASE, "output", vid, "transcript.corrected.txt")
        with open(dst, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(out_lines) + "\n")
        print(f"{vid}: {len(segs)} 段 -> {len(out_lines)} 行（修正 {fixed} 行，删除口癖段 {dropped}）")


if __name__ == "__main__":
    main()
