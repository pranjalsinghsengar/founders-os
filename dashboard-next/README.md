# Company OS — connected Next.js dashboard

The main route now uses actual SQLite workflow records and the Python runtime.
The original dummy UI is preserved separately at `/preview`.

From the project root:

```sh
npm --prefix dashboard-next ci
npm --prefix dashboard-next run build
.venv/bin/python company_cli.py dashboard --next --port 3000 --open
```

The CLI starts a private loopback Python API and the Next.js server together.
Ctrl+C stops both. Starting `npm start` by itself does not connect the runtime;
the CLI supplies the private bridge configuration. No credentials are printed or
served. Launch from your credential-configured terminal for paid worker actions.
An `OPENAI_API_KEY` environment variable and a configured model are required for
model work; Gmail requires the existing local OAuth setup. Do not paste keys here.

## Working controls

- Persistent founder ideas and AI discovery research mandates.
- Focused public-source research of founder ideas, through the existing model API.
- Independent model review, research rework, complete proposal drafting and reviewed
  proposal registration as an unapproved product.
- Real project/task/budget/permission/dependency state, saved artifacts and feedback.
- Gmail request sending, authenticated decision polling and ambiguous-send reconciliation.
- Task assignment, grant/revoke, project pause/resume, planning, reviewed-plan installation,
  bounded scheduling and explicit employee execution.
- Actual local Git workspace initialization and scoped file/branch/hash inspection.
- Persistent jobs and audit history; local diagnostics and interrupted-run recovery.

Provider and Gmail actions require a confirmation dialog. Backend approval, grants,
allowances and attempt limits remain authoritative. Investment approval has no UI
bypass; founder decisions go through the authenticated Gmail flow. Internal units
are not a currency invoice ceiling. Job success means the CLI completed; inspect
the resulting task/review status to determine whether work was accepted.

## Idea-to-product walkthrough

1. Ideas: save your title, context and market. Saving does not spend credits.
2. Choose **Deep research this idea**, review the allowance, then explicitly authorize
   paid work. Alternatively, authorize AI discovery for a market.
3. Inspect the actual research task/report, sources and failure/review feedback.
4. Run independent model QA. Rework only when changes are requested.
5. Once research is accepted, draft the full proposal and independently review it.
6. Submit the accepted proposal with a product allowance. This creates an unapproved
   candidate; it does not start product work or inherit research permissions.
7. Project → Decisions: send the complete Gmail approval request, reply as founder,
   and poll authenticated decisions.
8. After product approval, initialize the repository with delivery grants, generate
   and independently review a plan, install it and run bounded employee steps.
9. Inspect actual files and QA evidence. Product readiness still needs the missing
   release/behavioral integrations below.

## Remaining integrations and limits

Only OpenAI Responses executes live model employees today. Claude, NVIDIA-hosted,
GLM, Qwen and provider routing remain design previews; no live adapter is claimed.
Isolated application builds, browser journeys, deployment/health/rollback and
reliable unattended service remain outstanding. GitHub create/push/reconciliation
and market-grouped new local roots are implemented as described below. Existing Python workspaces keep `workspaces/<project-id>/`; new roots use
`workspaces/<market>/<project-id>/`. The runtime
permits bounded static files. It does not execute arbitrary generated applications.
No product is declared ready merely because files or a local commit exist.

The loopback service is for one trusted local operator. Dashboard jobs are
serialized in SQLite across controllers; CLI workers outside the dashboard are not
covered by that lock. Do not recover while any worker is active. Restart marks
orphaned jobs interrupted and never automatically repeats external actions.

The UI refreshes every four seconds. Activity is limited to the latest 250 events
and Jobs to the latest 100 records. Artifact/file previews are scoped and redacted;
credential files are never exposed. No arbitrary shell/file API exists.

## Verification

Production build, Python workflow/HTTP regressions and a real isolated
Next.js → Python → SQLite/CLI/Git integration check pass. Integration research
uses a scripted model; no paid provider call or Gmail send was performed during
connection work. Interactive visual browser verification remains pending.

## Actual GitHub delivery

New approved repositories are grouped under `workspaces/<market>/<project-id>/`;
existing registered repositories keep their location. Market is transferred from
research to candidate creation. The Repository tab lists actual files and hashes.

You may explicitly create a private GitHub remote, push the current committed
product revision or reconcile an unknown outcome. Supply `OWNER/REPOSITORY` and
confirm the external operation. Authenticate the GitHub CLI locally first, e.g.
`gh auth login`; no token is accepted or printed by the dashboard. No GitHub remote was created or pushed during developer verification; these tests
mock GitHub.

Remote creation is recorded before requesting it and cannot be blindly repeated.
Push requires clean committed permitted files, rejects credential-like material,
disables Git hooks, binds the expected commit and verifies the remote product
branch SHA. Unknown push outcomes block another push until reconciliation.
Neither a successful push nor a static QA result certifies product readiness.
Deployment, isolated app execution and browser acceptance are still missing.

For local static QA, Task details can accept an operator-controlled criterion-to-
check JSON mapping. Exactly one fixed check must cover each acceptance criterion.
This queues real independent file checks without a model call or shell command.

## Local OpenAI credential setup

If the running process has no OpenAI key, paid controls are disabled. AI Providers
has a password field that saves the key **locally** under `.secrets/openai-key`,
atomically with file mode 600. The value is never returned, printed or included in
audit events. The backend process and subsequent CLI workers load it locally.
Saving does not test the provider or incur a model call; the UI labels presence
separately from provider acceptance. Credential changes are rejected during active
dashboard jobs. An existing environment key takes precedence on a later CLI launch.
GitHub auth and Gmail OAuth still use their separate local setup procedures.
