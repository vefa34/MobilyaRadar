"""Provider-agnostic LLM adapter with structured (JSON-schema) outputs, validation, model
fallback and token/cost accounting.

The LLM is only ever used to *propose* things (extra search terms, a classification hint, product
attributes from a catalogue). It is never a source of companies: nothing returned by the LLM is
written to ``companies`` — company records require a connector record with a traceable source URL.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.config import get_settings

log = logging.getLogger("llm")

# USD per 1M tokens (input, output). Keep in sync with provider price lists.
PRICING = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


@dataclass
class LLMUsage:
    model: str
    input_tokens: int
    output_tokens: int

    @property
    def cost_usd(self) -> float:
        pin, pout = PRICING.get(self.model, (5.0, 25.0))
        return (self.input_tokens * pin + self.output_tokens * pout) / 1_000_000


class LLMUnavailable(Exception):
    pass


class LLMProvider(Protocol):
    async def complete_json(self, model: str, system: str, prompt: str, schema: dict) -> tuple[dict, LLMUsage]: ...


class AnthropicProvider:
    def __init__(self, api_key: str | None, effort: str = "low"):
        import anthropic
        self._anthropic = anthropic
        self.client = anthropic.AsyncAnthropic(api_key=api_key) if api_key else anthropic.AsyncAnthropic()
        self.effort = effort

    async def complete_json(self, model: str, system: str, prompt: str, schema: dict) -> tuple[dict, LLMUsage]:
        resp = await self.client.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.stop_reason == "refusal":
            raise LLMUnavailable(f"model declined: {getattr(resp.stop_details, 'category', None)}")
        if resp.stop_reason == "max_tokens":
            raise LLMUnavailable("output truncated (max_tokens)")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        usage = LLMUsage(model, resp.usage.input_tokens, resp.usage.output_tokens)
        return json.loads(text), usage


class OpenAICompatibleProvider:
    """Any OpenAI-compatible chat-completions endpoint (raw HTTP; no SDK dependency)."""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        import httpx
        self.client = httpx.AsyncClient(base_url=base_url, timeout=60, headers={"Authorization": f"Bearer {api_key}"})

    async def complete_json(self, model: str, system: str, prompt: str, schema: dict) -> tuple[dict, LLMUsage]:
        r = await self.client.post("/chat/completions", json={
            "model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "result", "schema": schema, "strict": True}},
        })
        r.raise_for_status()
        data = r.json()
        u = data.get("usage") or {}
        return json.loads(data["choices"][0]["message"]["content"]), LLMUsage(model, u.get("prompt_tokens", 0), u.get("completion_tokens", 0))


class LLMClient:
    def __init__(self, provider: LLMProvider | None = None, model: str | None = None, fallback_model: str | None = None):
        s = get_settings()
        self.model = model or s.llm_model
        self.fallback_model = fallback_model if fallback_model is not None else s.llm_fallback_model
        self.provider = provider
        if self.provider is None:
            if s.llm_provider == "anthropic":
                self.provider = AnthropicProvider(s.anthropic_api_key, s.llm_effort)
            elif s.llm_provider == "openai" and s.openai_api_key:
                self.provider = OpenAICompatibleProvider(s.openai_api_key)
        self.usage: list[LLMUsage] = []

    @property
    def enabled(self) -> bool:
        return self.provider is not None

    @property
    def total_cost_usd(self) -> float:
        return sum(u.cost_usd for u in self.usage)

    async def structured(self, system: str, prompt: str, output_model: type[BaseModel]) -> BaseModel:
        """Call the model, validate against ``output_model``; on failure retry once on the fallback model."""
        if not self.provider:
            raise LLMUnavailable("no LLM provider configured")
        schema = _strict_schema(output_model.model_json_schema())
        last: Exception | None = None
        for model in [m for m in (self.model, self.fallback_model) if m]:
            try:
                data, usage = await self.provider.complete_json(model, system, prompt, schema)
                self.usage.append(usage)
                return output_model.model_validate(data)
            except (ValidationError, json.JSONDecodeError, LLMUnavailable) as exc:
                last = exc
                log.warning("LLM output invalid on %s: %s", model, exc)
            except Exception as exc:  # noqa: BLE001 - provider/network errors → try fallback
                last = exc
                log.warning("LLM call failed on %s: %s", model, exc)
        raise LLMUnavailable(str(last))


def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Structured-output schemas require additionalProperties=false on objects; inline $defs."""
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node.pop("$ref").split("/")[-1]
                node.update(walk(json.loads(json.dumps(defs[ref]))))
            if node.get("type") == "object":
                node.setdefault("additionalProperties", False)
                node["required"] = list((node.get("properties") or {}).keys())
            node.pop("title", None)
            node.pop("default", None)
            for v in list(node.values()):
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        return node

    return walk(schema)
