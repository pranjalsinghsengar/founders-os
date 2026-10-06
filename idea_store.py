"""Persistent idea inbox, separate from approved product investments."""
import uuid
from core import PolicyError

def initialize_ideas(company):
 company.db.execute('''CREATE TABLE IF NOT EXISTS ideas (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
 market TEXT NOT NULL, origin TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 research_project TEXT REFERENCES projects(id), research_task TEXT REFERENCES tasks(id))''')

def create_idea(company,title,description,market,origin='founder'):
 initialize_ideas(company)
 for value,limit in ((title,160),(description,4000),(market,300)):
  if not isinstance(value,str) or len(value)>limit:raise ValueError('Invalid idea fields')
 if not title.strip() or not market.strip() or origin not in ('founder','ai_discovery'):
  raise ValueError('Idea title, market and valid origin required')
 identifier=str(uuid.uuid4())
 with company.transaction():
  company.db.execute('INSERT INTO ideas(id,title,description,market,origin) VALUES (?,?,?,?,?)',
      (identifier,title.strip(),description.strip(),market.strip(),origin))
  company.event('idea.created',idea=identifier,origin=origin)
 return {'idea':identifier}

def idea_by_id(company,identifier):
 initialize_ideas(company)
 row=company.db.execute('SELECT * FROM ideas WHERE id=?',(identifier,)).fetchone()
 if not row:raise PolicyError('Unknown idea')
 if company.db.execute("SELECT 1 FROM trash WHERE kind='idea' AND target=?",(identifier,)).fetchone():
  raise PolicyError('Restore the idea from Trash before researching')
 return dict(row)
