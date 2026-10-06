import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from core import Company
from integrations import MCPConnections
from worker import Employee
from test_quality_gate import ready_response

try:
    import mcp
    import jsonschema
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


class ScriptedModel:
    def __init__(self, forbidden=False):
        self.calls = 0
        self.forbidden = forbidden

    def complete(self, instructions, history, tools):
        if instructions.startswith('Check your work before submission.'):
            return ready_response(history)
        self.calls += 1
        if self.calls == 1:
            return {"status": "completed", "output": [{"type": "function_call",
                "name": "forbidden" if self.forbidden else tools[0]["name"],
                "call_id": "call-1", "arguments": json.dumps({"topic": "company"})}]}
        assert history[-1]["type"] == "function_call_output"
        return {"status": "completed", "usage": {"output_tokens": 10}, "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "Local integration fixture completed."}]}]}


@unittest.skipUnless(HAS_MCP, "Install requirements.txt for real MCP transport tests")
class IntegrationTests(unittest.TestCase):
    def servers(self):
        return [{"name": "local", "command": sys.executable,
                 "args": [str(Path(__file__).parent.resolve() / "sample_mcp_server.py")],
                 "allow_tools": {"inspect_workflow": {"cost_units": 1}}}]

    def test_real_stdio_discovery_and_call(self):
        async def check():
            async with MCPConnections(self.servers()) as connection:
                self.assertEqual(len(connection.tools), 1)
                alias = next(iter(connection.tools))
                result = await connection.call(alias, {"topic": "test"})
                self.assertIn("Local test fixture", json.dumps(result))
                with self.assertRaises(Exception): await connection.call(alias, {"unexpected": True})
        asyncio.run(check())

    def run_employee(self, forbidden=False, grant=True):
        with tempfile.TemporaryDirectory() as folder:
            c = Company(str(Path(folder) / "company.db"))
            try:
                p, digest = c.project({"scope": "integration fixture"}, 50)
                c.approve_local(p, digest)
                c.grant(p, "researcher", "employee.researcher")
                if grant: c.grant(p, "researcher", "local/inspect_workflow")
                task = c.task(p, "researcher", "qa", "employee.researcher", {"acceptance_criteria":["Inspect fixture"]})
                async def work(payload):
                    async with MCPConnections(self.servers()) as connections:
                        return await Employee(c, task, ScriptedModel(forbidden), connections,
                                              "researcher", folder).run(payload)
                c.register_tool("employee.researcher", lambda p: asyncio.run(work(p)), 10)
                status = c.execute(task)
                snapshot = c.snapshot()
                if status == "awaiting_review":
                    self.assertTrue(Path(json.loads(snapshot["tasks"][0]["output"])["artifact"]).exists())
                return status, snapshot
            finally:
                c.db.close()

    def test_worker_with_real_mcp_and_scripted_model(self):
        status, snapshot = self.run_employee()
        self.assertEqual(status, "awaiting_review")
        self.assertEqual(snapshot["projects"][0]["spent"], 16)
        self.assertTrue(any(e["kind"] == "employee.tool.completed" for e in snapshot["events"]))

    def test_unauthorised_model_tool_blocked(self):
        status, snapshot = self.run_employee(forbidden=True)
        self.assertEqual(status, "failed")
        self.assertFalse(any(e["kind"] == "employee.tool.started" for e in snapshot["events"]))

    def test_ungranted_tools_hidden(self):
        status, snapshot = self.run_employee(grant=False)
        self.assertEqual(status, "failed")
        self.assertFalse(any(e["kind"] == "employee.tool.started" for e in snapshot["events"]))


if __name__ == "__main__":
    unittest.main()


class ModelDiagnosticTests(unittest.TestCase):
    def model(self):
        from unittest.mock import patch
        from integrations import OpenAIResponses
        with patch.dict('os.environ', {'OPENAI_API_KEY':'synthetic-key'}):
            return OpenAIResponses('fixture-model')
    def test_http_errors_are_classified_without_provider_body(self):
        import io
        import urllib.error
        from unittest.mock import patch
        from core import ToolFailure
        model = self.model()
        for status, code in ((400,'api_400'),(401,'api_401'),(403,'api_403'),(404,'api_404'),(429,'api_429'),(503,'api_server')):
            error = urllib.error.HTTPError('https://api.openai.com/v1/responses',status,
                                          'private-provider-detail',{},io.BytesIO(b'private-provider-body'))
            with patch('integrations.urllib.request.urlopen',side_effect=error):
                with self.assertRaises(ToolFailure) as result: model.complete('fixture',[],[])
            self.assertEqual(result.exception.code,code)
            self.assertNotIn('private-provider',str(result.exception))
    def test_timeout_is_classified(self):
        from unittest.mock import patch
        from core import ToolFailure
        with patch('integrations.urllib.request.urlopen',side_effect=TimeoutError('private-marker')):
            with self.assertRaises(ToolFailure) as error: self.model().complete('fixture',[],[])
        self.assertEqual(error.exception.code,'network_timeout')
    def test_open_weight_model_rejected_before_network_call(self):
        from unittest.mock import patch
        from integrations import OpenAIResponses
        from core import ToolFailure
        with patch.dict('os.environ',{'OPENAI_API_KEY':'synthetic-key'}):
            with self.assertRaises(ToolFailure) as error: OpenAIResponses('gpt-oss-120b')
        self.assertEqual(error.exception.code,'unsupported_hosted_model')


class QuotaClassificationTests(unittest.TestCase):
    def test_429_subtypes_and_redaction(self):
        import io
        import urllib.error
        from unittest.mock import patch
        from integrations import OpenAIResponses
        from core import ToolFailure
        with patch.dict('os.environ', {'OPENAI_API_KEY':'synthetic-key'}):
            model = OpenAIResponses('fixture-model')
        for provider_code, expected in [('insufficient_quota','api_quota'),
            ('credit_balance_exhausted','api_quota'),('project_spend_limit_exceeded','api_quota'),
            ('rate_limit_exceeded','api_rate_limit'),('slow_down','api_rate_limit'),
            ('private-unknown-code','api_429')]:
            body = json.dumps({'error':{'code':provider_code,'message':'private-provider-detail'}}).encode()
            failure = urllib.error.HTTPError('https://api.openai.com/v1/responses',429,'redacted',{},io.BytesIO(body))
            with patch('integrations.urllib.request.urlopen',side_effect=failure):
                with self.assertRaises(ToolFailure) as error: model.complete('fixture',[],[])
            self.assertEqual(error.exception.code,expected)
            self.assertNotIn('private-',str(error.exception))
