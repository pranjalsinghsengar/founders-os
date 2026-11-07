import json
import tempfile
import unittest
from pathlib import Path
from core import Company, PolicyError
from orchestration import validate_plan, generate_plan, install_plan, run_ready
import test_qa
from qa import run_review
from test_quality_gate import ready_response


def plan():
    return {'tasks': [
        {'key': 'build', 'role': 'developer', 'reviewer': 'qa', 'objective': 'Write result',
         'acceptance_criteria': ['Document result'], 'dependencies': []},
        {'key': 'followup', 'role': 'developer', 'reviewer': 'qa', 'objective': 'Use result',
         'acceptance_criteria': ['Document result'], 'dependencies': ['build']}]}


class Planner:
    def complete(self, *args):
        if args[0].startswith('Check your work before submission.'):
            return ready_response(args[1])
        return {'status': 'completed', 'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': json.dumps(plan())}]}]}


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = str(self.root / 'db')
        self.c = Company(self.path)
        self.p, digest = self.c.project({'scope': 'local fixture'}, 100)
        self.c.approve_local(self.p, digest)
        self.cfg = {'employees': {'developer': {}, 'qa': {}}}
        self.c.grant(self.p, 'planner', 'employee.planner')
    def tearDown(self):
        self.c.db.close()
        self.tmp.cleanup()
    def test_planned_qa_executes_but_review_audit_does_not(self):
        audit=self.c.task(self.p,'qa','operator.qa','employee.qa',{'source_task':'fixture','source_attempt':1})
        self.c.db.execute("UPDATE tasks SET status='awaiting_review' WHERE id=?",(audit,))
        assignment=self.c.task(self.p,'qa','product_manager','employee.qa',
            {'objective':'Run functional QA','acceptance_criteria':['Actual evidence']})
        executed=[]
        def execute(task):executed.append(task);return 'awaiting_review'
        actions=run_ready(self.c,self.p,execute,lambda _:self.fail('Audit must not be reviewed automatically'))
        self.assertEqual(executed,[assignment])
        self.assertEqual(actions[0]['task'],assignment)
    def reviewed_plan(self):
        result = generate_plan(self.c, self.p, Planner(), self.cfg, self.root)
        self.assertEqual(result['status'], 'awaiting_review')
        self.c.review(result['task'], 'product_manager', True, 'Fixture scope reviewed')
        return result['task']
    def test_graph_validation(self):
        for mutation in ('cycle', 'unknown', 'self_review', 'criteria', 'role'):
            p = plan()
            if mutation == 'cycle': p['tasks'][0]['dependencies'] = ['followup']
            if mutation == 'unknown': p['tasks'][0]['dependencies'] = ['absent']
            if mutation == 'self_review': p['tasks'][0]['reviewer'] = 'developer'
            if mutation == 'criteria': p['tasks'][0]['acceptance_criteria'] = []
            if mutation == 'role': p['tasks'][0]['role'] = 'unknown'
            with self.assertRaises(ValueError): validate_plan(p, self.cfg['employees'])
    def test_review_gate_and_restart_idempotency(self):
        result = generate_plan(self.c, self.p, Planner(), self.cfg, self.root)
        with self.assertRaises(PolicyError): install_plan(self.c, result['task'], self.cfg['employees'])
        self.c.review(result['task'], 'product_manager', True, 'Reviewed fixture')
        mapping = install_plan(self.c, result['task'], self.cfg['employees'])
        self.c.db.close()
        self.c = Company(self.path)
        self.assertEqual(install_plan(self.c, result['task'], self.cfg['employees']), mapping)
        self.assertEqual(len(self.c.snapshot()['tasks']), 3)
        self.assertEqual(self.c.db.execute("SELECT COUNT(*) FROM grants WHERE role='developer'").fetchone()[0], 0)
    def test_invalid_install_is_atomic(self):
        task = self.reviewed_plan()
        with self.assertRaises(ValueError): install_plan(self.c, task, {'developer': {}})
        self.assertEqual(len(self.c.snapshot()['tasks']), 1)
    def test_scheduler_qa_rework_and_dependencies(self):
        mapping = install_plan(self.c, self.reviewed_plan(), self.cfg['employees'])
        self.c.grant(self.p, 'developer', 'employee.developer')
        self.c.grant(self.p, 'qa', 'employee.qa')
        a, e = self.root / 'a.md', self.root / 'e.json'
        a.write_text('Fixture'); e.write_text('{}')
        self.c.register_tool('employee.developer', lambda _: {'artifact': str(a), 'evidence': str(e)})
        execute = self.c.execute
        reject = lambda t: run_review(self.c, t, test_qa.Model(False), self.root)
        accept = lambda t: run_review(self.c, t, test_qa.Model(True), self.root)
        self.assertEqual(len(run_ready(self.c, self.p, execute, reject)), 1)
        run_ready(self.c, self.p, execute, reject)
        run_ready(self.c, self.p, execute, accept)
        run_ready(self.c, self.p, execute, accept)
        self.assertEqual(self.c.db.execute('SELECT status FROM tasks WHERE id=?', (mapping['build'],)).fetchone()[0], 'completed')
        self.assertEqual(self.c.db.execute('SELECT status FROM tasks WHERE id=?', (mapping['followup'],)).fetchone()[0], 'awaiting_review')
        run_ready(self.c, self.p, execute, accept)
        self.assertEqual(run_ready(self.c, self.p, execute, accept), [])
    def test_failed_qa_not_repeated_automatically(self):
        install_plan(self.c, self.reviewed_plan(), self.cfg['employees'])
        self.c.grant(self.p, 'developer', 'employee.developer')
        self.c.grant(self.p, 'qa', 'employee.qa')
        a, e = self.root / 'a', self.root / 'e'
        a.write_text('fixture'); e.write_text('{}')
        self.c.register_tool('employee.developer', lambda _: {'artifact': str(a), 'evidence': str(e)})
        qa = lambda t: run_review(self.c, t, test_qa.Model(malformed=True), self.root)
        run_ready(self.c, self.p, self.c.execute, qa)
        run_ready(self.c, self.p, self.c.execute, qa)
        spent = self.c.snapshot()['projects'][0]['spent']
        self.assertEqual(run_ready(self.c, self.p, self.c.execute, qa), [])
        self.assertEqual(self.c.snapshot()['projects'][0]['spent'], spent)
    def test_pause_blocks_scheduler_and_install(self):
        task = self.reviewed_plan()
        self.c.pause(self.p)
        with self.assertRaises(PolicyError): install_plan(self.c, task, self.cfg['employees'])
        self.assertEqual(run_ready(self.c, self.p, lambda _: self.fail(), lambda _: self.fail()), [])


if __name__ == '__main__': unittest.main()
