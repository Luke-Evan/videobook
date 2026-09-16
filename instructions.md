# VideoBook：原味课程电子书工作流

目标：让读者基本不看原视频，也能获得接近原课的知识、论证、案例和老师个人表达；需确认时通过时间戳和截图回查。不是摘要流水线。所有命令在仓库根目录运行，用独立环境 `.venv/Scripts/python.exe`（Windows）或 `uv run python`。

## 1. 平台字幕优先

`python src/dump_transcript.py <url>`。平台字幕可用时绝不重跑 Whisper。优先复用完整的已有平台字幕缓存，保持 transcript.json / transcript.txt 不被校订覆盖。

检查 duration、chapters、segments 的首尾和中间覆盖。原脚本低于 50% 报错只是异常探针，不是“超过 50% 就完整”的验收标准。结尾短暂无语音可合理解释；大段缺失、未知总时长、登录态不足必须先解决，不能直接写完整书稿。

需要登录时用 `--cookies-from-profile <dir>` / `--cookies-file <path>`；专用配置可用 `python src/capture_frames.py --setup-profile` 一次登录。浏览器登录只由用户完成，cookie 不输出、不提交。海外源按用户现有代理配置处理。

只有确认平台确实无可用字幕才用原版 `asr_transcript.py`。先 `python src/asr_transcript.py <id> --sample-start 900 --sample-dur 180` 抽样，确认术语质量和耗时；全片昂贵 ASR 在告知用户实际估计并获得同意后运行。试跑后全量使用 `--restart` 防止漏开头。ASR 支持进度与续跑，详见 README；不以全片 Whisper、全量 OCR 或机械关键帧作为默认路径。

## 2. 最小字幕校订与书籍化

读取 `prompts/correction_system.md` 与 `prompts/stitcher_system.md` 后行动。

1. `python src/make_corrected.py <id>`：保留 raw，生成未审阅副本和 corrections.template.json。
2. 完整阅读字幕一次，在同一过程中建术语表、论证地图与 retention_checklist.md；清单规范见 `prompts/fidelity_check.md`，首次阅读前读完。AI 将确认修改写入 corrections.json，疑点写 correction_notes.md。不得仅从成品目录反向生成清单。
3. `python src/make_corrected.py <id> --edits output/<id>/corrections.json --force`：校验并应用逐段最小修改，产生 corrected 与变更日志。不跨段、不删段、不用全局替换表。
4. 按原课程节奏生成 book.md：保留措辞、类比、吐槽、铺垫、转折和重要案例；删除无意义卡顿与纯重复。不是标准教材化改写。按需插入 SCREENSHOT 时间戳。

AI 校订和书籍化由当前助手执行，不强制另购模型 API。脚本是变更验证器，不是语义校订器。不多轮完整重读长字幕，必要位置定点回查。

## 3. 按需截图（保留原版机制）

按教学信息增益选十几张真正有用的图，不做 100+ 帧和全量 OCR。需要术语证据时允许提前定点回查。截图流程、精确 seek、画质探针、增量补帧和物化沿用原项目。

- 桌面扩展可用时，优先 @Chrome 已登录播放器，截图保存 `images/shot_HH_MM_SS.png` 后 `python src/capture_frames.py <id> --materialize-only`。
- 否则 `python src/capture_frames.py <id> <url>`：使用专用 `.capture-profile/`，不调试主 Chrome 默认目录；登录需用户完成。有头登录窗口只在确需交互时使用。
- 浏览器方式失败/不可用时，`python src/extract_frames.py <id> <url>` 兜底；已有本地视频可复用，避免再次下载。

截完抽查 PPT/代码图和演示图，确认清晰、无遮挡、对应时间。book.md 不应残留未处理 SCREENSHOT；book.tagged.md 保留时间戳清单。

## 4. 轻量内容保真验收

按 `prompts/fidelity_check.md` 将首次阅读的保留清单逐项映射到书稿；检查重要案例步骤、转折顺序、限定语与直接引语。高风险或缺项位置才定点回查，不新增一轮全片重读、ASR 或全量 OCR。确认的实质遗漏先局部修补并复核，未解决的疑点明确标记；产出 fidelity_check.md，写明实际核验范围与证据等级。未解决实质问题的成品标“待核验版”，不宣称验收通过。

三段标定只在首次使用、实质修改书籍化提示词或更换课程类型时执行，不每课固定重做。清单和抽样均不能单独证明全书忠实。

## 5. 学习辅助与渲染

读取 `prompts/learning_aids.md`，从书稿生成 review.md（5–10 分钟复习）与 questions.md（章节自测和可折叠参考回答）。semantic_map.md 按需。不反向压缩主书稿。

`python src/post_process.py <url> output/<id>/book.md --learning-aids`，同时渲染已有 review.md / questions.md 并提供独立导航（不调用模型生成内容）。默认沿用上游 VideoBook 的原版渲染主题和排版；新增的 MathJax、截图放大、Bilibili 分 P 回链与学习辅助导航只作为功能增强，不改变原版视觉基调。

HTML 模板内置 MathJax 3（`src/assets/mathjax/es5`；每个独立课程目录的 `assets/es5` 是可直接预览的副本），支持 `\(...\)` 行内公式和 `\[...\]` 块级公式，不依赖 CDN 或外网。Markdown 转换前会保护数学分隔符，避免 Python-Markdown 吃掉反斜杠。

需要预览时用 `python -m http.server 8080 --bind 127.0.0.1 --directory output/<id>`。告知实际地址、文件和停止方式；不要暴露到局域网。检查桌面/移动端长文、目录、图片放大、视频回链。浏览器不可验证时明确说明，不冒称视觉 QA 完成。

## 6. 交付

book.md / book.html 是主产品；corrected、review、questions 为辅助；retention_checklist.md / fidelity_check.md 是保真检查记录，不插入主书正文。交付说明保真检查的实际范围与未解决疑点。数分钟进入可学习状态是目标，不是未测量的承诺。

保留大媒体缓存；只有用户确认才删除。`publish.py` 与 pages 推送仅在用户明确要求公开发布时执行，不把本地电子书自动上传。
