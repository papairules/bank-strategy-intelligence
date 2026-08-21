import asyncio
from functools import wraps
from types import SimpleNamespace

import pytest

from backend.app.application.agents.strategy_agent import (
    StrategyAgentError,
    StrategyAgentFailureCode,
    StrategyAgentRequest,
    StrategyProviderOutput,
    StrategyProviderRequest,
    StrategyProviderStage,
    StrategyToolSpec,
)
from backend.app.infrastructure.llm.vertex.strategy_agent import VertexGeminiStrategyAgentProvider


def async_test(function):
    @wraps(function)
    def wrapper():
        return asyncio.run(function())
    return wrapper


class Client:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.aio = SimpleNamespace(models=self)
    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def request(stage):
    return StrategyProviderRequest(
        stage=stage, system_policy="policy",
        request=StrategyAgentRequest(organization="Bank", question="Question?"),
        allowed_tools=[StrategyToolSpec(name="strategy.get_context", description="context", input_schema={"type": "object"})] if stage == StrategyProviderStage.PLAN else [],
    )


@async_test
async def test_planning_uses_sdk_parameters_and_afc_disabled():
    response = SimpleNamespace(function_calls=[SimpleNamespace(name="strategy_get_context", id="1", args={})], candidates=[])
    client = Client(response)
    provider = VertexGeminiStrategyAgentProvider(project="p", location="global", model="m", client_factory=lambda **_: client)
    result = await provider.respond(request(StrategyProviderStage.PLAN))
    declaration = client.calls[0]["config"]["tools"][0]["function_declarations"][0]
    assert "parameters" in declaration and "parameters_json_schema" not in declaration
    assert client.calls[0]["config"]["automatic_function_calling"]["disable"] is True
    assert result.tool_calls[0].name == "strategy.get_context"


@async_test
async def test_answer_uses_parsed_first():
    parsed = StrategyProviderOutput(executive_summary="Observed evidence is limited.", findings=[], limitations=[])
    class Response:
        candidates = []
        @property
        def text(self): raise AssertionError("text accessed")
    response = Response()
    response.parsed = parsed
    client = Client(response)
    provider = VertexGeminiStrategyAgentProvider(project="p", location="global", model="m", client_factory=lambda **_: client)
    result = await provider.respond(request(StrategyProviderStage.ANSWER))
    assert result.output == parsed


@async_test
async def test_answer_valid_json_fallback():
    response = SimpleNamespace(parsed=None, text='{"executive_summary":"Limited evidence.","findings":[],"limitations":[]}', candidates=[])
    provider = VertexGeminiStrategyAgentProvider(project="p", location="global", model="m", client_factory=lambda **_: Client(response))
    assert (await provider.respond(request(StrategyProviderStage.ANSWER))).output.executive_summary == "Limited evidence."


@async_test
async def test_malformed_and_max_tokens_are_typed():
    reason = SimpleNamespace(value="MAX_TOKENS")
    response = SimpleNamespace(parsed=None, text="{", candidates=[SimpleNamespace(finish_reason=reason)])
    provider = VertexGeminiStrategyAgentProvider(project="p", location="global", model="m", client_factory=lambda **_: Client(response))
    with pytest.raises(StrategyAgentError) as caught:
        await provider.respond(request(StrategyProviderStage.ANSWER))
    assert caught.value.code == StrategyAgentFailureCode.MALFORMED_PROVIDER_OUTPUT


def test_provider_is_lazy():
    called = False
    def factory(**kwargs):
        nonlocal called
        called = True
    VertexGeminiStrategyAgentProvider(project="p", location="global", model="m", client_factory=factory)
    assert called is False


def test_vertex_wire_schema_inlines_pydantic_definitions():
    schema = {"type": "object", "properties": {"level": {"$ref": "#/$defs/Level"}}, "$defs": {"Level": {"type": "string", "enum": ["senior"]}}}
    wire = VertexGeminiStrategyAgentProvider._vertex_schema(schema)
    assert wire == {"type": "object", "properties": {"level": {"type": "string", "enum": ["senior"]}}}
