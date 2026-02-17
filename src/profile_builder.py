from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ProfileStatus:
    ok: bool
    missing_required: List[str]
    errors: List[str]


class ComponentProfileBuilder:
    """
    Deterministic helper around a *schema-driven* component profile (JSON Schema):
      - knows required fields + enums
      - can coerce user inputs (str -> float, null, etc.)
      - can render the profile as a readable markdown table

    This was originally implemented for ValveProfile, but is now generalized to
    work with any component profile schema that follows the same conventions.
    """

    def __init__(self, schema_path: Path, component: Optional[str] = None) -> None:
        self.schema_path = schema_path
        self.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.component = component  # optional hint (e.g., "valve", "pump")

        self.required: List[str] = list(self.schema.get("required", []))
        self.props: Dict[str, Any] = dict(self.schema.get("properties", {}))
        self.enums: Dict[str, List[str]] = {
            k: v.get("enum", [])
            for k, v in self.props.items()
            if isinstance(v, dict) and "enum" in v
        }

    def title(self) -> str:
        return str(self.schema.get("title") or "ComponentProfile")

    def new_profile(self) -> Dict[str, Any]:
        # Start empty; callers fill in.
        return {}

    def primary_tag_field(self) -> Optional[str]:
        """
        Best-effort inference of the primary tag/identifier field for this profile.
        Preference order:
          1) First *required* field that ends with '_tag'
          2) First property key that ends with '_tag'
        """
        for k in self.required:
            if isinstance(k, str) and k.endswith("_tag"):
                return k

        tag_keys = sorted([k for k in self.props.keys() if isinstance(k, str) and k.endswith("_tag")])
        return tag_keys[0] if tag_keys else None

    def missing_required(self, profile: Dict[str, Any]) -> List[str]:
        missing: List[str] = []
        for k in self.required:
            v = profile.get(k, None)
            if v is None or (isinstance(v, str) and v.strip() == ""):
                missing.append(k)
        return missing

    def coerce_value(self, key: str, raw: Any) -> Tuple[Any, Optional[str]]:
        """
        Convert a raw user value into a schema-compatible value when possible.
        Returns: (value, error_message_or_None).
        """
        if raw is None:
            return None, None

        # Treat common null-ish strings as None
        if isinstance(raw, str):
            s = raw.strip()
            if s.lower() in {"null", "none", "na", "n/a", "unknown", "tbd", ""}:
                return None, None

        prop = self.props.get(key, {})
        types = prop.get("type", None)

        # JSON Schema can be a string or a list like ["number","null"]
        if isinstance(types, list):
            primary = [t for t in types if t != "null"]
            types = primary[0] if primary else None

        # Enums: enforce membership
        if key in self.enums:
            allowed = self.enums[key]
            val = str(raw).strip()
            if val in allowed:
                return val, None
            return None, f"Value '{val}' not in allowed enum for {key}: {allowed}"

        # Numeric fields
        if types == "number":
            try:
                return float(raw), None
            except Exception:
                return None, f"Could not parse number for {key}: {raw!r}"

        # Objects: accept dict only
        if types == "object":
            if isinstance(raw, dict):
                return raw, None
            return None, f"Expected object/dict for {key}, got: {type(raw).__name__}"

        # Default: string
        return str(raw), None

    def apply_patch(self, profile: Dict[str, Any], patch: Dict[str, Any]) -> List[str]:
        """
        Apply a partial update to the profile. Returns list of error strings.
        """
        errors: List[str] = []
        for k, raw in patch.items():
            if k not in self.props:
                errors.append(f"Unknown field '{k}' (not in {self.title()} schema)")
                continue
            val, err = self.coerce_value(k, raw)
            if err:
                errors.append(err)
                continue
            profile[k] = val
        return errors

    def status(self, profile: Dict[str, Any]) -> ProfileStatus:
        missing = self.missing_required(profile)
        errors: List[str] = []

        # quick enum checks
        for k, allowed in self.enums.items():
            v = profile.get(k, None)
            if v is None:
                continue
            if v not in allowed:
                errors.append(f"{k}='{v}' not in enum: {allowed}")

        return ProfileStatus(ok=(len(missing) == 0 and len(errors) == 0), missing_required=missing, errors=errors)

    def render_markdown(self, profile: Dict[str, Any], title: Optional[str] = None) -> str:
        """
        Render a readable markdown table. Good for notebooks and markdown-aware UIs.
        """
        keys = sorted(self.props.keys())
        rows = []
        for k in keys:
            if k not in profile:
                continue
            v = profile.get(k)
            rows.append((k, v))

        hdr = title or self.title()
        md = [f"### {hdr}", "", "| Field | Value |", "|---|---|"]
        for k, v in rows:
            md.append(f"| `{k}` | `{v}` |")
        if not rows:
            md.append("| _No fields set yet_ | |")
        return "\n".join(md)


# Backwards-compatible alias (old name was ValveProfileBuilder).
ValveProfileBuilder = ComponentProfileBuilder
