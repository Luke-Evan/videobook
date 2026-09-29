# 第 2b 步（可选）：字幕校订对照稿 transcript.corrected.txt

目的：给读者一份**可对照视频逐段核对**的字幕稿 —— 保留讲师原始字词与顺序，只修 ASR 错词和口癖，
不改写成书面语、不做概括（书面化重构是 `book.md` 的职责）。该文件随第六步发布到 `pages`，
落地页卡片会自动为含对照稿的书加上「字幕对照」入口。

## 命令

```bash
python src/make_corrected.py <video_id> [<video_id> ...]   # 或 --all
python src/make_corrected.py <video_id> --edits corrections.json
```

- 输出 `output/<video_id>/transcript.corrected.txt`，格式与 `transcript.txt` 相同：`[MM:SS] 原文`，逐段不合并。
- **重跑保护**：目标文件已存在时脚本拒绝覆盖（防止抹掉后续的人工 / AI 行级订正）。
  确需从头重建加 `--force`；要叠加新校订用 `--edits <corrections.json>`。
- 纯本地步骤，沙箱内可跑。

## 只允许两类修改（铁律 5）

1. **ASR 错词替换**：来自 `src/make_corrected.py` 里的 `MAP`（按 key 长度降序应用，避免子串误伤）。
   **新视频遇到的系统性错词，直接往 `MAP` 里加一条并提交**（仓库里已有按讲次补充的先例），
   不要把 MAP 复制进 skill 或 `book.md`。
2. **口癖清理**：纯语气词整段删除、句尾语气词剥离、单字口吃叠词折叠。

## AI 行级订正（第二遍，叠加在 MAP 之后）

MAP 覆盖不到的问题（少字、截断词、不通顺）由 agent 通读全文后提案，脚本校验通过才应用：

1. 通读 `transcript.corrected.txt`，产出 old → new 清单（量大时可委派子代理生成，再由主流程审）。
2. 写成 `corrections.json`：

```json
{
  "source_sha256": "<transcript.json 中 segments 的 sha256>",
  "edits": [
    {
      "segment_index": 123,
      "original": "MAP 之后该段的完整原文",
      "replacement": "订正后的单行文本",
      "category": "transcription",
      "reason": "少识别一个字：车轱话 -> 车轱辘话"
    }
  ]
}
```

3. `python src/make_corrected.py <video_id> --edits corrections.json`，脚本会产出审计报告
   `output/<video_id>/transcript.corrections.json`（含每条的 `change_ratio`）。
4. **生成后抽查若干行确认无过改**，再进入发布。

### 校验层会拒绝什么（见 `src/make_corrected.py` 的 `apply_ai_edits`）

| 规则 | 说明 |
|---|---|
| `source_sha256` 不匹配 | 提案基于旧版 transcript，必须重新生成 |
| `segment_index` 非法或重复 | 必须是 `0 <= idx < len(segments)` 的整数且不重复 |
| 段已被口癖清理删除 | 不允许对已删除的段做校订 |
| `original` 与基线不逐字一致 | 基线 = MAP 应用后的文本，必须逐字相同 |
| `replacement` 为空或含换行 | 禁止删段、空替换、多行替换 |
| `category` 不合法或 `reason` 为空 | `category` 取 `proper_noun` / `technical_term` / `transcription` / `punctuation` / `segmentation` |
| 大幅修改 | 段长 >= 40 且变更率 > 40% 时默认拒绝，人工确认后加 `--allow-large-edits` |

### 订正原则

- 少字 / 错字 / 截断词这类识别错误**必修**（「车轱话」→「车轱辘话」）。
- 讲师**有意为之的强调式重复原样保留、不得折叠**（「工作工作工作工作」「点点点点点点点了十层」）。
- 不替讲师改观点、不补外部知识、不雅化口语梗。