import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dashboard_control import Controls
from core import Company

class ControlTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.db=str(self.root/'db');self.cfg=str(self.root/'config.json')
  Path(self.cfg).write_text(json.dumps({'employees':{'developer':{},'qa':{}},'mcp_servers':[]}))
  self.controls=Controls(self.db,self.cfg)
 def tearDown(self):self.tmp.cleanup()
 def test_create_assign_and_permission_audit(self):
  p=self.controls.mutate({'action':'create-project','proposal':{'title':'Fixture'},'budget':10})['project']
  task=self.controls.mutate({'action':'assign','project':p,'role':'developer','reviewer':'qa','payload':{'objective':'Fixture','acceptance_criteria':['File exists']}})['task']
  self.controls.mutate({'action':'grant','project':p,'role':'developer','tool':'workspace/write_file'})
  self.controls.mutate({'action':'revoke','project':p,'role':'developer','tool':'workspace/write_file'})
  c=Company(self.db)
  self.assertEqual(c.db.execute('SELECT approved FROM projects WHERE id=?',(p,)).fetchone()[0],0)
  self.assertEqual(c.db.execute('SELECT status FROM tasks WHERE id=?',(task,)).fetchone()[0],'queued')
  self.assertEqual(c.db.execute('SELECT count(*) FROM grants').fetchone()[0],0);c.db.close()
 def test_unknown_actions_and_unconfirmed_paid_calls_rejected(self):
  for body in ({'action':'shell'},{'action':'discover'},{'action':'start-delivery','project':'--help'},{'action':'run','confirmed':True,'task':'--help'}):
   with self.assertRaises(ValueError):self.controls.submit(body)
 def test_research_mode_is_validated_and_forwarded(self):
  with self.assertRaises(ValueError):
   self.controls.submit({'action':'discover','confirmed':True,'research_mode':'arbitrary'})
  with patch('dashboard_control.threading.Thread') as thread:
   self.controls.submit({'action':'discover','confirmed':True,'research_mode':'deep','budget':150})
   argv=thread.call_args.kwargs['args'][2]
   self.assertEqual(argv[argv.index('--research-mode')+1],'deep')
 def test_serialization_and_persistent_interrupted_outcome(self):
  with patch('dashboard_control.threading.Thread'):
   self.controls.submit({'action':'doctor'})
   with self.assertRaises(ValueError):self.controls.submit({'action':'recover'})
  c=Company(self.db);c.db.execute('UPDATE dashboard_jobs SET owner_pid=NULL');c.db.close()
  Controls(self.db,self.cfg)
  c=Company(self.db);self.assertEqual(c.db.execute('SELECT status FROM dashboard_jobs').fetchone()[0],'interrupted');c.db.close()
 def test_cli_is_fixed_argv_and_logs_are_not_saved(self):
  with patch('dashboard_control.threading.Thread'):
   job=self.controls.submit({'action':'doctor'})['job']
  with patch('dashboard_control.subprocess.run') as run:
   run.return_value.returncode=0
   self.controls.run(job,'doctor',['--config',self.cfg])
   self.assertIn('company_cli.py',run.call_args.args[0][1])
   self.assertNotIn('shell',run.call_args.kwargs)
  c=Company(self.db);self.assertEqual(c.db.execute('SELECT status FROM dashboard_jobs').fetchone()[0],'succeeded');c.db.close()

 def test_another_controller_cannot_reset_or_overlap_a_live_job(self):
  with patch('dashboard_control.threading.Thread'):
   self.controls.submit({'action':'doctor'})
   other=Controls(self.db,self.cfg)
   with self.assertRaises(ValueError):other.submit({'action':'doctor'})
  c=Company(self.db);self.assertEqual(c.db.execute('SELECT status FROM dashboard_jobs').fetchone()[0],'queued');c.db.close()

 def test_change_prompt_creates_reviewed_local_task_without_starting_worker(self):
  p=self.controls.mutate({'action':'create-project','proposal':{'title':'Fixture'},'budget':100})['project']
  with self.assertRaises(ValueError):self.controls.mutate({'action':'request-project-change','project':p,'prompt':'Add dark mode'})
  c=Company(self.db);digest=c.db.execute('SELECT digest FROM projects WHERE id=?',(p,)).fetchone()[0];c.approve_local(p,digest);c.db.close()
  with patch('dashboard_control.subprocess.run') as run:
   result=self.controls.mutate({'action':'request-project-change','project':p,'prompt':'Add dark mode'})
   run.assert_not_called()
  c=Company(self.db);row=c.db.execute('SELECT * FROM tasks WHERE id=?',(result['task'],)).fetchone()
  self.assertEqual(row['status'],'queued');self.assertEqual(row['reviewer'],'qa')
  self.assertEqual(json.loads(row['payload'])['founder_prompt'],'Add dark mode')
  self.assertEqual(c.db.execute('SELECT spent FROM projects WHERE id=?',(p,)).fetchone()[0],0)
  with self.assertRaises(ValueError):self.controls.mutate({'action':'request-project-change','project':p,'prompt':' '})
  c.db.execute('UPDATE projects SET paused=1 WHERE id=?',(p,));c.db.close()
  with self.assertRaises(ValueError):self.controls.mutate({'action':'request-project-change','project':p,'prompt':'Add dark mode'})

 def test_change_retry_preserves_failed_source_and_authorizes_repair(self):
  p=self.controls.mutate({'action':'create-project','proposal':{'title':'Retry'},'budget':100})['project']
  c=Company(self.db);digest=c.db.execute('SELECT digest FROM projects WHERE id=?',(p,)).fetchone()[0];c.approve_local(p,digest);c.db.close()
  task=self.controls.mutate({'action':'request-project-change','project':p,'prompt':'Improve form'})['task']
  c=Company(self.db);c.db.execute("UPDATE tasks SET status='failed',attempts=1 WHERE id=?",(task,));c.db.close()
  body={'action':'retry-project-change','project':p,'task':task,'confirmed':True}
  with self.assertRaises(ValueError):self.controls.mutate({**body,'confirmed':False})
  with patch('local_recovery.recover_local',return_value=None):
   with self.assertRaisesRegex(ValueError,'Retry blocked'):self.controls.mutate(body)
  def repair(company,source,config,root):
   replacement='repair-fixture'
   company.db.execute('INSERT INTO tasks(id,project,owner,reviewer,tool,payload,max_attempts) VALUES (?,?,?,?,?,?,2)',(replacement,p,'developer','qa','employee.developer',json.dumps({'kind':'founder_change','repair_of':source})))
   return {'task':replacement,'strategy':'repair'}
  with patch('local_recovery.recover_local',side_effect=repair):result=self.controls.mutate(body)
  c=Company(self.db)
  self.assertEqual(c.db.execute('SELECT status,attempts FROM tasks WHERE id=?',(task,)).fetchone()[:],('failed',1))
  payload=json.loads(c.db.execute('SELECT payload FROM tasks WHERE id=?',(result['task'],)).fetchone()[0]);self.assertTrue(payload['autonomous']);c.db.close()

 def test_cli_failure_manual_retry_preserves_attempts_and_limits(self):
  p=self.controls.mutate({'action':'create-project','proposal':{'title':'CLI retry'},'budget':100})['project']
  c=Company(self.db);digest=c.db.execute('SELECT digest FROM projects WHERE id=?',(p,)).fetchone()[0];c.approve_local(p,digest);c.grant(p,'developer','employee.developer');c.db.close()
  task=self.controls.mutate({'action':'request-project-change','project':p,'prompt':'Improve form'})['task']
  c=Company(self.db);c.db.execute("UPDATE tasks SET status='failed',attempts=1 WHERE id=?",(task,));c.event('tool.failed',task=task,failure_code='cli_execution');c.db.close()
  result=self.controls.mutate({'action':'retry-project-change','project':p,'task':task,'confirmed':True})
  self.assertEqual(result['task'],task)
  c=Company(self.db);row=c.db.execute('SELECT status,attempts,payload FROM tasks WHERE id=?',(task,)).fetchone()
  self.assertEqual(row['status'],'changes_requested');self.assertEqual(row['attempts'],1);self.assertTrue(json.loads(row['payload'])['autonomous'])
  c.db.execute("UPDATE tasks SET status='failed',attempts=max_attempts WHERE id=?",(task,));c.db.close()
  with self.assertRaisesRegex(ValueError,'exhausted its attempts'):self.controls.mutate({'action':'retry-project-change','project':p,'task':task,'confirmed':True})
