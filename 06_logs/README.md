# 发布台账

`publish-ledger.csv` 用来做长期数据分析。

核心字段：

- `published_at`：发布到抖音的时间。
- `manual_minutes`：用户实际动手时间。
- `total_elapsed`：从开始到出片的总跨度。
- `reported_tokens`：用户报告的 token。
- `estimated_tokens`：项目侧估算 token。
- `douyin_url`：发布链接。

发布后用 Log Agent 补齐当天行，后续可以分析耗时、token 和发布时间的变化。

## 制作统计台账

`production-stats.csv` 用来做月度/年度制作复盘。它不等发布，成片完成后立即写入。

核心字段：

- `video_duration_seconds`：最终成片长度。
- `production_total_minutes`：从“视频上传/开始剪辑”到“最终 MP4 + 封面完成”的总用时。
- `column`：视频日记、碎碎念、读书笔记等栏目。
- `video_path` / `cover_path`：最终发布包路径。
- `estimated_tokens`：本次制作估算 token。

月度复盘优先读取 `production-stats.csv` 汇总视频长度和制作总用时，再回退到 `publish-ledger.csv` 和每日日志。

## 媒体保留审计

`media-retention/` 保存每次自动保留任务的 JSON 清单。清单记录候选、实际删除、
跳过原因、释放空间和生产锁状态；长期统计以
`00_state/media-retention-ledger.csv` 为准。清理不会删除本 README、脚本、字幕、
封面、发布文案或结构化统计。
