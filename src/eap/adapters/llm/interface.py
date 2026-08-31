"""Abstract LLM adapter interface and Model Gateway.

Per architecture.md §11, domain code must never import an LLM vendor SDK.
All LLM interactions go through this adapter. Changing the model must not
change business logic.

Per V1 review §18.1, the planner asks for a CAPABILITY, not a model name.
The gateway routes to the best available model for that capability.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from eap.core.config import get_logger

logger = get_logger("adapters.llm")


# ---------------------------------------------------------------------------
# Model Capabilities (V1 review §18.1)
# ---------------------------------------------------------------------------

class ModelCapability(str, Enum):
    """Capabilities a model can declare."""
    STRUCTURED_EXTRACTION = "structured_extraction"
    CLASSIFICATION = "classification"
    REASONING = "reasoning"
    VISION = "vision"
    EMBEDDING = "embedding"
    SUMMARIZATION = "summarization"
    PLANNING = "planning"
    CODE_GENERATION = "code_generation"


class ModelInfo(BaseModel):
    """Registration info for a model provider."""
    model_name: str
    provider: str = ""  # openai, anthropic, google, ollama, etc.
    capabilities: list[ModelCapability] = Field(default_factory=list)
    cost_per_1k_input_tokens: float = 0.0
    cost_per_1k_output_tokens: float = 0.0
    max_context_tokens: int = 128000
    supports_json_mode: bool = True
    supports_vision: bool = False
    healthy: bool = True
    priority: int = 0  # lower = preferred


class ModelHealthCheck(BaseModel):
    """Result of a model health check."""
    model_name: str
    healthy: bool
    latency_ms: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# Abstract LLM Adapter
# ---------------------------------------------------------------------------

class LLMAdapter(ABC):
    """Abstract interface for LLM operations."""

    @abstractmethod
    async def structured_resolve(
        self,
        prompt: str,
        context: dict[str, Any],
        response_model: type[BaseModel],
    ) -> BaseModel:
        """Resolve a prompt into a structured Pydantic model.

        Used for semantic resolution of business terms.
        """

    @abstractmethod
    async def classify(
        self,
        text: str,
        categories: list[str],
        context: str = "",
    ) -> tuple[str, float]:
        """Classify text into one of the given categories.

        Returns (category, confidence).
        """

    @abstractmethod
    async def plan(
        self,
        request_text: str,
        available_capabilities: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate an execution plan from a natural-language request.

        Returns structured plan dict.
        """

    @abstractmethod
    async def repair_proposal(
        self,
        error_description: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Propose a bounded repair for a detected error.

        Returns a repair action dict.
        """

    @abstractmethod
    async def summarize(self, text: str, max_length: int = 500) -> str:
        """Summarize text to the given max length."""

    @abstractmethod
    async def extract_parameters(
        self,
        natural_language: str,
        parameter_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract structured parameters from natural-language input."""


# ---------------------------------------------------------------------------
# Model Gateway (V1 review §18.1)
# ---------------------------------------------------------------------------

class ModelGateway:
    """Provider-neutral model gateway.

    Per V1 review §18.1:
    - The planner asks for a CAPABILITY (e.g., "structured_extraction").
    - The gateway routes to the best available model for that capability.
    - Adding a new model does NOT require rewriting agents.

    Conceptually:
        Model Gateway
        ├── OpenAI
        ├── Anthropic
        ├── Gemini
        ├── Azure/OpenAI-compatible providers
        ├── local models (Ollama)
        └── future providers
    """

    def __init__(self) -> None:
        self._models: dict[str, ModelInfo] = {}
        self._adapters: dict[str, LLMAdapter] = {}

    def register_model(
        self,
        model_info: ModelInfo,
        adapter: LLMAdapter,
    ) -> None:
        """Register a model with its adapter and declared capabilities."""
        self._models[model_info.model_name] = model_info
        self._adapters[model_info.model_name] = adapter
        logger.info(
            "model_registered",
            model=model_info.model_name,
            provider=model_info.provider,
            capabilities=[c.value for c in model_info.capabilities],
        )

    def get_adapter_for_capability(
        self,
        capability: ModelCapability,
        *,
        prefer_provider: str = "",
    ) -> LLMAdapter | None:
        """Route to the best model for a given capability.

        Selection priority:
        1. Models that declare this capability
        2. Among those, prefer the requested provider
        3. Among those, prefer lower priority number
        4. Among those, prefer healthy models
        """
        candidates = [
            (name, info) for name, info in self._models.items()
            if capability in info.capabilities and info.healthy
        ]

        if not candidates:
            logger.warning("no_model_for_capability", capability=capability.value)
            return None

        # Sort by preference
        def _sort_key(item: tuple[str, ModelInfo]) -> tuple[int, int, float]:
            name, info = item
            provider_match = 0 if prefer_provider and info.provider == prefer_provider else 1
            return (provider_match, info.priority, info.cost_per_1k_input_tokens)

        candidates.sort(key=_sort_key)
        best_name = candidates[0][0]

        logger.info(
            "model_routed",
            capability=capability.value,
            selected=best_name,
            candidates_count=len(candidates),
        )
        return self._adapters[best_name]

    def get_adapter_by_name(self, model_name: str) -> LLMAdapter | None:
        """Get a specific model adapter by name."""
        return self._adapters.get(model_name)

    def list_models(self) -> list[ModelInfo]:
        """List all registered models."""
        return list(self._models.values())

    def list_capabilities(self) -> dict[str, list[str]]:
        """List available capabilities and which models support them."""
        result: dict[str, list[str]] = {}
        for cap in ModelCapability:
            models = [
                name for name, info in self._models.items()
                if cap in info.capabilities and info.healthy
            ]
            if models:
                result[cap.value] = models
        return result

    async def health_check(self, model_name: str) -> ModelHealthCheck:
        """Run a health check on a specific model."""
        adapter = self._adapters.get(model_name)
        if not adapter:
            return ModelHealthCheck(
                model_name=model_name,
                healthy=False,
                error="Model not registered",
            )

        try:
            import time
            start = time.monotonic()
            await adapter.summarize("health check", max_length=10)
            elapsed = (time.monotonic() - start) * 1000

            info = self._models[model_name]
            info.healthy = True

            return ModelHealthCheck(
                model_name=model_name,
                healthy=True,
                latency_ms=elapsed,
            )
        except Exception as e:
            info = self._models.get(model_name)
            if info:
                info.healthy = False

            return ModelHealthCheck(
                model_name=model_name,
                healthy=False,
                error=str(e),
            )

    async def health_check_all(self) -> list[ModelHealthCheck]:
        """Run health checks on all registered models."""
        results = []
        for name in self._models:
            result = await self.health_check(name)
            results.append(result)
        return results
