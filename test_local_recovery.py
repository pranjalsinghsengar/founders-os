import json
import tempfile
import unittest
from pathlib import Path
from core import Company
from local_recovery import recover_local


class LocalRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.c=Company(str(self.root/'db'))
        self.p,d=self.c.project({'title':'Synthetic repair'},100);self.c.approve_local(self.p,d)
        self.c.grant(self.p,'developer','employee.developer');self.c.grant(self.p,'developer','workspace/read_file')
        self.t=self.c.task(self.p,'developer','qa','employee.developer',{'objective':'Fixture','acceptance_criteria':['Fixture']})
        self.c.db.execute("UPDATE tasks SET status='failed',attempts=3 WHERE id=?",(self.t,))
        self.c.event('tool.failed',task=self.t,failure_code='quality_invalid_check')
        self.c.db.execute('CREATE TABLE installed_plans (source_task TEXT PRIMARY KEY,mapping TEXT)')
        self.c.db.execute('INSERT INTO installed_plans VALUES (?,?)',('fixture-plan',json.dumps({'build':self.t})))
        self.cfg={'local_recovery_enabled':True,'employees':{'developer':{'run_cost_units':20}}}
    def tearDown(self):self.c.db.close();self.tmp.cleanup()
    def test_exhausted_task_gets_one_audited_repair_with_same_criteria_and_dependencies(self):
        downstream=self.c.task(self.p,'qa','product_manager','employee.qa',{'dependency_tasks':[self.t]},[self.t])
        result=recover_local(self.c,self.t,self.cfg,self.root)
        self.assertEqual(result['strategy'],'repair');replacement=result['task']
        original=self.c.db.execute('SELECT status,attempts FROM tasks WHERE id=?',(self.t,)).fetchone()
        self.assertEqual(tuple(original),('failed',3))
        new=self.c.db.execute('SELECT * FROM tasks WHERE id=?',(replacement,)).fetchone()
        self.assertEqual(json.loads(new['payload'])['acceptance_criteria'],['Fixture'])
        self.assertEqual(self.c.db.execute('SELECT dependency FROM dependencies WHERE task=?',(downstream,)).fetchone()[0],replacement)
        self.assertEqual(json.loads(self.c.db.execute('SELECT mapping FROM installed_plans').fetchone()[0])['build'],replacement)
        self.assertIsNone(recover_local(self.c,self.t,self.cfg,self.root))
        self.c.db.execute("UPDATE tasks SET status='failed',attempts=max_attempts WHERE id=?",(replacement,))
        self.c.event('tool.failed',task=replacement,failure_code='quality_not_ready')
        self.assertIsNone(recover_local(self.c,replacement,self.cfg,self.root))
    def test_known_local_failure_retries_without_resetting_attempts(self):
        self.c.db.execute('UPDATE tasks SET attempts=1 WHERE id=?',(self.t,))
        self.assertEqual(recover_local(self.c,self.t,self.cfg,self.root)['strategy'],'retry')
        self.assertEqual(tuple(self.c.db.execute('SELECT status,attempts FROM tasks WHERE id=?',(self.t,)).fetchone()),('changes_requested',1))
    def test_configured_repair_employee_owns_repair_and_cannot_self_review(self):
        self.cfg['employees']['repair_engineer']={'run_cost_units':20}
        self.c.db.execute('UPDATE tasks SET attempts=1 WHERE id=?',(self.t,))
        result=recover_local(self.c,self.t,self.cfg,self.root)
        row=self.c.db.execute('SELECT owner,reviewer,tool,payload FROM tasks WHERE id=?',(result['task'],)).fetchone()
        self.assertEqual((row['owner'],row['reviewer'],row['tool']),('repair_engineer','qa','employee.repair_engineer'))
        self.assertEqual(json.loads(row['payload'])['repair_of'],self.t)
        self.assertEqual(tuple(self.c.db.execute('SELECT status,attempts FROM tasks WHERE id=?',(self.t,)).fetchone()),('failed',1))
        self.assertTrue(self.c.db.execute("SELECT 1 FROM grants WHERE role='repair_engineer' AND tool='workspace/write_file'").fetchone())
        self.assertFalse(self.c.db.execute("SELECT 1 FROM grants WHERE role='repair_engineer' AND tool LIKE 'github/%'").fetchone())
        self.c.db.execute("UPDATE tasks SET status='failed',attempts=1 WHERE id=?",(result['task'],))
        self.c.event('tool.failed',task=result['task'],failure_code='quality_not_ready')
        self.assertEqual(recover_local(self.c,result['task'],self.cfg,self.root)['strategy'],'retry')
    def test_planned_qa_recovers_but_independent_review_audit_does_not(self):
        self.cfg['employees']['qa']={'run_cost_units':10}
        self.c.grant(self.p,'qa','employee.qa');self.c.grant(self.p,'qa','workspace/write_qa_file')
        self.c.db.execute("UPDATE tasks SET owner='qa',reviewer='product_manager',tool='employee.qa',attempts=1 WHERE id=?",(self.t,))
        self.assertEqual(recover_local(self.c,self.t,self.cfg,self.root)['strategy'],'retry')
        self.c.db.execute("UPDATE tasks SET status='failed',payload=? WHERE id=?",(json.dumps({'source_task':'fixture'}),self.t))
        self.assertIsNone(recover_local(self.c,self.t,self.cfg,self.root))
    def test_opt_in_unknown_outcome_external_permissions_and_budget_are_enforced(self):
        self.assertIsNone(recover_local(self.c,self.t,{},self.root))
        self.c.event('tool.failed',task=self.t,failure_code='network_timeout')
        self.assertIsNone(recover_local(self.c,self.t,self.cfg,self.root))
        self.c.event('tool.failed',task=self.t,failure_code='quality_not_ready')
        self.c.grant(self.p,'developer','github/push')
        self.assertIsNone(recover_local(self.c,self.t,self.cfg,self.root))
        self.c.db.execute("DELETE FROM grants WHERE tool='github/push'")
        self.c.db.execute('UPDATE projects SET spent=99 WHERE id=?',(self.p,))
        self.assertIsNone(recover_local(self.c,self.t,self.cfg,self.root))
        self.assertEqual(self.c.db.execute('SELECT budget FROM projects WHERE id=?',(self.p,)).fetchone()[0],100)

    def test_founder_change_gets_bounded_specialist_repair_without_plan(self):
        self.c.db.execute('DROP TABLE installed_plans')
        payload={'kind':'founder_change','founder_prompt':'Five ideas','objective':'Five ideas','acceptance_criteria':['Fixture']}
        self.c.db.execute('UPDATE tasks SET payload=?,attempts=1 WHERE id=?',(json.dumps(payload),self.t))
        self.cfg['employees']['repair_engineer']={'run_cost_units':20}
        result=recover_local(self.c,self.t,self.cfg,self.root)
        self.assertEqual(result['strategy'],'repair')
        new=self.c.db.execute('SELECT owner,payload FROM tasks WHERE id=?',(result['task'],)).fetchone()
        self.assertEqual(new['owner'],'repair_engineer')
        self.assertEqual(json.loads(new['payload'])['founder_prompt'],'Five ideas')
        self.assertIsNone(recover_local(self.c,self.t,self.cfg,self.root))
        self.assertEqual(tuple(self.c.db.execute('SELECT status,attempts FROM tasks WHERE id=?',(self.t,)).fetchone()),('failed',1))
