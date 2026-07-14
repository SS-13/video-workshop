"""Deterministic release gate for one real video-production Canary run."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import csv
import json
import struct

from video_production_core.contracts import load_json, validate_value
from video_production_core.release_transition import atomic_write_json, release_paths
from video_production_core.run_store import get_run, validate_run


def now_iso() -> str:
  return datetime.now().astimezone().isoformat(timespec="seconds")


def resolve_artifact_path(root: Path, value: str) -> Path:
  path = Path(value)
  if not path.is_absolute():
    path = root / path
  return path.resolve()


def relative_artifact_path(root: Path, path: Path) -> Optional[Path]:
  try:
    return path.relative_to(root.resolve())
  except ValueError:
    return None


def image_dimensions(path: Path) -> Optional[Tuple[int, int]]:
  data = path.read_bytes()
  if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
    return struct.unpack(">II", data[16:24])
  if not data.startswith(b"\xff\xd8"):
    return None

  offset = 2
  while offset + 9 < len(data):
    if data[offset] != 0xFF:
      offset += 1
      continue
    marker = data[offset + 1]
    offset += 2
    if marker in {0xD8, 0xD9}:
      continue
    if offset + 2 > len(data):
      break
    length = int.from_bytes(data[offset:offset + 2], "big")
    if length < 2 or offset + length > len(data):
      break
    if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
      height = int.from_bytes(data[offset + 3:offset + 5], "big")
      width = int.from_bytes(data[offset + 5:offset + 7], "big")
      return width, height
    offset += length
  return None


def production_stat_exists(root: Path, content_id: str) -> bool:
  path = root / "00_state" / "production-stats.csv"
  if not path.exists():
    return False
  with path.open("r", encoding="utf-8-sig", newline="") as file:
    return any(row.get("content_id") == content_id for row in csv.DictReader(file))


def add_check(
  checks: List[Dict[str, Any]],
  name: str,
  passed: bool,
  details: Any = None,
) -> None:
  checks.append({
    "name": name,
    "status": "pass" if passed else "fail",
    "details": details,
  })


def find_publish_package(
  root: Path,
  run: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[Path], List[str]]:
  schema = load_json(root / "00_system" / "contracts" / "schemas" / "publish-package.schema.json")
  errors: List[str] = []
  for artifact in run.get("artifacts", []):
    if artifact.get("stepId") != "publish_package" or artifact.get("type") != "json":
      continue
    path = resolve_artifact_path(root, str(artifact.get("relativePath", "")))
    if not artifact.get("available") or not path.is_file():
      errors.append(f"unavailable publish package: {path}")
      continue
    try:
      payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
      errors.append(f"invalid JSON {path}: {error}")
      continue
    contract_errors = validate_value(payload, schema)
    if contract_errors:
      errors.extend(contract_errors)
      continue
    if payload.get("runId") != run.get("id"):
      errors.append(f"publish package runId mismatch: {payload.get('runId')}")
      continue
    return payload, path, errors
  return None, None, errors


def validate_real_canary(
  root: Path,
  run_id: str,
  record_pass: bool = False,
  actor: str = "system-steward-agent",
) -> Dict[str, Any]:
  root = root.resolve()
  paths = release_paths(root)
  system = load_json(paths["system"])
  policy = load_json(paths["policy"])
  package_meta = load_json(paths["package"])
  manifest = load_json(paths["manifest"])
  candidate = str(system.get("candidateRelease", ""))
  stable = str(policy.get("stableRelease", ""))
  run = get_run(root, run_id)
  checks: List[Dict[str, Any]] = []

  run_contract = validate_run(root, run_id)
  add_check(checks, "run-contract", run_contract["valid"], run_contract["errors"])
  add_check(checks, "canary-channel", run.get("channel") == "canary", run.get("channel"))
  add_check(
    checks,
    "candidate-version",
    run.get("systemVersion") == candidate,
    {"run": run.get("systemVersion"), "candidate": candidate},
  )
  add_check(
    checks,
    "run-completed",
    run.get("status") == "succeeded" and run.get("currentStage") == "completed",
    {"status": run.get("status"), "stage": run.get("currentStage")},
  )
  incomplete_steps = [
    step.get("id")
    for step in run.get("steps", [])
    if step.get("status") not in {"succeeded", "skipped"}
  ]
  add_check(checks, "steps-completed", not incomplete_steps, incomplete_steps)
  add_check(checks, "run-publish-ready", run.get("publishReady") is True, run.get("publishReady"))

  missing_registered = []
  registered_paths = set()
  for artifact in run.get("artifacts", []):
    path = resolve_artifact_path(root, str(artifact.get("relativePath", "")))
    if artifact.get("available") and path.is_file():
      registered_paths.add(path)
    else:
      missing_registered.append(artifact.get("id"))
  add_check(checks, "registered-artifacts-available", not missing_registered, missing_registered)

  publish_package, publish_path, package_errors = find_publish_package(root, run)
  add_check(
    checks,
    "publish-package-contract",
    publish_package is not None,
    {"path": str(publish_path) if publish_path else None, "errors": package_errors},
  )

  if publish_package is not None:
    production = publish_package.get("production", {})
    add_check(
      checks,
      "publish-package-ready",
      publish_package.get("publishReady") is True,
      publish_package.get("publishReady"),
    )
    add_check(checks, "subtitle-quality", production.get("subtitleQc") == "pass", production.get("subtitleQc"))
    add_check(checks, "compliance", production.get("compliance") == "pass", production.get("compliance"))
    add_check(
      checks,
      "production-stats-recorded",
      production.get("statsRecorded") is True,
      production.get("statsRecorded"),
    )
    add_check(
      checks,
      "production-system-version",
      production.get("systemVersion") == candidate,
      production.get("systemVersion"),
    )
    content_id = str(publish_package.get("contentId", ""))
    add_check(
      checks,
      "production-stats-ledger",
      bool(content_id) and production_stat_exists(root, content_id),
      content_id,
    )

    package_artifacts = publish_package.get("artifacts", {})
    resolved_package_paths = {
      key: resolve_artifact_path(root, str(value))
      for key, value in package_artifacts.items()
    }
    missing_package_files = [
      key
      for key in ["video", "cover3x4", "cover4x3", "srt"]
      if key not in resolved_package_paths
      or not resolved_package_paths[key].is_file()
      or resolved_package_paths[key] not in registered_paths
    ]
    add_check(checks, "required-artifact-set", not missing_package_files, missing_package_files)

    expected_roots = {
      "video": "05_exports",
      "cover3x4": "05_exports",
      "cover4x3": "05_exports",
      "srt": "04_videos",
    }
    non_production_paths = []
    for key, expected_root in expected_roots.items():
      path = resolved_package_paths.get(key)
      relative = relative_artifact_path(root, path) if path else None
      if relative is None or not relative.parts or relative.parts[0] != expected_root or "shadow" in relative.parts:
        non_production_paths.append(key)
    add_check(checks, "real-production-paths", not non_production_paths, non_production_paths)

    ratio_errors = []
    for key, expected_ratio in [("cover3x4", 3 / 4), ("cover4x3", 4 / 3)]:
      path = resolved_package_paths.get(key)
      dimensions = image_dimensions(path) if path and path.is_file() else None
      if dimensions is None:
        ratio_errors.append(f"{key}: unreadable")
        continue
      width, height = dimensions
      if height <= 0 or abs((width / height) - expected_ratio) > 0.02:
        ratio_errors.append(f"{key}: {width}x{height}")
    add_check(checks, "cover-ratios", not ratio_errors, ratio_errors)

    video_path = resolved_package_paths.get("video")
    expected_size = production.get("fileSizeBytes")
    actual_size = video_path.stat().st_size if video_path and video_path.is_file() else None
    add_check(
      checks,
      "video-metadata",
      bool(production.get("videoDurationSeconds", 0) > 0)
      and actual_size is not None
      and expected_size == actual_size,
      {"duration": production.get("videoDurationSeconds"), "expectedSize": expected_size, "actualSize": actual_size},
    )

  stable_fallback_ready = (
    manifest.get("stableFallback") == stable
    and manifest.get("gates", {}).get("legacyFallback") == "pass"
    and system.get("activeRelease") in {stable, candidate}
    and package_meta.get("version") in {stable, candidate}
  )
  add_check(
    checks,
    "stable-fallback",
    stable_fallback_ready,
    {
      "stable": stable,
      "manifestFallback": manifest.get("stableFallback"),
      "active": system.get("activeRelease"),
      "packageVersion": package_meta.get("version"),
    },
  )

  valid = all(check["status"] == "pass" for check in checks)
  recorded = False
  checked_at = now_iso()
  if record_pass and valid:
    manifest.setdefault("gates", {})["realVideoCanary"] = "pass"
    manifest.setdefault("evidence", {})["realVideoCanary"] = {
      "runId": run_id,
      "checkedAt": checked_at,
      "checkedBy": actor,
    }
    atomic_write_json(paths["manifest"], manifest)
    recorded = True

  return {
    "valid": valid,
    "recorded": recorded,
    "runId": run_id,
    "candidateRelease": candidate,
    "checkedAt": checked_at,
    "checks": checks,
  }
