"""Actual Next.js -> Python -> SQLite/CLI verification. No providers are called."""
import http.client
import json
import os
import secrets
import signal
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from core import Company
from dashboard_server import DashboardServer,initialize

APP=Path(__file__).parent/'dashboard-next'
@unittest.skipUnless((APP/'.next/BUILD_ID').exists(),'Build dashboard-next before the bridge integration check')
class NextBridgeTests(unittest.TestCase):
 def test_real_proxy_session_actions_persistence_and_repository(self):
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ):
   os.environ.pop('OPENAI_API_KEY',None)
   root=Path(folder);db=root/'company.db';cfg=root/'company.config.json';initialize(db,cfg)
   c=Company(str(db));approved,digest=c.project({'title':'Synthetic authorized product'},100);c.approve_local(approved,digest);c.db.close()
   token=secrets.token_urlsafe(32);server=DashboardServer(db,cfg,0,bridge_token=token)
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
   env=dict(os.environ);env.pop('OPENAI_API_KEY',None)
   env.update({'COMPANY_BRIDGE_TOKEN':token,'COMPANY_API_ORIGIN':server.origin,'COMPANY_UI_ORIGIN':f'http://127.0.0.1:{port}','NEXT_TELEMETRY_DISABLED':'1'})
   process=subprocess.Popen(['node',str(APP/'node_modules/next/dist/bin/next'),'start','--hostname','127.0.0.1','--port',str(port)],cwd=APP,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
   connection=None
   try:
    cookie='';origin=f'http://127.0.0.1:{port}'
    for _ in range(50):
     try:
      connection=http.client.HTTPConnection('127.0.0.1',port,timeout=3);connection.request('GET','/api/state');r=connection.getresponse();payload=json.loads(r.read())
      if r.status==200:cookie=r.getheader('Set-Cookie').split(';')[0];break
     except (OSError,http.client.HTTPException):
      if connection:connection.close()
      time.sleep(.1)
    self.assertTrue(cookie,'Connected Next.js did not start')
    self.assertNotIn(token,json.dumps(payload));self.assertEqual(len(payload['projects']),1)
    def call(method,path,body=None,overrides=None):
     headers={'Cookie':cookie,'Origin':origin,'X-Company-UI':'1','Content-Type':'application/json'};headers.update(overrides or {})
     connection.request(method,path,json.dumps(body) if body is not None else None,headers);r=connection.getresponse();return r.status,json.loads(r.read())
    body={'action':'create-idea','title':'Persisted founder idea','market':'Local agencies','description':'Synthetic bridge verification'}
    status,_=call('POST','/api/control',body,{'Origin':'https://attacker.example'});self.assertEqual(status,403)
    status,_=call('POST','/api/control',body,{'Cookie':''});self.assertEqual(status,403)
    status,result=call('POST','/api/control',body);self.assertEqual(status,200)
    status,payload=call('GET','/api/state');self.assertEqual(payload['ideas'][0]['id'],result['idea'])
    status,_=call('POST','/api/action',{'action':'discover','market':'Test','budget':100});self.assertEqual(status,400)
    status,result=call('POST','/api/action',{'action':'workspace-init','project':approved,'grant_tools':True});self.assertEqual(status,202)
    for _ in range(100):
     _,payload=call('GET','/api/state');job=next(j for j in payload['jobs'] if j['id']==result['job'])
     if job['status'] not in ('queued','running'):break
     time.sleep(.05)
    self.assertEqual(job['status'],'succeeded')
    self.assertTrue((root/'workspaces'/'general'/approved/'.git').is_dir())
    status,repo=call('GET','/api/repository?project='+approved);self.assertEqual(status,200);self.assertEqual(repo['branch'],'product');self.assertEqual(repo['files'],[])
    status,_=call('GET','/api/repository?project='+approved+'&file=../company.config.json');self.assertEqual(status,400)
    status,result=call('POST','/api/control',{'action':'assign','project':approved,'role':'developer','reviewer':'qa','payload':{'objective':'Synthetic fixture task','acceptance_criteria':['Actual output required']},'dependencies':[]});self.assertEqual(status,200)
    source_task=result['task']
    c=Company(str(db));self.assertEqual(c.db.execute('SELECT status FROM tasks WHERE id=?',(source_task,)).fetchone()[0],'queued')
    from workspace import get_workspace
    w=get_workspace(c,approved);w.write_file('index.html','<title>Fixture</title><button id="submit">Submit</button>');w.checkpoint('Synthetic test deliverable')
    report=root/'artifacts'/'synthetic-deliverable.md';report.write_text('Synthetic worker output; real file-based QA follows.')
    c.register_tool('employee.developer',lambda _: {'artifact':str(report),'evidence':str(report)})
    self.assertEqual(c.execute(source_task),'awaiting_review');c.db.close()
    status,_=call('POST','/api/action',{'action':'qa-static','task':source_task,'checks':{}});self.assertEqual(status,400)
    status,result=call('POST','/api/action',{'action':'qa-static','task':source_task,'checks':{'Actual output required':{'kind':'html','path':'index.html','ids':['submit']}}});self.assertEqual(status,202)
    for _ in range(100):
     _,payload=call('GET','/api/state');job=next(j for j in payload['jobs'] if j['id']==result['job'])
     if job['status'] not in ('queued','running'):break
     time.sleep(.05)
    self.assertEqual(job['status'],'succeeded')
    self.assertEqual(next(t for t in payload['tasks'] if t['id']==source_task)['status'],'completed')
    synthetic_key='sk-synthetic-'+('x'*40)
    status,result=call('POST','/api/control',{'action':'configure-openai','key':synthetic_key});self.assertEqual(status,200)
    self.assertNotIn(synthetic_key,json.dumps(result));self.assertEqual((root/'.secrets/openai-key').stat().st_mode&0o777,0o600)
    _,payload=call('GET','/api/state');self.assertTrue(payload['model_credential_present']);self.assertNotIn(synthetic_key,json.dumps(payload))


   finally:
    if connection:connection.close()
    os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=10)
    server.shutdown();server.server_close();thread.join()
