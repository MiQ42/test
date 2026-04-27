"""Anthropic SDK adapter with prompt caching on the system prompt.

Each prompt stage is reused n × 9 × 2 = 180 times per model in the static study,
so caching the system prompt is essential — both for cost and for stabilising
the comparison condition (identical cached prefix bytes across calls).

Thinking is disabled across the board to reduce variance: this experiment
studies the effect of the *system prompt* on response shape, so introducing
adaptive thinking would add a confound.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import anthropic


MODELS = {
    "opus": "claude-opus-4-7",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
}


@dataclass
class Reply:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    stop_reason: str | None
    latency_s: float


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def call_static(
    *,
    model: str,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 4096,
    client: anthropic.Anthropic | None = None,
) -> Reply:
    """Single-turn call. System prompt is marked cacheable.

    Use the same `system_prompt` string across the n=10 repetitions for one
    (model, stage, language, question) cell so the prefix actually caches.
    """
    cli = client or _client()
    t0 = time.monotonic()
    resp = cli.messages.create(
        model=model,
        max_tokens=max_tokens,
        thinking={"type": "disabled"},
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )
    latency = time.monotonic() - t0
    text = "".join(b.text for b in resp.content if b.type == "text")
    return Reply(
        text=text,
        model=model,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
        cache_creation_tokens=resp.usage.cache_creation_input_tokens or 0,
        cache_read_tokens=resp.usage.cache_read_input_tokens or 0,
        stop_reason=resp.stop_reason,
        latency_s=latency,
    )


def call_with_history(
    *,
    model: str,
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 4096,
    client: anthropic.Anthropic | None = None,
) -> Reply:
    """Multi-turn call for the live study.

    The system prompt evolves across stages, so each new system prompt costs a
    cache write but caches for repeated calls within the same stage.
    """
    cli = client or _client()
    t0 = time.monotonic()
    resp = cli.messages.create(
        model=model,
        max_tokens=max_tokens,
        thinking={"type": "disabled"},
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
    )
    latency = time.monotonic() - t0
    text = "".join(b.text for b in resp.content if b.type == "text")
    return Reply(
        text=text,
        model=model,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
        cache_creation_tokens=resp.usage.cache_creation_input_tokens or 0,
        cache_read_tokens=resp.usage.cache_read_input_tokens or 0,
        stop_reason=resp.stop_reason,
        latency_s=latency,
    )
