"""Local workflow prototype. No live AI, email, or MCP transport configured."""
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager


class PolicyError(Exception):
    pass


class ToolFailure(Exception):
    """Fixed diagnostics only: never persist arbitrary exception/provider text."""
    REASONS = {
        'api_400': 'OpenAI rejected request parameters; check model/tool compatibility',
        'api_401': 'OpenAI credential rejected; check the local key',
        'api_403': 'OpenAI access denied; check project permissions',
        'api_404': 'OpenAI model or resource unavailable to this account',
        'api_429': 'OpenAI rate or quota limit reached; check account billing and limits',
        'api_rate_limit': 'OpenAI temporary rate limit reached; wait before retrying only this task',
        'api_quota': 'OpenAI billing or usage quota exhausted; check credits and project/organization limits before retrying',
        'api_server': 'OpenAI service error; request outcome may be uncertain',
        'api_other': 'OpenAI request failed; provider response was withheld',
        'network_timeout': 'Model request timed out; charges or outcome may be uncertain',
        'network_connection': 'Model connection failed; check network access',
        'invalid_response': 'Model returned invalid JSON',
        'incomplete_response': 'Model response incomplete; inspect the saved response artifact',
        'missing_deliverable': 'Model returned no text deliverable; inspect saved response artifact',
        'missing_search': 'Model response lacks completed web-search evidence',
        'insufficient_sources': 'Research returned fewer than three source URLs',
        'quality_not_ready': 'Pre-submission quality check still finds gaps after bounded revision; inspect saved quality reports',
        'quality_invalid_check': 'Pre-submission model self-check was invalid; independent handoff withheld',
        'quality_policy_blocked': 'Pre-submission work blocked by budget, pause or permissions; no handoff submitted',
        'unsupported_hosted_model': 'gpt-oss requires a separately deployed inference provider; this adapter uses hosted OpenAI Responses',
    }

    def __init__(self, code):
        self.code = code if code in self.REASONS else 'api_other'
        super().__init__(self.REASONS[self.code])


class Company:
    def __init__(self, path="company.db"):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS projects (
          id TEXT PRIMARY KEY, proposal TEXT NOT NULL, digest TEXT NOT NULL,
          approved INTEGER NOT NULL DEFAULT 0, budget INTEGER NOT NULL CHECK(budget>=0),
          spent INTEGER NOT NULL DEFAULT 0, paused INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id),
          owner TEXT NOT NULL, reviewer TEXT NOT NULL, tool TEXT NOT NULL,
          payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
          attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
          output TEXT, note TEXT, CHECK(owner != reviewer));
        CREATE TABLE IF NOT EXISTS dependencies (
          task TEXT REFERENCES tasks(id), dependency TEXT REFERENCES tasks(id),
          PRIMARY KEY(task, dependency));
        CREATE TABLE IF NOT EXISTS grants (
          project TEXT REFERENCES projects(id), role TEXT, tool TEXT,
          PRIMARY KEY(project, role, tool));
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT DEFAULT CURRENT_TIMESTAMP,
          kind TEXT NOT NULL, details TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS trash (
          kind TEXT NOT NULL CHECK(kind IN ('idea','project')), target TEXT NOT NULL,
          title TEXT NOT NULL, trashed_at TEXT DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(kind,target));
        ''')
        self.tools = {}

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def event(self, kind, **details):
        self.db.execute("INSERT INTO events(kind,details) VALUES (?,?)",
                        (kind, json.dumps(details)))

    def project(self, proposal, budget):
        if type(budget) is not int or budget < 0:
            raise ValueError("Budget must be a nonnegative integer in smallest currency units")
        body = json.dumps(proposal, sort_keys=True)
        digest = hashlib.sha256(body.encode()).hexdigest()
        identifier = str(uuid.uuid4())
        with self.transaction():
            self.db.execute("INSERT INTO projects(id,proposal,digest,budget) VALUES (?,?,?,?)",
                            (identifier, body, digest, budget))
            self.event("proposal.created", project=identifier, digest=digest)
        return identifier, digest

    def approve_local(self, project, digest):
        """Trusted local operator API, NOT an authenticated email approval endpoint."""
        with self.transaction():
            row = self.db.execute("SELECT * FROM projects WHERE id=?", (project,)).fetchone()
            if row is None or row["digest"] != digest:
                raise PolicyError("Unknown project or mismatched proposal")
            if not row["approved"]:
                self.db.execute("UPDATE projects SET approved=1 WHERE id=?", (project,))
                self.event("proposal.approved.local", project=project, digest=digest)

    def pause(self, project, paused=True):
        with self.transaction():
            if not paused and self.db.execute("SELECT 1 FROM trash WHERE kind='project' AND target=?",(project,)).fetchone():
                raise PolicyError('Restore the project from Trash before resuming')
            if not paused and self.db.execute("SELECT 1 FROM sqlite_master WHERE name='ideas'").fetchone():
                if self.db.execute("SELECT 1 FROM trash JOIN ideas ON ideas.id=trash.target WHERE trash.kind='idea' AND ideas.research_project=?",(project,)).fetchone():
                    raise PolicyError('Restore the idea from Trash before resuming research')
            self.db.execute("UPDATE projects SET paused=? WHERE id=?", (int(paused), project))
            self.event("project.pause", project=project, paused=paused)

    def register_tool(self, name, handler, cost=0):
        if type(cost) is not int or cost < 0:
            raise ValueError("Invalid tool cost")
        self.tools[name] = (handler, cost)

    def grant(self, project, role, tool):
        with self.transaction():
            self.db.execute("INSERT OR IGNORE INTO grants VALUES (?,?,?)", (project, role, tool))
            self.event("tool.granted", project=project, role=role, tool=tool)

    def task(self, project, owner, reviewer, tool, payload, dependencies=(), max_attempts=3):
        if owner == reviewer or type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("Independent reviewer and positive attempt limit required")
        identifier = str(uuid.uuid4())
        with self.transaction():
            for dep in dependencies:
                row = self.db.execute("SELECT project FROM tasks WHERE id=?", (dep,)).fetchone()
                if row is None or row["project"] != project:
                    raise PolicyError("Dependency must belong to this project")
            self.db.execute('''INSERT INTO tasks
                (id,project,owner,reviewer,tool,payload,max_attempts) VALUES (?,?,?,?,?,?,?)''',
                (identifier, project, owner, reviewer, tool, json.dumps(payload), max_attempts))
            for dep in dependencies:
                self.db.execute("INSERT INTO dependencies VALUES (?,?)", (identifier, dep))
            self.event("task.created", task=identifier, project=project)
        return identifier

    def execute(self, task):
        with self.transaction():
            t = self.db.execute("SELECT * FROM tasks WHERE id=?", (task,)).fetchone()
            if t is None:
                raise PolicyError("Unknown task")
            if t["status"] not in ("queued", "blocked", "changes_requested"):
                raise PolicyError("Task is not executable")
            p = self.db.execute("SELECT * FROM projects WHERE id=?", (t["project"],)).fetchone()
            if not p["approved"] or p["paused"]:
                raise PolicyError("Project requires approval and must not be paused")
            pending = self.db.execute('''SELECT 1 FROM dependencies d JOIN tasks t
                ON t.id=d.dependency WHERE d.task=? AND t.status!='completed' ''', (task,)).fetchone()
            if pending:
                raise PolicyError("Dependencies require completed independent reviews")
            grant = self.db.execute("SELECT 1 FROM grants WHERE project=? AND role=? AND tool=?",
                                    (t["project"], t["owner"], t["tool"])).fetchone()
            if not grant:
                raise PolicyError("Tool permission denied")
            if t["tool"] not in self.tools:
                self.db.execute("UPDATE tasks SET status='blocked',note='Missing tool connection' WHERE id=?", (task,))
                self.event("task.blocked", task=task, reason="Missing tool connection")
                return "blocked"
            handler, cost = self.tools[t["tool"]]
            if t["attempts"] >= t["max_attempts"]:
                raise PolicyError("Attempt limit reached")
            if p["spent"] + cost > p["budget"]:
                raise PolicyError("Budget exceeded")
            # Conservative upfront charge: failed/uncertain calls retain their cost.
            self.db.execute("UPDATE projects SET spent=spent+? WHERE id=?", (cost, p["id"]))
            self.db.execute("UPDATE tasks SET status='running',attempts=attempts+1 WHERE id=?", (task,))
            self.event("tool.started", task=task, tool=t["tool"], cost=cost)
        try:
            output = handler(json.loads(t["payload"]))
            if not isinstance(output, dict) or not output.get("artifact") or not output.get("evidence"):
                raise ValueError("Tool must return artifact and evidence")
            encoded = json.dumps(output)
        except Exception as error:
            reason = str(error) if isinstance(error, ToolFailure) else 'Tool failed; reconcile before retry'
            code = error.code if isinstance(error, ToolFailure) else 'unclassified'
            with self.transaction():
                self.db.execute("UPDATE tasks SET status='failed',note=? WHERE id=?", (reason, task))
                self.event("tool.failed", task=task, failure_code=code, reason=reason)
            return "failed"
        with self.transaction():
            self.db.execute("UPDATE tasks SET status='awaiting_review',output=? WHERE id=?", (encoded, task))
            self.event("task.submitted", task=task)
        return "awaiting_review"

    def review(self, task, reviewer, accepted, note, expected_output=None, expected_attempts=None):
        if not note.strip():
            raise ValueError("Review evidence or defect description required")
        with self.transaction():
            t = self.db.execute("SELECT * FROM tasks WHERE id=?", (task,)).fetchone()
            if t is None or t["status"] != "awaiting_review" or reviewer != t["reviewer"]:
                raise PolicyError("Wrong reviewer or task state")
            if expected_output is not None and (t["output"] != expected_output or t["attempts"] != expected_attempts):
                raise PolicyError("Source task changed during QA")
            status = "completed" if accepted else ("failed" if t["attempts"] >= t["max_attempts"] else "changes_requested")
            self.db.execute("UPDATE tasks SET status=?,note=? WHERE id=?", (status, note, task))
            self.event("task.reviewed", task=task, reviewer=reviewer, accepted=bool(accepted), note=note)

    def reserve_employee_call(self, task, tool, cost=0):
        """Recheck authority and reserve cost immediately before an employee tool call."""
        if type(cost) is not int or cost < 0:
            raise ValueError("Invalid tool cost")
        with self.transaction():
            t = self.db.execute("SELECT * FROM tasks WHERE id=?", (task,)).fetchone()
            if t is None or t["status"] != "running":
                raise PolicyError("Worker task must be running")
            p = self.db.execute("SELECT * FROM projects WHERE id=?", (t["project"],)).fetchone()
            if not p["approved"] or p["paused"]:
                raise PolicyError("Project is paused or unapproved")
            if not self.db.execute("SELECT 1 FROM grants WHERE project=? AND role=? AND tool=?",
                                   (t["project"], t["owner"], tool)).fetchone():
                raise PolicyError("Employee tool access denied")
            if p["spent"] + cost > p["budget"]:
                raise PolicyError("Budget exceeded")
            self.db.execute("UPDATE projects SET spent=spent+? WHERE id=?", (cost, p["id"]))
            self.event("employee.tool.started", task=task, tool=tool, cost=cost)
    def invoke_for_running_task(self, task, tool, arguments, handler, cost=0):
        self.reserve_employee_call(task, tool, cost)
        try:
            result = handler(arguments)
        except Exception:
            with self.transaction():
                self.event("employee.tool.failed", task=task, tool=tool)
            raise
        with self.transaction():
            self.event("employee.tool.completed", task=task, tool=tool)
        return result

    def recover_interrupted(self):
        with self.transaction():
            rows = self.db.execute("SELECT id FROM tasks WHERE status='running'").fetchall()
            for row in rows:
                self.db.execute("UPDATE tasks SET status='failed',note='Interrupted: reconcile external outcome' WHERE id=?", (row["id"],))
                self.event("task.interrupted", task=row["id"])
        return len(rows)

    def snapshot(self):
        return {table: [dict(r) for r in self.db.execute("SELECT * FROM " + table)]
                for table in ("projects", "tasks", "events")}
