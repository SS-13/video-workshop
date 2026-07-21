"""Project sanitized Daily Engineering Loop TopK items to GitHub Issues."""

from __future__ import annotations

from datetime import date as date_type, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import json
import re
import subprocess
import time


MANAGED_START = "<!-- video-workshop-managed:start -->"
MANAGED_END = "<!-- video-workshop-managed:end -->"
METADATA_PATTERN = re.compile(
  r"<!-- video-workshop-topk\s+(\{.*?\})\s+-->",
  re.DOTALL,
)
CLOSING_PATTERN = re.compile(
  r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b",
  re.IGNORECASE,
)
TOPK_FIX_MARKER = "<!-- video-workshop-topk-fix -->"
UNCHECKED_CANARY_PATTERN = re.compile(
  r"(?im)^\s*-\s*\[\s\]\s+.*\bcanary\b.*$"
)
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MANAGED_LABEL_PREFIXES = ("priority:", "type:", "status:")
PRIVATE_PATTERNS = [
  re.compile(r"/(?:Users|home)/", re.IGNORECASE),
  re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
  re.compile(r"file://", re.IGNORECASE),
  re.compile(r"\b(?:authorization|cookie|password|secret|token)\s*[:=]", re.IGNORECASE),
  re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
]

LABEL_DEFINITIONS = {
  "topk": {
    "color": "5319E7",
    "description": "Selected by the Daily Engineering Loop TopK",
  },
  "type:bug": {
    "color": "D73A4A",
    "description": "Existing behavior is defective or regressed",
  },
  "type:feature": {
    "color": "0E8A16",
    "description": "Backward-compatible capability or integration",
  },
  "type:other": {
    "color": "6E7781",
    "description": "Policy, maintenance, or major evolution work",
  },
  "priority:P0": {
    "color": "B60205",
    "description": "Highest effective priority",
  },
  "priority:P1": {
    "color": "D93F0B",
    "description": "High effective priority",
  },
  "priority:P2": {
    "color": "FBCA04",
    "description": "Normal effective priority",
  },
  "priority:P3": {
    "color": "0E8A16",
    "description": "Low effective priority",
  },
  "status:topk": {
    "color": "1D76DB",
    "description": "Selected and awaiting verified completion",
  },
  "status:verified": {
    "color": "0E8A16",
    "description": "Local completion and verification evidence are recorded",
  },
  "status:backlog": {
    "color": "6E7781",
    "description": "Previously selected work currently outside the active TopK",
  },
}


class GitHubIssueSyncError(Exception):
  """Raised when the public GitHub Issue projection cannot be completed."""


def load_json(path: Path) -> Dict[str, Any]:
  return json.loads(path.read_text(encoding="utf-8"))


def validate_date(value: str) -> str:
  try:
    date_type.fromisoformat(value)
  except ValueError as error:
    raise GitHubIssueSyncError(f"Invalid date: {value}") from error
  return value


def workspace_github_config(root: Path) -> Dict[str, Any]:
  path = root / "00_state" / "workspace.json"
  if not path.is_file():
    return {}
  payload = load_json(path)
  return dict(payload.get("integrations", {}).get("githubIssues", {}))


def parse_repository_url(value: str) -> str:
  raw = value.strip()
  patterns = [
    re.compile(r"^https?://github\.com/([^/]+/[^/]+?)(?:\.git)?$"),
    re.compile(r"^git@github\.com:([^/]+/[^/]+?)(?:\.git)?$"),
    re.compile(r"^ssh://git@github\.com/([^/]+/[^/]+?)(?:\.git)?$"),
  ]
  for pattern in patterns:
    match = pattern.match(raw)
    if match:
      return match.group(1)
  if REPOSITORY_PATTERN.match(raw):
    return raw.removesuffix(".git")
  raise GitHubIssueSyncError(f"Could not resolve a GitHub repository from: {value}")


def discover_repository(root: Path) -> str:
  result = subprocess.run(
    ["git", "-C", str(root), "remote", "get-url", "origin"],
    check=False,
    capture_output=True,
    text=True,
  )
  if result.returncode != 0 or not result.stdout.strip():
    raise GitHubIssueSyncError("GitHub repository is not configured; pass --repo OWNER/REPO.")
  return parse_repository_url(result.stdout.strip())


def resolve_repository(root: Path, explicit: Optional[str]) -> str:
  configured = str(workspace_github_config(root).get("repository", "")).strip()
  repository = explicit or configured
  if repository:
    repository = parse_repository_url(repository)
  else:
    repository = discover_repository(root)
  if not REPOSITORY_PATTERN.match(repository):
    raise GitHubIssueSyncError(f"Invalid GitHub repository: {repository}")
  return repository


def priority_rank(priority: str, policy: Dict[str, Any]) -> int:
  order = list(policy.get("priorityOrder", ["P0", "P1", "P2", "P3"]))
  try:
    return order.index(priority)
  except ValueError:
    return len(order)


def effective_priority(
  original_priority: str,
  first_seen_at: str,
  target_date: str,
  policy: Dict[str, Any],
) -> Tuple[str, int, int]:
  aging = policy.get("selection", {}).get("priorityAging", {})
  if not aging.get("enabled", False):
    return original_priority, 0, 0
  try:
    first_date = datetime.fromisoformat(first_seen_at.replace("Z", "+00:00")).date()
  except ValueError:
    first_date = date_type.fromisoformat(target_date)
  age_days = max(0, (date_type.fromisoformat(target_date) - first_date).days)
  days_per_level = max(1, int(aging.get("daysPerLevel", 1)))
  raised_by = age_days // days_per_level
  order = list(policy.get("priorityOrder", ["P0", "P1", "P2", "P3"]))
  original_rank = priority_rank(original_priority, policy)
  maximum_rank = priority_rank(str(aging.get("maximumPriority", "P0")), policy)
  effective_rank = max(maximum_rank, original_rank - raised_by)
  if effective_rank >= len(order):
    return original_priority, age_days, 0
  return str(order[effective_rank]), age_days, max(0, original_rank - effective_rank)


def load_completed_candidates(root: Path) -> Dict[str, Dict[str, Any]]:
  completed: Dict[str, Dict[str, Any]] = {}
  completion_root = root / "00_state" / "evolution" / "completed"
  if not completion_root.is_dir():
    return completed
  for path in sorted(completion_root.glob("*.json")):
    try:
      payload = load_json(path)
    except (OSError, json.JSONDecodeError):
      continue
    for item in payload.get("completed", []):
      candidate_id = str(item.get("candidateId", "")).strip()
      if candidate_id and candidate_id not in completed:
        completed[candidate_id] = item
  return completed


def issue_type_for(candidate: Dict[str, Any], completion: Optional[Dict[str, Any]]) -> str:
  if completion:
    return {
      "bugfix": "bug",
      "feature": "feature",
      "major-evolution": "other",
    }.get(str(completion.get("changeType", "")), "other")
  category = str(candidate.get("category", "uncategorized"))
  if category == "bug":
    return "bug"
  if category in {"new-capability", "integration-request"}:
    return "feature"
  return "other"


def public_safety_reason(candidate: Dict[str, Any], public_scopes: Iterable[str]) -> str:
  scope = str(candidate.get("scope", ""))
  if scope not in set(public_scopes):
    return f"scope-not-public:{scope or 'missing'}"
  summary = str(candidate.get("summary", "")).strip()
  if not summary:
    return "empty-summary"
  if len(summary) > 500:
    return "summary-too-long"
  triage = candidate.get("triage", {})
  triage_values = triage.values() if isinstance(triage, dict) else []
  values = [summary, str(candidate.get("affectedComponent", "")), *[str(value) for value in triage_values]]
  for value in values:
    if any(pattern.search(value) for pattern in PRIVATE_PATTERNS):
      return "private-pattern"
  return ""


def parse_metadata(body: str) -> Optional[Dict[str, Any]]:
  match = METADATA_PATTERN.search(body or "")
  if not match:
    return None
  try:
    payload = json.loads(match.group(1))
  except json.JSONDecodeError:
    return None
  if not str(payload.get("candidateId", "")).startswith("CAND-"):
    return None
  return payload


def markdown_value(value: Any) -> str:
  return str(value).replace("|", "\\|").replace("\n", " ")


def build_managed_block(
  metadata: Dict[str, Any],
  priority: str,
  workflow_status: str,
  completion: Optional[Dict[str, Any]] = None,
) -> str:
  metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
  triage = metadata.get("triage", {}) if isinstance(metadata.get("triage", {}), dict) else {}
  occurrence_count = int(metadata.get("occurrenceCount", 1) or 1)
  eligibility_reasons = metadata.get("eligibilityReasons", [])

  def triage_value(key: str, fallback: str) -> str:
    value = str(triage.get(key, "")).strip()
    return markdown_value(value or fallback)

  reproduction_fallback = (
    f"同类 Observation 已记录 {occurrence_count} 次。"
    if occurrence_count > 1
    else "复现细节待在实现前补齐；原始运行记录保留在本地。"
  )
  priority_fallback = (
    ", ".join(str(value) for value in eligibility_reasons)
    or f"当前有效优先级为 {priority}。"
  )
  verified = workflow_status == "verified"
  checked = "x" if verified else " "
  process_action = str(completion.get("processAction", "none")) if completion else "pending"
  return "\n".join([
    MANAGED_START,
    f"<!-- video-workshop-topk {metadata_json} -->",
    "## Top-K Issue",
    "",
    str(metadata["summary"]),
    "",
    "| 字段 | 当前值 |",
    "| --- | --- |",
    f"| Candidate | `{markdown_value(metadata['candidateId'])}` |",
    f"| 首次进入 Top-K | `{markdown_value(metadata['selectedDate'])}` |",
    f"| 类型 | `{markdown_value(metadata['issueType'])}` |",
    f"| 当前优先级 | `{priority}` |",
    f"| 原始优先级 | `{markdown_value(metadata['originalPriority'])}` |",
    f"| 组件 | `{markdown_value(metadata['component'])}` |",
    f"| 公开投影 | `{'redacted' if metadata.get('redacted') else 'full'}` |",
    f"| 当前状态 | `{workflow_status}` |",
    "",
    "## 运行分诊",
    "",
    f"- **影响的流程步骤：** {triage_value('workflowStep', str(metadata.get('component', 'general')))}",
    f"- **复现条件 / 运行记录：** {triage_value('reproduction', reproduction_fallback)}",
    f"- **用户或产物损失：** {triage_value('userImpact', '待评估；未确认前不得夸大影响。')}",
    f"- **优先级理由：** {triage_value('priorityReason', priority_fallback)}",
    f"- **修复方案：** {triage_value('proposedFix', '由实现 PR 给出最小修复方案。')}",
    f"- **验证证据：** {triage_value('validationPlan', '测试、产物、真实运行或用户验收至少提供一项。')}",
    f"- **是否需要改流程或加门禁：** {triage_value('processGate', '完成时通过 processAction 显式判断。')}",
    f"- **完成后的流程回写：** `{process_action}`",
    "",
    "## 关闭门禁",
    "",
    f"- [{checked}] 实现完成并形成可核对产物",
    f"- [{checked}] 通过 `vp evolve complete` 登记验证证据",
    "- [ ] 实现 PR 使用 `Closes #<issue-number>` 关联本 Issue",
    "- [ ] 必需检查通过并合并到默认分支",
    "",
    "本 Issue 不由夜间同步器直接关闭。只有关联 PR 合并到默认分支后，GitHub 才会自动关闭。",
    MANAGED_END,
  ])


def replace_managed_block(body: str, managed_block: str) -> str:
  existing = body or ""
  start = existing.find(MANAGED_START)
  end = existing.find(MANAGED_END)
  if start >= 0 and end >= start:
    end += len(MANAGED_END)
    return existing[:start] + managed_block + existing[end:]
  if existing.strip():
    return managed_block + "\n\n" + existing
  return managed_block + "\n"


def issue_label_names(issue: Dict[str, Any]) -> List[str]:
  names = []
  for value in issue.get("labels", []):
    name = value.get("name", "") if isinstance(value, dict) else str(value)
    if name:
      names.append(name)
  return names


def is_managed_label(name: str) -> bool:
  return name == "topk" or name.startswith(MANAGED_LABEL_PREFIXES)


def merged_labels(existing: Iterable[str], issue_type: str, priority: str, workflow_status: str) -> List[str]:
  custom = [name for name in existing if not is_managed_label(name)]
  managed = [
    "topk",
    f"type:{issue_type}",
    f"priority:{priority}",
    f"status:{workflow_status}",
  ]
  return sorted(set([*custom, *managed]))


def metadata_from_candidate(candidate: Dict[str, Any], target_date: str, issue_type: str) -> Dict[str, Any]:
  return {
    "candidateId": str(candidate["id"]),
    "selectedDate": target_date,
    "originalPriority": str(candidate.get("originalPriority", candidate.get("priority", "P2"))),
    "firstSeenAt": str(candidate.get("firstSeenAt", f"{target_date}T00:00:00+00:00")),
    "issueType": issue_type,
    "summary": str(candidate.get("summary", "")).strip(),
    "component": str(candidate.get("affectedComponent", "general")),
    "category": str(candidate.get("category", "uncategorized")),
    "scope": str(candidate.get("scope", "system-core")),
    "redacted": bool(candidate.get("redacted", False)),
    "occurrenceCount": int(candidate.get("occurrenceCount", 1) or 1),
    "eligibilityReasons": list(candidate.get("eligibilityReasons", [])),
    "triage": dict(candidate.get("triage", {})) if isinstance(candidate.get("triage", {}), dict) else {},
  }


def redacted_candidate(candidate: Dict[str, Any], reason: str) -> Dict[str, Any]:
  candidate_id = str(candidate.get("id", "unknown"))
  return {
    **candidate,
    "summary": f"受限事项 {candidate_id}",
    "affectedComponent": "private-local",
    "scope": "redacted",
    "contentIds": [],
    "observationIds": [],
    "redacted": True,
    "redactionReason": reason,
    "triage": {
      "workflowStep": "细节保留在本地工作区。",
      "reproduction": "细节保留在本地工作区。",
      "userImpact": "细节保留在本地工作区。",
      "priorityReason": "公开投影仅保留动态优先级。",
      "proposedFix": "细节保留在本地工作区。",
      "validationPlan": "验证证据保留在本地工作区。",
      "processGate": "流程判断保留在本地工作区。",
    },
  }


def candidate_from_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
  return {
    "id": metadata.get("candidateId"),
    "summary": metadata.get("summary", ""),
    "originalPriority": metadata.get("originalPriority", "P2"),
    "priority": metadata.get("originalPriority", "P2"),
    "firstSeenAt": metadata.get("firstSeenAt", ""),
    "affectedComponent": metadata.get("component", "general"),
    "category": metadata.get("category", "uncategorized"),
    "scope": metadata.get("scope", "system-core"),
    "occurrenceCount": metadata.get("occurrenceCount", 1),
    "eligibilityReasons": metadata.get("eligibilityReasons", []),
    "triage": metadata.get("triage", {}),
  }


def historical_candidate(root: Path, candidate_id: str) -> Optional[Dict[str, Any]]:
  state_root = root / "00_state" / "evolution"
  if not state_root.is_dir():
    return None
  for path in sorted(state_root.glob("*.json"), reverse=True):
    try:
      state = load_json(path)
    except (OSError, json.JSONDecodeError):
      continue
    for candidate in [*state.get("topK", []), *state.get("backlog", [])]:
      if str(candidate.get("id", "")) == candidate_id:
        return candidate
  return None


def load_daily_candidate(root: Path, target_date: str, candidate_id: str) -> Dict[str, Any]:
  state_path = root / "00_state" / "evolution" / f"{validate_date(target_date)}.json"
  if not state_path.is_file():
    raise GitHubIssueSyncError(f"Daily Evolution state does not exist: {target_date}")
  state = load_json(state_path)
  for candidate in state.get("topK", []):
    if str(candidate.get("id", "")) == candidate_id:
      return candidate
  raise GitHubIssueSyncError(
    f"Candidate is not in the active Top-K for {target_date}: {candidate_id}"
  )


def recommended_change_type(candidate: Dict[str, Any]) -> str:
  category = str(candidate.get("category", ""))
  if category == "bug":
    return "bugfix"
  if category in {"new-capability", "integration-request"}:
    return "feature"
  return "major-evolution"


def build_issue_work_packet(
  root: Path,
  target_date: str,
  candidate_id: str,
  repository: Optional[str] = None,
  client: Optional["GitHubClient"] = None,
  offline: bool = False,
) -> Dict[str, Any]:
  candidate = load_daily_candidate(root.resolve(), target_date, candidate_id)
  packet: Dict[str, Any] = {
    "date": target_date,
    "candidateId": candidate_id,
    "summary": str(candidate.get("summary", "")).strip(),
    "priority": str(candidate.get("priority", candidate.get("originalPriority", "P2"))),
    "category": str(candidate.get("category", "uncategorized")),
    "affectedComponent": str(candidate.get("affectedComponent", "general")),
    "validationPlan": str(candidate.get("triage", {}).get("validationPlan", "")),
    "proposedFix": str(candidate.get("triage", {}).get("proposedFix", "")),
    "recommendedChangeType": recommended_change_type(candidate),
    "branchName": f"fix/topk-{candidate_id.lower()}",
    "issueNumber": None,
    "issueUrl": "",
  }
  if offline or client is None:
    if not offline:
      packet["githubStatus"] = "not-queried"
    else:
      packet["githubStatus"] = "offline"
  else:
    packet["githubStatus"] = "queried"
    for issue in client.list_managed_issues():
      metadata = parse_metadata(str(issue.get("body", "")))
      if metadata and str(metadata.get("candidateId", "")) == candidate_id:
        packet["issueNumber"] = issue.get("number")
        packet["issueUrl"] = str(issue.get("html_url", ""))
        break
    if packet["issueNumber"] is None:
      raise GitHubIssueSyncError(
        f"No GitHub Issue exists for {candidate_id}; run evolve issues sync first."
      )
  issue_reference = (
    f"Closes #{packet['issueNumber']}"
    if packet.get("issueNumber") is not None
    else "Closes #<issue-number>"
  )
  packet["prBody"] = "\n".join([
    TOPK_FIX_MARKER,
    "",
    "## Problem",
    "",
    packet["summary"],
    "",
    "## Verification",
    "",
    f"- Validation plan: {packet['validationPlan'] or 'Add regression evidence before completion.'}",
    "- Run `vp evolve complete` only after the evidence is available.",
    "",
    issue_reference,
  ])
  packet["completionCommand"] = " ".join([
    "python3 09_tools/vp.py evolve complete",
    candidate_id,
    f"--date {target_date}",
    f"--change-type {packet['recommendedChangeType']}",
    "--evidence path/to/verification-report.md",
    "--process-action test",
  ])
  return packet


class GitHubClient:
  def __init__(self, repository: str):
    self.repository = repository

  def _run(self, args: List[str], payload: Optional[Dict[str, Any]] = None) -> Any:
    command = ["gh", "api", *args]
    input_text = None
    if payload is not None:
      command.extend(["--input", "-"])
      input_text = json.dumps(payload, ensure_ascii=False)
    method = "GET"
    if "--method" in args:
      method_index = args.index("--method")
      if method_index + 1 < len(args):
        method = str(args[method_index + 1]).upper()
    attempts = 5 if method in {"GET", "PATCH", "PUT", "DELETE"} else 1
    result = None
    for attempt in range(attempts):
      result = subprocess.run(
        command,
        input=input_text,
        check=False,
        capture_output=True,
        text=True,
      )
      if result.returncode == 0:
        break
      detail = result.stderr.strip() or result.stdout.strip()
      transient = any(
        marker in detail.lower()
        for marker in (
          "http 502",
          "http 503",
          "http 504",
          "connection reset",
          "connection refused",
          "temporary failure",
          "timeout",
          "timed out",
        )
      )
      if not transient or attempt + 1 >= attempts:
        break
      time.sleep(min(2 ** attempt, 8))
    if result is None or result.returncode != 0:
      detail = (
        (result.stderr.strip() or result.stdout.strip())
        if result is not None
        else "unknown gh api error"
      )
      raise GitHubIssueSyncError(detail or "unknown gh api error")
    if not result.stdout.strip():
      return None
    return json.loads(result.stdout)

  def ensure_labels(self) -> None:
    existing = self._run([f"repos/{self.repository}/labels?per_page=100"])
    existing_names = {str(item.get("name", "")) for item in existing or []}
    for name, definition in LABEL_DEFINITIONS.items():
      if name in existing_names:
        continue
      self._run(
        ["--method", "POST", f"repos/{self.repository}/labels"],
        {"name": name, **definition},
      )

  def list_managed_issues(self) -> List[Dict[str, Any]]:
    pages = self._run([
      "--paginate",
      "--slurp",
      f"repos/{self.repository}/issues?state=all&labels=topk&per_page=100",
    ])
    if not pages:
      return []
    if isinstance(pages[0], list):
      return [item for page in pages for item in page if "pull_request" not in item]
    return [item for item in pages if "pull_request" not in item]

  def create_issue(self, title: str, body: str, labels: List[str]) -> Dict[str, Any]:
    return self._run(
      ["--method", "POST", f"repos/{self.repository}/issues"],
      {"title": title, "body": body, "labels": labels},
    )

  def update_issue(
    self,
    number: int,
    title: str,
    body: str,
    labels: List[str],
  ) -> Dict[str, Any]:
    return self._run(
      ["--method", "PATCH", f"repos/{self.repository}/issues/{number}"],
      {"title": title, "body": body, "labels": labels},
    )

  def get_issue(self, number: int) -> Dict[str, Any]:
    return self._run([f"repos/{self.repository}/issues/{number}"])

  def get_pull_request(self, number: int) -> Dict[str, Any]:
    return self._run([f"repos/{self.repository}/pulls/{number}"])

  def default_branch(self) -> str:
    repository = self._run([f"repos/{self.repository}"])
    return str(repository.get("default_branch", "main"))

  def get_pull_request_checks(self, number: int) -> Dict[str, Any]:
    """Read required PR checks without executing code from the PR branch."""
    result = subprocess.run(
      [
        "gh",
        "pr",
        "checks",
        str(number),
        "--repo",
        self.repository,
        "--required",
        "--json",
        "name,state,bucket",
      ],
      check=False,
      capture_output=True,
      text=True,
    )
    output = result.stdout.strip()
    try:
      checks = json.loads(output) if output else []
    except json.JSONDecodeError as error:
      raise GitHubIssueSyncError(
        f"Could not parse required PR checks for #{number}: {output or result.stderr.strip()}"
      ) from error
    if result.returncode != 0 and not checks:
      detail = result.stderr.strip() or output or "gh pr checks failed"
      raise GitHubIssueSyncError(detail)
    checks = list(checks or [])
    states = {str(item.get("state", "")).upper() for item in checks}
    success_states = {"SUCCESS", "NEUTRAL", "SKIPPED"}
    pending_states = {"PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED", "STARTUP_FAILURE"}
    if not checks:
      status = "no-checks"
    elif states <= success_states:
      status = "success"
    elif states & pending_states:
      status = "pending"
    else:
      status = "failure"
    return {
      "status": status,
      "checks": checks,
      "states": sorted(states),
    }

  def merge_pull_request(self, number: int, auto: bool = False) -> Dict[str, Any]:
    command = ["gh", "pr", "merge", str(number), "--repo", self.repository, "--squash"]
    if auto:
      command.append("--auto")
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
      detail = result.stderr.strip() or result.stdout.strip() or "gh pr merge failed"
      raise GitHubIssueSyncError(detail)
    return {
      "number": number,
      "auto": auto,
      "output": result.stdout.strip(),
    }


def expected_issue(
  metadata: Dict[str, Any],
  target_date: str,
  policy: Dict[str, Any],
  completion: Optional[Dict[str, Any]],
  existing: Optional[Dict[str, Any]] = None,
  active: bool = True,
) -> Dict[str, Any]:
  candidate = candidate_from_metadata(metadata)
  issue_type = issue_type_for(candidate, completion)
  metadata = {**metadata, "issueType": issue_type}
  priority, age_days, raised_by = effective_priority(
    str(metadata["originalPriority"]),
    str(metadata["firstSeenAt"]),
    target_date,
    policy,
  )
  verified = completion is not None
  workflow_status = "verified" if verified else ("topk" if active else "backlog")
  existing_labels = issue_label_names(existing or {})
  labels = merged_labels(existing_labels, issue_type, priority, workflow_status)
  title = str(metadata["summary"])[:240]
  managed = build_managed_block(metadata, priority, workflow_status, completion)
  body = replace_managed_block(str((existing or {}).get("body", "")), managed)
  return {
    "candidateId": metadata["candidateId"],
    "metadata": metadata,
    "title": title,
    "body": body,
    "labels": labels,
    "issueType": issue_type,
    "priority": priority,
    "originalPriority": metadata["originalPriority"],
    "ageDays": age_days,
    "priorityRaisedBy": raised_by,
    "verified": verified,
    "workflowStatus": workflow_status,
  }


def issue_changed(existing: Dict[str, Any], expected: Dict[str, Any]) -> bool:
  return any([
    str(existing.get("title", "")) != expected["title"],
    str(existing.get("body", "")) != expected["body"],
    sorted(issue_label_names(existing)) != sorted(expected["labels"]),
  ])


def sync_topk_issues(
  root: Path,
  target_date: str,
  repository: Optional[str] = None,
  dry_run: bool = False,
  if_enabled: bool = False,
  client: Optional[GitHubClient] = None,
) -> Dict[str, Any]:
  root = root.resolve()
  target_date = validate_date(target_date)
  config = workspace_github_config(root)
  if if_enabled and not bool(config.get("enabled", False)):
    return {
      "date": target_date,
      "enabled": False,
      "skipped": True,
      "reason": "github-issues-disabled",
      "created": [],
      "updated": [],
      "unchanged": [],
      "closed": [],
      "privacySkipped": [],
      "privacyRedacted": [],
    }

  repository = client.repository if client else resolve_repository(root, repository)
  state_path = root / "00_state" / "evolution" / f"{target_date}.json"
  if not state_path.is_file():
    raise GitHubIssueSyncError(f"Daily Evolution state does not exist: {target_date}")
  state = load_json(state_path)
  if not state.get("topKLocked", False) and state.get("selectionMode") != "rolling":
    raise GitHubIssueSyncError(f"Daily TopK is neither locked nor rolling: {target_date}")
  policy = load_json(root / "00_system" / "evolution-policy.json")
  public_scopes = policy.get("githubIssues", {}).get("publicScopes", ["system-core"])
  completions = load_completed_candidates(root)

  remote_issues = [] if dry_run and client is None else (client or GitHubClient(repository)).list_managed_issues()
  remote_by_candidate: Dict[str, Dict[str, Any]] = {}
  for issue in remote_issues:
    metadata = parse_metadata(str(issue.get("body", "")))
    if metadata:
      remote_by_candidate[str(metadata["candidateId"])] = issue

  candidates: Dict[str, Dict[str, Any]] = {}
  active_candidate_ids = {
    str(candidate.get("id", ""))
    for candidate in state.get("topK", [])
    if candidate.get("id")
  }
  privacy_skipped = []
  privacy_redacted = []
  state_candidates = [
    *state.get("topK", []),
    *[
      candidate
      for candidate in state.get("backlog", [])
      if candidate.get("eligible", True)
    ],
  ]
  for candidate in state_candidates:
    candidate_id = str(candidate.get("id", ""))
    if not candidate_id or candidate_id in candidates:
      continue
    reason = public_safety_reason(candidate, public_scopes)
    if reason:
      privacy_redacted.append({
        "candidateId": candidate_id,
        "reason": reason,
      })
      candidate = redacted_candidate(candidate, reason)
    completion = completions.get(candidate_id)
    issue_type = issue_type_for(candidate, completion)
    candidates[candidate_id] = metadata_from_candidate(candidate, target_date, issue_type)

  for candidate_id, issue in remote_by_candidate.items():
    metadata = parse_metadata(str(issue.get("body", "")))
    if metadata and candidate_id not in candidates:
      candidates[candidate_id] = metadata

  for candidate_id, completion in completions.items():
    if candidate_id in candidates:
      continue
    candidate = historical_candidate(root, candidate_id)
    if candidate is None:
      candidate = {
        "id": candidate_id,
        "summary": f"已验证工作项 {candidate_id}",
        "originalPriority": completion.get("priority", "P2"),
        "priority": completion.get("priority", "P2"),
        "firstSeenAt": completion.get("completedAt", f"{target_date}T00:00:00+00:00"),
        "affectedComponent": "private-local",
        "category": "uncategorized",
        "scope": "redacted",
        "redacted": True,
      }
    reason = public_safety_reason(candidate, public_scopes)
    if reason:
      privacy_redacted.append({"candidateId": candidate_id, "reason": reason})
      candidate = redacted_candidate(candidate, reason)
    issue_type = issue_type_for(candidate, completion)
    candidates[candidate_id] = metadata_from_candidate(candidate, target_date, issue_type)

  created = []
  updated = []
  unchanged = []
  closed = []
  actions = []
  active_client = None if dry_run else (client or GitHubClient(repository))
  if active_client:
    active_client.ensure_labels()

  for candidate_id, metadata in sorted(candidates.items()):
    existing = remote_by_candidate.get(candidate_id)
    completion = completions.get(candidate_id)
    expected = expected_issue(
      metadata,
      target_date,
      policy,
      completion,
      existing,
      active=candidate_id in active_candidate_ids,
    )
    summary = {
      "candidateId": candidate_id,
      "issueType": expected["issueType"],
      "priority": expected["priority"],
      "originalPriority": expected["originalPriority"],
      "ageDays": expected["ageDays"],
      "verified": expected["verified"],
      "workflowStatus": expected["workflowStatus"],
    }
    if existing and str(existing.get("state", "open")) == "closed":
      closed.append({**summary, "number": existing.get("number"), "url": existing.get("html_url")})
      continue
    if existing is None:
      actions.append({"action": "create", **summary})
      if active_client:
        issue = active_client.create_issue(expected["title"], expected["body"], expected["labels"])
        created.append({**summary, "number": issue.get("number"), "url": issue.get("html_url")})
      else:
        created.append(summary)
      continue
    if issue_changed(existing, expected):
      actions.append({"action": "update", "number": existing.get("number"), **summary})
      if active_client:
        issue = active_client.update_issue(
          int(existing["number"]),
          expected["title"],
          expected["body"],
          expected["labels"],
        )
        updated.append({**summary, "number": issue.get("number"), "url": issue.get("html_url")})
      else:
        updated.append({**summary, "number": existing.get("number")})
    else:
      unchanged.append({
        **summary,
        "number": existing.get("number"),
        "url": existing.get("html_url"),
      })

  return {
    "date": target_date,
    "enabled": True,
    "skipped": False,
    "repository": repository,
    "dryRun": dry_run,
    "created": created,
    "updated": updated,
    "unchanged": unchanged,
    "closed": closed,
    "privacySkipped": privacy_skipped,
    "privacyRedacted": privacy_redacted,
    "actions": actions,
    "closureStrategy": "verified-linked-pr-merge-to-default",
  }


def closing_issue_numbers(body: str) -> List[int]:
  return sorted({int(value) for value in CLOSING_PATTERN.findall(body or "")})


def check_pull_request_issue_gate(
  client: GitHubClient,
  pull_number: int,
  require_topk: bool = False,
) -> Dict[str, Any]:
  pull = client.get_pull_request(pull_number)
  default_branch = client.default_branch()
  body = str(pull.get("body", ""))
  issue_numbers = closing_issue_numbers(body)
  checked = []
  violations = []
  for issue_number in issue_numbers:
    issue = client.get_issue(issue_number)
    labels = issue_label_names(issue)
    if "topk" not in labels:
      continue
    checked.append({
      "number": issue_number,
      "url": issue.get("html_url"),
      "labels": labels,
    })
    if str(issue.get("state", "open")) != "open":
      violations.append(f"TopK issue #{issue_number} is already closed before this merge.")
    if "status:verified" not in labels:
      violations.append(
        f"TopK issue #{issue_number} is not verified; run vp evolve complete and sync issues first."
      )
  if require_topk and not checked:
    violations.append(
      "TopK repair PRs must contain Closes #N for at least one managed TopK Issue."
    )
  if checked and str(pull.get("base", {}).get("ref", "")) != default_branch:
    violations.append(
      f"TopK issues may close only through the default branch: {default_branch}."
    )
  return {
    "valid": not violations,
    "repository": client.repository,
    "pullNumber": pull_number,
    "baseBranch": str(pull.get("base", {}).get("ref", "")),
    "defaultBranch": default_branch,
    "closingIssueNumbers": issue_numbers,
    "checkedTopKIssues": checked,
    "requireTopK": require_topk,
    "isTopKFix": bool(checked) or TOPK_FIX_MARKER in body,
    "draft": bool(pull.get("draft", False)),
    "violations": violations,
  }


def check_pull_request_merge_gate(
  client: GitHubClient,
  pull_number: int,
) -> Dict[str, Any]:
  pull = client.get_pull_request(pull_number)
  issue_gate = check_pull_request_issue_gate(client, pull_number, require_topk=True)
  violations = list(issue_gate["violations"])
  default_branch = issue_gate["defaultBranch"]
  base_branch = str(pull.get("base", {}).get("ref", ""))
  if base_branch != default_branch and not any(
    "default branch" in violation for violation in violations
  ):
    violations.append(f"TopK repair PRs must target the default branch: {default_branch}.")
  if bool(pull.get("draft", False)):
    violations.append("TopK repair PR must be marked Ready for review before merge.")
  unchecked_canary = UNCHECKED_CANARY_PATTERN.findall(str(pull.get("body", "")))
  if unchecked_canary:
    violations.append(
      "PR still has an unchecked Canary gate; record real Canary evidence before merge."
    )
  checks = client.get_pull_request_checks(pull_number)
  if checks.get("status") != "success":
    violations.append(
      f"Required PR checks are not green: {checks.get('status', 'unknown')}."
    )
  return {
    **issue_gate,
    "valid": not violations,
    "checks": checks,
    "uncheckedCanaryGates": unchecked_canary,
    "violations": violations,
  }
