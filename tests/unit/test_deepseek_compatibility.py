"""Verify actual structured-output request serialization, with HTTP mocked."""
import json

import httpx
import pytest

from runtime.config.settings import Settings
from runtime.graph.nodes.supervisor import AgentTaskDecision
from runtime.llm.profiles import ModelProfile, build_model


@pytest.mark.asyncio
async def test_deepseek_structured_request_disables_incompatible_thinking_mode():
    captured = []

    def respond(request):
        payload = json.loads(request.content)
        captured.append(payload)
        return httpx.Response(200, json={
            "id": "mock-completion", "model": "deepseek-flash",
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": "", "tool_calls": [{
                    "id": "mock-tool", "type": "function", "function": {
                        "name": "AgentTaskDecision",
                        "arguments": json.dumps({"agent_task": "Inspect the target logs."}),
                    },
                }],
            }}],
        })

    settings = Settings(_env_file=None, openai_api_key="test-only",
        openai_base_url="https://api.deepseek.com", flash_model_name="deepseek-flash")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = build_model(ModelProfile.FAST_CLASSIFIER, settings, http_async_client=client)
        result = await model.with_structured_output(
            AgentTaskDecision, method="function_calling",
        ).ainvoke("Investigate example.com")
    assert result.agent_task == "Inspect the target logs."
    assert captured[0]["reasoning_effort"] == "none"
    assert captured[0]["tool_choice"]["function"]["name"] == "AgentTaskDecision"


def test_other_openai_compatible_endpoints_do_not_receive_deepseek_options():
    settings = Settings(_env_file=None, openai_api_key="test-only",
                        openai_base_url="https://model.example/v1")
    model = build_model(ModelProfile.FAST_CLASSIFIER, settings)
    assert model.reasoning_effort is None
