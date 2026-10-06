import json
import tempfile
import unittest
from pathlib import Path
from core import Company
from quality_gate import QualityGate

def message(text):
    return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':text}]}]}

def ready_response(history, ready=True):
    assignment = json.loads(history[0]['content'])['assignment']
    return message(json.dumps({'ready':ready,
        'checks':[{'criterion':c,'passed':ready,'evidence':'Explicit scripted self-check fixture'}
                  for c in assignment['acceptance_criteria']],
        'corrections':[] if ready else ['Add the missing supported cost assumptions']}))

class QualityGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.c=Company(str(self.root/'db'))
        self.p,d=self.c.project({'title':'Synthetic quality fixture'},100)
        self.c.approve_local(self.p,d);self.c.grant(self.p,'researcher','research')
        self.assignment={'acceptance_criteria':['Explain supported costs']}
        self.t=self.c.task(self.p,'researcher','qa','research',self.assignment)
    def tearDown(self):self.c.db.close();self.tmp.cleanup()
    def execute(self, model, budget=None):
        if budget is not None:self.c.db.execute('UPDATE projects SET budget=? WHERE id=?',(budget,self.p))
        def work(_):
            text,audit=QualityGate(self.c,self.t,model,self.root).improve(self.assignment,'Incomplete fixture',{'fixture':True})
            artifact=self.root/'result.md';artifact.write_text(text)
            return {'artifact':str(artifact),'evidence':audit}
        self.c.register_tool('research',work,30)
        return self.c.execute(self.t)
    def test_revision_then_recheck_before_independent_handoff(self):
        class Model:
            calls=0
            def complete(self,instructions,history,tools):
                self.calls+=1
                if self.calls==2:return message('Revised fixture with supported costs')
                return ready_response(history,self.calls==3)
        model=Model();self.assertEqual(self.execute(model),'awaiting_review')
        self.assertEqual(model.calls,3)
        self.assertEqual(self.c.snapshot()['projects'][0]['spent'],50)
        self.assertEqual((self.root/'result.md').read_text(),'Revised fixture with supported costs')
        audit=json.loads(next(self.root.glob('*.quality.json')).read_text())
        self.assertEqual([r['phase'] for r in audit['checks_and_revisions']],['check','revision','check'])
        self.assertNotEqual(self.c.snapshot()['tasks'][0]['status'],'completed')
    def test_exhausted_revision_withholds_submission(self):
        class Model:
            def complete(self,instructions,history,tools):
                return ready_response(history,False) if instructions.startswith('Check') else message('Still incomplete fixture')
        self.assertEqual(self.execute(Model()),'failed')
        self.assertIn('bounded revision',self.c.snapshot()['tasks'][0]['note'])
        self.assertFalse(any(e['kind']=='task.submitted' for e in self.c.snapshot()['events']))
        from dashboard_server import artifact
        preview=artifact(self.root/'db',self.root,self.t,'quality')
        self.assertIn('missing supported cost assumptions',preview['content'])
    def test_budget_blocks_repair_before_provider_call(self):
        class Model:
            calls=0
            def complete(self,instructions,history,tools):
                self.calls+=1;return ready_response(history,False)
        model=Model();self.assertEqual(self.execute(model,budget=35),'failed')
        self.assertEqual(model.calls,1)
        self.assertIn('budget',self.c.snapshot()['tasks'][0]['note'])
    def test_contradictory_self_check_fails_closed(self):
        class Model:
            def complete(self,instructions,history,tools):
                result=ready_response(history,False)
                part=result['output'][0]['content'][0]
                decision=json.loads(part['text']);decision['ready']=True;part['text']=json.dumps(decision)
                return result
        self.assertEqual(self.execute(Model()),'failed')
        self.assertIn('invalid',self.c.snapshot()['tasks'][0]['note'])
    def test_pause_between_draft_and_check_prevents_call(self):
        class Model:
            def complete(self,*args):raise AssertionError('No call allowed after pause')
        def work(_):
            self.c.pause(self.p)
            return QualityGate(self.c,self.t,Model(),self.root).improve(self.assignment,'draft',{})
        self.c.register_tool('research',work)
        self.assertEqual(self.c.execute(self.t),'failed')
