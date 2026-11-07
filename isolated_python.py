"""Fixed offline Python test runner; source snapshot only, no host environment."""
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from core import PolicyError

# Isolated Python omits the working directory from imports. Add only the
# read-only product snapshot, never the orchestration workspace or host PATH.
TEST_BOOTSTRAP="import sys, unittest; sys.path.insert(0, '/product'); unittest.main(module=None, argv=['unittest', 'discover', '-s', '/product/tests', '-v'])"


def run_tests(workspace, image):
    binary=shutil.which('docker')
    if not binary or not isinstance(image,str) or not re.fullmatch(r'sha256:[a-f0-9]{64}',image):
        return {'passed':False,'blocker':'Configure a trusted local Python test image and running Docker daemon',
                'verification':'Tests not executed'}
    files=workspace.list_files()
    tests=[f for f in files if f.startswith('tests/') and Path(f).name.startswith('test_') and f.endswith('.py')]
    if not tests:return {'passed':False,'blocker':'No tests/test_*.py files','verification':'Tests not executed'}
    env={k:os.environ[k] for k in ('PATH','HOME','TMPDIR','SYSTEMROOT') if k in os.environ}
    name='company-qa-'+uuid.uuid4().hex
    before=workspace.inspect()
    with tempfile.TemporaryDirectory(prefix='company-source-') as temporary:
        root=Path(temporary);root.chmod(0o755)
        for f in files:
            if Path(f).name in ('gmail-client.json','gmail-token.json','credentials.json','token.json'):
                raise PolicyError('Credential files cannot enter tests')
            content=workspace.read_file(f)['content']
            if re.search(r'\bsk-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----',content):
                raise PolicyError('Credential-like source material cannot enter tests')
            target=root/f;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(content);target.chmod(0o644)
        command=[binary,'run','--rm','--pull=never','--name',name,'--network=none','--read-only',
            '--cap-drop=ALL','--security-opt=no-new-privileges','--user','65534:65534',
            '--memory=256m','--cpus=1','--pids-limit=128',
            '--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=64m',
            '--mount','type=bind,source='+str(root)+',target=/product,readonly',
            '--workdir','/product','--entrypoint','python',image,'-I','-B','-c',TEST_BOOTSTRAP]
        with tempfile.TemporaryFile() as stream:
            try:
                result=subprocess.run(command,env=env,stdin=subprocess.DEVNULL,stdout=stream,
                                      stderr=subprocess.STDOUT,timeout=60)
                code=result.returncode;timed_out=False
            except subprocess.TimeoutExpired:
                code=None;timed_out=True
                subprocess.run([binary,'rm','--force',name],env=env,stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
            except OSError:
                return {'passed':False,'blocker':'Docker unavailable','verification':'Tests not executed'}
            stream.seek(0);digest=hashlib.file_digest(stream,'sha256').hexdigest()
            stream.seek(0);tail=stream.read(100000).decode(errors='replace')
            count=re.search(r'Ran (\d+) tests? in ',tail)
            failed_tests=re.findall(r'^(?:FAIL|ERROR): (test_[A-Za-z0-9_]+)',tail,re.MULTILINE)
    unchanged=workspace.inspect()==before
    return {'passed':code==0 and not timed_out and unchanged and bool(count) and int(count[1])>0,
            'returncode':code,'timed_out':timed_out,'test_count':int(count[1]) if count else 0,
            'source_unchanged':unchanged,'workspace':before,'output_sha256':digest,
            'failed_tests':failed_tests,
            'verification':'Offline Docker unittest execution; coverage limited to supplied tests, no deployment/TLS certification'}
