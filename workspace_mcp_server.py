"""Approved local repository tools scoped to one running task and project."""
import argparse
from core import Company, PolicyError
from workspace import get_workspace
from mcp.server.fastmcp import FastMCP

parser=argparse.ArgumentParser()
parser.add_argument('--db',required=True)
parser.add_argument('--task',required=True)
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
def checkpoint(message:str) -> dict:
    """Commit permitted product files on the local product branch; no push."""
    return invoke('checkpoint',lambda w:w.checkpoint(message))


@mcp.tool()
def inspect() -> dict:
    """Return file hashes and branch identity for independently checked evidence."""
    return invoke('inspect',lambda w:w.inspect())


if __name__=='__main__':mcp.run(transport='stdio')
