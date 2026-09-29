# 第六步（可选）：发布成品到 pages 分支

```bash
python src/publish.py <video_id>      # 或 --all：发布 output/ 下所有含 book.html 的视频
git push origin pages
```

- **发布内容**：`book.html`、`book.md`、`images/`，以及（若存在）`transcript.corrected.txt`。
  落地页卡片对含对照稿的书自动附「字幕对照」入口。
- **不发布**：原始字幕、`transcript.json` 等中间物不进公开仓库；`output/` 本地工作区不受任何 git 操作影响（铁律 4）。
- 目录名 = 视频标题（例如 `提示词工程 [02-Raw／26生成式软件工程／NJU]`）。
- 内容无变化时自动跳过提交。纯本地 git 操作，沙箱内可跑；`git push` 需要网络。

## pages 分支

- `pages` 是**独立 orphan 分支**，与 `main` 没有共同历史：`main` = 工具代码，`pages` = 成品。
- 首次推送后需在 GitHub 仓库 **Settings → Pages** 一次性启用：分支选 `pages`、目录选 `/ (root)`；
  之后每次 `git push origin pages` 自动部署。
- 在线阅读地址：`https://<owner>.github.io/videobook/`（落地页列出全部电子书，支持截图放大与 Mermaid 交互）。

## 注意

- 不要对 `pages` 或 `main` 强推。`main` 上已配置 ruleset（禁止强推与删除分支），
  确实需要重写历史时先临时停用规则，改完立刻恢复。
- 发布前确认 `book.html` 是最新的：改过 `book.md`、跑过 `--apply-map` 或更新过校订稿之后，都要重跑第四步 `post_process.py`。
- 课程讲义 / 幻灯片通常是 CC BY-NC 之类授权，发布到公开页面时书首的出处与许可署名**不能删**（铁律 7）。