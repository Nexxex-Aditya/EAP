"""Tests for the LLM Adapter."""

import pytest
from pydantic import BaseModel
from eap.adapters.llm.interface import LLMAdapter
from eap.adapters.llm.litellm_adapter import LiteLLMAdapter


class DummyResponse(BaseModel):
    result: str


def test_litellm_adapter_implements_interface():
    """Verify that LiteLLMAdapter correctly implements the LLMAdapter ABC."""
    adapter = LiteLLMAdapter(model_name="gpt-4o")
    assert isinstance(adapter, LLMAdapter)
    assert adapter.model_name == "gpt-4o"
    assert adapter.client is not None

def test_litellm_adapter_can_change_model():
    """Verify that the adapter can be configured for different models (Claude, open source, etc)."""
    adapter_openai = LiteLLMAdapter(model_name="gpt-4o")
    assert adapter_openai.model_name == "gpt-4o"
    
    adapter_claude = LiteLLMAdapter(model_name="claude-3-5-sonnet-20240620")
    assert adapter_claude.model_name == "claude-3-5-sonnet-20240620"
    
    adapter_oss = LiteLLMAdapter(model_name="ollama/llama3")
    assert adapter_oss.model_name == "ollama/llama3"
