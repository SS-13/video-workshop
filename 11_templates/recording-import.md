# 录制素材导入清单

## 放置目录

```text
03_recordings/YYYY-MM-DD/
```

## 文件命名

```text
YYYY-MM-DD_S01_short-topic_take1.mp4
YYYY-MM-DD_S01_short-topic_take2.mp4
YYYY-MM-DD_S02_short-topic_take1.mp4
YYYY-MM-DD_S03_short-topic_take1.mp4
```

## 导入后检查

- [ ] 每个脚本都有对应视频
- [ ] 文件名包含日期（可选）
- [ ] 文件名包含 S01/S02/S03（可选；默认按录制顺序匹配）
- [ ] 多 take 已标明 take1/take2（可选；没标明时由 Video Pipeline Agent 列出待确认）
- [ ] 当天没有横屏竖屏混用
- [ ] 声音正常
- [ ] 画面没有明显遮挡

## 给 Codex 的指令

```text
今天的脚本在 02_scripts/YYYY-MM-DD.md，原始视频在 03_recordings/YYYY-MM-DD/。
请按 WORKFLOW.md 生成自动粗剪工程。

规则：
- 同一个 S 编号如果有多个 take，优先使用编号最大的 take。
- 如果文件名没有 S 编号，按录制顺序自动匹配 S01、S02、S03。
- 每段视频都独立检测并裁掉末尾黑屏/品牌页副本，不改原始素材。
- 每段前加 1-2 秒标题卡。
- 保留真实口播，不要过度包装。
- 输出到 04_videos/YYYY-MM-DD/ 和 05_exports/YYYY-MM-DD/。
```
