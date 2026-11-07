# Autonomous AI Company — Operating Blueprint

Version 2 · 3 October 2026 · Founder: Pranjal Sengar

7 October backend checkpoint: scoped source writes now include Python and
TypeScript. Offline Python unittest execution is available through a trusted
operator-configured Docker image. Source snapshots omit company credentials and
tests receive no network access. Syntax and functional test evidence remain
distinct from model reviews and complete product/release certification.

6 October checkpoint: opt-in idea workflows now schedule the research-to-proposal
handoffs and authenticated Gmail decision monitoring. Accepted investment
decisions advance to bounded local delivery automatically; action-limit pauses
continue without founder clicks. Project pause, task failures, uncertain external
outcomes and exhausted allowances stop scheduling. The scheduler runs only while
the dashboard server is running. No workflow was activated during development;
tests use scripted models and fake mail. Fully built, tested and deployed apps
still require missing build, browser/device QA and hosting integrations.

Current delivery checkpoint: an approved product now has one bounded autonomous
delivery action. The orchestrator assigns configured roles, grants scoped local
permissions, prepares and independently reviews a plan, installs tasks and creates
the market/project workspace, then advances build/QA/rework handoffs. Manual
assignment and permissions are advanced controls. Approval, pause, attempt and
allowance limits remain enforced; no budget increase, outreach or deployment is
implicit. This is a bounded run with durable state, not an unattended service.
Isolated builds, mobile/device execution, browser QA and release integrations
remain missing. Tests exercise scripted models and real local Git, not a live
end-to-end product launch.

## 1. Mission and agreed scope

Distribution target: founders download the orchestration application from GitHub
and run it locally. Setup detects installed AI CLIs (initially Codex and Claude),
offers a provider choice and should reuse each provider's local authentication.
CLI detection and Codex employee/planner/review execution are implemented.
Codex reuses local authentication; verify with `ai-verify`. Claude and Codex
research evidence adapters remain missing. The API runtime remains selectable.
Generated products live in separate market/project workspaces. Source exports
include code and verification metadata; a package is only considered final after
its required build, executable QA and release gates pass.

Build a company operated by AI employees that discovers product opportunities, prepares complete investment proposals, obtains the founder’s approval by email, and then independently plans, builds, verifies, launches, supports, and improves approved products.

The company is not limited to invoicing apps or any predetermined product. Software products are the initial implementation scope. Physical products and other businesses require additional operational capabilities before they can be executed autonomously.

Autonomy means workers can make routine decisions and complete workflows within granted authority. It does not imply guaranteed demand, profitability, legal accountability, or unlimited spending.

This document defines the system to build. No live workers, email connections, campaigns, payments, or deployments have been activated by creating it.

## 2. Founder and company authority

The founder defines the company mission, available capital, permitted markets, and spending policy. Each new product requires investment approval. Once approved, the team executes without requiring the founder to assign individual tasks.

| Decision | Authority |
|---|---|
| Research and internal planning | Autonomous within the research allowance |
| Start a new product | Founder approves a versioned proposal |
| Assign tasks and choose implementation details | AI management within approved scope |
| Release approved product | Release worker after independent checks and within granted deployment authority |
| Contact prospects or run campaigns | Only within an explicitly granted communication and campaign policy |
| Spend funds | Approved categories and enforceable limits |
| Increase budget or materially change scope | Founder approves amendment |
| Enter contracts or make commitments outside delegated authority | Escalate to founder |
| Pause unsafe or malfunctioning work | Automatic controls and founder |
| Stop a product experiment | Management within approved stop rules; record rationale |

Policies must be enforced by the tool gateway and workflow engine. A prompt telling an employee to respect a budget is insufficient.

## 3. Employees and handoffs

| Employee | Required output | Who verifies it |
|---|---|---|
| Researcher | Opportunity brief with dated sources, customer problem, competing options, evidence and uncertainties | Product manager |
| Product manager | Investment proposal, requirements, task graph, acceptance criteria and metrics | Management; founder approves investment |
| Company manager | Resource allocations, blocker decisions and progress reports | Policy engine and audit records |
| Designer | User journeys, screens, component specifications and usability findings | Product manager and frontend worker |
| Engineering lead | Architecture, interfaces, risk assessment and implementation plan | Independent technical reviewer |
| Developer | Code, implementation notes and executable validation | Reviewer and QA |
| QA worker | Test results, defects, reproducible evidence and release recommendation | Release gates |
| Release/operations worker | Deployment record, rollback plan, monitoring and incident handling | Automated checks and independent review |
| Growth worker | Approved acquisition experiments with cost and outcome records | Product manager and finance |
| Support worker | Resolved enquiries, escalations and recurring customer problems | Quality sampling and policy checks |
| Finance worker | Cost ledger, reconciled revenue, forecasts and budget alerts | Deterministic accounting checks |

Roles are logical responsibilities. They do not all need permanent running agents. Start workers when a task requires them. Reviewers must not approve their own deliverables; critical checks should use executable evidence rather than agreement between models alone.

## 4. Product lifecycle

Research → evidence review → validation → proposal → awaiting approval → planning → development → independent verification → release → measurement → improve, pivot or stop.

Research can continue while a proposal awaits approval, but that product must not enter execution. Failed verification returns work to the responsible employee. A blocked dependency pauses dependent tasks only. Budget exhaustion pauses actions that incur additional costs.

Every transition records the actor, time, input version, evidence, policy decision and resulting state. Completion requires verified artifacts, not a worker’s claim that the work is done.

## 5. Research and investment proposal

Research begins with a recurring customer problem, not a predetermined feature list. Workers distinguish observed facts, inferred conclusions and untested assumptions. Popularity alone is not proof of willingness to pay.

Each proposal contains:

1. Target customer and specific problem.
2. Evidence of frequency, urgency and existing workarounds.
3. Competitor comparison with dated sources.
4. Demand validation performed, results and remaining uncertainties.
5. Product positioning and proposed advantage.
6. MVP scope, exclusions, user journeys and acceptance criteria.
7. Pricing hypothesis and acquisition approach.
8. Technical and operational feasibility, dependencies and risks.
9. Investment request, cost categories, recurring expenses and proposed schedule.
10. Launch requirements and independent quality checks.
11. Success metrics, measurement period, continuation and stop criteria.
12. Exact authority requested from the founder.

Never fabricate interviews, customer commitments, traffic, conversion rates or market sizes. If evidence is insufficient, submit a validation experiment or reject the opportunity rather than manufacture confidence.

## 6. Email approval protocol

The email includes a concise summary and access to the complete immutable proposal. Bind the approval to project ID, proposal version/hash, founder identity, budget, permitted actions and expiration.

Illustrative reply: APPROVE PROJECT-104 VERSION-3. A bare “yes” without unambiguous project context is not enough. Authenticate the reply through the selected email integration and founder account; uncertain replies can lead to a signed confirmation page. Reject spoofed, expired, superseded and duplicate approvals.

Approval creates one recorded authorization and one workflow. Repeated email delivery must not start duplicate projects. Revisions affecting scope or investment invalidate prior pending approval. Rejection archives the proposal; requested changes return it to the product manager.

Gmail is the selected provider. The founder account must be connected locally through OAuth before this feature can operate.

## 7. Company operating system

| Component | Function |
|---|---|
| Control centre | Projects, proposals, workers, tasks, budgets, incidents and pause controls |
| Durable workflow engine | Persist lifecycle state, dependencies, retries, deadlines and resumable execution |
| Worker runtime | Execute role-specific tasks with scoped tools and bounded context |
| Policy/tool gateway | Enforce identity, permissions, action limits and budget reservations |
| Shared memory | Versioned requirements, decisions, research, code artifacts and customer learning |
| Verification service | Run tests, check artifacts and enforce release gates |
| Event/audit log | Record decisions, tool actions, approvals and state changes |
| Cost ledger | Reserve spending, reconcile actual charges and prevent concurrent overspending |
| Integration adapters | Email, repositories, execution environments, hosting, analytics and support |

Workers return structured results: output artifact, evidence, cost, status, confidence and blockers. The workflow engine decides the next valid action. External websites, emails and documents are untrusted inputs and cannot grant permissions or override company policy.

## 7A. Plugins, skills and MCP tools

AI employees must execute tasks through connected tools and produce verifiable results. In this system, a plugin is an integration bundle, a skill supplies task instructions, and an MCP server exposes callable capabilities. Their availability does not automatically grant permission to use an account or perform an action.

Maintain a capability registry containing tool names and schemas, provider/server identity, approved versions, required skills, authentication reference, role grants, project scope, read/write classification, spending policy, rate limits, connection health and approved fallback capabilities. Discover capabilities from approved connections; do not install arbitrary plugins or MCP servers automatically.

| Employee | Capability categories | Completion evidence |
|---|---|---|
| Researcher | Search, authorised browser access, research/data connectors | Sources, observations and saved research artifacts |
| Product manager | Documents and task management | Versioned requirements and linked tasks |
| Designer | Design editor, assets and design skills | Accessible design artifacts and specifications |
| Developer | Repository, terminal, database and API tools | Reviewed changes and execution results |
| QA | Browser automation, test runners and issue tracking | Reproducible tests, screenshots and defect records |
| Operations | Hosting, deployment and monitoring | Release identifier, health checks and rollback record |
| Growth/support | Analytics, CRM, email and support integrations | Authorised action records and measured outcomes |
| Finance | Billing and payment reporting | Reconciled ledger entries |

These categories describe required capabilities, not already connected providers. Select actual providers during implementation after checking their current capabilities and costs.

For every task, the orchestrator identifies needed capabilities and grants only the required tools. The employee loads applicable skills, checks access and connection health, executes calls through the policy gateway, saves artifacts, and submits evidence for independent review. The gateway enforces permissions before execution; MCP is a connection protocol, not an authorization policy.

Missing access creates a precise blocker identifying the connection or grant needed. Transient failures receive bounded retries; an approved alternative may be selected without expanding authority. After an ambiguous write failure, reconcile external state before retrying. Expired credentials, rate limits and incompatible schemas must not be reported as successful work.

Record each call's task/run identity, tool version, redacted inputs, outcome, external artifact reference, timing and cost. Keep secrets out of employee prompts and logs. Integration instructions and returned content cannot expand authority. Changes to plugins or server capabilities require compatibility verification before existing workflows adopt them.

Example: a developer receives a login-page task, reads approved requirements and design through connected tools, edits an isolated repository branch, and runs checks. QA uses browser and test tools to verify the customer journey. Verified artifacts close the task; merely generating a description of a login page does not.

## 8. Minimum data model

CompanyPolicy; Opportunity; Evidence; ProposalVersion; Approval; Project; EmployeeRole; Task; TaskDependency; WorkerRun; ArtifactVersion; Review; CapabilityRegistryEntry; PluginVersion; MCPConnection; SkillBinding; ToolGrant; ToolCall; Budget; BudgetReservation; LedgerEntry; Event; Incident; Experiment; MetricObservation.

Each task records project, owner, input versions, deliverable, acceptance criteria, reviewer, dependencies, deadline, spending allowance, attempts and state. States: queued, ready, running, awaiting review, changes requested, blocked, completed, failed or cancelled.

Keep customer and project information isolated. Restrict credentials to the tool gateway and authorised integrations, rather than shared worker memory.

## 9. Failure and recovery

Persist checkpoints before handing work off. Use idempotency keys for external actions such as emails, payments and deployments. After an ambiguous failure, inspect the external outcome before retrying.

Bound retries by count, cost and time. Repeated failures become incidents with an owner and escalation path. Changes use isolated environments, reviewed integration and rollback-capable releases. A company-wide pause prevents new actions; emergency rollback remains available under its own restricted authority.

Preserve backups and test recovery. Log exceptions without exposing credentials. Monitor stalled tasks, failed jobs, error rates, external service health and cost anomalies.

## 10. Measures of success

Track two separate outcomes:

| Company execution | Product business |
|---|---|
| Verified task completion and rework rate | Validated customer demand |
| Cycle time and time spent blocked | Activation and repeat usage |
| Spending against approved budget | Paying customers and revenue |
| Failed releases and recovery time | Acquisition cost and contribution margin |
| Founder interventions per project | Retention, support burden and profitability |

Set product-specific thresholds in the proposal before launch. A task completed or an application deployed is not evidence of a successful business.

## 11. Implementation milestones

### Milestone 1: Reliable internal workflow

Build the policy model, project/task records, durable execution, artifact storage, capability registry, tool gateway and audit trail. Demonstrate a synthetic proposal-to-review workflow without real spending or external communications. Prove restart recovery, bounded retries, dependency handling and pause behaviour. Verify a permitted tool call succeeds, a prohibited call is blocked, a missing connection creates a blocker, and duplicate action events do not cause duplicate writes.

### Milestone 2: Research and approval

Connect authorised research tools and the founder’s selected email account. Produce one evidence-backed proposal. Verify approval identity, version binding, rejection, expiration and duplicate-event handling.

### Milestone 3: Autonomous product delivery

Connect the code repository, isolated execution and test environment. Translate an approved proposal into design and engineering work. Demonstrate QA rejecting a defect and the developer fixing it. Verify a deployable artifact against requirements.

### Milestone 4: Release and operations

Connect approved hosting and observability. Deploy, verify production behaviour, exercise rollback and handle a simulated incident. No unconfigured integration should be represented as active.

### Milestone 5: Business feedback loop

Connect approved customer acquisition, support, payment and analytics capabilities. Run a bounded experiment, reconcile costs and results, and make an evidence-backed continue/pivot/stop decision.

First business proof: one opportunity becomes an approved product that reaches a paying customer and produces an accurate outcome report. First engineering proof: the workflow runs, survives failure, and respects approval and spending limits.

## 12. Outstanding setup decisions

Before live execution, configure the research allowance, product investment ceiling, permitted markets, founder email identity, model/tool accounts, repository, hosting, customer communication rules and spending permissions. These are configuration requirements, not reasons to delay the internal workflow implementation.

This blueprint intentionally leaves vendor selection open. Technical choices should be checked against current capabilities, pricing and the deployment environment during implementation.

## 13. Implementation checkpoint — 4 October 2026

Gmail is the selected founder approval provider. The implementation uses the
founder account directly and verifies decisions against replies in that account's
Sent mailbox, the original thread, request binding and expiry. Complete proposals
are attached to request emails. Repeated replies cannot duplicate authorization;
ambiguous delivery is reconciled before further sends. Local OAuth setup remains
required; no Gmail account or real email has been exercised during development.

The initial discovery direction is recurring workflow problems among small
service businesses. This is a research scope, not a chosen product or validated
market. Employees must compare opportunities and report missing demand evidence.
Only public-source desk research is contemplated initially; acquisition campaigns,
prospect contact, purchases and deployment require explicit authority.

Working local code now includes reviewed task-graph installation, bounded ready
task scheduling, model evidence review, optional operator-configured executable
QA, and Gmail approval policy. The Gmail tests use fake transport; model tests
use scripted responses. Real MCP stdio and local QA process execution are tested.
Live research, repository and hosting integrations, control dashboard, cost
reconciliation and reliable unattended operation remain outstanding. Planning
is still a separate command after approval; email polling does not start paid
workers or grant capabilities automatically.

The hosted research adapter and `research-cycle --send-approval` now implement
the research-to-proposal-to-email path. The operator command grants a separate
research-only mandate; resulting candidate projects remain unapproved and inherit
no permissions. Provider-returned sources are saved and draft references checked.
Research and proposal receive separate model assessments before sending. Full-cycle
tests use scripted models and fake Gmail; live provider calls remain unverified.
Repository, hosting, independent research execution checks and unattended recovery
remain outstanding. See Stage 6 in LIVE-SETUP.md for the local live-run command.

The local Company OS dashboard is now implemented, initialized and launched with
`company_cli.py init --open`. It observes existing SQLite records, role assignments,
review feedback, artifacts, Gmail approval history, internal allowances and events.
Project pause/resume is available and audited. It does not start paid employees,
raise allowances, approve investments or perform deployments. Repository/hosting
and reliable unattended operation remain outstanding. Browser layout QA remains
pending; data, HTTP controls and UI render checks pass.

Local delivery checkpoint: approved-product Git workspaces and task-bound stdio
MCP repository tools are implemented. Tools write permitted static product files
and create real local commits, with approval/pause/grant checks on each call.
Independent static QA records hashes and supports defect rejection and rework.
All 72 Python tests and dashboard rendering checks pass. Delivery integration
tests use scripted models and synthetic approvals; no genuine product was approved
or built in this checkpoint. Browser behavior, remote repository/deployment and
unattended execution remain outstanding. Milestones 1–3 are not yet demonstrated
as a complete live end-to-end workflow. See LIVE-SETUP.md Stage 8.

Dashboard control checkpoint: the operator console now dispatches workflow actions
through fixed CLI commands, with persistent job status, serialized execution,
explicit provider/email confirmation and audited capability grant/revoke. Existing
approval/budget gates remain authoritative. This is a local control layer, not a
production unattended service; deployment and complete live product proof remain
outstanding. See LIVE-SETUP.md Stage 9.

## Idea-first and multi-model product direction

Opportunities may originate from AI discovery or founder input in any market,
including existing profitable categories. Both paths require deep research and
independent critical review before founder submission converts an idea into a
project. Research must assess demand, competition, attributable revenue evidence,
flaws, differentiation, feasibility, costs, risks, validation and stop criteria.
Commercial success is uncertain and must not be fabricated or guaranteed.
Project creation is distinct from investment approval and execution authority.

Employees are logical roles that can be assigned models from multiple providers,
including OpenAI, Anthropic, NVIDIA-hosted models, GLM, Qwen and additional hosted
or local providers. Independent reviewer identity remains mandatory. The Next.js
prototype represents this flow with dummy reports and provider routing; production
adapters and genuine deep research are not implemented by these design screens.

## Complete delivery contract

The intended outcome for an approved product is a complete working deliverable:
a dedicated repository and product root grouped by market, implemented agreed
scope, independent behavioral QA, review bound to a Git revision, verified remote
push, setup/configuration documentation and an authorized release with health and
rollback evidence. Folder creation, code generation, a commit or a push alone do
not establish completion. Missing integrations or checks must remain visible.
The Next.js Repository screen previews this contract with simulated steps only;
current Python workspaces remain local and have no remote push/deployment adapter.

Connected control-center checkpoint: Next.js now uses real persisted ideas,
projects, tasks, approvals, capabilities, jobs and artifacts through a private
loopback Python API. Provider/email actions require explicit authorization and
existing engine policy. The former dummy dashboard remains isolated at `/preview`.
Founder ideas can be researched directly; reviewed proposals become unapproved
products. Actual local Git workspaces now support market grouping for new roots.
Explicit GitHub private creation/push/reconciliation is implemented with verified
remote commit SHA and unknown-outcome blocking. GitHub calls are mocked in tests;
no live remote was created. Multi-provider adapters, isolated full builds, browser
QA, hosting and production unattended operation remain outstanding.
