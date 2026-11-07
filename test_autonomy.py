import base64
import json
import tempfile
import time
import os
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import Mock, patch
from core import Company, PolicyError, ToolFailure
from idea_store import create_idea
from autonomy import start_autonomy,advance_autonomy,resume_autonomy
from autonomy_service import AutonomyService
from dashboard_control import Controls
from test_discovery import ScriptedModel
from test_gmail_approval import FakeGmail

class AutonomyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.c=Company(str(self.root/'db'))
        self.idea=create_idea(self.c,'Synthetic invoice idea','Fixture, not live research','Test services')['idea']
        self.cfg={'gmail':{'founder':'founder@example.com','token_file':'fixture'}}
        self.model=ScriptedModel();self.gmail=FakeGmail();self.deliveries=[]
        self.workflow=start_autonomy(self.c,self.idea,self.cfg,research_budget=200)['workflow']
    def tearDown(self):self.c.db.close();self.tmp.cleanup()
    def advance(self):
        def deliver(project):
            self.deliveries.append(project)
            return {'status':'waiting' if len(self.deliveries)==1 else 'local_tasks_reviewed',
                    'stage':'release_blocked','note':'Fixture local tasks reviewed; deployment missing'}
        return advance_autonomy(self.c,self.workflow,self.cfg,self.root,lambda _:self.model,deliver,lambda:self.gmail)
    def to_approval(self):
        for _ in range(15):
            result=self.advance()
            if result['status']=='waiting_approval':return result
        self.fail('Did not reach approval')
    def test_known_formatting_failure_recovers_automatically_without_research_retry(self):
        class FencedModel(ScriptedModel):
            def complete(self,instructions,history,tools):
                result=super().complete(instructions,history,tools)
                if instructions.startswith('Check your work'):
                    part=result['output'][0]['content'][0]
                    part['text']='```json\n'+part['text']+'\n```'
                return result
        self.model=FencedModel()
        # Simulate the old parser refusing the saved first check.
        with patch('quality_gate.parse_check',side_effect=ToolFailure('quality_invalid_check')):
            result=self.advance()
        self.assertEqual(result['status'],'ready')
        self.assertEqual(self.model.calls,2)
        source=self.c.db.execute('SELECT research_task FROM ideas WHERE id=?',(self.idea,)).fetchone()[0]
        task=self.c.db.execute('SELECT status,attempts FROM tasks WHERE id=?',(source,)).fetchone()
        self.assertEqual(tuple(task),('awaiting_review',1))
        self.advance()
        self.assertEqual(self.c.db.execute('SELECT status FROM tasks WHERE id=?',(source,)).fetchone()[0],'completed')
    def test_automatic_idea_to_email_then_authenticated_approval_and_delivery(self):
        self.to_approval()
        self.assertEqual(self.gmail.calls,1);self.assertEqual(self.deliveries,[])
        run=self.c.db.execute('SELECT * FROM autonomy_runs WHERE id=?',(self.workflow,)).fetchone()
        request=self.c.db.execute('SELECT * FROM email_requests WHERE id=?',(run['email_request'],)).fetchone()
        self.assertEqual(self.c.db.execute('SELECT approved FROM projects WHERE id=?',(run['project'],)).fetchone()[0],0)
        reply=EmailMessage();reply['From']=self.gmail.founder;reply['To']=self.gmail.founder
        reply['Subject']='Re: Company investment approval '+request['id'];reply['In-Reply-To']=request['rfc_id']
        reply.set_content('APPROVE '+request['id']+' '+request['binding'])
        self.gmail.messages.append({'id':'reply','threadId':'thread','labelIds':['SENT'],
            'internalDate':str(int(time.time())*1000),'raw':base64.urlsafe_b64encode(reply.as_bytes()).decode()})
        self.assertEqual(self.advance()['stage'],'delivery')
        self.assertEqual(self.advance()['status'],'ready')
        self.assertEqual(self.advance()['stage'],'release_blocked')
        self.assertEqual(len(self.deliveries),2);self.assertEqual(self.gmail.calls,1)
    def test_start_is_idempotent_and_never_raises_existing_allowances(self):
        self.assertEqual(start_autonomy(self.c,self.idea,self.cfg,research_budget=999)['workflow'],self.workflow)
        self.assertEqual(self.c.db.execute('SELECT research_budget FROM autonomy_runs').fetchone()[0],200)
    def test_unapproved_product_never_starts_delivery(self):
        self.to_approval();self.advance()
        self.assertEqual(self.deliveries,[])
    def test_paused_research_stops_before_another_call(self):
        self.advance()
        project=self.c.db.execute('SELECT research_project FROM ideas WHERE id=?',(self.idea,)).fetchone()[0]
        self.c.pause(project);calls=self.model.calls
        self.assertEqual(self.advance()['status'],'blocked')
        self.assertEqual(self.model.calls,calls)
    def test_stopped_work_resumes_only_by_explicit_action(self):
        self.advance()
        project=self.c.db.execute('SELECT research_project FROM ideas WHERE id=?',(self.idea,)).fetchone()[0]
        self.c.pause(project)
        self.c.db.execute("UPDATE autonomy_runs SET enabled=0,status='disabled'")
        with self.assertRaises(PolicyError):self.advance()
        resume_autonomy(self.c,self.workflow)
        self.assertEqual(self.c.db.execute('SELECT paused FROM projects WHERE id=?',(project,)).fetchone()[0],0)
        self.assertEqual(self.advance()['status'],'ready')
    def test_uncertain_email_is_not_sent_again(self):
        self.gmail.fail=True
        for _ in range(15):
            result=self.advance()
            if result['status']=='blocked':break
        self.assertEqual(self.gmail.calls,1)
        self.assertEqual(self.c.db.execute('SELECT state FROM email_requests').fetchone()[0],'unknown')
        with self.assertRaises(PolicyError):self.advance()
        self.assertEqual(self.gmail.calls,1)
    def test_rejected_proposal_is_corrected_without_duplicate_draft(self):
        from test_discovery import message
        class Model(ScriptedModel):
            rejected=False
            def complete(self,instructions,history,tools):
                response=super().complete(instructions,history,tools)
                if instructions.startswith('You are an independent QA'):
                    assignment=json.loads(history[0]['content'])['assignment']
                    if assignment['objective'].startswith('Prepare a complete') and not self.rejected:
                        self.rejected=True
                        return message(json.dumps({'accepted':False,'note':'Fixture: clarify investment assumptions',
                            'checks':[{'criterion':c,'passed':False,'evidence':'Fixture correction required'} for c in assignment['acceptance_criteria']]}))
                return response
        self.model=Model();self.to_approval()
        drafts=self.c.db.execute("SELECT id,attempts FROM tasks WHERE tool='proposal.draft'").fetchall()
        self.assertEqual(len(drafts),1);self.assertEqual(drafts[0]['attempts'],2)
        self.assertTrue((self.root/'artifacts'/(drafts[0]['id']+'.proposal.json')).is_file())

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.db=str(root/'db');cfg=root/'config.json';cfg.write_text('{}')
        self.controls=Controls(self.db,str(cfg));self.controls.submit=Mock()
        self.service=AutonomyService(self.controls)
    def tearDown(self):self.tmp.cleanup()
    def test_no_work_without_explicit_opt_in(self):
        self.service.tick();self.controls.submit.assert_not_called()
    def test_enabled_work_is_scheduled_but_disabled_and_interrupted_work_is_not(self):
        c=Company(self.db)
        idea=create_idea(c,'Fixture','No actual research','Test')['idea']
        run=start_autonomy(c,idea,{})['workflow']
        self.service.tick();self.controls.submit.assert_called_once_with({'action':'advance-autonomy','workflow':run,'confirmed':True})
        self.controls.submit.reset_mock()
        c.db.execute("UPDATE autonomy_runs SET status='running'")
        self.service.tick();self.controls.submit.assert_not_called()
        self.assertEqual(c.db.execute('SELECT status FROM autonomy_runs').fetchone()[0],'blocked')
        c.db.execute("UPDATE autonomy_runs SET status='running',owner_pid=?",(os.getpid(),))
        self.service.tick();self.controls.submit.assert_not_called()
        self.assertEqual(c.db.execute('SELECT status FROM autonomy_runs').fetchone()[0],'running')
        c.db.execute("UPDATE autonomy_runs SET status='ready',enabled=0")
        self.service.tick();self.controls.submit.assert_not_called();c.db.close()

    def test_opted_in_chat_failure_schedules_bounded_repair_without_delivery_plan(self):
        cfg={'local_recovery_enabled':True,'employees':{'developer':{'run_cost_units':20},'repair_engineer':{'run_cost_units':20}}}
        Path(self.controls.config).write_text(json.dumps(cfg))
        c=Company(self.db)
        try:
            p,d=c.project({'title':'Founder change'},100);c.approve_local(p,d)
            c.grant(p,'developer','employee.developer');c.grant(p,'developer','workspace/read_file')
            t=c.task(p,'developer','qa','employee.developer',{'kind':'founder_change','objective':'Change UI','acceptance_criteria':['Fixture']})
            c.db.execute("UPDATE tasks SET status='failed',attempts=1 WHERE id=?",(t,))
            c.event('tool.failed',task=t,failure_code='quality_not_ready')
            self.service.tick()
            self.controls.submit.assert_called_once()
            request=self.controls.submit.call_args.args[0]
            self.assertEqual(request['action'],'run');self.assertTrue(request['confirmed'])
            self.assertEqual(c.db.execute('SELECT owner FROM tasks WHERE id=?',(request['task'],)).fetchone()[0],'repair_engineer')
            self.assertEqual(c.db.execute('SELECT attempts FROM tasks WHERE id=?',(t,)).fetchone()[0],1)
        finally:c.db.close()
