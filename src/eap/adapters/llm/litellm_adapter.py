"""LiteLLM adapter for model-agnostic LLM interactions."""

from __future__ import annotations

import json
from typing import Any

import instructor
from litellm import acompletion
from pydantic import BaseModel

from eap.adapters.llm.interface import LLMAdapter
from eap.core.config import get_logger

logger = get_logger("adapters.llm.litellm")


class ClassificationResult(BaseModel):
    category: str
    confidence: float


class LiteLLMAdapter(LLMAdapter):
    """LLM Adapter powered by LiteLLM and Instructor.

    Supports OpenAI, Anthropic, Google, OSS models, etc. by simply changing the model string.
    """

    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name
        # Initialize instructor with LiteLLM's async completion
        self.client = instructor.from_litellm(acompletion)

    async def structured_resolve(
        self,
        prompt: str,
        context: dict[str, Any],
        response_model: type[BaseModel],
    ) -> BaseModel:
        """Resolve a prompt into a structured Pydantic model."""
        system_prompt = "You are a semantic resolution assistant. Use the provided context to resolve the user request."

        context_str = json.dumps(context, indent=2)
        full_prompt = f"Context:\n{context_str}\n\nRequest:\n{prompt}"

        response = await self.client.chat.completions.create(
            model=self.model_name,
            response_model=response_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt},
            ],
        )
        return response

    async def classify(
        self,
        text: str,
        categories: list[str],
        context: str = "",
    ) -> tuple[str, float]:
        """Classify text into one of the given categories."""
        system_prompt = (
            f"Classify the following text into one of these categories: {', '.join(categories)}.\n"
            f"Return the category and your confidence score (0.0 to 1.0).\n"
            f"Additional context: {context}"
        )

        response = await self.client.chat.completions.create(
            model=self.model_name,
            response_model=ClassificationResult,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        )
        return response.category, response.confidence

    async def plan(
        self,
        request_text: str,
        available_capabilities: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate an execution plan from a natural-language request."""
        system_prompt = (
            "You are an AI planner. Create a JSON execution plan for the request based on the available capabilities.\n"
            "Respond ONLY with valid JSON."
        )

        caps_str = json.dumps(available_capabilities, indent=2)
        full_prompt = f"Capabilities:\n{caps_str}\n\nRequest:\n{request_text}"

        response = await acompletion(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt},
            ],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        try:
            return json.loads(content or "{}")
        except Exception as e:
            logger.error("plan_parsing_failed", error=str(e))
            return {}

    async def repair_proposal(
        self,
        error_description: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Propose a bounded repair for a detected error."""
        system_prompt = (
            "Propose a repair for the described error given the context.\n"
            "Return a JSON object with 'repair_action', 'description', and 'reversible' (boolean)."
        )

        ctx_str = json.dumps(context, indent=2)
        full_prompt = f"Context:\n{ctx_str}\n\nError:\n{error_description}"

        response = await acompletion(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt},
            ],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        try:
            return json.loads(content or "{}")
        except Exception as e:
            logger.error("repair_parsing_failed", error=str(e))
            return {}

    async def summarize(self, text: str, max_length: int = 500) -> str:
        """Summarize text to the given max length."""
        system_prompt = f"Summarize the following text in under {max_length} characters."

        response = await acompletion(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        )
        return response.choices[0].message.content or ""

    async def extract_parameters(
        self,
        natural_language: str,
        parameter_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract structured parameters from natural-language input."""
        system_prompt = (
            "Extract parameters from the text according to the provided JSON schema.\n"
            "Return ONLY a JSON object matching the schema."
        )

        schema_str = json.dumps(parameter_schema, indent=2)
        full_prompt = f"Schema:\n{schema_str}\n\nText:\n{natural_language}"

        response = await acompletion(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt},
            ],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        try:
            return json.loads(content or "{}")
        except Exception as e:
            logger.error("extract_parsing_failed", error=str(e))
            return {}
