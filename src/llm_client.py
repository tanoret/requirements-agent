from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol


class LLMClient(Protocol):
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 800) -> str:
        ...


@dataclass
class OpenAICompatibleClient:
    """
    Minimal client for any OpenAI-compatible Chat Completions endpoint.
    Works with many local gateways / proxies that expose /v1/chat/completions.

    Recommended env vars:
      - LLM_BASE_URL  (e.g., http://localhost:8000)
      - LLM_API_KEY   (can be dummy for local servers)
      - LLM_MODEL     (e.g., a model name supported by the endpoint)
    """
    base_url: str
    api_key: str
    model: str

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 800) -> str:
        url = self.base_url.rstrip("/") + "/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        return data["choices"][0]["message"]["content"]


@dataclass
class OllamaClient:
    """
    Minimal client for Ollama's /api/chat endpoint.
    Defaults to localhost:11434.

    Env vars (optional):
      - OLLAMA_BASE_URL (default http://localhost:11434)
      - OLLAMA_MODEL
    """
    base_url: str
    model: str

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 800) -> str:
        url = self.base_url.rstrip("/") + "/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        return data["message"]["content"]


def from_env() -> Optional[LLMClient]:
    """
    Create a client from environment variables.
    Returns None if no configuration is found.

    Supported modes:
      - LLM_MODE=ollama
      - LLM_MODE=openai_compat
    """
    mode = (os.getenv("LLM_MODE") or "").strip().lower()
    if mode == "ollama":
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3.1")
        return OllamaClient(base_url=base, model=model)

    if mode == "openai_compat":
        base = os.getenv("LLM_BASE_URL")
        key = os.getenv("LLM_API_KEY", "")
        model = os.getenv("LLM_MODEL")
        if not base or not model:
            raise ValueError("LLM_MODE=openai_compat requires LLM_BASE_URL and LLM_MODEL (and optionally LLM_API_KEY).")
        return OpenAICompatibleClient(base_url=base, api_key=key, model=model)

    return None
