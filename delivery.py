"""Bounded approved-product orchestration with automatic local role grants."""
import json
import os
from pathlib import Path
from core import PolicyError
from orchestration import generate_plan, install_plan, run_ready
from workspace import setup_market_workspace, TOOLS

LOCAL_ROLES = ('designer','developer','product_manager','qa')
CAPABILITIES = {
    'available':['Scoped local Git source files: Python, TS/TSX, JS/JSX, HTML, CSS, TOML, JSON, Markdown, text and SVG',
                 'Python syntax checks without execution',
                 'Offline Python unittest containers when a trusted python_test_image is configured and Docker is available',
                 'Model self-checks and independent artifact assessment'],
    'missing':['Isolated package installation/build execution','Native mobile build and device testing',
               'Browser behavior QA','Deployment, monitoring and rollback'],
    'authority':'Local MVP delivery only; no customer contact, remote writes or deployment grants',
}

def initialize_delivery(company):
    company.db.execute('''CREATE TABLE IF NOT EXISTS delivery_runs (
        project TEXT PRIMARY KEY REFERENCES projects(id), plan_task TEXT,
        status TEXT NOT NULL, stage TEXT NOT NULL, note TEXT NOT NULL,
        owner_pid INTEGER, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

def run_delivery(company, project, model, config, root, execute, review,
                 max_actions=10, resume=False, plan=None):
    """One run continues handoffs until blocked or its action limit; no background daemon."""
    if type(max_actions) is not int or not 1 <= max_actions <= 20:
        raise ValueError('Delivery max_actions must be 1..20')
    initialize_delivery(company)
    root = Path(root).resolve()
    with company.transaction():
        row = company.db.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone()
        if not row or not row['approved'] or json.loads(row['proposal']).get('kind')=='research_mandate':
            raise PolicyError('Autonomous delivery requires an approved product')
        tables={r[0] for r in company.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'trash' in tables and company.db.execute("SELECT 1 FROM trash WHERE kind='project' AND target=?",(project,)).fetchone():
            raise PolicyError('Restore the product before starting delivery')
        if row['paused'] and not resume:
            raise PolicyError('Product paused; explicitly resume before starting delivery')
        prior=company.db.execute('SELECT * FROM delivery_runs WHERE project=?',(project,)).fetchone()
        if prior and prior['status']=='running':
            alive=False
            if prior['owner_pid']:
                try:os.kill(prior['owner_pid'],0);alive=True
                except ProcessLookupError:pass
                except PermissionError:alive=True
            if alive:raise PolicyError('Delivery is already running')
            # Interrupted tasks are not retried: their external outcomes may be unknown.
        if company.db.execute("SELECT 1 FROM tasks WHERE project=? AND status='running'",(project,)).fetchone():
            raise PolicyError('A worker is running or interrupted; reconcile before continuing')
        if row['paused']:
            company.db.execute('UPDATE projects SET paused=0 WHERE id=?',(project,))
            company.event('project.resumed',project=project,actor='delivery.start')
        company.db.execute('''INSERT INTO delivery_runs(project,status,stage,note,owner_pid)
            VALUES (?,'running','planning','Automatic handoffs starting',?)
            ON CONFLICT(project) DO UPDATE SET status='running',owner_pid=excluded.owner_pid,
            updated_at=CURRENT_TIMESTAMP''',(project,os.getpid()))
        company.event('delivery.started',project=project,max_actions=max_actions)

    actions=[]
    def grant(role,tool):
        if not company.db.execute('SELECT 1 FROM grants WHERE project=? AND role=? AND tool=?',(project,role,tool)).fetchone():
            company.grant(project,role,tool)
    def update(status, stage, note, task=None):
        with company.transaction():
            company.db.execute('UPDATE delivery_runs SET status=?,stage=?,note=?,updated_at=CURRENT_TIMESTAMP WHERE project=?',
                               (status,stage,note,project))
            if task:company.db.execute('UPDATE delivery_runs SET plan_task=? WHERE project=?',(task,project))
            company.event('delivery.progress',project=project,status=status,stage=stage,note=note)
        return {'project':project,'status':status,'stage':stage,'note':note,'actions':actions,
                'limitations':CAPABILITIES['missing']}

    try:
        required={'planner','product_manager','developer','designer','qa'}
        if not required <= set(config.get('employees',{})):
            return update('blocked','configuration','Required delivery roles are not configured')
        for role,tool in (('planner','employee.planner'),('product_manager','employee.qa')):
            grant(role,tool)
        # Planning gets actual connected capabilities, not an imagined full delivery stack.
        planning_config={**config,'employees':{r:config['employees'][r] for r in LOCAL_ROLES},
                         'delivery_capabilities':CAPABILITIES}
        if plan is None:
            plan=lambda rework:generate_plan(company,project,model,planning_config,root/'artifacts',rework_task=rework)
        while len(actions)<max_actions:
            p=company.db.execute('SELECT approved,paused,budget,spent FROM projects WHERE id=?',(project,)).fetchone()
            if p['paused'] or not p['approved']:
                return update('blocked','paused','Product paused or approval revoked')
            if p['spent']>=p['budget']:
                return update('blocked','budget','Approved internal allowance exhausted; no budget increased')
            run=company.db.execute('SELECT plan_task FROM delivery_runs WHERE project=?',(project,)).fetchone()
            pt=company.db.execute('SELECT * FROM tasks WHERE id=?',(run['plan_task'],)).fetchone() if run['plan_task'] else None
            if pt is None:
                pt=company.db.execute("SELECT * FROM tasks WHERE project=? AND tool='employee.planner' ORDER BY rowid DESC LIMIT 1",(project,)).fetchone()
            if pt is None or pt['status'] in ('queued','blocked','changes_requested'):
                update('running','planning','AI is preparing or correcting the delivery plan')
                result=plan(pt['id'] if pt else None)
                actions.append({'action':'plan',**result})
                update('running','planning','Plan attempt recorded',result['task'])
                if result['status']!='awaiting_review':
                    return update('blocked','planning','Plan did not pass pre-submission checks; inspect its feedback')
                continue
            update('running','plan_review','Inspecting delivery plan state',pt['id'])
            if pt['status']=='awaiting_review':
                prior_reviews=company.db.execute("SELECT payload FROM tasks WHERE project=? AND tool='employee.qa'",(project,)).fetchall()
                if any(json.loads(r['payload']).get('source_task')==pt['id'] and
                       json.loads(r['payload']).get('source_attempt')==pt['attempts'] for r in prior_reviews):
                    return update('blocked','plan_review','This plan attempt already has an unresolved review; no paid review repeated')
                result=review(pt['id']);actions.append({'action':'plan_review',**result})
                if result.get('status') not in ('completed','changes_requested'):
                    return update('blocked','plan_review','Plan review failed; inspect reviewer feedback')
                continue
            if pt['status']!='completed':
                return update('blocked','planning','Plan failed or exhausted its attempts; inspect feedback')
            mapping=install_plan(company,pt['id'],planning_config['employees'])
            setup_market_workspace(company,project,root/'workspaces')
            # Derive grants from installed assignments; never grant unrelated MCP or account access.
            for task in mapping.values():
                t=company.db.execute('SELECT owner,reviewer FROM tasks WHERE id=?',(task,)).fetchone()
                grant(t['owner'],'employee.'+t['owner'])
                grant(t['reviewer'],'employee.qa')
                for role in {t['owner'],t['reviewer']}:
                    names=TOOLS if role==t['owner'] and role in ('developer','designer','repair_engineer') else ('read_file','list_files','inspect','check_python','test_python')
                    if role==t['owner'] and role=='qa':names=(*names,'write_qa_file','checkpoint')
                    for name in names:grant(role,'workspace/'+name)
            work=[company.db.execute('SELECT * FROM tasks WHERE id=?',(task,)).fetchone() for task in mapping.values()]
            if all(t['status']=='completed' for t in work):
                return update('local_tasks_reviewed','release_blocked',
                    'Local plan tasks passed artifact review; release remains blocked by missing build/browser/deployment capabilities')
            failed=next((t for t in work if t['status']=='failed'),None)
            if failed:
                from local_recovery import recover_local
                recovery=recover_local(company,failed['id'],config,root)
                if recovery:
                    actions.append({'action':'automatic_recovery',**recovery})
                    continue
                return update('blocked','delivery','Employee task '+failed['id'][:8]+' failed: '+
                    (failed['note'] or 'Inspect saved feedback before retrying'))
            # This runtime has no deployment or customer-pilot measurements
            # adapter. Do not pay a text worker to represent them as executed.
            for candidate in work:
                objective=json.loads(candidate['payload']).get('objective','').lower()
                if candidate['owner']=='product_manager' and candidate['status'] in ('queued','blocked','changes_requested') and any(x in objective for x in ('pilot deployment','pilot results')):
                    pending=company.db.execute("SELECT 1 FROM dependencies d JOIN tasks t ON t.id=d.dependency WHERE d.task=? AND t.status!='completed'",(candidate['id'],)).fetchone()
                    if not pending:
                        return update('blocked','pilot_integration','Next handoff requires live pilot/deployment and usage-metrics integrations that are not connected; no pilot execution or customer contact was started')
            update('running','delivery','AI is assigning, building, reviewing and repairing ready work')
            step=run_ready(company,project,execute,review,max_actions=1)
            if not step:
                return update('blocked','delivery','No safe ready handoff; inspect dependencies or unresolved review')
            actions.extend(step)
            if step[0].get('status')=='policy_blocked' or step[0].get('result',{}).get('status')=='policy_blocked':
                return update('blocked','policy','Next action blocked by allowance or permissions; no limits expanded')
        return update('waiting','action_limit','Bounded run reached its action limit; Continue resumes the existing plan')
    except PolicyError:
        return update('blocked','policy','Next action blocked by approval, pause, permissions or allowance; inspect task state')
    except Exception:
        update('blocked','failure','Delivery failed; reconcile task and tool outcomes before continuing')
        raise
