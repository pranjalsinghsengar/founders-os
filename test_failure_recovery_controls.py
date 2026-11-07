import json
import tempfile
import unittest
from pathlib import Path
from core import Company, PolicyError
from idea_store import create_idea
from autonomy import start_autonomy,retry_autonomy,resume_autonomy,advance_autonomy
from failure_notifications import queue_blocked,send_failure
from gmail_approval import GmailError
from test_gmail_approval import FakeGmail


class FailureRecoveryControlsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.c=Company(str(self.root/'db'))
        self.idea=create_idea(self.c,'Fixture','Synthetic','Fixture market')['idea']
        self.cfg={'employees':{'developer':{'run_cost_units':20}},'gmail':{'founder':'founder@example.com','token_file':'fixture'}}
        self.workflow=start_autonomy(self.c,self.idea,self.cfg)['workflow']
        self.project,d=self.c.project({'title':'Fixture product'},100);self.c.approve_local(self.project,d)
        self.c.db.execute("UPDATE autonomy_runs SET project=?,stage='delivery',status='blocked',note='Local write failed' WHERE id=?",(self.project,self.workflow))
        self.c.grant(self.project,'developer','employee.developer');self.c.grant(self.project,'developer','workspace/write_file')
        self.task=self.c.task(self.project,'developer','qa','employee.developer',{'acceptance_criteria':['Fixture']})
        self.c.db.execute("UPDATE tasks SET status='failed',attempts=1,note='Fixture failure' WHERE id=?",(self.task,))
    def tearDown(self):self.c.db.close();self.tmp.cleanup()
    def test_budget_amendment_preserves_spend_scope_and_blocked_state(self):
        self.c.db.execute('UPDATE projects SET spent=95 WHERE id=?',(self.project,))
        result=self.c.increase_budget(self.project,100,100)
        self.assertEqual(result,{'budget':200,'remaining':105})
        self.assertEqual(self.c.db.execute('SELECT status FROM autonomy_runs WHERE id=?',(self.workflow,)).fetchone()[0],'blocked')
        with self.assertRaises(PolicyError):self.c.increase_budget(self.project,100,100)
        for amount in (True,0,-1):
            with self.assertRaises(ValueError):self.c.increase_budget(self.project,amount,200)
    def test_retry_requires_budget_and_preserves_attempt_count(self):
        self.c.db.execute('UPDATE projects SET spent=95 WHERE id=?',(self.project,))
        with self.assertRaises(PolicyError):retry_autonomy(self.c,self.workflow,self.cfg)
        self.c.increase_budget(self.project,100,100)
        self.assertEqual(retry_autonomy(self.c,self.workflow,self.cfg)['status'],'ready')
        task=self.c.db.execute('SELECT status,attempts FROM tasks WHERE id=?',(self.task,)).fetchone()
        self.assertEqual(tuple(task),('changes_requested',1))
    def test_external_grants_and_exhausted_attempts_block_retry(self):
        self.c.grant(self.project,'developer','github/push')
        with self.assertRaises(PolicyError):retry_autonomy(self.c,self.workflow,self.cfg)
        self.c.db.execute("DELETE FROM grants WHERE tool='github/push'")
        self.c.db.execute('UPDATE tasks SET attempts=max_attempts WHERE id=?',(self.task,))
        with self.assertRaises(PolicyError):retry_autonomy(self.c,self.workflow,self.cfg)
    def test_budget_stop_resumes_after_explicit_amendment_without_task_retry(self):
        self.c.db.execute("UPDATE tasks SET status='completed' WHERE id=?",(self.task,))
        self.c.db.execute("UPDATE autonomy_runs SET stage='budget' WHERE id=?",(self.workflow,))
        self.c.db.execute('UPDATE projects SET spent=budget WHERE id=?',(self.project,))
        with self.assertRaises(PolicyError):resume_autonomy(self.c,self.workflow)
        self.c.increase_budget(self.project,100,100)
        self.assertEqual(resume_autonomy(self.c,self.workflow)['status'],'ready')
        self.assertEqual(self.c.db.execute('SELECT attempts FROM tasks WHERE id=?',(self.task,)).fetchone()[0],1)
        deliveries=[]
        def delivery(project):
            deliveries.append(project)
            return {'status':'waiting'}
        result=advance_autonomy(self.c,self.workflow,self.cfg,self.root,
                               lambda _:self.fail('Recovery must not repeat research'),delivery)
        self.assertEqual(deliveries,[self.project])
        self.assertEqual((result['status'],result['stage']),('ready','delivery'))
    def test_completed_repair_allows_resume_without_erasing_original_failure(self):
        replacement=self.c.task(self.project,'developer','qa','employee.developer',{})
        self.c.db.execute("UPDATE tasks SET status='completed' WHERE id=?",(replacement,))
        self.c.db.execute('CREATE TABLE local_repairs(source_task TEXT PRIMARY KEY,replacement_task TEXT)')
        self.c.db.execute('INSERT INTO local_repairs VALUES (?,?)',(self.task,replacement))
        self.assertEqual(resume_autonomy(self.c,self.workflow)['status'],'ready')
        self.assertEqual(self.c.db.execute('SELECT status FROM tasks WHERE id=?',(self.task,)).fetchone()[0],'failed')
    def test_dashboard_marks_repaired_history_without_changing_failure_status(self):
        from dashboard_server import state
        replacement=self.c.task(self.project,'developer','qa','employee.developer',{})
        self.c.db.execute("UPDATE tasks SET status='completed' WHERE id=?",(replacement,))
        self.c.db.execute('CREATE TABLE local_repairs(source_task TEXT PRIMARY KEY,replacement_task TEXT)')
        self.c.db.execute('INSERT INTO local_repairs VALUES (?,?)',(self.task,replacement))
        path=self.root/'config.json';path.write_text(json.dumps(self.cfg))
        snapshot=state(self.root/'db',path)
        original=next(t for t in snapshot['tasks'] if t['id']==self.task)
        self.assertEqual(original['status'],'failed')
        self.assertEqual(original['recovery_status'],'repaired')
        self.assertEqual(original['superseded_by'],replacement)
    def test_failure_email_deduplicated_with_local_retry_link(self):
        with self.c.transaction():
            first=queue_blocked(self.c,self.workflow,'delivery','Local write failed')
            again=queue_blocked(self.c,self.workflow,'delivery','Local write failed')
        self.assertEqual(first,again)
        self.c.db.execute("INSERT INTO runtime_settings VALUES ('dashboard_origin','http://127.0.0.1:3011')")
        gmail=FakeGmail()
        self.assertEqual(send_failure(self.c,first,self.cfg,self.root,lambda:gmail)['status'],'sent')
        self.assertEqual(send_failure(self.c,first,self.cfg,self.root,lambda:gmail)['status'],'sent')
        self.assertEqual(gmail.calls,1)
        from gmail_approval import decode
        msg=decode(gmail.messages[0])
        self.assertIn('retry='+self.workflow,msg.get_body(preferencelist=('plain',)).get_content())
        self.assertIn('Review &amp; retry',msg.get_body(preferencelist=('html',)).get_content())
        self.assertEqual(self.c.db.execute('SELECT status FROM autonomy_runs WHERE id=?',(self.workflow,)).fetchone()[0],'blocked')
    def test_uncertain_failure_email_never_resends(self):
        with self.c.transaction():identifier=queue_blocked(self.c,self.workflow,'delivery','Fixture failure')
        gmail=FakeGmail();gmail.fail=True
        with self.assertRaises(GmailError):send_failure(self.c,identifier,self.cfg,self.root,lambda:gmail)
        self.assertEqual(send_failure(self.c,identifier,self.cfg,self.root,lambda:gmail)['status'],'unknown')
        self.assertEqual(gmail.calls,1)
