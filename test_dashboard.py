import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from core import Company
from dashboard_server import DashboardServer, initialize, state, artifact, redact


class DashboardDataTests(unittest.TestCase):
    def test_init_preserves_config_and_records(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'company.db'; config=Path(folder)/'company.config.json'
            initialize(db,config)
            cfg=json.loads(config.read_text()); self.assertEqual(cfg['mcp_servers'],[])
            cfg['model']='fixture'; config.write_text(json.dumps(cfg)); before=config.read_bytes()
            c=Company(str(db)); project,_=c.project({'title':'Real record'},100); c.db.close()
            initialize(db,config)
            self.assertEqual(before,config.read_bytes())
            self.assertEqual(state(db,config)['projects'][0]['id'],project)
    def test_projection_redacts_and_omits_credentials_and_raw_output(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'db';cfg=Path(folder)/'config.json';initialize(db,cfg)
            c=Company(str(db));p,digest=c.project({'title':'A project','api_key':'private-marker','scope':'sk-fixturekey'},100)
            task=c.task(p,'dev','qa','build',{'objective':'Real objective'})
            c.db.execute('UPDATE tasks SET output=? WHERE id=?',(json.dumps({'artifact':'/tmp/safe.md','provider_response':'private-output'}),task)); c.db.close()
            payload=state(db,cfg); text=json.dumps(payload)
            self.assertNotIn('private-marker',text);self.assertNotIn('sk-fixturekey',text)
            self.assertNotIn('private-output',text);self.assertNotIn('/tmp/safe.md',text)
            self.assertEqual(payload['tasks'][0]['artifacts']['artifact'],'safe.md')
    def test_artifacts_reject_traversal_and_symlinks_and_redact_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'artifacts';root.mkdir();db=Path(folder)/'db'
            c=Company(str(db));p,_=c.project({},0);t=c.task(p,'dev','qa','tool',{})
            secret=Path(folder)/'outside.json';secret.write_text('{"api_key":"private-marker"}')
            link=root/'link.json';link.symlink_to(secret)
            c.db.execute('UPDATE tasks SET output=? WHERE id=?',(json.dumps({'artifact':str(link)}),t))
            with self.assertRaises(ValueError):artifact(db,root,t,'artifact')
            allowed=root/'report.json';allowed.write_text('{"api_key":"private-marker","note":"safe"}')
            c.db.execute('UPDATE tasks SET output=? WHERE id=?',(json.dumps({'artifact':str(allowed)}),t));c.db.close()
            result=artifact(db,root,t,'artifact');self.assertNotIn('private-marker',result['content'])
            self.assertIn('safe',result['content'])
    def test_redacts_nested_credentials(self):
        result=redact({'items':[{'refresh_token':'private','text':'Bearer fixture-token'}]})
        self.assertEqual(result['items'][0]['refresh_token'],'[redacted]')
        self.assertNotIn('fixture-token',result['items'][0]['text'])


class DashboardHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.db=self.root/'db';self.cfg=self.root/'config.json';initialize(self.db,self.cfg)
        c=Company(str(self.db));self.project,_=c.project({'title':'HTTP fixture'},100);c.db.close()
        self.server=DashboardServer(self.db,self.cfg,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        self.cookie=''
    def tearDown(self):
        self.connection.close();self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,method,path,body=None,headers=None):
        headers=dict(headers or {})
        if self.cookie:headers.setdefault('Cookie',self.cookie)
        self.connection.request(method,path,body,headers)
        r=self.connection.getresponse();raw=r.read()
        if r.getheader('Set-Cookie'):self.cookie=r.getheader('Set-Cookie').split(';')[0]
        return r,raw
    def test_state_requires_session_then_shows_real_records(self):
        r,_=self.request('GET','/api/state');self.assertEqual(r.status,403)
        r,html=self.request('GET','/');self.assertEqual(r.status,200)
        self.assertIn(b'Company OS',html);self.assertIn('HttpOnly',r.getheader('Set-Cookie'))
        r,raw=self.request('GET','/api/state');self.assertEqual(r.status,200)
        self.assertEqual(json.loads(raw)['projects'][0]['id'],self.project)
        self.assertEqual(r.getheader('Cache-Control'),'no-store')
    def test_cross_origin_and_rebinding_blocked(self):
        r,_=self.request('GET','/',headers={'Host':'attacker.example'});self.assertEqual(r.status,403)
        r,_=self.request('GET','/',headers={'Sec-Fetch-Site':'cross-site'});self.assertEqual(r.status,403)
        self.request('GET','/')
        r,_=self.request('POST','/api/pause',json.dumps({'project':self.project,'paused':True}),
            {'Origin':'https://attacker.example','X-CSRF-Token':self.server.token})
        self.assertEqual(r.status,403)
    def test_pause_requires_csrf_and_is_audited(self):
        self.request('GET','/')
        body=json.dumps({'project':self.project,'paused':True})
        r,_=self.request('POST','/api/pause',body,{'Origin':self.server.origin});self.assertEqual(r.status,403)
        r,_=self.request('POST','/api/pause',body,{'Origin':self.server.origin,'X-CSRF-Token':self.server.token})
        self.assertEqual(r.status,200)
        payload=state(self.db,self.cfg);self.assertEqual(payload['projects'][0]['paused'],1)
        self.assertEqual(payload['events'][0]['kind'],'project.pause')
        self.assertEqual(payload['tasks'],[])
    def test_no_arbitrary_file_or_execution_endpoints(self):
        self.request('GET','/')
        r,_=self.request('GET','/.secrets/gmail-client.json');self.assertEqual(r.status,404)
        r,_=self.request('GET','/../company.config.json');self.assertEqual(r.status,404)
        r,_=self.request('POST','/api/run','{}',{'Origin':self.server.origin,'X-CSRF-Token':self.server.token})
        self.assertEqual(r.status,404)
    def test_invalid_pause_type_does_not_mutate(self):
        self.request('GET','/')
        r,_=self.request('POST','/api/pause',json.dumps({'project':self.project,'paused':'false'}),
                         {'Origin':self.server.origin,'X-CSRF-Token':self.server.token})
        self.assertEqual(r.status,400)
        self.assertEqual(state(self.db,self.cfg)['projects'][0]['paused'],0)


class StartupDiagnosticTests(unittest.TestCase):
    def test_cli_reports_occupied_port_and_existing_url(self):
        import contextlib
        import errno
        import io
        import company_cli
        error = io.StringIO()
        with patch('sys.argv',['company_cli.py','dashboard','--port','8787']), \
             patch('dashboard_server.serve',side_effect=OSError(errno.EADDRINUSE,'private-system-detail')), \
             contextlib.redirect_stderr(error):
            with self.assertRaises(SystemExit) as result: company_cli.main()
        self.assertEqual(result.exception.code,1)
        self.assertIn('http://127.0.0.1:8787',error.getvalue())
        self.assertIn('--port 8788',error.getvalue())
        self.assertNotIn('private-system-detail',error.getvalue())
    def test_permission_error_is_not_reported_as_port_conflict(self):
        import errno
        from dashboard_server import startup_error
        message=startup_error(OSError(errno.EPERM,'private-detail'),8787)
        self.assertIn('Permission denied',message)
        self.assertNotIn('already in use',message)
