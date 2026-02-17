from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Tuple, List, Optional


_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
        inner = value[1:-1]
        # Basic escape handling for double-quoted strings
        if value[0] == '"':
            inner = inner.encode("utf-8").decode("unicode_escape")
        return inner
    return value


def parse_dotenv(text: str) -> Tuple[Dict[str, str], List[str]]:
    """
    Parse a dotenv file content into (vars, warnings).

    Supported lines:
      - KEY=VALUE
      - export KEY=VALUE
    Notes:
      - Lines starting with '#' are ignored
      - Inline comments after values are not parsed (to avoid ambiguity)
      - Quotes around values are supported
    """
    vars_out: Dict[str, str] = {}
    warnings: List[str] = []

    for idx, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.lower().startswith("export "):
            line = line[7:].strip()

        if "=" not in line:
            warnings.append(f"Line {idx}: skipping (no '='): {raw_line!r}")
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not _KEY_RE.match(key):
            warnings.append(f"Line {idx}: invalid key {key!r}; skipping")
            continue

        vars_out[key] = _strip_quotes(value)

    return vars_out, warnings


def load_env_file(path: Path, override: bool = False) -> Tuple[Dict[str, str], List[str]]:
    """
    Load KEY=VALUE pairs from a .env file into os.environ.

    Args:
      path: .env file path
      override: if True, overwrite existing os.environ values

    Returns:
      (loaded_vars, warnings)
    """
    path = path.expanduser()
    if not path.exists() or not path.is_file():
        return {}, []

    text = path.read_text(encoding="utf-8", errors="replace")
    vars_out, warnings = parse_dotenv(text)

    loaded: Dict[str, str] = {}
    for k, v in vars_out.items():
        if (not override) and (k in os.environ):
            continue
        os.environ[k] = v
        loaded[k] = v

    return loaded, warnings


def load_default_env(repo_root: Optional[Path] = None, override: bool = False) -> Tuple[Dict[str, str], List[str], Optional[Path]]:
    """
    Convenience loader:
      1) If LLM_ENV_FILE is set, load that
      2) Else if repo_root/.env exists, load that
      3) Else if CWD/.env exists, load that

    Returns:
      (loaded_vars, warnings, used_path)
    """
    env_file = os.getenv("LLM_ENV_FILE")
    candidates: List[Path] = []
    if env_file:
        candidates.append(Path(env_file))
    if repo_root:
        candidates.append(repo_root / ".env")
    candidates.append(Path.cwd() / ".env")

    for p in candidates:
        if p.exists() and p.is_file():
            loaded, warnings = load_env_file(p, override=override)
            return loaded, warnings, p

    return {}, [], None
