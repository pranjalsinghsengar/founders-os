import json
import tempfile
import unittest
from pathlib import Path
from core import Company, PolicyError
from qa import run_review

class Model:
    def __init__(self, accepted=True, malformed=False):
        self.accepted, self.malformed = accepted, malformed
    def complete(self, instructions, history, tools):
        decision = {'accepted': self.accepted, 'note': 'Scripted fixture review.',
                    'checks': [{'criterion': 'Document result', 'passed': self.accepted,
                                'evidence': 'Scripted fixture evidence'}]}
        return {'status': 'completed', 'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': 'invalid' if self.malformed else json.dumps(decision)}]}]}

class QATests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.c = Company(str(self.root / 'db'))
        self.p, digest = self.c.project({}, 30)
        self.c.approve_local(self.p, digest)
        self.c.grant(self.p, 'developer', 'build')
        self.c.grant(self.p, 'qa', 'employee.qa')
        self.t = self.c.task(self.p, 'developer', 'qa', 'build',
                             {'acceptance_criteria': ['Document result']})
        a, e = self.root / 'result.md', self.root / 'evidence.json'
        a.write_text('Scripted fixture'); e.write_text('{"fixture": true}')
        self.c.register_tool('build', lambda _: {'artifact': str(a), 'evidence': str(e)})
        self.c.execute(self.t)
    def tearDown(self):
        self.c.db.close(); self.tmp.cleanup()
    def status(self):
        return self.c.db.execute('SELECT status FROM tasks WHERE id=?', (self.t,)).fetchone()[0]
    def test_accept_persists_report_and_charges_budget(self):
        result = run_review(self.c, self.t, Model(), self.root)
        self.assertEqual(self.status(), 'completed')
        self.assertTrue((self.root / (result['review_task'] + '.qa.json')).exists())
        self.assertEqual(self.c.snapshot()['projects'][0]['spent'], 10)
    def test_referenced_bug_log_contents_are_supplied_to_reviewer(self):
        from workspace import setup_workspace,get_workspace
        setup_workspace(self.c,self.p,self.root/'products')
        get_workspace(self.c,self.p).write_file('docs/qa_bug_log.md','P0: synthetic defect, resolved with executed evidence')
        (self.root/'result.md').write_text('Prioritized bugs are recorded in docs/qa_bug_log.md.')
        test=self
        class ReadDocuments(Model):
            def complete(self,instructions,history,tools):
                inputs=json.loads(history[0]['content'])
                test.assertIn('P0: synthetic defect',inputs['referenced_workspace_documents']['docs/qa_bug_log.md'])
                return super().complete(instructions,history,tools)
        self.assertEqual(run_review(self.c,self.t,ReadDocuments(),self.root)['status'],'completed')
    def test_reject_allows_rework(self):
        run_review(self.c, self.t, Model(False), self.root)
        self.assertEqual(self.status(), 'changes_requested')
        self.assertEqual(self.c.execute(self.t), 'awaiting_review')
    def test_malformed_does_not_accept(self):
        result = run_review(self.c, self.t, Model(malformed=True), self.root)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(self.status(), 'awaiting_review')
    def test_rejection_with_all_checks_passed_is_invalid(self):
        class ContradictoryModel(Model):
            def complete(self, instructions, history, tools):
                response = super().complete(instructions, history, tools)
                part = response['output'][0]['content'][0]
                decision = json.loads(part['text'])
                decision['accepted'] = False
                decision['note'] = 'All criteria passed, but require extra interviews.'
                part['text'] = json.dumps(decision)
                return response
        result = run_review(self.c, self.t, ContradictoryModel(), self.root)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(self.status(), 'awaiting_review')
    def test_paused_does_not_review(self):
        self.c.pause(self.p)
        with self.assertRaises(PolicyError): run_review(self.c, self.t, Model(), self.root)
        self.assertEqual(self.status(), 'awaiting_review')
    def test_stale_review_does_not_accept(self):
        with self.assertRaises(PolicyError):
            self.c.review(self.t, 'qa', True, 'stale', expected_output='old', expected_attempts=1)
        self.assertEqual(self.status(), 'awaiting_review')

if __name__ == '__main__': unittest.main()


class ReviewInputTests(unittest.TestCase):
    def test_research_input_omits_duplicate_response_but_keeps_provenance(self):
        from qa import review_evidence
        evidence = {'provider':'OpenAI Responses web_search','source_urls':['https://example.com'],
            'response':{'instructions':'duplicate-marker','usage':{'input_tokens':100},'output':[
                {'type':'web_search_call','action':{'sources':[{'url':'https://example.com'}]}},
                {'type':'message','content':[{'text':'duplicate-deliverable',
                    'annotations':[{'type':'url_citation','url':'https://example.com'}]}]}]}}
        compact = review_evidence(evidence)
        self.assertNotIn('duplicate-',json.dumps(compact))
        self.assertEqual(compact['source_urls'],evidence['source_urls'])
        self.assertEqual(compact['citations'][0]['url'],'https://example.com')
        self.assertEqual(len(compact['search_calls']),1)
        self.assertIn('response',evidence)
    def test_review_api_failure_returns_safe_reason_and_leaves_source_pending(self):
        from core import ToolFailure
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            c = Company(str(Path(folder)/'db'))
            try:
                project,digest = c.project({},30); c.approve_local(project,digest)
                c.grant(project,'dev','build'); c.grant(project,'qa','employee.qa')
                task = c.task(project,'dev','qa','build',{'acceptance_criteria':['Document result']})
                a,e=Path(folder)/'a.md',Path(folder)/'e.json'; a.write_text('fixture');e.write_text('{}')
                c.register_tool('build',lambda _: {'artifact':str(a),'evidence':str(e)})
                c.execute(task)
                model=Mock(); model.complete.side_effect=ToolFailure('api_rate_limit')
                result=run_review(c,task,model,folder)
                self.assertEqual(result['status'],'failed')
                self.assertIn('temporary rate limit',result['reason'])
                self.assertEqual(c.db.execute('SELECT status FROM tasks WHERE id=?',(task,)).fetchone()[0],'awaiting_review')
            finally:
                c.db.close()
