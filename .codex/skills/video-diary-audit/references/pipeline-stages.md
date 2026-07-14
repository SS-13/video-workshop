# Pipeline Stages (8 阶段诊断点)

每个阶段的输入 / 处理 / 输出必须存在且一致。

## Stage 0 — 想法收集（`01_inbox/`）

- 输入：用户随口想法
- 处理：`video-diary-intake` skill + `09_tools/new-day.mjs`
- 输出：`01_inbox/YYYY-MM-DD.md`
- 诊断：原始口述是否被改写？Day 编号是否合理？空模板段落是否被误识别？

## Stage 1 — 提词器脚本（`02_scripts/`）

- 输入：`01_inbox/YYYY-MM-DD.md`
- 处理：`video-diary-script` + public speaking-style default + optional local personal override
- 输出：`02_scripts/YYYY-MM-DD.md`
- 诊断：脚本结构是否包含一句话核心/提词器文案/拍摄提示？空段落是否被识别？

## Stage 2 — 原始素材（`03_recordings/`）

- 输入：手机导出视频
- 处理：仅复制，不改名
- 输出：`03_recordings/YYYY-MM-DD/*.mp4|MOV`
- 诊断：每段是否独立？是否需要片尾检测？横竖屏是否混用？

## Stage 3 — 自动剪辑工程（`04_videos/`）

- 输入：`02_scripts/YYYY-MM-DD.md` + `03_recordings/YYYY-MM-DD/`
- 处理：`video-diary-edit` skill 的 12 个脚本
- 输出：`04_videos/YYYY-MM-DD/BRIEF.md|EDIT_DECISIONS.md|STORYBOARD.md` + 处理后视频
- 诊断：所有脚本是否被引用？legacy 脚本是否退役？字幕路径是否一致？

## Stage 4 — 最终成片（`05_exports/`）

- 输入：`04_videos/` 的处理结果
- 处理：仅复制 mp4 + cover.jpg
- 输出：`05_exports/YYYY-MM-DD/YYYY-MM-DD_DayNN_video-diary.mp4` + `..._cover.jpg`
- 诊断：发布包结构是否完整？是否有 Day 编号？

## Stage 5 — 剪映微调 / 发布

- 输入：`05_exports/`
- 处理：人工剪映
- 输出：发布到抖音
- 诊断：是否记录到 publish-ledger.csv？抖音链接是否回填？

## Stage 6 — 日志（`06_logs/`）

- 输入：用户耗时报告 + 各 agent 输出
- 处理：`video-diary-log` skill + `video-diary-douyin`
- 输出：`06_logs/YYYY-MM-DD.md` + `publish-ledger.csv` + `douyin-*.csv`
- 诊断：5-10 分钟目标是否达成？token 估算是否标注？失败日志是否记录？

## Stage 7 — 封面陈列（`15_cover_gallery/`）

- 输入：每次封面改版
- 处理：`video-diary-cover` skill
- 输出：`15_cover_gallery/YYYY-MM-DD/vNN_*.jpg` + INDEX.md
- 诊断：cover-routes.json 版本是否演进？archive-cover 是否每次调用？

## Stage 8 — 月度归档（`16_monthly_archive/`）

- 输入：月末用户指令
- 处理：`video-diary-monthly-review` skill
- 输出：`16_monthly_archive/YYYY-MM/INDEX.md` + 文本归档 + `video-files.md`
- 诊断：是否有双路径实现？是否生成了清理清单？

## 跨阶段诊断

- **横向同步**：08_workflows/、11_templates/、10_skills/ 是否与 .codex/skills/ 同步？
- **Owner 矩阵**：每个 skill 是否在 package.json 有 npm 入口？每个 npm 入口是否有 skill 接管？
- **Lock 现状**：skills-lock.json 是否需要 lock project-local skill？
