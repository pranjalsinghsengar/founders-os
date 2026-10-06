"""Export bounded product source with truthful verification metadata."""
import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from core import PolicyError
from workspace import get_workspace


def export_project(company, project, output_dir):
    row = company.db.execute('SELECT * FROM projects WHERE id=?', (project,)).fetchone()
    if not row or not row['approved'] or json.loads(row['proposal']).get('kind') == 'research_mandate':
        raise PolicyError('Export requires an approved product with a code workspace')
    if company.db.execute("SELECT 1 FROM sqlite_master WHERE name='trash'").fetchone():
        if company.db.execute("SELECT 1 FROM trash WHERE kind='project' AND target=?", (project,)).fetchone():
            raise PolicyError('Restore the product before exporting')
    w = get_workspace(company, project)
    files = w.list_files()
    if not files:
        raise PolicyError('No product code exists to export')
    contents = {}
    for name in files:
        target = w.path(name)
        if target.stat().st_size > 60000:
            raise PolicyError('Product file exceeds export limit')
        data = target.read_bytes()
        if target.name in ('gmail-client.json', 'gmail-token.json', 'credentials.json', 'token.json') or re.search(
                rb'\bsk-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----', data):
            raise PolicyError('Credential-like material must be removed before export')
        contents[name] = data
    tasks = [dict(t) for t in company.db.execute(
        'SELECT id,owner,status,attempts FROM tasks WHERE project=? ORDER BY id', (project,))]
    delivery = None
    if company.db.execute("SELECT 1 FROM sqlite_master WHERE name='delivery_runs'").fetchone():
        result = company.db.execute('SELECT status,stage FROM delivery_runs WHERE project=?', (project,)).fetchone()
        delivery = dict(result) if result else None
    manifest = {'project': project, 'format_version': 1, 'delivery': delivery,
                'tasks': tasks, 'release_certified': False,
                'verification': 'Source snapshot only; export does not certify a working or deployed application',
                'files': [{'path': name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
                          for name, data in contents.items()]}
    folder = Path(output_dir)
    if folder.is_symlink():
        raise PolicyError('Export directory symlinks are prohibited')
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='product-', suffix='.zip', dir=folder)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in contents.items():
                archive.writestr('code/' + name, data)
            archive.writestr('manifest.json', json.dumps(manifest, indent=2))
        digest = hashlib.sha256(Path(temporary).read_bytes()).hexdigest()
        destination = folder / (project + '-' + digest[:12] + '.zip')
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    company.event('workspace.exported', project=project, sha256=digest, file_count=len(files))
    return {'project': project, 'archive': str(destination), 'sha256': digest,
            'file_count': len(files), 'release_certified': False}
