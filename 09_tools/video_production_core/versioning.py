"""Plan release targets for verified evolution work."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import re
import os
import tempfile


SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
VERSION_PLAN_SCHEMA_VERSION = 1
DEFAULT_VERSIONING_POLICY = {
  "automatic": True,
  "baseVersion": "",
  "baseVersionAt": "",
  "historicalCandidateIds": [],
  "bugfixBump": "patch",
  "featureBump": "minor",
  "majorRequiresUserConfirmation": True,
}


class VersioningError(ValueError):
  """Raised when release version metadata is invalid."""


def parse_version(value: str) -> Tuple[int, int, int]:
  match = SEMVER_RE.fullmatch(str(value).strip())
  if not match:
    raise VersioningError(f"Invalid SemVer: {value}")
  return tuple(int(part) for part in match.groups())


def format_version(parts: Tuple[int, int, int]) -> str:
  return ".".join(str(part) for part in parts)


def bump_version(current: str, change_type: str) -> str:
  major, minor, patch = parse_version(current)
  if change_type == "bugfix":
    return format_version((major, minor, patch + 1))
  if change_type == "feature":
    return format_version((major, minor + 1, 0))
  raise VersioningError(f"Automatic bump is not available for {change_type}.")


def proposed_major_version(current: str) -> str:
  major, _, _ = parse_version(current)
  return format_version((major + 1, 0, 0))


def _load_json(path: Path) -> Dict[str, Any]:
  return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
  content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
  path.parent.mkdir(parents=True, exist_ok=True)
  descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
  try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
      file.write(content)
      file.flush()
      os.fsync(file.fileno())
    os.replace(temporary_name, path)
  finally:
    if os.path.exists(temporary_name):
      os.unlink(temporary_name)


def _timestamp(value: str) -> datetime:
  raw = str(value or "").strip()
  if not raw:
    return datetime.min.replace(tzinfo=timezone.utc)
  try:
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
  except ValueError:
    return datetime.min.replace(tzinfo=timezone.utc)
  if parsed.tzinfo is None:
    return parsed.replace(tzinfo=timezone.utc)
  return parsed.astimezone(timezone.utc)


def load_versioning_policy(root: Path) -> Dict[str, Any]:
  release_policy_path = root / "00_system" / "release-policy.json"
  release_policy = _load_json(release_policy_path) if release_policy_path.exists() else {}
  configured = release_policy.get("versioning", {})
  versioning = {**DEFAULT_VERSIONING_POLICY, **configured}
  package = _load_json(root / "package.json")
  base_version = str(versioning.get("baseVersion") or package.get("version", "")).strip()
  parse_version(base_version)
  base_at = str(versioning.get("baseVersionAt") or "").strip()
  if base_at:
    _timestamp(base_at)
  historical_ids = {
    str(value).strip()
    for value in versioning.get("historicalCandidateIds", [])
    if str(value).strip()
  }
  return {
    **versioning,
    "baseVersion": base_version,
    "baseVersionAt": base_at,
    "historicalCandidateIds": sorted(historical_ids),
  }


def _completion_files(root: Path) -> List[Path]:
  directory = root / "00_state" / "evolution" / "completed"
  return sorted(directory.glob("*.json")) if directory.exists() else []


def _completion_records(root: Path) -> List[Dict[str, Any]]:
  records: List[Dict[str, Any]] = []
  for path in _completion_files(root):
    try:
      payload = _load_json(path)
    except (OSError, json.JSONDecodeError):
      continue
    for index, item in enumerate(payload.get("completed", [])):
      candidate_id = str(item.get("candidateId", "")).strip()
      if not candidate_id:
        continue
      records.append({
        **item,
        "_path": path,
        "_index": index,
      })
  return sorted(
    records,
    key=lambda item: (
      _timestamp(str(item.get("completedAt", ""))),
      str(item.get("candidateId", "")),
    ),
  )


def _is_historical(record: Dict[str, Any], policy: Dict[str, Any]) -> bool:
  candidate_id = str(record.get("candidateId", ""))
  if candidate_id in set(policy.get("historicalCandidateIds", [])):
    return True
  base_at = str(policy.get("baseVersionAt", "")).strip()
  return bool(base_at) and _timestamp(str(record.get("completedAt", ""))) <= _timestamp(base_at)


def build_version_plan(root: Path) -> Dict[str, Any]:
  root = Path(root).resolve()
  policy = load_versioning_policy(root)
  base_version = policy["baseVersion"]
  cursor = base_version
  planned_records: List[Dict[str, Any]] = []
  pending_major: List[Dict[str, Any]] = []

  for record in _completion_records(root):
    change_type = str(record.get("changeType", "")).strip()
    candidate_id = str(record.get("candidateId", "")).strip()
    historical = _is_historical(record, policy)
    release_target: Optional[str]
    version_decision: str

    if historical:
      release_target = base_version
      version_decision = (
        "historical-user-confirmed"
        if change_type == "major-evolution"
        else "historical-base"
      )
    elif not policy.get("automatic", True):
      release_target = None
      version_decision = "automatic-disabled"
    elif change_type == "major-evolution":
      release_target = None
      version_decision = "user-confirmation-required"
      pending_major.append({
        "candidateId": candidate_id,
        "summary": str(record.get("summary", "")),
        "completedAt": str(record.get("completedAt", "")),
        "proposedTarget": proposed_major_version(cursor),
      })
    elif change_type in {"bugfix", "feature"}:
      previous_version = cursor
      cursor = bump_version(cursor, change_type)
      release_target = cursor
      version_decision = "automatic-bump"
      record = {**record, "previousPlannedVersion": previous_version}
    else:
      release_target = None
      version_decision = "manual-review-required"

    planned_records.append({
      "candidateId": candidate_id,
      "summary": str(record.get("summary", "")),
      "completedAt": str(record.get("completedAt", "")),
      "changeType": change_type,
      "releaseTarget": release_target,
      "versionDecision": version_decision,
      "path": str(record["_path"].relative_to(root)),
      "index": record["_index"],
      "historical": historical,
    })

  package = _load_json(root / "package.json")
  system_path = root / "00_system" / "system.json"
  system = _load_json(system_path) if system_path.exists() else {}
  return {
    "schemaVersion": VERSION_PLAN_SCHEMA_VERSION,
    "automatic": bool(policy.get("automatic", True)),
    "baseVersion": base_version,
    "baseVersionAt": policy.get("baseVersionAt", ""),
    "packageVersion": str(package.get("version", "")),
    "activeRelease": str(system.get("activeRelease", "")),
    "lastPlannedVersion": cursor,
    "nextBugfixVersion": bump_version(cursor, "bugfix"),
    "nextFeatureVersion": bump_version(cursor, "feature"),
    "pendingMajor": pending_major,
    "records": planned_records,
  }


def apply_version_plan(root: Path) -> Dict[str, Any]:
  root = Path(root).resolve()
  plan = build_version_plan(root)
  records_by_path: Dict[str, List[Dict[str, Any]]] = {}
  for record in plan["records"]:
    records_by_path.setdefault(record["path"], []).append(record)

  changed_files: List[str] = []
  changed_records = 0
  for relative_path, records in records_by_path.items():
    path = root / relative_path
    payload = _load_json(path)
    changed = False
    for record in records:
      item = payload["completed"][record["index"]]
      expected = {
        "releaseTarget": record["releaseTarget"],
        "versionDecision": record["versionDecision"],
        "versionPlanBase": plan["baseVersion"],
      }
      if any(item.get(key) != value for key, value in expected.items()):
        item.update(expected)
        changed = True
        changed_records += 1
    if changed:
      _atomic_write_json(path, payload)
      changed_files.append(relative_path)

  return {
    **plan,
    "applied": True,
    "changedFiles": changed_files,
    "changedRecords": changed_records,
  }
