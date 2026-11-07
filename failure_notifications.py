"""Durable failure-email outbox. Ambiguous sends are never repeated automatically."""
import hashlib
import html
import json
import re
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlsplit, urlencode
from core import PolicyError
from gmail_approval import Gmail, GmailError


def initialize(company):
    company.db.execute('''CREATE TABLE IF NOT EXISTS failure_notifications (
        id TEXT PRIMARY KEY, workflow TEXT NOT NULL, project TEXT, stage TEXT NOT NULL,
        note TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
        gmail_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    company.db.execute('CREATE TABLE IF NOT EXISTS runtime_settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)')


def dashboard_origin(origin):
    value=urlsplit(origin)
    if value.scheme!='http' or value.hostname not in ('127.0.0.1','localhost') or value.username or value.password or value.path not in ('','/') or value.query or value.fragment:
        raise ValueError('Local dashboard HTTP origin required')
    if not value.port or not 1<=value.port<=65535:raise ValueError('Dashboard port required')
    return origin.rstrip('/')


def queue_blocked(company, workflow, stage, note):
    # Caller owns the transaction. Stable fingerprint suppresses repeated alerts.
    run=company.db.execute('SELECT idea,project FROM autonomy_runs WHERE id=?',(workflow,)).fetchone()
    idea=company.db.execute('SELECT research_project FROM ideas WHERE id=?',(run['idea'],)).fetchone()
    project=run['project'] or idea['research_project']
    tasks=[tuple(r) for r in company.db.execute("SELECT id,attempts,status FROM tasks WHERE project=? AND status='failed' ORDER BY id",(project,))]
    identifier=hashlib.sha256(json.dumps([workflow,stage,note,tasks],sort_keys=True).encode()).hexdigest()
    # Notes are application diagnostics, not raw exception/provider output.
    safe=re.sub(r'\bsk-[A-Za-z0-9_-]+','[redacted]',note)[:1000]
    company.db.execute('INSERT OR IGNORE INTO failure_notifications(id,workflow,project,stage,note) VALUES (?,?,?,?,?)',
                       (identifier,workflow,project,stage,safe))
    return identifier


def send_failure(company, identifier, config, root, gmail_factory=None):
    initialize(company)
    row=company.db.execute('SELECT * FROM failure_notifications WHERE id=?',(identifier,)).fetchone()
    if not row:raise PolicyError('Unknown failure notification')
    if row['status']!='pending':return {'status':row['status']}
    g=config.get('gmail',{})
    if not g.get('founder') or not g.get('token_file'):raise GmailError('Configure Gmail for failure alerts')
    setting=company.db.execute("SELECT value FROM runtime_settings WHERE key='dashboard_origin'").fetchone()
    origin=dashboard_origin(setting[0] if setting else config.get('dashboard_origin','http://127.0.0.1:3000'))
    link=origin+'/?'+urlencode({'project':row['project'] or '', 'retry':row['workflow']})
    p=company.db.execute('SELECT budget,spent FROM projects WHERE id=?',(row['project'],)).fetchone()
    allowance=str(p['budget']-p['spent'])+' internal units remaining' if p else 'No project allowance available'
    msg=EmailMessage();msg['From']=g['founder'];msg['To']=g['founder']
    msg['Subject']='Company automation stopped: '+row['stage']
    msg['Message-ID']='<failure-'+identifier+'@company.local>'
    body='Automation stopped.\nProject: '+str(row['project'])+'\nStage: '+row['stage']+'\nReason: '+row['note']+'\n'+allowance+'\n\nReview and retry: '+link+'\n\nThe link opens your local dashboard. Review the blocker and confirm before paid work resumes. Unknown external outcomes cannot be retried automatically.'
    msg.set_content(body)
    msg.add_alternative('<p>'+html.escape(body).replace('\n','<br>')+'</p><p><a href="'+html.escape(link,quote=True)+'" style="padding:12px 20px;background:#2563eb;color:white;text-decoration:none">Review &amp; retry</a></p>',subtype='html')
    mail=gmail_factory() if gmail_factory else Gmail(Path(root)/g['token_file'],g['founder'])
    with company.transaction():
        changed=company.db.execute("UPDATE failure_notifications SET status='sending' WHERE id=? AND status='pending'",(identifier,)).rowcount
        if not changed:return {'status':'already_claimed'}
        company.event('failure.email.sending',notification=identifier,workflow=row['workflow'])
    try:
        result=mail.send(msg)
        if not isinstance(result,dict) or not isinstance(result.get('id'),str):
            raise GmailError('Send outcome unverified')
    except Exception:
        with company.transaction():
            company.db.execute("UPDATE failure_notifications SET status='unknown' WHERE id=?",(identifier,))
            company.event('failure.email.unknown',notification=identifier)
        raise GmailError('Failure email outcome unknown; no automatic resend') from None
    with company.transaction():
        company.db.execute("UPDATE failure_notifications SET status='sent',gmail_id=? WHERE id=?",(result['id'],identifier))
        company.event('failure.email.sent',notification=identifier,workflow=row['workflow'])
    return {'status':'sent'}
