"""Groq access. Every LLM call in the app goes through `text()` or `structured()`."""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any, List, Literal, Sequence, Type, TypeVar

import groq
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel

from app.config import get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Tier = Literal["main", "fast"]


class LLMConfigError(RuntimeError):
    """Missing or invalid configuration (e.g. no GROQ_API_KEY)."""


class LLMOutputError(RuntimeError):
    """The model kept returning output that does not match the schema."""


# Errors that mean "this structured-output mode did not work", not "Groq is down".
_FALLBACK_ON = (groq.BadRequestError, OutputParserException, ValueError)


def is_retryable(exc: Exception) -> bool:
    """Used by LangGraph RetryPolicy: transient Groq problems and bad model output."""
    return isinstance(
        exc,
        (
            groq.RateLimitError,
            groq.APIConnectionError,
            groq.InternalServerError,
            LLMOutputError,
        ),
    )


@lru_cache(maxsize=16)
def _build(model: str, max_tokens: int | None) -> ChatGroq:
    s = get_settings()
    if not s.groq_api_key:
        raise LLMConfigError(
            "GROQ_API_KEY is not set. Copy backend/.env.example to backend/.env and add your key."
        )
    extra: dict[str, Any] = {}
    if s.groq_reasoning_effort and "gpt-oss" in model:
        extra["reasoning_effort"] = s.groq_reasoning_effort
    return ChatGroq(
        model=model,
        api_key=s.groq_api_key,
        temperature=s.llm_temperature,
        max_retries=s.groq_max_retries,
        timeout=s.groq_timeout_s,
        max_tokens=max_tokens,
        **extra,
    )


def get_llm(tier: Tier = "main", max_tokens: int | None = None) -> ChatGroq:
    s = get_settings()
    model = s.groq_model if tier == "main" else s.groq_fast_model
    return _build(model, max_tokens)


def reset_llm_cache() -> None:
    _build.cache_clear()


def _to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            parts.append(p if isinstance(p, str) else p.get("text", "") if isinstance(p, dict) else "")
        return "".join(parts)
    return str(content)


def text(messages: Sequence[BaseMessage], *, tier: Tier = "main", max_tokens: int | None = None) -> str:
    return _to_text(get_llm(tier, max_tokens).invoke(list(messages)).content).strip()


def _extract_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    start, end = raw.find("{"), raw.rfind("}")
    return raw[start : end + 1] if start != -1 and end > start else raw


def _with_schema_instruction(messages: Sequence[BaseMessage], schema: Type[BaseModel]) -> List[BaseMessage]:
    instruction = (
        "Respond with ONE valid JSON object and nothing else: no markdown fences, no commentary. "
        "It must satisfy this JSON Schema:\n" + json.dumps(schema.model_json_schema())
    )
    msgs = list(messages)
    if msgs and isinstance(msgs[0], SystemMessage):
        msgs[0] = SystemMessage(content=f"{msgs[0].content}\n\n{instruction}")
    else:
        msgs.insert(0, SystemMessage(content=instruction))
    return msgs


def _json_mode(llm: ChatGroq, schema: Type[T], messages: Sequence[BaseMessage], first_error: Exception | None) -> T:
    bound = llm.bind(response_format={"type": "json_object"})
    msgs = _with_schema_instruction(messages, schema)
    last: Exception | None = first_error
    for _ in range(2):
        raw = _to_text(bound.invoke(msgs).content)
        try:
            return schema.model_validate_json(_extract_json(raw))
        except ValueError as exc:  # pydantic.ValidationError is a ValueError
            last = exc
            msgs = [
                *msgs,
                AIMessage(content=raw),
                HumanMessage(content=f"That JSON was invalid: {str(exc)[:500]}\nReturn the corrected JSON object only."),
            ]
    raise LLMOutputError(f"Model returned invalid structured output: {last}")


def structured(
    schema: Type[T],
    messages: Sequence[BaseMessage],
    *,
    tier: Tier = "fast",
    max_tokens: int | None = None,
) -> T:
    """Return a validated `schema` instance.

    Tries Groq's json_schema mode first, then falls back to json_object mode with the schema
    in the prompt plus one repair round. Rate limits and network errors are NOT swallowed here;
    they propagate so LangGraph's retry policy can back off.
    """
    s = get_settings()
    llm = get_llm(tier, max_tokens)
    first_error: Exception | None = None

    if s.structured_method == "json_schema":
        try:
            result = llm.with_structured_output(schema, method="json_schema").invoke(list(messages))
            if isinstance(result, schema):
                return result
            if isinstance(result, dict):
                return schema.model_validate(result)
            first_error = ValueError("json_schema mode returned no parsed result")
        except _FALLBACK_ON as exc:
            first_error = exc
        log.warning("json_schema mode failed (%s); falling back to json_mode", first_error)

    return _json_mode(llm, schema, messages, first_error)
