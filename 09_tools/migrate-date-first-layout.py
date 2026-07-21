#!/usr/bin/env python3
"""Migrate local content into date/content-type/sequence layout."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile

from video_production_core.content_layout import ContentRef, CONTENT_TYPES


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TEXT_ROOTS = ("01_inbox", "02_scripts", "06_logs")
MEDIA_ROOTS = ("03_recordings", "04_videos", "05_exports", "15_cover_gallery")
TEXT_SUFFIXES = {".md", ".json", ".csv", ".txt", ".tsv", ".ffmpeg", ".yaml", ".yml"}
EXCLUDED_PARTS = {"shadow", "canary"}


def file_hash(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as file:
    for chunk in iter(lambda: file.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def content_target(root: Path, stage: str, date: str) -> Path:
  ref = ContentRef(date, "video-diary", "001")
  return ref.text_path(root, stage) if stage in TEXT_ROOTS else ref.media_dir(root, stage)


def is_content_type_directory(path: Path) -> bool:
  return path.is_dir() and path.name in CONTENT_TYPES


def build_operations(root: Path) -> list[dict[str, Any]]:
  operations = []
  for stage in TEXT_ROOTS:
    stage_root = root / stage
    if not stage_root.is_dir():
      continue
    for source in sorted(stage_root.glob("*.md")):
      date = source.stem
      if not DATE_RE.fullmatch(date):
        continue
      target = content_target(root, stage, date)
      operations.append({
        "action": "move",
        "stage": stage,
        "source": source,
        "target": target,
      })

  for stage in MEDIA_ROOTS:
    stage_root = root / stage
    if not stage_root.is_dir():
      continue
    for date_dir in sorted(stage_root.iterdir()):
      if not date_dir.is_dir() or not DATE_RE.fullmatch(date_dir.name):
        continue
      target_dir = content_target(root, stage, date_dir.name)
      for source in sorted(date_dir.iterdir()):
        if is_content_type_directory(source):
          continue
        target = target_dir / source.name
        operations.append({
          "action": "link" if stage == "03_recordings" else "move",
          "stage": stage,
          "source": source,
          "target": target,
        })
  return operations


def operation_conflict(operation: dict[str, Any]) -> str:
  source = operation["source"]
  target = operation["target"]
  if not source.exists():
    return ""
  if not target.exists():
    return ""
  if source.is_file() and target.is_file():
    try:
      if os.path.samefile(source, target) or (
        source.stat().st_size == target.stat().st_size
        and file_hash(source) == file_hash(target)
      ):
        return ""
    except OSError:
      pass
  return f"Target already exists with different content: {target}"


def atomic_write(path: Path, text: str) -> None:
  descriptor, temporary_name = tempfile.mkstemp(prefix=f"{path.name}-", dir=str(path.parent))
  try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
      file.write(text)
    os.replace(temporary_name, path)
  finally:
    if os.path.exists(temporary_name):
      os.unlink(temporary_name)


def link_file(source: Path, target: Path) -> None:
  target.parent.mkdir(parents=True, exist_ok=True)
  if target.exists():
    return
  try:
    os.link(source, target)
  except OSError:
    shutil.copy2(source, target)


def link_tree(source: Path, target: Path) -> None:
  if source.is_file():
    link_file(source, target)
    return
  target.mkdir(parents=True, exist_ok=True)
  for child in source.iterdir():
    link_tree(child, target / child.name)


def apply_operation(operation: dict[str, Any]) -> str:
  source = operation["source"]
  target = operation["target"]
  if not source.exists():
    return "source-missing"
  if target.exists():
    return "already-migrated"
  target.parent.mkdir(parents=True, exist_ok=True)
  if operation["action"] == "link":
    link_tree(source, target)
    return "linked-original-preserved"
  shutil.move(str(source), str(target))
  return "moved"


def rewrite_layout_references(text: str) -> str:
  text = re.sub(
    r"(01_inbox|02_scripts|06_logs)/(\d{4}-\d{2}-\d{2})\.md",
    r"\1/\2/video-diary/001.md",
    text,
  )
  text = re.sub(
    r"(03_recordings|04_videos|05_exports|15_cover_gallery)/(\d{4}-\d{2}-\d{2})/"
    r"(?!(?:video-diary|suisuinian|reading-note)/\d{3}(?:/|$))",
    r"\1/\2/video-diary/001/",
    text,
  )
  return text


def rewrite_active_references(root: Path, apply: bool) -> list[dict[str, str]]:
  scan_roots = [root / value for value in (*TEXT_ROOTS, *MEDIA_ROOTS, "00_state")]
  changed = []
  for scan_root in scan_roots:
    if not scan_root.is_dir():
      continue
    for path in scan_root.rglob("*"):
      if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
        continue
      relative_parts = path.relative_to(root).parts
      if any(part in EXCLUDED_PARTS for part in relative_parts):
        continue
      try:
        original = path.read_text(encoding="utf-8")
      except UnicodeDecodeError:
        continue
      updated = rewrite_layout_references(original)
      if updated == original:
        continue
      changed.append({"path": str(path.relative_to(root)), "status": "updated" if apply else "planned"})
      if apply:
        atomic_write(path, updated)
  return changed


def verify_operations(operations: list[dict[str, Any]]) -> list[dict[str, str]]:
  results = []
  for operation in operations:
    source = operation["source"]
    target = operation["target"]
    status = "missing"
    if target.is_file():
      if source.is_file() and operation["action"] == "link":
        status = "pass" if file_hash(source) == file_hash(target) else "hash-mismatch"
      else:
        status = "pass"
    elif target.is_dir():
      status = "pass"
    results.append({"target": str(target), "status": status})
  return results


def serialize_operation(root: Path, operation: dict[str, Any]) -> dict[str, str]:
  return {
    "action": operation["action"],
    "stage": operation["stage"],
    "source": str(operation["source"].relative_to(root)),
    "target": str(operation["target"].relative_to(root)),
  }


def main() -> int:
  parser = argparse.ArgumentParser(description="Migrate all local content to date-first layout.")
  parser.add_argument("--root", default=".")
  parser.add_argument("--apply", action="store_true")
  parser.add_argument("--report", default="17_reports/migrations/date-first-layout.json")
  args = parser.parse_args()

  root = Path(args.root).expanduser().resolve()
  operations = build_operations(root)
  conflicts = [value for value in (operation_conflict(item) for item in operations) if value]
  if conflicts:
    for conflict in conflicts:
      print(f"conflict={conflict}")
    return 2

  results = []
  if args.apply:
    for operation in operations:
      results.append({
        **serialize_operation(root, operation),
        "status": apply_operation(operation),
      })
  else:
    results = [{**serialize_operation(root, item), "status": "planned"} for item in operations]

  references = rewrite_active_references(root, args.apply)
  verification = verify_operations(operations) if args.apply else []
  report = {
    "schemaVersion": 1,
    "mode": "apply" if args.apply else "dry-run",
    "layout": "stage/date/content-type/sequence",
    "defaultHistoricalClassification": "video-diary/001",
    "originalRecordingPolicy": "hard-link or copy; legacy original preserved",
    "shadowCanaryModified": False,
    "operationCount": len(results),
    "referenceUpdateCount": len(references),
    "conflicts": conflicts,
    "operations": results,
    "referenceUpdates": references,
    "verification": verification,
  }
  report_path = root / args.report
  report_path.parent.mkdir(parents=True, exist_ok=True)
  atomic_write(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")

  failed = [item for item in verification if item["status"] != "pass"]
  print(f"mode={report['mode']}")
  print(f"operations={len(results)}")
  print(f"reference_updates={len(references)}")
  print(f"conflicts={len(conflicts)}")
  print(f"verification_failures={len(failed)}")
  print(f"report={report_path.relative_to(root)}")
  return 0 if not failed else 3


if __name__ == "__main__":
  raise SystemExit(main())
