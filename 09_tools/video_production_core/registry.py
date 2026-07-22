"""Read and validate the 3.0 candidate control-plane registries."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json

from .versioning import VersioningError, build_version_plan


def load_json(path: Path) -> Dict[str, Any]:
  return json.loads(path.read_text(encoding="utf-8"))


def load_documents(directory: Path) -> Dict[str, Dict[str, Any]]:
  documents: Dict[str, Dict[str, Any]] = {}
  if not directory.exists():
    return documents
  for path in sorted(directory.glob("*.json")):
    payload = load_json(path)
    document_id = str(payload.get("id", "")).strip()
    if document_id:
      documents[document_id] = payload
  return documents


def get_system_info(root: Path) -> Dict[str, Any]:
  system = load_json(root / "00_system" / "system.json")
  package = load_json(root / "package.json")
  return {
    **system,
    "packageVersion": package.get("version", "unknown"),
    "root": str(root),
  }


def get_content_types(root: Path, enabled_only: bool = False) -> List[Dict[str, Any]]:
  system = load_json(root / "00_system" / "system.json")
  directory = root / system.get("contentTypeRoot", "00_system/content-types")
  items = list(load_documents(directory).values())
  if enabled_only:
    items = [item for item in items if item.get("enabled", False)]
  return sorted(items, key=lambda item: (not item.get("default", False), item["id"]))


def get_profile(root: Path, profile_id: str) -> Dict[str, Any]:
  system = load_json(root / "00_system" / "system.json")
  directory = root / system.get("profileRoot", "00_system/profiles")
  profiles = load_documents(directory)
  if profile_id not in profiles:
    raise KeyError(profile_id)
  return profiles[profile_id]


def get_release_status(root: Path) -> Dict[str, Any]:
  system = load_json(root / "00_system" / "system.json")
  release_policy = load_json(root / "00_system" / "release-policy.json")
  candidate = str(system.get("candidateRelease", "")).strip()
  manifest_path = root / "00_system" / "releases" / candidate / "manifest.json"
  manifest = load_json(manifest_path) if candidate and manifest_path.exists() else None
  try:
    version_plan = build_version_plan(root)
  except (OSError, json.JSONDecodeError, VersioningError) as error:
    version_plan = {"error": str(error)}
  return {
    "activeRelease": system.get("activeRelease"),
    "candidateRelease": candidate or None,
    "stableRelease": release_policy.get("stableRelease"),
    "targetDate": release_policy.get("targetDate"),
    "productionGuard": release_policy.get("productionGuard", {}),
    "rollback": release_policy.get("rollback", {}),
    "candidateManifest": manifest,
    "versionPlan": version_plan,
  }


def validate_control_plane(root: Path) -> Dict[str, Any]:
  errors: List[Dict[str, str]] = []
  warnings: List[Dict[str, str]] = []

  def add_error(code: str, message: str) -> None:
    errors.append({"code": code, "message": message})

  def add_warning(code: str, message: str) -> None:
    warnings.append({"code": code, "message": message})

  system_path = root / "00_system" / "system.json"
  package_path = root / "package.json"
  if not system_path.exists():
    add_error("SYSTEM_MISSING", "00_system/system.json is missing.")
    return {"valid": False, "errors": errors, "warnings": warnings, "counts": {}}
  if not package_path.exists():
    add_error("PACKAGE_MISSING", "package.json is missing.")
    return {"valid": False, "errors": errors, "warnings": warnings, "counts": {}}

  system = load_json(system_path)
  package = load_json(package_path)
  content_root = root / system.get("contentTypeRoot", "00_system/content-types")
  profile_root = root / system.get("profileRoot", "00_system/profiles")
  command_path = root / system.get("commandRegistry", "00_system/registries/commands.json")
  agent_path = root / system.get("agentRegistry", "00_system/registries/agents.json")
  content_types = load_documents(content_root)
  profiles = load_documents(profile_root)
  commands = load_json(command_path).get("commands", {}) if command_path.exists() else {}
  agents = load_json(agent_path).get("agents", {}) if agent_path.exists() else {}

  if not command_path.exists():
    add_error("COMMAND_REGISTRY_MISSING", str(command_path.relative_to(root)))
  if not agent_path.exists():
    add_error("AGENT_REGISTRY_MISSING", str(agent_path.relative_to(root)))

  default_types = [item["id"] for item in content_types.values() if item.get("default", False)]
  if len(default_types) != 1:
    add_error("DEFAULT_CONTENT_TYPE_COUNT", f"Expected one default content type, found {len(default_types)}.")
  elif default_types[0] != system.get("defaultContentType"):
    add_error(
      "DEFAULT_CONTENT_TYPE_MISMATCH",
      f"system.json={system.get('defaultContentType')} registry={default_types[0]}",
    )

  for content_id, content_type in content_types.items():
    profile_id = str(content_type.get("profile", ""))
    if profile_id not in profiles:
      add_error("PROFILE_REFERENCE_MISSING", f"{content_id} references {profile_id}.")
    elif profiles[profile_id].get("contentType") != content_id:
      add_error("PROFILE_CONTENT_TYPE_MISMATCH", f"{profile_id} does not target {content_id}.")
    if not content_type.get("enabled", False):
      add_warning("CONTENT_TYPE_DISABLED", content_id)

  for profile_id, profile in profiles.items():
    for role, agent_id in profile.get("agents", {}).items():
      if agent_id not in agents:
        add_error("AGENT_REFERENCE_MISSING", f"{profile_id}.{role} references {agent_id}.")
    for role, skill_id in profile.get("skills", {}).items():
      skill_path = root / ".codex" / "skills" / skill_id / "SKILL.md"
      if not skill_path.exists():
        add_error("SKILL_REFERENCE_MISSING", f"{profile_id}.{role} references {skill_id}.")
    for role, command_id in profile.get("commands", {}).items():
      if command_id not in commands:
        add_error("COMMAND_REFERENCE_MISSING", f"{profile_id}.{role} references {command_id}.")

  for agent_id, agent in agents.items():
    definition = root / str(agent.get("definition", ""))
    if not definition.exists():
      add_error("AGENT_DEFINITION_MISSING", f"{agent_id}: {definition}")

  package_scripts = package.get("scripts", {})
  missing_commands = sorted(set(package_scripts) - set(commands))
  extra_commands = sorted(set(commands) - set(package_scripts))
  for command_id in missing_commands:
    add_error("COMMAND_OWNER_MISSING", command_id)
  for command_id in extra_commands:
    add_error("COMMAND_NOT_IN_PACKAGE", command_id)
  for command_id in sorted(set(package_scripts) & set(commands)):
    registered = commands[command_id]
    if registered.get("command") != package_scripts[command_id]:
      add_error("COMMAND_TEXT_MISMATCH", command_id)
    owner = str(registered.get("owner", ""))
    owner_path = root / ".codex" / "skills" / owner / "SKILL.md"
    if not owner_path.exists():
      add_error("COMMAND_OWNER_SKILL_MISSING", f"{command_id}: {owner}")

  candidate_release = str(system.get("candidateRelease", "")).strip()
  if candidate_release:
    manifest = root / "00_system" / "releases" / candidate_release / "manifest.json"
    if not manifest.exists():
      add_error("CANDIDATE_MANIFEST_MISSING", candidate_release)

  return {
    "valid": not errors,
    "errors": errors,
    "warnings": warnings,
    "counts": {
      "contentTypes": len(content_types),
      "profiles": len(profiles),
      "commands": len(commands),
      "agents": len(agents),
    },
    "defaultContentType": system.get("defaultContentType"),
    "activeRelease": system.get("activeRelease"),
    "candidateRelease": system.get("candidateRelease"),
  }
