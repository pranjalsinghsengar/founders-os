import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import Company,PolicyError
from repository_remote import create_remote,push_remote,reconcile_remote,remote_row,validate_target
from workspace import setup_market_workspace,get_workspace,git

class RemoteTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.c=Company(str(self.root/'db'));self.p,d=self.c.project({'title':'Synthetic product','market':'Creative agencies'},100);self.c.approve_local(self.p,d);setup_market_workspace(self.c,self.p,self.root/'workspaces');self.w=get_workspace(self.c,self.p)
 def tearDown(self):self.c.db.close();self.tmp.cleanup()
 def info(self,*args):return json.dumps({'nameWithOwner':'fixture/product','url':'https://github.com/fixture/product','isPrivate':True})
 def test_market_grouping_preserves_existing_registered_root(self):
  self.assertEqual(self.w.root.parent.name,'creative-agencies');self.assertEqual(setup_market_workspace(self.c,self.p,self.root/'workspaces')['status'],'existing')
 def test_remote_creation_is_private_and_explicit_with_mocked_github(self):
  with patch('repository_remote.gh',side_effect=self.info) as gh:
   result=create_remote(self.c,self.p,'fixture/product')
   self.assertEqual(gh.call_args_list[0].args,('repo','create','fixture/product','--private'))
  self.assertEqual(result['status'],'created');self.assertEqual(git(self.w.root,'remote','get-url','origin'),'https://github.com/fixture/product.git')
  with self.assertRaises(PolicyError):create_remote(self.c,self.p,'fixture/product')
 def test_unknown_creation_is_not_repeated_and_can_be_reconciled(self):
  with patch('repository_remote.gh',side_effect=PolicyError('Synthetic ambiguous outcome')):
   with self.assertRaises(PolicyError):create_remote(self.c,self.p,'fixture/product')
  self.assertEqual(remote_row(self.c,self.p)['status'],'unknown')
  with patch('repository_remote.gh',side_effect=self.info):self.assertEqual(reconcile_remote(self.c,self.p)['status'],'created')
 def test_push_requires_clean_commit_and_verifies_remote_sha(self):
  with patch('repository_remote.gh',side_effect=self.info):create_remote(self.c,self.p,'fixture/product')
  self.w.write_file('index.html','<title>Actual fixture file</title>')
  with self.assertRaises(PolicyError):push_remote(self.c,self.p)
  commit=self.w.checkpoint('Synthetic fixture')['commit']
  import subprocess
  original=subprocess.run
  def run(args,**kwargs):
   if 'push' in args:
    class Result:returncode=0;stdout=b''
    return Result()
   return original(args,**kwargs)
  with patch('repository_remote.subprocess.run',side_effect=run),patch('repository_remote.gh',return_value=json.dumps({'object':{'sha':commit}})):
   result=push_remote(self.c,self.p)
  self.assertEqual(result['commit'],commit);self.assertEqual(remote_row(self.c,self.p)['status'],'pushed')
 def test_unapproved_paused_and_invalid_targets_are_rejected(self):
  for target in ('--public','owner/../../file','https://github.com/x/y','owner/name;evil'):
   with self.assertRaises(ValueError):validate_target(target)
  self.c.pause(self.p)
  with self.assertRaises(PolicyError):create_remote(self.c,self.p,'fixture/product')
 def test_pushurl_redirection_is_rejected(self):
  with patch('repository_remote.gh',side_effect=self.info):create_remote(self.c,self.p,'fixture/product')
  git(self.w.root,'remote','set-url','--push','origin','https://example.com/other.git')
  with self.assertRaises(PolicyError):push_remote(self.c,self.p)

 def test_unknown_push_must_be_reconciled_before_another_push(self):
  with patch('repository_remote.gh',side_effect=self.info):create_remote(self.c,self.p,'fixture/product')
  self.w.write_file('index.html','<title>Fixture</title>');commit=self.w.checkpoint('Fixture commit')['commit']
  import subprocess
  original=subprocess.run
  def fail_push(args,**kwargs):
   if 'push' in args:
    class Result:returncode=1;stdout=b''
    return Result()
   return original(args,**kwargs)
  with patch('repository_remote.subprocess.run',side_effect=fail_push):
   with self.assertRaises(PolicyError):push_remote(self.c,self.p)
  self.assertEqual(remote_row(self.c,self.p)['status'],'push_unknown')
  with self.assertRaises(PolicyError):push_remote(self.c,self.p)
  def remote(*args):return json.dumps({'object':{'sha':commit}}) if args[0]=='api' else self.info()
  with patch('repository_remote.gh',side_effect=remote):self.assertEqual(reconcile_remote(self.c,self.p)['status'],'pushed')
