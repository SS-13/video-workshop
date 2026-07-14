#!/usr/bin/env python3
"""Video production system CLI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import argparse
import json
import sys


INSTALL_ROOT = Path(__file__).resolve().parents[1]
EVOLUTION_SCRIPT_DIR = INSTALL_ROOT / ".codex" / "skills" / "video-production-evolution" / "scripts"
sys.path.insert(0, str(EVOLUTION_SCRIPT_DIR))

from video_production_core.project_root import RootDiscoveryError, resolve_project_root  # noqa: E402
from video_production_core.contracts import validate_contract_examples  # noqa: E402
from video_production_core.registry import (  # noqa: E402
  get_content_types,
  get_profile,
  get_release_status,
  get_system_info,
  validate_control_plane,
)
from video_production_core.routing import RouteResolutionError, resolve_route  # noqa: E402
from video_production_core.transcript_quality import compare_transcripts  # noqa: E402
from video_production_core.shadow_validation import (  # noqa: E402
  markdown_report,
  validate_historical_shadow,
  validate_shadow,
)
from video_production_core.release_transition import (  # noqa: E402
  ReleaseTransitionError,
  activate_release,
  activation_readiness,
  rollback_release,
)
from video_production_core.state_reconcile import reconcile_state  # noqa: E402
from video_production_core.workspace_bootstrap import (  # noqa: E402
  build_ai_context,
  doctor_workspace,
  initialize_workspace,
)
from video_production_core.canary_validation import validate_real_canary  # noqa: E402
from video_production_core.canary_adoption import adopt_canary_run  # noqa: E402
from video_production_core.active_finalization import finalize_active_run  # noqa: E402
from video_production_core.run_store import (  # noqa: E402
  RunStateError,
  advance_run,
  get_run,
  list_runs,
  register_artifact,
  start_run,
  validate_run,
)
from evolution_loop import (  # noqa: E402
  EvolutionDeferred,
  EvolutionError,
  LeaseBusy,
  ObservationParseError,
  VALID_CATEGORIES,
  VALID_PRIORITIES,
  VALID_SCOPES,
  record_observation,
  run_evolution,
)


def today() -> str:
  return datetime.now().astimezone().date().isoformat()


def json_envelope(root: Path, data: Any) -> Dict[str, Any]:
  package_path = root / "package.json"
  if not package_path.exists():
    package_path = INSTALL_ROOT / "package.json"
  package = json.loads(package_path.read_text(encoding="utf-8"))
  return {
    "apiVersion": "video-production.v1",
    "ok": True,
    "data": data,
    "meta": {
      "systemVersion": package.get("version", "unknown"),
      "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
    },
  }


def error_envelope(code: str, message: str, details: Any = None) -> Dict[str, Any]:
  return {
    "apiVersion": "video-production.v1",
    "ok": False,
    "error": {
      "code": code,
      "message": message,
      "details": details,
    },
  }


def print_json(payload: Dict[str, Any]) -> None:
  print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def add_common_json_flag(parser: argparse.ArgumentParser) -> None:
  parser.add_argument("--json", action="store_true", help="Print a stable JSON envelope")


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(prog="vp", description="Video production system CLI")
  parser.add_argument("--root", help="Workspace root; defaults to upward discovery or VIDEO_PRODUCTION_ROOT")
  subparsers = parser.add_subparsers(dest="command", required=True)

  init = subparsers.add_parser("init", help="Initialize the ignored local workspace")
  add_common_json_flag(init)

  doctor = subparsers.add_parser("doctor", help="Check clone, workspace, Loop, and render readiness")
  add_common_json_flag(doctor)

  context = subparsers.add_parser("context", help="Show the ordered AI read list and local corpus")
  add_common_json_flag(context)

  observe = subparsers.add_parser("observe", help="Record one workflow observation")
  observe.add_argument("--date", default=today())
  observe.add_argument("--summary", required=True)
  observe.add_argument("--category", choices=sorted(VALID_CATEGORIES), default="uncategorized")
  observe.add_argument("--priority", choices=VALID_PRIORITIES, default="P2")
  observe.add_argument("--scope", choices=sorted(VALID_SCOPES), default="single-run")
  observe.add_argument("--component", default="general")
  observe.add_argument("--source", default="user-correction")
  observe.add_argument("--actor", default="cli")
  observe.add_argument("--content-id", default="")
  observe.add_argument("--evidence", default="", help="Short evidence note")
  observe.add_argument("--promote", action="store_true", help="User explicitly requested permanent promotion")
  observe.add_argument("--deterministic", action="store_true", help="Finding came from a deterministic validator")
  add_common_json_flag(observe)

  evolve = subparsers.add_parser("evolve", help="Run the P0 Daily Engineering Loop")
  evolve.add_argument("--date", default=today())
  evolve.add_argument("--top-k", type=int, default=None)
  evolve.add_argument("--actor", default="system-steward-agent")
  evolve.add_argument(
    "--reselect",
    action="store_true",
    help="Explicitly recalculate today's TopK instead of preserving the first selection",
  )
  add_common_json_flag(evolve)

  system = subparsers.add_parser("system", help="Inspect the generic control plane")
  system_subparsers = system.add_subparsers(dest="system_action", required=True)
  system_info = system_subparsers.add_parser("info", help="Show system and release identity")
  add_common_json_flag(system_info)
  system_reconcile = system_subparsers.add_parser(
    "reconcile",
    help="Reconcile Day and content ledgers from production statistics",
  )
  system_reconcile.add_argument("--apply", action="store_true")
  add_common_json_flag(system_reconcile)

  registry = subparsers.add_parser("registry", help="Validate control-plane registries")
  registry_subparsers = registry.add_subparsers(dest="registry_action", required=True)
  registry_validate = registry_subparsers.add_parser("validate", help="Validate all registry references")
  add_common_json_flag(registry_validate)

  content_type = subparsers.add_parser("content-type", help="Inspect registered content types")
  content_subparsers = content_type.add_subparsers(dest="content_action", required=True)
  content_list = content_subparsers.add_parser("list", help="List content types")
  content_list.add_argument("--enabled-only", action="store_true")
  add_common_json_flag(content_list)

  profile = subparsers.add_parser("profile", help="Inspect workflow profiles")
  profile_subparsers = profile.add_subparsers(dest="profile_action", required=True)
  profile_get = profile_subparsers.add_parser("get", help="Get one workflow profile")
  profile_get.add_argument("profile_id")
  add_common_json_flag(profile_get)

  release = subparsers.add_parser("release", help="Inspect release channels")
  release_subparsers = release.add_subparsers(dest="release_action", required=True)
  release_status = release_subparsers.add_parser("status", help="Show stable and candidate releases")
  add_common_json_flag(release_status)
  transcript_check = release_subparsers.add_parser(
    "transcript-check",
    help="Compare a candidate SRT with a reviewed golden SRT",
  )
  transcript_check.add_argument("--actual", required=True)
  transcript_check.add_argument("--expected", required=True)
  transcript_check.add_argument("--min-accuracy", type=float, default=0.98)
  add_common_json_flag(transcript_check)
  shadow_check = release_subparsers.add_parser(
    "shadow-check",
    help="Validate an isolated 3.0 short-video Shadow Regression",
  )
  shadow_check.add_argument("--workspace", required=True)
  shadow_check.add_argument("--date", required=True)
  shadow_check.add_argument("--started-at", required=True)
  shadow_check.add_argument("--visual-check", choices=["pass", "pending", "fail"], default="pending")
  shadow_check.add_argument("--min-transcript-accuracy", type=float, default=0.98)
  shadow_check.add_argument("--report-json")
  shadow_check.add_argument("--report-markdown")
  add_common_json_flag(shadow_check)
  historical_shadow_check = release_subparsers.add_parser(
    "historical-shadow-check",
    help="Validate a full historical v2/legacy Shadow Regression",
  )
  historical_shadow_check.add_argument("--workspace", required=True)
  historical_shadow_check.add_argument("--date", required=True)
  historical_shadow_check.add_argument("--started-at", required=True)
  historical_shadow_check.add_argument(
    "--visual-check",
    choices=["pass", "pending", "fail"],
    default="pending",
  )
  historical_shadow_check.add_argument("--report-json")
  historical_shadow_check.add_argument("--report-markdown")
  add_common_json_flag(historical_shadow_check)
  release_readiness = release_subparsers.add_parser(
    "readiness",
    help="Show whether the candidate can be manually activated",
  )
  add_common_json_flag(release_readiness)
  release_canary_check = release_subparsers.add_parser(
    "canary-check",
    help="Validate one real Canary run without activating the candidate",
  )
  release_canary_check.add_argument("--run-id", required=True)
  release_canary_check.add_argument("--record-pass", action="store_true")
  release_canary_check.add_argument("--actor", default="system-steward-agent")
  add_common_json_flag(release_canary_check)
  release_canary_adopt = release_subparsers.add_parser(
    "canary-adopt",
    help="Adopt one completed Stable production into a tracked Canary run",
  )
  release_canary_adopt.add_argument("--date", required=True)
  release_canary_adopt.add_argument("--publish-package")
  release_canary_adopt.add_argument("--content-type", default="video-diary")
  release_canary_adopt.add_argument("--script")
  release_canary_adopt.add_argument("--recording")
  release_canary_adopt.add_argument("--actor", default="system-steward-agent")
  add_common_json_flag(release_canary_adopt)
  release_activate = release_subparsers.add_parser(
    "activate",
    help="Manually activate the candidate after all gates pass",
  )
  release_activate.add_argument("--confirm", action="store_true")
  release_activate.add_argument("--dry-run", action="store_true")
  release_activate.add_argument("--actor", default="cli")
  add_common_json_flag(release_activate)
  release_rollback = release_subparsers.add_parser(
    "rollback",
    help="Restore the stable release pointer and package version",
  )
  release_rollback.add_argument("--confirm", action="store_true")
  release_rollback.add_argument("--dry-run", action="store_true")
  release_rollback.add_argument("--actor", default="cli")
  add_common_json_flag(release_rollback)

  route = subparsers.add_parser("route", help="Resolve profile actions without executing them")
  route_subparsers = route.add_subparsers(dest="route_action", required=True)
  route_resolve = route_subparsers.add_parser("resolve", help="Resolve one content action")
  route_resolve.add_argument("--content-type", required=True)
  route_resolve.add_argument("--action", required=True)
  add_common_json_flag(route_resolve)

  contract = subparsers.add_parser("contract", help="Validate public control-plane contracts")
  contract_subparsers = contract.add_subparsers(dest="contract_action", required=True)
  contract_validate = contract_subparsers.add_parser(
    "validate",
    help="Validate bundled contract examples",
  )
  add_common_json_flag(contract_validate)

  run = subparsers.add_parser("run", help="Manage persistent production run state")
  run_subparsers = run.add_subparsers(dest="run_action", required=True)
  run_start = run_subparsers.add_parser("start", help="Create or reuse one production run")
  run_start.add_argument("--date", required=True)
  run_start.add_argument("--content-type", default="video-diary")
  run_start.add_argument("--id")
  run_start.add_argument("--title", default="")
  run_start.add_argument("--channel", choices=["stable", "candidate", "canary"], default="stable")
  run_start.add_argument("--actor", default="cli")
  add_common_json_flag(run_start)

  run_status = run_subparsers.add_parser("status", help="Show one production run")
  run_status.add_argument("--id", required=True)
  add_common_json_flag(run_status)

  run_list = run_subparsers.add_parser("list", help="List production runs")
  run_list.add_argument("--limit", type=int, default=20)
  add_common_json_flag(run_list)

  run_advance = run_subparsers.add_parser("advance", help="Advance one run stage")
  run_advance.add_argument("--id", required=True)
  run_advance.add_argument("--stage", required=True)
  run_advance.add_argument(
    "--step-status",
    choices=["pending", "running", "waiting_user", "succeeded", "failed", "skipped"],
    default="succeeded",
  )
  run_advance.add_argument("--actor", default="cli")
  run_advance.add_argument("--note", default="")
  run_advance.add_argument("--publish-ready", choices=["true", "false"])
  add_common_json_flag(run_advance)

  run_artifact = run_subparsers.add_parser("artifact", help="Register or replace one run artifact")
  run_artifact.add_argument("--id", required=True)
  run_artifact.add_argument("--artifact-id", required=True)
  run_artifact.add_argument("--step", required=True)
  run_artifact.add_argument(
    "--type",
    required=True,
    choices=["text", "subtitle", "image", "video", "json", "report"],
  )
  run_artifact.add_argument("--label", required=True)
  run_artifact.add_argument("--path", required=True)
  run_artifact.add_argument("--mime-type")
  run_artifact.add_argument("--duration-seconds", type=float)
  run_artifact.add_argument("--actor", default="cli")
  add_common_json_flag(run_artifact)

  run_validate = run_subparsers.add_parser("validate", help="Validate one run and its artifacts")
  run_validate.add_argument("--id", required=True)
  add_common_json_flag(run_validate)
  run_finalize_active = run_subparsers.add_parser(
    "finalize-active",
    help="Finalize a publish-ready package into Run State when 3.x is Active",
  )
  run_finalize_active.add_argument("--date", required=True)
  run_finalize_active.add_argument("--publish-package")
  run_finalize_active.add_argument("--content-type", default="video-diary")
  run_finalize_active.add_argument("--script")
  run_finalize_active.add_argument("--recording")
  run_finalize_active.add_argument("--actor", default="video-agent")
  add_common_json_flag(run_finalize_active)

  return parser


def handle_observe(root: Path, args: argparse.Namespace) -> int:
  evidence = {"note": args.evidence} if args.evidence else {}
  observation = record_observation(root, {
    "date": args.date,
    "summary": args.summary,
    "category": args.category,
    "priority": args.priority,
    "scope": args.scope,
    "component": args.component,
    "source": args.source,
    "actor": args.actor,
    "contentId": args.content_id,
    "evidence": evidence,
    "promoteRequested": args.promote,
    "deterministicFinding": args.deterministic,
  })
  if args.json:
    print_json(json_envelope(root, observation))
  else:
    print(f"observation_id={observation['id']}")
    print(f"date={observation['date']}")
    print(f"category={observation['category']}")
    print(f"priority={observation['priority']}")
    print("status=observed")
  return 0


def handle_init(root: Path, args: argparse.Namespace) -> int:
  data = initialize_workspace(root)
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"root={data['root']}")
    print(f"system_version={data['systemVersion']}")
    print(f"default_content_type={data['defaultContentType']}")
    print(f"created_directories={len(data['createdDirectories'])}")
    print(f"created_files={len(data['createdFiles'])}")
    print(f"changed={str(data['changed']).lower()}")
    print(f"next={data['nextCommand']}")
  return 0


def handle_doctor(root: Path, args: argparse.Namespace) -> int:
  data = doctor_workspace(root)
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"valid={str(data['valid']).lower()}")
    print(f"ready_for_content={str(data['readyForContent']).lower()}")
    print(f"ready_for_render={str(data['readyForRender']).lower()}")
    print(f"loop_ready={str(data['loopReady']).lower()}")
    for check in data["checks"]:
      print(f"{check['status']}\t{check['name']}\t{check['detail']}")
  return 0 if data["valid"] else 2


def handle_context(root: Path, args: argparse.Namespace) -> int:
  data = build_ai_context(root)
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"root={data['root']}")
    print(f"personalization_status={data['personalization']['status']}")
    print(f"source_file_count={data['personalization']['sourceFileCount']}")
    for index, value in enumerate(data["publicReadOrder"], 1):
      print(f"read_{index}={value}")
    for value in data["localOverrides"]:
      print(f"local_override={value}")
    for value in data["personalization"]["sourceFiles"]:
      print(f"source={value}")
  return 0


def handle_evolve(root: Path, args: argparse.Namespace) -> int:
  result = run_evolution(
    root,
    args.date,
    top_k_override=args.top_k,
    actor=args.actor,
    reselect=args.reselect,
  )
  if args.json:
    print_json(json_envelope(root, result))
  else:
    print(f"date={result['date']}")
    print(f"observation_count={result['summary']['todayObservationCount']}")
    print(f"eligible_candidate_count={result['summary']['eligibleCandidateCount']}")
    print(f"top_k_limit={result['topKLimit']}")
    print(f"selected_top_k={len(result['topK'])}")
    print(f"selection_mode={result['selectionMode']}")
    print(f"backlog_count={result['summary']['backlogCount']}")
    print(f"report={result['reportPath']}")
    print(f"state={result['statePath']}")
    print(f"reused={str(result['reused']).lower()}")
  return 0


def handle_system(root: Path, args: argparse.Namespace) -> int:
  data = get_system_info(root)
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"name={data['name']}")
    print(f"package_version={data['packageVersion']}")
    print(f"active_release={data['activeRelease']}")
    print(f"candidate_release={data.get('candidateRelease') or ''}")
    print(f"default_content_type={data['defaultContentType']}")
    print(f"root={data['root']}")
  return 0


def handle_system_reconcile(root: Path, args: argparse.Namespace) -> int:
  data = reconcile_state(root, apply=args.apply)
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"valid={str(data['valid']).lower()}")
    print(f"applied={str(data['applied']).lower()}")
    print(f"latest_content_id={data.get('latestContentId', '')}")
    print(f"latest_day={data.get('latestDay', '')}")
    print(f"counter_changed={str(data.get('counterChanged', False)).lower()}")
    print(f"ledger_added={len(data.get('ledgerAdded', []))}")
    print(f"ledger_updated={len(data.get('ledgerUpdated', []))}")
  return 0 if data["valid"] else 2


def handle_registry(root: Path, args: argparse.Namespace) -> int:
  data = validate_control_plane(root)
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"valid={str(data['valid']).lower()}")
    for key, value in data.get("counts", {}).items():
      print(f"{key}={value}")
    print(f"errors={len(data['errors'])}")
    print(f"warnings={len(data['warnings'])}")
    for error in data["errors"]:
      print(f"error={error['code']}:{error['message']}")
  return 0 if data["valid"] else 2


def handle_content_type(root: Path, args: argparse.Namespace) -> int:
  data = get_content_types(root, enabled_only=args.enabled_only)
  if args.json:
    print_json(json_envelope(root, data))
  else:
    for item in data:
      print(
        f"{item['id']}\tdefault={str(item.get('default', False)).lower()}\t"
        f"enabled={str(item.get('enabled', False)).lower()}\tprofile={item['profile']}"
      )
  return 0


def handle_profile(root: Path, args: argparse.Namespace) -> int:
  data = get_profile(root, args.profile_id)
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"id={data['id']}")
    print(f"content_type={data['contentType']}")
    print(f"render={data['commands']['render']}")
    print(f"fallback_render={data['commands']['fallbackRender']}")
  return 0


def handle_release(root: Path, args: argparse.Namespace) -> int:
  data = get_release_status(root)
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"active_release={data['activeRelease']}")
    print(f"stable_release={data['stableRelease']}")
    print(f"candidate_release={data['candidateRelease'] or ''}")
    print(f"target_date={data['targetDate']}")
    manifest = data.get("candidateManifest") or {}
    print(f"candidate_status={manifest.get('status', '')}")
  return 0


def handle_transcript_check(root: Path, args: argparse.Namespace) -> int:
  actual = Path(args.actual)
  expected = Path(args.expected)
  if not actual.is_absolute():
    actual = root / actual
  if not expected.is_absolute():
    expected = root / expected
  data = compare_transcripts(actual, expected, args.min_accuracy)
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"passed={str(data['passed']).lower()}")
    print(f"accuracy={data['accuracy']:.6f}")
    print(f"character_error_rate={data['characterErrorRate']:.6f}")
    print(f"edit_distance={data['editDistance']}")
    print(f"actual={data['actual']}")
    print(f"expected={data['expected']}")
  return 0 if data["passed"] else 2


def handle_shadow_check(root: Path, args: argparse.Namespace) -> int:
  workspace = Path(args.workspace)
  if not workspace.is_absolute():
    workspace = root / workspace
  data = validate_shadow(
    root=root,
    workspace=workspace,
    date=args.date,
    started_at=args.started_at,
    visual_check=args.visual_check,
    min_transcript_accuracy=args.min_transcript_accuracy,
  )
  if args.report_json:
    report_json = Path(args.report_json)
    if not report_json.is_absolute():
      report_json = root / report_json
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  if args.report_markdown:
    report_markdown = Path(args.report_markdown)
    if not report_markdown.is_absolute():
      report_markdown = root / report_markdown
    report_markdown.parent.mkdir(parents=True, exist_ok=True)
    report_markdown.write_text(markdown_report(data), encoding="utf-8")
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"valid={str(data['valid']).lower()}")
    for check in data["checks"]:
      print(f"gate={check['name']}\tstatus={check['status']}")
  return 0 if data["valid"] else 2


def write_release_reports(root: Path, args: argparse.Namespace, data: Dict[str, Any]) -> None:
  if args.report_json:
    report_json = Path(args.report_json)
    if not report_json.is_absolute():
      report_json = root / report_json
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  if args.report_markdown:
    report_markdown = Path(args.report_markdown)
    if not report_markdown.is_absolute():
      report_markdown = root / report_markdown
    report_markdown.parent.mkdir(parents=True, exist_ok=True)
    report_markdown.write_text(markdown_report(data), encoding="utf-8")


def handle_historical_shadow_check(root: Path, args: argparse.Namespace) -> int:
  workspace = Path(args.workspace)
  if not workspace.is_absolute():
    workspace = root / workspace
  data = validate_historical_shadow(
    root=root,
    workspace=workspace,
    date=args.date,
    started_at=args.started_at,
    visual_check=args.visual_check,
  )
  write_release_reports(root, args, data)
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"valid={str(data['valid']).lower()}")
    for check in data["checks"]:
      print(f"gate={check['name']}\tstatus={check['status']}")
  return 0 if data["valid"] else 2


def print_release_transition(data: Dict[str, Any], as_json: bool, root: Path) -> None:
  if as_json:
    print_json(json_envelope(root, data))
    return
  for key in [
    "action",
    "ready",
    "changed",
    "dryRun",
    "activeRelease",
    "candidateRelease",
    "stableRelease",
    "targetRelease",
    "packageVersion",
    "manifestStatus",
  ]:
    if key in data:
      value = data[key]
      if isinstance(value, bool):
        value = str(value).lower()
      print(f"{key}={value}")
  print(f"blockingGates={json.dumps(data.get('blockingGates', {}), ensure_ascii=False, sort_keys=True)}")
  print(f"errors={json.dumps(data.get('errors', []), ensure_ascii=False)}")


def handle_release_readiness(root: Path, args: argparse.Namespace) -> int:
  data = activation_readiness(root)
  print_release_transition(data, args.json, root)
  return 0 if data["ready"] else 2


def handle_release_canary_check(root: Path, args: argparse.Namespace) -> int:
  data = validate_real_canary(
    root,
    args.run_id,
    record_pass=args.record_pass,
    actor=args.actor,
  )
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"valid={str(data['valid']).lower()}")
    print(f"recorded={str(data['recorded']).lower()}")
    print(f"run_id={data['runId']}")
    for check in data["checks"]:
      print(f"gate={check['name']}\tstatus={check['status']}")
  return 0 if data["valid"] else 2


def handle_release_canary_adopt(root: Path, args: argparse.Namespace) -> int:
  data = adopt_canary_run(
    root,
    date=args.date,
    publish_package_path=args.publish_package,
    content_type=args.content_type,
    script_path=args.script,
    recording_path=args.recording,
    actor=args.actor,
  )
  validation = data["validation"]
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"run_id={data['run']['id']}")
    print(f"reused={str(data['reused']).lower()}")
    print(f"adoption_mode={data['adoptionMode']}")
    print(f"canary_package={data['canaryPackage']}")
    print(f"valid={str(validation['valid']).lower()}")
    print("next=python3 09_tools/vp.py release canary-check "
          f"--run-id {data['run']['id']} --record-pass")
  return 0 if validation["valid"] else 2


def handle_release_activate(root: Path, args: argparse.Namespace) -> int:
  data = activate_release(root, confirm=args.confirm, dry_run=args.dry_run, actor=args.actor)
  print_release_transition(data, args.json, root)
  return 0 if data.get("ready", False) else 2


def handle_release_rollback(root: Path, args: argparse.Namespace) -> int:
  data = rollback_release(root, confirm=args.confirm, dry_run=args.dry_run, actor=args.actor)
  print_release_transition(data, args.json, root)
  return 0


def handle_route(root: Path, args: argparse.Namespace) -> int:
  data = resolve_route(root, args.content_type, args.action)
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"content_type={data['contentType']}")
    print(f"profile={data['profile']}")
    print(f"action={data['action']}")
    print(f"command_id={data['commandId']}")
    print(f"command={data['command']}")
    print(f"owner_skill={data['ownerSkill']}")
    print(f"owner_agent={data.get('ownerAgent') or ''}")
    print("executes=false")
  return 0


def handle_contract(root: Path, args: argparse.Namespace) -> int:
  data = validate_contract_examples(root)
  if args.json:
    print_json(json_envelope(root, data))
  else:
    print(f"valid={str(data['valid']).lower()}")
    for result in data["contracts"]:
      print(
        f"contract={result['contract']}\t"
        f"valid={str(result['valid']).lower()}\t"
        f"errors={len(result['errors'])}"
      )
    for error in data["errors"]:
      print(f"error={error['contract']}:{error['error']}")
  return 0 if data["valid"] else 2


def print_run_summary(data: Dict[str, Any]) -> None:
  print(f"id={data['id']}")
  print(f"content_type={data['contentType']}")
  print(f"channel={data['channel']}")
  print(f"system_version={data['systemVersion']}")
  print(f"status={data['status']}")
  print(f"current_stage={data['currentStage']}")
  print(f"revision={data['revision']}")
  print(f"publish_ready={str(data.get('publishReady', False)).lower()}")
  print(f"artifacts={len(data.get('artifacts', []))}")


def handle_run(root: Path, args: argparse.Namespace) -> int:
  if args.run_action == "start":
    data = start_run(
      root=root,
      date=args.date,
      content_type=args.content_type,
      title=args.title,
      run_id=args.id,
      channel=args.channel,
      actor=args.actor,
    )
    if args.json:
      print_json(json_envelope(root, data))
    else:
      print_run_summary(data)
      print(f"reused={str(data.get('reused', False)).lower()}")
    return 0

  if args.run_action == "status":
    data = get_run(root, args.id)
    if args.json:
      print_json(json_envelope(root, data))
    else:
      print_run_summary(data)
    return 0

  if args.run_action == "list":
    data = list_runs(root)[:max(0, args.limit)]
    if args.json:
      print_json(json_envelope(root, data))
    else:
      for run in data:
        print(
          f"{run['id']}\t{run['channel']}\t{run['status']}\t"
          f"{run['currentStage']}\t{run['updatedAt']}"
        )
    return 0

  if args.run_action == "advance":
    publish_ready = None
    if args.publish_ready is not None:
      publish_ready = args.publish_ready == "true"
    data = advance_run(
      root=root,
      run_id=args.id,
      stage=args.stage,
      step_status=args.step_status,
      actor=args.actor,
      note=args.note,
      publish_ready=publish_ready,
    )
    if args.json:
      print_json(json_envelope(root, data))
    else:
      print_run_summary(data)
    return 0

  if args.run_action == "artifact":
    data = register_artifact(
      root=root,
      run_id=args.id,
      artifact_id=args.artifact_id,
      step_id=args.step,
      artifact_type=args.type,
      label=args.label,
      path_value=args.path,
      mime_type=args.mime_type,
      duration_seconds=args.duration_seconds,
      actor=args.actor,
    )
    if args.json:
      print_json(json_envelope(root, data))
    else:
      print(f"artifact_id={data['id']}")
      print(f"run_id={data['runId']}")
      print(f"path={data['relativePath']}")
      print(f"available={str(data['available']).lower()}")
    return 0

  if args.run_action == "validate":
    data = validate_run(root, args.id)
    if args.json:
      print_json(json_envelope(root, data))
    else:
      print(f"valid={str(data['valid']).lower()}")
      print(f"run_id={data['runId']}")
      print(f"status={data['status']}")
      print(f"current_stage={data['currentStage']}")
      print(f"revision={data['revision']}")
      print(f"artifacts={data['artifactCount']}")
      for error in data["errors"]:
        print(f"error={error['scope']}:{error['error']}")
    return 0 if data["valid"] else 2

  if args.run_action == "finalize-active":
    data = finalize_active_run(
      root,
      date=args.date,
      publish_package_path=args.publish_package,
      content_type=args.content_type,
      script_path=args.script,
      recording_path=args.recording,
      actor=args.actor,
    )
    if args.json:
      print_json(json_envelope(root, data))
    else:
      print(f"enabled={str(data['enabled']).lower()}")
      print(f"changed={str(data['changed']).lower()}")
      print(f"valid={str(data['valid']).lower()}")
      print(f"reason={data['reason']}")
      if data.get("run"):
        print(f"run_id={data['run']['id']}")
    return 0 if data["valid"] else 2

  raise RunStateError(f"Unknown run action: {args.run_action}")


def main(argv: Optional[list] = None) -> int:
  parser = build_parser()
  args = parser.parse_args(argv)
  try:
    root = resolve_project_root(
      explicit=args.root,
      start=Path.cwd(),
      fallback=INSTALL_ROOT,
    )
    if args.command == "init":
      return handle_init(root, args)
    if args.command == "doctor":
      return handle_doctor(root, args)
    if args.command == "context":
      return handle_context(root, args)
    if args.command == "observe":
      return handle_observe(root, args)
    if args.command == "evolve":
      return handle_evolve(root, args)
    if args.command == "system" and args.system_action == "info":
      return handle_system(root, args)
    if args.command == "system" and args.system_action == "reconcile":
      return handle_system_reconcile(root, args)
    if args.command == "registry" and args.registry_action == "validate":
      return handle_registry(root, args)
    if args.command == "content-type" and args.content_action == "list":
      return handle_content_type(root, args)
    if args.command == "profile" and args.profile_action == "get":
      return handle_profile(root, args)
    if args.command == "release" and args.release_action == "status":
      return handle_release(root, args)
    if args.command == "release" and args.release_action == "transcript-check":
      return handle_transcript_check(root, args)
    if args.command == "release" and args.release_action == "shadow-check":
      return handle_shadow_check(root, args)
    if args.command == "release" and args.release_action == "historical-shadow-check":
      return handle_historical_shadow_check(root, args)
    if args.command == "release" and args.release_action == "readiness":
      return handle_release_readiness(root, args)
    if args.command == "release" and args.release_action == "canary-check":
      return handle_release_canary_check(root, args)
    if args.command == "release" and args.release_action == "canary-adopt":
      return handle_release_canary_adopt(root, args)
    if args.command == "release" and args.release_action == "activate":
      return handle_release_activate(root, args)
    if args.command == "release" and args.release_action == "rollback":
      return handle_release_rollback(root, args)
    if args.command == "route" and args.route_action == "resolve":
      return handle_route(root, args)
    if args.command == "contract" and args.contract_action == "validate":
      return handle_contract(root, args)
    if args.command == "run":
      return handle_run(root, args)
    parser.error(f"Unknown command: {args.command}")
  except ObservationParseError as error:
    payload = error_envelope("OBSERVATION_PARSE_ERROR", str(error), error.errors)
    print_json(payload)
    return 2
  except EvolutionDeferred as error:
    payload = error_envelope("EVOLUTION_DEFERRED", str(error), {"locks": error.locks})
    print_json(payload)
    return 4
  except LeaseBusy as error:
    payload = error_envelope("LEASE_BUSY", str(error), {"path": str(error.path)})
    print_json(payload)
    return 4
  except KeyError as error:
    payload = error_envelope("NOT_FOUND", f"Registry item not found: {error.args[0]}")
    print_json(payload)
    return 3
  except RouteResolutionError as error:
    payload = error_envelope("ROUTE_RESOLUTION_ERROR", str(error))
    print_json(payload)
    return 3
  except ReleaseTransitionError as error:
    payload = error_envelope("RELEASE_TRANSITION_ERROR", str(error))
    print_json(payload)
    return 3
  except RunStateError as error:
    payload = error_envelope("RUN_STATE_ERROR", str(error))
    print_json(payload)
    return 3
  except (EvolutionError, RootDiscoveryError, OSError, json.JSONDecodeError) as error:
    payload = error_envelope("EVOLUTION_ERROR", str(error))
    print_json(payload)
    return 2
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
