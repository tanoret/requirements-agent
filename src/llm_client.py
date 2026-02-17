from __future__ import annotations

"""
LLM client utilities for the requirements agent.

Supports:
  - LLM_MODE=ollama
  - LLM_MODE=openai_compat  (OpenAI API or any OpenAI-compatible gateway)

Key features:
  - Optional .env loading (no third-party dependency)
  - TLS controls for corporate proxies / self-signed cert chains:
      * LLM_TLS_VERIFY=0 (dev only)
      * LLM_CA_BUNDLE=/path/to/ca.pem  (recommended)
  - Better HTTP error messages (includes response body)
  - Exponential backoff retries for transient errors (429/5xx), per OpenAI guidance
    (and uses Retry-After if present).
"""

import json
import os
import random
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Union


# -----------------------------
# Public protocol
# -----------------------------

class LLMClient(Protocol):
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 800) -> str:
        ...


# -----------------------------
# Small helpers
# -----------------------------

def _env_bool(name: str, default: bool = True) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    val = val.strip().lower()
    return val not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    v = (os.getenv(name) or "").strip()
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    v = (os.getenv(name) or "").strip()
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _load_dotenv(dotenv_path: Path, override: bool = False) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ (lightweight, no dependencies)."""
    if not dotenv_path.exists():
        return

    for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        # Strip surrounding quotes
        if (len(value) >= 2) and ((value[0] == value[-1]) and value[0] in {"'", '"'}):
            value = value[1:-1]

        if not override and key in os.environ:
            continue

        os.environ[key] = value


def _pick_ca_bundle() -> Optional[str]:
    """Select a CA bundle path if provided."""
    for k in ("LLM_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        v = (os.getenv(k) or "").strip()
        if v:
            return v
    return None


def _build_ssl_context() -> Optional[ssl.SSLContext]:
    """Build an SSL context for urllib based on env vars."""
    verify = _env_bool("LLM_TLS_VERIFY", True)
    ca_bundle = _pick_ca_bundle()

    if not verify:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    ctx = ssl.create_default_context()
    if ca_bundle:
        if not os.path.exists(ca_bundle):
            raise FileNotFoundError(f"CA bundle file not found: {ca_bundle}")
        ctx.load_verify_locations(cafile=ca_bundle)
    return ctx


def _http_body_from_error(err: urllib.error.HTTPError) -> str:
    try:
        data = err.read()
    except Exception:
        return ""
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return repr(data)


def _sleep_with_jitter(seconds: float) -> None:
    # +/- 20% jitter
    jitter = seconds * 0.2
    delay = max(0.0, seconds + random.uniform(-jitter, jitter))
    time.sleep(delay)


def _urlopen(req: urllib.request.Request, timeout: int = 120) -> str:
    """urlopen wrapper with TLS config + retries + clearer errors.

    Retries:
      - 429 (rate limit / quota) and common transient 5xx.
    """
    ctx = _build_ssl_context()

    max_retries = _env_int("LLM_MAX_RETRIES", 6)
    base_delay = _env_float("LLM_BACKOFF_BASE_SECONDS", 1.0)
    max_delay = _env_float("LLM_BACKOFF_MAX_SECONDS", 30.0)
    debug = _env_bool("LLM_DEBUG", False)

    retry_codes = {429, 500, 502, 503, 504}

    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = _http_body_from_error(e)

            # Retry on transient / rate limit errors
            if e.code in retry_codes and attempt < max_retries:
                # Prefer Retry-After if server provides it
                ra = (e.headers.get("Retry-After") or "").strip()
                delay: float
                if ra:
                    try:
                        delay = float(ra)
                    except ValueError:
                        delay = base_delay * (2 ** attempt)
                else:
                    delay = base_delay * (2 ** attempt)

                delay = min(delay, max_delay)

                if debug:
                    print(f"[LLM] HTTP {e.code}. Retrying in {delay:.2f}s (attempt {attempt+1}/{max_retries})")

                _sleep_with_jitter(delay)
                continue

            # No retry left (or non-retryable)
            msg = f"LLM HTTPError {e.code}: {e.reason}"
            if body:
                msg += f"\n--- body ---\n{body}\n--- end body ---"
            raise RuntimeError(msg) from e

        except urllib.error.URLError as e:
            # Often wrapped as URLError(reason=SSLCertVerificationError)
            if isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
                hint = (
                    "TLS certificate verification failed.\n"
                    "If you're behind a corporate proxy (TLS inspection) or calling an internal gateway with a private CA, "
                    "add the proxy/root CA certificate (PEM) and set LLM_CA_BUNDLE=/path/to/ca.pem (or SSL_CERT_FILE).\n"
                    "For local development only, you can bypass verification with LLM_TLS_VERIFY=0."
                )
                raise RuntimeError(f"{hint}\nOriginal error: {e}") from e
            raise RuntimeError(f"LLM URLError: {e}") from e


# -----------------------------
# Concrete clients
# -----------------------------

@dataclass
class OpenAICompatibleClient:
    """Minimal client for any OpenAI-compatible Chat Completions endpoint."""
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
        headers = {"Content-Type": "application/json"}
        # Some gateways don't require a key, so only include if present.
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        body = _urlopen(req, timeout=120)
        data = json.loads(body)
        return data["choices"][0]["message"]["content"]


@dataclass
class OllamaClient:
    """Minimal client for Ollama's /api/chat endpoint."""
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
        body = _urlopen(req, timeout=120)
        data = json.loads(body)
        return data["message"]["content"]


# -----------------------------
# Factory
# -----------------------------

def from_env(
    repo_root: Optional[Union[str, Path]] = None,
    env_file: Optional[Union[str, Path]] = None,
    load_env: bool = True,
    override_env: bool = False,
    **_ignored,
) -> Optional[LLMClient]:
    """Create an LLM client from environment variables.

    Compatible with both CLI variants:
      - older: from_env()
      - newer: from_env(repo_root=..., load_env=False)

    If load_env is False but required vars are missing, we still try a best-effort .env load
    from repo_root/.env (or CWD/.env) to avoid surprising "None" configs.
    """
    rr = Path(repo_root).resolve() if repo_root else Path.cwd()

    # Best-effort .env loading
    if load_env:
        ef = Path(env_file).resolve() if env_file else (rr / ".env")
        _load_dotenv(ef, override=override_env)
    else:
        # If caller *thought* env was loaded but it's not, try to recover.
        if not os.getenv("LLM_MODE") and (rr / ".env").exists():
            _load_dotenv(rr / ".env", override=override_env)

    mode = (os.getenv("LLM_MODE") or "").strip().lower()
    if mode == "ollama":
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3.1")
        return OllamaClient(base_url=base, model=model)

    if mode == "openai_compat":
        # Base URL is required, but default to OpenAI if user didn't set it.
        base = (os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com").strip()
        key = (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
        model = (os.getenv("LLM_MODEL") or "").strip()

        if not model:
            raise ValueError("LLM_MODE=openai_compat requires LLM_MODEL (e.g., gpt-4o-mini).")

        return OpenAICompatibleClient(base_url=base, api_key=key, model=model)

    # Unconfigured -> manual mode upstream
    return None
