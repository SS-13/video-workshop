"""Canonical date-first paths for every content type."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import re


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CONTENT_TYPE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEQUENCE_RE = re.compile(r"^\d{3}$")
CONTENT_TYPES = ("video-diary", "suisuinian", "reading-note")
TEXT_STAGES = ("01_inbox", "02_scripts", "06_logs")
MEDIA_STAGES = ("03_recordings", "04_videos", "05_exports", "15_cover_gallery")


class ContentLayoutError(ValueError):
  pass


def normalize_sequence(value: str | int) -> str:
  try:
    number = int(value)
  except (TypeError, ValueError) as error:
    raise ContentLayoutError("Sequence must be a positive integer.") from error
  if number < 1 or number > 999:
    raise ContentLayoutError("Sequence must be between 1 and 999.")
  return f"{number:03d}"


@dataclass(frozen=True)
class ContentRef:
  date: str
  content_type: str = "video-diary"
  sequence: str = "001"

  def __post_init__(self) -> None:
    if not DATE_RE.fullmatch(self.date):
      raise ContentLayoutError("Date must use YYYY-MM-DD.")
    if not CONTENT_TYPE_RE.fullmatch(self.content_type):
      raise ContentLayoutError("Content type must use lowercase kebab-case.")
    object.__setattr__(self, "sequence", normalize_sequence(self.sequence))

  @property
  def content_key(self) -> str:
    return f"{self.date}/{self.content_type}/{self.sequence}"

  @property
  def generic_content_id(self) -> str:
    return f"{self.date}_{self.content_type}_{self.sequence}"

  def text_path(self, root: Path, stage: str) -> Path:
    if stage not in TEXT_STAGES:
      raise ContentLayoutError(f"Not a text stage: {stage}")
    return Path(root) / stage / self.date / self.content_type / f"{self.sequence}.md"

  def media_dir(self, root: Path, stage: str) -> Path:
    if stage not in MEDIA_STAGES:
      raise ContentLayoutError(f"Not a media stage: {stage}")
    return Path(root) / stage / self.date / self.content_type / self.sequence

  def stage_path(self, root: Path, stage: str) -> Path:
    if stage in TEXT_STAGES:
      return self.text_path(root, stage)
    return self.media_dir(root, stage)

  def relative_stage_path(self, stage: str) -> str:
    path = self.stage_path(Path("."), stage)
    value = path.as_posix()
    return value[2:] if value.startswith("./") else value


def next_sequence(root: Path, date: str, content_type: str) -> str:
  found = set()
  probe = ContentRef(date, content_type, "001")
  for stage in (*TEXT_STAGES, *MEDIA_STAGES):
    parent = Path(root) / stage / probe.date / probe.content_type
    if not parent.is_dir():
      continue
    for child in parent.iterdir():
      token = child.stem if stage in TEXT_STAGES else child.name
      if SEQUENCE_RE.fullmatch(token):
        found.add(int(token))
  return normalize_sequence(max(found, default=0) + 1)


def ensure_content_directories(root: Path, ref: ContentRef) -> Iterable[Path]:
  created = []
  for stage in TEXT_STAGES:
    parent = ref.text_path(root, stage).parent
    if not parent.exists():
      parent.mkdir(parents=True, exist_ok=True)
      created.append(parent)
  for stage in MEDIA_STAGES:
    directory = ref.media_dir(root, stage)
    if not directory.exists():
      directory.mkdir(parents=True, exist_ok=True)
      created.append(directory)
  return created
