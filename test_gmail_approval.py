import base64
import json
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from core import Company, PolicyError
from gmail_approval import EmailApprovals, GmailError, save_private


class FakeGmail:
    founder = 'founder@example.com'
    def __init__(self):
        self.calls = 0
        self.messages = []
        self.fail = False
    def send(self, message):
        self.calls += 1
        self.messages.append({'id': 'out', 'threadId': 'thread', 'labelIds': ['SENT'],
                              'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()})
        if self.fail:
            raise RuntimeError('Fixture ambiguous delivery')
        return {'id':'out', 'threadId':'thread'}
    def sent(self, query):
        return iter(self.messages)
    def get_message(self, identifier):
        return next(item for item in self.messages if item['id']==identifier)


class EmailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'db')
        self.c = Company(self.path)
        self.p, self.digest = self.c.project({'title':'Synthetic fixture', 'authority_requested': ['local development']}, 100)
        self.gmail = FakeGmail()
        self.clock = 1000
        self.gateway = EmailApprovals(self.c, self.gmail, lambda: self.clock)
        self.request = self.gateway.prepare(self.p, 60)
        self.gateway.send(self.request)
    def tearDown(self):
        self.c.db.close()
        self.tmp.cleanup()
    def reply(self, verb='APPROVE', sender=None, labels=None, thread='thread', binding=None):
        r = self.c.db.execute('SELECT * FROM email_requests WHERE id=?', (self.request,)).fetchone()
        msg = EmailMessage()
        msg['From'] = sender or self.gmail.founder
        msg['To'] = self.gmail.founder
        msg['Subject'] = 'Re: Company investment approval ' + self.request
        msg['In-Reply-To'] = r['rfc_id']
        msg.set_content(verb + ' ' + self.request + ' ' + (binding or r['binding']) + '\n\n> quoted request')
        return {'id':'reply-' + self.request, 'threadId':thread, 'labelIds':['SENT'] if labels is None else labels,
                'internalDate':str(self.clock * 1000), 'raw':base64.urlsafe_b64encode(msg.as_bytes()).decode()}
    def approved(self):
        return self.c.db.execute('SELECT approved FROM projects WHERE id=?', (self.p,)).fetchone()[0]
    def test_valid_approval_restart_and_duplicate(self):
        item = self.reply()
        self.assertEqual(self.gateway.consume(self.request,item), 'APPROVE')
        self.assertEqual(self.approved(), 1)
        self.c.db.close(); self.c = Company(self.path)
        self.gateway = EmailApprovals(self.c, self.gmail, lambda:self.clock)
        self.assertIsNone(self.gateway.consume(self.request,item))
        self.assertEqual(self.c.db.execute('SELECT COUNT(*) FROM email_decisions').fetchone()[0],1)
    def test_spoofed_inbox_or_wrong_sender_or_thread(self):
        for item in (self.reply(labels=['INBOX']), self.reply(sender='attacker@example.com'),
                     self.reply(thread='different'), self.reply(binding='0'*64)):
            with self.assertRaises(PolicyError): self.gateway.consume(self.request,item)
        self.assertEqual(self.approved(),0)
    def test_expiration_and_budget_binding(self):
        self.clock = 1061
        with self.assertRaises(PolicyError): self.gateway.consume(self.request,self.reply())
        self.clock = 1000
        self.c.db.execute('UPDATE projects SET budget=200 WHERE id=?',(self.p,))
        with self.assertRaises(PolicyError): self.gateway.consume(self.request,self.reply())
        self.assertEqual(self.approved(),0)
    def test_reject_and_changes_do_not_authorize(self):
        self.assertEqual(self.gateway.consume(self.request,self.reply('REJECT')),'REJECT')
        self.assertEqual(self.approved(),0)
        self.assertIsNone(self.gateway.consume(self.request,self.reply('APPROVE')))
        p,_ = self.c.project({'authority_requested':['fixture']},10)
        self.request = self.gateway.prepare(p,60); self.gateway.send(self.request)
        self.assertEqual(self.gateway.consume(self.request,self.reply('CHANGES')),'CHANGES')
    def test_duplicate_prepare_and_send(self):
        self.assertEqual(self.gateway.prepare(self.p,60),self.request)
        self.assertEqual(self.gateway.send(self.request),'sent')
        self.assertEqual(self.gmail.calls,1)
    def test_unknown_delivery_reconciled_without_resending(self):
        p,_ = self.c.project({'authority_requested':['fixture']},10)
        request = self.gateway.prepare(p,60)
        self.gmail.fail = True
        with self.assertRaises(GmailError): self.gateway.send(request)
        with self.assertRaises(PolicyError): self.gateway.send(request)
        self.assertEqual(self.gateway.reconcile(request),'sent')
        self.assertEqual(self.gmail.calls,2)
    def test_attachment_is_exact_proposal(self):
        msg = self.gateway.message(self.request)
        attachment = next(msg.iter_attachments())
        stored = self.c.db.execute('SELECT proposal FROM projects WHERE id=?',(self.p,)).fetchone()[0]
        self.assertEqual(attachment.get_content(),stored.encode())
    def test_expired_replacement_invalidates_old(self):
        self.clock = 1061
        replacement = self.gateway.prepare(self.p,60)
        self.assertNotEqual(replacement,self.request)
        self.assertEqual(self.c.db.execute('SELECT state FROM email_requests WHERE id=?',(self.request,)).fetchone()[0],'superseded')
    def test_pause_blocks_and_noncommand_ignored(self):
        self.assertIsNone(self.gateway.consume(self.request,self.reply('yes')))
        self.c.pause(self.p)
        with self.assertRaises(PolicyError): self.gateway.consume(self.request,self.reply())
    def test_poll_approves_only_reply(self):
        self.gmail.messages.append(self.reply())
        self.assertEqual(self.gateway.poll(),[{'request':self.request,'decision':'APPROVE'}])
        self.assertEqual(self.gateway.poll(),[])
    def test_gmail_rewritten_message_id_and_wrapped_command(self):
        from gmail_approval import decode
        original=self.gmail.messages[0]
        msg=decode(original)
        msg.replace_header('Message-ID','<gmail-rewritten@example.com>')
        original['raw']=base64.urlsafe_b64encode(msg.as_bytes()).decode()
        item=self.reply();reply=decode(item)
        reply.replace_header('In-Reply-To','<gmail-rewritten@example.com>')
        r=self.c.db.execute('SELECT binding FROM email_requests WHERE id=?',(self.request,)).fetchone()
        reply.set_content('APPROVE '+self.request+'\n'+r['binding']+'\n\n> quoted request')
        item['raw']=base64.urlsafe_b64encode(reply.as_bytes()).decode()
        self.gmail.messages.append(item)
        self.assertEqual(self.gateway.poll(),[{'request':self.request,'decision':'APPROVE'}])
        self.assertEqual(self.approved(),1)
    def test_wrong_original_attachment_cannot_change_reply_binding(self):
        from gmail_approval import decode
        item=self.gmail.messages[0];msg=decode(item)
        next(msg.iter_attachments()).set_content(b'wrong proposal',maintype='application',subtype='json')
        item['raw']=base64.urlsafe_b64encode(msg.as_bytes()).decode()
        self.gmail.messages.append(self.reply())
        with self.assertRaises(PolicyError):self.gateway.poll()
        self.assertEqual(self.approved(),0)
    def test_quoted_or_embedded_approval_is_never_parsed(self):
        from gmail_approval import decode
        for prefix in ('My reply\n','> ','Please '):
            item=self.reply();msg=decode(item)
            body=msg.get_content();msg.set_content(prefix+body)
            item['raw']=base64.urlsafe_b64encode(msg.as_bytes()).decode()
            self.assertIsNone(self.gateway.consume(self.request,item))
        self.assertEqual(self.approved(),0)
    def test_authority_required(self):
        p,_ = self.c.project({'title':'No authority'},100)
        with self.assertRaises(PolicyError): self.gateway.prepare(p)
    def test_token_file_private(self):
        token = Path(self.tmp.name) / 'token.json'
        save_private(token,'fixture')
        self.assertEqual(token.stat().st_mode & 0o777,0o600)
        save_private(token,'replacement')
        self.assertEqual(token.read_text(),'replacement')


class TransportTests(unittest.TestCase):
    def test_api_transport_refresh_persistence_and_error_redaction(self):
        from unittest.mock import Mock
        from gmail_approval import Gmail
        with tempfile.TemporaryDirectory() as folder:
            gateway = Gmail.__new__(Gmail)
            gateway.token_file = Path(folder) / 'token.json'
            gateway.credentials = Mock()
            gateway.credentials.to_json.return_value = '{"fixture":true}'
            gateway.session = Mock()
            response = gateway.session.request.return_value
            response.json.return_value = {'emailAddress':'founder@example.com'}
            self.assertEqual(gateway.profile(),'founder@example.com')
            args, kwargs = gateway.session.request.call_args
            self.assertEqual(args,('GET','https://gmail.googleapis.com/gmail/v1/users/me/profile'))
            self.assertEqual(kwargs['timeout'],30)
            self.assertEqual(gateway.token_file.stat().st_mode & 0o777,0o600)
            gateway.session.request.side_effect = RuntimeError('sensitive-provider-detail')
            with self.assertRaises(GmailError) as error: gateway.profile()
            self.assertNotIn('sensitive-provider-detail', str(error.exception))
    def test_sent_pagination_and_raw_fetch(self):
        from unittest.mock import Mock
        from gmail_approval import Gmail
        gateway = Gmail.__new__(Gmail)
        gateway.request = Mock(side_effect=[{'messages':[{'id':'a'}], 'nextPageToken':'next'},
                                           {'id':'a','raw':'fixture'}, {'messages':[{'id':'b'}]},
                                           {'id':'b','raw':'fixture'}])
        self.assertEqual([r['id'] for r in gateway.sent('fixture-query')],['a','b'])
        calls = gateway.request.call_args_list
        self.assertEqual(calls[0].kwargs['params']['labelIds'],'SENT')
        self.assertEqual(calls[2].kwargs['params']['pageToken'],'next')
        self.assertEqual(calls[1].kwargs['params'],{'format':'raw'})
