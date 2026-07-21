"""Persistent run state for the generic video production control plane."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import fcntl
import json
import os
import re
import tempfile

from video_production_core.contracts import load_json, validate_value
from video_production_core.registry import get_content_types, get_profile


RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
RUN_STAGES = [
  "created",
  "input_review",
  "script",
  "recording",
  "cover",
  "subtitles",
  "combined_review",
  "compliance",
  "render",
  "publish_package",
  "log",
  "output_review",
  "completed",
]
STEP_DEFINITIONS = [
  ("input_review", "compliance-agent"),
  ("script", "text-agent"),
  ("recording", "orchestrator"),
  ("cover", "video-agent"),
  ("subtitles", "video-agent"),
  ("combined_review", "orchestrator"),
  ("compliance", "compliance-agent"),
  ("render", "video-agent"),
  ("publish_package", "video-agent"),
  ("log", "video-agent"),
  ("output_review", "compliance-agent"),
]


class RunStateError(Exception):
  pass


def now_iso() -> str:
  return datetime.now().astimezone().isoformat(timespec="seconds")


def validate_run_id(run_id: str) -> str:
  if not RUN_ID_RE.fullmatch(run_id):
    raise RunStateError("Run id may contain only letters, numbers, dot, underscore, and hyphen.")
  return run_id


def load_system(root: Path) -> Dict[str, Any]:
  return load_json(root / "00_system" / "system.json")


def run_root(root: Path) -> Path:
  system = load_system(root)
  return root / system.get("runRoot", "00_state/runs")


def run_path(root: Path, run_id: str) -> Path:
  return run_root(root) / validate_run_id(run_id) / "run.json"


def lock_path(root: Path, run_id: str) -> Path:
  return root / "00_state" / "locks" / f"run-{validate_run_id(run_id)}.lock"


@contextmanager
def run_lock(root: Path, run_id: str):
  path = lock_path(root, run_id)
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("a+", encoding="utf-8") as file:
    fcntl.flock(file.fileno(), fcntl.LOCK_EX)
    try:
      yield
    finally:
      fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  descriptor, temporary_name = tempfile.mkstemp(prefix="run-", suffix=".json", dir=str(path.parent))
  try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
      json.dump(payload, file, ensure_ascii=False, indent=2)
      file.write("\n")
    os.replace(temporary_name, path)
  finally:
    if os.path.exists(temporary_name):
      os.unlink(temporary_name)


def default_run_id(root: Path, date: str, content_type: str, sequence: str = "001") -> str:
  if content_type == "video-diary" and sequence == "001":
    counter_path = root / "00_state" / "day-counter.json"
    if counter_path.exists():
      counter = load_json(counter_path)
      if counter.get("updatedAt") == date and counter.get("lastContentId"):
        return validate_run_id(str(counter["lastContentId"]))
  return validate_run_id(f"{date}_{content_type}_{sequence}")


def system_version(root: Path, channel: str) -> str:
  system = load_system(root)
  if channel in {"candidate", "canary"}:
    return str(system.get("candidateRelease", ""))
  return str(system.get("activeRelease", ""))


def start_run(
  root: Path,
  date: str,
  content_type: str,
  title: str = "",
  run_id: Optional[str] = None,
  channel: str = "stable",
  actor: str = "cli",
  sequence: str = "001",
) -> Dict[str, Any]:
  content_types = {item["id"]: item for item in get_content_types(root, enabled_only=True)}
  if content_type not in content_types:
    raise RunStateError(f"Unknown or disabled content type: {content_type}")
  content = content_types[content_type]
  profile = get_profile(root, content["profile"])
  resolved_id = validate_run_id(run_id) if run_id else default_run_id(
    root, date, content_type, sequence
  )
  path = run_path(root, resolved_id)
  with run_lock(root, resolved_id):
    if path.exists():
      existing = load_json(path)
      if (
        existing.get("date") != date
        or existing.get("contentType") != content_type
        or existing.get("sequence", "001") != sequence
      ):
        raise RunStateError(f"Run id already belongs to another content item: {resolved_id}")
      if existing.get("channel") != channel:
        raise RunStateError(
          f"Run id already belongs to another channel: {resolved_id} "
          f"({existing.get('channel')} != {channel})"
        )
      return {**existing, "reused": True}

    timestamp = now_iso()
    run = {
      "schemaVersion": 1,
      "id": resolved_id,
      "workflowId": profile["id"],
      "contentType": content_type,
      "sequence": sequence,
      "date": date,
      "title": title,
      "channel": channel,
      "systemVersion": system_version(root, channel),
      "status": "pending",
      "currentStage": "created",
      "revision": 0,
      "publishReady": False,
      "createdAt": timestamp,
      "updatedAt": timestamp,
      "updatedBy": actor,
      "steps": [
        {
          "id": step_id,
          "status": "pending",
          "ownerAgent": owner_agent,
          "startedAt": None,
          "completedAt": None,
          "note": "",
        }
        for step_id, owner_agent in STEP_DEFINITIONS
      ],
      "artifacts": [],
    }
    atomic_write_json(path, run)
    return {**run, "reused": False}


def get_run(root: Path, run_id: str) -> Dict[str, Any]:
  path = run_path(root, run_id)
  if not path.exists():
    raise RunStateError(f"Run not found: {run_id}")
  return load_json(path)


def list_runs(root: Path) -> List[Dict[str, Any]]:
  directory = run_root(root)
  if not directory.exists():
    return []
  runs = []
  for path in sorted(directory.glob("*/run.json")):
    runs.append(load_json(path))
  return sorted(runs, key=lambda item: item.get("updatedAt", ""), reverse=True)


def advance_run(
  root: Path,
  run_id: str,
  stage: str,
  step_status: str = "succeeded",
  actor: str = "cli",
  note: str = "",
  publish_ready: Optional[bool] = None,
) -> Dict[str, Any]:
  if stage not in RUN_STAGES:
    raise RunStateError(f"Unknown run stage: {stage}")
  with run_lock(root, run_id):
    run = get_run(root, run_id)
    current_index = RUN_STAGES.index(run.get("currentStage", "created"))
    target_index = RUN_STAGES.index(stage)
    if target_index < current_index:
      raise RunStateError(
        f"Run stage cannot move backwards: {run.get('currentStage')} -> {stage}"
      )
    if target_index > current_index + 1:
      raise RunStateError(
        f"Run stage must advance one step at a time: {run.get('currentStage')} -> {stage}"
      )
    timestamp = now_iso()
    for step in run.get("steps", []):
      if step.get("id") != stage:
        continue
      step["status"] = step_status
      if step_status == "running" and not step.get("startedAt"):
        step["startedAt"] = timestamp
      if step_status == "succeeded":
        step["startedAt"] = step.get("startedAt") or timestamp
        step["completedAt"] = timestamp
      if note:
        step["note"] = note

    if step_status == "failed":
      run["status"] = "failed"
    elif stage == "combined_review" and step_status != "succeeded":
      run["status"] = "waiting_user"
    elif stage == "completed":
      run["status"] = "succeeded"
    else:
      run["status"] = "running"
    run["currentStage"] = stage
    if publish_ready is not None:
      run["publishReady"] = publish_ready
    run["revision"] = int(run.get("revision", 0)) + 1
    run["updatedAt"] = timestamp
    run["updatedBy"] = actor
    atomic_write_json(run_path(root, run_id), run)
    return run


def relative_path(root: Path, path: Path) -> str:
  try:
    return str(path.resolve().relative_to(root.resolve()))
  except ValueError:
    return str(path.resolve())


def register_artifact(
  root: Path,
  run_id: str,
  artifact_id: str,
  step_id: str,
  artifact_type: str,
  label: str,
  path_value: str,
  mime_type: Optional[str] = None,
  duration_seconds: Optional[float] = None,
  actor: str = "cli",
) -> Dict[str, Any]:
  validate_run_id(artifact_id)
  path = Path(path_value)
  if not path.is_absolute():
    path = root / path
  available = path.is_file()
  artifact = {
    "id": artifact_id,
    "runId": run_id,
    "stepId": step_id,
    "type": artifact_type,
    "label": label,
    "mimeType": mime_type,
    "relativePath": relative_path(root, path),
    "available": available,
    "sizeBytes": path.stat().st_size if available else None,
    "durationSeconds": duration_seconds,
  }
  schema = load_json(root / "00_system" / "contracts" / "schemas" / "artifact.schema.json")
  errors = validate_value(artifact, schema)
  if errors:
    raise RunStateError("Invalid artifact: " + "; ".join(errors))

  with run_lock(root, run_id):
    run = get_run(root, run_id)
    artifacts = [item for item in run.get("artifacts", []) if item.get("id") != artifact_id]
    artifacts.append(artifact)
    run["artifacts"] = artifacts
    run["revision"] = int(run.get("revision", 0)) + 1
    run["updatedAt"] = now_iso()
    run["updatedBy"] = actor
    atomic_write_json(run_path(root, run_id), run)
  return artifact


def validate_run(root: Path, run_id: str) -> Dict[str, Any]:
  run = get_run(root, run_id)
  run_schema = load_json(root / "00_system" / "contracts" / "schemas" / "run.schema.json")
  artifact_schema = load_json(root / "00_system" / "contracts" / "schemas" / "artifact.schema.json")
  errors = [{"scope": "run", "error": error} for error in validate_value(run, run_schema)]
  for artifact in run.get("artifacts", []):
    for error in validate_value(artifact, artifact_schema):
      errors.append({"scope": artifact.get("id", "artifact"), "error": error})
  return {
    "valid": not errors,
    "runId": run_id,
    "status": run.get("status"),
    "currentStage": run.get("currentStage"),
    "revision": run.get("revision"),
    "artifactCount": len(run.get("artifacts", [])),
    "errors": errors,
  }
