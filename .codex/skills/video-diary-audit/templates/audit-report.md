# Video Workshop 工作流第三方监视报告（模板）

> 由 `audit_pipeline.py` 自动生成。请勿手填。

**审计日期**：YYYY-MM-DD
**审计工具**：`video-diary-audit/scripts/audit_pipeline.py`
**审计方法**：麦肯锡 5 步诊断法（Frame / Structure / Evidence / Gap & Redundancy / Action）
**审计范围**：`.codex/skills/` + `09_tools/` + `11_templates/` + `08_workflows/` + `10_skills/` + `07_agents/`
**审计结论（Findings 总数）**：N 条

---

## 一、执行摘要

一段话，三句话内说清楚今天发现的核心问题。

## 二、断链 / 冗余 清单（按类别）

### CATEGORY-NAME（N 条）

#### FID-NNN — Title

- **严重度**：P0 / P1 / P2
- **Owner**：`skill-name` 或 `(unassigned)`
- **文件**：
  - `path/to/file`
- **证据**：一句事实陈述
- **Action**：一句可执行操作

## 三、可落地建议（按 P0 → P1 → P2 排序）

- **[P0] ID** — action text
- **[P1] ID** — action text
- **[P2] ID** — action text

## 四、扫描证据（原始 finding JSON）

```json
[
  {
    "id": "...",
    "category": "...",
    "severity": "...",
    "title": "...",
    "files": ["..."],
    "owner": "...",
    "action": "..."
  }
]
```

## 五、下次审计触发条件

- 每完成 5 条视频日记
- 每当新增 / 删除 / 重命名一个 skill 或 script
- 每当 `package.json` 增加 npm 命令
- 月末归档前
- 用户显式说"再来一次审计" / "复检"时
