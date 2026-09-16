# 最小字幕校订

目标是忠实的 corrected transcript，不是书稿，不是摘要。完整阅读 raw 字幕一次，在同一阅读过程中建立术语表与正文论证地图；后续仅定点回查，不多轮重读全片。

保留所有段、时间戳、顺序和老师原词。只修专有名词、英文技术词、明显听写错误、断句和标点。断句只在本段内调整标点，不跨段合并或移动内容。不要删除口癖、折叠强调式重复、改变观点、类比、吐槽或把口语提升为教材表述。口癖清理属于书稿阶段。

重点核验 Codex、Agent、Skill、Reward Hacking、Specification、Neovim。这些是核验候选，不是无条件替换表。Wi-Fi 不一定是 verifier；“外部”不一定是“外包”。优先结合本段前后上下文；只有确实需要时定点查看 PPT/截图，OCR 不是最终证据。不确定的词不猜改，另记在 correction_notes.md（段号、时间、候选、需要的证据）。

先运行 `python src/make_corrected.py <id>` 导出 raw 和 proposal 模板。读取 transcript.json 的 segments；segment_index 为从 0 开始的序号。把已确认的修改写成 corrections.json：

```json
{
  "source_sha256": "复制 corrections.template.json 的值",
  "edits": [
    {
      "segment_index": 12,
      "original": "必须逐字等于该段原文",
      "replacement": "最小修正版",
      "category": "technical_term",
      "reason": "结合相邻段可确定是在介绍编辑器 Neovim",
      "evidence": "可选：相邻段号或截图时间戳"
    }
  ]
}
```

category 仅允许 proper_noun / technical_term / transcription / punctuation / segmentation。每段最多一条修改，只提交有实质差异的段。

运行 `python src/make_corrected.py <id> --edits output/<id>/corrections.json --force`。脚本验证 raw 哈希、原文匹配、段数和修改比例；输出 transcript.corrected.txt 与 transcript.corrections.json。空 edits 只意味着没有提交修改，不意味着已经完成 AI 校订。不得把脚本生成的 raw 副本冒充 AI 校订结果。

最后抽查：技术词修改、长改动、讲师强调式重复各至少一处（若存在）。脚本只能检查结构和变更范围，不能证明语义忠实；语义责任仍由 AI 校订承担。
