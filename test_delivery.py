import json
import os
import tempfile
import unittest
from pathlib import Path
from core import Company, PolicyError
from delivery import run_delivery, initialize_delivery
from qa import run_review
from test_quality_gate import ready_response, message
from workspace import get_workspace

class Model:
    def __init__(self,reject_plan=False):
        self.reject_plan=reject_plan;self.plan_calls=0;self.plan_reviews=0
    def complete(self,instructions,history,tools):
        if instructions.startswith('Check your work'):
            return ready_response(history)
        if instructions.startswith('Plan only'):
            self.plan_calls+=1
            return message(json.dumps({'tasks':[{'key':'build','role':'developer','reviewer':'qa',
                'objective':'Synthetic local static fixture, not a live product',
                'acceptance_criteria':['Page has save button'],'dependencies':[]}]}))
        inputs=json.loads(history[0]['content']);assignment=inputs['assignment']
        if assignment['objective'].startswith('Plan the approved'):
            self.plan_reviews+=1
            accepted=not self.reject_plan or self.plan_reviews>1
        else:accepted='repaired' in inputs['deliverable']
        return message(json.dumps({'accepted':accepted,'note':'Scripted independent assessment fixture',
            'checks':[{'criterion':c,'passed':accepted,'evidence':'Scripted fixture evidence'} for c in assignment['acceptance_criteria']]}))

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.c=Company(str(self.root/'db'))
        self.p,d=self.c.project({'title':'Synthetic approved local prototype','market':'Test services'},100)
        self.c.approve_local(self.p,d)
        self.cfg={'employees':{r:{'run_cost_units':1} for r in ('planner','designer','developer','product_manager','qa')},
                  'planning_cost_units':1,'quality_check_cost_units':1,'qa_run_cost_units':1}
        self.worker_calls=0
    def tearDown(self):self.c.db.close();self.tmp.cleanup()
    def run_work(self,task):
        def work(_):
            self.worker_calls+=1
            w=get_workspace(self.c,self.p)
            repaired=self.worker_calls>1
            w.write_file('index.html','<title>Fixture</title>'+('<button id="save">Save</button>' if repaired else ''))
            w.checkpoint('Synthetic local fixture')
            path=self.root/'artifacts'/(task+'.attempt-'+str(self.worker_calls)+'.md')
            path.write_text('repaired scripted fixture' if repaired else 'defective scripted fixture')
            evidence=path.with_suffix('.json');evidence.write_text(json.dumps({'fixture':True,'files':w.inspect()}))
            return {'artifact':str(path),'evidence':str(evidence)}
        self.c.register_tool('employee.developer',work,1)
        return self.c.execute(task)
    def run_delivery(self,model=None,**kwargs):
        model=model or Model()
        return run_delivery(self.c,self.p,model,self.cfg,self.root,self.run_work,
            lambda task:run_review(self.c,task,model,self.root/'artifacts',1),**kwargs)
    def test_automatic_plan_assignment_workspace_review_and_repair(self):
        result=self.run_delivery()
        self.assertEqual(result['status'],'local_tasks_reviewed')
        self.assertEqual(self.worker_calls,2)
        self.assertIn('id="save"',get_workspace(self.c,self.p).read_file('index.html')['content'])
        grants={(r['role'],r['tool']) for r in self.c.db.execute('SELECT role,tool FROM grants WHERE project=?',(self.p,))}
        self.assertIn(('planner','employee.planner'),grants)
        self.assertIn(('developer','workspace/write_file'),grants)
        self.assertIn(('qa','employee.qa'),grants)
        self.assertNotIn(('qa','workspace/write_file'),grants)
        self.assertTrue(all(not tool.startswith('github/') for _,tool in grants))
        self.assertEqual(result['stage'],'release_blocked')
    def test_known_worker_failure_repairs_automatically_without_founder_retry(self):
        from core import ToolFailure
        self.cfg['local_recovery_enabled']=True
        first=True
        def execute(task):
            nonlocal first
            if first:
                first=False
                def failed(_):raise ToolFailure('quality_not_ready')
                self.c.register_tool('employee.developer',failed,1)
                return self.c.execute(task)
            return self.run_work(task)
        model=Model()
        result=run_delivery(self.c,self.p,model,self.cfg,self.root,execute,
            lambda task:run_review(self.c,task,model,self.root/'artifacts',1))
        self.assertEqual(result['status'],'local_tasks_reviewed')
        self.assertTrue(any(a['action']=='automatic_recovery' for a in result['actions']))
        self.assertEqual(self.c.db.execute("SELECT attempts FROM tasks WHERE tool='employee.developer'").fetchone()[0],3)
    def test_unimplemented_pilot_handoff_stops_before_paid_execution(self):
        class PilotModel(Model):
            def complete(self,instructions,history,tools):
                response=super().complete(instructions,history,tools)
                if instructions.startswith('Plan only'):
                    part=response['output'][0]['content'][0];graph=json.loads(part['text'])
                    graph['tasks'].append({'key':'pilot','role':'product_manager','reviewer':'qa',
                        'objective':'Manage pilot deployment and collect real usage metrics',
                        'acceptance_criteria':['Executed pilot evidence'],'dependencies':['build']})
                    part['text']=json.dumps(graph)
                return response
        result=self.run_delivery(PilotModel())
        self.assertEqual(result['stage'],'pilot_integration')
        row=self.c.db.execute("SELECT status,attempts FROM tasks WHERE tool='employee.product_manager'").fetchone()
        self.assertEqual(tuple(row),('queued',0))
    def test_rejected_plan_corrects_same_task_and_preserves_first_artifact(self):
        model=Model(reject_plan=True);result=self.run_delivery(model)
        self.assertEqual(result['status'],'local_tasks_reviewed')
        self.assertEqual(model.plan_calls,2)
        rows=self.c.db.execute("SELECT id,attempts FROM tasks WHERE tool='employee.planner'").fetchall()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['attempts'],2)
        self.assertTrue((self.root/'artifacts'/(rows[0]['id']+'.plan.json')).is_file())
    def test_resume_continues_existing_plan_without_duplicate_assignment(self):
        first=self.run_delivery(max_actions=3)
        self.assertEqual(first['status'],'waiting')
        count=self.c.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
        second=self.run_delivery()
        self.assertEqual(second['status'],'local_tasks_reviewed')
        self.assertEqual(self.c.db.execute("SELECT COUNT(*) FROM tasks WHERE tool='employee.planner'").fetchone()[0],1)
        self.assertEqual(self.c.db.execute("SELECT COUNT(*) FROM tasks WHERE tool='employee.developer'").fetchone()[0],1)
        self.assertGreaterEqual(self.c.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],count)
    def test_pause_requires_explicit_resume(self):
        self.c.pause(self.p)
        with self.assertRaises(PolicyError):self.run_delivery()
        self.assertEqual(self.run_delivery(resume=True,max_actions=1)['status'],'waiting')
    def test_unapproved_and_research_cannot_get_delivery_grants(self):
        self.c.db.execute('UPDATE projects SET approved=0 WHERE id=?',(self.p,))
        with self.assertRaises(PolicyError):self.run_delivery()
        self.c.db.execute('UPDATE projects SET approved=1,proposal=? WHERE id=?',(json.dumps({'kind':'research_mandate'}),self.p))
        with self.assertRaises(PolicyError):self.run_delivery()
        self.assertEqual(self.c.db.execute('SELECT COUNT(*) FROM grants').fetchone()[0],0)
    def test_budget_exhaustion_stops_without_extra_worker_calls(self):
        self.c.db.execute('UPDATE projects SET budget=3 WHERE id=?',(self.p,))
        result=self.run_delivery()
        self.assertEqual(result['stage'],'budget');self.assertEqual(self.worker_calls,0)
        self.assertEqual(self.c.db.execute('SELECT budget FROM projects WHERE id=?',(self.p,)).fetchone()[0],3)
    def test_live_delivery_run_cannot_overlap(self):
        initialize_delivery(self.c)
        self.c.db.execute("INSERT INTO delivery_runs(project,status,stage,note,owner_pid) VALUES (?,'running','planning','fixture',?)",(self.p,os.getpid()))
        with self.assertRaises(PolicyError):self.run_delivery()
