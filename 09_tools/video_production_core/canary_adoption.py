"""Adopt one completed Stable production into a tracked 3.0 Canary run."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import csv
import json
import re

from video_production_core.canary_validation import validate_real_canary
from video_production_core.contracts import load_json, validate_value
from video_production_core.release_transition import atomic_write_json, now_iso
from video_production_core.run_store import (
  RUN_STAGES,
  RunStateError,
  advance_run,
  register_artifact,
  start_run,
  validate_run_id,
)


MIME_TYPES = {
  "text": "text/markdown",
  "subtitle": "application/x-subrip",
  "image": "image/jpeg",
  "video": "video/mp4",
  "json": "application/json",
  "report": "text/markdown",
}


def resolve_path(root: Path, value: str) -> Path:
  path = Path(value).expanduser()
  if not path.is_absolute():
    path = root / path
  return path.resolve()


def relative_or_absolute(root: Path, path: Path) -> str:
  try:
    return str(path.resolve().relative_to(root.resolve()))
  except ValueError:
    return str(path.resolve())


def require_file(root: Path, value: str, label: str) -> Path:
  path = resolve_path(root, value)
  if not path.is_file():
    raise RunStateError(f"Missing {label}: {path}")
  return path


def production_row(root: Path, content_id: str) -> Optional[Dict[str, str]]:
  path = root / "00_state" / "production-stats.csv"
  if not path.exists():
    return None
  with path.open("r", encoding="utf-8-sig", newline="") as file:
    for row in csv.DictReader(file):
      if row.get("content_id") == content_id:
        return row
  return None


def production_path(root: Path, path: Path, expected_root: str, label: str) -> None:
  try:
    relative = path.relative_to(root.resolve())
  except ValueError as error:
    raise RunStateError(f"{label} must be inside the workspace: {path}") from error
  if not relative.parts or relative.parts[0] != expected_root or "shadow" in relative.parts:
    raise RunStateError(f"{label} is not a real production artifact: {relative}")


def optional_script(root: Path, date: str, explicit: Optional[str]) -> Optional[Path]:
  if explicit:
    return require_file(root, explicit, "script")
  candidate = root / "02_scripts" / f"{date}.md"
  return candidate.resolve() if candidate.is_file() else None


def optional_recording(root: Path, date: str, explicit: Optional[str]) -> Optional[Path]:
  if explicit:
    return require_file(root, explicit, "recording")
  directory = root / "03_recordings" / date
  if not directory.exists():
    return None
  candidates = [
    path.resolve()
    for path in directory.iterdir()
    if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".m4v"}
  ]
  if len(candidates) == 1:
    return candidates[0]
  return None


def register(
  root: Path,
  run_id: str,
  artifact_id: str,
  step: str,
  artifact_type: str,
  label: str,
  path: Path,
  actor: str,
) -> Dict[str, Any]:
  mime_type = MIME_TYPES[artifact_type]
  if path.suffix.lower() == ".png":
    mime_type = "image/png"
  elif path.suffix.lower() == ".csv":
    mime_type = "text/csv"
  elif path.suffix.lower() == ".mov":
    mime_type = "video/quicktime"
  return register_artifact(
    root,
    run_id=run_id,
    artifact_id=artifact_id,
    step_id=step,
    artifact_type=artifact_type,
    label=label,
    path_value=str(path),
    mime_type=mime_type,
    actor=actor,
  )


def advance_if_needed(
  root: Path,
  run: Dict[str, Any],
  stage: str,
  actor: str,
  note: str,
  step_status: str = "succeeded",
  publish_ready: Optional[bool] = None,
) -> Dict[str, Any]:
  current_index = RUN_STAGES.index(run.get("currentStage", "created"))
  target_index = RUN_STAGES.index(stage)
  if target_index <= current_index:
    return run
  return advance_run(
    root,
    run_id=run["id"],
    stage=stage,
    step_status=step_status,
    actor=actor,
    note=note,
    publish_ready=publish_ready,
  )


def finalize_prepared_run(
  root: Path,
  date: str,
  package_path: Path,
  package: Dict[str, Any],
  content_type: str,
  channel: str,
  script_path: Optional[str],
  recording_path: Optional[str],
  actor: str,
) -> Dict[str, Any]:
  if package.get("publishReady") is not True:
    raise RunStateError("Run finalization requires publishReady=true.")
  production = package.get("production", {})
  if production.get("statsRecorded") is not True:
    raise RunStateError("Run finalization requires recorded production statistics.")
  if production.get("subtitleQc") != "pass" or production.get("compliance") != "pass":
    raise RunStateError("Run finalization requires passed subtitle and compliance checks.")

  run_id = validate_run_id(str(package.get("runId", "")).strip())
  content_id = str(package.get("contentId", "")).strip()
  if not content_id:
    raise RunStateError("Publish package requires contentId.")
  stats = production_row(root, content_id)
  if stats is None:
    raise RunStateError(f"Production statistics do not contain content_id={content_id}.")

  artifacts = package["artifacts"]
  video = require_file(root, artifacts["video"], "final video")
  cover_3x4 = require_file(root, artifacts["cover3x4"], "3:4 cover")
  cover_4x3 = require_file(root, artifacts["cover4x3"], "4:3 cover")
  srt = require_file(root, artifacts["srt"], "corrected SRT")
  production_path(root, video, "05_exports", "Final video")
  production_path(root, cover_3x4, "05_exports", "3:4 cover")
  production_path(root, cover_4x3, "05_exports", "4:3 cover")
  production_path(root, srt, "04_videos", "Corrected SRT")

  script = optional_script(root, date, script_path)
  recording = optional_recording(root, date, recording_path)
  publish_markdown = package_path.parent / "PUBLISH.md"
  run = start_run(
    root,
    date=date,
    content_type=content_type,
    title=str(package.get("title", "")),
    run_id=run_id,
    channel=channel,
    actor=actor,
  )
  if run.get("reused") and run.get("currentStage") == "completed":
    return {"run": run, "productionStats": stats, "reused": True}

  run = advance_if_needed(
    root,
    run,
    "input_review",
    actor,
    "Completed production retained its source input review.",
    step_status="skipped",
  )
  run = advance_if_needed(
    root,
    run,
    "script",
    actor,
    "Script artifact registered." if script else "No separate script artifact was available.",
    step_status="succeeded" if script else "skipped",
  )
  if script:
    register(root, run_id, "script-md", "script", "text", "Production script", script, actor)

  run = advance_if_needed(
    root,
    run,
    "recording",
    actor,
    "Source recording registered." if recording else "Source recording was not uniquely discoverable.",
    step_status="succeeded" if recording else "skipped",
  )
  if recording:
    register(root, run_id, "source-video", "recording", "video", "Source recording", recording, actor)

  run = advance_if_needed(root, run, "cover", actor, "Production cover pair registered.")
  register(root, run_id, "cover-3x4", "cover", "image", "Production cover 3:4", cover_3x4, actor)
  register(root, run_id, "cover-4x3", "cover", "image", "Production cover 4:3", cover_4x3, actor)

  run = advance_if_needed(root, run, "subtitles", actor, "Corrected production SRT registered.")
  register(root, run_id, "corrected-srt", "subtitles", "subtitle", "Corrected production SRT", srt, actor)
  run = advance_if_needed(root, run, "combined_review", actor, "Subtitle text and timing QC passed.")
  run = advance_if_needed(root, run, "compliance", actor, "Publish package compliance status passed.")

  run = advance_if_needed(root, run, "render", actor, "Final production video registered.")
  register(root, run_id, "final-video", "render", "video", "Final production video", video, actor)

  run = advance_if_needed(
    root,
    run,
    "publish_package",
    actor,
    "Publish-ready package registered.",
    publish_ready=True,
  )
  register(root, run_id, "publish-json", "publish_package", "json", "Publish package", package_path, actor)
  if publish_markdown.is_file():
    register(root, run_id, "publish-md", "publish_package", "report", "Publish brief", publish_markdown, actor)

  run = advance_if_needed(root, run, "log", actor, "Production statistics row verified.")
  register(
    root,
    run_id,
    "production-stats",
    "log",
    "report",
    "Production statistics ledger",
    root / "00_state" / "production-stats.csv",
    actor,
  )
  run = advance_if_needed(root, run, "output_review", actor, "Output review completed.")
  run = advance_if_needed(root, run, "completed", actor, "Run finalization completed.")
  return {"run": run, "productionStats": stats, "reused": False}


def adopt_canary_run(
  root: Path,
  date: str,
  publish_package_path: Optional[str] = None,
  content_type: str = "video-diary",
  script_path: Optional[str] = None,
  recording_path: Optional[str] = None,
  actor: str = "system-steward-agent",
) -> Dict[str, Any]:
  root = root.resolve()
  package_path = require_file(
    root,
    publish_package_path or f"05_exports/{date}/publish-package.json",
    "publish package",
  )
  package = json.loads(package_path.read_text(encoding="utf-8"))
  schema = load_json(root / "00_system" / "contracts" / "schemas" / "publish-package.schema.json")
  errors = validate_value(package, schema)
  if errors:
    raise RunStateError("Invalid publish package: " + "; ".join(errors))
  if package.get("publishReady") is not True:
    raise RunStateError("Canary adoption requires publishReady=true.")

  production = package.get("production", {})
  if production.get("statsRecorded") is not True:
    raise RunStateError("Canary adoption requires recorded production statistics.")
  if production.get("subtitleQc") != "pass" or production.get("compliance") != "pass":
    raise RunStateError("Canary adoption requires passed subtitle and compliance checks.")

  source_package_path = package_path
  source_run_id = str(package.get("runId", "")).strip()
  content_id = str(package.get("contentId", "")).strip()
  if not source_run_id or not content_id:
    raise RunStateError("Publish package requires runId and contentId.")
  system = load_json(root / "00_system" / "system.json")
  candidate = str(system.get("candidateRelease", "")).strip()
  if not candidate:
    raise RunStateError("No candidate release is configured.")

  adoption_mode = "native-canary-package"
  if production.get("systemVersion") != candidate:
    safe_content_id = re.sub(r"[^A-Za-z0-9._-]+", "-", content_id).strip("-") or "content"
    run_id = validate_run_id(f"{safe_content_id}-canary-{candidate}")
    package = json.loads(json.dumps(package, ensure_ascii=False))
    package["runId"] = run_id
    package["production"]["systemVersion"] = candidate
    package["generatedAt"] = now_iso()
    package["canary"] = {
      "mode": "stable-artifact-adoption",
      "mediaReencoded": False,
      "sourceRunId": source_run_id,
      "sourceSystemVersion": production.get("systemVersion"),
      "sourcePackage": relative_or_absolute(root, source_package_path),
    }
    package_path = (
      root
      / "00_state"
      / "releases"
      / candidate
      / "canary"
      / date
      / safe_content_id
      / "publish-package.json"
    )
    candidate_errors = validate_value(package, schema)
    if candidate_errors:
      raise RunStateError("Invalid Canary package: " + "; ".join(candidate_errors))
    atomic_write_json(package_path, package)
    adoption_mode = "stable-artifact-adoption"
  else:
    run_id = validate_run_id(source_run_id)

  finalized = finalize_prepared_run(
    root,
    date=date,
    package_path=package_path,
    package=package,
    content_type=content_type,
    channel="canary",
    script_path=script_path,
    recording_path=recording_path,
    actor=actor,
  )
  run = finalized["run"]
  validation = validate_real_canary(root, run_id)
  return {
    "run": run,
    "validation": validation,
    "reused": finalized["reused"],
    "productionStats": finalized["productionStats"],
    "adoptionMode": adoption_mode,
    "sourcePackage": relative_or_absolute(root, source_package_path),
    "canaryPackage": relative_or_absolute(root, package_path),
  }
