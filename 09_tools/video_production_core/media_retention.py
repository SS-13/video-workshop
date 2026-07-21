"""Safe, opt-in retention for completed local video media."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
import csv
import json
import os
import shutil
import tempfile


VIDEO_EXTENSIONS = {
  ".avi",
  ".m4v",
  ".mkv",
  ".mov",
  ".mp4",
  ".webm",
}
MEDIA_ROOTS = {
  "recordings": "03_recordings",
  "working-videos": "04_videos",
  "exports": "05_exports",
}
DEFAULT_RETENTION_DAYS = 3
DEFAULT_MINIMUM_FREE_BYTES = 5 * 1024 * 1024 * 1024
LEDGER_FIELDS = [
  "deleted_at",
  "as_of_date",
  "cutoff_date",
  "content_id",
  "stage",
  "path",
  "bytes",
  "manifest",
]


class MediaRetentionError(Exception):
  """Raised when retention configuration or execution is unsafe."""


def now_iso() -> str:
  return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_date(value: str) -> date:
  try:
    return date.fromisoformat(value)
  except ValueError as error:
    raise MediaRetentionError(f"Invalid date: {value}") from error


def relative_path(root: Path, path: Path) -> str:
  return path.resolve().relative_to(root.resolve()).as_posix()


def inside(path: Path, parent: Path) -> bool:
  try:
    path.resolve().relative_to(parent.resolve())
  except ValueError:
    return False
  return True


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  descriptor, temporary = tempfile.mkstemp(
    dir=path.parent,
    prefix=f".{path.name}.",
    suffix=".tmp",
  )
  try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
      json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
      file.write("\n")
      file.flush()
      os.fsync(file.fileno())
    os.replace(temporary, path)
  finally:
    if os.path.exists(temporary):
      os.unlink(temporary)


def load_workspace(root: Path) -> Tuple[Path, Dict[str, Any]]:
  path = root / "00_state" / "workspace.json"
  if not path.is_file():
    raise MediaRetentionError("Workspace is not initialized: 00_state/workspace.json")
  try:
    payload = json.loads(path.read_text(encoding="utf-8"))
  except json.JSONDecodeError as error:
    raise MediaRetentionError(f"Invalid workspace configuration: {error}") from error
  if not isinstance(payload, dict):
    raise MediaRetentionError("Workspace configuration must be a JSON object.")
  return path, payload


def normalize_config(workspace: Dict[str, Any]) -> Dict[str, Any]:
  raw = workspace.get("mediaRetention", {})
  if not isinstance(raw, dict):
    raise MediaRetentionError("mediaRetention must be a JSON object.")
  enabled = raw.get("enabled", False)
  days = raw.get("retentionDays", DEFAULT_RETENTION_DAYS)
  minimum_free_bytes = raw.get("minimumFreeBytes", DEFAULT_MINIMUM_FREE_BYTES)
  if not isinstance(enabled, bool):
    raise MediaRetentionError("mediaRetention.enabled must be boolean.")
  if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365:
    raise MediaRetentionError("mediaRetention.retentionDays must be between 1 and 365.")
  if (
    isinstance(minimum_free_bytes, bool)
    or not isinstance(minimum_free_bytes, int)
    or minimum_free_bytes < 0
  ):
    raise MediaRetentionError("mediaRetention.minimumFreeBytes must be a non-negative integer.")
  return {
    "enabled": enabled,
    "retentionDays": days,
    "minimumFreeBytes": minimum_free_bytes,
    "mediaRoots": list(MEDIA_ROOTS.values()),
    "videoExtensions": sorted(VIDEO_EXTENSIONS),
    "requirePublishReady": True,
    "requireProductionStats": True,
  }


def get_retention_config(root: Path) -> Dict[str, Any]:
  _, workspace = load_workspace(root)
  return normalize_config(workspace)


def disk_space_status(root: Path) -> Dict[str, Any]:
  config = get_retention_config(root)
  usage = shutil.disk_usage(root)
  minimum_free_bytes = config["minimumFreeBytes"]
  return {
    "ready": usage.free >= minimum_free_bytes,
    "freeBytes": usage.free,
    "minimumFreeBytes": minimum_free_bytes,
    "retentionEnabled": config["enabled"],
  }


def configure_retention(
  root: Path,
  enabled: bool | None = None,
  retention_days: int | None = None,
) -> Dict[str, Any]:
  path, workspace = load_workspace(root)
  current = normalize_config(workspace)
  if enabled is not None:
    current["enabled"] = enabled
  if retention_days is not None:
    current["retentionDays"] = retention_days
  validated = normalize_config({"mediaRetention": current})
  workspace["mediaRetention"] = {
    "enabled": validated["enabled"],
    "retentionDays": validated["retentionDays"],
    "minimumFreeBytes": validated["minimumFreeBytes"],
  }
  workspace["updatedAt"] = now_iso()
  atomic_write_json(path, workspace)
  return validated


def active_production_locks(root: Path) -> List[str]:
  lock_root = root / "00_state" / "locks"
  if not lock_root.is_dir():
    return []
  return sorted(
    relative_path(root, path)
    for path in lock_root.glob("production-*.lock.json")
    if path.is_file()
  )


def production_content_ids(root: Path) -> set[str]:
  path = root / "00_state" / "production-stats.csv"
  if not path.is_file():
    return set()
  with path.open(encoding="utf-8", newline="") as file:
    return {
      str(row.get("content_id", "")).strip()
      for row in csv.DictReader(file)
      if str(row.get("content_id", "")).strip()
    }


def discover_content_keys(root: Path) -> List[Tuple[str, str, str]]:
  keys = set()
  for root_name in MEDIA_ROOTS.values():
    stage_root = root / root_name
    if not stage_root.is_dir():
      continue
    for date_path in stage_root.iterdir():
      if not date_path.is_dir():
        continue
      try:
        parse_date(date_path.name)
      except MediaRetentionError:
        continue
      for content_path in date_path.iterdir():
        if not content_path.is_dir():
          continue
        for sequence_path in content_path.iterdir():
          if sequence_path.is_dir():
            keys.add((date_path.name, content_path.name, sequence_path.name))
  return sorted(keys)


def evaluate_content(
  root: Path,
  key: Tuple[str, str, str],
  cutoff: date,
  known_content_ids: set[str],
) -> Tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
  date_value, content_type, sequence = key
  content_date = parse_date(date_value)
  base = {
    "date": date_value,
    "contentType": content_type,
    "sequence": sequence,
  }
  if content_date > cutoff:
    return None, {**base, "reason": "retention-window"}
  package_path = (
    root / "05_exports" / date_value / content_type / sequence / "publish-package.json"
  )
  if not package_path.is_file():
    return None, {**base, "reason": "publish-package-missing"}
  try:
    package = json.loads(package_path.read_text(encoding="utf-8"))
  except json.JSONDecodeError:
    return None, {**base, "reason": "publish-package-invalid"}
  production = package.get("production", {})
  content_id = str(package.get("contentId", "")).strip()
  if package.get("publishReady") is not True:
    return None, {**base, "contentId": content_id, "reason": "publish-not-ready"}
  if not isinstance(production, dict) or production.get("statsRecorded") is not True:
    return None, {**base, "contentId": content_id, "reason": "stats-not-recorded"}
  if content_id not in known_content_ids:
    return None, {**base, "contentId": content_id, "reason": "production-row-missing"}
  return {
    **base,
    "contentId": content_id,
    "publishPackage": relative_path(root, package_path),
  }, None


def video_files_for_content(
  root: Path,
  content: Dict[str, Any],
) -> Iterable[Dict[str, Any]]:
  for stage, root_name in MEDIA_ROOTS.items():
    stage_root = root / root_name
    content_root = (
      stage_root
      / content["date"]
      / content["contentType"]
      / content["sequence"]
    )
    if not content_root.is_dir():
      continue
    for path in sorted(content_root.rglob("*")):
      if not path.is_file() or path.is_symlink() or path.suffix.lower() not in VIDEO_EXTENSIONS:
        continue
      if not inside(path, stage_root):
        continue
      yield {
        "path": relative_path(root, path),
        "bytes": path.stat().st_size,
        "date": content["date"],
        "contentType": content["contentType"],
        "sequence": content["sequence"],
        "contentId": content["contentId"],
        "stage": stage,
      }


def build_retention_plan(root: Path, as_of_date: str) -> Dict[str, Any]:
  root = root.resolve()
  config = get_retention_config(root)
  target_date = parse_date(as_of_date)
  cutoff = target_date - timedelta(days=config["retentionDays"])
  known_content_ids = production_content_ids(root)
  eligible = []
  protected = []
  for key in discover_content_keys(root):
    content, reason = evaluate_content(root, key, cutoff, known_content_ids)
    if content:
      eligible.append(content)
    elif reason:
      protected.append(reason)
  candidates = sorted(
    (
      file
      for content in eligible
      for file in video_files_for_content(root, content)
    ),
    key=lambda item: item["path"],
  )
  disk_status = disk_space_status(root)
  return {
    "asOfDate": target_date.isoformat(),
    "cutoffDate": cutoff.isoformat(),
    "config": config,
    "productionLocks": active_production_locks(root),
    "freeBytes": disk_status["freeBytes"],
    "eligibleContents": eligible,
    "protectedContents": protected,
    "candidateFiles": candidates,
    "candidateCount": len(candidates),
    "candidateBytes": sum(item["bytes"] for item in candidates),
  }


def append_ledger(
  root: Path,
  item: Dict[str, Any],
  plan: Dict[str, Any],
  manifest_path: Path,
  deleted_at: str,
) -> None:
  path = root / "00_state" / "media-retention-ledger.csv"
  path.parent.mkdir(parents=True, exist_ok=True)
  is_new = not path.exists()
  with path.open("a", encoding="utf-8", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=LEDGER_FIELDS)
    if is_new:
      writer.writeheader()
    writer.writerow({
      "deleted_at": deleted_at,
      "as_of_date": plan["asOfDate"],
      "cutoff_date": plan["cutoffDate"],
      "content_id": item["contentId"],
      "stage": item["stage"],
      "path": item["path"],
      "bytes": str(item["bytes"]),
      "manifest": relative_path(root, manifest_path),
    })
    file.flush()
    os.fsync(file.fileno())


def run_retention(
  root: Path,
  as_of_date: str,
  apply: bool = False,
  if_enabled: bool = False,
) -> Dict[str, Any]:
  root = root.resolve()
  plan = build_retention_plan(root, as_of_date)
  if not plan["config"]["enabled"]:
    if not if_enabled:
      raise MediaRetentionError(
        "Media retention is disabled. Enable it with vp cleanup configure --enabled."
      )
    return {**plan, "mode": "apply" if apply else "dry-run", "status": "skipped", "reason": "disabled"}
  if plan["productionLocks"]:
    return {**plan, "mode": "apply" if apply else "dry-run", "status": "skipped", "reason": "production-lock"}
  if not apply:
    return {**plan, "mode": "dry-run", "status": "planned", "reason": ""}

  started_at = now_iso()
  manifest_id = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f%z")
  manifest_path = root / "06_logs" / "media-retention" / f"{manifest_id}.json"
  result = {
    **plan,
    "mode": "apply",
    "status": "running",
    "reason": "",
    "startedAt": started_at,
    "completedAt": "",
    "manifest": relative_path(root, manifest_path),
    "deletedFiles": [],
    "deletedBytes": 0,
    "skippedFiles": [],
    "failures": [],
  }
  atomic_write_json(manifest_path, result)

  for item in plan["candidateFiles"]:
    locks = active_production_locks(root)
    if locks:
      result["status"] = "deferred"
      result["reason"] = "production-lock"
      result["productionLocks"] = locks
      break
    path = (root / item["path"]).resolve()
    allowed_root = root / MEDIA_ROOTS[item["stage"]]
    if not inside(path, allowed_root) or path.is_symlink():
      result["skippedFiles"].append({**item, "reason": "unsafe-path"})
      atomic_write_json(manifest_path, result)
      continue
    if not path.is_file():
      result["skippedFiles"].append({**item, "reason": "missing"})
      atomic_write_json(manifest_path, result)
      continue
    current_size = path.stat().st_size
    if current_size != item["bytes"]:
      result["skippedFiles"].append({**item, "reason": "size-changed"})
      atomic_write_json(manifest_path, result)
      continue
    try:
      path.unlink()
      deleted_at = now_iso()
      append_ledger(root, item, plan, manifest_path, deleted_at)
      result["deletedFiles"].append({**item, "deletedAt": deleted_at})
      result["deletedBytes"] += item["bytes"]
    except OSError as error:
      result["failures"].append({**item, "error": str(error)})
      result["status"] = "partial-failure"
      result["reason"] = "file-delete-failed"
      atomic_write_json(manifest_path, result)
      break
    atomic_write_json(manifest_path, result)

  if result["status"] == "running":
    result["status"] = "completed"
  result["completedAt"] = now_iso()
  result["freeBytesAfter"] = shutil.disk_usage(root).free
  atomic_write_json(manifest_path, result)
  return result
