"""Loopback-only company control centre. No paid worker or email actions."""
import json
import errno
import os
import re
import secrets
import sqlite3
import shutil
from local_ai import resolve_local_ai
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from core import Company, PolicyError
from workspace import TOOLS

STATIC = Path(__file__).parent / 'dashboard'
SENSITIVE = re.compile(r'(?i)(api[_-]?key|password|secret|access[_-]?token|refresh[_-]?token|authorization)')


def redact(value):
    if isinstance(value, dict):
        return {k: ('[redacted]' if SENSITIVE.search(k) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[redacted]', value)
        value = re.sub(r'(?i)Bearer\s+[A-Za-z0-9._-]+', 'Bearer [redacted]', value)
    return value


def parsed(value, default=None):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def local_previews(config, projects):
    result=[]
    configured=config.get('product_previews',{})
    if not isinstance(configured,dict):return result
    for project in projects:
        entry=configured.get(project['id'],{})
        if not isinstance(entry,dict):continue
        url=entry.get('url','')
        if not isinstance(url,str):continue
        try:
            parsed_url=urlsplit(url)
            if (parsed_url.scheme not in ('http','https') or
                parsed_url.hostname not in ('127.0.0.1','localhost','::1') or
                parsed_url.username or parsed_url.password or not parsed_url.port or
                any(c.isspace() for c in url)):
                continue
        except ValueError:continue
        result.append({'project':project['id'],'url':url,
                       'mode':'simulation' if entry.get('mode')=='simulation' else 'local preview'})
    return result


def state(db_path, config_path):
    with sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        trash = [dict(r) for r in db.execute('SELECT * FROM trash ORDER BY trashed_at DESC')] if 'trash' in tables else []
        projects = [dict(r) for r in db.execute('SELECT rowid AS history_sequence,* FROM projects ORDER BY rowid DESC')]
        submissions = {r['project']:r['task'] for r in db.execute('SELECT project,task FROM registered_proposals')} if 'registered_proposals' in tables else {}
        tasks = [dict(r) for r in db.execute('SELECT rowid AS history_sequence,* FROM tasks ORDER BY rowid DESC')]
        events = [dict(r) for r in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 250')]
        deps = [dict(r) for r in db.execute('SELECT * FROM dependencies')]
        grants = [dict(r) for r in db.execute('SELECT * FROM grants')]
        approvals = [dict(r) for r in db.execute('SELECT rowid AS history_sequence,* FROM email_requests ORDER BY rowid DESC')] if 'email_requests' in tables else []
        ideas = [dict(r) for r in db.execute('SELECT rowid AS history_sequence,* FROM ideas ORDER BY rowid DESC')] if 'ideas' in tables else []
        workspaces = [dict(r) for r in db.execute('SELECT project,root FROM workspaces')] if 'workspaces' in tables else []
        remotes = [dict(r) for r in db.execute('SELECT * FROM repository_remotes')] if 'repository_remotes' in tables else []
        jobs = [dict(r) for r in db.execute('SELECT rowid AS history_sequence,* FROM dashboard_jobs ORDER BY rowid DESC LIMIT 100')] if 'dashboard_jobs' in tables else []
        delivery_runs = [dict(r) for r in db.execute('SELECT project,plan_task,status,stage,note,updated_at FROM delivery_runs ORDER BY updated_at DESC,rowid DESC')] if 'delivery_runs' in tables else []
        autonomy_runs = [dict(r) for r in db.execute('SELECT * FROM autonomy_runs ORDER BY updated_at DESC,rowid DESC')] if 'autonomy_runs' in tables else []
        repairs = {r['source_task']:r['replacement_task'] for r in db.execute('SELECT source_task,replacement_task FROM local_repairs')} if 'local_repairs' in tables else {}
        for records,field,created_kind in ((tasks,'task','task.created'),(projects,'project','proposal.created'),(approvals,'request','approval.email.prepared')):
            entity="json_extract(details,'$."+field+"')"
            if field=='project':
                entity="COALESCE("+entity+",(SELECT project FROM tasks WHERE id=json_extract(events.details,'$.task')))"
            times={r['entity']:r for r in db.execute("SELECT "+entity+" AS entity,MIN(CASE WHEN kind=? THEN at END) AS created_at,MAX(at) AS updated_at FROM events GROUP BY entity",(created_kind,)) if r['entity']}
            for record in records:
                timing=times.get(record['id'])
                record['created_at']=timing['created_at'] if timing else None
                record['updated_at']=timing['updated_at'] if timing else None
        for records in (projects,tasks,approvals,ideas,jobs):
            records.sort(key=lambda r:(r.get('updated_at') or r.get('created_at') or '',r.get('history_sequence',0)),reverse=True)
    trashed_projects={r['target'] for r in trash if r['kind']=='project'}
    trashed_ideas={r['target'] for r in trash if r['kind']=='idea'}
    hidden_projects=trashed_projects|{i['research_project'] for i in ideas if i['id'] in trashed_ideas and i['research_project']}
    for task in tasks:
        task['in_trash']=task['project'] in hidden_projects
    projects=[p for p in projects if p['id'] not in hidden_projects]
    ideas=[i for i in ideas if i['id'] not in trashed_ideas]
    for workspace in workspaces:
        root=Path(workspace.pop('root'))
        try:workspace['folder']=str(root.relative_to(Path(config_path).resolve().parent/'workspaces'))
        except ValueError:workspace['folder']=root.name
    for project in projects:
        project['submission_task'] = submissions.get(project['id'])
        project['proposal'] = parsed(project['proposal'], {})
        project['title'] = project['proposal'].get('title', 'Untitled project') if isinstance(project['proposal'], dict) else 'Untitled project'
        project['kind'] = project['proposal'].get('kind', 'candidate') if isinstance(project['proposal'], dict) else 'candidate'
        project['remaining'] = project['budget'] - project['spent']
    for task in tasks:
        task['payload'] = parsed(task['payload'], {})
        if task['id'] in repairs:
            replacement=next((r for r in tasks if r['id']==repairs[task['id']]),None)
            task['superseded_by']=repairs[task['id']]
            task['recovery_status']='repaired' if replacement and replacement['status']=='completed' else 'repair_blocked' if replacement and replacement['status']=='failed' else 'repair_in_progress'
        output = parsed(task.pop('output'), {}) or {}
        # Expose identifiers, not filesystem paths or duplicated raw provider responses.
        task['artifacts'] = {kind: Path(output[kind]).name for kind in ('artifact','evidence')
                             if isinstance(output, dict) and isinstance(output.get(kind), str)}
        quality_path = Path(config_path).resolve().parent/'artifacts'/(task['id']+'.attempt-'+str(task['attempts'])+'.quality.json')
        if quality_path.is_file():
            task['artifacts']['quality'] = quality_path.name
        task['result_summary']={key:output[key] for key in ('kind','sources','verification','research_mode','quality_status') if isinstance(output,dict) and key in output}
        task['audit_task'] = task['tool'] == 'employee.qa' and bool(task['payload'].get('source_task'))
    for event in events:
        event['details'] = parsed(event['details'], {})
    cfg = json.loads(Path(config_path).read_text()) if Path(config_path).exists() else {}
    from research_modes import research_profile
    from quality_gate import quality_settings
    quality = quality_settings(cfg)
    research_profiles = [research_profile(cfg,mode) for mode in ('normal','deep')]
    configured_roles = set(cfg.get('employees', {}))
    roles = sorted(configured_roles | {t['owner'] for t in tasks} | {t['reviewer'] for t in tasks if not t['reviewer'].startswith('operator.')})
    employees = [{'role':role, 'skills':cfg.get('employees', {}).get(role, {}).get('skills', []),
                  'configured':role in configured_roles,
                  'task_ids':[t['id'] for t in tasks if t['owner'] == role]} for role in roles]
    connections = [
        {'name':'Model runtime', 'status':('configured' if resolve_local_ai('codex',cfg.get('codex_executable')) else 'missing') if cfg.get('model_runtime')=='codex_cli' else ('configured' if cfg.get('model') and not cfg['model'].startswith('REPLACE') else 'missing'),
         'detail': 'Codex CLI (local authentication)' if cfg.get('model_runtime')=='codex_cli' else 'Model: ' + str(cfg.get('model','Not selected')),
         'note':'Uses installed CLI login; research adapter unavailable' if cfg.get('model_runtime')=='codex_cli' else ('Key present in dashboard process' if os.environ.get('OPENAI_API_KEY') else 'Key absent from dashboard process; another terminal may have it')},
        {'name':'Hosted research', 'status':'missing' if cfg.get('model_runtime')=='codex_cli' else 'observed' if any(e['kind'] == 'research.response.saved' for e in events) else 'implemented',
         'detail':'CLI research evidence unavailable' if cfg.get('model_runtime')=='codex_cli' else 'OpenAI web search', 'note':'CLI research is blocked; no API fallback' if cfg.get('model_runtime')=='codex_cli' else 'Saved live responses recorded' if any(e['kind'] == 'research.response.saved' for e in events) else 'No recent response recorded'},
        {'name':'Gmail approvals', 'status':'configured' if cfg.get('gmail', {}).get('founder') and
            cfg.get('gmail', {}).get('token_file') and (Path(config_path).parent / cfg['gmail']['token_file']).is_file() else 'missing',
         'detail':'Founder OAuth approval gateway', 'note':'Local setup only; account access not validated by dashboard'},
        {'name':'Local repository','status':'configured' if workspaces else 'implemented','detail':str(len(workspaces))+' project workspaces','note':'Local task-scoped Git; remote push and deployment are not connected'},
        {'name':'GitHub repository delivery','status':'configured' if remotes else 'implemented','detail':'Explicit private repository creation, push and reconciliation','note':'Requires locally authenticated gh CLI; no remote access tested by dashboard startup'},
        {'name':'Deployment','status':'missing','detail':'No deployment adapter configured','note':'Build isolation, browser verification, hosting, health and rollback remain outstanding'},
        {'name':'Autonomous handoffs','status':'implemented','detail':'Opt-in idea workflow and automatic approval monitoring','note':'Runs while the dashboard server is running; missing integrations remain blockers'},
        {'name':'Unattended operation','status':'missing','detail':'No OS-managed worker service','note':'Dashboard scheduler must remain running; interrupted outcomes require reconciliation'},
    ]
    for server in cfg.get('mcp_servers', []):
        connections.append({'name':'MCP · ' + str(server.get('name','unnamed')),
            'status':'configured' if Path(server.get('command','')).is_file() else 'missing',
            'detail':str(len(server.get('allow_tools',{}))) + ' allowlisted tools',
            'note':'Executable presence only; connection not tested'})
    return redact({'updated_at':datetime.now(timezone.utc).isoformat(), 'projects':projects,'tasks':tasks,
                   'events':events,'dependencies':deps,'grants':grants,'approvals':approvals,'trash':trash,
                   'employees':employees,'connections':connections,'jobs':jobs,'ideas':ideas,'workspaces':workspaces,'repository_remotes':remotes,
                   'research_profiles':research_profiles,'product_previews':local_previews(cfg,projects),
                   'quality_settings':quality,
                   'delivery_runs':delivery_runs,
                   'autonomy_runs':autonomy_runs,
                   'model_credential_present':bool(os.environ.get('OPENAI_API_KEY')),'model_runtime_ready':bool(resolve_local_ai('codex',cfg.get('codex_executable'))) if cfg.get('model_runtime')=='codex_cli' else bool(os.environ.get('OPENAI_API_KEY')),'model':cfg.get('codex_model','CLI default') if cfg.get('model_runtime')=='codex_cli' else cfg.get('model'),'model_runtime':cfg.get('model_runtime','openai_api'),'supported_providers':['OpenAI Responses','Codex CLI'],
                   'allowlisted_tools':['employee.'+r for r in configured_roles]+['workspace/'+t for t in TOOLS]+[s['name']+'/'+t for s in cfg.get('mcp_servers',[]) for t in s.get('allow_tools',{})],'mode':'Local operator · controlled execution'})


def artifact(db_path, root, task_id, kind):
    if kind not in ('artifact','evidence','quality'):
        raise ValueError('Unknown artifact type')
    with sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT output,attempts FROM tasks WHERE id=?',(task_id,)).fetchone()
    if not row:
        raise ValueError('Unknown task')
    output = parsed(row[0], {}) or {}
    path = (Path(root)/(task_id+'.attempt-'+str(row[1])+'.quality.json')).resolve() if kind=='quality' else Path(output.get(kind, '')).resolve()
    if not path.is_relative_to(Path(root).resolve()) or path.suffix not in ('.md','.json','.txt') or not path.is_file():
        raise ValueError('Artifact is not accessible')
    if path.stat().st_size > 200000:
        raise ValueError('Artifact is too large for preview')
    text = path.read_text()
    if path.suffix == '.json':
        text = json.dumps(redact(json.loads(text)), indent=2)
    return {'name':path.name,'content':redact(text)}


def initialize(db_path, config_path):
    db_path, config_path = Path(db_path), Path(config_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = Company(str(db_path)); c.db.close()
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite an existing operator configuration or introduce fixture tools.
        cfg = json.loads((Path(__file__).parent/'company.config.example.json').read_text())
        cfg['mcp_servers'] = []
        with config_path.open('x') as stream:
            json.dump(cfg, stream, indent=2)
    (config_path.parent/'artifacts').mkdir(exist_ok=True)
    skills = config_path.parent/'skills'
    skills.mkdir(exist_ok=True)
    for source in (Path(__file__).parent/'skills').glob('*.md'):
        destination = skills/source.name
        if not destination.exists():
            with destination.open('x') as stream:
                stream.write(source.read_text())


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, db_path, config_path, port=8787, bridge_token=None):
        self.db_path = str(Path(db_path).resolve())
        self.config_path = str(Path(config_path).resolve())
        from local_credentials import load_local_credentials
        load_local_credentials(self.config_path)
        self.artifact_root = Path(self.config_path).parent/'artifacts'
        self.token = secrets.token_urlsafe(32)
        self.bridge_token = bridge_token
        super().__init__(('127.0.0.1',port), Handler)
        from idea_store import initialize_ideas
        c=Company(self.db_path);initialize_ideas(c);c.db.close()
        from dashboard_control import Controls
        self.controls = Controls(self.db_path,self.config_path)
        from failure_notifications import queue_blocked
        c=Company(self.db_path)
        try:
            with c.transaction():
                c.db.execute("INSERT OR REPLACE INTO runtime_settings(key,value) VALUES ('dashboard_origin',?)",('http://127.0.0.1:'+str(self.server_port),))
                for run in c.db.execute("SELECT id,stage,note FROM autonomy_runs WHERE enabled=1 AND status='blocked'").fetchall():
                    queue_blocked(c,run['id'],run['stage'],run['note'])
        finally:c.db.close()
        from autonomy_service import AutonomyService
        self.autonomy = AutonomyService(self.controls)
        self.autonomy.start()
        self.origin = 'http://127.0.0.1:' + str(self.server_port)

    def server_close(self):
        if hasattr(self,'autonomy'):self.autonomy.close()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def allowed(self):
        host = self.headers.get('Host', '')
        return host in ('127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)) and \
            self.headers.get('Sec-Fetch-Site','same-origin') not in ('cross-site','same-site')
    def bridge_authenticated(self):
        value=self.headers.get('X-Company-Bridge','')
        return bool(self.server.bridge_token and secrets.compare_digest(value,self.server.bridge_token))
    def authenticated(self):
        if self.bridge_authenticated():return True
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie',''))
            token = cookie.get('company_session')
            return token is not None and secrets.compare_digest(token.value,self.server.token)
        except Exception:
            return False
    def reply(self,status,body,content_type='application/json',session=False):
        if not isinstance(body, (bytes,str)):
            body = json.dumps(body)
        if isinstance(body,str): body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        if session:
            self.send_header('Set-Cookie','company_session=' + self.server.token + '; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if not self.allowed():
            return self.reply(403,{'error':'Local same-origin access required'})
        path = urlsplit(self.path)
        if path.path in ('/','/index.html'):
            html = (STATIC/'index.html').read_text().replace('{{csrf}}',self.server.token)
            return self.reply(200,html,'text/html; charset=utf-8',session=True)
        if path.path in ('/app.js','/style.css'):
            name = path.path[1:]
            return self.reply(200,(STATIC/name).read_bytes(), 'text/javascript; charset=utf-8' if name.endswith('.js') else 'text/css; charset=utf-8')
        if not self.authenticated():
            return self.reply(403,{'error':'Open the dashboard first'})
        try:
            if path.path == '/api/state':
                return self.reply(200,state(self.server.db_path,self.server.config_path))
            if path.path == '/api/repository':
                from workspace import get_workspace
                query=parse_qs(path.query);c=Company(self.server.db_path)
                try:
                    w=get_workspace(c,query.get('project',[''])[0])
                    name=query.get('file',[''])[0]
                    result=w.read_file(name) if name else w.inspect()
                    if name and name.endswith('.json'):
                        try:result['content']=json.dumps(redact(json.loads(result['content'])),indent=2)
                        except ValueError:pass
                    return self.reply(200,redact(result))
                finally:c.db.close()
            if path.path == '/api/artifact':
                query = parse_qs(path.query)
                return self.reply(200,artifact(self.server.db_path,self.server.artifact_root,
                    query.get('task',[''])[0],query.get('kind',[''])[0]))
            return self.reply(404,{'error':'Not found'})
        except (ValueError, OSError, sqlite3.Error, PolicyError):
            return self.reply(400,{'error':'Unable to load requested data'})
    def do_POST(self):
        expected = ('http://127.0.0.1:' + str(self.server.server_port), 'http://localhost:' + str(self.server.server_port))
        if not self.allowed() or not (self.bridge_authenticated() or (self.authenticated() and self.headers.get('Origin') in expected and secrets.compare_digest(self.headers.get('X-CSRF-Token',''), self.server.token))):
            return self.reply(403,{'error':'Local session and CSRF verification required'})
        if self.path not in ('/api/pause','/api/action','/api/control'):
            return self.reply(404,{'error':'Not found'})
        try:
            size = int(self.headers.get('Content-Length','0'))
            if not 1 <= size <= 60000: raise ValueError()
            data = json.loads(self.rfile.read(size))
            if not isinstance(data,dict):raise ValueError()
            if self.path == '/api/action':
                return self.reply(202,self.server.controls.submit(data))
            if self.path == '/api/control':
                return self.reply(200,self.server.controls.mutate(data))
            if not isinstance(data,dict) or not isinstance(data.get('project'),str) or type(data.get('paused')) is not bool:
                raise ValueError()
            c = Company(self.server.db_path)
            try:
                if not c.db.execute('SELECT 1 FROM projects WHERE id=?',(data['project'],)).fetchone():
                    raise ValueError()
                c.pause(data['project'],data['paused'])
            finally: c.db.close()
            return self.reply(200,{'ok':True})
        except ValueError as error:
            if self.path=='/api/control' and isinstance(locals().get('data'),dict) and data.get('action') in ('retry-project-change','delete-project'):
                return self.reply(400,{'error':str(error)})
            return self.reply(400,{'error':'Action rejected; check identifiers, permissions, approval and configuration'})
        except (OSError,sqlite3.Error,PolicyError):
            return self.reply(400,{'error':'Action rejected; check identifiers, permissions, approval and configuration'})


def startup_error(error, port):
    if error.errno == errno.EADDRINUSE:
        return ('Port ' + str(port) + ' is already in use.\n'
                'If your Company OS dashboard is already running, open http://127.0.0.1:' + str(port) + '\n'
                'Otherwise choose another port: company_cli.py dashboard --port ' + str(port + 1 if port < 65535 else 8787) + ' --open\n')
    if error.errno in (errno.EACCES, errno.EPERM):
        return 'Permission denied while starting the dashboard. Run from your local terminal or allow loopback server access.\n'
    return 'Unable to start dashboard. Check database/config access and valid file paths.\n'


def serve(db_path,config_path,port=8787,open_browser=False):
    initialize(db_path,config_path)
    server = DashboardServer(db_path,config_path,port)
    print('Company dashboard: ' + server.origin, flush=True)
    print('Local control centre. No workers started. Ctrl+C stops the dashboard.', flush=True)
    if open_browser:
        import webbrowser
        webbrowser.open(server.origin)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
