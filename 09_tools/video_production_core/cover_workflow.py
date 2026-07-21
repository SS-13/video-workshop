"""Minimal control plane for Pencil cover design and daily cover production."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import os
import re
import shutil
import subprocess
import sys

from video_production_core.content_layout import ContentRef

from PIL import Image


ROUTES_PATH = Path(".codex/skills/video-diary-cover/references/cover-routes.json")
DESIGN_ROOT = Path("15_cover_gallery/designs")
VERSION_RE = re.compile(r"^v\d+\.\d+(?:\.\d+)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CoverWorkflowError(ValueError):
  """Raised when a cover workflow request would break its version contract."""


def now_iso() -> str:
  return datetime.now().astimezone().isoformat(timespec="seconds")


def resolve_path(root: Path, value: str | Path) -> Path:
  path = Path(value)
  return path.resolve() if path.is_absolute() else (root / path).resolve()


def relative_path(root: Path, path: Path) -> str:
  try:
    return str(path.resolve().relative_to(root.resolve()))
  except ValueError:
    return str(path.resolve())


def load_json(path: Path) -> Dict[str, Any]:
  if not path.is_file():
    raise CoverWorkflowError(f"Missing JSON file: {path}")
  payload = json.loads(path.read_text(encoding="utf-8"))
  if not isinstance(payload, dict):
    raise CoverWorkflowError(f"Expected a JSON object: {path}")
  return payload


def write_json(path: Path, payload: Dict[str, Any]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical_hash(payload: Any) -> str:
  value = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
  return sha256(value.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
  digest = sha256()
  with path.open("rb") as file:
    for chunk in iter(lambda: file.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def load_routes(root: Path) -> tuple[Path, Dict[str, Any]]:
  path = root / ROUTES_PATH
  payload = load_json(path)
  if not isinstance(payload.get("routes"), dict):
    raise CoverWorkflowError("cover-routes.json must contain a routes object")
  return path, payload


def normalize_route(routes: Dict[str, Any], requested: str) -> str:
  route_name = (requested or routes.get("defaultRoute") or "video-diary").strip()
  if route_name in routes["routes"]:
    return route_name
  for name, route in routes["routes"].items():
    if route_name in route.get("aliases", []):
      return name
  valid = ", ".join(sorted(routes["routes"]))
  raise CoverWorkflowError(f"Unknown cover route: {route_name}. Valid routes: {valid}")


def require_file(root: Path, value: str | Path, label: str) -> Path:
  path = resolve_path(root, value)
  if not path.is_file():
    raise CoverWorkflowError(f"Missing {label}: {path}")
  return path


def inspect_preview(path: Path, aspect: str) -> List[int]:
  try:
    with Image.open(path) as image:
      width, height = image.size
  except Exception as error:
    raise CoverWorkflowError(f"Cannot read {aspect} preview: {path}") from error
  expected = 3 / 4 if aspect == "3:4" else 4 / 3
  if height <= 0 or abs(width / height - expected) > 0.01:
    raise CoverWorkflowError(
      f"{aspect} preview has the wrong ratio: {path} ({width}x{height})"
    )
  return [width, height]


def copied_name(label: str, source: Path) -> str:
  suffix = "".join(source.suffixes) or ".bin"
  return f"{label}{suffix.lower()}"


def register_pencil_design(
  root: Path,
  route: str,
  version: str,
  pencil_source: str | Path,
  preview_3x4: str | Path,
  preview_4x3: str | Path,
  tokens: Optional[str | Path] = None,
  activate: bool = False,
  note: str = "",
) -> Dict[str, Any]:
  root = root.resolve()
  if not VERSION_RE.fullmatch(version):
    raise CoverWorkflowError("Style version must look like v1.4 or v1.4.1")

  routes_path, routes = load_routes(root)
  route_name = normalize_route(routes, route)
  route_config = routes["routes"][route_name]
  versions = route_config.setdefault("versions", {})
  existing_tokens = versions.get(version)

  if tokens:
    style_tokens = load_json(require_file(root, tokens, "renderer token file"))
  elif isinstance(existing_tokens, dict):
    style_tokens = existing_tokens
  else:
    raise CoverWorkflowError("A new style version requires --tokens path/to/style.json")

  if existing_tokens is not None and existing_tokens != style_tokens:
    raise CoverWorkflowError(
      f"Style {route_name}/{version} already exists with different tokens; create a new version"
    )

  source_path = require_file(root, pencil_source, "Pencil source")
  preview_3x4_path = require_file(root, preview_3x4, "3:4 preview")
  preview_4x3_path = require_file(root, preview_4x3, "4:3 preview")
  preview_dimensions = {
    "3x4": inspect_preview(preview_3x4_path, "3:4"),
    "4x3": inspect_preview(preview_4x3_path, "4:3"),
  }

  design_dir = root / DESIGN_ROOT / route_name / version
  manifest_path = design_dir / "manifest.json"
  if design_dir.exists():
    raise CoverWorkflowError(
      f"Pencil design {route_name}/{version} is already registered; create a new version"
    )
  design_dir.mkdir(parents=True, exist_ok=False)

  assets = {
    "pencilSource": (source_path, design_dir / copied_name("pencil-source", source_path)),
    "preview3x4": (preview_3x4_path, design_dir / copied_name("preview-3x4", preview_3x4_path)),
    "preview4x3": (preview_4x3_path, design_dir / copied_name("preview-4x3", preview_4x3_path)),
  }
  for source, destination in assets.values():
    shutil.copy2(source, destination)

  tokens_path = design_dir / "renderer-tokens.json"
  write_json(tokens_path, style_tokens)

  routes_changed = existing_tokens is None
  if routes_changed:
    versions[version] = style_tokens
  if activate and route_config.get("defaultVersion") != version:
    route_config["defaultVersion"] = version
    routes_changed = True
  if routes_changed:
    write_json(routes_path, routes)

  manifest = {
    "schemaVersion": 1,
    "tool": "pencil",
    "route": route_name,
    "styleVersion": version,
    "active": route_config.get("defaultVersion") == version,
    "createdAt": now_iso(),
    "note": note.strip(),
    "tokenHash": canonical_hash(style_tokens),
    "previewDimensions": preview_dimensions,
    "assets": {
      key: relative_path(root, destination)
      for key, (_, destination) in assets.items()
    } | {"rendererTokens": relative_path(root, tokens_path)},
    "assetHashes": {
      key: file_hash(destination)
      for key, (_, destination) in assets.items()
    } | {"rendererTokens": file_hash(tokens_path)},
  }
  write_json(manifest_path, manifest)

  return {
    "route": route_name,
    "styleVersion": version,
    "active": manifest["active"],
    "routesChanged": routes_changed,
    "manifest": relative_path(root, manifest_path),
    "tokenHash": manifest["tokenHash"],
  }


def run_command(command: List[str], root: Path) -> subprocess.CompletedProcess:
  try:
    return subprocess.run(
      command,
      cwd=root,
      text=True,
      capture_output=True,
      check=True,
    )
  except (OSError, subprocess.CalledProcessError) as error:
    stderr = getattr(error, "stderr", "") or ""
    stdout = getattr(error, "stdout", "") or ""
    detail = stderr.strip() or stdout.strip() or str(error)
    raise CoverWorkflowError(f"Cover command failed: {detail}") from error


def parse_key_values(text: str) -> Dict[str, str]:
  values = {}
  for line in text.splitlines():
    key, separator, value = line.partition("=")
    if separator and key.strip():
      values[key.strip()] = value.strip()
  return values


def default_output_prefix(
  root: Path,
  date: str,
  route: str,
  day_label: str,
  content_type: str = "video-diary",
  sequence: str = "001",
) -> Path:
  day_token = re.sub(r"[^A-Za-z0-9]+", "", day_label)
  identity = day_token or route.replace("-", "_")
  export_dir = ContentRef(date, content_type, sequence).media_dir(root, "05_exports")
  return export_dir / f"{date}_{identity}_cover"


def make_cover_pair(
  root: Path,
  date: str,
  portrait: str | Path,
  landscape: Optional[str | Path] = None,
  route: str = "video-diary",
  version: str = "",
  day_label: str = "",
  title: str = "",
  book_title: str = "",
  subtitle: str = "",
  note: str = "",
  output_prefix: Optional[str | Path] = None,
  content_type: Optional[str] = None,
  sequence: str = "001",
) -> Dict[str, Any]:
  root = root.resolve()
  if not DATE_RE.fullmatch(date):
    raise CoverWorkflowError("Date must use YYYY-MM-DD")

  _, routes = load_routes(root)
  route_name = normalize_route(routes, route)
  resolved_content_type = content_type or route_name
  route_config = routes["routes"][route_name]
  style_version = version or route_config.get("defaultVersion", "")
  if style_version not in route_config.get("versions", {}):
    raise CoverWorkflowError(f"Unknown style version for {route_name}: {style_version}")

  portrait_path = require_file(root, portrait, "portrait cover source")
  landscape_path = require_file(root, landscape, "landscape cover source") if landscape else None
  prefix = (
    resolve_path(root, output_prefix)
    if output_prefix
    else default_output_prefix(
      root, date, route_name, day_label, resolved_content_type, sequence
    )
  )
  prefix.parent.mkdir(parents=True, exist_ok=True)

  render_script = root / ".codex/skills/video-diary-cover/scripts/render-cover-pair.py"
  command = [
    sys.executable,
    str(render_script),
    "--date",
    date,
    "--content-type",
    resolved_content_type,
    "--sequence",
    sequence,
    "--route",
    route_name,
    "--style-version",
    style_version,
    "--day-label",
    day_label,
    "--base-frame-3x4",
    str(portrait_path),
    "--output-prefix",
    str(prefix),
  ]
  if landscape_path:
    command.extend(["--base-frame-4x3", str(landscape_path)])
  for flag, value in [
    ("--title", title),
    ("--book-title", book_title),
    ("--subtitle", subtitle),
    ("--note", note),
  ]:
    if value:
      command.extend([flag, value])
  render_result = run_command(command, root)

  output_3x4 = prefix.parent / f"{prefix.name}_3x4.jpg"
  output_4x3 = prefix.parent / f"{prefix.name}_4x3.jpg"
  manifest_path = ContentRef(
    date, resolved_content_type, sequence
  ).media_dir(root, "04_videos") / "cover-qc" / f"{prefix.name}_pair_manifest.json"
  for path in [output_3x4, output_4x3]:
    if not path.is_file():
      raise CoverWorkflowError(f"Cover renderer did not create: {path}")
  if not manifest_path.is_file():
    raise CoverWorkflowError(f"Cover renderer did not create its pair manifest: {manifest_path}")

  node_bin = os.environ.get("NODE_BIN") or shutil.which("node") or "node"
  archive_script = root / ".codex/skills/video-diary-cover/scripts/archive-cover.mjs"
  archived = {}
  for aspect, output_path in [("3x4", output_3x4), ("4x3", output_4x3)]:
    archive_note = f"{aspect} | {note}" if note else aspect
    archive_command = [
      node_bin,
      str(archive_script),
      date,
      "--content-type",
      resolved_content_type,
      "--sequence",
      sequence,
      "--source",
      str(output_path),
      "--route",
      route_name,
      "--style-version",
      style_version,
      "--title",
      title or book_title,
      "--note",
      archive_note,
    ]
    archive_result = run_command(archive_command, root)
    archived[aspect] = parse_key_values(archive_result.stdout).get("cover", "")

  gallery_script = root / ".codex/skills/video-diary-cover/scripts/build-gallery-index.mjs"
  gallery_result = run_command([node_bin, str(gallery_script)], root)
  gallery = parse_key_values(gallery_result.stdout).get("gallery", "15_cover_gallery/INDEX.md")

  return {
    "date": date,
    "contentType": resolved_content_type,
    "sequence": ContentRef(date, resolved_content_type, sequence).sequence,
    "route": route_name,
    "styleVersion": style_version,
    "covers": {
      "3x4": relative_path(root, output_3x4),
      "4x3": relative_path(root, output_4x3),
    },
    "archived": archived,
    "pairManifest": relative_path(root, manifest_path),
    "gallery": gallery,
    "rendererOutput": parse_key_values(render_result.stdout),
  }


def parse_gallery_rows(index_path: Path, route: str) -> List[Dict[str, str]]:
  if not index_path.is_file():
    return []
  rows = []
  for line in index_path.read_text(encoding="utf-8").splitlines():
    if not line.startswith("|"):
      continue
    cells = [cell.strip() for cell in line.split("|")[1:-1]]
    if not cells or cells[0] == "version" or all(re.fullmatch(r"-+", cell) for cell in cells):
      continue
    if len(cells) < 6 or (route and cells[2] != route):
      continue
    rows.append({
      "version": cells[0],
      "file": cells[1],
      "route": cells[2],
      "styleVersion": cells[3],
      "title": cells[4],
      "note": cells[5],
    })
  return rows


def list_cover_history(root: Path, route: str = "", limit: int = 20) -> Dict[str, Any]:
  root = root.resolve()
  _, routes = load_routes(root)
  route_name = normalize_route(routes, route) if route else ""
  route_names = [route_name] if route_name else sorted(routes["routes"])

  styles = []
  for name in route_names:
    route_config = routes["routes"][name]
    for version in route_config.get("versions", {}):
      manifest_path = root / DESIGN_ROOT / name / version / "manifest.json"
      manifest = load_json(manifest_path) if manifest_path.is_file() else {}
      styles.append({
        "route": name,
        "styleVersion": version,
        "default": route_config.get("defaultVersion") == version,
        "origin": "pencil" if manifest else "renderer-config",
        "manifest": relative_path(root, manifest_path) if manifest else "",
        "createdAt": manifest.get("createdAt", ""),
        "note": manifest.get("note", ""),
      })

  revisions = []
  gallery_root = root / "15_cover_gallery"
  if gallery_root.is_dir():
    for date_dir in sorted(gallery_root.iterdir(), reverse=True):
      if not date_dir.is_dir() or not DATE_RE.fullmatch(date_dir.name):
        continue
      indexes = sorted(date_dir.glob("*/*/INDEX.md"), reverse=True)
      legacy_index = date_dir / "INDEX.md"
      if legacy_index.is_file():
        indexes.append(legacy_index)
      for index_path in indexes:
        relative_parts = index_path.relative_to(date_dir).parts
        content_type = relative_parts[0] if len(relative_parts) >= 3 else "video-diary"
        sequence = relative_parts[1] if len(relative_parts) >= 3 else "001"
        for row in parse_gallery_rows(index_path, route_name):
          revisions.append({
            "date": date_dir.name,
            "contentType": content_type,
            "sequence": sequence,
            **row,
          })
          if len(revisions) >= max(1, limit):
            break
        if len(revisions) >= max(1, limit):
          break
      if len(revisions) >= max(1, limit):
        break

  return {
    "route": route_name or "all",
    "styleVersions": styles,
    "dailyRevisions": revisions,
    "styleCount": len(styles),
    "revisionCount": len(revisions),
  }
