# Company OS — autonomous company workspace

Backend repair checkpoint: project workspaces now support Python and TypeScript
source. Workers receive actual file capabilities and can run Python syntax checks
and offline Docker unittests. Python tests require a trusted local image pinned by
image ID; no automatic image downloads, package installs or host credentials are
provided during test execution. This is not deployment or full product certification.

The intended distribution is a GitHub download that runs locally: detect installed
AI CLIs, let the founder choose one, research an idea, obtain approval, then produce
the product's source folder and a downloadable package. This architecture keeps
the orchestration application separate from each generated product.

Local CLI discovery is available with `python company_cli.py ai-discover`.
`python company_cli.py init --no-serve --ai codex` detects installed Codex/Claude
and saves a preference. **Codex employee, planner and review execution is implemented. Selection activates
the CLI for new calls. Claude and CLI research evidence adapters remain missing.**

Export existing approved product code with
`python company_cli.py export-project PROJECT_ID`. The ZIP in ignored `exports/`
contains `code/` and a manifest with file hashes and actual task/delivery states.
It excludes orchestration credentials and audit artifacts. Export does not certify
builds, application behavior or deployment; incomplete products stay incomplete.

**Ideas → Enable autonomous idea workflow** now schedules research, independent
reviews, corrections, proposal drafting, Gmail approval delivery and monitoring,
then approved local delivery without per-stage clicks. It is explicitly opt-in,
uses fixed allowances and runs while the dashboard server is running. Build and
launch integration gaps remain visible blockers. See [setup](LIVE-SETUP.md).

Approved products now have **Start autonomous delivery**: AI handles role grants,
planning, independent plan review, task assignment, local workspace setup and
bounded build/QA/rework handoffs. Manual grants and assignments are advanced
controls. See [delivery limits and setup](LIVE-SETUP.md). Missing mobile builds,
browser QA, deployment and unattended operation remain blockers.

Connected Next.js dashboard: launch with
`.venv/bin/python company_cli.py dashboard --next --port 3000 --open` after
`npm --prefix dashboard-next run build`. The main UI reads real workflow state and
dispatches explicit actions. The previous dummy UI is at `/preview`. See
[connected dashboard setup](dashboard-next/README.md).

Local delivery now includes approved-product Git workspaces, task-scoped MCP file
and commit tools, and independent static artifact QA. See Stage 8 in
[LIVE-SETUP.md](LIVE-SETUP.md). The 72-test suite passes; delivery model calls in
the integration test are scripted. Live product approval, browser QA, deployment
and reliable unattended operation remain unverified or missing.

Open the local control dashboard:

```sh
.venv/bin/python company_cli.py init --open
```

The default address is http://127.0.0.1:8787. `init` preserves your existing SQLite
state, configuration and skills; a new workspace gets empty state, an example
configuration and role skills. No paid calls or worker processes start.

The dashboard includes overview, projects, tasks, employees, Gmail approvals,
activity, connections and blueprint milestones. Select a project or task to read
scope, permissions, acceptance criteria, review feedback and saved artifacts.
State refreshes every five seconds. Pause/resume changes are audited; resume does
not start work automatically. Paid execution and investment approval remain in the
CLI/Gmail workflow. Budget figures are internal units, not currency invoices.

Commands:

```sh
.venv/bin/python company_cli.py init --no-serve
.venv/bin/python company_cli.py dashboard --open
.venv/bin/python company_cli.py dashboard --port 8790
```

Stop the foreground server with Ctrl+C. This is a local trusted-operator control
centre, not a remote multi-user service. Browser sessions, same-origin checks and
CSRF protection guard the pause endpoint; credential files are never served.
Artifact previews are limited to declared files under the artifact directory.

Validation: 65 Python tests pass, plus `node test_dashboard_ui.js` for eight views,
detail rendering and escaped content. HTTP tests need permission to bind temporary
loopback ports. Interactive visual browser verification remains outstanding.

## Workflow core

Core plus Stage 2 integrations and Stage 3 artifact QA. Python 3.10+.
Core/demo use the standard library; live MCP integrations require requirements.txt.
See LIVE-SETUP.md for model/MCP setup and operator commands.

Run from this directory:

```sh
python3 demo.py
python3 -m unittest -v
```

The demo creates a temporary SQLite database, approves a synthetic proposal,
assigns research and build tasks, detects a missing connection, demonstrates QA
rejection/rework, and reloads persistent state. Temporary demo data is removed
after the run. For persistent use, instantiate `Company("company.db")`.

Implemented: immutable proposal hashes, trusted local approval, role/project tool
grants, dependency gates, independent reviewer identity checks, upfront budget
charges, bounded attempts, pause control, event records and interrupted-run recovery.

Tool handlers are injectable local functions. Stage 2 adds a model worker and
real MCP adapter; no external accounts, real research, email, authentication,
deployment or payments are configured by default. Reviewer identities
are trusted local arguments, not authenticated accounts. Synthetic evidence is
labelled explicitly. This is a core prototype, not a running autonomous company.

Unknown-outcome calls are marked failed for reconciliation and are never retried
automatically. Pausing prevents new calls but cannot cancel an already running
handler. Costs are configured integer units, not measured provider bills. Tools
must be re-registered after restarting. The registry is in memory; grants and
workflow state are persisted. Audit records exclude raw tool payloads, although
project/task storage can contain input data and must be protected in production.

Next engineering work: authenticated operator, durable
capability registry, approved MCP adapters, independent executable
evidence validation, timeout/process isolation, cost reconciliation, migrations
and production operations. Existing state APIs are for a single trusted local operator;
do not expose them directly as public endpoints.

Stage 3 adds `company_cli.py qa TASK_ID --config company.config.json`. See
LIVE-SETUP.md for grants, criteria format, and review limitations.

New: `plan`, `apply-plan`, `tick` and `doctor` commands in `company_cli.py`.
Plans are generated through the model adapter, checked for valid independent roles
and an acyclic task graph, reviewed, then installed atomically without duplicate
assignment. Bounded scheduling handles ready work, dependency gates and QA/rework.
Optional operator-configured executable QA runs real local checks; default QA
remains a model assessment. See Stage 4 in LIVE-SETUP.md for local credentials,
permissions and limitations. Gmail approval is now implemented but not connected. Hosted research is implemented but not live-verified. Repository/hosting
connections and reliable unattended service are still missing.

Gmail: `gmail-connect`, `email-proposal`, `email-poll` and `email-reconcile` implement
founder-account OAuth approval, proposal/budget/authority/expiry binding, Sent-mail
identity checks and durable deduplication. See Stage 5 in LIVE-SETUP.md. Tests use
fake Gmail transport; no live OAuth account or external email has been exercised.

`research-cycle --send-approval` now runs bounded hosted OpenAI web search,
independent model research review, complete proposal drafting, model QA, unapproved
candidate registration and founder Gmail delivery. It bypasses the fixture MCP
server. Run locally with configured model credentials and Gmail OAuth; see Stage
6 in LIVE-SETUP.md. All 47 tests pass. Full-cycle tests are scripted/fake, and no
live model/search/email run has yet been verified.

Dashboard **Controls** now dispatches bounded orchestration actions and records
persistent jobs: proposals, assignments, grants, research, employees, model QA,
planning, local repositories and Gmail. Restart the dashboard to enable the API.
See LIVE-SETUP.md Stage 9 for confirmation, recovery and provider-cost behavior.
