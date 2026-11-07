"""Codex text/action adapter. Company, never Codex, executes employee tools."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
from core import ToolFailure
from local_ai import resolve_local_ai

SCHEMA = {'type':'object','additionalProperties':False,'required':['text','calls'],
 'properties':{'text':{'type':'string'},'calls':{'type':'array','maxItems':8,'items':{
 'type':'object','additionalProperties':False,'required':['name','arguments'],
 'properties':{'name':{'type':'string'},'arguments':{'type':'string'}}}}}}

class CodexCLI:
    def __init__(self, model=None, timeout=180, executable=None):
        self.command = resolve_local_ai('codex',executable)
        if not self.command:
            raise ToolFailure('cli_missing')
        if type(timeout) is not int or not 10 <= timeout <= 600:
            raise ValueError('CLI timeout must be 10..600 seconds')
        self.model, self.timeout = model, timeout

    def complete(self, instructions, history, tools):
        prompt = ('You are a Company model adapter. Do not use native tools or inspect local files. '
                  'Return JSON with text and calls. Calls are proposals for the external Company gateway, '
                  'not actions you execute. Use only supplied tool names, JSON-encode each arguments object. '
                  'When no tools are supplied return calls=[] and put the entire requested answer '
                  '(including any requested JSON) in text. Never claim a proposed action has executed.\n' +
                  json.dumps({'instructions':instructions,'history':history,'permitted_tools':tools}))
        if len(prompt.encode()) > 1000000:
            raise ToolFailure('cli_invalid_response')
        # Reuse CLI auth, not company API/OAuth keys. Ignore personal plugins/MCP/hooks.
        env = {k:os.environ[k] for k in ('PATH','HOME','CODEX_HOME','SYSTEMROOT','TMPDIR') if k in os.environ}
        with tempfile.TemporaryDirectory(prefix='company-codex-') as directory:
            root = Path(directory)
            schema, output = root/'schema.json', root/'answer.json'
            schema.write_text(json.dumps(SCHEMA)); schema.chmod(0o600)
            args = [self.command,'exec','--ignore-user-config','--ignore-rules','--ephemeral',
                    '--skip-git-repo-check','--sandbox','read-only','--color','never',
                    '--disable','shell_tool','--disable','apps','--disable','plugins',
                    '--disable','hooks','--disable','multi_agent','--disable','browser_use',
                    '--disable','computer_use','--disable','image_generation',
                    '-c','web_search="disabled"','-c','approval_policy="never"',
                    '--output-schema',str(schema),'--output-last-message',str(output),'-']
            if self.model:
                args[-1:-1] = ['--model',self.model]
            try:
                # Raw CLI diagnostics are withheld: may contain authentication data.
                result = subprocess.run(args,input=prompt,text=True,cwd=root,env=env,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=self.timeout)
            except subprocess.TimeoutExpired:
                raise ToolFailure('cli_timeout') from None
            except OSError:
                raise ToolFailure('cli_missing') from None
            if result.returncode:
                raise ToolFailure('cli_execution')
            try:
                if output.is_symlink() or not output.is_file() or output.stat().st_size > 200000:
                    raise ValueError()
                answer = json.loads(output.read_text())
                from jsonschema import validate
                validate(answer,SCHEMA)
                allowed = {t['name']:t for t in tools if t.get('type')=='function'}
                calls = []
                for call in answer['calls']:
                    if call['name'] not in allowed:
                        raise ValueError()
                    arguments = json.loads(call['arguments'])
                    if not isinstance(arguments,dict):
                        raise ValueError()
                    validate(arguments,allowed[call['name']]['parameters'])
                    calls.append({'type':'function_call','call_id':str(uuid.uuid4()),
                                  'name':call['name'],'arguments':json.dumps(arguments)})
                if not calls and not answer['text'].strip():
                    raise ValueError()
            except Exception:
                raise ToolFailure('cli_invalid_response') from None
        message = {'type':'message','role':'assistant','content':[{'type':'output_text','text':answer['text']}]}
        return {'status':'completed','output':calls if calls else [message],
                'usage':{'provider':'codex_cli','token_usage':'not collected'}}

    def research(self, instructions, history, max_search_calls=4):
        # Existing research validator requires actual Responses web_search evidence.
        raise ToolFailure('cli_research_unavailable')


def make_model(config, max_output_tokens=2000):
    runtime = config.get('model_runtime','openai_api')
    if runtime == 'codex_cli':
        return CodexCLI(config.get('codex_model'),config.get('codex_timeout_seconds',180),config.get('codex_executable'))
    if runtime != 'openai_api':
        raise ValueError('Unsupported model runtime')
    from integrations import OpenAIResponses
    return OpenAIResponses(config['model'],max_output_tokens=max_output_tokens)
