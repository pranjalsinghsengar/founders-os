"""Durable opt-in idea orchestration. No automatic budget increases or launches."""
import json
import os
import time
import uuid
from pathlib import Path
from core import PolicyError, ToolFailure
from idea_store import idea_by_id
from discovery import discover, draft_proposal, register_proposal, reconcile_saved_research
from qa import run_review
from gmail_approval import Gmail, EmailApprovals, GmailError
from research_modes import research_profile
from quality_gate import quality_settings

def initialize_autonomy(company):
    from failure_notifications import initialize
    initialize(company)
    company.db.execute('''CREATE TABLE IF NOT EXISTS autonomy_runs (
        id TEXT PRIMARY KEY, idea TEXT NOT NULL UNIQUE, enabled INTEGER NOT NULL,
        status TEXT NOT NULL, stage TEXT NOT NULL, note TEXT NOT NULL,
        research_mode TEXT NOT NULL, research_budget INTEGER NOT NULL,
        product_budget INTEGER NOT NULL, proposal_task TEXT, project TEXT,
        email_request TEXT, next_at INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    if 'owner_pid' not in {r[1] for r in company.db.execute('PRAGMA table_info(autonomy_runs)')}:
        company.db.execute('ALTER TABLE autonomy_runs ADD COLUMN owner_pid INTEGER')

def start_autonomy(company, idea, config, research_mode='normal', research_budget=100, product_budget=100):
    initialize_autonomy(company)
    idea_by_id(company,idea)
    for value in (research_budget,product_budget):
        if type(value) is not int or not 1<=value<=100000:
            raise ValueError('Positive bounded allowance required')
    profile=research_profile(config,research_mode)
    if research_budget<profile['cost_units']+quality_settings(config)['check_cost_units']:
        raise ValueError('Research allowance cannot cover the first research and self-check')
    with company.transaction():
        prior=company.db.execute('SELECT * FROM autonomy_runs WHERE idea=?',(idea,)).fetchone()
        if prior:
            return {'workflow':prior['id'],'status':prior['status']}
        identifier=str(uuid.uuid4())
        company.db.execute('''INSERT INTO autonomy_runs
            (id,idea,enabled,status,stage,note,research_mode,research_budget,product_budget)
            VALUES (?,?,1,'ready','research','Autonomous research-to-approval authorized',?,?,?)''',
            (identifier,idea,research_mode,research_budget,product_budget))
        company.event('autonomy.enabled',workflow=identifier,idea=idea,research_budget=research_budget,
                      product_budget=product_budget,research_mode=research_mode)
    return {'workflow':identifier,'status':'ready'}

def advance_autonomy(company, identifier, config, root, model_factory, delivery, gmail_factory=None):
    """Advance one handoff; the dashboard service schedules the next safe handoff."""
    initialize_autonomy(company)
    root=Path(root).resolve()
    with company.transaction():
        run=company.db.execute('SELECT * FROM autonomy_runs WHERE id=?',(identifier,)).fetchone()
        if not run or not run['enabled'] or run['status'] not in ('ready','waiting_approval'):
            raise PolicyError('Autonomous workflow is disabled, blocked or already active')
        idea=idea_by_id(company,run['idea'])
        for project in (idea['research_project'],run['project']):
            if project:
                p=company.db.execute('SELECT paused FROM projects WHERE id=?',(project,)).fetchone()
                if p and p['paused']:
                    company.db.execute("UPDATE autonomy_runs SET status='blocked',note='Associated project is paused; autonomy will not resume it' WHERE id=?",(identifier,))
                    return {'workflow':identifier,'status':'blocked','note':'Associated project is paused'}
        if company.db.execute("SELECT 1 FROM trash WHERE (kind='idea' AND target=?) OR (kind='project' AND target IN (?,?))",
                              (idea['id'],idea['research_project'],run['project'])).fetchone():
            company.db.execute("UPDATE autonomy_runs SET status='blocked',note='Restore associated items from Trash before continuing' WHERE id=?",(identifier,))
            return {'workflow':identifier,'status':'blocked','note':'Associated item is in Trash'}
        company.db.execute("UPDATE autonomy_runs SET status='running',owner_pid=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(os.getpid(),identifier))
    def update(status,stage,note,delay=0,**fields):
        with company.transaction():
            # Stopping the workflow during a call prevents subsequent scheduling.
            enabled=company.db.execute('SELECT enabled FROM autonomy_runs WHERE id=?',(identifier,)).fetchone()[0]
            if not enabled:status='disabled'
            company.db.execute('UPDATE autonomy_runs SET status=?,stage=?,note=?,next_at=?,owner_pid=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                               (status,stage,note,int(time.time())+delay,identifier))
            for key,value in fields.items():
                if key not in ('proposal_task','project','email_request'):raise ValueError('Invalid workflow field')
                company.db.execute('UPDATE autonomy_runs SET '+key+'=? WHERE id=?',(value,identifier))
            company.event('autonomy.progress',workflow=identifier,idea=idea['id'],status=status,stage=stage,note=note)
            if status=='blocked':
                from failure_notifications import queue_blocked
                queue_blocked(company,identifier,stage,note)
        return {'workflow':identifier,'status':status,'stage':stage,'note':note}
    def assessment(task):
        prior=company.db.execute("SELECT payload FROM tasks WHERE project=? AND tool='employee.qa'",(task['project'],)).fetchall()
        if any(json.loads(r['payload']).get('source_task')==task['id'] and
               json.loads(r['payload']).get('source_attempt')==task['attempts'] for r in prior):
            return update('blocked',run['stage'],'Existing review is unresolved; no repeated paid review')
        result=run_review(company,task['id'],model_factory('normal'),root/'artifacts',config.get('qa_run_cost_units',10))
        if result['status'] not in ('completed','changes_requested'):
            return update('blocked',run['stage'],'Independent review failed; inspect task feedback')
        return update('ready',run['stage'],'Independent assessment recorded; AI will take the next handoff')
    try:
        if run['stage']=='research':
            task=company.db.execute('SELECT * FROM tasks WHERE id=?',(idea['research_task'],)).fetchone() if idea['research_task'] else None
            if not task or task['status']=='changes_requested':
                result=discover(company,model_factory(run['research_mode']),config,root/'artifacts',
                    budget=run['research_budget'],market=idea['market'],idea=idea,
                    rework_task=task['id'] if task else None,research_mode=run['research_mode'])
                if result['status']!='awaiting_review':
                    if reconcile_saved_research(company,result['research_task'],root/'artifacts'):
                        return update('ready','research','Saved research formatting recovered; independent review is next')
                    return update('blocked','research','Research did not pass its pre-submission gate; inspect feedback')
                return update('ready','research','Research submitted; AI will independently review it')
            if task['status']=='awaiting_review':return assessment(task)
            if task['status']=='failed' and reconcile_saved_research(company,task['id'],root/'artifacts'):
                return update('ready','research','Saved research formatting recovered; independent review is next')
            if task['status']!='completed':return update('blocked','research',
                'Research is failed or interrupted; reconcile before retrying. Task feedback: '+
                (task['note'] or 'No failure detail recorded'))
            return update('ready','proposal','Research accepted; preparing the investment proposal')
        if run['stage']=='proposal':
            task=company.db.execute('SELECT * FROM tasks WHERE id=?',(run['proposal_task'],)).fetchone() if run['proposal_task'] else None
            if task is None:
                # Reuse an existing draft after a lost handoff instead of creating duplicates.
                task=company.db.execute("SELECT * FROM tasks WHERE project=? AND tool='proposal.draft' ORDER BY rowid DESC LIMIT 1",
                                        (idea['research_project'],)).fetchone()
            if task is None:
                result=draft_proposal(company,idea['research_task'],model_factory('normal'),config,root/'artifacts')
                return update('ready' if result['status']=='awaiting_review' else 'blocked','proposal',
                              'Proposal draft recorded; independent review next',proposal_task=result['proposal_task'])
            if not run['proposal_task']:
                return update('ready','proposal','Existing proposal draft linked',proposal_task=task['id'])
            if task['status']=='awaiting_review':return assessment(task)
            if task['status']=='changes_requested':
                result=draft_proposal(company,idea['research_task'],model_factory('normal'),config,root/'artifacts',rework_task=task['id'])
                return update('ready' if result['status']=='awaiting_review' else 'blocked','proposal','Proposal correction recorded')
            if task['status']!='completed':return update('blocked','proposal','Proposal failed or interrupted; inspect feedback')
            product=register_proposal(company,task['id'],run['product_budget'])
            if product['approved']:
                return update('ready','delivery','Existing approved product linked; automatic delivery next',project=product['project'])
            return update('ready','email','Reviewed proposal registered; approval email next',project=product['project'])
        def gateway():
            g=config.get('gmail',{})
            if not g.get('founder') or not g.get('token_file'):
                raise GmailError('Configure founder Gmail before autonomous approval delivery')
            mail=gmail_factory() if gmail_factory else Gmail(root/g['token_file'],g['founder'])
            return EmailApprovals(company,mail)
        if run['stage']=='email':
            approvals=gateway();request=run['email_request'] or approvals.prepare(run['project'])
            # Persist the request before an external write so uncertain delivery is never resent.
            with company.transaction():company.db.execute('UPDATE autonomy_runs SET email_request=? WHERE id=?',(request,identifier))
            state=company.db.execute('SELECT state FROM email_requests WHERE id=?',(request,)).fetchone()[0]
            if state in ('sending','unknown'):
                return update('blocked','email','Email delivery outcome is uncertain; reconcile Sent mail before continuing')
            approvals.send(request)
            return update('waiting_approval','approval','Proposal emailed; monitoring your authenticated reply',delay=60)
        if run['stage']=='approval':
            p=company.db.execute('SELECT approved FROM projects WHERE id=?',(run['project'],)).fetchone()
            if not p['approved']:
                gateway().poll()
                p=company.db.execute('SELECT approved FROM projects WHERE id=?',(run['project'],)).fetchone()
            if p['approved']:return update('ready','delivery','Founder approval recorded; automatic delivery next')
            r=company.db.execute('SELECT state,expires FROM email_requests WHERE id=?',(run['email_request'],)).fetchone()
            if r['state']!='sent' or r['expires']<=time.time():
                return update('blocked','approval','Approval rejected, changed or expired; no product work starts')
            invalid=company.db.execute("SELECT details FROM events WHERE kind='approval.email.reply.invalid' AND json_extract(details,'$.request')=? ORDER BY id DESC LIMIT 1",
                                       (run['email_request'],)).fetchone()
            note='Waiting for your authenticated investment decision'
            if invalid:
                note='Approval reply could not be authenticated: copy the complete APPROVE command from the original email, including its full verification token, and reply in that thread'
            return update('waiting_approval','approval',note,delay=60)
        if run['stage']=='delivery':
            result=delivery(run['project'])
            if result['status']=='waiting':return update('ready','delivery','Continuing approved delivery automatically')
            return update('blocked',result['stage'],result['note'])
        return update('blocked',run['stage'],'No implemented integration for this handoff')
    except (PolicyError,ToolFailure,GmailError):
        return update('blocked',run['stage'],'Handoff blocked by allowance, permissions, provider or quality checks; inspect task feedback')
    except Exception:
        update('blocked',run['stage'],'Unexpected or unknown outcome; reconcile before retrying')
        raise

def retry_autonomy(company, identifier, config, schedule=True):
    """Founder-confirmed retry of local employee work; no remote-write retries."""
    initialize_autonomy(company)
    with company.transaction():
        run=company.db.execute('SELECT * FROM autonomy_runs WHERE id=?',(identifier,)).fetchone()
        if not run or not run['enabled'] or run['status']!='blocked':raise PolicyError('Only an enabled blocked workflow can retry')
        idea=idea_by_id(company,run['idea'])
        project=run['project'] or idea['research_project']
        if run['stage'] not in ('research','proposal','delivery'):raise PolicyError('Reconcile this integration outcome before retrying')
        p=company.db.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone()
        if not p or not p['approved'] or p['paused']:raise PolicyError('Project must be approved and active')
        if company.db.execute("SELECT 1 FROM trash WHERE (kind='project' AND target=?) OR (kind='idea' AND target=?)",(project,idea['id'])).fetchone():raise PolicyError('Restore associated items first')
        if company.db.execute("SELECT 1 FROM tasks WHERE project=? AND status='running'",(project,)).fetchone():raise PolicyError('A worker is active or interrupted; reconcile first')
        failed=company.db.execute("SELECT * FROM tasks WHERE project=? AND status='failed'",(project,)).fetchall()
        if not failed:raise PolicyError('No failed local task to retry; resolve the reported blocker before resuming')
        minimum=0
        for task in failed:
            if task['tool']=='employee.qa':raise PolicyError('Failed independent reviews require separate reconciliation')
            if task['attempts']>=task['max_attempts']:raise PolicyError('Task retry limit reached')
            if not task['tool'].startswith('employee.') or task['owner'] not in config.get('employees',{}):
                raise PolicyError('Retry supports local employee tasks only; research/integration failures require reconciliation')
            grants=[r[0] for r in company.db.execute('SELECT tool FROM grants WHERE project=? AND role=?',(project,task['owner']))]
            if any(not g.startswith(('employee.','workspace/')) for g in grants):raise PolicyError('External tool outcomes must be reconciled before retrying')
            minimum+=config['employees'][task['owner']].get('run_cost_units',20)+quality_settings(config)['check_cost_units']+config.get('qa_run_cost_units',10)
        if p['budget']-p['spent']<minimum:raise PolicyError('Insufficient allowance for retry and review; increase the internal budget first')
        for task in failed:
            company.db.execute("UPDATE tasks SET status='changes_requested',note=? WHERE id=?",
                ('Founder requested bounded local retry. Inspect existing files and prior failure before acting; do not claim missing integrations are available. '+(task['note'] or ''),task['id']))
            company.event('task.retry.authorized.local',task=task['id'],attempt=task['attempts'],workflow=identifier)
        company.db.execute("UPDATE autonomy_runs SET status=?,next_at=0,note=?,owner_pid=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            ('ready' if schedule else 'blocked','Founder confirmed local retry within current allowance' if schedule else
             'Stepwise repair: operator prepared one bounded retry; automatic handoffs held for verification',identifier))
        company.event('autonomy.retry.authorized',workflow=identifier,minimum_units=minimum)
    return {'status':'ready' if schedule else 'blocked','minimum_units':minimum}


def resume_autonomy(company, identifier):
    """Founder explicitly resumes known stopped work; unresolved failures stay blocked."""
    initialize_autonomy(company)
    with company.transaction():
        run=company.db.execute('SELECT * FROM autonomy_runs WHERE id=?',(identifier,)).fetchone()
        if not run or run['status'] not in ('disabled','blocked'):
            raise PolicyError('Only stopped or blocked workflows can be resumed')
        idea=idea_by_id(company,run['idea'])
        for project in (idea['research_project'],run['project']):
            if not project:continue
            if company.db.execute("SELECT 1 FROM trash WHERE kind='project' AND target=?",(project,)).fetchone():
                raise PolicyError('Restore associated projects before resuming')
            superseded=" AND id NOT IN (SELECT source_task FROM local_repairs)" if company.db.execute("SELECT 1 FROM sqlite_master WHERE name='local_repairs'").fetchone() else ''
            if company.db.execute("SELECT 1 FROM tasks WHERE project=? AND status IN ('failed','running')"+superseded,(project,)).fetchone():
                raise PolicyError('Reconcile failed or interrupted tasks before resuming')
            remaining=company.db.execute('SELECT budget-spent FROM projects WHERE id=?',(project,)).fetchone()[0]
            if remaining<=0 and (project==run['project'] or not run['project']):
                raise PolicyError('Increase the approved internal allowance before resuming')
            company.db.execute('UPDATE projects SET paused=0 WHERE id=?',(project,))
        if company.db.execute("SELECT 1 FROM trash WHERE kind='idea' AND target=?",(run['idea'],)).fetchone():
            raise PolicyError('Restore the idea before resuming')
        if run['email_request'] and company.db.execute("SELECT 1 FROM email_requests WHERE id=? AND state IN ('sending','unknown')",(run['email_request'],)).fetchone():
            raise PolicyError('Reconcile uncertain email delivery before resuming')
        # Delivery blockers are reported as stages, but budget is not an
        # executable handoff. Restore delivery after an explicit funded resume.
        stage='delivery' if run['stage']=='budget' and run['project'] else run['stage']
        company.db.execute("UPDATE autonomy_runs SET enabled=1,status='ready',stage=?,next_at=0,note='Founder resumed automatic handoffs',updated_at=CURRENT_TIMESTAMP WHERE id=?",(stage,identifier))
        company.event('autonomy.resumed',workflow=identifier)
    return {'workflow':identifier,'status':'ready'}
