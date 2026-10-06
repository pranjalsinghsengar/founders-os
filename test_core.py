import tempfile
import unittest
from pathlib import Path
from core import Company, PolicyError


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "test.db")
        self.c = Company(self.path)
        self.p, self.digest = self.c.project({"scope": "fixture"}, 10)
        self.c.register_tool("tool", lambda _: {"artifact": "a", "evidence": "e"}, 6)
        self.t = self.c.task(self.p, "dev", "qa", "tool", {})

    def tearDown(self):
        self.c.db.close()
        self.tmp.cleanup()

    def enable(self):
        self.c.approve_local(self.p, self.digest)
        self.c.grant(self.p, "dev", "tool")

    def test_approval_and_permission_enforced(self):
        with self.assertRaises(PolicyError): self.c.execute(self.t)
        with self.assertRaises(PolicyError): self.c.approve_local(self.p, "wrong")
        self.c.approve_local(self.p, self.digest)
        with self.assertRaises(PolicyError): self.c.execute(self.t)
        self.enable()
        self.assertEqual(self.c.execute(self.t), "awaiting_review")

    def test_review_and_dependency(self):
        self.enable()
        child = self.c.task(self.p, "dev", "qa", "tool", {}, [self.t])
        with self.assertRaises(PolicyError): self.c.execute(child)
        self.c.execute(self.t)
        with self.assertRaises(PolicyError): self.c.review(self.t, "dev", True, "self")
        self.c.review(self.t, "qa", True, "validated")
        self.assertEqual(self.c.snapshot()["tasks"][0]["status"], "completed")

    def test_budget_and_duplicate_execution(self):
        self.enable()
        self.c.execute(self.t)
        with self.assertRaises(PolicyError): self.c.execute(self.t)
        self.c.review(self.t, "qa", False, "defect")
        with self.assertRaises(PolicyError): self.c.execute(self.t)
        self.assertEqual(self.c.snapshot()["projects"][0]["spent"], 6)

    def test_missing_connection_and_pause(self):
        self.enable()
        self.c.tools.clear()
        self.assertEqual(self.c.execute(self.t), "blocked")
        self.c.pause(self.p)
        with self.assertRaises(PolicyError): self.c.execute(self.t)

    def test_restart_and_interrupted_call(self):
        self.enable()
        self.c.db.execute("UPDATE tasks SET status='running' WHERE id=?", (self.t,))
        self.c.db.close()
        self.c = Company(self.path)
        self.assertEqual(self.c.recover_interrupted(), 1)
        self.assertEqual(self.c.snapshot()["tasks"][0]["status"], "failed")
        with self.assertRaises(PolicyError): self.c.execute(self.t)

    def test_duplicate_approval(self):
        self.enable()
        self.c.approve_local(self.p, self.digest)
        approvals = [e for e in self.c.snapshot()["events"] if e["kind"] == "proposal.approved.local"]
        self.assertEqual(len(approvals), 1)

    def test_bounded_rework(self):
        self.c.register_tool("tool", lambda _: {"artifact": "a", "evidence": "e"})
        self.enable()
        for _ in range(3):
            self.c.execute(self.t)
            self.c.review(self.t, "qa", False, "defect")
        self.assertEqual(self.c.snapshot()["tasks"][0]["status"], "failed")
        with self.assertRaises(PolicyError): self.c.execute(self.t)


if __name__ == "__main__":
    unittest.main()
