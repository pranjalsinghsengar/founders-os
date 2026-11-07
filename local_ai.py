"""Discover local CLI installations without starting models or reading credentials."""
import json
import os
import shutil
import tempfile
from pathlib import Path
from core import PolicyError


def resolve_local_ai(provider, executable=None):
    """Find a CLI on PATH or in its known local installation directories."""
    if executable:
        candidate=Path(executable).expanduser()
        return str(candidate.resolve()) if candidate.is_file() and os.access(candidate,os.X_OK) else None
    found=shutil.which(provider)
    if found:
        return found
    if provider!='codex':
        return None
    candidates=[]
    for directory in (Path.home()/'.vscode/extensions',Path.home()/'.cursor/extensions'):
        if directory.is_dir():
            candidates.extend(directory.glob('openai.chatgpt-*/bin/*/codex'))
    candidates=[p for p in candidates if p.is_file() and os.access(p,os.X_OK)]
    candidates.sort(key=lambda p:p.stat().st_mtime,reverse=True)
    return str(candidates[0].resolve()) if candidates else None


def discover_local_ai():
    return [{'id': name, 'installed': bool(resolve_local_ai(name)),
             'authentication': 'not checked', 'runtime_connected': False,
             'adapter_status': 'implemented; select to activate' if name == 'codex' else 'not implemented'} for name in ('codex', 'claude')]


def select_local_ai(config_file, provider):
    if provider not in ('codex', 'claude'):
        raise PolicyError('Choose codex or claude')
    if provider == 'claude':
        raise PolicyError('Claude adapter is not implemented; current runtime preserved')
    executable=resolve_local_ai(provider)
    if not executable:
        raise PolicyError('Codex CLI not found on PATH or in VS Code/Cursor extensions; install Codex CLI and sign in')
    path = Path(config_file)
    if path.is_symlink():
        raise PolicyError('Configuration symlinks are prohibited')
    path = path.resolve()
    cfg = json.loads(path.read_text())
    # Explicit selection activates the adapter; does not start a model call.
    cfg['local_ai_preference'] = provider
    cfg['model_runtime'] = 'codex_cli'
    cfg['codex_executable'] = executable
    fd, temporary = tempfile.mkstemp(prefix='.company-config-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(cfg, handle, indent=2)
            handle.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'selected': provider, 'runtime_connected': True, 'authentication': 'not checked',
            'note': 'Codex CLI selected for new employee/review calls; research evidence adapter remains unavailable'}
