#!/usr/bin/env python3
"""audit_pipeline.py — McKinsey-style third-party audit scanner.

Scans 6 categories of issues in the Video Workshop workflow. Read-only.
Writes one dated audit report to 17_reports/.

Usage:
  python3 .codex/skills/video-diary-audit/scripts/audit_pipeline.py \
    --output 17_reports/workflow-audit-YYYY-MM-DD.md
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[4]
SKILLS_DIR = ROOT / ".codex" / "skills"
PACKAGE_JSON = ROOT / "package.json"
COMMAND_REGISTRY = ROOT / "00_system" / "registries" / "commands.json"
TEMPLATES_DIR = ROOT / "11_templates"
WORKFLOWS_DIR = ROOT / "08_workflows"
OLD_SKILLS_DIR = ROOT / "10_skills"
OLD_AGENTS_DIR = ROOT / "07_agents"

# Scripts explicitly marked as legacy in their skill's SKILL.md / references.
# These are intentionally NOT flagged as ORPHAN_SCRIPT.
LEGACY_SCRIPT_EXEMPT = {
    "render-ass-subtitles.py",
    "render-scripted-subtitles.py",
}

# Scripts in a `legacy/` subdirectory are not part of the live skill surface.
LEGACY_DIR_NAME = "legacy"

# Skills declared to do work but with no scripts/ directory.
SKILLS_DECLARING_WORK = {
    "video-diary-orchestrator",  # router only — exempt
    "video-diary-intake",  # calls npm run new-day
    "video-diary-script",  # calls LLMs, no scripts
    "video-diary-log",  # writes files, no scripts
    "video-diary-remote",  # wraps npm scripts
    "video-diary-cleanup",  # wraps npm scripts
    "video-diary-douyin",  # wraps npm scripts
    "video-production-bootstrap",  # wraps vp init/context/doctor
    "video-production-release",  # release logic lives in video_production_core
}

# Templates and their target skill owners (used to detect UNUSED_TEMPLATE).
TEMPLATE_OWNER_HINTS = {
    "daily-script.md": "video-diary-script",
    "daily-log.md": "video-diary-log",
    "video-diary-brief.md": "video-diary-edit",
    "codex-daily-edit-prompt.md": "video-diary-edit",
    "recording-import.md": "video-diary-edit",
}


@dataclass
class Finding:
    category: str
    severity: str
    title: str
    files: list[str] = field(default_factory=list)
    detail: str = ""
    owner: str = ""
    action: str = ""
    fid: str = ""


def scan_orphan_scripts() -> list[Finding]:
    """Scripts in skill's scripts/ that are NOT referenced in SKILL.md."""
    findings: list[Finding] = []
    if not SKILLS_DIR.exists():
        return findings
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        scripts_dir = skill_dir / "scripts"
        skill_md = skill_dir / "SKILL.md"
        if not scripts_dir.exists() or not skill_md.exists():
            continue
        skill_text = skill_md.read_text(encoding="utf-8")
        referenced: set[str] = set()
        for m in re.finditer(r"scripts/([\w\-]+\.\w+)", skill_text):
            referenced.add(m.group(1))
        for script in sorted(scripts_dir.rglob("*")):
            if not script.is_file():
                continue
            if LEGACY_DIR_NAME in script.relative_to(scripts_dir).parts:
                continue
            if script.suffix not in {".py", ".mjs", ".sh", ".js"}:
                continue
            name = script.name
            if name in LEGACY_SCRIPT_EXEMPT:
                continue
            # Count references anywhere within the skill tree
            refs = sum(
                1
                for f in skill_dir.rglob("*.md")
                if name in f.read_text(encoding="utf-8", errors="ignore")
            )
            if refs == 0:
                rel = script.relative_to(ROOT)
                findings.append(
                    Finding(
                        category="ORPHAN_SCRIPT",
                        severity="P2",
                        title=f"{skill_dir.name} has unreferenced script: {name}",
                        files=[str(rel)],
                        detail=(
                            "Script is in scripts/ but no .md inside the skill "
                            "mentions it. Either expose via SKILL.md or remove."
                        ),
                        owner=skill_dir.name,
                        action=(
                            "Add a 'Optional Branches' or 'Subtitle Quality Gate' "
                            f"section in {skill_dir.name}/SKILL.md that references "
                            f"`scripts/{name}`, OR delete the script."
                        ),
                    )
                )
    return findings


def scan_npm_orphans() -> list[Finding]:
    """package.json scripts without a clear skill owner."""
    findings: list[Finding] = []
    if not PACKAGE_JSON.exists():
        return findings
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    scripts = pkg.get("scripts", {})
    registry = {}
    if COMMAND_REGISTRY.exists():
        registry = json.loads(COMMAND_REGISTRY.read_text(encoding="utf-8")).get("commands", {})
    for cmd in sorted(scripts.keys()):
        owner = registry.get(cmd, {}).get("owner")
        if owner is None:
            findings.append(
                Finding(
                    category="NPM_ORPHAN",
                    severity="P1",
                    title=f"package.json script '{cmd}' has no owning skill",
                    files=["package.json"],
                    detail=(
                        "An npm command exists with no mapping to a "
                        "00_system command owner. Future agents cannot route to it."
                    ),
                    owner="(unassigned)",
                    action=(
                        f"Add '{cmd}' to 00_system/registries/commands.json "
                        "and verify a skill claims it; OR remove the script."
                    ),
                )
            )
    return findings


def scan_skill_no_script() -> list[Finding]:
    """Skills that have a SKILL.md but no scripts/ dir."""
    findings: list[Finding] = []
    if not SKILLS_DIR.exists():
        return findings
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name in SKILLS_DECLARING_WORK:
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        if not (skill_dir / "scripts").exists():
            findings.append(
                Finding(
                    category="SKILL_NO_SCRIPT",
                    severity="P2",
                    title=f"{skill_dir.name} declares work but has no scripts/",
                    files=[f".codex/skills/{skill_dir.name}/SKILL.md"],
                    detail="Skill has no scripts/ directory. All execution must live somewhere.",
                    owner=skill_dir.name,
                    action="Add scripts/ with executable code, or move to README-level doc.",
                )
            )
    return findings


def scan_double_source() -> list[Finding]:
    """Detect rules declared in two places at once."""
    findings: list[Finding] = []
    # Agent architecture overlap
    new_skill_count = len([p for p in SKILLS_DIR.iterdir() if p.is_dir()])
    agents_md = OLD_AGENTS_DIR / "README.md"
    if agents_md.exists():
        findings.append(
            Finding(
                category="DOUBLE_SOURCE",
                severity="P1",
                title="Agent architecture described in both 07_agents/ and .codex/skills/",
                files=[str(agents_md.relative_to(ROOT))],
                detail=(
                    f"{new_skill_count} project-local skills exist but the old "
                    "4-agent description in 07_agents/README.md still ships. "
                    "Onboarding models may pick either."
                ),
                owner="(cross-system)",
                action=(
                    "Keep AGENTS.md declaring .codex/skills/ as "
                    "the single source of truth; mark 07_agents/ as legacy."
                ),
            )
        )
    return findings


def scan_dual_path() -> list[Finding]:
    """Same action implemented in two paths."""
    findings: list[Finding] = []
    # Month-end archive: 09_tools/archive-month.mjs vs skill script
    old_archive = ROOT / "09_tools" / "archive-month.mjs"
    new_archive = (
        SKILLS_DIR
        / "video-diary-monthly-review"
        / "scripts"
        / "monthly_review.py"
    )
    package_text = PACKAGE_JSON.read_text(encoding="utf-8") if PACKAGE_JSON.exists() else ""
    if old_archive.exists() and new_archive.exists() and "node 09_tools/archive-month.mjs" in package_text:
        findings.append(
            Finding(
                category="DUAL_PATH",
                severity="P0",
                title="Month-end archive has two implementations",
                files=[
                    str(old_archive.relative_to(ROOT)),
                    str(new_archive.relative_to(ROOT)),
                ],
                detail=(
                    "Two tools do the same thing; nothing prevents the user "
                    "from running the wrong one."
                ),
                owner="video-diary-monthly-review",
                action=(
                    "Decide one canonical path, delete the other, update "
                    "package.json and the skill's SKILL.md."
                ),
            )
        )
    # Cover archive command: SKILL says archive-cover but command also lives at root 09_tools? — checked below
    return findings


def scan_unused_templates() -> list[Finding]:
    """Templates never referenced by any skill."""
    findings: list[Finding] = []
    if not TEMPLATES_DIR.exists():
        return findings
    for tpl in sorted(TEMPLATES_DIR.glob("*.md")):
        name = tpl.name
        owner_hint = TEMPLATE_OWNER_HINTS.get(name, "")
        # Count references inside .codex/skills/ across all SKILL.md
        ref_count = 0
        for md in SKILLS_DIR.rglob("*.md"):
            if name in md.read_text(encoding="utf-8", errors="ignore"):
                ref_count += 1
        if ref_count == 0:
            findings.append(
                Finding(
                    category="UNUSED_TEMPLATE",
                    severity="P2",
                    title=f"Template {name} is not referenced by any skill",
                    files=[str(tpl.relative_to(ROOT))],
                    detail=(
                        f"Suggested owner: {owner_hint or '(none)'}. "
                        "Two copies of the same content will drift."
                    ),
                    owner=owner_hint or "(unassigned)",
                    action=(
                        f"Either move into .codex/skills/{owner_hint}/references/ "
                        "or have the skill's SKILL.md reference it explicitly."
                    ),
                )
            )
    return findings


def render_markdown(findings: list[Finding], today: str) -> str:
    by_category: dict[str, list[Finding]] = {}
    for f in findings:
        by_category.setdefault(f.category, []).append(f)

    lines: list[str] = []
    lines.append(f"# Video Workshop 工作流第三方监视报告")
    lines.append("")
    lines.append(f"**审计日期**：{today}")
    lines.append(f"**审计工具**：`video-diary-audit/scripts/audit_pipeline.py`")
    lines.append(f"**审计方法**：麦肯锡 5 步诊断法（Frame / Structure / Evidence / Gap & Redundancy / Action）")
    lines.append(f"**审计范围**：`.codex/skills/` + `09_tools/` + `11_templates/` + `08_workflows/` + `10_skills/` + `07_agents/`")
    lines.append(f"**审计结论（Findings 总数）**：{len(findings)} 条")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Executive summary
    lines.append("## 一、执行摘要")
    lines.append("")
    p0 = [f for f in findings if f.severity == "P0"]
    p1 = [f for f in findings if f.severity == "P1"]
    p2 = [f for f in findings if f.severity == "P2"]
    summary = (
        f"本次审计扫描出 {len(findings)} 条 finding："
        f"P0 **{len(p0)}** 条 / P1 **{len(p1)}** 条 / P2 **{len(p2)}** 条。"
    )
    if p0:
        summary += f"最高优先级问题：{p0[0].title}。"
    if p1:
        summary += f"次高优先级问题集中在 DOUBLE_SOURCE 与 NPM_ORPHAN。"
    if not findings:
        summary = "本次扫描未发现任何 finding，所有 6 类检查通过。"
    lines.append(summary)
    lines.append("")
    lines.append("---")
    lines.append("")

    # Findings by category
    lines.append("## 二、断链 / 冗余 清单（按类别）")
    lines.append("")
    if not findings:
        lines.append("无 finding。")
    for cat, items in sorted(by_category.items()):
        lines.append(f"### {cat}（{len(items)} 条）")
        lines.append("")
        for idx, f in enumerate(items, 1):
            f.fid = f"{cat[:3]}-{idx:03d}"
            lines.append(f"#### {f.fid} — {f.title}")
            lines.append("")
            lines.append(f"- **严重度**：{f.severity}")
            lines.append(f"- **Owner**：`{f.owner or '(unassigned)'}`")
            lines.append(f"- **文件**：")
            for fp in f.files:
                lines.append(f"  - `{fp}`")
            lines.append(f"- **证据**：{f.detail}")
            lines.append(f"- **Action**：{f.action}")
            lines.append("")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Actions sorted by severity
    lines.append("## 三、可落地建议（按 P0 → P1 → P2 排序）")
    lines.append("")
    sorted_findings = sorted(findings, key=lambda x: (x.severity, x.category, x.fid))
    if not sorted_findings:
        lines.append("无建议项。")
    for f in sorted_findings:
        if not f.fid:
            f.fid = f"{f.category[:3]}-X"
        lines.append(f"- **[{f.severity}] {f.fid}** — {f.action}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Evidence dump (raw JSON)
    lines.append("## 四、扫描证据（原始 finding JSON）")
    lines.append("")
    lines.append("```json")
    payload = [
        {
            "id": f.fid,
            "category": f.category,
            "severity": f.severity,
            "title": f.title,
            "files": f.files,
            "owner": f.owner,
            "action": f.action,
        }
        for f in findings
    ]
    lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Trigger conditions
    lines.append("## 五、下次审计触发条件")
    lines.append("")
    lines.append("- 每完成 5 条视频日记（pipeline 稳定性回归）")
    lines.append("- 每当新增 / 删除 / 重命名一个 skill 或 script")
    lines.append("- 每当 `package.json` 增加 npm 命令")
    lines.append("- 月末归档前（与 `video-diary-monthly-review` 串联）")
    lines.append("- 用户显式说\"再来一次审计\" / \"复检\"时")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path to write the audit report (e.g. 17_reports/workflow-audit-2030-01-01.md)",
    )
    args = parser.parse_args()

    today = date.today().isoformat()
    findings: list[Finding] = []
    findings.extend(scan_orphan_scripts())
    findings.extend(scan_npm_orphans())
    findings.extend(scan_skill_no_script())
    findings.extend(scan_double_source())
    findings.extend(scan_dual_path())
    findings.extend(scan_unused_templates())

    output = render_markdown(findings, today)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")

    print(f"AUDIT_DONE findings={len(findings)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
