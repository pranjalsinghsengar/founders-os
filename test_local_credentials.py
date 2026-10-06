import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import PolicyError
from local_credentials import configure_openai,load_local_credentials
class CredentialTests(unittest.TestCase):
 def test_local_storage_permissions_no_response_disclosure_and_reload(self):
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ):
   cfg=Path(folder)/'config.json';key='sk-synthetic-'+('x'*40)
   result=configure_openai(cfg,key);self.assertNotIn(key,json.dumps(result))
   path=Path(folder)/'.secrets/openai-key';self.assertEqual(path.stat().st_mode&0o777,0o600)
   os.environ.pop('OPENAI_API_KEY',None);load_local_credentials(cfg);self.assertEqual(os.environ['OPENAI_API_KEY'],key)
 def test_invalid_key_and_symlink_directory_refused(self):
  with tempfile.TemporaryDirectory() as folder:
   cfg=Path(folder)/'config.json'
   with self.assertRaises(ValueError):configure_openai(cfg,'invalid')
   outside=Path(folder)/'outside';outside.mkdir();(Path(folder)/'.secrets').symlink_to(outside,target_is_directory=True)
   with self.assertRaises(PolicyError):configure_openai(cfg,'sk-synthetic-'+('x'*40))
