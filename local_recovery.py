"""Opt-in, bounded recovery for diagnosed local delivery failures only."""
import json
import uuid
from contextlib import nullcontext
from pathlib import Path
from quality_gate import quality_settings

RECOVERABLE={'worker_round_limit','quality_not_ready','quality_invalid_check','workspace_path'}


def recover_local(company, task, config, root):
    if config.get('local_recovery_enabled') is not True:return None
    company.db.execute('''CREATE TABLE IF NOT EXISTS local_repairs (
        source_task TEXT PRIMARY KEY, replacement_task TEXT UNIQUE,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    with (nullcontext() if company.db.in_transaction else company.transaction()):
        t=company.db.execute('SELECT * FROM tasks WHERE id=?',(task,)).fetchone()
        if not t or t['status']!='failed' or t['owner'] not in ('developer','designer','qa','repair_engineer'):return None
        if t['owner']=='qa' and json.loads(t['payload']).get('source_task'):return None
        p=company.db.execute('SELECT * FROM projects WHERE id=?',(t['project'],)).fetchone()
        if not p or not p['approved'] or p['paused']:return None
        tables={r[0] for r in company.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'trash' in tables and company.db.execute("SELECT 1 FROM trash WHERE kind='project' AND target=?",(t['project'],)).fetchone():return None
        if company.db.execute("SELECT 1 FROM tasks WHERE project=? AND status='running'",(t['project'],)).fetchone():return None
        grants=[r[0] for r in company.db.execute('SELECT tool FROM grants WHERE project=? AND role=?',(t['project'],t['owner']))]
        if not grants or any(not g.startswith(('employee.','workspace/')) for g in grants):return None
        failure=company.db.execute("SELECT details FROM events WHERE kind IN ('tool.failed','task.failure.reconciled.local') AND json_extract(details,'$.task')=? ORDER BY id DESC LIMIT 1",(task,)).fetchone()
        code=json.loads(failure[0]).get('failure_code') if failure else None
        if code not in RECOVERABLE:
            review=company.db.execute("SELECT details FROM events WHERE kind='task.reviewed' AND json_extract(details,'$.task')=? ORDER BY id DESC LIMIT 1",(task,)).fetchone()
            if not (json.loads(t['payload']).get('kind')=='founder_change' and review and json.loads(review[0]).get('accepted') is False):return None
            code='review_changes_requested'
        specialist=config.get('employees',{}).get('repair_engineer')
        owner='repair_engineer' if specialist and t['owner']!='repair_engineer' else t['owner']
        if owner==t['reviewer']:return None
        owner_grants=[r[0] for r in company.db.execute('SELECT tool FROM grants WHERE project=? AND role=?',(t['project'],owner))]
        if any(not g.startswith(('employee.','workspace/')) for g in owner_grants):return None
        role=config.get('employees',{}).get(owner)
        if not role:return None
        settings=quality_settings(config)
        minimum=role.get('run_cost_units',20)+settings['check_cost_units']*(settings['max_revisions']+1)+settings['revision_cost_units']*settings['max_revisions']+config.get('qa_run_cost_units',10)
        if p['budget']-p['spent']<minimum:return None
        corrections=[]
        for path in sorted((Path(root)/'artifacts').glob(task+'.attempt-'+str(t['attempts'])+'.quality.*.check.json')):
            try:
                response=json.loads(path.read_text())
                for item in response.get('output',[]):
                    for part in item.get('content',[]):
                        if part.get('type')=='output_text':
                            decision=json.loads(part['text'])
                            corrections.extend(x for x in decision.get('corrections',[]) if isinstance(x,str))
            except (ValueError,OSError,TypeError):pass
        feedback=(t['note'] or '')+' Automatic local repair. Inspect current files and saved evidence; preserve accepted tests and security controls. Fix the original criteria; simulations are not working integrations. '+json.dumps(corrections[:20])
        if owner==t['owner'] and t['attempts']<t['max_attempts']:
            company.db.execute("UPDATE tasks SET status='changes_requested',note=? WHERE id=?",(feedback,task))
            company.event('task.recovery.automatic',task=task,code=code,minimum_units=minimum,attempts_preserved=t['attempts'])
            return {'task':task,'strategy':'retry','code':code}
        # One repair lineage only. Never reset attempts or expand the proposal.
        if company.db.execute('SELECT 1 FROM local_repairs WHERE source_task=? OR replacement_task=?',(task,task)).fetchone():return None
        plan=company.db.execute('SELECT * FROM installed_plans WHERE mapping LIKE ?',('%'+task+'%',)).fetchone() if 'installed_plans' in tables else None
        if not plan and json.loads(t['payload']).get('kind')!='founder_change':return None
        payload=json.loads(t['payload']);payload['repair_of']=task
        deps=[r[0] for r in company.db.execute('SELECT dependency FROM dependencies WHERE task=?',(task,))]
        replacement=str(uuid.uuid4())
        company.db.execute('INSERT INTO tasks(id,project,owner,reviewer,tool,payload,max_attempts,note) VALUES (?,?,?,?,?,?,2,?)',
                           (replacement,t['project'],owner,t['reviewer'],'employee.'+owner,json.dumps(payload),feedback))
        if owner=='repair_engineer':
            from workspace import TOOLS
            for tool in ('employee.repair_engineer',*('workspace/'+name for name in TOOLS)):
                company.db.execute('INSERT OR IGNORE INTO grants VALUES (?,?,?)',(t['project'],owner,tool))
        for dep in deps:company.db.execute('INSERT INTO dependencies VALUES (?,?)',(replacement,dep))
        if plan:
            mapping=json.loads(plan['mapping'])
            mapping={k:replacement if v==task else v for k,v in mapping.items()}
            company.db.execute('UPDATE installed_plans SET mapping=? WHERE source_task=?',(json.dumps(mapping),plan['source_task']))
        downstream=company.db.execute('SELECT task FROM dependencies WHERE dependency=?',(task,)).fetchall()
        for dependent in downstream:
            company.db.execute('UPDATE dependencies SET dependency=? WHERE task=? AND dependency=?',(replacement,dependent[0],task))
            row=company.db.execute('SELECT payload FROM tasks WHERE id=?',(dependent[0],)).fetchone()
            data=json.loads(row[0]);data['dependency_tasks']=[replacement if x==task else x for x in data.get('dependency_tasks',[])]
            company.db.execute('UPDATE tasks SET payload=? WHERE id=?',(json.dumps(data),dependent[0]))
        company.db.execute('INSERT INTO local_repairs(source_task,replacement_task) VALUES (?,?)',(task,replacement))
        company.event('task.repair.created.automatic',task=replacement,source_task=task,owner=owner,code=code,minimum_units=minimum)
        return {'task':replacement,'strategy':'repair','code':code}
