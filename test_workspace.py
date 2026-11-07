import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from core import Company, PolicyError
from workspace import setup_workspace, get_workspace, review_workspace, check_static, TOOLS
from integrations import MCPConnections
from worker import Employee
from test_quality_gate import ready_response


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.c=Company(str(self.root/'db'));self.p,self.digest=self.c.project({'title':'Synthetic local delivery fixture','authority_requested':'Local static prototype'},100)
        self.c.approve_local(self.p,self.digest)
        setup_workspace(self.c,self.p,self.root/'workspaces')
        self.w=get_workspace(self.c,self.p)
    def tearDown(self):self.c.db.close();self.tmp.cleanup()
    def test_research_or_unapproved_scope_cannot_open_product_workspace(self):
        p,d=self.c.project({'title':'Unapproved'},100)
        with self.assertRaises(PolicyError):setup_workspace(self.c,p,self.root/'workspaces')
        p,d=self.c.project({'kind':'research_mandate'},100);self.c.approve_local(p,d)
        with self.assertRaises(PolicyError):setup_workspace(self.c,p,self.root/'workspaces')
    def test_real_git_repository_paths_and_idempotency(self):
        self.w.write_file('index.html','<html><title>Fixture</title></html>')
        result=self.w.checkpoint('Synthetic local fixture')
        self.assertEqual(len(result['commit']),40)
        self.assertEqual(result['branch'],'product')
        self.assertEqual(setup_workspace(self.c,self.p,self.root/'workspaces')['status'],'existing')
        for name in ('../outside.json','.env','.git/config','/tmp/file.md','nested/../../file.html','server.exe'):
            with self.assertRaises(PolicyError):self.w.write_file(name,'fixture')
        outside=self.root/'outside.txt';outside.write_text('private fixture')
        (self.w.root/'link.txt').symlink_to(outside)
        with self.assertRaises(PolicyError):self.w.read_file('link.txt')
    def test_static_checks_refuse_oversized_operator_modified_files(self):
        (self.w.root/'index.html').write_text('x'*60001)
        with self.assertRaises(PolicyError):
            check_static(self.w,{'Bounded inspection':{'kind':'contains','path':'index.html','text':'x'}})
    def test_independent_static_qa_rejects_defect_and_accepts_repair(self):
        self.c.grant(self.p,'developer','build');self.c.grant(self.p,'qa','employee.qa');self.c.grant(self.p,'qa','workspace/inspect')
        criteria='Page has required customer action'
        task=self.c.task(self.p,'developer','qa','build',{'acceptance_criteria':[criteria]})
        report=self.root/'artifacts'/'build.md';report.parent.mkdir();report.write_text('Synthetic build fixture')
        self.c.register_tool('build',lambda _: {'artifact':str(report),'evidence':str(report)})
        self.w.write_file('index.html','<html><title>Fixture</title></html>');self.c.execute(task)
        checks={criteria:{'kind':'html','path':'index.html','ids':['submit']}}
        result=review_workspace(self.c,task,checks,self.root/'artifacts')
        self.assertFalse(result['accepted']);self.assertEqual(result['status'],'changes_requested')
        self.w.write_file('index.html','<html><title>Fixture</title><button id="submit">Submit</button></html>')
        self.c.execute(task)
        result=review_workspace(self.c,task,checks,self.root/'artifacts')
        self.assertTrue(result['accepted']);self.assertEqual(result['status'],'completed')
    def test_real_mcp_worker_writes_and_commits_local_artifact(self):
        class Model:
            def __init__(self):self.step=0
            def complete(self,instructions,history,tools):
                if instructions.startswith('Check your work before submission.'):
                    return ready_response(history)
                self.step+=1
                if self.step<3:
                    suffix='write_file' if self.step==1 else 'checkpoint'
                    name=next(t['name'] for t in tools if suffix in t['description'].lower() or
                              (suffix=='write_file' and 'create or replace' in t['description'].lower()) or
                              (suffix=='checkpoint' and 'commit permitted' in t['description'].lower()))
                    args={'path':'index.html','content':'<title>Real file, scripted fixture</title>'} if self.step==1 else {'message':'Scripted integration fixture'}
                    return {'status':'completed','output':[{'type':'function_call','name':name,'call_id':str(self.step),'arguments':json.dumps(args)}]}
                return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'Scripted model fixture; actual repository file and commit created.'}]}]}
        self.c.grant(self.p,'developer','employee.developer')
        for name in TOOLS:self.c.grant(self.p,'developer','workspace/'+name)
        task=self.c.task(self.p,'developer','qa','employee.developer',{'acceptance_criteria':['Create page']})
        async def work(payload):
            server={'name':'workspace','command':sys.executable,'args':[str(Path(__file__).parent.resolve()/'workspace_mcp_server.py'),'--db',str(self.root/'db'),'--task',task],
                    'allow_tools':{name:{'cost_units':0} for name in TOOLS}}
            async with MCPConnections([server]) as connections:
                return await Employee(self.c,task,Model(),connections,'developer',self.root/'artifacts').run(payload)
        self.c.register_tool('employee.developer',lambda payload:asyncio.run(work(payload)))
        self.assertEqual(self.c.execute(task),'awaiting_review')
        self.assertTrue((self.w.root/'index.html').is_file())
        self.assertEqual(self.w.inspect()['branch'],'product')
    def test_denied_write_retains_response_and_fixed_error_through_stdio_cleanup(self):
        class Model:
            def complete(self,instructions,history,tools):
                name=next(t['name'] for t in tools if 'Create or replace' in t['description'])
                return {'status':'completed','output':[{'type':'function_call','name':name,
                    'call_id':'denied-write','arguments':json.dumps({'path':'backend/storage.exe','content':'fixture'})}]}
        self.c.grant(self.p,'developer','employee.developer')
        self.c.grant(self.p,'developer','workspace/write_file')
        task=self.c.task(self.p,'developer','qa','employee.developer',{'acceptance_criteria':['Write fixture']})
        artifacts=self.root/'artifacts'
        async def work(payload):
            server={'name':'workspace','command':sys.executable,
                'args':[str(Path(__file__).parent.resolve()/'workspace_mcp_server.py'),'--db',str(self.root/'db'),'--task',task],
                'allow_tools':{'write_file':{'cost_units':0}}}
            async with MCPConnections([server]) as connections:
                return await Employee(self.c,task,Model(),connections,'developer',artifacts).run(payload)
        self.c.register_tool('employee.developer',lambda payload:asyncio.run(work(payload)))
        self.assertEqual(self.c.execute(task),'failed')
        row=self.c.db.execute('SELECT note FROM tasks WHERE id=?',(task,)).fetchone()
        self.assertIn('path or file type',row['note'])
        checkpoint=artifacts/(task+'.attempt-1.round-1.response.json')
        self.assertTrue(checkpoint.is_file());self.assertEqual(checkpoint.stat().st_mode & 0o777,0o600)
        response=json.loads(checkpoint.read_text())
        self.assertEqual(json.loads(response['output'][0]['arguments'])['path'],'backend/storage.exe')
    def test_registered_root_symlink_cannot_redirect_file_access(self):
        original=self.w.root
        renamed=original.with_name(original.name+'-saved')
        original.rename(renamed)
        outside=self.root/'outside-folder';outside.mkdir()
        original.symlink_to(outside,target_is_directory=True)
        with self.assertRaises(PolicyError):get_workspace(self.c,self.p)

    def test_employee_self_check_returns_to_mcp_to_repair_before_submission(self):
        class Model:
            step=0
            def complete(self,instructions,history,tools):
                if instructions.startswith('Check your work before submission.'):
                    supplied=json.loads(history[0]['content'])
                    return ready_response(history,'repaired' in supplied['deliverable'])
                self.step+=1
                if self.step in (1,3):
                    name=next(t['name'] for t in tools if 'create or replace' in t['description'].lower())
                    content='<title>Fixture</title>' if self.step==1 else '<title>Fixture</title><button id="submit">Submit</button>'
                    return {'status':'completed','output':[{'type':'function_call','name':name,
                        'call_id':str(self.step),'arguments':json.dumps({'path':'index.html','content':content})}]}
                return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text',
                    'text':'Defective scripted fixture' if self.step==2 else 'Actual file repaired; scripted fixture'}]}]}
        self.c.grant(self.p,'developer','employee.developer')
        self.c.grant(self.p,'developer','workspace/write_file')
        task=self.c.task(self.p,'developer','qa','employee.developer',{'acceptance_criteria':['Page has submit button']})
        async def work(payload):
            server={'name':'workspace','command':sys.executable,
                'args':[str(Path(__file__).parent.resolve()/'workspace_mcp_server.py'),'--db',str(self.root/'db'),'--task',task],
                'allow_tools':{'write_file':{'cost_units':0}}}
            async with MCPConnections([server]) as connections:
                return await Employee(self.c,task,Model(),connections,'developer',self.root/'artifacts').run(payload)
        self.c.register_tool('employee.developer',lambda payload:asyncio.run(work(payload)))
        self.assertEqual(self.c.execute(task),'awaiting_review')
        self.assertIn('id="submit"',self.w.read_file('index.html')['content'])
        self.assertEqual(self.c.snapshot()['projects'][0]['spent'],20)
        checks=[e for e in self.c.snapshot()['events'] if e['kind']=='employee.quality.checked']
        self.assertEqual([json.loads(e['details'])['ready'] for e in checks],[False,True])
