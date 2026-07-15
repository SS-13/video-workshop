#!/usr/bin/env python3
"""Deterministic P0 Daily Engineering Loop."""

from __future__ import annotations

from datetime import date as date_type, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import hashlib
import json
import os
import re
import tempfile
import unicodedata
import uuid


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_PRIORITIES = ("P0", "P1", "P2", "P3")
VALID_CATEGORIES = {
  "bug",
  "content-rule",
  "visual-rule",
  "subtitle-rule",
  "platform-rule",
  "performance",
  "token-cost",
  "new-capability",
  "temporary-exception",
  "integration-request",
  "uncategorized",
}
PRODUCTION_ISSUE_CATEGORIES = {
  "bug",
  "performance",
  "integration-request",
  "temporary-exception",
}
VALID_SCOPES = {
  "single-run",
  "content-profile",
  "workspace-user",
  "system-core",
  "platform-adapter",
}
VALID_CHANGE_TYPES = ("bugfix", "feature", "major-evolution")
CHANGE_TYPE_DEFAULTS = {
  "bugfix": {
    "recommendedSemVer": "patch",
    "compatibilityImpact": "backward-compatible-fix",
    "requiresMigration": False,
    "requiresCanary": False,
  },
  "feature": {
    "recommendedSemVer": "minor",
    "compatibilityImpact": "backward-compatible-feature",
    "requiresMigration": False,
    "requiresCanary": False,
  },
  "major-evolution": {
    "recommendedSemVer": "major",
    "compatibilityImpact": "core-contract-change",
    "requiresMigration": True,
    "requiresCanary": True,
  },
}
DEFAULT_POLICY = {
  "schemaVersion": 3,
  "topK": 3,
  "lookbackDays": 7,
  "repeatThreshold": 2,
  "priorityOrder": list(VALID_PRIORITIES),
  "candidateRules": {
    "explicitPromotionRequest": True,
    "repeatedObservation": True,
    "p0AlwaysEligible": True,
    "deterministicFinding": True,
  },
  "selection": {
    "freezeDailyTopK": True,
    "carryForwardBacklog": True,
    "priorityAging": {
      "enabled": True,
      "daysPerLevel": 1,
      "maximumPriority": "P0",
      "p0OldestFirst": True,
    },
  },
  "automation": {
    "modifyFormalRules": False,
    "modifySkills": False,
    "modifyHooks": False,
    "bumpVersion": False,
  },
}


class EvolutionError(Exception):
  pass


class ObservationParseError(EvolutionError):
  def __init__(self, errors: List[Dict[str, Any]]):
    super().__init__("Observation data contains invalid NDJSON.")
    self.errors = errors


class EvolutionDeferred(EvolutionError):
  def __init__(self, locks: List[str]):
    super().__init__("Evolution deferred because production is active.")
    self.locks = locks


class LeaseBusy(EvolutionError):
  def __init__(self, path: Path):
    super().__init__(f"Lease is already held: {path}")
    self.path = path


def now_iso() -> str:
  return datetime.now().astimezone().isoformat(timespec="seconds")


def validate_date(value: str) -> str:
  if not DATE_RE.match(value):
    raise EvolutionError(f"Invalid date: {value}")
  try:
    date_type.fromisoformat(value)
  except ValueError as error:
    raise EvolutionError(f"Invalid date: {value}") from error
  return value


def find_project_root(start: Optional[Path] = None) -> Path:
  current = (start or Path.cwd()).resolve()
  for candidate in [current, *current.parents]:
    if (candidate / "package.json").exists() and (candidate / ".codex").exists():
      return candidate
  raise EvolutionError("Could not locate the video production project root.")


def load_json(path: Path) -> Dict[str, Any]:
  return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_text(path: Path, content: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
  try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
      file.write(content)
      file.flush()
      os.fsync(file.fileno())
    os.replace(temp_name, path)
  finally:
    if os.path.exists(temp_name):
      os.unlink(temp_name)


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
  content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
  atomic_write_text(path, content)


def completion_path(root: Path, target_date: str) -> Path:
  return root / "00_state" / "evolution" / "completed" / f"{target_date}.json"


def load_completed_candidates(root: Path) -> Dict[str, Dict[str, Any]]:
  completed: Dict[str, Dict[str, Any]] = {}
  completed_root = root / "00_state" / "evolution" / "completed"
  if not completed_root.exists():
    return completed
  for path in sorted(completed_root.glob("*.json")):
    try:
      payload = load_json(path)
    except (OSError, json.JSONDecodeError):
      continue
    for entry in payload.get("completed", []):
      candidate_id = str(entry.get("candidateId", "")).strip()
      if not candidate_id or candidate_id in completed:
        continue
      completed[candidate_id] = {
        **entry,
        "completionRecord": str(path.relative_to(root)),
      }
  return completed


def verified_relative_paths(root: Path, values: Iterable[str], label: str) -> List[str]:
  verified: List[str] = []
  for value in values:
    raw = str(value).strip()
    if not raw:
      continue
    path = Path(raw)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
      relative = resolved.relative_to(root)
    except ValueError as error:
      raise EvolutionError(f"{label} must stay inside the workspace: {raw}") from error
    if not resolved.exists():
      raise EvolutionError(f"{label} does not exist: {relative}")
    normalized = str(relative)
    if normalized not in verified:
      verified.append(normalized)
  return verified


class FileLease:
  def __init__(self, path: Path, actor: str, command: str):
    self.path = path
    self.actor = actor
    self.command = command
    self.lease_id = uuid.uuid4().hex
    self.acquired = False

  def __enter__(self) -> "FileLease":
    self.path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
      "leaseId": self.lease_id,
      "actor": self.actor,
      "command": self.command,
      "acquiredAt": now_iso(),
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
      descriptor = os.open(str(self.path), flags, 0o600)
    except FileExistsError as error:
      raise LeaseBusy(self.path) from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
      json.dump(payload, file, ensure_ascii=False, indent=2)
      file.write("\n")
    self.acquired = True
    return self

  def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
    if not self.acquired or not self.path.exists():
      return
    try:
      payload = load_json(self.path)
    except (OSError, json.JSONDecodeError):
      return
    if payload.get("leaseId") == self.lease_id:
      self.path.unlink()


def load_policy(root: Path) -> Dict[str, Any]:
  path = root / "00_system" / "evolution-policy.json"
  policy = dict(DEFAULT_POLICY)
  if path.exists():
    loaded = load_json(path)
    policy.update(loaded)
  top_k = int(policy.get("topK", 3))
  lookback_days = int(policy.get("lookbackDays", 7))
  repeat_threshold = int(policy.get("repeatThreshold", 2))
  if top_k < 1 or top_k > 50:
    raise EvolutionError("topK must be between 1 and 50.")
  if lookback_days < 1 or lookback_days > 365:
    raise EvolutionError("lookbackDays must be between 1 and 365.")
  if repeat_threshold < 1:
    raise EvolutionError("repeatThreshold must be positive.")
  policy["topK"] = top_k
  policy["lookbackDays"] = lookback_days
  policy["repeatThreshold"] = repeat_threshold
  return policy


def normalize_text(value: str) -> str:
  text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
  text = re.sub(r"[\s\-_.,，。:：;；!！?？'\"“”‘’()（）\[\]{}]+", "", text)
  return text


def normalize_observation(payload: Dict[str, Any], fallback_id: Optional[str] = None) -> Dict[str, Any]:
  summary = str(payload.get("summary", "")).strip()
  if not summary:
    raise EvolutionError("Observation summary is required.")
  observation_date = validate_date(str(payload.get("date", "")))
  priority = str(payload.get("priority", "P2")).upper()
  if priority not in VALID_PRIORITIES:
    priority = "P2"
  category = str(payload.get("category", "uncategorized")).strip().lower()
  if category not in VALID_CATEGORIES:
    category = "uncategorized"
  scope = str(payload.get("scope", "single-run")).strip().lower()
  if scope not in VALID_SCOPES:
    scope = "single-run"
  component = str(
    payload.get("affectedComponent", payload.get("component", "general"))
  ).strip() or "general"
  created_at = str(payload.get("createdAt", f"{observation_date}T00:00:00+08:00"))
  observation_id = str(payload.get("id", fallback_id or "")).strip()
  if not observation_id:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    observation_id = f"OBS-{observation_date.replace('-', '')}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:10]}"
  raw_content_id = payload.get("contentId")
  content_id = str(raw_content_id).strip() if raw_content_id is not None else ""
  return {
    "id": observation_id,
    "date": observation_date,
    "contentId": content_id or None,
    "actor": str(payload.get("actor", "unknown")).strip() or "unknown",
    "source": str(payload.get("source", "unknown")).strip().lower() or "unknown",
    "category": category,
    "priority": priority,
    "scope": scope,
    "affectedComponent": component,
    "summary": summary,
    "evidence": payload.get("evidence", {}),
    "promoteRequested": bool(payload.get("promoteRequested", False)),
    "deterministicFinding": bool(payload.get("deterministicFinding", False)),
    "createdAt": created_at,
    "status": str(payload.get("status", "observed")),
  }


def observation_fingerprint(observation: Dict[str, Any]) -> str:
  parts = [
    observation["category"],
    observation["scope"],
    normalize_text(observation["affectedComponent"]),
    normalize_text(observation["summary"]),
  ]
  return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def observation_dates(target_date: str, lookback_days: int) -> Iterable[str]:
  end = date_type.fromisoformat(target_date)
  start = end - timedelta(days=lookback_days - 1)
  for offset in range(lookback_days):
    yield (start + timedelta(days=offset)).isoformat()


def read_observation_files(
  root: Path,
  target_date: str,
  lookback_days: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
  observations: List[Dict[str, Any]] = []
  errors: List[Dict[str, Any]] = []
  observation_root = root / "00_state" / "observations"
  for current_date in observation_dates(target_date, lookback_days):
    path = observation_root / f"{current_date}.ndjson"
    if not path.exists():
      continue
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
      if not line.strip():
        continue
      try:
        raw = json.loads(line)
        fallback_id = f"OBS-{current_date.replace('-', '')}-{line_number:04d}"
        observations.append(normalize_observation(raw, fallback_id=fallback_id))
      except (json.JSONDecodeError, EvolutionError, TypeError) as error:
        errors.append({
          "path": str(path.relative_to(root)),
          "line": line_number,
          "error": str(error),
        })
  return observations, errors


def priority_rank(priority: str, policy: Dict[str, Any]) -> int:
  order = policy.get("priorityOrder", list(VALID_PRIORITIES))
  try:
    return list(order).index(priority)
  except ValueError:
    return len(order)


def timestamp_value(value: str) -> float:
  try:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
  except ValueError:
    return 0.0


def effective_priority(
  priority: str,
  first_seen_at: str,
  target_date: str,
  policy: Dict[str, Any],
) -> Tuple[str, int, int]:
  selection = policy.get("selection", {})
  aging = selection.get("priorityAging", {})
  if not aging.get("enabled", False):
    return priority, 0, 0
  try:
    first_date = datetime.fromisoformat(first_seen_at.replace("Z", "+00:00")).date()
  except ValueError:
    first_date = date_type.fromisoformat(target_date)
  age_days = max(0, (date_type.fromisoformat(target_date) - first_date).days)
  days_per_level = max(1, int(aging.get("daysPerLevel", 1)))
  raised_by = age_days // days_per_level
  original_rank = priority_rank(priority, policy)
  maximum_rank = priority_rank(str(aging.get("maximumPriority", "P0")), policy)
  effective_rank = max(maximum_rank, original_rank - raised_by)
  order = list(policy.get("priorityOrder", VALID_PRIORITIES))
  if effective_rank >= len(order):
    return priority, age_days, 0
  return str(order[effective_rank]), age_days, max(0, original_rank - effective_rank)


def carried_backlog_ids(root: Path, target_date: str, lookback_days: int) -> set[str]:
  target = date_type.fromisoformat(target_date)
  carried = set()
  decided = set()
  for offset in range(1, lookback_days):
    state_path = root / "00_state" / "evolution" / f"{target - timedelta(days=offset)}.json"
    if not state_path.is_file():
      continue
    try:
      state = load_json(state_path)
    except (OSError, json.JSONDecodeError):
      continue
    for item in state.get("topK", []):
      candidate_id = str(item.get("id", ""))
      if candidate_id:
        decided.add(candidate_id)
    for item in state.get("backlog", []):
      candidate_id = str(item.get("id", ""))
      if candidate_id and candidate_id not in decided:
        carried.add(candidate_id)
        decided.add(candidate_id)
  return carried


def group_updates(
  observations: List[Dict[str, Any]],
  target_date: str,
  policy: Dict[str, Any],
  carry_forward_ids: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
  grouped: Dict[str, List[Dict[str, Any]]] = {}
  for observation in observations:
    fingerprint = observation_fingerprint(observation)
    grouped.setdefault(fingerprint, []).append(observation)

  updates: List[Dict[str, Any]] = []
  repeat_threshold = int(policy["repeatThreshold"])
  rules = policy.get("candidateRules", {})
  for fingerprint, items in grouped.items():
    candidate_id = f"CAND-{fingerprint[:12]}"
    today_items = [item for item in items if item["date"] == target_date]
    if not today_items and candidate_id not in (carry_forward_ids or set()):
      continue
    ordered = sorted(items, key=lambda item: (timestamp_value(item["createdAt"]), item["id"]))
    latest = ordered[-1]
    original_priority = min(
      (item["priority"] for item in items),
      key=lambda priority: priority_rank(priority, policy),
    )
    best_priority, age_days, priority_raised_by = effective_priority(
      original_priority, ordered[0]["createdAt"], target_date, policy
    )
    promote_requested = any(item["promoteRequested"] for item in items)
    deterministic = any(
      item["deterministicFinding"] or item["source"] in {"audit", "validator", "workflow-audit"}
      for item in items
    )
    reasons: List[str] = []
    if rules.get("explicitPromotionRequest", True) and promote_requested:
      reasons.append("explicit-promotion-request")
    if rules.get("repeatedObservation", True) and len(items) >= repeat_threshold:
      reasons.append("repeated-observation")
    if rules.get("p0AlwaysEligible", True) and best_priority == "P0":
      reasons.append("p0-priority")
    if rules.get("deterministicFinding", True) and deterministic:
      reasons.append("deterministic-finding")
    eligible = bool(reasons)
    base_score = (len(policy.get("priorityOrder", VALID_PRIORITIES)) - priority_rank(best_priority, policy)) * 100
    score = base_score
    score += 40 if promote_requested else 0
    score += 30 if deterministic else 0
    score += min(len(items), 20) * 5
    score += min(len(today_items), 10)
    updates.append({
      "id": candidate_id,
      "fingerprint": fingerprint,
      "summary": latest["summary"],
      "category": latest["category"],
      "priority": best_priority,
      "originalPriority": original_priority,
      "ageDays": age_days,
      "priorityRaisedBy": priority_raised_by,
      "scope": latest["scope"],
      "affectedComponent": latest["affectedComponent"],
      "occurrenceCount": len(items),
      "todayCount": len(today_items),
      "firstSeenAt": ordered[0]["createdAt"],
      "lastSeenAt": latest["createdAt"],
      "contentIds": sorted({item["contentId"] for item in items if item["contentId"]}),
      "observationIds": [item["id"] for item in ordered],
      "eligible": eligible,
      "eligibilityReasons": reasons,
      "promoteRequested": promote_requested,
      "deterministicFinding": deterministic,
      "rankScore": score,
      "status": "candidate" if eligible else "needs-evidence",
    })
  return updates


def select_top_k(
  updates: List[Dict[str, Any]],
  top_k: int,
  policy: Dict[str, Any],
  frozen_top_k: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
  eligible = [update for update in updates if update["eligible"]]
  p0_oldest_first = bool(
    policy.get("selection", {}).get("priorityAging", {}).get("p0OldestFirst", True)
  )

  def selection_key(update: Dict[str, Any]) -> Tuple[Any, ...]:
    rank = priority_rank(update["priority"], policy)
    p0_timestamp = (
      timestamp_value(update["firstSeenAt"])
      if p0_oldest_first and update["priority"] == "P0"
      else float("inf")
    )
    return (
      rank,
      p0_timestamp,
      -int(update["rankScore"]),
      -timestamp_value(update["lastSeenAt"]),
      update["fingerprint"],
    )

  eligible.sort(key=selection_key)
  eligible_by_id = {update["id"]: update for update in eligible}
  selected: List[Dict[str, Any]] = []
  selected_ids = set()

  for previous in sorted(frozen_top_k or [], key=lambda update: int(update.get("rank", 999))):
    current = eligible_by_id.get(previous.get("id"))
    if current is None or current["id"] in selected_ids or len(selected) >= top_k:
      continue
    selected.append(current)
    selected_ids.add(current["id"])

  for update in eligible:
    if update["id"] in selected_ids or len(selected) >= top_k:
      continue
    selected.append(update)
    selected_ids.add(update["id"])

  ranked_selected: List[Dict[str, Any]] = []
  for rank, update in enumerate(selected, start=1):
    selected_update = dict(update)
    selected_update["rank"] = rank
    selected_update["selectedTopK"] = True
    selected_update["status"] = "candidate"
    ranked_selected.append(selected_update)

  backlog: List[Dict[str, Any]] = []
  for update in updates:
    if update["id"] in selected_ids:
      continue
    backlog_update = dict(update)
    backlog_update["selectedTopK"] = False
    backlog_update["status"] = "parked-topk" if update["eligible"] else "needs-evidence"
    backlog.append(backlog_update)
  backlog.sort(key=lambda update: (
    0 if update["eligible"] else 1,
    *selection_key(update),
  ))
  return ranked_selected, backlog


def canonical_hash(payload: Any) -> str:
  content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
  return hashlib.sha256(content.encode("utf-8")).hexdigest()


def markdown_cell(value: Any) -> str:
  return str(value).replace("|", "\\|").replace("\n", " ")


def priority_label(item: Dict[str, Any]) -> str:
  original = item.get("originalPriority", item.get("priority", ""))
  current = item.get("priority", "")
  return current if original == current else f"{original} -> {current}"


def build_report(state: Dict[str, Any]) -> str:
  lines = [
    f"# {state['date']} Daily Engineering Loop",
    "",
    f"- 系统版本：`{state['systemVersion']}`",
    f"- TopK：`{len(state['topK'])}/{state['topKLimit']}`",
    f"- TopK 选择模式：`{state.get('selectionMode', 'ranked')}`",
    f"- 当日 Observation：`{state['summary']['todayObservationCount']}`",
    f"- 去重后更新：`{state['summary']['deduplicatedUpdateCount']}`",
    f"- Eligible Candidate：`{state['summary']['eligibleCandidateCount']}`",
    f"- Backlog：`{state['summary']['backlogCount']}`",
    f"- TopK 已完成：`{state['summary'].get('completedTopKCount', 0)}`",
    "",
    "## 今日 TopK",
    "",
  ]
  if state["topK"]:
    lines.extend([
      "| Rank | Status | Priority | First seen | Age | Update | Occurrences | Reason |",
      "| ---: | --- | --- | --- | ---: | --- | ---: | --- |",
    ])
    for item in state["topK"]:
      lines.append(
        f"| {item['rank']} | {item['status']} | {priority_label(item)} | {item['firstSeenAt']} | "
        f"{item.get('ageDays', 0)}d | {markdown_cell(item['summary'])} | "
        f"{item['occurrenceCount']} | {', '.join(item['eligibilityReasons'])} |"
      )
  else:
    lines.append("今日没有达到 Candidate 条件的更新。")

  lines.extend(["", "## Backlog", ""])
  if state["backlog"]:
    lines.extend([
      "| Status | Priority | First seen | Age | Update | Occurrences |",
      "| --- | --- | --- | ---: | --- | ---: |",
    ])
    for item in state["backlog"]:
      lines.append(
        f"| {item['status']} | {priority_label(item)} | {item['firstSeenAt']} | "
        f"{item.get('ageDays', 0)}d | {markdown_cell(item['summary'])} | "
        f"{item['occurrenceCount']} |"
      )
  else:
    lines.append("无 backlog。")

  production_issues = [
    item for item in [*state["topK"], *state["backlog"]]
    if item.get("category") in PRODUCTION_ISSUE_CATEGORIES
  ]
  lines.extend(["", "## 生产问题清单", ""])
  if production_issues:
    lines.extend([
      "| Status | Priority | Component | Issue | Occurrences | Next |",
      "| --- | --- | --- | --- | ---: | --- |",
    ])
    next_action = {
      "candidate": "本轮工程候选",
      "completed": "已完成并进入 Release 候选清单",
      "parked-topk": "下一轮工程候选",
      "needs-evidence": "待复现/判断",
    }
    for item in production_issues:
      lines.append(
        f"| {item['status']} | {item['priority']} | "
        f"{markdown_cell(item['affectedComponent'])} | {markdown_cell(item['summary'])} | "
        f"{item['occurrenceCount']} | {next_action.get(item['status'], '待判断')} |"
      )
  else:
    lines.append("今日没有记录生产卡点。")

  lines.extend([
    "",
    "## P0 结论",
    "",
    "- 所有有效更新均已保留。",
    f"- 仅前 `{state['topKLimit']}` 项进入当日 TopK。",
    "- 当日 TopK 首次选定后保持锁定；持续新增内容进入 backlog。",
    f"- 今日 TopK 已有 `{state['summary'].get('completedTopKCount', 0)}` 项完成并写入追加式完成清单。",
    "- Backlog 每跨一个自然日提升一级，最高 P0；P0 按 firstSeenAt 从早到晚排序。",
    "- 生产卡点先记录、后归因；确认需要修复的问题进入下一轮工程 Loop。",
    "- 本次 Loop 未修改正式 Skill、Rule、Hook、Agent、生产脚本或版本号。",
    "",
  ])
  return "\n".join(lines)


def build_error_report(target_date: str, errors: List[Dict[str, Any]]) -> str:
  lines = [
    f"# {target_date} Daily Engineering Loop Error",
    "",
    "Observation NDJSON 存在解析错误。原始 Observation 和之前成功的 Evolution State 均未修改。",
    "",
    "| File | Line | Error |",
    "| --- | ---: | --- |",
  ]
  for item in errors:
    lines.append(
      f"| {markdown_cell(item['path'])} | {item['line']} | {markdown_cell(item['error'])} |"
    )
  lines.append("")
  return "\n".join(lines)


def active_production_locks(root: Path) -> List[str]:
  lock_root = root / "00_state" / "locks"
  if not lock_root.exists():
    return []
  return sorted(
    str(path.relative_to(root))
    for path in lock_root.glob("production-*.lock.json")
    if path.is_file()
  )


def complete_candidate(
  root: Path,
  target_date: str,
  candidate_id: str,
  change_type: str,
  evidence_paths: Iterable[str],
  artifact_paths: Iterable[str] = (),
  actor: str = "system-steward-agent",
  compatibility_impact: Optional[str] = None,
  requires_migration: Optional[bool] = None,
  requires_canary: Optional[bool] = None,
) -> Dict[str, Any]:
  target_date = validate_date(target_date)
  root = Path(root).resolve()
  candidate_id = str(candidate_id).strip()
  if not candidate_id:
    raise EvolutionError("Candidate id is required.")
  if change_type not in VALID_CHANGE_TYPES:
    raise EvolutionError(f"Invalid change type: {change_type}")
  production_locks = active_production_locks(root)
  if production_locks:
    raise EvolutionDeferred(production_locks)

  state_path = root / "00_state" / "evolution" / f"{target_date}.json"
  if not state_path.is_file():
    raise EvolutionError(f"Daily Evolution state does not exist: {target_date}")
  state = load_json(state_path)
  candidate = next(
    (item for item in state.get("topK", []) if item.get("id") == candidate_id),
    None,
  )
  if candidate is None:
    raise EvolutionError(f"Candidate is not in the locked TopK: {candidate_id}")

  evidence = verified_relative_paths(root, evidence_paths, "Evidence")
  artifacts = verified_relative_paths(root, artifact_paths, "Artifact")
  if not evidence:
    raise EvolutionError("At least one verification evidence path is required.")

  defaults = CHANGE_TYPE_DEFAULTS[change_type]
  completed_at = now_iso()
  entry = {
    "completionId": f"DONE-{candidate_id.removeprefix('CAND-')}",
    "candidateId": candidate_id,
    "summary": candidate.get("summary", ""),
    "priority": candidate.get("priority", "P2"),
    "rank": candidate.get("rank"),
    "completedAt": completed_at,
    "actor": actor,
    "validationEvidence": evidence,
    "artifacts": artifacts,
    "releaseCandidate": True,
    "releaseTarget": None,
    "changeType": change_type,
    "recommendedSemVer": defaults["recommendedSemVer"],
    "compatibilityImpact": compatibility_impact or defaults["compatibilityImpact"],
    "requiresMigration": (
      defaults["requiresMigration"] if requires_migration is None else requires_migration
    ),
    "requiresCanary": defaults["requiresCanary"] if requires_canary is None else requires_canary,
    "status": "completed",
  }

  ledger_path = completion_path(root, target_date)
  completion_lock = root / "00_state" / "locks" / "completion-write.lock.json"
  reused = False
  with FileLease(completion_lock, actor, "vp evolve complete"):
    ledger = {
      "schemaVersion": 1,
      "date": target_date,
      "completed": [],
    }
    if ledger_path.exists():
      ledger = load_json(ledger_path)
    existing = next(
      (
        item for item in ledger.get("completed", [])
        if item.get("candidateId") == candidate_id
      ),
      None,
    )
    if existing is not None:
      if existing.get("changeType") != change_type:
        raise EvolutionError(
          f"Completed candidate is immutable and already classified as "
          f"{existing.get('changeType')}: {candidate_id}"
        )
      entry = existing
      reused = True
    else:
      ledger.setdefault("completed", []).append(entry)
      ledger["updatedAt"] = completed_at
      atomic_write_json(ledger_path, ledger)

  evolution = run_evolution(root, target_date, actor=actor)
  completed_item = next(
    (item for item in evolution.get("topK", []) if item.get("id") == candidate_id),
    None,
  )
  if completed_item is None or completed_item.get("status") != "completed":
    raise EvolutionError(f"Completion state was not reconciled: {candidate_id}")
  return {
    "completion": entry,
    "completionRecord": str(ledger_path.relative_to(root)),
    "statePath": evolution["statePath"],
    "reportPath": evolution["reportPath"],
    "reused": reused,
  }


def system_version(root: Path) -> str:
  package_path = root / "package.json"
  if not package_path.exists():
    return "unknown"
  return str(load_json(package_path).get("version", "unknown"))


def record_observation(root: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
  observation_date = validate_date(str(payload.get("date", "")))
  timestamp = str(payload.get("createdAt", now_iso()))
  raw_summary = str(payload.get("summary", "")).strip()
  seed = f"{observation_date}|{timestamp}|{raw_summary}|{uuid.uuid4().hex}"
  observation_id = f"OBS-{observation_date.replace('-', '')}-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:10]}"
  observation = normalize_observation({
    **payload,
    "id": payload.get("id", observation_id),
    "createdAt": timestamp,
    "status": "observed",
  })
  observation_path = root / "00_state" / "observations" / f"{observation_date}.ndjson"
  lock_path = root / "00_state" / "locks" / "observation-write.lock.json"
  with FileLease(lock_path, observation["actor"], "vp observe"):
    existing = observation_path.read_text(encoding="utf-8") if observation_path.exists() else ""
    if existing:
      for line_number, line in enumerate(existing.splitlines(), start=1):
        if not line.strip():
          continue
        try:
          normalize_observation(json.loads(line))
        except (json.JSONDecodeError, EvolutionError, TypeError) as error:
          raise ObservationParseError([{
            "path": str(observation_path.relative_to(root)),
            "line": line_number,
            "error": str(error),
          }]) from error
    content = existing
    if content and not content.endswith("\n"):
      content += "\n"
    content += json.dumps(observation, ensure_ascii=False, sort_keys=True) + "\n"
    atomic_write_text(observation_path, content)
  return observation


def run_evolution(
  root: Path,
  target_date: str,
  top_k_override: Optional[int] = None,
  actor: str = "system-steward-agent",
  reselect: bool = False,
) -> Dict[str, Any]:
  target_date = validate_date(target_date)
  root = Path(root).resolve()
  production_locks = active_production_locks(root)
  if production_locks:
    raise EvolutionDeferred(production_locks)
  policy = load_policy(root)
  top_k = int(top_k_override if top_k_override is not None else policy["topK"])
  if top_k < 1 or top_k > 50:
    raise EvolutionError("topK must be between 1 and 50.")

  evolution_lock = root / "00_state" / "locks" / f"evolution-{target_date}.lock.json"
  observation_lock = root / "00_state" / "locks" / "observation-write.lock.json"
  with FileLease(evolution_lock, actor, "vp evolve"):
    with FileLease(observation_lock, actor, "vp evolve read"):
      observations, errors = read_observation_files(root, target_date, int(policy["lookbackDays"]))
    report_root = root / "17_reports" / "evolution"
    if errors:
      error_path = report_root / f"{target_date}-daily-evolution-error.md"
      atomic_write_text(error_path, build_error_report(target_date, errors))
      raise ObservationParseError(errors)

    state_path = root / "00_state" / "evolution" / f"{target_date}.json"
    report_path = report_root / f"{target_date}-daily-evolution.md"
    existing: Dict[str, Any] = {}
    if state_path.exists():
      try:
        existing = load_json(state_path)
      except (OSError, json.JSONDecodeError):
        existing = {}

    freeze_daily_top_k = bool(policy.get("selection", {}).get("freezeDailyTopK", True))
    frozen_top_k: Optional[List[Dict[str, Any]]] = None
    if (
      freeze_daily_top_k
      and not reselect
      and existing.get("date") == target_date
      and existing.get("topKLimit") == top_k
    ):
      frozen_top_k = existing.get("topK", [])

    carry_ids = (
      carried_backlog_ids(root, target_date, int(policy["lookbackDays"]))
      if policy.get("selection", {}).get("carryForwardBacklog", True)
      else set()
    )
    completed_candidates = load_completed_candidates(root)
    updates = group_updates(
      observations,
      target_date,
      policy,
      carry_forward_ids=carry_ids,
    )
    frozen_ids = {
      str(item.get("id", ""))
      for item in (frozen_top_k or [])
      if item.get("id")
    }
    selectable_updates = [
      item for item in updates
      if item["id"] not in completed_candidates or item["id"] in frozen_ids
    ]
    selected, backlog = select_top_k(
      selectable_updates,
      top_k,
      policy,
      frozen_top_k=frozen_top_k,
    )
    completed_ids = set(completed_candidates)
    selected = [
      {
        **item,
        "status": "completed",
        "completedAt": completed_candidates[item["id"]].get("completedAt"),
        "completionRecord": completed_candidates[item["id"]].get("completionRecord"),
        "changeType": completed_candidates[item["id"]].get("changeType"),
      }
      if item["id"] in completed_candidates
      else item
      for item in selected
    ]
    backlog = [item for item in backlog if item["id"] not in completed_ids]
    today_observations = [item for item in observations if item["date"] == target_date]
    input_payload = {
      "date": target_date,
      "topK": top_k,
      "policy": policy,
      "systemVersion": system_version(root),
      "observations": observations,
      "completed": [
        {
          "candidateId": item["candidateId"],
          "completedAt": item.get("completedAt"),
          "changeType": item.get("changeType"),
        }
        for item in sorted(
          completed_candidates.values(),
          key=lambda value: str(value.get("candidateId", "")),
        )
      ],
      "reselect": reselect,
    }
    input_hash = canonical_hash(input_payload)
    if state_path.exists() and report_path.exists():
      if existing.get("inputHash") == input_hash:
        return {
          **existing,
          "reused": True,
          "statePath": str(state_path.relative_to(root)),
          "reportPath": str(report_path.relative_to(root)),
        }

    state = {
      "schemaVersion": 1,
      "date": target_date,
      "systemVersion": system_version(root),
      "policyVersion": policy.get("schemaVersion", 1),
      "topKLimit": top_k,
      "topKLocked": freeze_daily_top_k,
      "selectionMode": "explicit-reselect" if reselect else (
        "frozen" if frozen_top_k is not None else "ranked"
      ),
      "inputHash": input_hash,
      "generatedAt": now_iso(),
      "topK": selected,
      "backlog": backlog,
      "summary": {
        "todayObservationCount": len(today_observations),
        "lookbackObservationCount": len(observations),
        "deduplicatedUpdateCount": len(updates),
        "eligibleCandidateCount": sum(1 for item in updates if item["eligible"]),
        "selectedTopKCount": len(selected),
        "backlogCount": len(backlog),
        "completedTopKCount": sum(
          1 for item in selected if item.get("status") == "completed"
        ),
      },
      "automation": {
        "formalFilesModified": False,
        "versionBumped": False,
      },
    }
    atomic_write_json(state_path, state)
    atomic_write_text(report_path, build_report(state))
    return {
      **state,
      "reused": False,
      "statePath": str(state_path.relative_to(root)),
      "reportPath": str(report_path.relative_to(root)),
    }
