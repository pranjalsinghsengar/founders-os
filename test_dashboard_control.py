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
