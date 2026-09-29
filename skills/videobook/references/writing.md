# 第二步：把字幕改写成 book.md

## 顺序

1. 读 `output/<video_id>/transcript.json`（`duration`、`chapters`、`segments`）。
2. 若存在 `output/<video_id>/course/`：先读 `course/*.notes.md`（讲师书面讲义）与 `course/slides_text.md`
   （每页幻灯片标题 + 要点），用途见 `course-assets.md`。
3. 读排版指令（stitcher prompt）：仓库内存在 `prompts/stitcher_system.md` 时**以它为准**；
   否则用本 skill 自带的同源副本 `references/stitcher-prompt.md`。两者不一致时以仓库版本为准，并回头同步副本。
4. 按其要求把字幕重构成结构化 Markdown，写入 `output/<video_id>/book.md`。
5. 若 `course/` 存在：交稿前跑 `python src/course_assets.py <video_id> --audit`，必须 PASS（铁律 8）。

## 硬性要求

- 口语转书面化技术语言；分章节，用 `##` / `###` 组织并加恰当小标题。
- 原语言不是中文时**必须翻译成地道中文书面语**。
- 关键界面 / 操作步骤处必须插占位符：`![场景描述](SCREENSHOT:HH:MM:SS)`。
- 遇到系统架构、执行流程流转、条件判断，**必须用 Mermaid** 画图（`` ``mermaid `` 包裹，如 `graph TD`），不要只用文字描述。
- 重要章节开头可保留时间锚点 `*(参考时间: 01:15)*` 方便读者溯源。
- 视频中提到的代码用带语言标注的代码块给出；要点用粗体与无序列表。

## 章节与时间戳

- `chapters` 只是**辅助定位**：平台官方章节往往粗糙，顶层分章按内容自身逻辑组织，**不要求**与官方章节一一对应。
- `SCREENSHOT:` 时间戳落在其所属内容的时间区间内即可；优先选章节边界、新幻灯片出现时刻、演示画面时刻，
  结合前后字幕语义定位，格式 `HH:MM:SS`（毫秒取整到秒）。
- `course/` 存在时，「画面就是某一页幻灯片」的地方改用 `![描述](SLIDE:n@HH:MM:SS)`
  （`n` = `slides_text.md` 中的幻灯片编号，`@` 后是该页在视频中出现的时间）；
  演示、终端、浏览器、板书等非幻灯片画面仍用 `SCREENSHOT:`。
  拿不准就用 `SCREENSHOT:`，后续脚本会自动把「画面即幻灯片」的帧升级为官方渲染图。

## 容忍 ASR 噪声

动笔前先结合视频标题、`chapters`（有讲义时再加讲义）建立**术语表**，改写时统一规范化。常见同音错词：
「深圳市软件工程」→ 生成式软件工程、「威尔法 / WIFI」→ verifier、「chain of salt」→ chain of thought、
「KIMIK3」→ Kimi K3。讲师的口语梗（「舔狗」「做题家」等）保留原意，不要雅化成术语。
反复出现的系统性错词应补进 `src/make_corrected.py` 的 MAP，见 `correction.md`。

## 保真底线（优先于「去除口语化」）

1. 保留讲师的类比、案例、铺垫与推理链：重要案例不得压缩成一句结论；代码、推导、操作保留足够步骤；
   没有证据的代码不得凭空补写。
2. 区分讲师判断、客观事实与编辑补充：必要补充明确标注「编者说明」；不替讲师纠正观点，不默默加入外部知识。
3. 只删无意义口癖、卡顿与纯重复：讲师有意的强调式重复、幽默与铺垫不属于纯重复。

## 写完之后

- 接着做第三步截帧（`capture.md`）。有 `course/` 时**先物化 SLIDE 占位符再截帧**，
  `capture_frames.py` 只会补拍剩下的 SCREENSHOT 帧。
- 需要字幕对照稿时做 `correction.md`；它与截帧没有依赖关系，可以并行。