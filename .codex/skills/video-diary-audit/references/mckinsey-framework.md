# McKinsey Diagnostic Framework (5 步)

本文是 `video-diary-audit` 的诊断骨架。每个审计报告都必须按这个结构写。

## 1. Frame — 界定问题

回答三个问题：

- **审计目标**：今天查什么？（断链？冗余？合规？）
- **审计范围**：哪些文件夹、哪些 skill、哪些工具？
- **时间窗**：快照到哪一天？

输出要求：报告顶部必须有一句话明确这三个问题。

## 2. Structure — MECE 拆分

把工作流拆到**互相独立、完全穷尽**的诊断单元：

```
8 个管道阶段 × 3 类产物（脚本 / 文档 / 数据）= 24 个诊断单元
```

每个诊断单元查三件事：

- **输入**：上游是否真的存在、是否还在维护
- **处理**：执行逻辑在哪？有没有冗余实现？
- **输出**：下游是否能消费？契约是否一致？

## 3. Evidence — 证据收集

不靠"看起来像"，靠文件路径 + 行号 + 引用关系。每条 finding 必须能回答：

- 在哪个文件？（绝对路径）
- 为什么是问题？（引用对比、规则违背、规模超阈值）
- 谁应该修？（owner）

不要把"建议"当成"证据"。"建议"放第四节，证据放第三节。

## 4. Gap & Redundancy — 断链与冗余

把第六节扫描出来的 6 类问题分桶：

- **Gap**：缺的东西（缺 skill、缺脚本、缺引用、缺 owner）
- **Redundancy**：多的东西（孤儿脚本、孤儿 npm 入口、双源规则、双路径实现）

每条 finding 必须有：

| 字段 | 内容 |
| --- | --- |
| ID | `GAP-001` / `RED-001` |
| Category | ORPHAN_SCRIPT / DOUBLE_SOURCE / DUAL_PATH / ... |
| File | 绝对路径 |
| Owner | 哪个 skill 应该负责 |
| Severity | P0 / P1 / P2 |
| Action | 一句话操作 |

## 5. Action — 可落地建议

按 P0/P1/P2/P3 排序，每条必须满足：

- **可验证**：跑完命令或读了文件就能确认已完成
- **有 owner**：知道改哪个 skill
- **有边界**：知道不要动什么

避免"建议提升团队意识"、"建议完善机制"这类无法验证的条目。

## 6 类扫描规则（与 scripts/audit_pipeline.py 对齐）

| 类别 | 触发条件 | 严重度默认 |
| --- | --- | --- |
| ORPHAN_SCRIPT | skill/scripts/ 下文件未在 skill/SKILL.md 引用 | P2 |
| NPM_ORPHAN | package.json 命令无对应 skill 接管 | P1 |
| SKILL_NO_SCRIPT | skill 声明动作但 scripts/ 不存在 | P2 |
| DOUBLE_SOURCE | 同一规则在两个文件出现 | P1 |
| DUAL_PATH | 同一动作两条实现路径 | P0 |
| UNUSED_TEMPLATE | templates/ 文件被 0 个 skill 引用 | P2 |

具体豁免列表见 `audit_pipeline.py` 顶部。