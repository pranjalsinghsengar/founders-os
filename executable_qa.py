"""Independent local checks from trusted operator configuration, never model commands.

This executes with operator OS authority; it is not a sandbox. Output is suppressed
and only hashes are recorded to avoid capturing secrets printed by test programs.
"""
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from core import PolicyError


def run_executable_review(company, task, checks, artifact_dir, cost=0):
    row = company.db.execute('SELECT * FROM tasks WHERE id=?', (task,)).fetchone()
    if row is None or row['status'] != 'awaiting_review':
        raise PolicyError('Task must be awaiting review')
    criteria = json.loads(row['payload']).get('acceptance_criteria')
    if not isinstance(criteria, list) or not criteria or set(checks) != set(criteria):
        raise PolicyError('Operator must configure one executable check per acceptance criterion')
    for criterion in criteria:
        check = checks[criterion]
        command = check.get('command')
        if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
            raise ValueError('Check command must be a nonempty argument list')
        if not Path(command[0]).is_absolute() or not Path(check['cwd']).is_absolute():
            raise ValueError('Executable and working directory must be absolute operator-configured paths')
        timeout = check.get('timeout_seconds', 30)
        if type(timeout) is not int or not 1 <= timeout <= 60:
            raise ValueError('Check timeout must be 1..60 seconds')
    reviewer = row['reviewer']
    qa_task = company.task(row['project'], reviewer, 'operator.' + reviewer, 'employee.qa',
                           {'source_task': task, 'source_attempt': row['attempts'], 'verification': 'executable'})
    root = Path(artifact_dir).resolve()
    def work(_):
        results = []
        for criterion in criteria:
            check = checks[criterion]
            # Pause/approval/grant checks immediately before each process starts.
            company.reserve_employee_call(qa_task, 'employee.qa', 0)
            env = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT', 'TMPDIR') if k in os.environ}
            with tempfile.TemporaryFile() as stream:
                try:
                    process = subprocess.run(check['command'], cwd=check['cwd'], env=env,
                        stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                        timeout=check.get('timeout_seconds', 30), check=False)
                    code, timed_out = process.returncode, False
                except subprocess.TimeoutExpired:
                    code, timed_out = None, True
                stream.seek(0)
                digest = hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else _hash_stream(stream)
            results.append({'criterion': criterion, 'passed': code == 0 and not timed_out,
                            'returncode': code, 'timed_out': timed_out, 'output_sha256': digest})
            company.event('qa.check.completed', task=qa_task, passed=code == 0 and not timed_out)
        accepted = all(r['passed'] for r in results)
        decision = {'accepted': accepted, 'note': 'Operator-configured executable checks ' + ('passed' if accepted else 'failed'), 'checks': results}
        root.mkdir(parents=True, exist_ok=True)
        report = root / (qa_task + '.qa.json')
        report.write_text(json.dumps({'source_task': task, 'decision': decision,
                                     'verification': 'Executed local operator-configured commands; coverage limited to these checks'}, indent=2))
        return {'artifact': str(report), 'evidence': str(report), 'decision': decision}
    company.register_tool('employee.qa', work, cost)
    status = company.execute(qa_task)
    if status != 'awaiting_review':
        return {'review_task': qa_task, 'status': status}
    output = json.loads(company.db.execute('SELECT output FROM tasks WHERE id=?', (qa_task,)).fetchone()[0])
    decision = output['decision']
    company.review(task, reviewer, decision['accepted'], decision['note'],
                   expected_output=row['output'], expected_attempts=row['attempts'])
    return {'review_task': qa_task, 'accepted': decision['accepted'],
            'status': company.db.execute('SELECT status FROM tasks WHERE id=?', (task,)).fetchone()[0]}


def _hash_stream(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(65536), b''):
        digest.update(block)
    return digest.hexdigest()
