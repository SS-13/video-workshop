"""Project root discovery independent of the physical folder name."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional
import os


ROOT_ENV = "VIDEO_PRODUCTION_ROOT"
SYSTEM_MARKER = Path("00_system/system.json")


class RootDiscoveryError(Exception):
  pass


def is_project_root(path: Path) -> bool:
  return path.is_dir() and (path / SYSTEM_MARKER).is_file()


def validate_root(path: Path, source: str) -> Path:
  resolved = path.expanduser().resolve()
  if not is_project_root(resolved):
    raise RootDiscoveryError(
      f"{source} does not point to a video production workspace: {resolved}"
    )
  return resolved


def search_upward(start: Path) -> Optional[Path]:
  current = start.expanduser().resolve()
  if current.is_file():
    current = current.parent
  for candidate in [current, *current.parents]:
    if is_project_root(candidate):
      return candidate
  return None


def resolve_project_root(
  explicit: Optional[str] = None,
  start: Optional[Path] = None,
  environment: Optional[Mapping[str, str]] = None,
  fallback: Optional[Path] = None,
) -> Path:
  if explicit:
    return validate_root(Path(explicit), "--root")

  env = environment if environment is not None else os.environ
  env_root = str(env.get(ROOT_ENV, "")).strip()
  if env_root:
    return validate_root(Path(env_root), ROOT_ENV)

  discovered = search_upward(start or Path.cwd())
  if discovered:
    return discovered

  if fallback and is_project_root(fallback.expanduser().resolve()):
    return fallback.expanduser().resolve()

  raise RootDiscoveryError(
    "Could not locate 00_system/system.json. Use --root or VIDEO_PRODUCTION_ROOT."
  )
