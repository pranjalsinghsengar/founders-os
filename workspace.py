"""Project-scoped local Git workspaces and non-executing static checks.

Directory isolation is not an OS sandbox. No generated program is executed.
"""
import hashlib
import ast
import json
import os
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from core import PolicyError

ALLOWED = {'.html','.css','.js','.jsx','.ts','.tsx','.py','.toml','.json','.md','.txt','.svg'}
TOOLS = ('list_files','read_file','write_file','write_qa_file','checkpoint','inspect','check_python','test_python')


def git(root, *args):
    command=shutil.which('git')
    if not command:
        raise PolicyError('Local Git executable missing')
    env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','TMPDIR') if k in os.environ}
    env.update({'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull,
                'GIT_AUTHOR_NAME':'Company local employee','GIT_AUTHOR_EMAIL':'employee@company.local',
                'GIT_COMMITTER_NAME':'Company local employee','GIT_COMMITTER_EMAIL':'employee@company.local'})
    result=subprocess.run([command,'-c','core.hooksPath='+os.devnull,'-c','commit.gpgSign=false',*args],
        cwd=root,env=env,stdin=subprocess.DEVNULL,capture_output=True,timeout=20)
    if result.returncode:
        raise PolicyError('Local Git operation failed; inspect workspace without retrying writes blindly')
    return result.stdout.decode().strip()


class Workspace:
    def __init__(self,root):
        self.root=Path(root).resolve()
    def path(self,name):
        if not isinstance(name,str) or not name or '\\' in name:
            raise PolicyError('Relative product file required')
        pure=PurePosixPath(name)
        if pure.is_absolute() or any(p in ('..','.') or p.startswith('.') for p in pure.parts):
            raise PolicyError('Hidden files and traversal are prohibited')
        path=self.root.joinpath(*pure.parts)
        if path.suffix not in ALLOWED or not path.resolve().is_relative_to(self.root):
            raise PolicyError('Unsupported product file or path outside workspace')
        # Refuse symlinks even if their current targets are inside the workspace.
        for part in [path,*path.parents]:
            if part==self.root.parent:break
            if part.is_symlink():raise PolicyError('Workspace symlinks are prohibited')
        return path
    def list_files(self):
        files=[]
        for path in sorted(self.root.rglob('*')):
            relative=path.relative_to(self.root)
            if any(p.startswith('.') for p in relative.parts):continue
            if path.is_file() and path.suffix in ALLOWED:
                try:self.path(relative.as_posix())
                except PolicyError:continue
                files.append(relative.as_posix())
        if len(files)>200:raise PolicyError('Workspace file-count limit reached')
        return files
    def read_file(self,path):
        target=self.path(path)
        if not target.exists():
            return {'path':path,'exists':False,'error':'file_not_found',
                    'message':'This permitted product file does not exist; inspect list_files or create it if required by the task'}
        if not target.is_file() or target.stat().st_size>60000:raise PolicyError('File missing or exceeds read limit')
        return {'path':path,'content':target.read_text()}
    def write_file(self,path,content):
        if not isinstance(content,str) or len(content.encode())>60000:raise PolicyError('File content exceeds limit')
        target=self.path(path)
        if not target.exists() and len(self.list_files())>=200:raise PolicyError('Workspace file-count limit reached')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(content)
        return {'path':path,'sha256':hashlib.sha256(content.encode()).hexdigest(),'bytes':len(content.encode())}
    def write_qa_file(self,path,content):
        self.path(path)
        pure=PurePosixPath(path)
        if not ((len(pure.parts)==2 and pure.parts[0]=='tests' and pure.name.startswith('test_') and pure.suffix=='.py') or
                (len(pure.parts)==2 and pure.parts[0]=='docs' and pure.name.startswith('qa_') and pure.suffix in ('.md','.json'))):
            raise PolicyError('QA writes require tests/test_*.py or docs/qa_*.md/json; application source is read-only')
        return self.write_file(path,content)
    def inspect(self):
        files=self.list_files()
        if sum(self.path(f).stat().st_size for f in files)>2000000:raise PolicyError('Workspace exceeds inspection limit')
        return {'files':[{'path':f,'sha256':hashlib.sha256(self.path(f).read_bytes()).hexdigest()} for f in files],
                'branch':git(self.root,'branch','--show-current'),
                'verification':'File hashes and repository state; product behavior not verified'}
    def check_python(self):
        results=[]
        for name in self.list_files():
            if name.endswith('.py'):
                try:
                    ast.parse(self.read_file(name)['content'],filename=name)
                    results.append({'path':name,'passed':True})
                except SyntaxError as error:
                    results.append({'path':name,'passed':False,'line':error.lineno})
        return {'passed':bool(results) and all(r['passed'] for r in results),'checks':results,
                'verification':'Python syntax only; no code imported or executed'}
    def checkpoint(self,message):
        if not isinstance(message,str) or not message.strip() or len(message)>200:raise ValueError('Short commit message required')
        files=self.list_files()
        if not files:raise PolicyError('No product files to commit')
        git(self.root,'add','--',*files)
        if git(self.root,'status','--porcelain'):
            git(self.root,'commit','-m',message)
        return {'commit':git(self.root,'rev-parse','HEAD'),'branch':git(self.root,'branch','--show-current')}


def setup_workspace(company, project, base_dir):
    row=company.db.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone()
    if row is None or not row['approved'] or row['paused']:
        raise PolicyError('Workspace requires an approved active product')
    proposal=json.loads(row['proposal'])
    if not isinstance(proposal,dict) or proposal.get('kind')=='research_mandate':
        raise PolicyError('Research approval cannot authorize a product workspace')
    company.db.execute('CREATE TABLE IF NOT EXISTS workspaces (project TEXT PRIMARY KEY REFERENCES projects(id), root TEXT NOT NULL UNIQUE)')
    base=Path(base_dir).resolve();root=base/project
    if not root.resolve().is_relative_to(base):raise PolicyError('Invalid project workspace')
    with company.transaction():
        existing=company.db.execute('SELECT root FROM workspaces WHERE project=?',(project,)).fetchone()
        if existing:
            if Path(existing['root'])!=root:raise PolicyError('Workspace already registered elsewhere')
            return {'project':project,'root':str(root),'status':'existing'}
        if root.exists():raise PolicyError('Unregistered existing folder requires manual reconciliation')
        root.mkdir(parents=True)
        git(root,'init','--initial-branch=product')
        company.db.execute('INSERT INTO workspaces VALUES (?,?)',(project,str(root)))
        company.event('workspace.created',project=project,branch='product')
    return {'project':project,'root':str(root),'status':'created'}


def get_workspace(company, project):
    table=company.db.execute("SELECT 1 FROM sqlite_master WHERE name='workspaces'").fetchone()
    row=company.db.execute('SELECT root FROM workspaces WHERE project=?',(project,)).fetchone() if table else None
    if not row:raise PolicyError('Product workspace not configured')
    root=Path(row['root'])
    if not root.is_absolute() or root.resolve()!=root or not root.is_dir():raise PolicyError('Registered workspace path changed; reconcile before access')
    return Workspace(root)


class Document(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=set();self.title=False;self.links=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='title':self.title=True
        if attrs.get('id'):self.ids.add(attrs['id'])
        if tag in ('script','link'):
            value=attrs.get('src') if tag=='script' else attrs.get('href')
            if value:self.links.append(value)


def check_static(workspace, checks):
    """Only fixed checks from trusted operator config; never run generated code."""
    results=[]
    for criterion,spec in checks.items():
        if not isinstance(criterion,str) or not isinstance(spec,dict):raise ValueError('Invalid static check')
        path=workspace.path(spec['path']);kind=spec['kind']
        if path.is_file() and path.stat().st_size>60000:
            raise PolicyError('Static check file exceeds read limit')
        passed=False
        if kind=='exists':passed=path.is_file()
        elif kind=='contains':passed=path.is_file() and isinstance(spec.get('text'),str) and spec['text'] in path.read_text()
        elif kind=='html':
            if path.is_file():
                document=Document();document.feed(path.read_text())
                linked=[]
                for link in document.links:
                    if link.startswith(('https:','http:','//','data:')):continue
                    relative=(PurePosixPath(spec['path']).parent/link.split('?')[0]).as_posix()
                    linked.append(workspace.path(relative).is_file())
                passed=document.title and all(identifier in document.ids for identifier in spec.get('ids',[])) and all(linked)
        elif kind=='json':
            try:json.loads(path.read_text());passed=True
            except (ValueError,OSError):pass
        elif kind=='python':
            try:ast.parse(workspace.read_file(spec['path'])['content']);passed=True
            except (SyntaxError,OSError):pass
        else:raise ValueError('Unsupported static check kind')
        results.append({'criterion':criterion,'passed':passed,'path':spec['path'],'check':kind})
    return results


def review_workspace(company, task, checks, artifact_dir):
    row=company.db.execute('SELECT * FROM tasks WHERE id=?',(task,)).fetchone()
    if not row or row['status']!='awaiting_review':raise PolicyError('Task must await independent review')
    criteria=json.loads(row['payload']).get('acceptance_criteria')
    if not isinstance(criteria,list) or not criteria or set(criteria)!=set(checks):raise PolicyError('Configure exactly one check per acceptance criterion')
    workspace=get_workspace(company,row['project'])
    reviewer=row['reviewer']
    review_task=company.task(row['project'],reviewer,'operator.'+reviewer,'employee.qa',
                            {'source_task':task,'source_attempt':row['attempts'],'verification':'static_workspace'})
    def work(_):
        company.reserve_employee_call(review_task,'workspace/inspect',0)
        before=workspace.inspect()
        results=check_static(workspace,checks)
        if workspace.inspect()!=before:raise PolicyError('Workspace changed during QA')
        accepted=all(c['passed'] for c in results)
        note='Local static artifact checks passed' if accepted else 'Fix failed static checks: '+', '.join(c['criterion'] for c in results if not c['passed'])
        report={'source_task':task,'accepted':accepted,'note':note,'checks':results,'workspace':before,
                'verification':'Independent static checks only; no generated application code executed or browser journey tested'}
        root=Path(artifact_dir).resolve();root.mkdir(parents=True,exist_ok=True)
        path=root/(review_task+'.qa.json');path.write_text(json.dumps(report,indent=2))
        return {'artifact':str(path),'evidence':str(path),'decision':report}
    company.register_tool('employee.qa',work,0)
    status=company.execute(review_task)
    if status!='awaiting_review':return {'review_task':review_task,'status':status}
    decision=json.loads(company.db.execute('SELECT output FROM tasks WHERE id=?',(review_task,)).fetchone()[0])['decision']
    # Recheck exact workspace evidence before closing the source task.
    if workspace.inspect()!=decision['workspace']:raise PolicyError('Workspace changed before QA acceptance')
    company.review(task,reviewer,decision['accepted'],decision['note'],expected_output=row['output'],expected_attempts=row['attempts'])
    return {'review_task':review_task,'accepted':decision['accepted'],'status':company.db.execute('SELECT status FROM tasks WHERE id=?',(task,)).fetchone()[0]}


def setup_market_workspace(company,project,base_dir):
    """Group new products by market; never move a registered existing repository."""
    table=company.db.execute("SELECT 1 FROM sqlite_master WHERE name='workspaces'").fetchone()
    prior=company.db.execute('SELECT root FROM workspaces WHERE project=?',(project,)).fetchone() if table else None
    if prior:
        get_workspace(company,project)
        return setup_workspace(company,project,Path(prior['root']).parent)
    row=company.db.execute('SELECT proposal FROM projects WHERE id=?',(project,)).fetchone()
    if not row:raise PolicyError('Unknown product')
    proposal=json.loads(row['proposal'])
    market=re.sub(r'[^a-z0-9]+','-',str(proposal.get('market','general')).lower()).strip('-')[:60] or 'general'
    return setup_workspace(company,project,Path(base_dir)/market)
