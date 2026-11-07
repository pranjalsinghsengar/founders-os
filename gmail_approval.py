"""Founder-account Gmail OAuth approval. No model sees mail credentials.

Only commands retrieved from the authenticated founder's SENT mailbox qualify.
From headers alone never authorize anything. This adapter sends only to that
same founder account; it is not a general employee messaging capability.
"""
import base64
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import quote
from core import PolicyError

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/gmail.send']


class GmailError(Exception):
    """Safe error message: never expose provider response bodies or credentials."""


def save_private(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Gmail:
    def __init__(self, token_file, founder):
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import AuthorizedSession
            self.token_file = Path(token_file)
            if self.token_file.stat().st_mode & 0o077:
                raise GmailError('Gmail token file must have permissions 600')
            self.credentials = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
            if not self.credentials.has_scopes(SCOPES):
                raise GmailError('Reconnect Gmail with required scopes')
            self.session = AuthorizedSession(self.credentials)
            self.founder = founder.lower()
            if self.profile().lower() != self.founder:
                raise GmailError('Connected Gmail account does not match configured founder')
        except GmailError:
            raise
        except Exception:
            raise GmailError('Gmail unavailable; check dependencies, token file and account connection') from None

    def request(self, method, path, **kwargs):
        try:
            response = self.session.request(method, 'https://gmail.googleapis.com/gmail/v1/users/me/' + path,
                                            timeout=30, **kwargs)
            response.raise_for_status()
            result = response.json()
            save_private(self.token_file, self.credentials.to_json())
            return result
        except Exception:
            raise GmailError('Gmail API request failed; no automatic write retry') from None

    def profile(self):
        return self.request('GET', 'profile')['emailAddress']

    def send(self, message):
        return self.request('POST', 'messages/send', json={
            'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()})

    def get_message(self, identifier):
        return self.request('GET','messages/' + quote(identifier,safe=''),params={'format':'raw'})

    def sent(self, query):
        cursor = None
        for _ in range(20):
            params = {'labelIds': 'SENT', 'q': query, 'maxResults': 100}
            if cursor:
                params['pageToken'] = cursor
            page = self.request('GET', 'messages', params=params)
            for item in page.get('messages', []):
                yield self.request('GET', 'messages/' + quote(item['id'], safe=''), params={'format': 'raw'})
            cursor = page.get('nextPageToken')
            if not cursor:
                return
        raise GmailError('Gmail scan limit reached; narrow or reconcile pending requests')


def connect(client_file, token_file, founder):
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import AuthorizedSession
        credentials = InstalledAppFlow.from_client_secrets_file(
            str(client_file), SCOPES, autogenerate_code_verifier=True).run_local_server(
            host='127.0.0.1', port=0, timeout_seconds=180,
            authorization_prompt_message='Complete Gmail authorization in your browser.',
            success_message='Gmail authorization received. You can close this window.')
        response = AuthorizedSession(credentials).get(
            'https://gmail.googleapis.com/gmail/v1/users/me/profile', timeout=30)
        response.raise_for_status()
        if response.json()['emailAddress'].lower() != founder.lower():
            raise GmailError('Selected Gmail account does not match founder; token not saved')
        save_private(token_file, credentials.to_json())
    except GmailError:
        raise
    except Exception:
        raise GmailError('Gmail connection failed; check Desktop OAuth client and local authorization') from None


class EmailApprovals:
    def __init__(self, company, gmail, now=time.time):
        self.company, self.gmail, self.now = company, gmail, now
        company.db.executescript('''
        CREATE TABLE IF NOT EXISTS email_requests (
          id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id),
          binding TEXT NOT NULL, founder TEXT NOT NULL, expires INTEGER NOT NULL,
          state TEXT NOT NULL, rfc_id TEXT NOT NULL, gmail_id TEXT, thread_id TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS one_pending_email ON email_requests(project)
          WHERE state IN ('prepared','sending','unknown','sent');
        CREATE TABLE IF NOT EXISTS email_decisions (
          message_id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE REFERENCES email_requests(id),
          decision TEXT NOT NULL, at INTEGER NOT NULL);
        ''')
        if 'gmail_rfc_id' not in {r[1] for r in company.db.execute('PRAGMA table_info(email_requests)')}:
            company.db.execute('ALTER TABLE email_requests ADD COLUMN gmail_rfc_id TEXT')

    @staticmethod
    def binding(project):
        return hashlib.sha256(json.dumps({'project': project['id'], 'digest': project['digest'],
            'budget': project['budget'], 'proposal': project['proposal']}, sort_keys=True).encode()).hexdigest()

    def prepare(self, project, lifetime=86400):
        if type(lifetime) is not int or not 60 <= lifetime <= 604800:
            raise ValueError('Approval lifetime must be 60 seconds..7 days')
        c = self.company
        with c.transaction():
            row = c.db.execute('SELECT * FROM projects WHERE id=?', (project,)).fetchone()
            if row is None or row['approved'] or row['paused']:
                raise PolicyError('Email request requires an unapproved active proposal')
            proposal = json.loads(row['proposal'])
            if not isinstance(proposal, dict) or not proposal.get('authority_requested'):
                raise PolicyError('Proposal must include explicit authority_requested')
            previous = c.db.execute("SELECT * FROM email_requests WHERE project=? AND state IN ('prepared','sending','unknown','sent')", (project,)).fetchone()
            if previous:
                if previous['state'] in ('sending', 'unknown'):
                    raise PolicyError('Reconcile ambiguous delivery before preparing another request')
                if previous['expires'] > self.now() and previous['binding'] == self.binding(row):
                    return previous['id']
                c.db.execute("UPDATE email_requests SET state='superseded' WHERE id=?", (previous['id'],))
            terminal = c.db.execute("SELECT 1 FROM email_requests WHERE project=? AND binding=? AND state IN ('rejected','changes_requested')",
                                    (project, self.binding(row))).fetchone()
            if terminal:
                raise PolicyError('Rejected or changed proposal requires a new proposal version')
            identifier = str(uuid.uuid4())
            c.db.execute('INSERT INTO email_requests(id,project,binding,founder,expires,state,rfc_id) VALUES (?,?,?,?,?,?,?)',
                (identifier, project, self.binding(row), self.gmail.founder, int(self.now()) + lifetime,
                 'prepared', '<company-' + identifier + '@approval.local>'))
            c.event('approval.email.prepared', request=identifier, project=project)
            return identifier

    def message(self, request):
        c = self.company
        r = c.db.execute('SELECT * FROM email_requests WHERE id=?', (request,)).fetchone()
        if r is None:
            raise PolicyError('Unknown email request')
        p = c.db.execute('SELECT * FROM projects WHERE id=?', (r['project'],)).fetchone()
        proposal = json.loads(p['proposal'])
        msg = EmailMessage()
        msg['From'] = r['founder']; msg['To'] = r['founder']
        msg['Subject'] = 'Company investment approval ' + r['id']
        msg['Message-ID'] = r['rfc_id']
        msg.set_content('Investment proposal: ' + str(proposal.get('title', 'Untitled')) + '\n'
            'Project: ' + p['id'] + '\nProposal SHA256: ' + p['digest'] + '\n'
            'Budget (internal units, not invoice ceiling): ' + str(p['budget']) + '\n'
            'Authority requested: ' + json.dumps(proposal['authority_requested']) + '\n'
            'Expires (UTC epoch): ' + str(r['expires']) + '\n\n'
            'Read the complete attached proposal. Reply from this same Gmail account to this thread. '
            'Put exactly one of these commands on the first nonempty line:\n'
            + '\n'.join(verb + ' ' + r['id'] + ' ' + r['binding'] for verb in ('APPROVE','REJECT','CHANGES'))
            + '\n\nApproval authorizes this proposal only; tool grants remain separately enforced.')
        msg.add_attachment(p['proposal'].encode(), maintype='application', subtype='json', filename='proposal.json')
        return msg

    def send(self, request):
        c = self.company
        with c.transaction():
            r = c.db.execute('SELECT * FROM email_requests WHERE id=?', (request,)).fetchone()
            if r is None:
                raise PolicyError('Unknown email request')
            if r['state'] == 'sent':
                return 'sent'
            if r['state'] != 'prepared':
                raise PolicyError('Ambiguous delivery must be reconciled; never resend automatically')
            p = c.db.execute('SELECT * FROM projects WHERE id=?', (r['project'],)).fetchone()
            self._current(r, p)
            c.db.execute("UPDATE email_requests SET state='sending' WHERE id=?", (request,))
            c.event('approval.email.sending', request=request)
        try:
            result = self.gmail.send(self.message(request))
            if not result.get('id') or not result.get('threadId'):
                raise GmailError('Incomplete Gmail send result')
        except Exception:
            with c.transaction():
                c.db.execute("UPDATE email_requests SET state='unknown' WHERE id=?", (request,))
                c.event('approval.email.unknown', request=request)
            raise GmailError('Delivery outcome unknown; reconcile Sent mail before any further action') from None
        with c.transaction():
            c.db.execute("UPDATE email_requests SET state='sent',gmail_id=?,thread_id=? WHERE id=?", (result['id'], result['threadId'], request))
            c.event('approval.email.sent', request=request)
        return 'sent'

    def _current(self, r, p):
        if r['founder'] != self.gmail.founder or p['paused'] or p['approved'] or r['expires'] <= self.now() or r['binding'] != self.binding(p):
            raise PolicyError('Approval request expired, superseded, paused or belongs to another founder')

    def reconcile(self, request):
        c = self.company
        r = c.db.execute('SELECT * FROM email_requests WHERE id=?', (request,)).fetchone()
        if r is None or r['state'] not in ('sending','unknown') or r['founder'] != self.gmail.founder:
            raise PolicyError('Only ambiguous requests for this founder can be reconciled')
        matches = []
        for item in self.gmail.sent('rfc822msgid:' + r['rfc_id'].strip('<>')):
            msg = decode(item)
            if 'SENT' in item.get('labelIds', []) and msg.get('Message-ID') == r['rfc_id']:
                matches.append(item)
        if len(matches) != 1:
            raise PolicyError('Delivery cannot be uniquely confirmed; request remains blocked')
        with c.transaction():
            c.db.execute("UPDATE email_requests SET state='sent',gmail_id=?,thread_id=? WHERE id=? AND state IN ('sending','unknown')",
                         (matches[0]['id'], matches[0]['threadId'], request))
            c.event('approval.email.reconciled', request=request)
        return 'sent'

    def poll(self):
        c = self.company
        results = []
        rows = c.db.execute("SELECT * FROM email_requests WHERE state='sent'").fetchall()
        for r in rows:
            if not r['gmail_rfc_id']:
                self.record_sent_identity(r['id'],self.gmail.get_message(r['gmail_id']))
            for item in self.gmail.sent('subject:"Company investment approval ' + r['id'] + '"'):
                try:
                    result = self.consume(r['id'], item)
                except (PolicyError, ValueError):
                    continue
                if result:
                    results.append({'request': r['id'], 'decision': result})
        return results

    def record_sent_identity(self, request, item):
        """Bind Gmail's actual RFC identifier to the exact originally sent proposal."""
        c = self.company
        msg = decode(item)
        with c.transaction():
            r = c.db.execute('SELECT * FROM email_requests WHERE id=?',(request,)).fetchone()
            p = c.db.execute('SELECT * FROM projects WHERE id=?',(r['project'],)).fetchone() if r else None
            attachments = list(msg.iter_attachments())
            body = msg.get_body(preferencelist=('plain',))
            text = body.get_content() if body else ''
            message_id = msg.get('Message-ID','')
            if (not r or r['state']!='sent' or not p or item.get('id')!=r['gmail_id'] or
                item.get('threadId')!=r['thread_id'] or 'SENT' not in item.get('labelIds',[]) or
                parseaddr(msg.get('From',''))[1].lower()!=r['founder'] or
                msg.get('Subject')!='Company investment approval '+r['id'] or
                not re.fullmatch(r'<[^\s<>]+@[^\s<>]+>',message_id) or
                len(msg.get_all('Message-ID',[]))!=1 or
                len(attachments)!=1 or attachments[0].get_content()!=p['proposal'].encode() or
                r['binding'] not in text or r['id'] not in text):
                raise PolicyError('Original sent proposal identity could not be verified')
            c.db.execute('UPDATE email_requests SET gmail_rfc_id=? WHERE id=?',(message_id,request))
            c.event('approval.email.identity.verified',request=request)

    def consume(self, request, item):
        """Private adapter boundary: item must come from this authenticated Gmail API."""
        msg = decode(item)
        if 'SENT' not in item.get('labelIds', []) or parseaddr(msg.get('From', ''))[1].lower() != self.gmail.founder:
            raise PolicyError('Approval must originate in authenticated founder Sent mail')
        if len(msg.get_all('From', [])) != 1:
            raise PolicyError('Ambiguous sender')
        body = msg.get_body(preferencelist=('plain',))
        text = body.get_content() if body else (msg.get_content() if msg.get_content_type() == 'text/plain' else '')
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        first = lines[0] if lines else ''
        # Gmail can hard-wrap before or inside the binding token. Fold only
        # adjacent hexadecimal fragments of that token, never quoted mail/prose.
        prefix = re.fullmatch(r'(APPROVE|REJECT|CHANGES) ([a-f0-9-]{36})(?: ([a-f0-9]{1,64}))?',first)
        if prefix:
            binding = prefix[3] or ''
            for fragment in lines[1:4]:
                if len(binding) >= 64 or not re.fullmatch(r'[a-f0-9]{1,64}',fragment):
                    break
                binding += fragment
            first = prefix[1] + ' ' + prefix[2] + ' ' + binding
        command = re.fullmatch(r'(APPROVE|REJECT|CHANGES) ([a-f0-9-]{36}) ([a-f0-9]{64})', first)
        if not command or command[2] != request:
            if prefix and prefix[2] == request:
                code = 'incomplete_command' if len(binding) < 64 else 'invalid_command'
                # Store a fixed diagnostic once per authenticated message, never its body/token.
                if not self.company.db.execute("SELECT 1 FROM events WHERE kind='approval.email.reply.invalid' AND json_extract(details,'$.message')=? AND json_extract(details,'$.request')=?",
                                               (item['id'],request)).fetchone():
                    self.company.event('approval.email.reply.invalid',request=request,message=item['id'],code=code)
            return None
        c = self.company
        with c.transaction():
            r = c.db.execute('SELECT * FROM email_requests WHERE id=?', (request,)).fetchone()
            if r is None:
                raise PolicyError('Unknown request')
            prior = c.db.execute('SELECT 1 FROM email_decisions WHERE message_id=? OR request_id=?', (item['id'],request)).fetchone()
            if prior:
                return None
            p = c.db.execute('SELECT * FROM projects WHERE id=?', (r['project'],)).fetchone()
            self._current(r, p)
            if r['state'] != 'sent' or command[3] != r['binding'] or item.get('threadId') != r['thread_id'] or msg.get('In-Reply-To') != (r['gmail_rfc_id'] or r['rfc_id']):
                raise PolicyError('Approval must match proposal binding and original request thread')
            if int(item['internalDate']) // 1000 > r['expires']:
                raise PolicyError('Late approval')
            decision = command[1]
            c.db.execute('INSERT INTO email_decisions VALUES (?,?,?,?)', (item['id'], request, decision, int(self.now())))
            c.db.execute('UPDATE email_requests SET state=? WHERE id=?',
                         ({'APPROVE':'approved','REJECT':'rejected','CHANGES':'changes_requested'}[decision],request))
            if decision == 'APPROVE':
                c.db.execute('UPDATE projects SET approved=1 WHERE id=?', (r['project'],))
            c.event('proposal.email.decision', project=r['project'], request=request, decision=decision,
                    binding=r['binding'], founder=r['founder'])
            return decision


def decode(item):
    raw = item.get('raw', '')
    if len(raw) > 2000000:
        raise ValueError('Email exceeds approval size limit')
    return BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
