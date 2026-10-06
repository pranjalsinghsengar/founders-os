import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import Company, PolicyError
from discovery import discover, draft_proposal, register_proposal, research_cycle, SECTIONS
from integrations import OpenAIResponses
from test_gmail_approval import FakeGmail
from test_quality_gate import ready_response

URLS = ['https://example.com/one','https://example.com/two','https://example.com/three']


def message(text):
    return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':text}]}]}


class ScriptedModel:
    def __init__(self, no_sources=False, reject=False):
        self.no_sources, self.reject = no_sources, reject
        self.calls = 0
    def research(self,*args):
        self.calls += 1
        result = message('Synthetic research fixture. No actual research.')
        result['output'].insert(0,{'type':'web_search_call','status':'completed','action':{'sources':
            [] if self.no_sources else [{'url':u} for u in URLS]}})
        return result
    def complete(self,instructions,history,tools):
        self.calls += 1
        if instructions.startswith('Check your work before submission.'):
            return ready_response(history)
        if instructions.startswith('Prepare a founder'):
            proposal = {key:'Synthetic fixture; no observed customer demand' for key in SECTIONS}
            proposal['title'] = 'Synthetic proposal fixture'
            proposal['evidence'] = [{'url':URLS[0],'claim':'Synthetic fixture claim'}]
            return message(json.dumps(proposal))
        assignment = json.loads(history[0]['content'])['assignment']
        return message(json.dumps({'accepted':not self.reject,'note':'Scripted independent review fixture',
            'checks':[{'criterion':c,'passed':not self.reject,'evidence':'Fixture evidence'}
                      for c in assignment['acceptance_criteria']]}))


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.c = Company(str(self.root/'db'))
        self.model = ScriptedModel()
    def tearDown(self):
        self.c.db.close(); self.tmp.cleanup()
    def test_full_cycle_registers_unapproved_product_and_emails(self):
        gmail = FakeGmail()
        result = research_cycle(self.c,self.model,{},self.root,gmail=gmail)
        self.assertEqual(result['status'],'awaiting_founder_approval')
        self.assertEqual(result['email_status'],'sent')
        self.assertEqual(self.model.calls,6)
        self.assertEqual(gmail.calls,1)
        project = self.c.db.execute('SELECT * FROM projects WHERE id=?',(result['candidate']['project'],)).fetchone()
        self.assertEqual(project['approved'],0)
        self.assertEqual(project['spent'],0)
        self.assertEqual(self.c.db.execute('SELECT COUNT(*) FROM grants WHERE project=?',(project['id'],)).fetchone()[0],0)
        prior = register_proposal(self.c,result['proposal_task'],100)
        self.assertEqual(prior,result['candidate'])
        self.assertEqual(len(self.c.snapshot()['projects']),2)
    def test_missing_sources_fails_without_draft(self):
        result = discover(self.c,ScriptedModel(no_sources=True),{},self.root)
        self.assertEqual(result['status'],'failed')
        with self.assertRaises(PolicyError): draft_proposal(self.c,result['research_task'],self.model,{},self.root)
    def test_review_rejection_stops_cycle(self):
        model = ScriptedModel(reject=True)
        gmail = FakeGmail()
        result = research_cycle(self.c,model,{},self.root,gmail=gmail)
        self.assertEqual(result['status'],'research_review_blocked')
        self.assertEqual(model.calls,3)
        self.assertEqual(gmail.calls,0)
        self.assertEqual(len(self.c.snapshot()['projects']),1)
    def test_budget_preflight_prevents_calls(self):
        with self.assertRaises(ValueError): research_cycle(self.c,self.model,{},self.root,budget=1)
        self.assertEqual(self.model.calls,0)
        self.assertEqual(len(self.c.snapshot()['projects']),0)
    def test_draft_registration_requires_review_and_exact_sources(self):
        result = discover(self.c,self.model,{},self.root)
        with self.assertRaises(PolicyError): draft_proposal(self.c,result['research_task'],self.model,{},self.root)
        self.c.review(result['research_task'],'product_manager',True,'Synthetic fixture review')
        draft = draft_proposal(self.c,result['research_task'],self.model,{},self.root)
        with self.assertRaises(PolicyError): register_proposal(self.c,draft['proposal_task'],100)
        self.c.review(draft['proposal_task'],'qa',True,'Synthetic fixture review')
        row = self.c.db.execute('SELECT output FROM tasks WHERE id=?',(draft['proposal_task'],)).fetchone()
        output = json.loads(row['output'])
        output['proposal']['evidence'][0]['url']='https://invented.example/source'
        self.c.db.execute('UPDATE tasks SET output=? WHERE id=?',(json.dumps(output),draft['proposal_task']))
        with self.assertRaises(ValueError): register_proposal(self.c,draft['proposal_task'],100)
    def test_api_uses_bounded_required_search_and_requests_sources(self):
        with patch.dict('os.environ',{'OPENAI_API_KEY':'synthetic-test-key'}):
            model = OpenAIResponses('fixture-model')
        with patch('integrations.urllib.request.urlopen') as opened:
            opened.return_value.__enter__.return_value.read.return_value = b'{"status":"completed"}'
            model.research('fixture',[],3)
            payload = json.loads(opened.call_args.args[0].data)
            self.assertEqual(payload['tools'],[{'type':'web_search'}])
            self.assertEqual(payload['max_tool_calls'],3)
            self.assertEqual(payload['tool_choice'],'required')
            self.assertEqual(payload['include'],['web_search_call.action.sources'])
            self.assertFalse(payload['store'])


class DiscoveryFailureTests(unittest.TestCase):
    def test_response_checkpoint_saved_before_validation_and_reason_returned(self):
        with tempfile.TemporaryDirectory() as folder:
            c = Company(str(Path(folder)/'db'))
            try:
                result = discover(c,ScriptedModel(no_sources=True),{},folder)
                self.assertEqual(result['status'],'failed')
                self.assertIn('fewer than three',result['reason'])
                self.assertTrue((Path(folder)/(result['research_task']+'.response.json')).exists())
                events = [json.loads(e['details']) for e in c.snapshot()['events'] if e['kind']=='tool.failed']
                self.assertEqual(events[0]['failure_code'],'insufficient_sources')
            finally:
                c.db.close()


class ResearchReworkTests(unittest.TestCase):
    def test_deep_profile_persists_and_rework_inherits_mode(self):
        class Model(ScriptedModel):
            def research(self, *args):
                self.context = json.loads(args[1][0]['content'])
                self.search_limit = args[2]
                return super().research(*args)
        with tempfile.TemporaryDirectory() as folder:
            c = Company(str(Path(folder)/'db'))
            try:
                model = Model()
                first = discover(c,model,{},folder,budget=150,research_mode='deep')
                self.assertEqual(model.search_limit,8)
                self.assertEqual(model.context['research_profile']['mode'],'deep')
                c.review(first['research_task'],'product_manager',False,'More relevant evidence needed')
                discover(c,model,{},folder,rework_task=first['research_task'])
                self.assertEqual(model.context['research_profile']['mode'],'deep')
                self.assertEqual(c.snapshot()['projects'][0]['spent'],130)
            finally: c.db.close()

    def test_invalid_or_unaffordable_deep_profile_creates_no_work(self):
        with tempfile.TemporaryDirectory() as folder:
            c = Company(str(Path(folder)/'db'))
            try:
                model = ScriptedModel()
                for mode,budget in (('invalid',100),('deep',30)):
                    with self.assertRaises(ValueError):
                        discover(c,model,{},folder,budget=budget,research_mode=mode)
                self.assertEqual(model.calls,0)
                self.assertEqual(c.snapshot()['projects'],[])
            finally: c.db.close()
    def test_rework_reuses_task_feedback_and_preserves_original_artifacts(self):
        class Model(ScriptedModel):
            def research(self, *args):
                self.last_context = json.loads(args[1][0]['content'])
                return super().research(*args)
        with tempfile.TemporaryDirectory() as folder:
            c = Company(str(Path(folder)/'db'))
            try:
                model = Model()
                first = discover(c,model,{},folder)
                task = first['research_task']
                original = c.db.execute('SELECT output FROM tasks WHERE id=?',(task,)).fetchone()[0]
                original_path = Path(json.loads(original)['artifact'])
                original_contents = original_path.read_bytes()
                c.review(task,'product_manager',False,'Cite independent sources for each problem')
                result = discover(c,model,{},folder,rework_task=task)
                self.assertEqual(result['research_task'],task)
                self.assertEqual(result['research_project'],first['research_project'])
                self.assertEqual(result['status'],'awaiting_review')
                self.assertEqual(model.last_context['review_feedback'],'Cite independent sources for each problem')
                row = c.db.execute('SELECT * FROM tasks WHERE id=?',(task,)).fetchone()
                self.assertEqual(row['attempts'],2)
                self.assertIn('.attempt-2.md',json.loads(row['output'])['artifact'])
                self.assertEqual(original_path.read_bytes(),original_contents)
                self.assertEqual(len(c.snapshot()['projects']),1)
                self.assertEqual(c.snapshot()['projects'][0]['spent'],70)
                self.assertEqual(c.snapshot()['projects'][0]['budget'],100)
            finally: c.db.close()
    def test_rework_rejects_wrong_state_and_respects_pause(self):
        with tempfile.TemporaryDirectory() as folder:
            c = Company(str(Path(folder)/'db'))
            try:
                model = ScriptedModel()
                result = discover(c,model,{},folder)
                with self.assertRaises(PolicyError): discover(c,model,{},folder,rework_task=result['research_task'])
                c.review(result['research_task'],'product_manager',False,'Needs sources')
                c.pause(result['research_project'])
                with self.assertRaises(PolicyError): discover(c,model,{},folder,rework_task=result['research_task'])
                self.assertEqual(model.calls,2)
            finally: c.db.close()
