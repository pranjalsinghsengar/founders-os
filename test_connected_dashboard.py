import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from core import Company
from dashboard_server import DashboardServer,initialize,state
from dashboard_control import Controls
from idea_store import create_idea,idea_by_id
from discovery import discover
from test_quality_gate import ready_response
from workspace import setup_workspace,get_workspace

class ConnectedTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.db=self.root/'db';self.config=self.root/'config.json';initialize(self.db,self.config)
  self.server=DashboardServer(self.db,self.config,0,bridge_token='private-fixture-bridge')
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  self.http=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
 def tearDown(self):self.http.close();self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def call(self,method,path,body=None,token='private-fixture-bridge'):
  headers={'X-Company-Bridge':token}
  if body is not None:headers['Content-Type']='application/json';body=json.dumps(body)
  self.http.request(method,path,body,headers);r=self.http.getresponse();return r.status,json.loads(r.read())
 def test_private_bridge_rejects_bad_token(self):
  status,_=self.call('GET','/api/state',token='wrong');self.assertEqual(status,403)
  status,payload=self.call('GET','/api/state');self.assertEqual(status,200);self.assertNotIn('private-fixture-bridge',json.dumps(payload))
 def test_real_idea_creation_persists_across_connections(self):
  status,result=self.call('POST','/api/control',{'action':'create-idea','title':'Test founder idea','market':'Local services','description':'Explicitly synthetic verification'})
  self.assertEqual(status,200)
  c=Company(str(self.db));idea=idea_by_id(c,result['idea']);c.db.close();self.assertEqual(idea['title'],'Test founder idea')
  status,payload=self.call('GET','/api/state');self.assertEqual(payload['ideas'][0]['id'],result['idea'])
  self.assertEqual(payload['projects'],[])
 def test_real_workspace_file_access_refuses_outside_and_hidden_files(self):
  c=Company(str(self.db));p,d=c.project({'title':'Synthetic approved product'},100);c.approve_local(p,d);setup_workspace(c,p,self.root/'workspaces');w=get_workspace(c,p);w.write_file('index.html','<title>Actual fixture file</title>');w.checkpoint('Fixture checkpoint');c.db.close()
  status,payload=self.call('GET','/api/repository?project='+p);self.assertEqual(status,200);self.assertEqual(payload['files'][0]['path'],'index.html')
  status,payload=self.call('GET','/api/repository?project='+p+'&file=index.html');self.assertEqual(payload['content'],'<title>Actual fixture file</title>')
  for name in ('../config.json','.git/config'):
   status,_=self.call('GET','/api/repository?project='+p+'&file='+name);self.assertEqual(status,400)
 def test_unconfirmed_research_never_queues_provider_work(self):
  status,_=self.call('POST','/api/action',{'action':'discover','market':'Test market','budget':100});self.assertEqual(status,400)
  self.assertEqual(state(self.db,self.config)['jobs'],[])
 def test_idea_research_focus_and_linkage_with_scripted_model(self):
  c=Company(str(self.db));identifier=create_idea(c,'Founder booking idea','Research flaws and demand','Local studios')['idea'];idea=idea_by_id(c,identifier)
  class Model:
   def complete(self,instructions,history,tools):return ready_response(history)
   def research(self,instructions,history,max_search_calls):
    self.context=json.dumps(history)
    return {'status':'completed','output':[{'type':'web_search_call','status':'completed','action':{'sources':[{'url':'https://example.com/a'},{'url':'https://example.org/b'},{'url':'https://example.net/c'}]}},{'type':'message','content':[{'type':'output_text','text':'Scripted fixture, not live research.'}]}]}
  model=Model();result=discover(c,model,{'research_cost_units':1},self.root/'artifacts',100,idea['market'],idea=idea)
  self.assertIn('Founder booking idea',model.context)
  saved=idea_by_id(c,identifier);self.assertEqual(saved['research_task'],result['research_task'])
  self.assertEqual(result['status'],'awaiting_review');self.assertEqual(c.db.execute('SELECT count(*) FROM projects WHERE approved=0').fetchone()[0],0);c.db.close()
