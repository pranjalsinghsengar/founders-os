import tempfile
import unittest
from pathlib import Path
from core import Company
from dashboard_control import Controls
from project_deletion import delete_project

class DeletionTests(unittest.TestCase):
 def test_deletion_is_scoped_and_requires_trash_confirmation(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);Controls(str(root/'db'),str(root/'config'))
   c=Company(str(root/'db'));p,_=c.project({'title':'Delete'},100);other,_=c.project({'title':'Keep'},100)
   task=c.task(p,'dev','qa','employee.dev',{})
   workspace=root/'workspaces'/'application-market'/p;workspace.mkdir(parents=True);(workspace/'code.py').write_text('fixture')
   c.db.execute('CREATE TABLE workspaces(project TEXT PRIMARY KEY REFERENCES projects(id),root TEXT)');c.db.execute('INSERT INTO workspaces VALUES (?,?)',(p,str(workspace)))
   artifacts=root/'artifacts';artifacts.mkdir();(artifacts/(task+'.report.json')).write_text('{}');(artifacts/'keep.json').write_text('{}')
   with self.assertRaises(ValueError):delete_project(c,p,root,True)
   c.db.execute("INSERT INTO trash(kind,target,title) VALUES ('project',?,'Delete')",(p,))
   with self.assertRaises(ValueError):delete_project(c,p,root)
   delete_project(c,p,root,True)
   self.assertFalse(workspace.exists());self.assertFalse((artifacts/(task+'.report.json')).exists());self.assertTrue((artifacts/'keep.json').exists())
   self.assertIsNone(c.db.execute('SELECT id FROM projects WHERE id=?',(p,)).fetchone());self.assertIsNotNone(c.db.execute('SELECT id FROM projects WHERE id=?',(other,)).fetchone());c.db.close()
 def test_active_work_and_outside_paths_are_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);Controls(str(root/'db'),str(root/'config'));c=Company(str(root/'db'));p,_=c.project({},100)
   task=c.task(p,'dev','qa','employee.dev',{});c.db.execute("INSERT INTO trash(kind,target,title) VALUES ('project',?,'Delete')",(p,))
   c.db.execute("UPDATE tasks SET status='running' WHERE id=?",(task,))
   with self.assertRaisesRegex(ValueError,'active work'):delete_project(c,p,root,True)
   c.db.execute("UPDATE tasks SET status='failed' WHERE id=?",(task,));c.db.execute('CREATE TABLE workspaces(project TEXT,root TEXT)');outside=root/p;outside.mkdir();c.db.execute('INSERT INTO workspaces VALUES (?,?)',(p,str(outside)))
   with self.assertRaisesRegex(ValueError,'outside managed'):delete_project(c,p,root,True)
   self.assertTrue(outside.exists());c.db.close()
