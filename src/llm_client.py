from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Protocol

from .dotenv_loader import load_default_env


class LLMClient(Protocol):
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 800) -> str:
        ...


@dataclass
class OpenAICompatibleClient:
    """
    Minimal client for any OpenAI-compatible Chat Completions endpoint.
    Works with OpenAI and many local gateways / proxies that expose /v1/chat/completions.

    Recommended env vars:
      - LLM_BASE_URL  (e.g., https://api.openai.com OR http://localhost:8000)
      - LLM_API_KEY   (or OPENAI_API_KEY)
      - LLM_MODEL     (e.g., gpt-4o-mini)
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


def _normalize_mode(mode: str | None) -> str:
    return (mode or "").strip().lower()


def from_env(*, repo_root: Optional[Path] = None, load_env: bool = True) -> Optional[LLMClient]:
    """
    Create a client from environment variables.
    Returns None if no configuration is found.

    If load_env=True, tries to load a .env file first (without overriding existing variables):
      1) $LLM_ENV_FILE (if set)
      2) <repo_root>/.env (if repo_root passed)
      3) <cwd>/.env

    Supported modes:
      - LLM_MODE=ollama
      - LLM_MODE=openai_compat
    """
    if load_env:
        load_default_env(repo_root=repo_root, override=False)

    mode = _normalize_mode(os.getenv("LLM_MODE"))
    if mode == "ollama":
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3.1")
        return OllamaClient(base_url=base, model=model)

    if mode == "openai_compat":
        base = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com"
        key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")
        if not model:
            raise ValueError("LLM_MODE=openai_compat requires LLM_MODEL (or OPENAI_MODEL).")
        if not key:
            raise ValueError("LLM_MODE=openai_compat requires LLM_API_KEY (or OPENAI_API_KEY).")
        return OpenAICompatibleClient(base_url=base, api_key=key, model=model)

    return None
