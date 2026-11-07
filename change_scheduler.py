"""Select bounded automatic work for explicitly authorized local product changes."""
import json
from quality_gate import quality_settings


def next_change_action(company, config):
    settings=quality_settings(config)
    for task in company.db.execute("SELECT t.*,p.approved,p.paused,p.budget-p.spent AS remaining FROM tasks t JOIN projects p ON p.id=t.project WHERE json_extract(t.payload,'$.kind')='founder_change' AND t.status IN ('queued','changes_requested','awaiting_review') ORDER BY CASE t.status WHEN 'awaiting_review' THEN 0 WHEN 'changes_requested' THEN 1 ELSE 2 END,t.rowid"):
        payload=json.loads(task['payload'])
        authorized=payload.get('autonomous') is True or (config.get('project_changes_autonomous') is True and task['attempts']>0) or (payload.get('repair_of') and config.get('local_recovery_enabled') is True)
        if not authorized or not task['approved'] or task['paused']:continue
        if company.db.execute("SELECT 1 FROM trash WHERE kind='project' AND target=?",(task['project'],)).fetchone():continue
        if company.db.execute("SELECT 1 FROM sqlite_master WHERE name='local_repairs'").fetchone() and company.db.execute('SELECT 1 FROM local_repairs WHERE source_task=?',(task['id'],)).fetchone():continue
        if company.db.execute("SELECT 1 FROM tasks WHERE project=? AND status='running'",(task['project'],)).fetchone():continue
        role=config.get('employees',{}).get(task['owner'])
        if role is None:continue
        grants=[r[0] for r in company.db.execute('SELECT tool FROM grants WHERE project=? AND role=?',(task['project'],task['owner']))]
        if task['tool'] not in grants or any(not g.startswith(('employee.','workspace/')) for g in grants):continue
        if task['status']=='awaiting_review':
            if task['reviewer'] not in config.get('employees',{}) or not company.db.execute('SELECT 1 FROM grants WHERE project=? AND role=? AND tool=?',(task['project'],task['reviewer'],'employee.qa')).fetchone():continue
            # Never repeat a failed/uncertain independent review of the same output.
            if company.db.execute("SELECT 1 FROM tasks WHERE json_extract(payload,'$.source_task')=? AND json_extract(payload,'$.source_attempt')=?",(task['id'],task['attempts'])).fetchone():continue
            if task['remaining']<config.get('qa_run_cost_units',10):continue
            return {'action':'qa','task':task['id'],'confirmed':True}
        if task['attempts']>=task['max_attempts']:continue
        minimum=role.get('run_cost_units',20)+settings['check_cost_units']*(settings['max_revisions']+1)+settings['revision_cost_units']*settings['max_revisions']+config.get('qa_run_cost_units',10)
        if task['remaining']<minimum:continue
        return {'action':'run','task':task['id'],'confirmed':True}
    return None
