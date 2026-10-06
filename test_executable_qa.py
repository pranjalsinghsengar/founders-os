import json
import sys
import unittest
import test_qa
from executable_qa import run_executable_review
from core import PolicyError


class ExecutableQATests(unittest.TestCase):
    setUp = test_qa.QATests.setUp
    tearDown = test_qa.QATests.tearDown
    status = test_qa.QATests.status
    def checks(self, code):
        return {'Document result': {'command': [sys.executable, '-c', code], 'cwd': str(self.root)}}
    def test_real_command_accepts(self):
        result = run_executable_review(self.c, self.t, self.checks('assert 1 + 1 == 2'), self.root)
        self.assertTrue(result['accepted'])
        self.assertEqual(self.status(), 'completed')
    def test_real_command_rejects_and_rework(self):
        result = run_executable_review(self.c, self.t, self.checks('raise SystemExit(1)'), self.root)
        self.assertFalse(result['accepted'])
        self.assertEqual(self.status(), 'changes_requested')
    def test_uncovered_criteria_blocked(self):
        with self.assertRaises(PolicyError): run_executable_review(self.c, self.t, {}, self.root)
        self.assertEqual(self.status(), 'awaiting_review')
    def test_output_and_credentials_not_saved(self):
        result = run_executable_review(self.c, self.t,
            self.checks('import os; assert "OPENAI_API_KEY" not in os.environ; print("secret-output-marker")'), self.root)
        report = (self.root / (result['review_task'] + '.qa.json')).read_text()
        self.assertNotIn('secret-output-marker', report)
        self.assertIn('output_sha256', report)
    def test_timeout_rejects(self):
        checks = self.checks('import time; time.sleep(2)')
        checks['Document result']['timeout_seconds'] = 1
        result = run_executable_review(self.c, self.t, checks, self.root)
        self.assertFalse(result['accepted'])
