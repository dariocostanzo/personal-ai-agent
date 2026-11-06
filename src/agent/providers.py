"""Optional text-model providers; Ollama stays the default and cloud is explicit."""

import json
import os
import urllib.error
import urllib.request

from src.agent import agent_state
from src.agent.config import OLLAMA_BASE_URL, OLLAMA_MODEL


def _setting(name, default=""):
    return os.getenv(name, default).strip()


def _estimated_tokens(text):
    return max(1, len(text) // 4) if text else 0


def _default_model(provider):
    if provider == "openai":
        return _setting("OPENAI_MODEL", "gpt-4o-mini")
    if provider == "anthropic":
        return _setting("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
    return OLLAMA_MODEL


def _request_json(url, payload, headers=None, timeout=180):
    request_headers = {"Content-Type": "application/json"}
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers=request_headers, method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _call(provider, model, messages):
    if provider == "ollama":
        result = _request_json(
            f"{OLLAMA_BASE_URL}/api/chat",
            {"model": model or OLLAMA_MODEL, "messages": messages,
             "stream": False, "think": False},
        )
        answer = result["message"]["content"]
        return answer, result.get("prompt_eval_count"), result.get("eval_count")
    if provider == "openai":
        key = _setting("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required for the OpenAI provider.")
        result = _request_json(
            _setting("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            + "/chat/completions",
            {"model": model or _setting("OPENAI_MODEL", "gpt-4o-mini"),
             "messages": messages},
            {"Authorization": "Bearer " + key},
        )
        usage = result.get("usage", {})
        return result["choices"][0]["message"]["content"], usage.get("prompt_tokens"), usage.get("completion_tokens")
    if provider == "anthropic":
        key = _setting("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for the Claude provider.")
        system = "\n\n".join(
            message["content"] for message in messages if message["role"] == "system"
        )
        conversation = [message for message in messages if message["role"] != "system"]
        result = _request_json(
            _setting("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")
            + "/messages",
            {"model": model or _setting("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
             "max_tokens": int(_setting("ANTHROPIC_MAX_TOKENS", "2048")),
             "system": system, "messages": conversation},
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
        )
        answer = "".join(
            block.get("text", "") for block in result.get("content", [])
            if block.get("type") == "text"
        )
        usage = result.get("usage", {})
        return answer, usage.get("input_tokens"), usage.get("output_tokens")
    raise ValueError(f"Unknown model provider: {provider}")


def complete(messages, capability="chat"):
    """Run the selected provider and record privacy-aware usage metadata."""
    provider = _setting(f"AGENT_PROVIDER_{capability.upper()}",
                        _setting("AGENT_PROVIDER", "ollama")).lower()
    model = _setting(f"AGENT_MODEL_{capability.upper()}")
    fallback = _setting("AGENT_FALLBACK_PROVIDER").lower()
    content = "\n".join(message.get("content", "") for message in messages)
    locality = "local" if provider == "ollama" else "cloud"
    privacy = ("Prompt and context stayed on this device."
               if locality == "local" else
               "Prompt and context were sent to the configured cloud provider.")
    try:
        answer, input_tokens, output_tokens = _call(provider, model, messages)
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError, RuntimeError) as error:
        if not fallback or fallback == provider:
            raise RuntimeError(f"{provider} provider failed: {error}") from error
        fallback_model = _setting(f"AGENT_MODEL_{capability.upper()}_FALLBACK")
        try:
            answer, input_tokens, output_tokens = _call(fallback, fallback_model, messages)
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError, RuntimeError) as fallback_error:
            raise RuntimeError(
                f"{provider} provider failed ({error}); configured fallback {fallback} "
                f"also failed: {fallback_error}"
            ) from fallback_error
        provider, model = fallback, fallback_model or _default_model(fallback)
        locality = "local" if provider == "ollama" else "cloud"
        privacy = ("Fallback kept prompt and context on this device."
                   if locality == "local" else
                   "Fallback sent prompt and context to the configured cloud provider.")

    input_tokens = input_tokens or _estimated_tokens(content)
    output_tokens = output_tokens or _estimated_tokens(answer)
    cost = 0.0
    if locality == "cloud":
        prefix = "OPENAI" if provider == "openai" else "ANTHROPIC"
        input_rate = float(_setting(f"{prefix}_INPUT_COST_PER_MILLION", "0") or 0)
        output_rate = float(_setting(f"{prefix}_OUTPUT_COST_PER_MILLION", "0") or 0)
        cost = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
    agent_state.record_usage(
        capability, provider, model or _default_model(provider), locality,
        input_tokens, output_tokens, cost, privacy,
    )
    agent_state.add_decision(
        "model_call", capability, f"Used {provider} ({locality}) for {capability}.",
        {"model": model or _default_model(provider), "input_tokens": input_tokens,
         "output_tokens": output_tokens, "estimated_cost": cost},
    )
    return answer


def status():
    provider = _setting(
        "AGENT_PROVIDER_CHAT", _setting("AGENT_PROVIDER", "ollama")
    ).lower()
    configured_providers = {
        _setting(f"AGENT_PROVIDER_{capability}", _setting("AGENT_PROVIDER", "ollama")).lower()
        for capability in ("CHAT", "NEWS", "EMAIL", "GUARDIAN", "SELF_IMPROVEMENT")
    }
    configured_providers.discard("")
    return {
        "provider": provider,
        "locality": "local" if provider == "ollama" else "cloud",
        "cloud_enabled": any(item != "ollama" for item in configured_providers)
        or _setting("AGENT_FALLBACK_PROVIDER").lower() in ("openai", "anthropic"),
        "cost_rates_configured": (
            bool(_setting("OPENAI_INPUT_COST_PER_MILLION"))
            and bool(_setting("OPENAI_OUTPUT_COST_PER_MILLION"))
            if provider == "openai" else
            bool(_setting("ANTHROPIC_INPUT_COST_PER_MILLION"))
            and bool(_setting("ANTHROPIC_OUTPUT_COST_PER_MILLION"))
            if provider == "anthropic" else False
        ),
    }
