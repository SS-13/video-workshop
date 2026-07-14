"""Compare a candidate SRT with a reviewed golden transcript."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import re
import unicodedata


TIMING_RE = re.compile(r"\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}")


def srt_text(path: Path) -> str:
  rows = []
  for line in path.read_text(encoding="utf-8-sig").splitlines():
    value = line.strip()
    if not value or value.isdigit() or TIMING_RE.fullmatch(value):
      continue
    rows.append(value)
  return "".join(rows)


def normalize_text(value: str) -> str:
  normalized = unicodedata.normalize("NFKC", value).lower()
  return "".join(character for character in normalized if character.isalnum())


def edit_distance(left: str, right: str) -> int:
  if len(left) < len(right):
    left, right = right, left
  previous = list(range(len(right) + 1))
  for left_index, left_character in enumerate(left, 1):
    current = [left_index]
    for right_index, right_character in enumerate(right, 1):
      current.append(min(
        current[-1] + 1,
        previous[right_index] + 1,
        previous[right_index - 1] + (left_character != right_character),
      ))
    previous = current
  return previous[-1]


def compare_transcripts(actual_path: Path, expected_path: Path, min_accuracy: float) -> Dict[str, Any]:
  actual = normalize_text(srt_text(actual_path))
  expected = normalize_text(srt_text(expected_path))
  distance = edit_distance(actual, expected)
  denominator = max(1, len(expected))
  error_rate = distance / denominator
  accuracy = max(0.0, 1.0 - error_rate)
  return {
    "passed": accuracy >= min_accuracy,
    "actual": str(actual_path),
    "expected": str(expected_path),
    "actualCharacters": len(actual),
    "expectedCharacters": len(expected),
    "editDistance": distance,
    "characterErrorRate": round(error_rate, 6),
    "accuracy": round(accuracy, 6),
    "minimumAccuracy": min_accuracy,
    "normalizedActual": actual,
    "normalizedExpected": expected,
  }
