---
name: video-diary-audit
description: Third-party Video Workshop audit using a McKinsey-style diagnostic framework. Use when the user asks for 工作流体检, 第三方监视, 找断链, 查漏补缺, redundant skill, audit workflow, or wants a structured 改进建议 report. Reads skills, scripts, templates, and workflows; writes one dated audit report to 17_reports/ with no source modifications.
---

# Video Diary Audit (McKinsey-style)

## Core Rule

Be a third-party monitor, not a participant. Read everything, write one report, change nothing in the source. Every finding must cite a concrete file path and the exact issue category. No vague advice, no "you should consider…".

## Method (5 步诊断)

1. **界定问题（Frame）**：明确审计目标、范围、时间窗、可执行边界
2. **建立诊断框架（Structure）**：MECE 拆分工作流到阶段、阶段内拆到输入/处理/输出
3. **证据收集（Evidence）**：用脚本扫事实，每条事实对应一个文件路径
4. **识别断链与冗余（Gap & Redundancy）**：每条 finding 必须可指派 owner
5. **可落地建议（Action）**：按 P0/P1/P2/P3 排序，每条带文件路径 + owner + 可验证标准

## Trigger

Use this skill when the user says any of:

- 工作流体检 / 找断链 / 查漏补缺 / 第三方监视 / 监视报告
- redundant skill / orphan script / 哪些脚本没人用 / 哪些 skill 没人引
- audit workflow / pipeline integrity / 工作流完整性
- 想让我做一份改进建议报告

Do not use this skill for daily edits, scripts, or content work. Use `video-diary-cleanup` for daily cleanup and `video-diary-monthly-review` for month-end archive.

## How To Run

Run the bundled scanner and write one dated report:

```bash
python3 .codex/skills/video-diary-audit/scripts/audit_pipeline.py \
  --output 17_reports/workflow-audit-YYYY-MM-DD.md
```

The script scans six categories:

| 类别 | 含义 | 输出 |
| --- | --- | --- |
| ORPHAN_SCRIPT | skill 内 scripts/ 下存在但 SKILL.md 未引用 | 文件路径 + 风险说明 |
| NPM_ORPHAN | package.json 暴露的 npm 命令但对应 skill 不存在 | 命令 + 缺失 skill |
| SKILL_NO_SCRIPT | skill 无任何执行脚本却声明有动作 | skill 名 + 缺什么脚本 |
| DOUBLE_SOURCE | 同一规则在两个文件并存 | 两个文件路径 |
| DUAL_PATH | 同一动作有两条实现路径 | 路径对比 |
| UNUSED_TEMPLATE | templates/ 文件无人引用 | 模板路径 + 建议 |

Then read `references/mckinsey-framework.md` and `references/pipeline-stages.md` for the diagnostic lens; read `templates/audit-report.md` for the output shape.

## Output

One file: `17_reports/workflow-audit-YYYY-MM-DD.md`.

The report must contain:

1. **执行摘要**：一段话，3 句话内说清楚今天发现的核心问题
2. **断链清单（Gaps）**：必须改的项，按风险排序
3. **冗余清单（Redundancy）**：可以删的项
4. **可改进建议（Actions）**：P0/P1/P2/P3 排序，每条带 owner
5. **扫描证据（Evidence）**：脚本输出原文，作为可验证的事实底
6. **下次审计触发条件**：什么时候再跑一次

## Rules

- Read-only. Never edit source skills, scripts, or templates.
- One audit, one report. Do not generate intermediate files.
- Every finding cites a file path. If you cannot cite, do not list it.
- Prefix report filename with `MiniMax` per user convention.
- Run the script, do not manually rewrite the scanner output. The script is the source of truth.
