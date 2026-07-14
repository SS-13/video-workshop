"""Resolve generic profile actions to existing stable commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import json

from video_production_core.registry import get_content_types, get_profile


class RouteResolutionError(Exception):
  pass


def load_json(path: Path) -> Dict[str, Any]:
  return json.loads(path.read_text(encoding="utf-8"))


def resolve_route(root: Path, content_type_id: str, action: str) -> Dict[str, Any]:
  content_types = {item["id"]: item for item in get_content_types(root)}
  if content_type_id not in content_types:
    raise RouteResolutionError(f"Unknown content type: {content_type_id}")
  content_type = content_types[content_type_id]
  if not content_type.get("enabled", False):
    raise RouteResolutionError(f"Content type is disabled: {content_type_id}")

  profile = get_profile(root, content_type["profile"])
  profile_commands = profile.get("commands", {})
  if action not in profile_commands:
    raise RouteResolutionError(
      f"Profile {profile['id']} does not define action: {action}"
    )
  command_id = profile_commands[action]
  system = load_json(root / "00_system" / "system.json")
  registry_path = root / system.get("commandRegistry", "00_system/registries/commands.json")
  commands = load_json(registry_path).get("commands", {})
  if command_id not in commands:
    raise RouteResolutionError(f"Command is not registered: {command_id}")
  command = commands[command_id]

  owner_skill = command["owner"]
  owner_agent = None
  for role, skill_id in profile.get("skills", {}).items():
    if skill_id == owner_skill:
      if role in {"intake", "script"}:
        owner_agent = profile.get("agents", {}).get("text")
      elif role in {"cover", "edit", "log"}:
        owner_agent = profile.get("agents", {}).get("video")
      break

  return {
    "contentType": content_type_id,
    "profile": profile["id"],
    "action": action,
    "commandId": command_id,
    "command": command["command"],
    "ownerSkill": owner_skill,
    "ownerAgent": owner_agent,
    "stableCompatible": True,
    "executes": False,
  }
