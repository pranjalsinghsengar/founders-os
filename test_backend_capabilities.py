import json
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch,Mock
from core import Company,PolicyError
from workspace import setup_workspace,get_workspace
from isolated_python import run_tests


class BackendCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.c=Company(str(self.root/'db'));self.p,d=self.c.project({'title':'Fixture backend'},100)
        self.c.approve_local(self.p,d);setup_workspace(self.c,self.p,self.root/'products')
        self.w=get_workspace(self.c,self.p)
    def tearDown(self):self.c.db.close();self.tmp.cleanup()
    def test_isolated_discovery_can_import_sibling_product_module(self):
        snapshot=self.root/'snapshot';(snapshot/'tests').mkdir(parents=True)
        (snapshot/'fixture_module.py').write_text('VALUE=42\n')
        (snapshot/'tests/test_fixture.py').write_text(
            'import unittest\nfrom fixture_module import VALUE\n'
            'class ImportTest(unittest.TestCase):\n'
            ' def test_value(self): self.assertEqual(VALUE,42)\n')
        original=subprocess.run([sys.executable,'-I','-B','-m','unittest','discover',
            '-s',str(snapshot/'tests')],cwd=snapshot,capture_output=True,text=True)
        self.assertNotEqual(original.returncode,0)
        self.assertIn('ModuleNotFoundError',original.stderr)
        from isolated_python import TEST_BOOTSTRAP
        fixed=subprocess.run([sys.executable,'-I','-B','-c',
            TEST_BOOTSTRAP.replace('/product',str(snapshot))],cwd=snapshot,capture_output=True,text=True)
        self.assertEqual(fixed.returncode,0,fixed.stderr)
        self.assertIn('Ran 1 test',fixed.stderr)
    def test_python_and_typescript_source_allowed_but_paths_stay_scoped(self):
        for path in ('backend/app.py','web/page.tsx','web/types.ts','pyproject.toml'):
            self.w.write_file(path,'pass' if path.endswith('.py') else 'fixture')
        for path in ('../app.py','.secrets/key.py','backend/.env','backend/app.sh'):
            with self.assertRaises(PolicyError):self.w.write_file(path,'fixture')
        self.assertTrue(self.w.check_python()['passed'])
        self.w.write_file('backend/broken.py','def invalid(:')
        self.assertFalse(self.w.check_python()['passed'])
    def test_missing_product_read_is_recoverable_without_relaxing_path_checks(self):
        result=self.w.read_file('tests/test_community.py')
        self.assertEqual(result['error'],'file_not_found')
        self.assertFalse(result['exists'])
        self.assertNotIn('content',result)
        self.assertFalse((self.w.root/'tests/test_community.py').exists())
        for path in ('../test.py','.secrets/key.py','/tmp/test.py'):
            with self.assertRaises(PolicyError):self.w.read_file(path)
        self.w.write_file('tests/test_community.py','fixture')
        self.assertEqual(self.w.read_file('tests/test_community.py')['content'],'fixture')
    def test_qa_writes_are_limited_to_test_scripts_and_prefixed_reports(self):
        for path in ('tests/test_performance.py','docs/qa_bug_log.md','docs/qa_results.json'):
            self.w.write_qa_file(path,'fixture')
            self.assertEqual(self.w.read_file(path)['content'],'fixture')
        for path in ('backend/storage_api.py','frontend/page.jsx','docs/design.md','tests/helper.py','../tests/test_bad.py'):
            with self.assertRaises(PolicyError):self.w.write_qa_file(path,'fixture')
    def test_test_runner_requires_pinned_image_and_tests(self):
        self.assertFalse(run_tests(self.w,None)['passed'])
        with patch('isolated_python.shutil.which',return_value='/bin/docker'):
            self.assertFalse(run_tests(self.w,'sha256:'+'a'*64)['passed'])
            self.assertFalse(run_tests(self.w,'python:latest')['passed'])
    def test_runner_command_is_offline_readonly_and_does_not_forward_secrets(self):
        self.w.write_file('tests/test_fixture.py','fixture')
        def fake(command,**kwargs):
            if 'branch' in command:return Mock(returncode=0,stdout=b'product')
            self.assertIn('--network=none',command);self.assertIn('--read-only',command)
            self.assertIn('--pull=never',command);self.assertIn('--cap-drop=ALL',command)
            from isolated_python import TEST_BOOTSTRAP
            self.assertEqual(command[command.index('-c')+1],TEST_BOOTSTRAP)
            self.assertIn("sys.path.insert(0, '/product')",TEST_BOOTSTRAP)
            self.assertNotIn('OPENAI_API_KEY',kwargs['env'])
            self.assertNotIn(str(self.w.root),command)
            mount=command[command.index('--mount')+1]
            snapshot=Path(mount.split('source=')[1].split(',')[0])
            self.assertTrue((snapshot/'tests/test_fixture.py').is_file())
            self.assertFalse((snapshot/'.git').exists())
            kwargs['stdout'].write(b'Ran 1 test in 0.1s\nOK\n')
            return Mock(returncode=0)
        with patch('isolated_python.shutil.which',return_value='/bin/docker'),patch('isolated_python.subprocess.run',side_effect=fake),patch.dict('os.environ',{'OPENAI_API_KEY':'synthetic-secret'}):
            result=run_tests(self.w,'sha256:'+'a'*64)
        self.assertTrue(result['passed']);self.assertEqual(result['test_count'],1)
    def test_zero_tests_never_certifies_success(self):
        self.w.write_file('tests/test_fixture.py','fixture')
        def fake(command,**kwargs):
            if 'branch' in command:return Mock(returncode=0,stdout=b'product')
            kwargs['stdout'].write(b'Ran 0 tests in 0.1s\nOK\n');return Mock(returncode=0)
        with patch('isolated_python.shutil.which',return_value='/bin/docker'),patch('isolated_python.subprocess.run',side_effect=fake):
            self.assertFalse(run_tests(self.w,'sha256:'+'a'*64)['passed'])
