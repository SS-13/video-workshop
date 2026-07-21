from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "topk-merge.yml"


class TopKWorkflowContractTest(unittest.TestCase):
  def test_merge_workflow_has_post_merge_fallback_and_safe_reconciliation(self):
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    self.assertIn("issues: write", workflow)
    self.assertIn("github.event_name == 'pull_request_target'", workflow)
    self.assertIn("github.event.action == 'closed'", workflow)
    self.assertIn("github.event_name == 'workflow_run'", workflow)
    self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)
    self.assertIn("startsWith(github.event.pull_request.head.ref, 'fix/topk-')", workflow)
    self.assertIn("[[ \"${head_ref}\" != fix/topk-* ]]", workflow)
    self.assertIn("sleep 5", workflow)
    self.assertIn("evolve issues reconcile", workflow)


if __name__ == "__main__":
  unittest.main()
