"""Tests for the Model Gateway per V1 review §18.1."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import BaseModel

from eap.adapters.llm.interface import (
    LLMAdapter,
    ModelCapability,
    ModelGateway,
    ModelInfo,
)


class FakeAdapter(LLMAdapter):
    """Minimal fake adapter for testing gateway routing."""

    def __init__(self, name: str = "fake"):
        self.name = name

    async def structured_resolve(self, prompt, context, response_model):
        return response_model()

    async def classify(self, text, categories, context=""):
        return categories[0], 0.95

    async def plan(self, request_text, available_capabilities):
        return {"plan": "fake"}

    async def repair_proposal(self, error_description, context):
        return {"repair_action": "retry"}

    async def summarize(self, text, max_length=500):
        return "summary"

    async def extract_parameters(self, natural_language, parameter_schema):
        return {}


class TestModelGateway:
    """Test capability-based routing."""

    def setup_method(self):
        self.gateway = ModelGateway()

    def test_register_and_list(self):
        adapter = FakeAdapter("gpt4")
        info = ModelInfo(
            model_name="gpt-4o",
            provider="openai",
            capabilities=[ModelCapability.REASONING, ModelCapability.STRUCTURED_EXTRACTION],
        )
        self.gateway.register_model(info, adapter)
        models = self.gateway.list_models()
        assert len(models) == 1
        assert models[0].model_name == "gpt-4o"

    def test_route_by_capability(self):
        adapter_gpt = FakeAdapter("gpt4")
        adapter_claude = FakeAdapter("claude")

        self.gateway.register_model(
            ModelInfo(
                model_name="gpt-4o",
                provider="openai",
                capabilities=[ModelCapability.REASONING],
                priority=1,
            ),
            adapter_gpt,
        )
        self.gateway.register_model(
            ModelInfo(
                model_name="claude-3-5-sonnet",
                provider="anthropic",
                capabilities=[ModelCapability.REASONING, ModelCapability.VISION],
                priority=0,
            ),
            adapter_claude,
        )

        # Claude has lower priority, so it should be preferred for REASONING
        result = self.gateway.get_adapter_for_capability(ModelCapability.REASONING)
        assert result is adapter_claude

    def test_route_with_provider_preference(self):
        adapter_gpt = FakeAdapter("gpt4")
        adapter_claude = FakeAdapter("claude")

        self.gateway.register_model(
            ModelInfo(
                model_name="gpt-4o",
                provider="openai",
                capabilities=[ModelCapability.REASONING],
                priority=0,
            ),
            adapter_gpt,
        )
        self.gateway.register_model(
            ModelInfo(
                model_name="claude-3-5-sonnet",
                provider="anthropic",
                capabilities=[ModelCapability.REASONING],
                priority=0,
            ),
            adapter_claude,
        )

        # Explicitly prefer anthropic
        result = self.gateway.get_adapter_for_capability(
            ModelCapability.REASONING, prefer_provider="anthropic"
        )
        assert result is adapter_claude

    def test_no_model_for_capability_returns_none(self):
        result = self.gateway.get_adapter_for_capability(ModelCapability.VISION)
        assert result is None

    def test_get_adapter_by_name(self):
        adapter = FakeAdapter("test")
        self.gateway.register_model(
            ModelInfo(model_name="test-model", capabilities=[]),
            adapter,
        )
        assert self.gateway.get_adapter_by_name("test-model") is adapter
        assert self.gateway.get_adapter_by_name("nonexistent") is None

    def test_list_capabilities(self):
        self.gateway.register_model(
            ModelInfo(
                model_name="gpt-4o",
                capabilities=[ModelCapability.REASONING, ModelCapability.PLANNING],
            ),
            FakeAdapter(),
        )
        caps = self.gateway.list_capabilities()
        assert "reasoning" in caps
        assert "planning" in caps
        assert "gpt-4o" in caps["reasoning"]

    def test_unhealthy_model_excluded_from_routing(self):
        adapter = FakeAdapter()
        self.gateway.register_model(
            ModelInfo(
                model_name="broken-model",
                capabilities=[ModelCapability.REASONING],
                healthy=False,
            ),
            adapter,
        )
        result = self.gateway.get_adapter_for_capability(ModelCapability.REASONING)
        assert result is None  # unhealthy model should be excluded


class TestModelCapability:
    """Test that all required capabilities exist per V1 review §18.1."""

    def test_all_capabilities_exist(self):
        assert ModelCapability.STRUCTURED_EXTRACTION
        assert ModelCapability.CLASSIFICATION
        assert ModelCapability.REASONING
        assert ModelCapability.VISION
        assert ModelCapability.EMBEDDING
        assert ModelCapability.SUMMARIZATION
        assert ModelCapability.PLANNING
        assert ModelCapability.CODE_GENERATION
