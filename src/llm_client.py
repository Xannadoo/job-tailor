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


def complete_with_tools(prompt: str, tools: list[dict], system: str | None = None):
    """
    Send a prompt with tool definitions available, and return the raw
    response message (not just text) so the caller can inspect
    whether the model chose to call a tool.

    This is new and separate from complete() rather than a parameter
    added to it, because tool-calling changes the shape of what comes
    back - a caller might get a tool_call request instead of text, and
    treating that as a plain string would silently lose information.
    Existing pipeline stages that only ever want plain text keep using
    complete() unchanged.

    Confirmed working on Ollama cloud models via LiteLLM, but only
    when the model is registered with the ollama_chat/ provider
    prefix in litellm_config.yaml, not ollama/ - the older prefix
    routes to Ollama's /api/generate endpoint, which doesn't support
    tools, and LiteLLM silently drops the tools parameter rather than
    erroring (drop_params: true in litellm_settings). If tool calls
    aren't firing, check the prefix before assuming the model or
    backend doesn't support tool calling at all.

    Returns the full response message object (has .content and
    .tool_calls), not just a string - the caller needs both.
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
        tools=tools,
    )

    return response.choices[0].message


def run_agentic_loop(
    prompt: str,
    tools: list[dict],
    tool_executor,
    system: str | None = None,
    max_tool_rounds: int = 3,
) -> dict:
    """
    Completes the full tool-calling round trip that complete_with_tools()
    only starts: send the prompt with tools available, and if the model
    asks to call one, actually run it, send the result back, and let
    the model produce a final answer using that result. Repeats up to
    max_tool_rounds in case the model wants to call a tool more than
    once before answering (kept low - this project's tool use so far
    is one narrow verification call, not open-ended multi-step
    agentic work, so a runaway loop here would indicate something
    wrong rather than legitimate extra reasoning).

    tool_executor is a callable: (tool_name: str, arguments: dict) ->
    dict. It's the caller's job to know how to actually run whichever
    tools were passed in - this function only handles the conversation
    mechanics (sending results back in the right format), not the
    tools' actual logic.

    Returns a dict: {"final_content": str | None, "tool_calls_made":
    list of {"name", "arguments", "result"}, "hit_max_rounds": bool}.
    tool_calls_made is kept because seeing what the model actually
    chose to call, and with what arguments, is itself useful to
    inspect - not just the final answer.
    """
    import json

    client = get_client()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    tool_calls_made = []
    hit_max_rounds = False

    for round_num in range(max_tool_rounds):
        response = client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=messages,
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
            tools=tools,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            return {
                "final_content": message.content,
                "tool_calls_made": tool_calls_made,
                "hit_max_rounds": False,
            }

        # Model wants to call one or more tools. Append its request to
        # the conversation, then run each tool and append the result,
        # so the next call has the full history to reason from.
        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in message.tool_calls
                ],
            }
        )

        for call in message.tool_calls:
            arguments = json.loads(call.function.arguments)
            result = tool_executor(call.function.name, arguments)

            tool_calls_made.append(
                {"name": call.function.name, "arguments": arguments, "result": result}
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result),
                }
            )

        if round_num == max_tool_rounds - 1:
            hit_max_rounds = True

    return {
        "final_content": None,
        "tool_calls_made": tool_calls_made,
        "hit_max_rounds": hit_max_rounds,
    }