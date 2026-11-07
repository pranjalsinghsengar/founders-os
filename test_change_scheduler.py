import json
import tempfile
import unittest
from pathlib import Path
from core import Company
from dashboard_control import Controls
from change_scheduler import next_change_action

class ChangeSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.cfg={'employees':{'developer':{'run_cost_units':20},'qa':{},'repair_engineer':{'run_cost_units':20}},'local_recovery_enabled':True}
        self.config=self.root/'config.json';self.config.write_text(json.dumps(self.cfg))
        self.controls=Controls(str(self.root/'db'),str(self.config));self.c=Company(str(self.root/'db'))
        self.p,d=self.c.project({'title':'Change fixture'},200);self.c.approve_local(self.p,d)
        for tool in ('employee.developer','workspace/read_file'):self.c.grant(self.p,'developer',tool)
        self.c.grant(self.p,'qa','employee.qa')
    def tearDown(self):self.c.db.close();self.tmp.cleanup()
    def request(self,autonomous=True):
        return self.controls.mutate({'action':'request-project-change','project':self.p,'prompt':'Five related ideas','autonomous':autonomous,'confirmed':autonomous})['task']
    def test_authorized_change_runs_then_reviews_then_corrects_within_attempts(self):
        task=self.request()
        self.assertEqual(next_change_action(self.c,self.cfg),{'action':'run','task':task,'confirmed':True})
        self.c.db.execute("UPDATE tasks SET status='awaiting_review',attempts=1 WHERE id=?",(task,))
        self.assertEqual(next_change_action(self.c,self.cfg)['action'],'qa')
        self.c.review(task,'qa',False,'Fix the missing result')
        self.assertEqual(next_change_action(self.c,self.cfg)['action'],'run')
        self.c.db.execute("UPDATE tasks SET status='awaiting_review',attempts=2 WHERE id=?",(task,))
        self.assertEqual(next_change_action(self.c,self.cfg)['action'],'qa')
        self.c.review(task,'qa',True,'Synthetic evidence accepted')
        self.assertIsNone(next_change_action(self.c,self.cfg))
    def test_saved_only_request_requires_authorization(self):
        with self.assertRaises(ValueError):self.controls.mutate({'action':'request-project-change','project':self.p,'prompt':'Change','autonomous':True})
        self.request(False)
        self.assertIsNone(next_change_action(self.c,self.cfg))
    def test_pause_budget_external_grants_and_attempt_limits_stop_work(self):
        task=self.request()
        for sql in ("UPDATE projects SET paused=1", "UPDATE projects SET spent=budget-1", "UPDATE tasks SET attempts=max_attempts"):
            with self.subTest(sql=sql):
                self.c.db.execute(sql)
                self.assertIsNone(next_change_action(self.c,self.cfg))
                self.c.db.execute('UPDATE projects SET paused=0,spent=0');self.c.db.execute('UPDATE tasks SET attempts=0')
        self.c.db.execute("INSERT INTO grants VALUES (?,?,?)",(self.p,'developer','external/write'))
        self.assertIsNone(next_change_action(self.c,self.cfg))
    def test_failed_review_is_not_repeated_automatically(self):
        task=self.request();self.c.db.execute("UPDATE tasks SET status='awaiting_review',attempts=1 WHERE id=?",(task,))
        audit=self.c.task(self.p,'qa','operator.qa','employee.qa',{'source_task':task,'source_attempt':1})
        self.c.db.execute("UPDATE tasks SET status='failed' WHERE id=?",(audit,))
        self.assertIsNone(next_change_action(self.c,self.cfg))

    def test_supervisor_continues_authorized_change_into_independent_review(self):
        from unittest.mock import Mock
        from autonomy_service import AutonomyService
        task=self.request()
        self.controls.submit=Mock()
        service=AutonomyService(self.controls)
        service.tick()
        self.controls.submit.assert_called_once_with({'action':'run','task':task,'confirmed':True})
        self.controls.submit.reset_mock()
        self.c.db.execute("UPDATE tasks SET status='awaiting_review',attempts=1 WHERE id=?",(task,))
        service.tick()
        self.controls.submit.assert_called_once_with({'action':'qa','task':task,'confirmed':True})
