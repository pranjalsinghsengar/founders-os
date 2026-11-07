# Stage 2: model workers and MCP connections

## Backend source and isolated Python QA

Optional automatic local recovery: set `local_recovery_enabled: true` in the
local configuration. Enabled delivery workflows diagnose fixed worker-round and
self-check failures, retry within remaining attempts, or create one audited repair
assignment when the original attempts are exhausted. Original failed tasks and
attempts remain recorded; dependent plan tasks are redirected to the repair, which
keeps the original criteria and independent review. Repair lineages cannot grow
indefinitely. The supervisor reserves enough current allowance for the worker,
configured correction cycles and review before scheduling. It does not increase
budgets, retry unknown external outcomes, bypass permissions or certify release.
The dashboard must remain running for background recovery. Contradictory positive
self-check summaries with explicit failed criteria are corrected to rejection and
normal corrective work; they never authorize submission.

Configure `employees.repair_engineer` with `skills/repair_engineer.md` and
`run_cost_units: 20` to send diagnosed local product failures to a dedicated
Repair Engineer. It gets scoped source/test/report and local checkpoint tools,
keeps the original task's acceptance criteria and independent reviewer, and has
two attempts on its repair assignment. Failed originals remain in audit history.
There is at most one replacement per repair lineage; budgets and external-account
permissions are never expanded. It cannot repair the orchestration host itself or
unknown deployment/provider outcomes. The Employees view shows the configured
role; Tasks and Activity show its assignments, diagnostics and review handoffs.

Employee model round limits can be set per role with
`employees.developer.max_rounds` (`null` for no cap, or integer 1–50); otherwise
the worker uses global `max_rounds`, default 6. Set global `max_rounds` to `null`
and remove role overrides to disable round caps for every employee. Configuration
applies when a worker starts; in-flight workers retain their original settings.
Round exhaustion retains saved files and response
artifacts, reports `worker_round_limit`, and withholds independent submission.
Inspect the files before a bounded local retry. More rounds permit additional
provider calls; they do not increase the project allowance or retry limit, and
internal units are not provider invoice limits. Mock AI outputs remain simulations.

Workspace tools now accept `.py`, `.ts`, `.tsx`, `.jsx` and `.toml` alongside
existing web/document files. Path, hidden-file, symlink and size restrictions still
apply. `workspace/check_python` parses source without importing it. Syntax success
does not certify behavior, encryption or integrations.

To prepare Python functional tests, build the trusted image with
`docker build -t company-python-qa:local qa-image`, then obtain its immutable ID
with `docker image inspect company-python-qa:local --format '{{.Id}}'`. Set
`python_test_image` in local company.config.json to that `sha256:…` ID. Keep Docker
running. Image construction downloads dependencies; test execution never pulls or
installs packages. `workspace/test_python` runs `tests/test_*.py` in an offline,
read-only container with dropped capabilities, resource limits and an ephemeral
source snapshot. It forwards no company API keys or OAuth tokens. Generated tests
define coverage; passing them is not proof of complete security or compliance.

Verified for project b82587cb: eight actual backend tests cover authentication,
encrypted payload/usernames, cross-user isolation, account/data deletion,
malformed input, restart persistence, missing-key rejection and a locally trusted
HTTPS handshake. No live customer data or deployment was involved. Remaining
MVP features, real AI module integration and production hosting are separate work.

## Local distribution setup

Budget amendments: open a project’s **Overview → Internal budget**, enter the
additional units and click **Approve budget increase**. Confirmation records an
audited founder amendment using the displayed current total; stale or duplicate
amendments are rejected. Scope, spent units and blocked state are preserved.
CLI: `increase-budget PROJECT_ID --amount 100 --expected-budget 100`.

When an enabled autonomous workflow blocks, a durable Gmail failure notification
is queued. The running dashboard sends one alert per failure incident, containing
the reason, remaining internal units and a **Review & retry** link to the local
dashboard. Keep the dashboard running on that computer. Email delivery with an
unknown outcome is not automatically repeated. These alerts do not grant approval.

The link opens **Overview → Automation recovery**. **Review & retry local work**
requires confirmation, sufficient allowance for the attempt/self-check/review,
remaining attempts and local-only employee grants. It preserves prior attempts,
files and audit history. External-write outcomes, failed reviews, research and
unimplemented release integrations require reconciliation; the button does not
bypass them. Increasing a budget never triggers a retry by itself.

Known research self-check formatting failures can be recovered from saved provider
responses without repeating research or charging another attempt. Recovery requires
a completed, single fenced JSON check that passes every original criterion, an
unchanged draft and saved search sources. It restores `awaiting_review`, never
acceptance. Paused, interrupted, uncertain, genuinely rejected or malformed work
remains blocked. Autonomous handoffs apply this narrow recovery before stopping.

Run `python company_cli.py ai-discover` to list installed Codex and Claude CLIs.
This only checks PATH; it does not read authentication files, launch a model or
consume provider usage. Run `python company_cli.py init --no-serve --ai codex`
to initialize and activate Codex for new employee, planning and review calls.
The adapter reuses local CLI login and returns structured tool proposals to the
existing Company gateway. Claude and CLI research evidence remain unavailable;
CLI research stops explicitly without silently switching to the API.

After an approved product has actual source files in its registered workspace,
run `python company_cli.py export-project PROJECT_ID`. It writes a bounded ZIP
under ignored `exports/`, containing `code/` plus `manifest.json` with file hashes
and task/delivery states. No generated code is executed by export. Review required
build, executable QA and deployment results before treating the package as final.

Autonomous idea workflow: **Ideas → Enable autonomous idea workflow** authorizes
automatic research, self-checks, independent reviews, bounded corrections,
complete proposal drafting, product registration and Gmail approval delivery for
that idea. The selected research allowance is fixed; existing research allowances
are reused without increases. The proposed product allowance (100 by default)
requires the founder's authenticated Gmail approval. After that decision, local
delivery starts and continues automatically without per-handoff clicks.

Each handoff is recorded in `autonomy_runs` and dispatched as a serialized
dashboard job. While the dashboard server remains running, its background
scheduler checks ready work every five seconds and polls approval replies at most
once per minute per workflow. No workflow is enabled by startup or these code
changes. Startup resumes only previously opted-in, safe ready work; interrupted
handoffs are blocked for reconciliation. **Stop automatic handoffs** disables the
workflow and pauses associated projects. Explicit **Resume** reuses the same
scope and allowances; failed/unknown outcomes must first be reconciled.

CLI setup: `start-autonomy IDEA_ID --research-mode normal --budget 100
--product-budget 100 --config company.config.json` persists the opt-in policy.
The running dashboard schedules `advance-autonomy WORKFLOW_ID`; without the
dashboard server there is no automatic scheduling. This is not an OS-managed
service or verified recovery daemon. Tests use scripted models and fake Gmail;
no live paid calls or email sends were performed for this implementation.
Native mobile builds/device testing, isolated builds, browser QA, deployment,
production monitoring and business-feedback integrations remain incomplete.
The workflow reports those blockers instead of labeling local artifacts a
finished application or automatically expanding authority.

Autonomous local delivery: open an approved product and click **Start autonomous
delivery**, or **Resume & start** when paused. A single confirmed paid action
grants the planner and independent reviewer their scoped capabilities, generates
and self-checks the plan, independently reviews it, corrects rejected plans within
attempt limits, installs assignments, creates the market/project Git workspace,
derives employee/reviewer permissions and advances build/review/rework handoffs.
The founder no longer assigns routine roles or grants workspace tools manually.
CLI: `company_cli.py start-delivery PROJECT_ID --config company.config.json`
(`--resume` explicitly resumes a paused product). The dashboard runs up to 10
handoffs; CLI `--max-actions` permits 1–20. **Continue autonomous delivery** reuses
the existing plan and assignments after a bounded run stops. Status, stage and
blockers are persisted in `delivery_runs` and the audit trail.

This is bounded local orchestration, not an unattended daemon or completed
deployment integration. No budget increase, unconfigured external MCP access,
customer contact, GitHub write or deployment grant is automatic. Completed local
artifact reviews are labeled `local_tasks_reviewed`, with release blocked by
missing isolated builds, mobile/device execution, browser QA and hosting. Paused,
unapproved or trashed products cannot start implicitly. Failed/unknown tool calls
and failed reviews stop for reconciliation; automatic paid retries are limited to
changes-requested work. Delivery tests use scripted models and real local Git.

Dashboard Trash: use Move to Trash inside an idea or project, then restore from
the Trash sidebar. Records, artifacts and repositories are retained in SQLite
and on disk. Trash pauses associated work and blocks resuming it until restored;
restore leaves work paused. Running tasks/jobs must finish before trash/restore.
Employee work monitor shows actual task states, attempts, saved artifacts,
feedback and recent tool events, refreshing every four seconds. It does not
display private model reasoning or claim that idle employees are running.

Gmail approval compatibility: Gmail may replace the outgoing RFC Message-ID and
hard-wrap the approval command before its binding hash. Polling now verifies the
original message through its saved Gmail message/thread identifiers, authenticated
Sent mailbox, sender, subject, complete proposal attachment and request binding,
then stores Gmail's actual RFC identifier for reply checks. An exact command
wrapped across two lines is accepted; quoted or embedded commands are ignored.
Sender, thread, immutable proposal/budget binding, expiry and deduplication checks
still apply. Existing sent requests are hydrated during the next poll; no resend
is needed. One existing live founder reply was successfully consumed after this
fix; that validates this approval path, not autonomous delivery or deployment.

Pre-submission quality gate: new research, proposal, planner and model employee
runs now check every assignment criterion before handing off. A failed check
triggers at most one corrective revision and a second check. Employee code
corrections run through the same granted tools and model-round limit; research
and document revisions use supplied evidence only and cannot invent new sources.
Unresolved gaps, malformed checks, provider failures or budget/pause/grant blockers
withhold submission. Independent review and founder approval remain required.
This is an employee model self-assessment, not verified truth or executable QA.

Defaults: each check costs 5 internal units, each revision 10. A successful first
check adds 5 per stage; one revision plus recheck adds up to 20 per stage. Configure
`quality_max_revisions` (0–2), `quality_check_cost_units` and
`quality_revision_cost_units` locally. Zero revisions still requires a self-check.
No budget is increased automatically. Saved draft/response and attempt-specific
quality reports preserve check evidence, correction requests and usage; inspect
**Read quality** in task details, including withheld handoffs. Existing completed
tasks and review decisions remain unchanged. Provider bills are not reconciled
by these internal cost units. Tests use scripted models, not live paid calls.

Research/review update: new research runs and rework use a proposal-ready brief
with a dated, classified evidence ledger, demand/competitor analysis, flaws,
differentiation, feasibility, costs, risks and bounded validation. Founder ideas
follow their specific assignment rather than an obligatory three-problem comparison.
Model reviewers are instructed to use the explicit criteria, keep optional
suggestions nonblocking, and return a decision consistent with every criterion
check. This remains model assessment of supplied sources, not independently
executed source verification. Existing reports and decisions are retained.
Retrying still incurs configured costs and requires sufficient remaining allowance;
these changes neither increase budgets nor start paid calls.

The Ideas dashboard offers Normal and Deep research for discovery, founder ideas
and rework. CLI: `discover --research-mode normal` or `--research-mode deep`;
`rework-research TASK_ID --research-mode deep` switches a retry's profile.
Without a flag, rework inherits the previous attempt's mode (legacy reports
default to Normal). Defaults: Normal 30 internal units, up to 4 search calls and
6000 output tokens; Deep 60 units, up to 8 search calls and 10000 output tokens.
Configure `deep_research_cost_units`, `deep_research_max_search_calls` and
`deep_research_max_output_tokens` locally to override Deep defaults. Normal uses
the existing `research_*` settings. These are bounded hosted-search profiles,
not a separate deep-research API or proof of exhaustive research. Both request
a ranked customer-interest improvement backlog; only new assignments add that
backlog to their acceptance criteria. Existing task criteria remain unchanged.
Review/drafting incur separate costs. No budget is increased automatically.
Rebuild Next.js and restart the dashboard after updating code.

This stage adds an OpenAI Responses API adapter, real MCP stdio discovery and
tool calls, role skill loading, per-call permission/budget checks, artifacts,
model usage evidence, and a trusted local operator CLI.

## Setup

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp company.config.example.json company.config.json
python -m unittest -v
```

Set `OPENAI_API_KEY` in your local environment. Do not paste keys into chat or
commit them. Edit the config to specify your model ID and absolute MCP executable
and server script paths. The included MCP server exposes a harmless local fixture;
connect an approved search/repository/design server for actual work. It does not
perform research or build products.

`allow_tools` names the server tools permitted for discovery. The worker also
needs a project/role grant for the canonical `server/tool` name. The model receives
only tools satisfying both restrictions. MCP server commands come from trusted
operator configuration; installing or running an arbitrary server grants that
process access under your operating-system account.

## Run a task

Create `proposal.json` containing your proposal and `task.json` containing the
task objective, acceptance criteria and context. Then run:

```sh

python company_cli.py propose proposal.json --budget 100
python company_cli.py approve PROJECT_ID PROPOSAL_DIGEST
python company_cli.py grant PROJECT_ID researcher employee.researcher
python company_cli.py grant PROJECT_ID researcher local/inspect_workflow
python company_cli.py assign PROJECT_ID researcher qa task.json
python company_cli.py run TASK_ID --config company.config.json
python company_cli.py status
python company_cli.py review TASK_ID qa accept 'Describe your independent verification'
```

Replace the uppercase identifiers with CLI output. Approval is a trusted local
operator action; authenticated email approval is still pending. Review is also
performed by the local operator, not an autonomous QA worker yet. Outputs are in
`artifacts/`; tasks remain awaiting review until accepted or rejected.

The example researcher skill requires source-backed evidence, so running it
against the sample fixture should explain missing research capabilities rather
than claim real market findings.

## Costs, recovery and limitations

The database budget is an internal unit allowance. Worker run cost is charged
upfront; per-tool configured costs are charged before calls. These units do NOT
enforce a currency ceiling on actual API invoices. Configure provider-side spend
limits; actual model token usage is saved for subsequent reconciliation. Each
run is bounded by model rounds, output tokens and request/tool timeouts.

Model or tool failures stop the task; there are no automatic network retries.
After a terminated process, use `python company_cli.py recover`, inspect external
outcomes, and create replacement work only after reconciliation. Recovery must
run only when no other worker is active. Persisted grants and workflow state
survive restarts; MCP connections are recreated from configuration.

This implementation supports local stdio MCP, not remote HTTP/OAuth yet. Skills
are explicitly configured local files, not automatic plugin marketplace installs.
It does not provide process sandboxing, credential rotation, authenticated user
accounts, durable mid-conversation resumes, or a durable unattended service. Stage 4 below adds task generation and bounded scheduling.
Tool evidence files may contain sensitive account output; restrict local access.

Verified here: a real local MCP server was launched, tools were discovered,
schema validation ran, and a tool was invoked. Worker integration tests use a
scripted model, explicitly labelled as such. A live paid model run requires
your credentials and was not executed during development.

Protocol references:
- https://github.com/modelcontextprotocol/python-sdk
- https://developers.openai.com/api/docs/guides/function-calling

## Stage 3: independent artifact QA

Include an `acceptance_criteria` list of strings in each task assignment. Grant
its designated reviewer permission to run QA, then request review:

```sh
python company_cli.py grant PROJECT_ID qa employee.qa
python company_cli.py qa TASK_ID --config company.config.json
```

Replace `qa` in the grant with the task's designated reviewer role. The QA model
runs separately from the employee, receives the assignment, saved deliverable and
saved tool evidence, and must return a decision for every criterion. Acceptance
completes the source task; rejection requests rework, or fails it when its attempt
limit is exhausted. Running the source task again receives the QA feedback.

QA reserves `qa_run_cost_units` (default 10) under the same approval, pause, grant
and budget gates. Each QA run is a separate persistent task with a JSON report;
that QA task remains awaiting operator review. Invalid model responses fail the
QA run and leave the source task awaiting review. Model reports assess supplied
artifacts: QA does not independently execute tests or browse sources. Acceptance
is a model judgment, not proof of correctness. Reports are restricted to artifacts
inside the configured artifacts directory and stale decisions cannot replace a
new source attempt. No automatic paid retries or email messages are sent.

Earlier system-Python verification: 12 tests passed and four MCP tests were
skipped. Current verification uses the existing .venv and passes all 27 tests.
Live QA requires the configured model and local OPENAI_API_KEY. Email approval
and a complete automatically scheduled research-to-product workflow remain pending.

## Stage 4: reviewed planning and bounded scheduling

Use the existing `.venv/bin/python`: it has the MCP dependencies installed.
`doctor` checks configuration/credential presence without printing values or
making network calls. It does not validate credentials with providers.

```sh
.venv/bin/python company_cli.py --db /tmp/company-setup-check.db doctor --config company.config.json
```

In your own zsh terminal, set the model credential using a hidden prompt (the key
is not entered as a command and does not become shell history):

```sh
read -rs 'OPENAI_API_KEY?OpenAI API key: '
export OPENAI_API_KEY
```

Set `model` in your local `company.config.json` to a model available to your
account. Add `planning_cost_units`, `qa_run_cost_units`, and any new employee
roles from `company.config.example.json`; the runtime never overwrites your
configuration. The key belongs only in the environment, never in this config.
For MCP credentials use a hidden prompt for each required variable and list its
name under that server's `env_names`. These variables are forwarded only to the
configured server process. Never paste credential values into chat.

After reviewing and approving a proposal locally:

```sh
.venv/bin/python company_cli.py grant PROJECT_ID planner employee.planner
.venv/bin/python company_cli.py plan PROJECT_ID
```

Planning makes a paid model call and produces a validated JSON DAG artifact. The
returned planning task requires independent scope review. Inspect its saved plan
and review it as `product_manager`, then install it:

```sh
.venv/bin/python company_cli.py review PLAN_TASK_ID product_manager accept 'Describe scope and acceptance checks actually performed'
.venv/bin/python company_cli.py apply-plan PLAN_TASK_ID
```

Installation is atomic and idempotent across restarts. It creates assigned tasks
and dependency links; it does not grant tools. Grant each planned employee its
`employee.ROLE` tool and only the actual MCP capabilities it needs. Grant each
reviewer `employee.qa`. Replace identifier placeholders with CLI output. Planning
requires an approved, unpaused proposal; changing approved scope needs new approval.

```sh
.venv/bin/python company_cli.py tick PROJECT_ID --max-actions 10
```

Each tick executes ready tasks OR reviews already-submitted tasks. Later ticks
perform subsequent handoffs. Completed dependencies unlock downstream work;
rejection causes bounded developer rework. Workers receive dependency artifact
references and their own review feedback. Missing connections and permissions
remain blockers. Failed QA is not automatically charged again for the same worker
attempt; investigate its report before explicitly retrying `qa`. QA report tasks
remain available for operator audit and are excluded from automatic scheduling.

This is a bounded, single-operator scheduler, not an unattended service. Do not
run overlapping ticks or recovery while workers are active. It has no daemon,
leases, process sandbox, deployment or monitoring integration.

### Executable QA

By default review is still a model assessment. To use independent local executable
checks, add an `executable_qa` entry keyed by project ID in trusted configuration:

```json
{
  "executable_qa": {
    "PROJECT_ID": {
      "Exact acceptance criterion from task": {
        "command": ["/absolute/path/to/python", "-m", "unittest", "discover"],
        "cwd": "/absolute/path/to/product-checkout",
        "timeout_seconds": 30
      }
    }
  }
}
```

Every criterion on a reviewed task must have exactly one configured check; missing
or extra criteria block review. Configure appropriate product tests, not the
company's own tests as a substitute for product validation. `qa` and `tick` select
executable checks for that project when configured. Standalone executable `qa`
needs no model credential. Commands come from the operator, never from generated
plans; they run under your OS account and are not sandboxed. The environment
excludes model/MCP credentials. Exit zero passes; nonzero and timeout reject.
Reports retain exit codes and output hashes; raw process output is discarded.
These checks prove only what the configured tests cover. Timeout stops the direct
process; child-process isolation and resource limits remain missing.

### Current verification and next live connections

All 27 tests pass in `.venv`, including four real local stdio MCP checks. New orchestration tests use scripted models; executable QA tests run real
local processes. No live OpenAI model, research provider, email account, repository
or hosting account was exercised. The example MCP server remains a fixture.

Authenticated email approval is not implemented. Select the founder email provider
before adding its authenticated adapter. Real discovery needs an approved research
connection; building requires repository/write and execution tools; launch requires
an explicitly granted hosting adapter. No autonomous launch or real product is
claimed by the current demonstration. Budget units remain internal allowances,
not provider invoice ceilings.

## Stage 5: founder Gmail approval

Gmail is the selected approval provider. The initial research direction is recurring
workflow problems among small service businesses, comparing opportunities before
choosing a product. `examples/research-assignment.json` supplies that direction;
it is an assignment, not researched evidence or an approved investment.

The Gmail adapter is implemented but requires your own local OAuth connection.
It uses the Gmail API directly as a restricted approval gateway, separate from
employee MCP tools. It sends only to the connected founder account. No employee
receives the refresh token or a general Gmail send capability.

### One-time local connection

1. In https://console.cloud.google.com/ create or select a project and enable Gmail API.
2. Configure Google Auth Platform branding/audience. For a personal Gmail account,
   use External and add your own Gmail address as a test user while testing.
3. Create an OAuth client of type **Desktop app**. Download its JSON and save it
   locally as `.secrets/gmail-client.json`. Do not paste it into chat.
4. Install the optional adapter dependencies if needed:

```sh
.venv/bin/python -m pip install -r requirements-gmail.txt
```

5. Run locally, replacing the address with your primary Gmail address:

```sh
.venv/bin/python company_cli.py gmail-connect --founder YOUR_PRIMARY_GMAIL_ADDRESS
```

The browser opens Google's consent screen. Select that same founder account.
Requested scopes are `gmail.readonly` and `gmail.send`: mailbox reading and sending.
The CLI checks the authenticated Gmail profile against the founder address before
saving a token. No email is sent by connecting. Token files are written atomically
with permissions 600, under ignored `.secrets/`. The local config gains only the
founder address and token path. Google controls token lifetime; an External app in
Testing may require reconnection. This is local-development OAuth, not production
verification or unattended credential lifecycle management.

Official references:
- https://developers.google.com/workspace/gmail/api/quickstart/python
- https://developers.google.com/workspace/gmail/api/auth/scopes
- https://developers.google.com/identity/protocols/oauth2/native-app

### Send an actual proposal for approval

Create a complete proposal covering the blueprint's twelve proposal sections.
Its JSON must include `authority_requested`, stating the exact requested actions;
include a concise `title`. Do not substitute the research assignment or synthetic
test fixture for a real evidence-backed proposal. Register it with `propose`, with
your chosen internal budget allowance, then send:

```sh
.venv/bin/python company_cli.py email-proposal PROJECT_ID
```

The mail goes from your connected Gmail account to itself and includes the complete
immutable proposal as a JSON attachment. It binds the project, proposal digest,
budget, full proposal (including authority) and expiry. Default expiry is 24 hours.
Reply from that same account in the same thread. Copy one command shown in the
mail onto the first nonempty line: `APPROVE REQUEST_ID BINDING`, `REJECT ...`, or
`CHANGES ...`. The original request mail does not itself count as approval.

```sh
.venv/bin/python company_cli.py email-poll
```

Only a matching reply fetched from the authenticated founder's **Sent** mailbox
can authorize work. An incoming email with a forged From header cannot qualify.
Sender, thread, In-Reply-To, exact command, binding and expiration are checked.
Approval and reply deduplication commit atomically. Repeated polls do not create
new projects or duplicate approval. Approval enables the existing planning path;
run `plan PROJECT_ID` next. This poll does not automatically grant tools or launch
workers. Local `approve` remains a trusted-operator override.

`REJECT` archives the email request; `CHANGES` marks it for revision. Neither enables
the project. The same rejected/changed proposal cannot be sent again: create a new
proposal/project record for the revision. There is no in-place proposal revision API.

If a send fails ambiguously or the process exits during delivery, do not resend:

```sh
.venv/bin/python company_cli.py email-reconcile REQUEST_ID
```

Reconciliation queries Sent mail by the stable Message-ID. Exactly one confirmed
message restores the sent state; absent or duplicate matches remain blocked for
manual investigation. There are no blind write retries. Expiry/scope/budget changes
invalidate approval; paused projects cannot send or accept approval.

Current verification: Gmail approval policy uses a **fake Gmail transport** in
unit tests, including spoof rejection, expiry, budget binding, duplicates, rejection,
changes, pause and ambiguous delivery reconciliation. No real Gmail account has
been connected, no live email has been sent, and Google OAuth consent remains a
required local step. The system still needs real research, repository and hosting
integrations before it can deliver a live product.

## Stage 6: live research to Gmail approval in one command

Run in the same terminal where your replacement `OPENAI_API_KEY` is exported:

```sh
.venv/bin/python company_cli.py research-cycle --send-approval
```

This is a paid live-model workflow, not a fixture. It uses the configured model,
OpenAI's hosted `web_search` tool and your connected founder Gmail. It does not
use or launch the placeholder sample MCP server. The model must support Responses
API web search; an incompatible model stops the task without automatic fallback.

One cycle:
1. Records and locally authorizes a **research-only mandate**, default 100 internal
   units, restricted to desk research and internal proposal preparation.
2. Executes one bounded live search response comparing problems for small service
   businesses; saves the brief, source URLs, timestamps, tool output and usage.
3. Runs a separate product-manager model review against every research criterion.
4. Drafts all twelve blueprint proposal sections, retaining research source links.
5. Runs a separate QA model review of the complete draft.
6. Registers a separate **unapproved** candidate project (default 100 proposed
   internal units) with no inherited tool grants or product tasks.
7. With `--send-approval`, sends that candidate to the configured founder Gmail.

Source provenance checks require at least three provider-returned HTTP(S) URLs;
proposal evidence cannot introduce URLs absent from research. This verifies that
sources were returned by the search tool, not that they support every claim.
Separate model reviews assess claim support and uncertainty; they are model
judgments, not independent browsing or customer validation. No fabricated demand
is permitted by employee instructions. A live proposal still needs your scrutiny.

Search is required, capped by `research_max_search_calls` (default 4, valid 1..8),
with `research_max_output_tokens` default 6000 and a 60-second HTTP timeout. No
network retries occur. Default internal charges: research 30, drafting 20, each
QA 10; the 100-unit research allowance covers the 70-unit cycle. These controls
DO NOT cap actual currency bills; provider spending controls remain necessary.
No product budget is spent before founder approval.

Optional arguments: `--market 'Your market'`, `--budget 100`, `--product-budget 100`.
Omit `--send-approval` to save an unapproved candidate without sending any email.
A rejected/failed review stops the cycle. Inspect returned task IDs with `status`
and saved artifacts. Use existing `qa`, `review` and explicit task commands to
resolve review blockers. Do not blindly rerun a whole cycle after ambiguous email
failure: reconcile the persisted request first. Interrupted tasks are not resumed
mid-request automatically. A new invocation starts a new research mandate.

For individual handoffs:

```sh
.venv/bin/python company_cli.py discover
.venv/bin/python company_cli.py qa RESEARCH_TASK_ID
.venv/bin/python company_cli.py draft-proposal RESEARCH_TASK_ID
.venv/bin/python company_cli.py qa PROPOSAL_TASK_ID
.venv/bin/python company_cli.py register-proposal PROPOSAL_TASK_ID --budget 100
.venv/bin/python company_cli.py email-proposal CANDIDATE_PROJECT_ID
```

When a real email arrives, read the attached proposal, reply with its exact command,
then run `email-poll`. A successful decision enables `plan CANDIDATE_PROJECT_ID`;
repository, execution and hosting access still need configuration before building
and launch. No paid build or deployment starts automatically from this cycle.

Current verification: 47 tests pass, including a full research→review→draft→review→
registration→email cycle with scripted model responses and fake Gmail transport.
OpenAI request-shape tests verify required bounded search and returned-source
configuration. Real stdio MCP and local executable QA remain tested. No live web
search, paid model call or Gmail delivery was performed by the agent during this
implementation; credentials remain in the operator's local terminal.

API reference: https://developers.openai.com/api/docs/guides/tools-web-search

### Research failure diagnostics

The hosted adapter does not serve `gpt-oss` model weights; that requires a separate
inference-provider adapter. The local configuration was changed from
`gpt-oss-120b` to the hosted search-compatible `gpt-4.1-mini` after the first failed
run. Account access and actual API behavior still require a live run to verify.

New failures retain a fixed, secret-free diagnostic category and return a reason.
HTTP status categories distinguish invalid parameters, credentials, permissions,
model availability, quota/rate limiting and provider errors. Raw provider error
bodies are never printed or persisted. Returned research responses are saved
before deliverable/source validation, so incomplete or insufficient research can
be investigated without another paid call. Earlier failures have no recoverable
exception details; their exact API error cannot be reconstructed.

### Verified live research and reviewer throttling

The operator's research task `37be0cad-e1e5-4bdb-a71e-db3ef47d9e8f`
completed a live hosted search and saved its brief and provider source evidence.
Its reviewer task failed with HTTP 429; the research remains `awaiting_review`.
No candidate or proposal email was produced by that run. This verifies live
research execution, not review acceptance or validated customer demand.

QA now returns its safe failure reason in CLI results. New 429 errors distinguish
known temporary rate-limit codes from credits/spend/usage quota codes. The old
429 body was discarded, so its subtype cannot be reconstructed. Review inputs
retain search calls, source URLs and citations while omitting duplicate response
prompts/deliverable text. Full response evidence remains saved locally.

After temporary throttling subsides (or a quota issue is resolved), reuse the
saved research rather than starting a new discovery cycle:

```sh
.venv/bin/python company_cli.py qa 37be0cad-e1e5-4bdb-a71e-db3ef47d9e8f
```

This creates one new paid QA attempt under the remaining research allowance.
If it completes the research, continue with `draft-proposal` using that same ID,
then QA the draft and register/send the candidate. Rejection requests better
research; do not override it merely to advance the workflow. Tests: 54 passing.

### Rework rejected research without starting a new project

A review decision of `changes_requested` is a quality rejection, not an API error.
Use the same saved task and its reviewer feedback:

```sh
.venv/bin/python company_cli.py rework-research RESEARCH_TASK_ID
.venv/bin/python company_cli.py qa RESEARCH_TASK_ID
```

Rework performs a new bounded paid search, retains the task's original assignment,
passes the previous brief and feedback as data, and strengthens claim-specific
independent-source attribution, dating and uncertainty instructions. It preserves
old artifacts and saves attempt-numbered replacements. Budget, pause, grants and
attempt limits still apply; neither acceptance criteria nor approval are bypassed.

The current live research project has spent 60 of its 100 internal units. One
30-unit rework plus 10-unit QA fits the remaining 40; subsequent proposal drafting
requires additional authorized research allowance. No allowance is silently raised.
Tests: 56 passing, including feedback handoff and artifact preservation.

## Stage 7: local control dashboard and CLI initialization

Run from the project directory:

```sh
.venv/bin/python company_cli.py init --open
```

This initializes missing local files without overwriting state or configuration,
then serves the dashboard at http://127.0.0.1:8787. `--open` opens the browser when
you run the command locally. Use `init --no-serve` for setup only, or `dashboard`
for subsequent launches. Choose another port with `--port 8790` if occupied.

The process stays in the foreground; Ctrl+C stops it. You can leave it in one
terminal and execute workflow commands in another. Launch from a terminal with
credentials exported if you want the Connections view to observe their presence;
the dashboard does not print credentials, validate them with providers, or start
paid API calls. The server binds only to 127.0.0.1.

Views: Overview, Projects, Tasks, Employees, Approvals, Activity, Connections and
Milestones. The dashboard uses existing workflow state with a five-second refresh.
Employee roles reflect configuration and recorded assignments, not invented
running agents. QA report tasks remain visible and labeled as operator audit
reports. Approval history reflects persisted email requests; no dashboard approval
button bypasses the founder Gmail protocol. Connection indicators distinguish
configuration/file presence from observed use and unimplemented integrations.

Click a project to inspect proposal, remaining allowance and grants, and to pause
or resume. Pause prevents new actions but does not terminate an in-flight handler;
resume does not launch workers. These changes use the workflow API and audit log.
Click a task to inspect criteria, dependencies and QA feedback, preview its saved
artifact/evidence, or copy its next CLI command. Copying never executes the command.
The dashboard does not increase budgets, send email, run tests, start research or
deploy products. Those retain the existing authorized CLI/Gmail path.

Local session cookies, Host/same-origin checks, no-store responses and CSRF tokens
protect the API. Dynamic text is escaped. Declared artifact previews are bounded
and restricted to the artifact directory, including resolved symlink checks.
Credential-like fields and API key strings are redacted. This is for a trusted
local operator, not public hosting, account login or multi-user access control.

65 Python tests pass, covering initialization preserving state, real HTTP session
and pause behavior, cross-origin rejection and artifact traversal protection.
`node test_dashboard_ui.js` checks all eight views and escaped data. The browser
connector was unavailable, so interactive visual layout verification is pending.

## Stage 8 — approved local product repository

After a **product** receives founder approval, create its local Git repository:

```sh
.venv/bin/python company_cli.py workspace-init PRODUCT_ID --grant-tools
```

This command refuses research mandates and unapproved or paused projects. It
creates `workspaces/PRODUCT_ID` on the `product` branch and explicitly grants
scoped tools. Developer and designer receive file and commit tools; QA and product
manager receive read/inspection tools. Existing configured employees are preserved.
Workers discover the local stdio MCP server only when their project grants permit
it. The server is bound to a running task and rechecks approval, pause and grants
on every invocation. No remote repository, push or hosting is configured.

For independent **static** QA, write an operator-controlled JSON mapping with
exactly one entry for each task acceptance criterion, for example:

```json
{
  "Page contains a customer action": {
    "kind": "html", "path": "index.html", "ids": ["submit"]
  }
}
```

```sh
.venv/bin/python company_cli.py qa TASK_ID --workspace-checks checks.json
```

Supported checks are `exists`, `contains` (with `text`), `html` (title, required
IDs and local linked-file presence), and `json` (parseable JSON). Saved review
evidence includes file hashes; changed files invalidate the review. Static checks
do not execute generated code or verify browser behavior. Directory scoping is
not an OS sandbox; backend execution and deployment remain unsupported here.

Verification checkpoint: all 72 Python tests pass, including actual Git and stdio
MCP file/commit operations, rejected traversal, and independent rejection/repair.
The model in this delivery integration test is scripted, and project approval is
a synthetic fixture. Eight dashboard views pass Node rendering checks. No paid
calls or external writes were made for this checkpoint. Actual research acceptance,
Gmail product approval, real model delivery and browser QA still need live proof.

## Stage 9 — dashboard orchestration controls

Restart the dashboard process to load the new API, then open **Controls**:

```sh
.venv/bin/python company_cli.py dashboard --open --port 8790
```

The operator console creates unapproved proposals, assigns tasks with dependencies,
changes configured capability grants, starts research/employee/model QA/planning,
installs reviewed plans, runs one scheduler action, initializes approved local Git
repositories, registers reviewed proposals and sends/polls/reconciles Gmail approval.
Doctor and interrupted-task recovery are available. No arbitrary command or path
can be supplied; actions dispatch fixed CLI argument lists. Existing core policy
still controls approval, permissions, internal allowance and attempt limits.

Select the action, fill its fields and explicitly confirm execution. Provider/email
access additionally requires confirmation in the API. Starting an action may incur
provider charges; developer verification did not run paid calls. Founder investment
approval continues through Gmail, not an approval bypass in this console.

Jobs persist queued/running/finished/interrupted status, with request/finish audit
records. One dashboard execution runs at a time. CLI processes outside the dashboard
are not covered by this lock: use a single operator process and do not run recovery
while a worker is active. A restart marks unfinished jobs as interrupted without
retrying. A 15-minute subprocess limit marks unknown outcomes for reconciliation.
Raw subprocess logs are discarded to avoid credential exposure; inspect task notes,
artifacts and audit events. Job success means the CLI command exited successfully;
always inspect the resulting task/review status for acceptance or failure.

The existing frontend is retained; no Next.js migration was needed for these
controls. This remains a loopback trusted-operator service. Credential onboarding,
configuration/skill editing, static QA mapping entry, deployment, automatic service
supervision and browser layout verification remain outstanding. Activity shows the
latest 250 events and Jobs the latest 100 actions, not an unlimited historical view.
Verification: 76 Python tests pass; Node checks nine views and control form fields.

## Stage 10 — connected Next.js control center

```sh
npm --prefix dashboard-next run build
.venv/bin/python company_cli.py dashboard --next --port 3000 --open
```

The main UI now reads real workflow data and dispatches explicit existing actions.
The CLI launches its private Python API on an ephemeral loopback port and shares
an internal bridge credential only with the Next.js server. The browser gets a
separate HttpOnly session; writes require that session, same-origin checks and a
custom header. Bridge credentials and provider keys are never returned. The old
mock UI remains at `/preview` and cannot mutate runtime state.

Founder's ideas persist independently of project authorization. Deep research can
focus on a saved idea; AI discovery also creates an idea record. Reports and drafts
must pass independent review before registration as an unapproved product. Candidate
creation is idempotent and research approval grants no product authority. Investment
approval continues through Gmail. Real repository viewing uses registered scoped
workspaces, not the illustrative folders from the preview.

See dashboard-next/README.md for the live walkthrough and missing integrations.
No paid or email action was performed during connection verification. Multiple
provider adapters, remote push and deployment remain outstanding.

GitHub delivery is now implemented as explicit `repo-create PROJECT --target OWNER/REPO`,
`repo-push PROJECT` and `repo-reconcile PROJECT` CLI actions and Next.js controls.
They require approved active product scope, a local registered workspace and local
GitHub CLI authentication. Reconciliation prevents blind repeated creation/push.
New local roots are grouped by market; existing roots remain intact. No live GitHub
write occurred in verification. Hosting and complete product behavioral QA remain
unconnected. Static workspace QA is also available in live task details.

## Codex CLI employee runtime

Sign into your installed CLI with `codex login` if needed, then run:

```sh
.venv/bin/python company_cli.py init --no-serve --ai codex
.venv/bin/python company_cli.py ai-verify
```

`ai-verify` makes one live text-only request, consuming CLI account usage. No key
is printed or copied. New employees, planning, self-checks and independent reviews
use Codex. In-flight calls retain their prior runtime. The adapter uses an empty
temporary working directory, read-only sandbox, ignores personal config/rules,
disables native shell, plugins, apps, hooks, browser and agent delegation, and
forwards only environment needed for CLI authentication. Company tools remain
external: structured proposals are checked against supplied schemas and passed
through existing grants, budget, pause and audit controls. No automatic retry or
API fallback occurs on CLI failure. Timeout defaults to 180 seconds (10–600 via
`codex_timeout_seconds`). Set optional `codex_model` only to a CLI-accessible model;
the existing API `model` value is not reused for CLI calls.

Research currently requires saved Responses web-search evidence. Codex research
therefore reports an explicit integration blocker; this is not a complete CLI-only
idea-to-release workflow. Claude is not connected. To restore API execution, set
`model_runtime` to `openai_api` in the local config. Selection does not configure
AI credentials for generated products; those products have their own setup.

Codex execution options: https://developers.openai.com/codex/noninteractive

CLI discovery also checks VS Code and Cursor OpenAI extension binaries when
Codex is absent from the terminal PATH. Selecting Codex saves the absolute
`codex_executable` in local config; employees and dashboard use that same path.
If an extension update removes it, rerun `init --no-serve --ai codex`.

Project and linked idea details show **Open application preview** when a local
`product_previews` entry is configured for the project ID, with `url` and `mode`.
Only loopback HTTP/HTTPS URLs with an explicit port are allowed. The link opens
a new tab and labels simulation previews. It does not start a server; keep the
product running separately. This is the actual product, distinct from `/preview`
which is the dashboard design mockup.

## Request product changes

Open a product project and select **Changes**. Enter a prompt and choose
**Send change request**, then **Apply requested change** to authorize the paid
employee run. Requests persist as developer tasks with independent QA, fixed
local-scope constraints and the current project allowance. **View progress and
response** opens saved task evidence; **Run independent review** is available
after submission. Saving a prompt alone never runs a model. Review completion
is separate from deployment. Restart the product server after accepted backend
changes to load them; frontend files are served from the workspace.

When local recovery is enabled, diagnosed local failures in **Changes** requests
also receive bounded repairs, even outside an installed delivery plan. Saved-only
requests are not automatically started. Original failures and attempts remain
in audit history; one specialist replacement per lineage is allowed, with the
existing budget, pause and independent-review gates. Before self-checks, employees
now read current source through granted workspace tools so historical readbacks
do not conceal a corrected implementation. Final evidence includes those snapshots.

## Automatic project changes and live employee status

In **Projects → Changes**, **Run autonomously** is selected by default. Choosing
**Send & start autonomously** records authorization for developer execution,
independent review and scoped corrections within the existing project allowance.
The supervisor advances those tasks every five seconds while the dashboard runs.
Uncheck it to save a draft request without starting work. The local
`project_changes_autonomous` preference also enables review/rework handoffs for
already-started chat tasks; it never starts saved-only requests with zero attempts.
Known local failures route to Repair Engineer when local recovery is enabled.
Each lineage remains bounded, and original errors and attempts stay recorded.

Project headers, task tables and change cards show the running employee with a
loading indicator. Error icons open task details with the actual failure note,
quality reports and audit history. Repaired errors are labelled as previous errors.
Pause, exhausted allowance/attempts, missing tools and uncertain review/provider
outcomes stop automatic execution. A failed review call for the same attempt is
not silently repeated. Production deployment is not authorized by a change prompt.

Dashboard history and logs show full date and time in IST (Asia/Kolkata), newest activity first. Tasks show creation and latest recorded activity times recovered from durable events. Older records without timestamps display “Time not recorded.”
