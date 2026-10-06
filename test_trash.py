import json
import tempfile
import unittest
from pathlib import Path
from core import Company, PolicyError
from dashboard_control import Controls
from dashboard_server import state
from idea_store import create_idea, idea_by_id


class TrashTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.db=str(self.root/'db'); self.cfg=str(self.root/'config.json')
        Path(self.cfg).write_text('{}')
        self.controls=Controls(self.db,self.cfg)
        self.c=Company(self.db)
        self.p,d=self.c.project({'title':'Fixture product'},100)
        self.c.approve_local(self.p,d)

    def tearDown(self):
        self.c.db.close(); self.tmp.cleanup()

    def test_project_trash_preserves_state_blocks_resume_and_restores_paused(self):
        self.controls.mutate({'action':'trash','kind':'project','target':self.p})
        snapshot=state(self.db,self.cfg)
        self.assertEqual(snapshot['projects'],[])
        self.assertEqual(snapshot['trash'][0]['title'],'Fixture product')
        with self.assertRaises(PolicyError):self.c.pause(self.p,False)
        with self.assertRaises(ValueError):self.controls.submit({'action':'plan','project':self.p,'confirmed':True})
        self.controls.mutate({'action':'restore','kind':'project','target':self.p})
        self.assertEqual(state(self.db,self.cfg)['projects'][0]['paused'],1)
        self.assertEqual(state(self.db,self.cfg)['trash'],[])

    def test_idea_trash_hides_linked_research_and_blocks_research(self):
        idea=create_idea(self.c,'Fixture idea','','Services')['idea']
        self.c.db.execute('UPDATE ideas SET research_project=? WHERE id=?',(self.p,idea))
        self.controls.mutate({'action':'trash','kind':'idea','target':idea})
        self.assertEqual(state(self.db,self.cfg)['ideas'],[])
        self.assertEqual(state(self.db,self.cfg)['projects'],[])
        with self.assertRaises(PolicyError):idea_by_id(self.c,idea)
        with self.assertRaises(PolicyError):self.c.pause(self.p,False)
        self.controls.mutate({'action':'restore','kind':'idea','target':idea})
        self.assertEqual(idea_by_id(self.c,idea)['title'],'Fixture idea')
        self.assertEqual(state(self.db,self.cfg)['projects'][0]['paused'],1)

    def test_running_work_prevents_trash(self):
        task=self.c.task(self.p,'developer','qa','fixture',{})
        self.c.db.execute("UPDATE tasks SET status='running' WHERE id=?",(task,))
        with self.assertRaises(ValueError):self.controls.mutate({'action':'trash','kind':'project','target':self.p})
        self.assertEqual(self.c.db.execute('SELECT COUNT(*) FROM trash').fetchone()[0],0)
