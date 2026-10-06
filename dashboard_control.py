"""Durable, serialized dashboard actions through the trusted CLI; no arbitrary shell."""
import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from core import Company

COMMANDS = {
 'start-autonomy':('idea',), 'advance-autonomy':('workflow',), 'resume-autonomy':('workflow',),
 'start-delivery':('project',),
 'run':('task',), 'qa':('task',), 'qa-static':('task',), 'plan':('project',), 'apply-plan':('task',),
 'tick':('project',), 'discover':(), 'rework-research':('task',),
 'draft-proposal':('task',), 'register-proposal':('task',),
 'repo-create':('project',), 'repo-push':('project',), 'repo-reconcile':('project',),
 'workspace-init':('project',), 'email-proposal':('project',),
 'email-poll':(), 'email-reconcile':('request',), 'doctor':(), 'recover':(),
}
PAID={'run','qa','plan','tick','discover','rework-research','draft-proposal','start-delivery','start-autonomy','advance-autonomy','resume-autonomy'}
EXTERNAL=PAID|{'repo-create','repo-push','repo-reconcile','email-proposal','email-poll','email-reconcile'}
CONFIG={'run','qa','qa-static','plan','apply-plan','tick','discover','rework-research','draft-proposal','workspace-init','email-proposal','email-poll','email-reconcile','doctor','start-delivery'}
CONFIG.update(('start-autonomy','advance-autonomy','resume-autonomy'))

class Controls:
 def __init__(self,db,config):
  self.db=db;self.config=config;self.lock=threading.Lock()
  c=Company(db)
  from autonomy import initialize_autonomy
  initialize_autonomy(c)
  with c.transaction():
   c.db.execute('CREATE TABLE IF NOT EXISTS dashboard_jobs (id TEXT PRIMARY KEY, action TEXT, status TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, finished_at TEXT, result TEXT)')
   columns={r[1] for r in c.db.execute('PRAGMA table_info(dashboard_jobs)')}
   if 'owner_pid' not in columns:c.db.execute('ALTER TABLE dashboard_jobs ADD COLUMN owner_pid INTEGER')
   for row in c.db.execute("SELECT id,owner_pid FROM dashboard_jobs WHERE status IN ('queued','running')").fetchall():
    alive=False
    if row['owner_pid']:
     try:os.kill(row['owner_pid'],0);alive=True
     except ProcessLookupError:pass
     except PermissionError:alive=True
    if not alive:c.db.execute("UPDATE dashboard_jobs SET status='interrupted', result='Outcome unknown; reconcile before retrying' WHERE id=?",(row['id'],))
  c.db.close()
 def submit(self,data):
  action=data.get('action')
  if action not in COMMANDS:raise ValueError('Unknown action')
  if action in EXTERNAL and data.get('confirmed') is not True:raise ValueError('Explicit confirmation required for provider or email access')
  args=[]
  for field in COMMANDS[action]:
   value=data.get(field,'')
   try:uuid.UUID(value)
   except (ValueError,TypeError,AttributeError):raise ValueError('Valid identifier required')
   args.append(value)
  if action=='repo-create':
   from repository_remote import validate_target
   args+=['--target',validate_target(data.get('target'))]
  if action=='start-autonomy':
   from research_modes import research_profile
   mode=research_profile({},data.get('research_mode','normal'))['mode']
   product_budget=data.get('product_budget',100)
   if type(product_budget) is not int or not 1<=product_budget<=100000:raise ValueError('Invalid proposed product allowance')
   args+=['--research-mode',mode,'--budget',str(self.budget(data)),'--product-budget',str(product_budget)]
  if action in ('discover','rework-research') and 'research_mode' in data:
   from research_modes import research_profile
   profile=research_profile({},data['research_mode'])
   args+=['--research-mode',profile['mode']]
  if action=='discover':
   if data.get('idea'):
    try:uuid.UUID(data['idea'])
    except (ValueError,TypeError,AttributeError):raise ValueError('Valid idea identifier required')
    args+=['--idea',data['idea']]
   market=data.get('market','Small service businesses')
   if not isinstance(market,str) or not 1<=len(market)<=300:raise ValueError('Market required')
   args+=['--market',market,'--budget',str(self.budget(data))]
  if action=='register-proposal':args+=['--budget',str(self.budget(data))]
  if action=='workspace-init' and data.get('grant_tools') is True:args+=['--grant-tools']
  if action=='tick':args+=['--max-actions','1']
  if action=='start-delivery':
   args+=['--max-actions','10']
   if data.get('resume') is True:args+=['--resume']
  if action in CONFIG:args+=['--config',self.config]
  if not self.lock.acquire(blocking=False):raise ValueError('Another dashboard action is active; wait for its outcome')
  identifier=str(uuid.uuid4())
  try:
   c=Company(self.db)
   with c.transaction():
    for field,kind in (('project','project'),('idea','idea')):
     if data.get(field) and c.db.execute('SELECT 1 FROM trash WHERE kind=? AND target=?',(kind,data[field])).fetchone():raise ValueError('Restore from Trash before running actions')
    if data.get('task'):
     row=c.db.execute('SELECT project FROM tasks WHERE id=?',(data['task'],)).fetchone()
     if row and c.db.execute("SELECT 1 FROM trash WHERE kind='project' AND target=?",(row['project'],)).fetchone():raise ValueError('Restore the task project from Trash first')
    if action=='qa-static':
     row=c.db.execute('SELECT payload,status FROM tasks WHERE id=?',(data['task'],)).fetchone()
     checks=data.get('checks')
     criteria=json.loads(row['payload']).get('acceptance_criteria',[]) if row else []
     if not row or row['status']!='awaiting_review' or not isinstance(checks,dict) or not criteria or set(checks)!=set(criteria):raise ValueError('Static QA requires exactly one trusted check per acceptance criterion')
     for spec in checks.values():
      if not isinstance(spec,dict) or spec.get('kind') not in ('exists','contains','html','json') or not isinstance(spec.get('path'),str):raise ValueError('Unsupported static check')
     check_root=Path(self.config).parent/'artifacts'/'checks';check_root.mkdir(parents=True,exist_ok=True)
     check_path=check_root/(identifier+'.json');check_path.write_text(json.dumps(checks))
     args+=['--workspace-checks',str(check_path)]
    if c.db.execute("SELECT 1 FROM dashboard_jobs WHERE status IN ('queued','running')").fetchone():raise ValueError('Another dashboard action is active; wait for its outcome')
    c.db.execute("INSERT INTO dashboard_jobs(id,action,status,owner_pid) VALUES (?,?,'queued',?)",(identifier,action,os.getpid()))
    c.event('dashboard.action.requested',job=identifier,action=action)
   c.db.close()
   threading.Thread(target=self.run,args=(identifier,action,args),daemon=True).start()
  except Exception:
   if 'c' in locals():c.db.close()
   self.lock.release();raise
  return {'job':identifier}
 @staticmethod
 def budget(data):
  value=data.get('budget',100)
  if type(value) is not int or not 0<=value<=100000:raise ValueError('Invalid internal allowance')
  return value
 def run(self,identifier,action,args):
  c=Company(self.db)
  try:
   with c.transaction():c.db.execute("UPDATE dashboard_jobs SET status='running' WHERE id=?",(identifier,))
   # Do not store raw provider/CLI output: it may contain account data or secrets.
   result=subprocess.run([sys.executable,str(Path(__file__).parent/'company_cli.py'),'--db',self.db,'qa' if action=='qa-static' else action,*args],
       cwd=Path(self.config).parent,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=900)
   status='succeeded' if result.returncode==0 else 'failed'
   message='Action finished; inspect task state and audit events' if result.returncode==0 else 'Action failed; inspect persisted task feedback and configuration'
   with c.transaction():
    c.db.execute('UPDATE dashboard_jobs SET status=?,finished_at=CURRENT_TIMESTAMP,result=? WHERE id=?',(status,message,identifier))
    c.event('dashboard.action.finished',job=identifier,action=action,status=status)
  except Exception:
   with c.transaction():c.db.execute("UPDATE dashboard_jobs SET status='interrupted',result='Outcome unknown; reconcile before retrying' WHERE id=?",(identifier,))
  finally:c.db.close();self.lock.release()

 def mutate(self,data):
  c=Company(self.db)
  try:
   action=data.get('action');project=data.get('project')
   if action=='stop-autonomy':
    workflow=data.get('workflow')
    with c.transaction():
     row=c.db.execute('SELECT idea,project FROM autonomy_runs WHERE id=?',(workflow,)).fetchone()
     if not row:raise ValueError('Unknown autonomous workflow')
     c.db.execute("UPDATE autonomy_runs SET enabled=0,status='disabled',note='Founder stopped automatic handoffs',updated_at=CURRENT_TIMESTAMP WHERE id=?",(workflow,))
     idea=c.db.execute('SELECT research_project FROM ideas WHERE id=?',(row['idea'],)).fetchone()
     for target in (row['project'],idea['research_project'] if idea else None):
      if target:c.db.execute('UPDATE projects SET paused=1 WHERE id=?',(target,))
     c.event('autonomy.disabled',workflow=workflow)
    return {'ok':True}
   if action in ('trash','restore'):
    kind=data.get('kind');target=data.get('target')
    if kind not in ('idea','project') or not isinstance(target,str):raise ValueError('Valid trash target required')
    table='ideas' if kind=='idea' else 'projects'
    with c.transaction():
     if c.db.execute("SELECT 1 FROM dashboard_jobs WHERE status IN ('queued','running')").fetchone() or c.db.execute("SELECT 1 FROM tasks WHERE status='running'").fetchone():raise ValueError('Wait for running work to finish before moving or restoring items')
     row=c.db.execute('SELECT * FROM '+table+' WHERE id=?',(target,)).fetchone()
     if not row:raise ValueError('Unknown '+kind)
     if action=='trash':
      title=row['title'] if kind=='idea' else json.loads(row['proposal']).get('title','Untitled project')
      c.db.execute('INSERT OR IGNORE INTO trash(kind,target,title) VALUES (?,?,?)',(kind,target,title))
      paused_project=target if kind=='project' else row['research_project']
      if paused_project:c.db.execute('UPDATE projects SET paused=1 WHERE id=?',(paused_project,))
     else:c.db.execute('DELETE FROM trash WHERE kind=? AND target=?',(kind,target))
     c.event('item.'+action,item_kind=kind,target=target)
    return {'ok':True,'message':'Restored; associated work stays paused' if action=='restore' else 'Moved to Trash; files and history preserved'}
   if action=='configure-openai':
    from local_credentials import configure_openai
    with c.transaction():
     if c.db.execute("SELECT 1 FROM dashboard_jobs WHERE status IN ('queued','running')").fetchone():raise ValueError('Wait for active work before changing credentials')
     result=configure_openai(self.config,data.get('key'))
     c.event('credential.configured',provider='OpenAI',method='local_file')
    return result
   if action=='create-idea':
    from idea_store import create_idea
    return create_idea(c,data.get('title'),data.get('description',''),data.get('market','Any market'),data.get('origin','founder'))
   if action=='create-project':
    proposal=data.get('proposal')
    if not isinstance(proposal,dict) or not isinstance(proposal.get('title'),str):raise ValueError('Proposal title required')
    p,d=c.project(proposal,self.budget(data));return {'project':p,'digest':d}
   if not c.db.execute('SELECT 1 FROM projects WHERE id=?',(project,)).fetchone():raise ValueError('Unknown project')
   if c.db.execute("SELECT 1 FROM trash WHERE kind='project' AND target=?",(project,)).fetchone():raise ValueError('Restore the project from Trash first')
   cfg=json.loads(Path(self.config).read_text());roles=cfg.get('employees',{})
   if action=='assign':
    role=data.get('role');reviewer=data.get('reviewer');payload=data.get('payload')
    if role not in roles or reviewer not in roles or not isinstance(payload,dict) or not payload.get('objective') or not payload.get('acceptance_criteria'):raise ValueError('Configured roles, objective and criteria required')
    return {'task':c.task(project,role,reviewer,'employee.'+role,payload,data.get('dependencies',[]))}
   if action in ('grant','revoke'):
    role=data.get('role');tool=data.get('tool')
    allowed={'employee.'+r for r in roles}
    for server in cfg.get('mcp_servers',[]):allowed.update(server['name']+'/'+t for t in server.get('allow_tools',{}))
    allowed.update('workspace/'+t for t in ('list_files','read_file','write_file','checkpoint','inspect'))
    if role not in roles or tool not in allowed:raise ValueError('Configured role and allowlisted tool required')
    if action=='grant':c.grant(project,role,tool)
    else:
     with c.transaction():
      c.db.execute('DELETE FROM grants WHERE project=? AND role=? AND tool=?',(project,role,tool));c.event('tool.revoked',project=project,role=role,tool=tool)
    return {'ok':True}
   raise ValueError('Unknown mutation')
  finally:c.db.close()
