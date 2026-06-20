"""
Thin wrapper around calls to a local LiteLLM proxy.

LiteLLM exposes an OpenAI-compatible /chat/completions endpoint, so we
use the `openai` Python package as the client even though there's no
OpenAI account or key involved - it's just talking to localhost.
"""

from openai import OpenAI

import config


def get_client() -> OpenAI:
    """Return a client configured to point at the local LiteLLM proxy."""
    return OpenAI(
        base_url=f"{config.LITELLM_BASE_URL}/v1",
        api_key=config.API_KEY,
    )


def complete(prompt: str, system: str | None = None) -> str:
    """
    Send a single prompt to the configured model and return the text
    response. Deliberately simple, single-turn - no conversation
    history, no streaming. Each pipeline stage calls this once with
    everything it needs already in the prompt.

    Raises whatever the underlying client raises on connection or API
    errors. Callers should catch and report failures clearly rather
    than letting a stack trace from the HTTP layer surface directly,
    since the most common failure mode here is "the proxy isn't
    running" or "the model name doesn't match what's registered."
    """
    client = get_client()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=config.MODEL_NAME,
        messages=messages,
        temperature=config.TEMPERATURE,
        max_tokens=config.MAX_TOKENS,
    )

    return response.choices[0].message.content
