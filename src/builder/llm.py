"""OpenRouter wrapper. OpenAI-compatible client with cost tracking + fallback."""

from __future__ import annotations

import base64
import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import RateLimitError, APITimeoutError, APIConnectionError

from .config import CONFIG


# --- Pricing (USD per 1M tokens) for OpenRouter-listed models ---------------
# Update these from https://openrouter.ai/models if needed.
MODEL_PRICES_USD_PER_M = {
    "anthropic/claude-3.5-haiku":   (0.80, 4.00),
    "anthropic/claude-3.5-sonnet":  (3.00, 15.00),
    "anthropic/claude-3.7-sonnet":  (3.00, 15.00),
    "openai/gpt-4o-mini":           (0.15, 0.60),
    "openai/gpt-4o":                (2.50, 10.00),
    "google/gemini-2.5-flash":      (0.075, 0.30),
    "google/gemini-2.5-flash-image-preview": (0.075, 0.30),
}


def encode_image_data_url(path: Path) -> str:
    """Encode a local image as a base64 data URL for OpenAI-compatible vision APIs."""
    suffix = path.suffix.lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "gif": "image/gif"}.get(suffix, "image/png")
    b64 = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _price_for(model: str) -> tuple[float, float]:
    """Return (input_per_M, output_per_M). Defaults to Claude Haiku if unknown."""
    return MODEL_PRICES_USD_PER_M.get(model, (0.80, 4.00))


@dataclass
class LLMUsage:
    """Tracks tokens + cost across a session. Thread-safe.

    Multiple workers in the asyncio batch share one LLMUsage instance, so
    `add()` and `snapshot()` must be atomic. The GIL alone isn't enough:
    we update 4+ fields per call, and `model_breakdown[k] = dict.get(k,0)+1`
    is a read-modify-write that races without a lock.
    """
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    model_breakdown: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, model: str, input_tok: int, output_tok: int):
        in_p, out_p = _price_for(model)
        cost = (input_tok / 1_000_000) * in_p + (output_tok / 1_000_000) * out_p
        with self._lock:
            self.input_tokens += input_tok
            self.output_tokens += output_tok
            self.cost_usd += cost
            self.calls += 1
            self.model_breakdown[model] = self.model_breakdown.get(model, 0) + 1

    def cost_snapshot(self) -> float:
        """Read cost atomically. Use this for budget checks."""
        with self._lock:
            return self.cost_usd


class LLM:
    """Wraps OpenRouter via the OpenAI SDK. Tracks cost per call."""

    def __init__(self, model: Optional[str] = None, fallback: Optional[str] = None,
                 request_timeout: float = 60.0):
        if not CONFIG.openrouter_api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY missing. Copy .env.example to .env and fill it in."
            )
        # Hard timeout so a hung request doesn't lock a worker for 10 min (default).
        # tenacity retries on top, so we keep max_retries=0 inside the SDK.
        base_url = "https://openrouter.ai/api/v1"
        if CONFIG.openrouter_api_key.startswith("sk-proj-"):
            base_url = "https://api.openai.com/v1"

        self.client = OpenAI(
            api_key=CONFIG.openrouter_api_key,
            base_url=base_url,
            timeout=httpx.Timeout(request_timeout, connect=10.0),
            max_retries=0,
        )
        self.model = model or CONFIG.model_content
        self.fallback = fallback or CONFIG.model_content_fallback
        self.usage = LLMUsage()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError)),
        reraise=True,
    )
    def _call(self, model: str, system: str, user: str, json_mode: bool = True,
              max_tokens: int = 4096, temperature: float = 0.7) -> str:
        kwargs: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        t0 = time.time()
        resp = self.client.chat.completions.create(**kwargs)
        if resp.usage:
            self.usage.add(model, resp.usage.prompt_tokens, resp.usage.completion_tokens)
        return resp.choices[0].message.content or ""

    def complete_json(self, system: str, user: str, max_tokens: int = 4096,
                      temperature: float = 0.7) -> str:
        """Run with primary model, fall back on hard failure."""
        try:
            return self._call(self.model, system, user,
                              json_mode=True, max_tokens=max_tokens, temperature=temperature)
        except Exception:
            # Hard failure on primary → try fallback once
            if self.fallback and self.fallback != self.model:
                return self._call(self.fallback, system, user,
                                  json_mode=True, max_tokens=max_tokens, temperature=temperature)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError)),
        reraise=True,
    )
    def vision_json(self, model: str, system: str, user_text: str,
                    image_path: Path, max_tokens: int = 1024,
                    temperature: float = 0.3) -> str:
        """Multimodal call: send a screenshot + text prompt, get strict JSON back.

        Used by the QA agent. Lower temperature for consistent scoring.
        """
        image_url = encode_image_data_url(image_path)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]},
        ]

        resp = self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        if resp.usage:
            self.usage.add(model, resp.usage.prompt_tokens, resp.usage.completion_tokens)
        return resp.choices[0].message.content or ""


# --- Helpers ----------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def parse_json_robust(raw: str) -> dict:
    """Strip markdown fences and parse. Raises ValueError if invalid."""
    s = raw.strip()
    m = _CODE_BLOCK_RE.match(s)
    if m:
        s = m.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}\n--- output ---\n{raw[:800]}") from e
