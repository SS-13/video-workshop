from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image


TOOLS_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

from video_production_core.project_root import (  # noqa: E402
  RootDiscoveryError,
  resolve_project_root,
)
from video_production_core.contracts import (  # noqa: E402
  load_json as load_contract_json,
  validate_contract_examples,
  validate_value,
)
from video_production_core.registry import (  # noqa: E402
  get_content_types,
  get_profile,
  get_release_status,
  validate_control_plane,
)
from video_production_core.routing import resolve_route  # noqa: E402
from video_production_core.transcript_quality import compare_transcripts  # noqa: E402
from video_production_core.shadow_validation import (  # noqa: E402
  inside,
  parse_ass,
  parse_ssim_output,
)
from video_production_core.release_transition import (  # noqa: E402
  activate_release,
  activation_readiness,
  rollback_release,
)
from video_production_core.state_reconcile import reconcile_state  # noqa: E402
from video_production_core.workspace_bootstrap import (  # noqa: E402
  CONTENT_LEDGER_FIELDS,
  WORKSPACE_DIRECTORIES,
  build_ai_context,
  doctor_workspace,
  initialize_workspace,
)
from video_production_core.run_store import (  # noqa: E402
  RunStateError,
  advance_run,
  get_run,
  register_artifact,
  start_run,
  validate_run,
)
from video_production_core.canary_validation import validate_real_canary  # noqa: E402
from video_production_core.canary_adoption import adopt_canary_run  # noqa: E402
from video_production_core.active_finalization import finalize_active_run  # noqa: E402
from video_production_core.cover_workflow import (  # noqa: E402
  CoverWorkflowError,
  list_cover_history,
  make_cover_pair,
  register_pencil_design,
)


class ProjectRootTest(unittest.TestCase):
  def make_workspace(self, root):
    (root / "00_system").mkdir(parents=True)
    (root / "00_system" / "system.json").write_text("{}\n", encoding="utf-8")

  def test_discovers_root_from_nested_directory(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory) / "renamed-video-production"
      nested = root / "03_recordings" / "2026-07-13"
      nested.mkdir(parents=True)
      self.make_workspace(root)

      discovered = resolve_project_root(start=nested, environment={})

      self.assertEqual(discovered, root.resolve())

  def test_environment_override_does_not_depend_on_folder_name(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory) / "任意目录名"
      root.mkdir(parents=True)
      self.make_workspace(root)

      discovered = resolve_project_root(
        start=Path(directory),
        environment={"VIDEO_PRODUCTION_ROOT": str(root)},
      )

      self.assertEqual(discovered, root.resolve())

  def test_invalid_explicit_root_fails(self):
    with tempfile.TemporaryDirectory() as directory:
      with self.assertRaises(RootDiscoveryError):
        resolve_project_root(explicit=directory, environment={})


class WorkspaceBootstrapTest(unittest.TestCase):
  def make_minimal_core(self, root):
    (root / "00_system").mkdir(parents=True)
    (root / "00_system" / "system.json").write_text(
      json.dumps({
        "activeRelease": "3.0.0",
        "defaultContentType": "video-diary",
      }) + "\n",
      encoding="utf-8",
    )
    (root / "00_system" / "evolution-policy.json").write_text(
      '{"topK": 3}\n',
      encoding="utf-8",
    )
    (root / "package.json").write_text('{"version": "3.0.0"}\n', encoding="utf-8")
    (root / ".codex" / "skills").mkdir(parents=True)

  def test_initialization_is_idempotent_and_starts_empty(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_minimal_core(root)

      first = initialize_workspace(root)
      second = initialize_workspace(root)

      self.assertTrue(first["changed"])
      self.assertFalse(second["changed"])
      counter = json.loads((root / "00_state" / "day-counter.json").read_text(encoding="utf-8"))
      self.assertEqual(counter["lastDay"], 0)
      ledger_header = (root / "00_state" / "content-ledger.csv").read_text(
        encoding="utf-8"
      ).strip()
      self.assertEqual(ledger_header, ",".join(CONTENT_LEDGER_FIELDS))

  def test_initialization_creates_complete_private_workspace_without_overwriting_seed(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_minimal_core(root)

      initialize_workspace(root)

      for value in WORKSPACE_DIRECTORIES:
        with self.subTest(directory=value):
          self.assertTrue((root / value).is_dir())

      seed = root / "12_research" / "high-frequency-questions.md"
      self.assertTrue(seed.is_file())
      seed.write_text("# Local questions\n\nKeep this edit.\n", encoding="utf-8")

      second = initialize_workspace(root)

      self.assertFalse(second["changed"])
      self.assertEqual(
        seed.read_text(encoding="utf-8"),
        "# Local questions\n\nKeep this edit.\n",
      )

  def test_clean_core_can_be_initialized_and_pass_doctor(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      shutil.copytree(PROJECT_ROOT / "00_system", root / "00_system")
      shutil.copytree(PROJECT_ROOT / ".codex", root / ".codex")
      shutil.copy2(PROJECT_ROOT / "package.json", root / "package.json")
      shutil.copy2(PROJECT_ROOT / ".gitignore", root / ".gitignore")
      shutil.copy2(PROJECT_ROOT / "AGENTS.md", root / "AGENTS.md")
      shutil.copy2(PROJECT_ROOT / "START_HERE.md", root / "START_HERE.md")
      shutil.copy2(PROJECT_ROOT / "PIPELINE.md", root / "PIPELINE.md")
      shutil.copy2(PROJECT_ROOT / "WORKFLOW.md", root / "WORKFLOW.md")

      initialize_workspace(root)
      result = doctor_workspace(root)

      self.assertTrue(result["valid"], result["requiredFailures"])
      self.assertTrue(result["readyForContent"])
      self.assertTrue(result["loopReady"])
      self.assertEqual(result["personalizationStatus"], "pending")

      workspace_path = root / "00_state" / "workspace.json"
      workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
      workspace["integrations"]["githubIssues"] = {
        "enabled": True,
        "repository": "example/video-workshop",
      }
      workspace_path.write_text(json.dumps(workspace), encoding="utf-8")
      with patch(
        "video_production_core.workspace_bootstrap.github_auth_ready",
        return_value=False,
      ):
        github_unavailable = doctor_workspace(root)

      github_check = next(
        check for check in github_unavailable["checks"]
        if check["name"] == "github-issues"
      )
      self.assertEqual(github_check["status"], "fail")
      self.assertFalse(github_check["required"])
      self.assertFalse(github_unavailable["githubIssuesReady"])
      self.assertTrue(github_unavailable["readyForContent"])

  def test_ai_context_lists_public_order_and_local_corpus(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      shutil.copytree(PROJECT_ROOT / "00_system", root / "00_system")
      shutil.copytree(PROJECT_ROOT / ".codex", root / ".codex")
      shutil.copy2(PROJECT_ROOT / "package.json", root / "package.json")
      shutil.copy2(PROJECT_ROOT / "AGENTS.md", root / "AGENTS.md")
      shutil.copy2(PROJECT_ROOT / "START_HERE.md", root / "START_HERE.md")
      shutil.copy2(PROJECT_ROOT / "PIPELINE.md", root / "PIPELINE.md")
      shutil.copy2(PROJECT_ROOT / "WORKFLOW.md", root / "WORKFLOW.md")
      initialize_workspace(root)
      (root / "01_inbox" / "sample.md").write_text("sample\n", encoding="utf-8")
      (root / "06_logs" / "README.md").write_text("public placeholder\n", encoding="utf-8")

      context = build_ai_context(root)

      self.assertEqual(context["publicReadOrder"][0], "AGENTS.md")
      self.assertEqual(context["personalization"]["status"], "pending")
      self.assertIn("01_inbox/sample.md", context["personalization"]["sourceFiles"])
      self.assertNotIn("06_logs/README.md", context["personalization"]["sourceFiles"])

  def test_doctor_blocks_render_when_disk_space_is_below_threshold(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      shutil.copytree(PROJECT_ROOT / "00_system", root / "00_system")
      shutil.copytree(PROJECT_ROOT / ".codex", root / ".codex")
      shutil.copy2(PROJECT_ROOT / "package.json", root / "package.json")
      shutil.copy2(PROJECT_ROOT / ".gitignore", root / ".gitignore")
      shutil.copy2(PROJECT_ROOT / "AGENTS.md", root / "AGENTS.md")
      shutil.copy2(PROJECT_ROOT / "START_HERE.md", root / "START_HERE.md")
      shutil.copy2(PROJECT_ROOT / "PIPELINE.md", root / "PIPELINE.md")
      shutil.copy2(PROJECT_ROOT / "WORKFLOW.md", root / "WORKFLOW.md")
      initialize_workspace(root)

      with patch(
        "video_production_core.media_retention.shutil.disk_usage",
        return_value=type("Usage", (), {"free": 1024})(),
      ):
        result = doctor_workspace(root)

      disk_check = next(
        check for check in result["checks"] if check["name"] == "disk-space"
      )
      self.assertEqual(disk_check["status"], "fail")
      self.assertTrue(result["valid"])
      self.assertFalse(result["readyForRender"])


class CoverWorkflowTest(unittest.TestCase):
  def make_root(self, root):
    routes_path = root / ".codex" / "skills" / "video-diary-cover" / "references"
    routes_path.mkdir(parents=True)
    (routes_path / "cover-routes.json").write_text(
      json.dumps({
        "defaultRoute": "video-diary",
        "routes": {
          "video-diary": {
            "defaultVersion": "v1.0",
            "aliases": ["视频日记"],
            "versions": {
              "v1.0": {"seriesLabel": "视频日记", "titleMode": "free-title"},
            },
          },
        },
      }, ensure_ascii=False, indent=2) + "\n",
      encoding="utf-8",
    )

  def make_image(self, path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (38, 42, 48)).save(path)

  def test_pencil_design_registration_is_versioned_and_immutable(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_root(root)
      source = root / "design.pen"
      source.write_text("pencil design\n", encoding="utf-8")
      preview_3x4 = root / "preview-3x4.png"
      preview_4x3 = root / "preview-4x3.png"
      self.make_image(preview_3x4, (1080, 1440))
      self.make_image(preview_4x3, (1440, 1080))
      tokens = root / "tokens.json"
      tokens.write_text(
        json.dumps({"seriesLabel": "视频日记", "titleMode": "free-title"}) + "\n",
        encoding="utf-8",
      )
      invalid_preview = root / "invalid-preview.png"
      self.make_image(invalid_preview, (1000, 1000))

      with self.assertRaises(CoverWorkflowError):
        register_pencil_design(
          root=root,
          route="video-diary",
          version="v1.1",
          pencil_source=source,
          preview_3x4=invalid_preview,
          preview_4x3=preview_4x3,
          tokens=tokens,
        )

      result = register_pencil_design(
        root=root,
        route="video-diary",
        version="v1.1",
        pencil_source=source,
        preview_3x4=preview_3x4,
        preview_4x3=preview_4x3,
        tokens=tokens,
        activate=True,
        note="Pencil layout approved",
      )

      self.assertTrue(result["active"])
      self.assertTrue((root / result["manifest"]).is_file())
      routes = json.loads(
        (root / ".codex/skills/video-diary-cover/references/cover-routes.json").read_text(
          encoding="utf-8"
        )
      )
      self.assertEqual(routes["routes"]["video-diary"]["defaultVersion"], "v1.1")
      self.assertIn("v1.1", routes["routes"]["video-diary"]["versions"])

      with self.assertRaises(CoverWorkflowError):
        register_pencil_design(
          root=root,
          route="video-diary",
          version="v1.1",
          pencil_source=source,
          preview_3x4=preview_3x4,
          preview_4x3=preview_4x3,
          tokens=tokens,
        )

  def test_cover_history_distinguishes_pencil_and_renderer_versions(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_root(root)
      manifest_path = (
        root / "15_cover_gallery/designs/video-diary/v1.0/manifest.json"
      )
      manifest_path.parent.mkdir(parents=True)
      manifest_path.write_text(
        json.dumps({
          "createdAt": "2026-07-14T10:00:00+08:00",
          "note": "Original Pencil style",
        }) + "\n",
        encoding="utf-8",
      )
      date_index = root / "15_cover_gallery/2026-07-14/INDEX.md"
      date_index.parent.mkdir(parents=True)
      date_index.write_text(
        "| version | file | route | style_version | title | note |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| v01 | cover.jpg | video-diary | v1.0 | Test title | 3x4 |\n",
        encoding="utf-8",
      )

      result = list_cover_history(root, route="video-diary", limit=5)

      self.assertEqual(result["styleVersions"][0]["origin"], "pencil")
      self.assertEqual(result["dailyRevisions"][0]["version"], "v01")

  def test_cover_make_uses_one_command_and_archives_both_aspects(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_root(root)
      portrait = root / "portrait.jpg"
      landscape = root / "landscape.jpg"
      self.make_image(portrait, (1080, 1440))
      self.make_image(landscape, (1440, 1080))
      calls = []
      archive_count = 0

      def fake_run(command, command_root):
        nonlocal archive_count
        calls.append(command)
        script = Path(command[1]).name
        if script == "render-cover-pair.py":
          prefix = Path(command[command.index("--output-prefix") + 1])
          self.make_image(prefix.parent / f"{prefix.name}_3x4.jpg", (1080, 1440))
          self.make_image(prefix.parent / f"{prefix.name}_4x3.jpg", (1440, 1080))
          manifest = (
            command_root / "04_videos/2026-07-14/video-diary/001/cover-qc"
            / f"{prefix.name}_pair_manifest.json"
          )
          manifest.parent.mkdir(parents=True, exist_ok=True)
          manifest.write_text("{}\n", encoding="utf-8")
          stdout = "qc=pass\n"
        elif script == "archive-cover.mjs":
          archive_count += 1
          stdout = f"cover=15_cover_gallery/2026-07-14/v0{archive_count}_cover.jpg\n"
        else:
          stdout = "gallery=15_cover_gallery/INDEX.md\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

      with patch(
        "video_production_core.cover_workflow.run_command",
        side_effect=fake_run,
      ):
        result = make_cover_pair(
          root=root,
          date="2026-07-14",
          portrait=portrait,
          landscape=landscape,
          day_label="Day 42",
          title="Test title",
        )

      self.assertEqual(len(calls), 4)
      self.assertEqual(result["styleVersion"], "v1.0")
      self.assertTrue(result["archived"]["3x4"].endswith("v01_cover.jpg"))
      self.assertTrue(result["archived"]["4x3"].endswith("v02_cover.jpg"))


class ControlPlaneRegistryTest(unittest.TestCase):
  def test_current_control_plane_is_valid(self):
    result = validate_control_plane(PROJECT_ROOT)

    self.assertTrue(result["valid"], result["errors"])
    self.assertEqual(result["counts"]["contentTypes"], 3)
    self.assertEqual(result["counts"]["profiles"], 3)
    self.assertGreaterEqual(result["counts"]["commands"], 40)

  def test_video_diary_is_the_single_default(self):
    content_types = get_content_types(PROJECT_ROOT)
    defaults = [item["id"] for item in content_types if item["default"]]

    self.assertEqual(defaults, ["video-diary"])

  def test_video_diary_profile_preserves_stable_and_legacy_routes(self):
    profile = get_profile(PROJECT_ROOT, "video-diary-default")

    self.assertEqual(profile["commands"]["render"], "edit:render-day-v2")
    self.assertEqual(profile["commands"]["fallbackRender"], "edit:render-day-legacy")
    self.assertTrue(profile["quality"]["publishPackageRequired"])

  def test_release_status_preserves_channels_and_active_identity(self):
    status = get_release_status(PROJECT_ROOT)

    self.assertEqual(status["stableRelease"], "2.1.0")
    self.assertEqual(status["candidateRelease"], "3.0.0")
    self.assertIn(status["activeRelease"], {"2.1.0", "3.0.0"})
    self.assertEqual(
      status["candidateManifest"]["active"],
      status["activeRelease"] == status["candidateRelease"],
    )
    package_version = json.loads(
      (PROJECT_ROOT / "package.json").read_text(encoding="utf-8")
    )["version"]
    self.assertEqual(package_version, status["activeRelease"])

  def test_release_commands_have_separate_release_agent_ownership(self):
    commands = json.loads(
      (PROJECT_ROOT / "00_system" / "registries" / "commands.json").read_text(encoding="utf-8")
    )["commands"]
    agents = json.loads(
      (PROJECT_ROOT / "00_system" / "registries" / "agents.json").read_text(encoding="utf-8")
    )["agents"]
    owners = json.loads(
      (PROJECT_ROOT / "00_system" / "owner-registry.json").read_text(encoding="utf-8")
    )["components"]

    self.assertEqual(commands["release:canary-adopt"]["owner"], "video-production-release")
    self.assertEqual(commands["release:canary-check"]["owner"], "video-production-release")
    self.assertEqual(commands["release:activate"]["owner"], "video-production-release")
    self.assertEqual(commands["release:rollback"]["owner"], "video-production-release")
    self.assertIn("release-agent", agents)
    self.assertEqual(owners["release-gate"]["agent"], "release-agent")
    self.assertEqual(owners["evolution-loop"]["agent"], "system-steward-agent")


class ProfileRoutingTest(unittest.TestCase):
  def test_video_diary_render_resolves_to_v2_without_execution(self):
    route = resolve_route(PROJECT_ROOT, "video-diary", "render")

    self.assertEqual(route["profile"], "video-diary-default")
    self.assertEqual(route["commandId"], "edit:render-day-v2")
    self.assertEqual(route["ownerSkill"], "video-diary-edit")
    self.assertEqual(route["ownerAgent"], "video-agent")
    self.assertFalse(route["executes"])

  def test_video_diary_fallback_resolves_to_legacy(self):
    route = resolve_route(PROJECT_ROOT, "video-diary", "fallbackRender")

    self.assertEqual(route["commandId"], "edit:render-day-legacy")
    self.assertIn("--engine legacy", route["command"])

  def test_video_diary_publish_package_is_routable(self):
    route = resolve_route(PROJECT_ROOT, "video-diary", "publishPackage")

    self.assertEqual(route["commandId"], "publish:package")
    self.assertEqual(route["ownerSkill"], "video-diary-edit")
    self.assertEqual(route["ownerAgent"], "video-agent")

  def test_all_profiles_resolve_their_declared_render_route(self):
    for content_type in get_content_types(PROJECT_ROOT, enabled_only=True):
      route = resolve_route(PROJECT_ROOT, content_type["id"], "render")

      self.assertEqual(route["contentType"], content_type["id"])
      self.assertTrue(route["stableCompatible"])


class ContractValidationTest(unittest.TestCase):
  def test_all_contract_examples_are_valid(self):
    result = validate_contract_examples(PROJECT_ROOT)

    self.assertTrue(result["valid"], result["errors"])
    self.assertEqual(len(result["contracts"]), 5)
    self.assertIn(
      "evolution-observation",
      {item["contract"] for item in result["contracts"]},
    )

  def test_invalid_contract_is_detected(self):
    schema = load_contract_json(
      PROJECT_ROOT / "00_system" / "contracts" / "schemas" / "artifact.schema.json"
    )
    invalid_artifact = {
      "id": "artifact_invalid",
      "runId": "run_invalid",
      "stepId": "step_invalid",
      "type": "video",
      "label": "Invalid artifact",
      "relativePath": "05_exports/invalid.mp4",
      "available": True,
      "sizeBytes": -1,
    }

    errors = validate_value(invalid_artifact, schema)

    self.assertTrue(any("below minimum" in error for error in errors))

  def test_boolean_is_not_accepted_as_integer(self):
    errors = validate_value(True, {"type": "integer"})

    self.assertTrue(errors)


class TranscriptQualityTest(unittest.TestCase):
  def write_srt(self, path, text):
    path.write_text(
      f"1\n00:00:00,000 --> 00:00:02,000\n{text}\n",
      encoding="utf-8",
    )

  def test_punctuation_and_spacing_do_not_reduce_accuracy(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      actual = root / "actual.srt"
      expected = root / "expected.srt"
      self.write_srt(actual, "今天是 7 月 12 号，晚上。")
      self.write_srt(expected, "今天是7月12号晚上")

      result = compare_transcripts(actual, expected, 1.0)

      self.assertTrue(result["passed"])
      self.assertEqual(result["editDistance"], 0)

  def test_semantic_transcription_error_fails_golden_gate(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      actual = root / "actual.srt"
      expected = root / "expected.srt"
      self.write_srt(actual, "改到一班只有23分钟的车")
      self.write_srt(expected, "改到一班只有20分钟的车")

      result = compare_transcripts(actual, expected, 0.98)

      self.assertFalse(result["passed"])
      self.assertGreater(result["editDistance"], 0)


class ShadowValidationTest(unittest.TestCase):
  def test_workspace_containment_rejects_sibling_path(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      workspace = root / "shadow"
      workspace.mkdir()

      self.assertTrue(inside(workspace / "output.mp4", workspace))
      self.assertFalse(inside(root / "05_exports" / "output.mp4", workspace))

  def test_ass_parser_reads_safe_area_and_line_count(self):
    with tempfile.TemporaryDirectory() as directory:
      ass = Path(directory) / "sample.ass"
      ass.write_text(
        "\n".join([
          "[Script Info]",
          "PlayResX: 1080",
          "PlayResY: 1920",
          "[V4+ Styles]",
          "Format: Name, Fontname, Fontsize, BorderStyle, Alignment, MarginL, MarginR, MarginV",
          "Style: Default,Arial Unicode MS,44,3,2,216,216,620",
          "[Events]",
          "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,第一行\\N第二行",
        ]) + "\n",
        encoding="utf-8",
      )

      result = parse_ass(ass)

      self.assertEqual(result["fontSize"], 44)
      self.assertEqual(result["marginVertical"], 620)
      self.assertEqual(result["maxLines"], 2)

  def test_ssim_parser_reads_all_score(self):
    output = "SSIM Y:1.000000 (inf) U:1.000000 (inf) V:1.000000 (inf) All:1.000000 (inf)"

    self.assertEqual(parse_ssim_output(output), 1.0)


class ReleaseTransitionTest(unittest.TestCase):
  def make_release_workspace(self, root, canary_status="pass"):
    (root / "00_system" / "releases" / "3.0.0").mkdir(parents=True)
    (root / "00_system" / "system.json").write_text(json.dumps({
      "activeRelease": "2.1.0",
      "candidateRelease": "3.0.0",
    }), encoding="utf-8")
    (root / "00_system" / "release-policy.json").write_text(json.dumps({
      "stableRelease": "2.1.0",
    }), encoding="utf-8")
    (root / "package.json").write_text(json.dumps({
      "version": "2.1.0",
      "scripts": {},
    }), encoding="utf-8")
    (root / "00_system" / "releases" / "3.0.0" / "manifest.json").write_text(json.dumps({
      "version": "3.0.0",
      "status": "rc1",
      "stableFallback": "2.1.0",
      "active": False,
      "gates": {
        "shortGoldenRegression": "pass",
        "legacyFallback": "pass",
        "realVideoCanary": canary_status,
        "manualActivation": "pending",
      },
    }), encoding="utf-8")

  def test_pending_canary_blocks_activation(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_release_workspace(root, canary_status="pending")

      readiness = activation_readiness(root)

      self.assertFalse(readiness["ready"])
      self.assertEqual(readiness["blockingGates"], {"realVideoCanary": "pending"})

  def test_activation_and_rollback_change_both_release_pointers(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_release_workspace(root)

      activated = activate_release(root, confirm=True, actor="test")

      self.assertTrue(activated["changed"])
      self.assertEqual(json.loads((root / "00_system" / "system.json").read_text())["activeRelease"], "3.0.0")
      self.assertEqual(json.loads((root / "package.json").read_text())["version"], "3.0.0")

      rolled_back = rollback_release(root, confirm=True, actor="test")

      self.assertTrue(rolled_back["changed"])
      self.assertEqual(json.loads((root / "00_system" / "system.json").read_text())["activeRelease"], "2.1.0")
      self.assertEqual(json.loads((root / "package.json").read_text())["version"], "2.1.0")


class StateReconcileTest(unittest.TestCase):
  def make_state_workspace(self, root):
    (root / "00_state").mkdir(parents=True)
    (root / "00_state" / "day-counter.json").write_text(json.dumps({
      "lastDay": 31,
      "lastContentId": "2026-07-03_Day31",
    }), encoding="utf-8")
    (root / "00_state" / "production-stats.csv").write_text(
      "content_id,date,column,day_label,title,video_path,cover_path\n"
      "2026-07-03_Day31,2026-07-03,video-diary,Day 31,旧标题,05_exports/31.mp4,05_exports/31.jpg\n"
      "2026-07-12_Day40,2026-07-12,video-diary,Day 40,示例标题,05_exports/40.mp4,05_exports/40.jpg\n",
      encoding="utf-8",
    )
    (root / "00_state" / "content-ledger.csv").write_text(
      ",".join([
        "content_id", "date", "column", "day_label", "title", "status",
        "inbox_ref", "script_ref", "recording_ref", "workspace_ref",
        "export_ref", "cover_ref", "published_at", "douyin_url", "notes",
      ]) + "\n"
      "2026-07-03_Day31,2026-07-03,video-diary,Day 31,旧标题,scripted,"
      "01_inbox/2026-07-03.md,02_scripts/2026-07-03.md,03_recordings/2026-07-03/,"
      "04_videos/2026-07-03/,,,,,\n",
      encoding="utf-8",
    )

  def test_reconcile_dry_run_and_apply(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_state_workspace(root)

      preview = reconcile_state(root, apply=False)

      self.assertEqual(preview["latestDay"], 40)
      self.assertFalse(preview["applied"])
      self.assertEqual(json.loads((root / "00_state" / "day-counter.json").read_text())["lastDay"], 31)

      applied = reconcile_state(root, apply=True)

      self.assertTrue(applied["applied"])
      self.assertEqual(json.loads((root / "00_state" / "day-counter.json").read_text())["lastDay"], 40)
      ledger = (root / "00_state" / "content-ledger.csv").read_text(encoding="utf-8")
      self.assertIn("2026-07-12_Day40", ledger)
      self.assertIn("exported", ledger)


class RunStoreTest(unittest.TestCase):
  def make_run_workspace(self, root):
    (root / "00_system" / "content-types").mkdir(parents=True)
    (root / "00_system" / "profiles").mkdir(parents=True)
    (root / "00_system" / "contracts" / "schemas").mkdir(parents=True)
    (root / "00_state").mkdir(parents=True)
    (root / "00_system" / "system.json").write_text(json.dumps({
      "activeRelease": "2.1.0",
      "candidateRelease": "3.0.0",
      "contentTypeRoot": "00_system/content-types",
      "profileRoot": "00_system/profiles",
      "runRoot": "00_state/runs",
    }), encoding="utf-8")
    (root / "00_system" / "content-types" / "video-diary.json").write_text(json.dumps({
      "id": "video-diary",
      "enabled": True,
      "default": True,
      "profile": "video-diary-default",
    }), encoding="utf-8")
    (root / "00_system" / "profiles" / "video-diary-default.json").write_text(json.dumps({
      "id": "video-diary-default",
      "contentType": "video-diary",
    }), encoding="utf-8")
    for name in ["run.schema.json", "artifact.schema.json"]:
      source = PROJECT_ROOT / "00_system" / "contracts" / "schemas" / name
      target = root / "00_system" / "contracts" / "schemas" / name
      target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

  def test_run_lifecycle_and_artifact_contract(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_run_workspace(root)
      artifact_path = root / "artifact.srt"
      artifact_path.write_text("subtitle", encoding="utf-8")

      created = start_run(
        root,
        date="2026-07-13",
        content_type="video-diary",
        run_id="2026-07-13_Day41",
        channel="canary",
        actor="test",
      )
      advanced = created
      for stage in ["input_review", "script", "recording", "cover", "subtitles"]:
        advanced = advance_run(
          root,
          run_id=created["id"],
          stage=stage,
          actor="test",
        )
      artifact = register_artifact(
        root,
        run_id=created["id"],
        artifact_id="artifact_srt",
        step_id="subtitles",
        artifact_type="subtitle",
        label="Corrected SRT",
        path_value=str(artifact_path),
        mime_type="application/x-subrip",
        actor="test",
      )
      validation = validate_run(root, created["id"])

      self.assertEqual(created["systemVersion"], "3.0.0")
      self.assertEqual(advanced["currentStage"], "subtitles")
      self.assertTrue(artifact["available"])
      self.assertTrue(validation["valid"], validation["errors"])
      self.assertEqual(get_run(root, created["id"])["revision"], 6)

  def test_existing_run_id_cannot_change_channel(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_run_workspace(root)
      start_run(
        root,
        date="2026-07-13",
        content_type="video-diary",
        run_id="2026-07-13_Day41",
        channel="stable",
        actor="test",
      )

      with self.assertRaisesRegex(RunStateError, "another channel"):
        start_run(
          root,
          date="2026-07-13",
          content_type="video-diary",
          run_id="2026-07-13_Day41",
          channel="canary",
          actor="test",
        )


class CanaryValidationTest(unittest.TestCase):
  def write_png_header(self, path, width, height):
    path.write_bytes(
      b"\x89PNG\r\n\x1a\n"
      + b"\x00\x00\x00\rIHDR"
      + width.to_bytes(4, "big")
      + height.to_bytes(4, "big")
    )

  def make_canary_workspace(
    self,
    root,
    publish_ready=True,
    write_run=True,
    package_system_version="3.0.0",
  ):
    run_id = "2026-07-13_Day41"
    content_id = run_id
    (root / "00_system" / "releases" / "3.0.0").mkdir(parents=True)
    (root / "00_system" / "contracts" / "schemas").mkdir(parents=True)
    (root / "00_system" / "content-types").mkdir(parents=True)
    (root / "00_system" / "profiles").mkdir(parents=True)
    (root / "00_state" / "runs" / run_id).mkdir(parents=True)
    (root / "04_videos" / "2026-07-13" / "subtitles").mkdir(parents=True)
    (root / "05_exports" / "2026-07-13").mkdir(parents=True)

    for name in ["run.schema.json", "artifact.schema.json", "publish-package.schema.json"]:
      source = PROJECT_ROOT / "00_system" / "contracts" / "schemas" / name
      target = root / "00_system" / "contracts" / "schemas" / name
      target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    (root / "00_system" / "system.json").write_text(json.dumps({
      "activeRelease": "2.1.0",
      "candidateRelease": "3.0.0",
      "runRoot": "00_state/runs",
      "contentTypeRoot": "00_system/content-types",
      "profileRoot": "00_system/profiles",
    }), encoding="utf-8")
    (root / "00_system" / "content-types" / "video-diary.json").write_text(json.dumps({
      "id": "video-diary",
      "enabled": True,
      "default": True,
      "profile": "video-diary-default",
    }), encoding="utf-8")
    (root / "00_system" / "profiles" / "video-diary-default.json").write_text(json.dumps({
      "id": "video-diary-default",
      "contentType": "video-diary",
    }), encoding="utf-8")
    (root / "00_system" / "release-policy.json").write_text(json.dumps({
      "stableRelease": "2.1.0",
    }), encoding="utf-8")
    (root / "package.json").write_text(json.dumps({
      "version": "2.1.0",
      "scripts": {},
    }), encoding="utf-8")
    manifest_path = root / "00_system" / "releases" / "3.0.0" / "manifest.json"
    manifest_path.write_text(json.dumps({
      "version": "3.0.0",
      "status": "rc1",
      "stableFallback": "2.1.0",
      "active": False,
      "gates": {
        "legacyFallback": "pass",
        "realVideoCanary": "pending",
        "manualActivation": "pending",
      },
    }), encoding="utf-8")

    workspace = root / "04_videos" / "2026-07-13" / "video-diary" / "001"
    export_dir = root / "05_exports" / "2026-07-13" / "video-diary" / "001"
    srt_path = workspace / "subtitles" / "corrected.srt"
    video_path = export_dir / "final.mp4"
    cover_3x4 = export_dir / "cover_3x4.png"
    cover_4x3 = export_dir / "cover_4x3.png"
    publish_path = export_dir / "publish-package.json"
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\n测试\n", encoding="utf-8")
    video_path.write_bytes(b"canary-video")
    self.write_png_header(cover_3x4, 1080, 1440)
    self.write_png_header(cover_4x3, 1440, 1080)

    publish_package = {
      "runId": run_id,
      "contentId": content_id,
      "platform": "douyin",
      "title": "Canary",
      "description": "Canary description",
      "chapters": [{"startSeconds": 0, "time": "00:00", "title": "开始"}],
      "artifacts": {
        "video": str(video_path.relative_to(root)),
        "cover3x4": str(cover_3x4.relative_to(root)),
        "cover4x3": str(cover_4x3.relative_to(root)),
        "srt": str(srt_path.relative_to(root)),
      },
      "production": {
        "videoDurationSeconds": 1.0,
        "fileSizeBytes": video_path.stat().st_size,
        "productionTotalMinutes": 2.0,
        "subtitleQc": "pass",
        "compliance": "pass",
        "statsRecorded": publish_ready,
        "systemVersion": package_system_version,
      },
      "publishReady": publish_ready,
    }
    publish_path.write_text(json.dumps(publish_package), encoding="utf-8")

    artifacts = []
    for artifact_id, step_id, artifact_type, path in [
      ("corrected-srt", "subtitles", "subtitle", srt_path),
      ("cover-3x4", "cover", "image", cover_3x4),
      ("cover-4x3", "cover", "image", cover_4x3),
      ("final-video", "render", "video", video_path),
      ("publish-json", "publish_package", "json", publish_path),
    ]:
      artifacts.append({
        "id": artifact_id,
        "runId": run_id,
        "stepId": step_id,
        "type": artifact_type,
        "label": artifact_id,
        "relativePath": str(path.relative_to(root)),
        "available": True,
        "sizeBytes": path.stat().st_size,
        "durationSeconds": 1.0 if artifact_type == "video" else None,
      })

    run = {
      "schemaVersion": 1,
      "id": run_id,
      "workflowId": "video-diary-default",
      "contentType": "video-diary",
      "date": "2026-07-13",
      "title": "Canary",
      "channel": "canary",
      "systemVersion": "3.0.0",
      "status": "succeeded",
      "currentStage": "completed",
      "revision": 1,
      "publishReady": publish_ready,
      "createdAt": "2026-07-13T09:00:00+08:00",
      "updatedAt": "2026-07-13T09:10:00+08:00",
      "updatedBy": "test",
      "steps": [{
        "id": "render",
        "status": "succeeded",
        "ownerAgent": "video-agent",
        "startedAt": None,
        "completedAt": None,
        "note": "",
      }],
      "artifacts": artifacts,
    }
    if write_run:
      (root / "00_state" / "runs" / run_id / "run.json").write_text(
        json.dumps(run),
        encoding="utf-8",
      )
    (root / "00_state" / "production-stats.csv").write_text(
      "content_id,date,title\n"
      f"{content_id},2026-07-13,Canary\n",
      encoding="utf-8",
    )
    return run_id, manifest_path

  def test_real_canary_can_record_release_gate(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      run_id, manifest_path = self.make_canary_workspace(root)

      result = validate_real_canary(root, run_id, record_pass=True, actor="test")

      self.assertTrue(result["valid"], result["checks"])
      self.assertTrue(result["recorded"])
      manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
      self.assertEqual(manifest["gates"]["realVideoCanary"], "pass")
      self.assertEqual(manifest["evidence"]["realVideoCanary"]["runId"], run_id)

  def test_not_publish_ready_canary_fails_without_recording(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      run_id, manifest_path = self.make_canary_workspace(root, publish_ready=False)

      result = validate_real_canary(root, run_id, record_pass=True, actor="test")

      self.assertFalse(result["valid"])
      self.assertFalse(result["recorded"])
      manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
      self.assertEqual(manifest["gates"]["realVideoCanary"], "pending")

  def test_adopt_completed_production_creates_valid_canary_run(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      run_id, _ = self.make_canary_workspace(root, write_run=False)
      protected_paths = [
        root / "04_videos" / "2026-07-13" / "video-diary" / "001" / "subtitles" / "corrected.srt",
        root / "05_exports" / "2026-07-13" / "video-diary" / "001" / "final.mp4",
        root / "05_exports" / "2026-07-13" / "video-diary" / "001" / "cover_3x4.png",
        root / "05_exports" / "2026-07-13" / "video-diary" / "001" / "cover_4x3.png",
        root / "05_exports" / "2026-07-13" / "video-diary" / "001" / "publish-package.json",
      ]
      before = {path: path.read_bytes() for path in protected_paths}

      result = adopt_canary_run(root, date="2026-07-13", actor="test")

      self.assertFalse(result["reused"])
      self.assertTrue(result["validation"]["valid"], result["validation"]["checks"])
      run = get_run(root, run_id)
      self.assertEqual(run["channel"], "canary")
      self.assertEqual(run["currentStage"], "completed")
      self.assertTrue(run["publishReady"])
      self.assertEqual({path: path.read_bytes() for path in protected_paths}, before)

      revision = run["revision"]
      repeated = adopt_canary_run(root, date="2026-07-13", actor="test")
      self.assertTrue(repeated["reused"])
      self.assertEqual(get_run(root, run_id)["revision"], revision)

  def test_adopt_rejects_not_ready_package_without_creating_run(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      run_id, _ = self.make_canary_workspace(
        root,
        publish_ready=False,
        write_run=False,
      )

      with self.assertRaisesRegex(RunStateError, "publishReady=true"):
        adopt_canary_run(root, date="2026-07-13", actor="test")

      self.assertFalse((root / "00_state" / "runs" / run_id / "run.json").exists())
      system = json.loads((root / "00_system" / "system.json").read_text(encoding="utf-8"))
      package = json.loads((root / "package.json").read_text(encoding="utf-8"))
      self.assertEqual(system["activeRelease"], "2.1.0")
      self.assertEqual(package["version"], "2.1.0")

  def test_adopt_clones_stable_package_without_reencoding_media(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      content_id, _ = self.make_canary_workspace(
        root,
        write_run=False,
        package_system_version="2.1.0",
      )
      source_package = root / "05_exports" / "2026-07-13" / "video-diary" / "001" / "publish-package.json"
      source_bytes = source_package.read_bytes()
      video = root / "05_exports" / "2026-07-13" / "video-diary" / "001" / "final.mp4"
      video_bytes = video.read_bytes()

      result = adopt_canary_run(root, date="2026-07-13", actor="test")

      self.assertEqual(result["adoptionMode"], "stable-artifact-adoption")
      self.assertTrue(result["validation"]["valid"], result["validation"]["checks"])
      self.assertEqual(source_package.read_bytes(), source_bytes)
      self.assertEqual(video.read_bytes(), video_bytes)
      canary_package = json.loads((root / result["canaryPackage"]).read_text(encoding="utf-8"))
      self.assertEqual(canary_package["production"]["systemVersion"], "3.0.0")
      self.assertEqual(canary_package["canary"]["sourceSystemVersion"], "2.1.0")
      self.assertFalse(canary_package["canary"]["mediaReencoded"])
      self.assertEqual(canary_package["contentId"], content_id)

  def test_canary_adopt_cli_runs_end_to_end_in_isolated_workspace(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_canary_workspace(
        root,
        write_run=False,
        package_system_version="2.1.0",
      )

      result = subprocess.run(
        [
          sys.executable,
          str(TOOLS_DIR / "vp.py"),
          "--root",
          str(root),
          "release",
          "canary-adopt",
          "--date",
          "2026-07-13",
          "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
      )

      self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
      payload = json.loads(result.stdout)
      self.assertTrue(payload["ok"])
      self.assertEqual(payload["data"]["adoptionMode"], "stable-artifact-adoption")
      self.assertTrue(payload["data"]["validation"]["valid"])

  def test_active_finalization_is_dormant_on_2_1(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      run_id, _ = self.make_canary_workspace(root, write_run=False)

      result = finalize_active_run(root, date="2026-07-13", actor="test")

      self.assertFalse(result["enabled"])
      self.assertFalse(result["changed"])
      self.assertTrue(result["valid"])
      self.assertIsNone(result["run"])
      self.assertFalse((root / "00_state" / "runs" / run_id / "run.json").exists())

  def test_activate_finalize_native_run_and_rollback(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      run_id, manifest_path = self.make_canary_workspace(root, write_run=False)
      manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
      manifest["gates"]["realVideoCanary"] = "pass"
      manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
      video = root / "05_exports" / "2026-07-13" / "video-diary" / "001" / "final.mp4"
      video_bytes = video.read_bytes()

      activated = activate_release(root, confirm=True, actor="test")
      finalized = finalize_active_run(root, date="2026-07-13", actor="test")

      self.assertTrue(activated["changed"])
      self.assertTrue(finalized["enabled"])
      self.assertTrue(finalized["changed"])
      self.assertTrue(finalized["valid"], finalized.get("errors"))
      run = get_run(root, run_id)
      self.assertEqual(run["channel"], "stable")
      self.assertEqual(run["systemVersion"], "3.0.0")
      self.assertEqual(run["currentStage"], "completed")
      self.assertTrue(run["publishReady"])
      self.assertEqual(video.read_bytes(), video_bytes)

      rolled_back = rollback_release(root, confirm=True, actor="test")
      self.assertTrue(rolled_back["changed"])
      self.assertEqual(
        json.loads((root / "00_system" / "system.json").read_text(encoding="utf-8"))["activeRelease"],
        "2.1.0",
      )
      self.assertEqual(
        json.loads((root / "package.json").read_text(encoding="utf-8"))["version"],
        "2.1.0",
      )
      self.assertTrue((root / "00_state" / "runs" / run_id / "run.json").exists())


if __name__ == "__main__":
  unittest.main()
