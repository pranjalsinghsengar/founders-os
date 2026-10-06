"""Discover local CLI installations without starting models or reading credentials."""
import json
import os
import shutil
import tempfile
from pathlib import Path
from core import PolicyError


def discover_local_ai():
    return [{'id': name, 'installed': bool(shutil.which(name)),
             'authentication': 'not checked', 'runtime_connected': False,
             'adapter_status': 'not implemented'} for name in ('codex', 'claude')]


def select_local_ai(config_file, provider):
    if provider not in ('codex', 'claude'):
        raise PolicyError('Choose codex or claude')
    if not shutil.which(provider):
        raise PolicyError('Selected AI CLI is not installed on PATH')
    path = Path(config_file)
    if path.is_symlink():
        raise PolicyError('Configuration symlinks are prohibited')
    path = path.resolve()
    cfg = json.loads(path.read_text())
    # Preference is separate from active runtime: detection is not integration.
    cfg['local_ai_preference'] = provider
    fd, temporary = tempfile.mkstemp(prefix='.company-config-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(cfg, handle, indent=2)
            handle.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'selected': provider, 'runtime_connected': False,
            'note': 'Preference saved; current workers still use the configured OpenAI API runtime'}
