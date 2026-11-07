"""Permanent deletion of trashed local projects; never deletes remote repositories."""
import shutil
import uuid
from pathlib import Path


def delete_project(company, project, root, confirmed=False):
    if confirmed is not True:
        raise ValueError('Confirm permanent project deletion')
    uuid.UUID(project)
    root=Path(root).resolve()
    staged=[]
    try:
        with company.transaction():
            db=company.db
            if not db.execute("SELECT 1 FROM trash WHERE kind='project' AND target=?",(project,)).fetchone():
                raise ValueError('Move the project to Trash before deleting it')
            if db.execute("SELECT 1 FROM tasks WHERE status='running'").fetchone() or db.execute("SELECT 1 FROM dashboard_jobs WHERE status IN ('queued','running')").fetchone():
                raise ValueError('Wait for active work before deleting a project')
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            tasks=[r[0] for r in db.execute('SELECT id FROM tasks WHERE project=?',(project,))]
            files=[]
            if 'workspaces' in tables:
                workspace=db.execute('SELECT root FROM workspaces WHERE project=?',(project,)).fetchone()
                if workspace:
                    path=Path(workspace[0])
                    if path.name!=project or path.is_symlink() or not path.resolve().is_relative_to(root/'workspaces'):
                        raise ValueError('Workspace is outside managed project folders; deletion requires reconciliation')
                    files.append(path)
            for folder,prefixes in ((root/'artifacts',tasks),(root/'exports',[project])):
                if folder.exists():
                    files.extend(p for p in folder.iterdir() if any(p.name.startswith(prefix+'.') or p.name.startswith(prefix+'-') for prefix in prefixes))
            for path in files:
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    raise ValueError('Unsafe project file path; deletion requires reconciliation')
            quarantine=root/('.delete-'+str(uuid.uuid4()))
            quarantine.mkdir()
            for index,path in enumerate(files):
                if path.exists():
                    destination=quarantine/str(index);path.rename(destination);staged.append((path,destination))
            task_query='SELECT id FROM tasks WHERE project=?'
            for table,columns in (('dependencies',('task','dependency')),('local_repairs',('source_task','replacement_task')),('installed_plans',('source_task',)),('registered_proposals',('task',))):
                if table in tables:
                    for column in columns:db.execute(f'DELETE FROM {table} WHERE {column} IN ({task_query})',(project,))
            if 'email_decisions' in tables:
                db.execute('DELETE FROM email_decisions WHERE request_id IN (SELECT id FROM email_requests WHERE project=?)',(project,))
            if 'ideas' in tables:
                db.execute(f'UPDATE ideas SET research_task=NULL,research_project=NULL WHERE research_project=? OR research_task IN ({task_query})',(project,project))
            db.execute(f"DELETE FROM events WHERE json_extract(details,'$.project')=? OR json_extract(details,'$.task') IN ({task_query}) OR json_extract(details,'$.source_task') IN ({task_query})",(project,project,project))
            for table in ('registered_proposals','workspaces','repository_remotes','delivery_runs','autonomy_runs','failure_notifications','email_requests','grants'):
                if table in tables:db.execute(f'DELETE FROM {table} WHERE project=?',(project,))
            db.execute('DELETE FROM tasks WHERE project=?',(project,))
            db.execute("DELETE FROM trash WHERE kind='project' AND target=?",(project,))
            db.execute('DELETE FROM projects WHERE id=?',(project,))
            company.event('project.deleted.permanently',deleted_project=project)
    except Exception:
        for original,destination in reversed(staged):destination.rename(original)
        if 'quarantine' in locals():shutil.rmtree(quarantine,ignore_errors=True)
        raise
    shutil.rmtree(quarantine)
    return {'ok':True,'message':'Project, tasks, local workspace, artifacts and exports permanently deleted. Remote repositories and Gmail messages are unchanged.'}
