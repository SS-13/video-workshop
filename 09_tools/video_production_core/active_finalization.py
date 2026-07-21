"""Finalize publish-ready output into Run State only when 3.x is Active."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import json
import re

from video_production_core.canary_adoption import finalize_prepared_run, require_file
from video_production_core.contracts import load_json, validate_value
from video_production_core.run_store import RunStateError, validate_run
from video_production_core.content_layout import ContentRef
from video_production_core.state_reconcile import finalize_content_ledger


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def version_tuple(value: str) -> Tuple[int, int, int]:
  match = re.match(r"^(\d+)\.(\d+)\.(\d+)", str(value or ""))
  if not match:
    return (0, 0, 0)
  return tuple(int(part) for part in match.groups())


def active_run_state_status(root: Path) -> Dict[str, Any]:
  system = load_json(root / "00_system" / "system.json")
  package = load_json(root / "package.json")
  active = str(system.get("activeRelease", ""))
  manifest_path = root / "00_system" / "releases" / active / "manifest.json"
  manifest = load_json(manifest_path) if manifest_path.exists() else {}
  enabled = (
    version_tuple(active) >= (3, 0, 0)
    and package.get("version") == active
    and manifest.get("version") == active
    and manifest.get("active") is True
    and manifest.get("status") == "active"
  )
  reason = "active-3x" if enabled else "active-release-does-not-enable-native-run-state"
  return {
    "enabled": enabled,
    "reason": reason,
    "activeRelease": active,
    "packageVersion": package.get("version"),
    "manifestPath": str(manifest_path),
    "manifestStatus": manifest.get("status"),
  }


def finalize_active_run(
  root: Path,
  date: str,
  publish_package_path: Optional[str] = None,
  content_type: str = "video-diary",
  script_path: Optional[str] = None,
  recording_path: Optional[str] = None,
  actor: str = "video-agent",
  sequence: str = "001",
) -> Dict[str, Any]:
  root = root.resolve()
  status = active_run_state_status(root)
  if not status["enabled"]:
    return {
      **status,
      "changed": False,
      "reused": False,
      "valid": True,
      "run": None,
    }
  if not DATE_RE.fullmatch(date):
    raise RunStateError(f"Active Run finalization requires YYYY-MM-DD date: {date}")

  package_path = require_file(
    root,
    publish_package_path or str(
      ContentRef(date, content_type, sequence).media_dir(root, "05_exports")
      / "publish-package.json"
    ),
    "publish package",
  )
  try:
    publish_package = json.loads(package_path.read_text(encoding="utf-8"))
  except json.JSONDecodeError as error:
    raise RunStateError(f"Invalid publish package JSON: {package_path}") from error
  schema = load_json(root / "00_system" / "contracts" / "schemas" / "publish-package.schema.json")
  errors = validate_value(publish_package, schema)
  if errors:
    raise RunStateError("Invalid publish package: " + "; ".join(errors))
  production_version = publish_package.get("production", {}).get("systemVersion")
  if production_version != status["activeRelease"]:
    raise RunStateError(
      f"Publish package systemVersion must match Active Release: "
      f"{production_version} != {status['activeRelease']}"
    )

  finalized = finalize_prepared_run(
    root,
    date=date,
    package_path=package_path,
    package=publish_package,
    content_type=content_type,
    channel="stable",
    script_path=script_path,
    recording_path=recording_path,
    actor=actor,
    sequence=sequence,
  )
  ledger = finalize_content_ledger(root, publish_package)
  run = finalized["run"]
  validation = validate_run(root, run["id"])
  active_errors = []
  if run.get("channel") != "stable":
    active_errors.append("active_run_channel_must_be_stable")
  if run.get("systemVersion") != status["activeRelease"]:
    active_errors.append("active_run_version_mismatch")
  if run.get("status") != "succeeded" or run.get("currentStage") != "completed":
    active_errors.append("active_run_not_completed")
  if run.get("publishReady") is not True:
    active_errors.append("active_run_not_publish_ready")

  valid = validation["valid"] and not active_errors
  return {
    **status,
    "changed": not finalized["reused"],
    "reused": finalized["reused"],
    "valid": valid,
    "run": run,
    "validation": validation,
    "errors": active_errors,
    "productionStats": finalized["productionStats"],
    "contentLedger": ledger,
  }
