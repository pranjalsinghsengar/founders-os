import asyncio
import tempfile
import unittest
from pathlib import Path
from core import Company
from worker import Employee


class WorkerLimitTests(unittest.TestCase):
    def test_unlimited_worker_exceeds_old_caps_but_still_obeys_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            c=Company(str(Path(directory)/'db'))
            try:
                p,d=c.project({'title':'Synthetic unlimited fixture'},100)
                c.approve_local(p,d)
                c.grant(p,'developer','employee.developer')
                c.grant(p,'developer','workspace/list_files')
                t=c.task(p,'developer','qa','employee.developer',{})
                class Connections:
                    tools={'list':{'canonical':'workspace/list_files','cost':0,'definition':{}}}
                    async def call(self,alias,args):return {'files':[]}
                class Model:
                    calls=0
                    def complete(self,instructions,history,tools):
                        self.calls+=1
                        if self.calls==25:c.pause(p,True)
                        return {'status':'completed','output':[{'type':'function_call',
                            'name':'list','arguments':'{}','call_id':str(self.calls)}]}
                model=Model()
                def work(payload):
                    return asyncio.run(Employee(c,t,model,Connections(),'developer',
                                                directory,max_rounds=None).run(payload))
                c.register_tool('employee.developer',work,20)
                self.assertEqual(c.execute(t),'failed')
                self.assertEqual(model.calls,25)
                # execute rolls back fixture mutations on failure; the paused
                # state still prevents the next tool/model call in the attempt.
                self.assertNotIn('model round limit',c.db.execute('SELECT note FROM tasks WHERE id=?',(t,)).fetchone()[0])
            finally:c.db.close()

    def test_exhaustion_preserves_evidence_and_reports_safe_specific_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            c=Company(str(Path(directory)/'db'))
            try:
                p,d=c.project({'title':'Synthetic worker limit fixture'},100)
                c.approve_local(p,d)
                c.grant(p,'developer','employee.developer')
                c.grant(p,'developer','workspace/list_files')
                t=c.task(p,'developer','qa','employee.developer',{'acceptance_criteria':['Fixture']})
                class Connections:
                    tools={'list':{'canonical':'workspace/list_files','cost':0,'definition':{}}}
                    async def call(self,alias,args):return {'files':[]}
                class Model:
                    def complete(self,instructions,history,tools):
                        return {'status':'completed','output':[{'type':'function_call',
                            'name':'list','arguments':'{}','call_id':'fixture'}]}
                def work(payload):
                    return asyncio.run(Employee(c,t,Model(),Connections(),'developer',
                                                directory,max_rounds=1).run(payload))
                c.register_tool('employee.developer',work,20)
                self.assertEqual(c.execute(t),'failed')
                row=c.db.execute('SELECT note,attempts FROM tasks WHERE id=?',(t,)).fetchone()
                self.assertIn('model round limit',row['note'])
                self.assertEqual(row['attempts'],1)
                self.assertTrue((Path(directory)/(t+'.attempt-1.round-1.response.json')).exists())
                self.assertEqual(c.db.execute('SELECT spent FROM projects WHERE id=?',(p,)).fetchone()[0],20)
                self.assertFalse(c.db.execute("SELECT 1 FROM events WHERE kind='task.submitted'").fetchone())
            finally:c.db.close()

    def test_quality_receives_final_readbacks_after_writes(self):
        from unittest.mock import patch
        import json
        with tempfile.TemporaryDirectory() as directory:
            c=Company(str(Path(directory)/'db'))
            try:
                p,d=c.project({'title':'Snapshot fixture'},100);c.approve_local(p,d)
                for tool in ('employee.developer','workspace/read_file','workspace/write_file'):c.grant(p,'developer',tool)
                t=c.task(p,'developer','qa','employee.developer',{'acceptance_criteria':['Current source']})
                class Connections:
                    content='old'
                    tools={'read':{'canonical':'workspace/read_file','cost':0,'definition':{}},'write':{'canonical':'workspace/write_file','cost':0,'definition':{}}}
                    async def call(self,alias,args):
                        if alias=='write':self.content=args['content'];return {'written':True}
                        return {'content':self.content}
                class Model:
                    calls=0
                    def complete(self,*args):
                        self.calls+=1
                        if self.calls==1:return {'status':'completed','output':[{'type':'function_call','name':'write','arguments':json.dumps({'path':'app.py','content':'final source'}),'call_id':'1'}]}
                        return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'Done'}]}]}
                with patch('worker.QualityGate') as gate:
                    gate.return_value.check.return_value={'ready':True}
                    gate.return_value.save.return_value=str(Path(directory)/'quality.json')
                    Path(directory,'quality.json').write_text('{}')
                    c.register_tool('employee.developer',lambda payload:asyncio.run(Employee(c,t,Model(),Connections(),'developer',directory).run(payload)),20)
                    self.assertEqual(c.execute(t),'awaiting_review')
                    packet=gate.return_value.check.call_args.args[2]
                    self.assertEqual(packet['current_files']['app.py']['content'],'final source')
            finally:c.db.close()
