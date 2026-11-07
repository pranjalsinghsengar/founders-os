import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from core import Company, PolicyError, ToolFailure
from integrations import MCPConnections
from codex_runtime import make_model
from worker import Employee
from qa import run_review
from orchestration import generate_plan, install_plan, run_ready
from executable_qa import run_executable_review
from gmail_approval import Gmail, GmailError, EmailApprovals, connect
from discovery import discover, draft_proposal, register_proposal
from workspace import setup_workspace, setup_market_workspace, get_workspace, review_workspace, TOOLS


def execute_employee(c, task, cfg, config_path):
    row = c.db.execute('SELECT * FROM tasks WHERE id=?', (task,)).fetchone()
    if row is None or row['owner'] not in cfg['employees']:
        raise PolicyError('Unknown task or unconfigured employee role')
    role = cfg['employees'][row['owner']]
    model = make_model(cfg, max_output_tokens=cfg.get('max_output_tokens', 2000))
    granted = {r[0] for r in c.db.execute('SELECT tool FROM grants WHERE project=? AND role=?',(row['project'],row['owner']))}
    # Start only explicitly granted configured connections, not unrelated fixtures.
    servers = [s for s in cfg.get('mcp_servers', []) if any(g.startswith(s['name'] + '/') for g in granted)]
    if any(g.startswith('workspace/') for g in granted):
        get_workspace(c,row['project'])
        servers.append({'name':'workspace','command':sys.executable,
                        'args':[str(Path(__file__).parent/'workspace_mcp_server.py'),'--db',str(Path(c.db.execute('PRAGMA database_list').fetchone()[2]).resolve()),'--task',task,'--config',str(config_path)],
                        'allow_tools':{name:{'cost_units':0} for name in TOOLS}})
    async def work(payload):
        async with MCPConnections(servers) as connections:
            skills = [str(config_path.parent / p) for p in role.get('skills', [])]
            return await Employee(c, task, model, connections, row['owner'],
                config_path.parent / 'artifacts', skills, role.get('max_rounds',cfg.get('max_rounds', 6)), cfg).run(payload)
    c.register_tool(row['tool'], lambda payload: asyncio.run(work(payload)), role['run_cost_units'])
    return c.execute(task)


def main():
    parser = argparse.ArgumentParser(description="Trusted local company operator CLI")
    parser.add_argument("--db", default="company.db")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser('ai-discover', help='Detect local AI CLI installations without model calls')
    verify=commands.add_parser('ai-verify',help='Perform one live harmless request using the selected model runtime')
    verify.add_argument('--config',default='company.config.json')
    p=commands.add_parser('failure-notify')
    p.add_argument('notification')
    p.add_argument('--config',default='company.config.json')
    p=commands.add_parser('retry-autonomy')
    p.add_argument('workflow')
    p.add_argument('--config',default='company.config.json')
    p=commands.add_parser('increase-budget')
    p.add_argument('project')
    p.add_argument('--amount',type=int,required=True)
    p.add_argument('--expected-budget',type=int,required=True)
    p = commands.add_parser('export-project', help='Package actual product source and verification status')
    p.add_argument('project')
    p.add_argument('--output-dir', default='exports')
    p = commands.add_parser("propose")
    p.add_argument("file")
    p.add_argument("--budget", type=int, required=True)
    p = commands.add_parser("approve")
    p.add_argument("project")
    p.add_argument("digest")
    p = commands.add_parser("assign")
    p.add_argument("project")
    p.add_argument("role")
    p.add_argument("reviewer")
    p.add_argument("file")
    p = commands.add_parser("grant")
    p.add_argument("project")
    p.add_argument("role")
    p.add_argument("tool", help="employee.role or server/tool")
    p = commands.add_parser("run")
    p.add_argument("task")
    p.add_argument("--config", default="company.config.json")
    p = commands.add_parser("qa")
    p.add_argument("task")
    p.add_argument("--config", default="company.config.json")
    p.add_argument('--workspace-checks', help='Trusted JSON criterion-to-static-check mapping; no model call')
    p = commands.add_parser("review")
    p.add_argument("task")
    p.add_argument("reviewer")
    p.add_argument("decision", choices=["accept", "reject"])
    p.add_argument("note")
    for name in ('plan', 'tick'):
        p = commands.add_parser(name)
        p.add_argument('project')
        p.add_argument('--config', default='company.config.json')
        if name == 'tick':
            p.add_argument('--max-actions', type=int, default=10)
    p = commands.add_parser('start-delivery')
    p.add_argument('project')
    p.add_argument('--config', default='company.config.json')
    p.add_argument('--max-actions', type=int, default=10)
    p.add_argument('--resume', action='store_true', help='Explicitly resume a paused product and start its bounded delivery run')
    p = commands.add_parser('start-autonomy')
    p.add_argument('idea')
    p.add_argument('--research-mode', choices=('normal','deep'), default='normal')
    p.add_argument('--budget', type=int, default=100)
    p.add_argument('--product-budget', type=int, default=100)
    p.add_argument('--config', default='company.config.json')
    for name in ('advance-autonomy','resume-autonomy'):
        p = commands.add_parser(name)
        p.add_argument('workflow')
        p.add_argument('--config', default='company.config.json')
    p = commands.add_parser('apply-plan')
    p.add_argument('task')
    p.add_argument('--config', default='company.config.json')
    p = commands.add_parser('doctor')
    p.add_argument('--config', default='company.config.json')
    p = commands.add_parser('gmail-connect')
    p.add_argument('--founder', required=True, help='Your primary Gmail address; token account must match')
    p.add_argument('--client', default='.secrets/gmail-client.json')
    p.add_argument('--config', default='company.config.json')
    p = commands.add_parser('email-proposal')
    p.add_argument('project')
    p.add_argument('--lifetime-seconds', type=int, default=86400)
    p.add_argument('--config', default='company.config.json')
    p = commands.add_parser('email-reconcile')
    p.add_argument('request')
    p.add_argument('--config', default='company.config.json')
    p = commands.add_parser('email-poll')
    p.add_argument('--config', default='company.config.json')
    for name in ('discover', 'research-cycle'):
        p = commands.add_parser(name)
        p.add_argument('--idea', help='Persisted founder idea to research (discover only)')
        if name == 'discover':
            p.add_argument('--research-mode', choices=('normal','deep'), default='normal')
        p.add_argument('--market', default='Small service businesses')
        p.add_argument('--budget', type=int, default=100, help='Internal research allowance; not a provider invoice ceiling')
        p.add_argument('--config', default='company.config.json')
        if name == 'research-cycle':
            p.add_argument('--product-budget', type=int, default=100, help='Proposed internal product allowance; requires founder approval')
            p.add_argument('--send-approval', action='store_true', help='Send independently model-reviewed proposal to founder Gmail')
    p = commands.add_parser('draft-proposal')
    p.add_argument('task', help='Completed reviewed research task')
    p.add_argument('--config', default='company.config.json')
    p = commands.add_parser('rework-research')
    p.add_argument('task')
    p.add_argument('--research-mode', choices=('normal','deep'), help='Defaults to the previous research mode')
    p.add_argument('--config', default='company.config.json')
    p = commands.add_parser('register-proposal')
    p.add_argument('task', help='Completed reviewed proposal draft')
    p.add_argument('--budget', type=int, required=True)
    p = commands.add_parser('workspace-init')
    p.add_argument('project')
    p.add_argument('--config', default='company.config.json')
    p.add_argument('--grant-tools', action='store_true', help='Grant scoped local delivery tools to developer/designer and read access to reviewers')
    for name in ('repo-create','repo-push','repo-reconcile'):
        p=commands.add_parser(name)
        p.add_argument('project')
        if name=='repo-create':p.add_argument('--target',required=True,help='GitHub OWNER/REPOSITORY; private only')
    for name in ('init', 'dashboard'):
        p = commands.add_parser(name, help='Initialize and open the local control centre' if name == 'init' else 'Serve the local control centre')
        p.add_argument('--config', default='company.config.json')
        p.add_argument('--port', type=int, default=8787)
        p.add_argument('--next', action='store_true', help='Launch the connected Next.js control center')
        p.add_argument('--open', action='store_true', help='Open your browser when run locally')
        if name == 'init':
            p.add_argument('--ai', choices=('codex','claude'), help='Select installed Codex CLI runtime (Claude adapter unavailable)')
            p.add_argument('--no-serve', action='store_true', help='Initialize workspace without starting the server')
    commands.add_parser("status")
    commands.add_parser("recover")
    p = commands.add_parser("pause")
    p.add_argument("project")
    p.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    from local_credentials import load_local_credentials
    if hasattr(args,'config'):
        try:load_local_credentials(args.config)
        except PolicyError as error:parser.exit(1,str(error)+'\n')
    if args.command in ('init', 'dashboard'):
        from dashboard_server import initialize, serve, startup_error
        try:
            if args.command == 'init':
                from local_ai import discover_local_ai, select_local_ai
                initialize(args.db,args.config)
                print(json.dumps({'local_ai': discover_local_ai()}))
                if args.ai:
                    print(json.dumps(select_local_ai(args.config,args.ai)))
            if args.command == 'init' and args.no_serve:
                initialize(args.db,args.config)
                print('Company workspace initialized. Existing config and state preserved.')
            else:
                if not 0 <= args.port <= 65535:
                    parser.error('port must be 0..65535')
                if args.next:
                    from next_dashboard import serve_next
                    serve_next(args.db,args.config,3000 if args.port==8787 else args.port,args.open)
                else:serve(args.db,args.config,args.port,args.open)
        except (PolicyError,ToolFailure) as error:
            parser.exit(1,str(error)+'\n')
        except OSError as error:
            parser.exit(1,startup_error(error,3000 if args.next and args.port==8787 else args.port))
        return
    if args.command == 'ai-discover':
        from local_ai import discover_local_ai
        print(json.dumps({'local_ai': discover_local_ai()}, indent=2))
        return
    if args.command == 'ai-verify':
        cfg=json.loads(Path(args.config).read_text())
        from local_credentials import load_local_credentials
        if cfg.get('model_runtime','openai_api')=='openai_api':
            load_local_credentials(args.config)
        try:
            response=make_model(cfg).complete('Reply exactly: COMPANY_CLI_OK',[],[])
        except (PolicyError,ToolFailure,ValueError) as error:
            parser.exit(1,str(error)+'\n')
        from quality_gate import text_response
        print(json.dumps({'runtime':cfg.get('model_runtime','openai_api'),
                          'verified':text_response(response).strip()=='COMPANY_CLI_OK'}))
        return
    c = Company(args.db)
    try:
        if args.command == 'increase-budget':
            print(json.dumps(c.increase_budget(args.project,args.amount,args.expected_budget)))
        elif args.command == 'failure-notify':
            from failure_notifications import send_failure
            config_path=Path(args.config).resolve()
            print(json.dumps(send_failure(c,args.notification,json.loads(config_path.read_text()),config_path.parent)))
        elif args.command == 'retry-autonomy':
            from autonomy import retry_autonomy
            print(json.dumps(retry_autonomy(c,args.workflow,json.loads(Path(args.config).read_text()))))
        elif args.command == 'export-project':
            from project_export import export_project
            print(json.dumps(export_project(c,args.project,args.output_dir), indent=2))
        elif args.command == "propose":
            identifier, digest = c.project(json.loads(Path(args.file).read_text()), args.budget)
            print(json.dumps({"project": identifier, "digest": digest}))
        elif args.command == "approve": c.approve_local(args.project, args.digest)
        elif args.command == "assign":
            print(c.task(args.project, args.role, args.reviewer, "employee." + args.role,
                         json.loads(Path(args.file).read_text())))
        elif args.command == "grant": c.grant(args.project, args.role, args.tool)
        elif args.command == "review": c.review(args.task, args.reviewer, args.decision == "accept", args.note)
        elif args.command == "status": print(json.dumps(c.snapshot(), indent=2))
        elif args.command == "recover": print(c.recover_interrupted())
        elif args.command == "pause": c.pause(args.project, not args.resume)
        elif args.command == 'register-proposal':
            print(json.dumps(register_proposal(c, args.task, args.budget)))
        elif args.command in ('repo-create','repo-push','repo-reconcile'):
            from repository_remote import create_remote,push_remote,reconcile_remote
            fn={'repo-create':create_remote,'repo-push':push_remote,'repo-reconcile':reconcile_remote}[args.command]
            print(json.dumps(fn(c,args.project,args.target) if args.command=='repo-create' else fn(c,args.project)))
        elif args.command == 'workspace-init':
            config_path=Path(args.config).resolve()
            result=setup_market_workspace(c,args.project,config_path.parent/'workspaces')
            if args.grant_tools:
                permissions={'developer':TOOLS,'designer':TOOLS,
                             'qa':('read_file','list_files','inspect'),
                             'product_manager':('read_file','list_files','inspect')}
                for role,names in permissions.items():
                    c.grant(args.project,role,'employee.'+role)
                    for name in names:c.grant(args.project,role,'workspace/'+name)
                c.grant(args.project,'planner','employee.planner')
                cfg=json.loads(config_path.read_text())
                defaults=json.loads((Path(__file__).parent/'company.config.example.json').read_text())
                for role in permissions:
                    cfg.setdefault('employees',{}).setdefault(role,defaults['employees'][role])
                config_path.write_text(json.dumps(cfg,indent=2)+'\n')
                result['tools_granted']=True
            print(json.dumps(result))
        elif args.command in ('discover', 'draft-proposal', 'research-cycle', 'rework-research'):
            config_path = Path(args.config).resolve()
            cfg = json.loads(config_path.read_text())
            from research_modes import research_profile
            mode = getattr(args, 'research_mode', None)
            if args.command == 'rework-research' and mode is None:
                prior = c.db.execute('SELECT payload,output FROM tasks WHERE id=?',(args.task,)).fetchone()
                if prior:
                    mode = json.loads(prior['output'] or '{}').get('research_mode',json.loads(prior['payload']).get('research_mode','normal'))
            profile = research_profile(cfg, mode or 'normal')
            model = make_model(cfg, max_output_tokens=profile['max_output_tokens'])
            root = config_path.parent / 'artifacts'
            if args.command == 'rework-research':
                result = discover(c, model, cfg, root, rework_task=args.task, research_mode=mode)
            elif args.command == 'draft-proposal':
                result = draft_proposal(c, args.task, model, cfg, root)
            elif args.command == 'discover':
                idea=None
                if args.idea:
                    from idea_store import idea_by_id
                    idea=idea_by_id(c,args.idea)
                    if idea['research_task']:raise PolicyError('Idea already has research; inspect, review or rework the recorded task')
                if idea is None:
                    from idea_store import create_idea,idea_by_id
                    identifier=create_idea(c,'Opportunity discovery: '+args.market,'Public-source comparison before selecting a product.',args.market,'ai_discovery')['idea']
                    idea=idea_by_id(c,identifier)
                result = discover(c, model, cfg, root, args.budget, idea['market'], idea=idea, research_mode=mode)
            else:
                from discovery import research_cycle
                gmail = None
                if args.send_approval:
                    gc = cfg.get('gmail', {})
                    if not gc.get('founder') or not gc.get('token_file'):
                        raise GmailError('Connect founder Gmail before sending an approval request')
                    gmail = Gmail(config_path.parent / gc['token_file'], gc['founder'])
                result = research_cycle(c, model, cfg, root, args.budget, args.product_budget, args.market, gmail)
            print(json.dumps(result, indent=2))
        elif args.command == 'gmail-connect':
            config_path = Path(args.config).resolve()
            cfg = json.loads(config_path.read_text())
            token = config_path.parent / '.secrets/gmail-token.json'
            connect(Path(args.client).resolve(), token, args.founder)
            cfg['gmail'] = {'founder': args.founder.lower(), 'token_file': '.secrets/gmail-token.json'}
            config_path.write_text(json.dumps(cfg, indent=2) + '\n')
            print('Founder Gmail connected. No email sent.')
        elif args.command in ('email-proposal', 'email-poll', 'email-reconcile'):
            config_path = Path(args.config).resolve()
            cfg = json.loads(config_path.read_text())
            gmail_cfg = cfg.get('gmail', {})
            if not gmail_cfg.get('founder') or not gmail_cfg.get('token_file'):
                raise GmailError('Run gmail-connect locally before using email approval')
            gateway = EmailApprovals(c, Gmail(config_path.parent / gmail_cfg['token_file'], gmail_cfg['founder']))
            if args.command == 'email-proposal':
                request = gateway.prepare(args.project, args.lifetime_seconds)
                print(json.dumps({'request': request, 'status': gateway.send(request)}))
            elif args.command == 'email-reconcile':
                print(json.dumps({'request': args.request, 'status': gateway.reconcile(args.request)}))
            else:
                print(json.dumps(gateway.poll()))
        elif args.command == "qa":
            config_path = Path(args.config).resolve()
            cfg = json.loads(config_path.read_text())
            project = c.db.execute('SELECT project FROM tasks WHERE id=?', (args.task,)).fetchone()
            if project is None:
                raise PolicyError('Unknown task')
            checks = cfg.get('executable_qa', {}).get(project['project'])
            if args.workspace_checks:
                result = review_workspace(c,args.task,json.loads(Path(args.workspace_checks).read_text()),config_path.parent/'artifacts')
            elif checks is not None:
                result = run_executable_review(c, args.task, checks, config_path.parent / 'artifacts',
                                               cfg.get('qa_run_cost_units', 10))
            else:
                model = make_model(cfg, max_output_tokens=cfg.get('max_output_tokens', 2000))
                result = run_review(c, args.task, model, config_path.parent / 'artifacts',
                                    cfg.get('qa_run_cost_units', 10))
            print(json.dumps(result))
        elif args.command in ('start-autonomy','advance-autonomy','resume-autonomy'):
            from autonomy import start_autonomy,advance_autonomy,resume_autonomy
            config_path=Path(args.config).resolve();cfg=json.loads(config_path.read_text())
            if args.command=='start-autonomy':
                result=start_autonomy(c,args.idea,cfg,args.research_mode,args.budget,args.product_budget)
            elif args.command=='resume-autonomy':result=resume_autonomy(c,args.workflow)
            else:
                from delivery import run_delivery
                from research_modes import research_profile
                def model_factory(mode):
                    return make_model(cfg,max_output_tokens=research_profile(cfg,mode)['max_output_tokens'])
                def delivery(project):
                    model=model_factory('normal')
                    return run_delivery(c,project,model,cfg,config_path.parent,
                        lambda task:execute_employee(c,task,cfg,config_path),
                        lambda task:run_review(c,task,model,config_path.parent/'artifacts',cfg.get('qa_run_cost_units',10)))
                result=advance_autonomy(c,args.workflow,cfg,config_path.parent,model_factory,delivery)
            print(json.dumps(result))
        elif args.command in ('plan', 'tick', 'apply-plan', 'doctor', 'start-delivery'):
            config_path = Path(args.config).resolve()
            cfg = json.loads(config_path.read_text())
            if args.command == 'doctor':
                # Report presence only; never emit environment values or raw configuration.
                checks = {'model_runtime': cfg.get('model_runtime','openai_api'),
                          'cli_installed': bool(__import__('local_ai').resolve_local_ai('codex',cfg.get('codex_executable'))) if cfg.get('model_runtime')=='codex_cli' else None,
                          'model_configured': bool(cfg.get('model')) and not cfg['model'].startswith('REPLACE'),
                          'model_credential_present': bool(os.environ.get('OPENAI_API_KEY')),
                          'email_approval': 'implemented; requires local Gmail OAuth',
                          'gmail_configured': bool(cfg.get('gmail', {}).get('founder')),
                          'gmail_token_present': bool(cfg.get('gmail', {}).get('token_file')) and
                              (config_path.parent / cfg['gmail']['token_file']).is_file(),
                          'deployment': 'not configured by this runtime',
                          'research': 'OpenAI web_search path implemented; live run requires model credential and supported model',
                          'mcp_servers': []}
                for server in cfg.get('mcp_servers', []):
                    checks['mcp_servers'].append({'command_exists': Path(server['command']).is_file(),
                        'required_env_present': all(bool(os.environ.get(k)) for k in server.get('env_names', [])),
                        'allowlisted_tool_count': len(server.get('allow_tools', {}))})
                print(json.dumps(checks, indent=2))
            elif args.command == 'apply-plan':
                print(json.dumps(install_plan(c, args.task, cfg['employees'])))
            else:
                model = make_model(cfg, max_output_tokens=cfg.get('max_output_tokens', 2000))
                if args.command == 'start-delivery':
                    from delivery import run_delivery
                    checks = cfg.get('executable_qa', {}).get(args.project)
                    result = run_delivery(c,args.project,model,cfg,config_path.parent,
                        lambda task:execute_employee(c,task,cfg,config_path),
                        lambda task:(run_executable_review(c,task,checks,config_path.parent/'artifacts',cfg.get('qa_run_cost_units',10))
                                     if checks is not None and c.db.execute('SELECT tool FROM tasks WHERE id=?',(task,)).fetchone()[0]!='employee.planner'
                                     else run_review(c,task,model,config_path.parent/'artifacts',cfg.get('qa_run_cost_units',10))),
                        max_actions=args.max_actions,resume=args.resume)
                elif args.command == 'plan':
                    result = generate_plan(c, args.project, model, cfg, config_path.parent / 'artifacts')
                else:
                    checks = cfg.get('executable_qa', {}).get(args.project)
                    result = run_ready(c, args.project,
                        lambda task: execute_employee(c, task, cfg, config_path),
                        lambda task: (run_executable_review(c, task, checks, config_path.parent / 'artifacts',
                                                           cfg.get('qa_run_cost_units', 10)) if checks is not None else
                                      run_review(c, task, model, config_path.parent / 'artifacts',
                                                 cfg.get('qa_run_cost_units', 10))), args.max_actions)
                print(json.dumps(result))
        elif args.command == 'run':
            config_path = Path(args.config).resolve()
            print(execute_employee(c, args.task, json.loads(config_path.read_text()), config_path))
    except (GmailError, ToolFailure) as error:
        parser.exit(1, str(error) + '\n')
    finally:
        c.db.close()


if __name__ == "__main__":
    main()
