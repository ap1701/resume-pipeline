"""Thin wrapper around the Anthropic SDK shared by all agents."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Type, TypeVar

import anthropic
from pydantic import BaseModel

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-5-5"
# Server-side refusal fallback: if a safety classifier declines, the API re-runs
# the request on a suitable fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_PAUSE_CONTINUATIONS = 6


class AgentError(RuntimeError):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    calls: int = 0

    def add(self, u: Any) -> None:
        self.calls += 1
        self.input_tokens += getattr(u, "input_tokens", 0) or 0
        self.output_tokens += getattr(u, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(u, "cache_read_input_tokens", 0) or 0


@dataclass
class LLM:
    model: str = DEFAULT_MODEL
    client: Any = None
    use_fallbacks: bool = True
    usage: Usage = field(default_factory=Usage)

    def __post_init__(self) -> None:
        if self.client is None:
            # Resolves ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / `ant auth login` profile.
            self.client = anthropic.Anthropic(max_retries=4)

    # ------------------------------------------------------------------ helpers
    def _common(self, effort: str) -> dict:
        kw: dict = {
            "model": self.model,
            "output_config": {"effort": effort},
            # Auto-cache the stable prefix (system prompt + resume + JD); the
            # writer/recruiter loop re-sends it every round.
            "cache_control": {"type": "ephemeral"},
        }
        if self.use_fallbacks:
            kw["betas"] = [FALLBACK_BETA]
            kw["fallbacks"] = "default"
        return kw

    @staticmethod
    def _check_stop(msg: Any, agent: str) -> None:
        if msg.stop_reason == "refusal":
            details = getattr(msg, "stop_details", None)
            raise AgentError(f"{agent}: model declined ({getattr(details, 'category', None)}): "
                             f"{getattr(details, 'explanation', '')}")
        if msg.stop_reason == "max_tokens":
            raise AgentError(f"{agent}: output hit max_tokens; raise it in llm.py")

    # -------------------------------------------------------------- free text
    def run_with_tools(self, *, agent: str, system: str, user: str, tools: list,
                       effort: str = "high", max_tokens: int = 64000) -> str:
        """Run a turn that uses server-side tools (web search / fetch).

        Server tools execute on Anthropic's side; the only client work is
        resuming when the server loop pauses (`pause_turn`).
        """
        messages: list = [{"role": "user", "content": user}]
        for _ in range(MAX_PAUSE_CONTINUATIONS + 1):
            with self.client.beta.messages.stream(
                max_tokens=max_tokens, system=system, messages=messages, tools=tools,
                **self._common(effort),
            ) as stream:
                msg = stream.get_final_message()
            self.usage.add(msg.usage)
            log.debug("%s stop_reason=%s", agent, msg.stop_reason)
            if msg.stop_reason == "pause_turn":
                # Re-send with the paused assistant turn; the server resumes it.
                if messages[-1]["role"] == "assistant":
                    messages[-1] = {"role": "assistant", "content": msg.content}
                else:
                    messages.append({"role": "assistant", "content": msg.content})
                continue
            self._check_stop(msg, agent)
            return _join_text(msg.content)
        raise AgentError(f"{agent}: still paused after {MAX_PAUSE_CONTINUATIONS} continuations")

    # ------------------------------------------------------------- structured
    def structured(self, *, agent: str, system: str, user: str, schema: Type[T],
                   effort: str = "high", max_tokens: int = 48000) -> T:
        with self.client.beta.messages.stream(
            max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema, **self._common(effort),
        ) as stream:
            msg = stream.get_final_message()
        self.usage.add(msg.usage)
        self._check_stop(msg, agent)
        parsed: Optional[T] = getattr(msg, "parsed_output", None)
        if parsed is None:
            for block in msg.content:
                if getattr(block, "type", None) == "text" and getattr(block, "parsed_output", None) is not None:
                    parsed = block.parsed_output
                    break
        if parsed is None:  # last resort: validate the text ourselves
            parsed = schema.model_validate_json(_join_text(msg.content))
        return parsed


def _join_text(content: list) -> str:
    return "".join(b.text for b in content if getattr(b, "type", None) == "text").strip()
