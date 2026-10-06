"""Local OpenAI credential storage. Values are never returned, logged or audited."""
import os
import re
import tempfile
from pathlib import Path
from core import PolicyError

def secret_path(config):
 root=Path(config).resolve().parent
 directory=root/'.secrets'
 if directory.exists() and (directory.is_symlink() or directory.resolve()!=directory):raise PolicyError('Credential directory must be local, not a symlink')
 return directory/'openai-key'

def valid_key(value):return isinstance(value,str) and bool(re.fullmatch(r'sk-[A-Za-z0-9_-]{20,500}',value))

def load_local_credentials(config):
 if os.environ.get('OPENAI_API_KEY'):return
 path=secret_path(config)
 if not path.exists():return
 if path.is_symlink() or not path.is_file() or path.stat().st_size>600:raise PolicyError('Local OpenAI credential file invalid')
 value=path.read_text().strip()
 if not valid_key(value):raise PolicyError('Local OpenAI credential format invalid')
 os.environ['OPENAI_API_KEY']=value

def configure_openai(config,value):
 if not valid_key(value):raise ValueError('Enter a valid OpenAI key locally; its value will not be displayed')
 path=secret_path(config);path.parent.mkdir(mode=0o700,exist_ok=True)
 if path.is_symlink():raise PolicyError('Credential file must not be a symlink')
 name=None
 try:
  with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as stream:
   name=stream.name;os.chmod(name,0o600);stream.write(value+'\n');stream.flush();os.fsync(stream.fileno())
  os.replace(name,path);os.environ['OPENAI_API_KEY']=value
 finally:
  if name and Path(name).exists():Path(name).unlink()
 return {'configured':True,'verification':'Stored locally; provider acceptance not verified'}
