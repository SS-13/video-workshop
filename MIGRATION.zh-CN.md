# 日期优先目录迁移

[English](MIGRATION.md)

已有本地工作区仍将内容直接放在 `YYYY-MM-DD` 目录下时，使用本说明迁移到：

```text
YYYY-MM-DD/<content-type>/<sequence>
```

历史内容默认归类为 `video-diary/001`。

## 迁移前

- 完成或停止正在运行的视频制作，渲染期间不得迁移。
- 对被 Git 忽略的本地工作区做文件系统备份或快照。个人内容未进入 Git，不能依赖
  Git 恢复。
- 在迁移验证通过前保留原始录像目录。

至少备份：

```text
00_state/
01_inbox/
02_scripts/
03_recordings/
04_videos/
05_exports/
06_logs/
15_cover_gallery/
```

## 预览

没有 `--apply` 时只生成迁移计划：

```bash
python3 09_tools/migrate-date-first-layout.py \
  --root . \
  --report 17_reports/migrations/date-first-dry-run.json
```

确认报告中的操作和冲突。目标位置存在不同内容时，工具会在执行迁移前停止。

## 执行

```bash
python3 09_tools/migrate-date-first-layout.py \
  --root . \
  --apply \
  --report 17_reports/migrations/date-first-apply.json
```

`03_recordings/` 中的原始录像不会移动，工具会通过硬链接或复制生成新目录内容。
文本文件和派生媒体可能发生移动，因此这些内容必须依靠迁移前备份恢复。

## 验证

```bash
npm run doctor
npm run new-day -- 2030-01-01
python3 09_tools/vp.py registry validate
python3 09_tools/vp.py contract validate
```

检查历史内容能否从新目录读取，并确认 Stable v2 与 legacy 命令仍在 Registry 中。

## 恢复

当前不提供自动反向迁移。验证失败时：

1. 停止视频生产并保留迁移报告。
2. 从文件系统备份恢复被移动的文本和派生媒体。
3. 保持原始录像不变。
4. 回到上一个确认可用的框架提交或 Release。
5. 运行 `npm run doctor`，通过后再继续生产。

legacy 是渲染与工作流回退通道，不是目录回滚工具。
