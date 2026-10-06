"""Explicit GitHub private-repository delivery. Fixed argv, no automatic retries."""
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from core import PolicyError
from workspace import get_workspace,git

def validate_target(target):
 if not isinstance(target,str) or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',target) or target.split('/')[1] in ('.','..'):raise ValueError('GitHub owner/repository required')
 return target

def initialize(company):
 company.db.execute('''CREATE TABLE IF NOT EXISTS repository_remotes (
 project TEXT PRIMARY KEY REFERENCES projects(id), target TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL, pushed_commit TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

def active_workspace(company,project):
 row=company.db.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone()
 if not row or not row['approved'] or row['paused'] or json.loads(row['proposal']).get('kind')=='research_mandate':raise PolicyError('Remote delivery requires an approved active product')
 return get_workspace(company,project)

def command_env():
 env={k:os.environ[k] for k in ('PATH','HOME','TMPDIR','SYSTEMROOT','GH_CONFIG_DIR','GH_TOKEN','GITHUB_TOKEN') if k in os.environ}
 env.update({'GH_PROMPT_DISABLED':'1','GIT_TERMINAL_PROMPT':'0','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull})
 return env

def gh(*args):
 binary=shutil.which('gh')
 if not binary:raise PolicyError('GitHub CLI missing; install and authenticate it locally')
 try:
  result=subprocess.run([binary,*args],env=command_env(),stdin=subprocess.DEVNULL,capture_output=True,timeout=90)
 except (OSError,subprocess.TimeoutExpired):raise PolicyError('GitHub outcome unknown; reconcile before retrying')
 if result.returncode:raise PolicyError('GitHub request failed or access denied; reconcile outcome and check local authentication')
 return result.stdout.decode()

def update(company,project,status,commit=None):
 with company.transaction():
  company.db.execute('UPDATE repository_remotes SET status=?,pushed_commit=COALESCE(?,pushed_commit),updated_at=CURRENT_TIMESTAMP WHERE project=?',(status,commit,project))
  company.event('repository.remote.status',project=project,status=status,commit=commit)

def remote_row(company,project):
 initialize(company);row=company.db.execute('SELECT * FROM repository_remotes WHERE project=?',(project,)).fetchone()
 if not row:raise PolicyError('GitHub repository not registered')
 return dict(row)

def ensure_origin(workspace,target):
 url='https://github.com/'+validate_target(target)+'.git'
 names=git(workspace.root,'remote').splitlines()
 if 'origin' in names:
  if git(workspace.root,'remote','get-url','origin')!=url or git(workspace.root,'remote','get-url','--push','origin')!=url:raise PolicyError('Existing origin differs; reconcile manually')
 else:git(workspace.root,'remote','add','origin',url)
 return url

def create_remote(company,project,target):
 target=validate_target(target);w=active_workspace(company,project);initialize(company)
 if 'origin' in git(w.root,'remote').splitlines():raise PolicyError('Existing origin requires reconciliation, not another remote creation')
 with company.transaction():
  if company.db.execute('SELECT 1 FROM repository_remotes WHERE project=?',(project,)).fetchone():raise PolicyError('Remote request already recorded; reconcile instead of repeating creation')
  company.db.execute("INSERT INTO repository_remotes(project,target,status) VALUES (?,?,'creating')",(project,target));company.event('repository.remote.create.requested',project=project,target=target)
 try:
  gh('repo','create',target,'--private')
  # Query actual private repo identity before attaching origin. No implicit push.
  return reconcile_remote(company,project)
 except Exception:
  update(company,project,'unknown');raise

def reconcile_remote(company,project):
 w=active_workspace(company,project);row=remote_row(company,project);target=validate_target(row['target'])
 try:
  info=json.loads(gh('repo','view',target,'--json','nameWithOwner,url,isPrivate'))
  if info.get('nameWithOwner','').lower()!=target.lower() or info.get('url')!='https://github.com/'+info.get('nameWithOwner','') or info.get('isPrivate') is not True:raise PolicyError('Repository identity or private visibility was not verified')
  ensure_origin(w,target)
  commit=row.get('pushed_commit')
  if row['status'] in ('pushing','push_unknown','pushed') and commit:
   ref=json.loads(gh('api','repos/'+target+'/git/ref/heads/product'))
   if ref.get('object',{}).get('sha')!=commit:raise PolicyError('Remote branch does not match expected commit; reconcile manually')
   status='pushed'
  else:status='pushed' if row['status']=='pushed' else 'created'
  update(company,project,status)
  return {'project':project,'target':target,'status':status,'url':'https://github.com/'+target}
 except Exception:
  update(company,project,'push_unknown' if row['status'] in ('pushing','push_unknown','pushed') else 'unknown');raise

def push_remote(company,project):
 w=active_workspace(company,project);row=remote_row(company,project)
 if row['status'] not in ('created','pushed'):raise PolicyError('Remote outcome requires reconciliation before pushing')
 target=validate_target(row['target']);ensure_origin(w,target)
 if git(w.root,'status','--porcelain'):raise PolicyError('Commit changes before remote push')
 commit=git(w.root,'rev-parse','HEAD')
 if not re.fullmatch('[0-9a-f]{40,64}',commit):raise PolicyError('Valid local commit required')
 tracked=git(w.root,'ls-tree','--name-only','-r','-z',commit).split('\0')
 for name in filter(None,tracked):
  path=w.path(name)
  if path.name in ('gmail-client.json','gmail-token.json','credentials.json','token.json'):raise PolicyError('Credential files cannot be pushed')
  blob=commit+':'+name
  if int(git(w.root,'cat-file','-s',blob))>60000:raise PolicyError('Tracked file exceeds bounded inspection limit')
  text=git(w.root,'show',blob)
  if re.search(r'\bsk-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----',text):raise PolicyError('Credential-like material must be removed before pushing')
 # Bind the expected revision before a request with an ambiguous possible outcome.
 update(company,project,'pushing',commit)
 try:
  binary=shutil.which('git');gh_binary=shutil.which('gh')
  if not binary or not gh_binary:raise PolicyError('Git and authenticated GitHub CLI are required locally')
  result=subprocess.run([binary,'-c','core.hooksPath='+os.devnull,'-c','credential.helper=',
      '-c','credential.helper=!'+shlex.quote(gh_binary)+' auth git-credential','-c','http.followRedirects=false',
      'push','origin',commit+':refs/heads/product'],cwd=w.root,env=command_env(),stdin=subprocess.DEVNULL,capture_output=True,timeout=90)
  if result.returncode:raise PolicyError('Remote push failed; reconcile before retrying')
  ref=json.loads(gh('api','repos/'+target+'/git/ref/heads/product'))
  if ref.get('object',{}).get('sha')!=commit:raise PolicyError('Remote commit was not verified; reconcile outcome')
  update(company,project,'pushed',commit)
  return {'project':project,'target':target,'status':'pushed','commit':commit,'verification':'Remote product branch SHA verified; product behavior and deployment not certified'}
 except Exception:
  update(company,project,'push_unknown');raise
