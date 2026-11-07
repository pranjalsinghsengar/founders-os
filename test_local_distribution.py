import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from core import Company, PolicyError
from local_ai import discover_local_ai, select_local_ai
from project_export import export_project
from workspace import setup_workspace, get_workspace


class LocalDistributionTests(unittest.TestCase):
    def test_discovery_and_preference_do_not_claim_connection(self):
        with tempfile.TemporaryDirectory() as temporary, patch('local_ai.shutil.which', side_effect=lambda name: '/bin/codex' if name == 'codex' else None):
            found = discover_local_ai()
            self.assertTrue(found[0]['installed'])
            self.assertFalse(found[1]['installed'])
            self.assertFalse(found[0]['runtime_connected'])
            path = Path(temporary) / 'config.json'
            path.write_text(json.dumps({'model': 'existing', 'gmail': {'founder': 'fixture'}}))
            selected=select_local_ai(path, 'codex')
            self.assertTrue(selected['runtime_connected'])
            self.assertEqual(json.loads(path.read_text())['model_runtime'],'codex_cli')
            self.assertEqual(json.loads(path.read_text())['model'], 'existing')
            with self.assertRaises(PolicyError): select_local_ai(path, 'claude')
            link = Path(temporary) / 'link.json'; link.symlink_to(path)
            with self.assertRaises(PolicyError): select_local_ai(link, 'codex')

    def test_export_contains_real_source_hashes_and_honest_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); c = Company(str(root/'db'))
            try:
                project, digest = c.project({'title': 'Fixture source export'}, 100)
                with self.assertRaises(PolicyError): export_project(c, project, root/'exports')
                c.approve_local(project, digest)
                setup_workspace(c, project, root/'workspaces')
                w = get_workspace(c, project)
                with self.assertRaises(PolicyError): export_project(c, project, root/'exports')
                w.write_file('index.html', '<title>Actual fixture source</title>')
                (w.root/'.env').write_text('private fixture')
                (w.root/'link.txt').symlink_to(root/'db')
                result = export_project(c, project, root/'exports')
                with zipfile.ZipFile(result['archive']) as archive:
                    self.assertEqual(set(archive.namelist()), {'code/index.html', 'manifest.json'})
                    manifest = json.loads(archive.read('manifest.json'))
                    self.assertFalse(manifest['release_certified'])
                    self.assertEqual(manifest['files'][0]['sha256'], hashlib.sha256(archive.read('code/index.html')).hexdigest())
                w.write_file('credentials.json', '{}')
                with self.assertRaises(PolicyError): export_project(c, project, root/'exports')
            finally: c.db.close()

class LocalCLIPathTests(unittest.TestCase):
    def test_extension_binary_detected_without_path_and_saved(self):
        from local_ai import resolve_local_ai
        with tempfile.TemporaryDirectory() as temporary, patch('local_ai.shutil.which',return_value=None),patch('local_ai.Path.home',return_value=Path(temporary)):
            binary=Path(temporary)/'.vscode/extensions/openai.chatgpt-fixture/bin/macos-aarch64/codex'
            binary.parent.mkdir(parents=True);binary.write_text('fixture');binary.chmod(0o700)
            self.assertEqual(resolve_local_ai('codex'),str(binary.resolve()))
            config=Path(temporary)/'config.json';config.write_text('{}')
            select_local_ai(config,'codex')
            self.assertEqual(json.loads(config.read_text())['codex_executable'],str(binary.resolve()))
            self.assertIsNone(resolve_local_ai('claude'))
    def test_missing_or_nonexecutable_explicit_path_rejected(self):
        from local_ai import resolve_local_ai
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary)/'codex';p.write_text('fixture');p.chmod(0o600)
            self.assertIsNone(resolve_local_ai('codex',str(p)))
            self.assertIsNone(resolve_local_ai('codex',str(p.parent/'missing')))
