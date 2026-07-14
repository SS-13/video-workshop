# Video Diary Sub Agents

当前视频工作流使用三个生产 Sub Agent，并增加独立的系统演进 Agent 和 Release Agent。

```text
Main Codex thread
  -> Compliance Agent
  -> Text Agent
  -> Video Agent
  -> Compliance Agent

Daily Engineering Loop
  -> System Steward Agent

Release Lifecycle
  -> Release Agent
```

主线程只负责：

- 判断用户当前意图
- 确认日期、栏目、标题等关键参数
- 把具体任务分派给对应 Sub Agent
- 审核 Sub Agent 的结果
- 给用户一个简短明确的最终反馈

具体执行不要塞进主线程上下文。

## Agents

| Agent | 文件 | 职责 |
| --- | --- | --- |
| Compliance Agent | `compliance-agent.md` | 入口/出口合规检视，标出平台风险和需要改写/剪掉的片段 |
| Text Agent | `text-agent.md` | 原始文本、`01_inbox`、脚本改写、语言风格 |
| Video Agent | `video-agent.md` | 封面、剪辑、字幕、导出、抖音发布包、日志和 `00_state` 统计 |
| System Steward Agent | `system-steward-agent.md` | P0 Observation、去重、每日 TopK、Candidate 和演进日报 |
| Release Agent | `release-agent.md` | Shadow、真实 Canary、发布门禁、人工激活和回退 |

## Boundary

- Compliance Agent 不改原始文本，不剪视频，只给明确风险和最小处理建议。
- Text Agent 不碰视频文件。
- Video Agent 不改原始想法和脚本结构。
- Video Agent 独占从“视频上传/开始剪辑”到“成片导出/统计落表”的生产计时。
- Video Agent 在任务结束前必须显示标题、描述、智能章节和本次制作结果。
- System Steward Agent 与生产 Agent 隔离；默认 `TopK=3`，未入选更新保留在 backlog。
- P0 System Steward Agent 不修改正式 Skill、Rule、Hook、Agent、生产脚本和版本号。
- Release Agent 不修改生产媒体；只有用户明确确认后才能激活 Candidate。
- 月度统计只读 `00_state/production-stats.csv`，不要依赖 03/04/05 里视频文件是否还存在。

旧 `07_agents/` 是历史 4-agent 架构，只保留为历史材料，不作为当前执行入口。
