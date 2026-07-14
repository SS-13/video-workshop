"""Guarded activation and rollback for video production releases."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict
import json
import os
import tempfile


class ReleaseTransitionError(Exception):
  pass


def load_json(path: Path) -> Dict[str, Any]:
  return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  descriptor, temporary_name = tempfile.mkstemp(
    prefix=f"{path.stem}-",
    suffix=".json",
    dir=str(path.parent),
  )
  try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
      json.dump(payload, file, ensure_ascii=False, indent=2)
      file.write("\n")
    os.replace(temporary_name, path)
  finally:
    if os.path.exists(temporary_name):
      os.unlink(temporary_name)


def now_iso() -> str:
  return datetime.now().astimezone().isoformat(timespec="seconds")


def release_paths(root: Path) -> Dict[str, Path]:
  system_path = root / "00_system" / "system.json"
  policy_path = root / "00_system" / "release-policy.json"
  package_path = root / "package.json"
  system = load_json(system_path)
  candidate = str(system.get("candidateRelease", "")).strip()
  if not candidate:
    raise ReleaseTransitionError("No candidate release is configured.")
  return {
    "system": system_path,
    "policy": policy_path,
    "package": package_path,
    "manifest": root / "00_system" / "releases" / candidate / "manifest.json",
  }


def activation_readiness(root: Path) -> Dict[str, Any]:
  paths = release_paths(root)
  system = load_json(paths["system"])
  policy = load_json(paths["policy"])
  package = load_json(paths["package"])
  if not paths["manifest"].exists():
    raise ReleaseTransitionError(f"Missing candidate manifest: {paths['manifest']}")
  manifest = load_json(paths["manifest"])
  candidate = system["candidateRelease"]
  stable = policy["stableRelease"]
  gates = manifest.get("gates", {})
  blocking_gates = {
    name: status
    for name, status in gates.items()
    if name != "manualActivation" and status != "pass"
  }
  errors = []
  if manifest.get("version") != candidate:
    errors.append("candidate_manifest_version_mismatch")
  if manifest.get("stableFallback") != stable:
    errors.append("stable_fallback_mismatch")
  if system.get("activeRelease") not in {stable, candidate}:
    errors.append("unexpected_active_release")
  return {
    "ready": not blocking_gates and not errors,
    "activeRelease": system.get("activeRelease"),
    "candidateRelease": candidate,
    "stableRelease": stable,
    "packageVersion": package.get("version"),
    "manifestStatus": manifest.get("status"),
    "blockingGates": blocking_gates,
    "errors": errors,
  }


def activate_release(
  root: Path,
  confirm: bool,
  dry_run: bool = False,
  actor: str = "cli",
) -> Dict[str, Any]:
  readiness = activation_readiness(root)
  result = {**readiness, "action": "activate", "changed": False, "dryRun": dry_run}
  if not readiness["ready"]:
    return result
  if not dry_run and not confirm:
    raise ReleaseTransitionError("Activation requires --confirm after Canary approval.")
  if dry_run:
    return result

  paths = release_paths(root)
  system = load_json(paths["system"])
  package = load_json(paths["package"])
  manifest = load_json(paths["manifest"])
  candidate = readiness["candidateRelease"]
  timestamp = now_iso()

  manifest["status"] = "active"
  manifest["active"] = True
  manifest.setdefault("gates", {})["manualActivation"] = "pass"
  manifest["activatedAt"] = timestamp
  manifest["activatedBy"] = actor
  system["activeRelease"] = candidate
  package["version"] = candidate

  atomic_write_json(paths["manifest"], manifest)
  atomic_write_json(paths["system"], system)
  atomic_write_json(paths["package"], package)
  return {
    **result,
    "changed": True,
    "activeRelease": candidate,
    "packageVersion": candidate,
    "activatedAt": timestamp,
  }


def rollback_release(
  root: Path,
  confirm: bool,
  dry_run: bool = False,
  actor: str = "cli",
) -> Dict[str, Any]:
  paths = release_paths(root)
  system = load_json(paths["system"])
  policy = load_json(paths["policy"])
  package = load_json(paths["package"])
  manifest = load_json(paths["manifest"])
  stable = policy["stableRelease"]
  result = {
    "action": "rollback",
    "changed": False,
    "dryRun": dry_run,
    "activeRelease": system.get("activeRelease"),
    "targetRelease": stable,
    "packageVersion": package.get("version"),
  }
  if not dry_run and not confirm:
    raise ReleaseTransitionError("Rollback requires --confirm.")
  if dry_run:
    return result

  timestamp = now_iso()
  system["activeRelease"] = stable
  package["version"] = stable
  manifest["status"] = "rolled-back"
  manifest["active"] = False
  manifest["rolledBackAt"] = timestamp
  manifest["rolledBackBy"] = actor

  atomic_write_json(paths["manifest"], manifest)
  atomic_write_json(paths["system"], system)
  atomic_write_json(paths["package"], package)
  return {
    **result,
    "changed": True,
    "activeRelease": stable,
    "packageVersion": stable,
    "rolledBackAt": timestamp,
  }
