"""Reconcile durable content state from canonical production statistics."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import csv
import json
import os
import re
import tempfile


DAY_RE = re.compile(r"Day\s*(\d+)", re.IGNORECASE)
CONTENT_LEDGER_FIELDS = [
  "content_id",
  "date",
  "column",
  "day_label",
  "title",
  "status",
  "inbox_ref",
  "script_ref",
  "recording_ref",
  "workspace_ref",
  "export_ref",
  "cover_ref",
  "published_at",
  "douyin_url",
  "notes",
]


def read_csv(path: Path) -> List[Dict[str, str]]:
  if not path.exists():
    return []
  with path.open("r", encoding="utf-8-sig", newline="") as file:
    return list(csv.DictReader(file))


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  descriptor, temporary_name = tempfile.mkstemp(prefix="state-", suffix=".json", dir=str(path.parent))
  try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
      json.dump(payload, file, ensure_ascii=False, indent=2)
      file.write("\n")
    os.replace(temporary_name, path)
  finally:
    if os.path.exists(temporary_name):
      os.unlink(temporary_name)


def atomic_write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  descriptor, temporary_name = tempfile.mkstemp(prefix="ledger-", suffix=".csv", dir=str(path.parent))
  try:
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as file:
      writer = csv.DictWriter(file, fieldnames=CONTENT_LEDGER_FIELDS)
      writer.writeheader()
      for row in rows:
        writer.writerow({field: row.get(field, "") for field in CONTENT_LEDGER_FIELDS})
    os.replace(temporary_name, path)
  finally:
    if os.path.exists(temporary_name):
      os.unlink(temporary_name)


def day_number(value: str) -> Optional[int]:
  match = DAY_RE.search(value or "")
  return int(match.group(1)) if match else None


def production_rows(root: Path) -> List[Dict[str, str]]:
  rows = read_csv(root / "00_state" / "production-stats.csv")
  latest: Dict[str, Dict[str, str]] = {}
  for row in rows:
    if row.get("column") != "video-diary":
      continue
    number = day_number(row.get("day_label", ""))
    if not number:
      continue
    content_id = row.get("content_id") or f"{row.get('date', '')}_Day{number}"
    normalized = {**row, "content_id": content_id, "day_number": str(number)}
    latest[content_id] = normalized
  return sorted(latest.values(), key=lambda row: int(row["day_number"]))


def default_reference(root: Path, value: str) -> str:
  return value if (root / value).exists() else value


def desired_ledger_row(
  root: Path,
  stats: Dict[str, str],
  existing: Optional[Dict[str, str]],
) -> Dict[str, str]:
  date = stats.get("date", "")
  current = dict(existing or {})
  current_status = current.get("status", "")
  early_statuses = {"", "initialized", "scripted", "recorded", "editing"}
  promote_existing = existing is None or current_status in early_statuses
  if promote_existing:
    desired_title = stats.get("title") or current.get("title", "")
  else:
    desired_title = current.get("title", "") or stats.get("title", "")
  note = current.get("notes", "")
  backfill_note = "Reconciled from 00_state/production-stats.csv."
  if existing is None and not note:
    note = backfill_note
  return {
    **{field: current.get(field, "") for field in CONTENT_LEDGER_FIELDS},
    "content_id": stats["content_id"],
    "date": date,
    "column": "video-diary",
    "day_label": stats.get("day_label", ""),
    "title": desired_title,
    "status": "exported" if promote_existing else current_status,
    "inbox_ref": current.get("inbox_ref") or default_reference(
      root, f"01_inbox/{date}/video-diary/001.md"
    ),
    "script_ref": current.get("script_ref") or default_reference(
      root, f"02_scripts/{date}/video-diary/001.md"
    ),
    "recording_ref": current.get("recording_ref") or f"03_recordings/{date}/video-diary/001/",
    "workspace_ref": current.get("workspace_ref") or f"04_videos/{date}/video-diary/001/",
    "export_ref": current.get("export_ref") or stats.get("video_path", ""),
    "cover_ref": current.get("cover_ref") or stats.get("cover_path", ""),
    "notes": note,
  }


def package_content_date(package: Dict[str, Any]) -> str:
  for value in [
    package.get("contentId", ""),
    package.get("runId", ""),
    *package.get("artifacts", {}).values(),
  ]:
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    if match:
      return match.group(0)
  return ""


def finalize_content_ledger(root: Path, package: Dict[str, Any]) -> Dict[str, Any]:
  """Idempotently close one content item after a publish-ready run."""
  content_id = str(package.get("contentId", "")).strip()
  content_type = str(package.get("contentType", "video-diary")).strip() or "video-diary"
  sequence = str(package.get("sequence", "001")).zfill(3)
  date = package_content_date(package)
  if not content_id or not date:
    return {"changed": False, "contentId": content_id, "error": "missing_content_identity"}

  ledger_path = root / "00_state" / "content-ledger.csv"
  rows = read_csv(ledger_path)
  by_id = {row.get("content_id", ""): row for row in rows}
  existing = by_id.get(content_id)
  day_match = re.search(r"Day\s*(\d+)", content_id, re.IGNORECASE)
  day_label = f"Day {day_match.group(1)}" if day_match else ""
  artifacts = package.get("artifacts", {})
  desired = {
    **{field: existing.get(field, "") if existing else "" for field in CONTENT_LEDGER_FIELDS},
    "content_id": content_id,
    "date": date,
    "column": content_type,
    "day_label": existing.get("day_label", "") if existing else day_label,
    "title": str(package.get("title", "")).strip() or (existing.get("title", "") if existing else ""),
    "status": "exported",
    "inbox_ref": (existing.get("inbox_ref", "") if existing else "") or f"01_inbox/{date}/{content_type}/{sequence}.md",
    "script_ref": (existing.get("script_ref", "") if existing else "") or f"02_scripts/{date}/{content_type}/{sequence}.md",
    "recording_ref": (existing.get("recording_ref", "") if existing else "") or f"03_recordings/{date}/{content_type}/{sequence}/",
    "workspace_ref": (existing.get("workspace_ref", "") if existing else "") or f"04_videos/{date}/{content_type}/{sequence}/",
    "export_ref": str(artifacts.get("video", "")).strip() or (existing.get("export_ref", "") if existing else ""),
    "cover_ref": str(artifacts.get("cover3x4", "")).strip() or (existing.get("cover_ref", "") if existing else ""),
    "notes": (existing.get("notes", "") if existing else "") or "Finalized from publish-ready package.",
  }

  changed = existing is None or any(
    (existing or {}).get(field, "") != desired.get(field, "")
    for field in CONTENT_LEDGER_FIELDS
  )
  if not changed:
    return {"changed": False, "contentId": content_id, "ledgerPath": str(ledger_path)}

  by_id[content_id] = desired
  atomic_write_csv(
    ledger_path,
    sorted(by_id.values(), key=lambda row: (row.get("date", ""), row.get("content_id", ""))),
  )
  return {
    "changed": True,
    "contentId": content_id,
    "ledgerPath": str(ledger_path),
    "status": desired["status"],
  }


def reconcile_state(root: Path, apply: bool = False) -> Dict[str, Any]:
  stats_rows = production_rows(root)
  if not stats_rows:
    return {
      "valid": False,
      "applied": False,
      "errors": ["no_video_diary_production_rows"],
      "changes": [],
    }

  latest = max(stats_rows, key=lambda row: int(row["day_number"]))
  counter_path = root / "00_state" / "day-counter.json"
  counter = json.loads(counter_path.read_text(encoding="utf-8")) if counter_path.exists() else {}
  desired_counter = {
    **counter,
    "series": "video-diary",
    "lastDay": int(latest["day_number"]),
    "lastContentId": latest["content_id"],
    "updatedAt": latest.get("date", ""),
    "rules": {
      "videoDiaryIncrementsDay": True,
      "suisuinianIncrementsDay": False,
      "readingNoteIncrementsDay": False,
    },
    "notes": "Only the video-diary column increments Day. Reconciled from production statistics.",
  }

  ledger_path = root / "00_state" / "content-ledger.csv"
  ledger_rows = read_csv(ledger_path)
  ledger_by_id = {row.get("content_id", ""): row for row in ledger_rows}
  reconciled_by_id = dict(ledger_by_id)
  updated_ids = []
  added_ids = []
  for stats in stats_rows:
    content_id = stats["content_id"]
    existing = ledger_by_id.get(content_id)
    desired = desired_ledger_row(root, stats, existing)
    if existing is None:
      added_ids.append(content_id)
    elif any(existing.get(field, "") != desired.get(field, "") for field in CONTENT_LEDGER_FIELDS):
      updated_ids.append(content_id)
    reconciled_by_id[content_id] = desired

  reconciled_rows = sorted(
    reconciled_by_id.values(),
    key=lambda row: (row.get("date", ""), row.get("content_id", "")),
  )
  counter_changed = counter != desired_counter
  changes = []
  if counter_changed:
    changes.append({
      "component": "day-counter",
      "from": counter.get("lastDay"),
      "to": desired_counter["lastDay"],
    })
  if added_ids or updated_ids:
    changes.append({
      "component": "content-ledger",
      "added": added_ids,
      "updated": updated_ids,
    })

  if apply:
    atomic_write_json(counter_path, desired_counter)
    atomic_write_csv(ledger_path, reconciled_rows)

  return {
    "valid": True,
    "applied": apply,
    "latestContentId": latest["content_id"],
    "latestDay": int(latest["day_number"]),
    "counterChanged": counter_changed,
    "ledgerAdded": added_ids,
    "ledgerUpdated": updated_ids,
    "changes": changes,
    "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
  }
