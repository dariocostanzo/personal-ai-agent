import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import agent_state, providers


class ProviderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(agent_state, "DB_PATH", Path(temp.name) / "state.db")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cloud_usage_is_recorded_with_explicit_cost_rates(self):
        environment = {
            "AGENT_PROVIDER": "ollama",
            "AGENT_PROVIDER_CHAT": "openai",
            "OPENAI_MODEL": "test-model",
            "OPENAI_INPUT_COST_PER_MILLION": "2",
            "OPENAI_OUTPUT_COST_PER_MILLION": "4",
        }
        with patch.dict(os.environ, environment, clear=True), patch.object(
            providers, "_call", return_value=("A response", 10, 4)
        ):
            answer = providers.complete(
                [{"role": "user", "content": "Hello"}], capability="chat"
            )
            status = providers.status()

        self.assertEqual(answer, "A response")
        self.assertEqual(status["provider"], "openai")
        self.assertEqual(status["locality"], "cloud")
        usage = agent_state.usage_summary()["cloud"]
        self.assertEqual(usage["input_tokens"], 10)
        self.assertEqual(usage["output_tokens"], 4)
        self.assertAlmostEqual(usage["estimated_cost"], 0.000036)

    def test_openai_request_uses_configured_api_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True), \
                patch.object(providers, "_request_json", return_value={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }) as request_json:
            providers._call("openai", "test-model", [{"role": "user", "content": "Hi"}])

        self.assertEqual(
            request_json.call_args.args[2]["Authorization"],
            "Bearer test-key",
        )


if __name__ == "__main__":
    unittest.main()
