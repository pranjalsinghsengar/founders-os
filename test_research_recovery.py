import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import Company, ToolFailure
from discovery import discover, reconcile_saved_research
from test_discovery import ScriptedModel


class ResearchRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.c=Company(str(self.root/'db'))
    def tearDown(self):
        self.c.db.close(); self.tmp.cleanup()
    def failed_formatting_fixture(self):
        class FencedModel(ScriptedModel):
            def complete(self,instructions,history,tools):
                result=super().complete(instructions,history,tools)
                if instructions.startswith('Check your work'):
                    part=result['output'][0]['content'][0]
                    part['text']='```json\n'+part['text']+'\n```'
                return result
        with patch('quality_gate.parse_check',side_effect=ToolFailure('quality_invalid_check')):
            result=discover(self.c,FencedModel(),{},self.root)
        self.assertEqual(result['status'],'failed')
        return result['research_task'],result['research_project']
    def test_recovery_uses_saved_work_without_spending_or_attempt(self):
        task,project=self.failed_formatting_fixture()
        before=self.c.db.execute('SELECT spent FROM projects WHERE id=?',(project,)).fetchone()[0]
        audit=next(self.root.glob('*.quality.json')); original=audit.read_bytes()
        self.assertTrue(reconcile_saved_research(self.c,task,self.root))
        row=self.c.db.execute('SELECT * FROM tasks WHERE id=?',(task,)).fetchone()
        self.assertEqual(row['status'],'awaiting_review');self.assertEqual(row['attempts'],1)
        output=json.loads(row['output']);self.assertTrue(Path(output['artifact']).is_file())
        self.assertEqual(self.c.db.execute('SELECT spent FROM projects WHERE id=?',(project,)).fetchone()[0],before)
        self.assertEqual(audit.read_bytes(),original)
        self.assertFalse(reconcile_saved_research(self.c,task,self.root))
    def test_pause_and_unknown_failure_do_not_recover(self):
        task,project=self.failed_formatting_fixture()
        self.c.pause(project)
        self.assertFalse(reconcile_saved_research(self.c,task,self.root))
        self.c.pause(project,False)
        self.c.event('tool.failed',task=task,failure_code='network_timeout')
        self.assertFalse(reconcile_saved_research(self.c,task,self.root))
    def test_changed_draft_or_failed_check_do_not_recover(self):
        task,project=self.failed_formatting_fixture()
        path=self.root/(task+'.draft.md');original=path.read_text();path.write_text('Changed after check')
        self.assertFalse(reconcile_saved_research(self.c,task,self.root))
        path.write_text(original)
        path=next(self.root.glob('*.check.json'));response=json.loads(path.read_text())
        part=response['output'][0]['content'][0]
        decision=json.loads(part['text'][8:-4]);decision['ready']=False
        decision['checks'][0]['passed']=False;decision['corrections']=['Fix missing evidence']
        part['text']='```json\n'+json.dumps(decision)+'\n```';path.write_text(json.dumps(response))
        self.assertFalse(reconcile_saved_research(self.c,task,self.root))
