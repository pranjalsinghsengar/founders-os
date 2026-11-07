"""Approved local repository tools scoped to one running task and project."""
import argparse
from core import Company, PolicyError
from workspace import get_workspace
from mcp.server.fastmcp import FastMCP

parser=argparse.ArgumentParser()
parser.add_argument('--db',required=True)
parser.add_argument('--task',required=True)
parser.add_argument('--config')
args=parser.parse_args()
mcp=FastMCP('Company scoped repository')


def invoke(name, action):
    company=Company(args.db)
    try:
        row=company.db.execute('SELECT t.*,p.approved,p.paused FROM tasks t JOIN projects p ON p.id=t.project WHERE t.id=?',(args.task,)).fetchone()
        if not row or row['status']!='running' or not row['approved'] or row['paused']:
            raise PolicyError('Tool requires its bound running approved task')
        if not company.db.execute('SELECT 1 FROM grants WHERE project=? AND role=? AND tool=?',
                                  (row['project'],row['owner'],'workspace/'+name)).fetchone():
            raise PolicyError('Scoped repository permission denied')
        return action(get_workspace(company,row['project']))
    finally:company.db.close()


@mcp.tool()
def list_files() -> dict:
    """List permitted files in this task's approved product repository."""
    return invoke('list_files',lambda w:{'files':w.list_files()})


@mcp.tool()
def read_file(path:str) -> dict:
    """Read one relative product file; secrets and outside paths are inaccessible."""
    return invoke('read_file',lambda w:w.read_file(path))


@mcp.tool()
def write_file(path:str,content:str) -> dict:
    """Create or replace an allowed relative product file; no program execution."""
    return invoke('write_file',lambda w:w.write_file(path,content))


@mcp.tool()
def write_qa_file(path:str,content:str) -> dict:
    """Write only tests/test_*.py or docs/qa_*.md/json; cannot modify application source."""
    def write(workspace):
        try:return workspace.write_qa_file(path,content)
        except PolicyError as error:
            if str(error)!='QA writes require tests/test_*.py or docs/qa_*.md/json; application source is read-only':raise
            return {'written':False,'error':'qa_artifact_path',
                    'allowed_paths':['tests/test_*.py','docs/qa_*.md','docs/qa_*.json'],
                    'message':'Choose a permitted QA artifact path; no file was modified'}
    return invoke('write_qa_file',write)


@mcp.tool()
def checkpoint(message:str) -> dict:
    """Commit permitted product files on the local product branch; no push."""
    return invoke('checkpoint',lambda w:w.checkpoint(message))


@mcp.tool()
def inspect() -> dict:
    """Return file hashes and branch identity for independently checked evidence."""
    return invoke('inspect',lambda w:w.inspect())


@mcp.tool()
def check_python() -> dict:
    """Parse Python source for syntax errors; no code execution or security certification."""
    return invoke('check_python',lambda w:w.check_python())


@mcp.tool()
def test_python() -> dict:
    """Run tests/test_*.py in a configured isolated offline Docker container; no host credentials."""
    def run(workspace):
        import json
        from pathlib import Path
        from isolated_python import run_tests
        config=Path(args.config) if args.config else Path(args.db).resolve().parent/'company.config.json'
        if not config.is_file():return {'passed':False,'blocker':'Python test image not configured','verification':'Tests not executed'}
        cfg=json.loads(config.read_text())
        return run_tests(workspace,cfg.get('python_test_image'))
    return invoke('test_python',run)


if __name__=='__main__':mcp.run(transport='stdio')
