import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from core import ToolFailure
from codex_runtime import CodexCLI, make_model

class CodexRuntimeTests(unittest.TestCase):
    def invoke(self, answer, tools=()):
        def run(args, **kwargs):
            self.assertNotIn('OPENAI_API_KEY',kwargs['env'])
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',args)
            self.assertIn('--ignore-user-config',args)
            self.assertIn('shell_tool',args)
            Path(args[args.index('--output-last-message')+1]).write_text(json.dumps(answer))
            return subprocess.CompletedProcess(args,0)
        with patch('codex_runtime.shutil.which',return_value='/bin/codex'),patch('codex_runtime.subprocess.run',side_effect=run):
            return CodexCLI().complete('fixture',[],list(tools))
    def test_text_and_nested_review_json(self):
        result=self.invoke({'text':'{"accepted":true}','calls':[]})
        self.assertEqual(result['output'][0]['content'][0]['text'],'{"accepted":true}')
    def test_tool_proposal_is_not_executed(self):
        tool={'type':'function','name':'allowed','parameters':{'type':'object','required':['path'],'properties':{'path':{'type':'string'}},'additionalProperties':False}}
        result=self.invoke({'text':'','calls':[{'name':'allowed','arguments':'{"path":"app.py"}'}]},[tool])
        self.assertEqual(result['output'][0]['type'],'function_call')
        self.assertTrue(result['output'][0]['call_id'])
    def test_unauthorized_and_invalid_arguments_rejected(self):
        for name,args in [('outside','{}'),('outside','not json')]:
            with self.subTest(name=name,args=args), self.assertRaises(ToolFailure):
                self.invoke({'text':'','calls':[{'name':name,'arguments':args}]})
    def test_timeout_and_process_error_are_redacted(self):
        for effect,code in [(subprocess.TimeoutExpired('secret',1),'cli_timeout'),(subprocess.CompletedProcess([],1),'cli_execution')]:
            with patch('codex_runtime.shutil.which',return_value='/bin/codex'),patch('codex_runtime.subprocess.run',side_effect=effect if isinstance(effect,Exception) else None,return_value=effect):
                with self.assertRaises(ToolFailure) as raised: CodexCLI().complete('x',[],[])
                self.assertEqual(raised.exception.code,code)
    def test_cli_research_has_no_silent_api_fallback(self):
        with patch('codex_runtime.shutil.which',return_value='/bin/codex'):
            model=make_model({'model_runtime':'codex_cli'})
            with self.assertRaises(ToolFailure):model.research('x',[])
    def test_unknown_runtime_rejected(self):
        with self.assertRaises(ValueError):make_model({'model_runtime':'unknown'})
