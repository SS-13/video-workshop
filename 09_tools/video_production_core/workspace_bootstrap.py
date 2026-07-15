"""Initialize and inspect a local Video Workshop workspace."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import csv
import importlib.util
import json
import os
import shutil

from video_production_core.contracts import validate_contract_examples
from video_production_core.registry import validate_control_plane


WORKSPACE_DIRECTORIES = [
  "00_state/observations",
  "00_state/evolution",
  "00_state/evolution/completed",
  "00_state/locks",
  "00_state/runs",
  "00_state/releases",
  "01_inbox",
  "02_scripts",
  "03_recordings",
  "04_videos",
  "05_exports",
  "06_logs",
  "10_skills/personal-speaking-style",
  "11_templates/audio/bgm",
  "11_templates/pencil-cover-demos",
  "11_templates/关键词收集",
  "12_research",
  "13_predictions",
  "15_cover_gallery",
  "16_monthly_archive",
  "17_reports/audits",
  "17_reports/evolution",
  "17_reports/releases",
  "18_learning",
]

PUBLIC_AI_READ_ORDER = [
  "AGENTS.md",
  "START_HERE.md",
  "PIPELINE.md",
  "WORKFLOW.md",
  "00_system/system.json",
  "00_system/profiles/video-diary-default.json",
  "00_system/registries/agents.json",
  ".codex/skills/video-diary-orchestrator/SKILL.md",
  ".codex/skills/video-production-evolution/SKILL.md",
  "00_system/defaults/speaking-style.md",
  ".codex/skills/video-production-bootstrap/references/personalization.md",
]

LOCAL_OVERRIDE_PATHS = [
  "10_skills/personal-speaking-style/SKILL.md",
  "11_templates/关键词收集/字幕纠错词库.tsv",
  "11_templates/关键词收集/专有名词清单.md",
  "00_state/personalization.json",
]

PERSONALIZATION_SOURCE_PATTERNS = [
  "01_inbox/**/*.md",
  "02_scripts/**/*.md",
  "06_logs/**/*.md",
]

CONTENT_LEDGER_FIELDS = [
  "content_id",
  "date",
  "column",
  "day_label",
  "title",
  "status",
  "inbox_ref",
  "script_ref",
  "recording_ref",
  "workspace_ref",
  "export_ref",
  "cover_ref",
  "published_at",
  "douyin_url",
  "notes",
]

PRODUCTION_STATS_FIELDS = [
  "content_id",
  "date",
  "column",
  "day_label",
  "title",
  "video_path",
  "cover_path",
  "video_duration_seconds",
  "video_duration_text",
  "production_started_at",
  "production_finished_at",
  "production_total_minutes",
  "production_total_text",
  "estimated_tokens",
  "export_file_size_bytes",
  "notes",
  "updated_at",
]

PUBLISH_LEDGER_FIELDS = [
  "date",
  "day_label",
  "topic",
  "status",
  "published_at",
  "video_path",
  "cover_path",
  "video_duration",
  "manual_minutes",
  "total_elapsed",
  "reported_tokens",
  "estimated_tokens",
  "codex_visible_tokens",
  "douyin_url",
  "notes",
]

PRIVATE_IGNORE_PATTERNS = [
  "00_state/**",
  "01_inbox/",
  "02_scripts/",
  "03_recordings/",
  "04_videos/",
  "05_exports/",
  "06_logs/**",
  "10_skills/personal-speaking-style/",
  "11_templates/关键词收集/",
  "15_cover_gallery/**",
  "17_reports/",
  "18_learning/**",
  ".runtime/",
  ".env",
  "*.mp4",
  "*.srt",
]


def now_iso() -> str:
  return datetime.now().astimezone().isoformat(timespec="seconds")


def relative_path(root: Path, path: Path) -> str:
  return str(path.resolve().relative_to(root.resolve()))


def write_text_if_missing(path: Path, content: str) -> bool:
  if path.exists():
    return False
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(content, encoding="utf-8")
  return True


def write_json_if_missing(path: Path, payload: Dict[str, Any]) -> bool:
  return write_text_if_missing(
    path,
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
  )


def csv_header(fields: List[str]) -> str:
  return ",".join(fields) + "\n"


def require_core(root: Path) -> None:
  required = [
    root / "package.json",
    root / "00_system" / "system.json",
    root / ".codex" / "skills",
  ]
  missing = [relative_path(root, path) for path in required if not path.exists()]
  if missing:
    raise OSError("Missing Video Workshop core files: " + ", ".join(missing))


def initialize_workspace(root: Path) -> Dict[str, Any]:
  root = root.resolve()
  require_core(root)
  system = json.loads((root / "00_system" / "system.json").read_text(encoding="utf-8"))
  package = json.loads((root / "package.json").read_text(encoding="utf-8"))

  created_directories = []
  existing_directories = []
  for value in WORKSPACE_DIRECTORIES:
    path = root / value
    if path.exists():
      existing_directories.append(value)
      continue
    path.mkdir(parents=True, exist_ok=True)
    created_directories.append(value)

  files = {
    root / "00_state" / "workspace.json": json.dumps({
      "schemaVersion": 1,
      "name": root.name,
      "systemVersion": package.get("version", "unknown"),
      "defaultContentType": system.get("defaultContentType", "video-diary"),
      "createdAt": now_iso(),
    }, ensure_ascii=False, indent=2) + "\n",
    root / "00_state" / "day-counter.json": json.dumps({
      "schemaVersion": 1,
      "series": "video-diary",
      "lastDay": 0,
      "lastContentId": "",
      "updatedAt": "",
      "rules": {
        "videoDiaryIncrementsDay": True,
        "suisuinianIncrementsDay": False,
        "readingNoteIncrementsDay": False,
      },
    }, ensure_ascii=False, indent=2) + "\n",
    root / "00_state" / "content-ledger.csv": csv_header(CONTENT_LEDGER_FIELDS),
    root / "00_state" / "production-stats.csv": csv_header(PRODUCTION_STATS_FIELDS),
    root / "00_state" / "publish-ledger.csv": csv_header(PUBLISH_LEDGER_FIELDS),
    root / "00_state" / "personalization.json": json.dumps({
      "schemaVersion": 1,
      "status": "pending",
      "sourcePaths": [],
      "sourceFileCount": 0,
      "lastAnalyzedAt": "",
      "artifacts": [
        "10_skills/personal-speaking-style/SKILL.md",
        "11_templates/关键词收集/字幕纠错词库.tsv",
        "11_templates/关键词收集/专有名词清单.md",
      ],
      "notes": "AI may update this file after reading user-approved local content.",
    }, ensure_ascii=False, indent=2) + "\n",
    root / "06_logs" / "production-stats.csv": csv_header(PRODUCTION_STATS_FIELDS),
    root / "06_logs" / "publish-ledger.csv": csv_header(PUBLISH_LEDGER_FIELDS),
    root / "11_templates" / "关键词收集" / "字幕纠错词库.tsv": (
      "# source\ttarget\tnote\n"
      "# Add local names, products, books, films, and recurring transcription fixes here.\n"
    ),
    root / "11_templates" / "关键词收集" / "专有名词清单.md": (
      "# 本地专有名词\n\n"
      "这里记录人名、产品名、书名、电影名和领域词汇。该文件默认不进入 Git。\n"
    ),
    root / "12_research" / "high-frequency-questions.md": (
      "# 高频问题清单\n\n"
      "这个文件用于记录反复值得讨论的问题，只保留问题和简短线索。\n\n"
      "## 待整理\n\n"
      "- \n\n"
      "## 使用规则\n\n"
      "- 生成脚本时只作为参考，不覆盖当天真实想法。\n"
      "- 每隔一段时间集中整理，不在当天出片时扩展系统。\n"
    ),
    root / "10_skills" / "personal-speaking-style" / "SKILL.md": (
      "# Personal Speaking Style\n\n"
      "Status: pending personalization.\n\n"
      "Use `00_system/defaults/speaking-style.md` until an AI has read the user-approved local "
      "corpus. Then replace this file with stable sentence rhythm, preferred transitions, words "
      "to keep or avoid, and a few source references. This file is ignored by Git.\n"
    ),
  }

  created_files = []
  existing_files = []
  for path, content in files.items():
    if write_text_if_missing(path, content):
      created_files.append(relative_path(root, path))
    else:
      existing_files.append(relative_path(root, path))

  return {
    "root": str(root),
    "systemVersion": package.get("version", "unknown"),
    "defaultContentType": system.get("defaultContentType", "video-diary"),
    "createdDirectories": created_directories,
    "existingDirectories": existing_directories,
    "createdFiles": created_files,
    "existingFiles": existing_files,
    "changed": bool(created_directories or created_files),
    "nextCommand": "npm run context",
  }


def build_ai_context(root: Path) -> Dict[str, Any]:
  root = root.resolve()
  require_core(root)

  public_read_order = [
    value for value in PUBLIC_AI_READ_ORDER
    if (root / value).is_file()
  ]
  local_overrides = [
    value for value in LOCAL_OVERRIDE_PATHS
    if (root / value).is_file()
  ]
  source_files = []
  for pattern in PERSONALIZATION_SOURCE_PATTERNS:
    source_files.extend(
      relative_path(root, path)
      for path in root.glob(pattern)
      if path.is_file()
    )
  source_files = sorted(set(source_files))

  personalization_path = root / "00_state" / "personalization.json"
  personalization = {}
  if personalization_path.is_file():
    personalization = json.loads(personalization_path.read_text(encoding="utf-8"))

  return {
    "root": str(root),
    "publicReadOrder": public_read_order,
    "localOverrides": local_overrides,
    "personalization": {
      "status": personalization.get("status", "missing"),
      "protocol": ".codex/skills/video-production-bootstrap/references/personalization.md",
      "sourcePatterns": PERSONALIZATION_SOURCE_PATTERNS,
      "sourceFileCount": len(source_files),
      "sourceFiles": source_files,
    },
    "nextActions": [
      "Read publicReadOrder in order.",
      "If personalization.status is pending, read sourceFiles and update only localOverrides.",
      "Run npm run doctor.",
      "Start the requested content workflow; default content type is video-diary.",
    ],
  }


def read_csv_header(path: Path) -> List[str]:
  if not path.is_file():
    return []
  with path.open("r", encoding="utf-8-sig", newline="") as file:
    return next(csv.reader(file), [])


def find_binary(name: str, candidates: List[Path] | None = None) -> str:
  for path in candidates or []:
    if path.is_file():
      return str(path)
  return shutil.which(name) or ""


def doctor_workspace(root: Path) -> Dict[str, Any]:
  root = root.resolve()
  checks = []

  def add(name: str, passed: bool, required: bool, detail: Any) -> None:
    checks.append({
      "name": name,
      "status": "pass" if passed else "fail",
      "required": required,
      "detail": detail,
    })

  package_path = root / "package.json"
  system_path = root / "00_system" / "system.json"
  package = json.loads(package_path.read_text(encoding="utf-8")) if package_path.exists() else {}
  system = json.loads(system_path.read_text(encoding="utf-8")) if system_path.exists() else {}
  active_release = system.get("activeRelease")
  package_version = package.get("version")
  add("core-files", package_path.is_file() and system_path.is_file(), True, str(root))
  missing_ai_entry = [
    value for value in PUBLIC_AI_READ_ORDER
    if not (root / value).is_file()
  ]
  add("ai-entry", not missing_ai_entry, True, missing_ai_entry)
  add(
    "release-identity",
    bool(active_release) and package_version == active_release,
    True,
    {"activeRelease": active_release, "packageVersion": package_version},
  )

  registry = validate_control_plane(root)
  add("registry", registry.get("valid", False), True, registry.get("errors", []))
  contracts = validate_contract_examples(root)
  add("contracts", contracts.get("valid", False), True, contracts.get("errors", []))

  missing_directories = [value for value in WORKSPACE_DIRECTORIES if not (root / value).is_dir()]
  add("workspace-directories", not missing_directories, True, missing_directories)

  ledgers = {
    "00_state/content-ledger.csv": CONTENT_LEDGER_FIELDS,
    "00_state/production-stats.csv": PRODUCTION_STATS_FIELDS,
    "00_state/publish-ledger.csv": PUBLISH_LEDGER_FIELDS,
  }
  bad_ledgers = [
    value for value, fields in ledgers.items()
    if read_csv_header(root / value) != fields
  ]
  add("workspace-ledgers", not bad_ledgers, True, bad_ledgers)

  missing_local_overrides = [
    value for value in LOCAL_OVERRIDE_PATHS
    if not (root / value).is_file()
  ]
  personalization_path = root / "00_state" / "personalization.json"
  personalization = {}
  if personalization_path.is_file():
    personalization = json.loads(personalization_path.read_text(encoding="utf-8"))
  personalization_status = personalization.get("status", "missing")
  add(
    "local-personalization-layer",
    not missing_local_overrides,
    True,
    {
      "status": personalization_status,
      "missing": missing_local_overrides,
    },
  )

  policy_path = root / "00_system" / "evolution-policy.json"
  policy = json.loads(policy_path.read_text(encoding="utf-8")) if policy_path.exists() else {}
  loop_ready = (
    isinstance(policy.get("topK"), int)
    and policy.get("topK", 0) > 0
    and (root / "00_state" / "observations").is_dir()
    and (root / "00_state" / "evolution").is_dir()
    and (root / "17_reports" / "evolution").is_dir()
  )
  add("daily-evolution-loop", loop_ready, True, {"topK": policy.get("topK")})

  ignore_path = root / ".gitignore"
  ignore_text = ignore_path.read_text(encoding="utf-8") if ignore_path.exists() else ""
  missing_patterns = [value for value in PRIVATE_IGNORE_PATTERNS if value not in ignore_text]
  add("private-data-boundary", not missing_patterns, True, missing_patterns)

  ffmpeg = find_binary("ffmpeg", [Path("/usr/local/opt/ffmpeg-full/bin/ffmpeg")])
  ffprobe = find_binary("ffprobe", [Path("/usr/local/opt/ffmpeg-full/bin/ffprobe")])
  node = find_binary("node")
  whisper = find_binary("whisper-cli", [Path("/usr/local/bin/whisper-cli")]) or find_binary("whisper")
  pillow = importlib.util.find_spec("PIL") is not None
  custom_font = os.environ.get("VIDEO_WORKSHOP_FONT", "").strip()
  cover_font_candidates = [
    Path(custom_font) if custom_font else None,
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    Path("C:/Windows/Fonts/msyhbd.ttc"),
    Path("C:/Windows/Fonts/msyh.ttc"),
  ]
  cover_font = next(
    (str(path) for path in cover_font_candidates if path and path.is_file()),
    "",
  )
  add("node", bool(node), False, node or "not found")
  add("ffmpeg", bool(ffmpeg), False, ffmpeg or "not found")
  add("ffprobe", bool(ffprobe), False, ffprobe or "not found")
  add("pillow", pillow, False, "installed" if pillow else "not found")
  add("cover-font", bool(cover_font), False, cover_font or "set VIDEO_WORKSHOP_FONT")
  add("transcription-engine", bool(whisper), False, whisper or "not found")

  required_failures = [
    check["name"] for check in checks
    if check["required"] and check["status"] != "pass"
  ]
  render_requirements = {"ffmpeg", "ffprobe", "pillow", "cover-font", "transcription-engine"}
  render_failures = [
    check["name"] for check in checks
    if check["name"] in render_requirements and check["status"] != "pass"
  ]
  valid = not required_failures
  return {
    "root": str(root),
    "valid": valid,
    "readyForContent": valid,
    "readyForRender": valid and not render_failures,
    "loopReady": loop_ready,
    "personalizationStatus": personalization_status,
    "defaultContentType": system.get("defaultContentType"),
    "activeRelease": active_release,
    "packageVersion": package_version,
    "checks": checks,
    "requiredFailures": required_failures,
    "renderWarnings": render_failures,
  }
