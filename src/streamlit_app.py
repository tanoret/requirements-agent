from __future__ import annotations

import json
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List
from zipfile import ZIP_DEFLATED, ZipFile

import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.component_registry import COMPONENTS, get_component
from src.engine import filter_and_instantiate, load_template


def _schema_path(rel_path: str) -> Path:
    return ROOT / rel_path


def _load_schema(rel_path: str) -> Dict[str, Any]:
    return json.loads(_schema_path(rel_path).read_text(encoding="utf-8"))


def _coerce_from_schema(raw: str, schema_prop: Dict[str, Any]) -> Any:
    text = raw.strip()
    if text == "":
        return None

    if text.lower() in {"null", "none", "n/a", "na", "tbd", "unknown"}:
        return None

    prop_type = schema_prop.get("type")
    if isinstance(prop_type, list):
        non_null = [t for t in prop_type if t != "null"]
        prop_type = non_null[0] if non_null else None

    if prop_type == "number":
        try:
            return float(text)
        except ValueError:
            return text

    if prop_type == "integer":
        try:
            return int(float(text))
        except ValueError:
            return text

    if prop_type == "boolean":
        lowered = text.lower()
        if lowered in {"true", "yes", "1", "y"}:
            return True
        if lowered in {"false", "no", "0", "n"}:
            return False
        return text

    return text


def _extract_unit(schema_prop: Dict[str, Any]) -> str | None:
    description = (schema_prop.get("description") or "").strip()
    if not description:
        return None

    if ":" in description:
        candidate = description.split(":", maxsplit=1)[1].strip()
        if candidate and len(candidate) <= 24:
            return candidate

    if len(description) <= 24 and " " not in description:
        return description

    return None


def _default_value(component_name: str, key: str, schema_prop: Dict[str, Any]) -> Any:
    enum_values = schema_prop.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]

    key_l = key.lower()
    if key_l in {"profile_id", "metadata"}:
        return ""
    if key_l.endswith("_tag"):
        return f"{component_name.upper()}-001"

    prop_type = schema_prop.get("type")
    if isinstance(prop_type, list):
        non_null = [t for t in prop_type if t != "null"]
        prop_type = non_null[0] if non_null else None

    if prop_type not in {"number", "integer", "boolean"}:
        return ""

    if prop_type == "boolean":
        return False

    unit = (_extract_unit(schema_prop) or "").lower()
    numeric_defaults = [
        ("years", 40),
        ("months", 12),
        ("cycles", 1000),
        ("rpm", 1800),
        ("mw", 50),
        ("kw", 500),
        ("mpa", 10),
        ("kpa", 100),
        ("kg/s", 100),
        ("kg/h", 500),
        ("m3/s", 5),
        ("m3", 10),
        ("m2", 100),
        ("m", 5),
        ("mm", 25),
        ("c/hr", 30),
        ("c", 300),
        ("s", 10),
        ("h", 24),
        ("hr", 24),
        ("%", 95),
        ("percent", 95),
        ("fraction", 0.9),
        ("count", 2),
    ]
    for token, value in numeric_defaults:
        if token in unit:
            return int(value) if prop_type == "integer" else value

    if "min" in key_l:
        return 1 if prop_type == "integer" else 1.0
    if "max" in key_l:
        return 10 if prop_type == "integer" else 10.0

    return 1 if prop_type == "integer" else 1.0


def _required_schema_keys(properties: Dict[str, Any], required: set[str]) -> List[str]:
    return sorted(k for k in properties.keys() if k in required)


def _render_profile_editor(component_name: str) -> Dict[str, Any]:
    cfg = get_component(component_name)
    schema = _load_schema(cfg.schema_default)
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    st.subheader(f"{schema.get('title', component_name.title())} fields")
    st.caption("Showing only required fields from the selected component schema.")

    profile: Dict[str, Any] = {}
    cols = st.columns(2)

    keys = _required_schema_keys(properties, required)

    if not keys:
        st.info("This component schema does not define required fields.")
        return profile

    for idx, key in enumerate(keys):
        prop = properties[key] if isinstance(properties[key], dict) else {}
        unit = _extract_unit(prop)
        label = f"{key}{f' ({unit})' if unit else ''} {'*' if key in required else ''}"
        help_text = prop.get("description")
        target_col = cols[idx % 2]
        default_value = _default_value(component_name, key, prop)

        with target_col:
            if "enum" in prop and isinstance(prop["enum"], list):
                options = [""] + [str(v) for v in prop["enum"]]
                default_index = options.index(str(default_value)) if str(default_value) in options else 0
                selected = st.selectbox(
                    label,
                    options=options,
                    index=default_index,
                    key=f"{component_name}_{key}",
                    help=help_text,
                )
                if selected != "":
                    profile[key] = selected
            elif prop.get("type") == "boolean" or (isinstance(prop.get("type"), list) and "boolean" in prop.get("type", [])):
                default_tri = "true" if default_value is True else "false" if default_value is False else ""
                tri_options = ["", "true", "false"]
                tri = st.selectbox(
                    label,
                    options=tri_options,
                    index=tri_options.index(default_tri),
                    key=f"{component_name}_{key}",
                    help=help_text,
                )
                if tri:
                    profile[key] = tri == "true"
            else:
                raw = st.text_input(label, value=str(default_value), key=f"{component_name}_{key}", help=help_text)
                value = _coerce_from_schema(raw, prop)
                if value is not None:
                    profile[key] = value

    missing_required = [k for k in sorted(required) if k not in profile]
    if missing_required:
        st.warning(f"Missing required fields: {', '.join(missing_required)}")
    else:
        st.success("All required schema fields are populated.")

    return profile


def _summarize_instance(instance: Dict[str, Any]) -> None:
    summary = instance.get("summary", {})
    validation = instance.get("validation", {})

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Applicable", summary.get("applicable_count", 0))
    m2.metric("Non-applicable", summary.get("non_applicable_count", 0))
    m3.metric("TBD parameters", summary.get("tbd_parameter_count", 0))
    m4.metric("Validation status", validation.get("overall_status", "unknown"))

    requirements = instance.get("applicable_requirements", [])
    if not requirements:
        st.info("No applicable requirements generated.")
        return

    st.markdown("### Requirement organization")

    by_type: Dict[str, List[Dict[str, Any]]] = {}
    by_status: Dict[str, List[Dict[str, Any]]] = {}
    for req in requirements:
        by_type.setdefault(str(req.get("type", "unknown")), []).append(req)
        by_status.setdefault(str(req.get("status", "unknown")), []).append(req)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**By requirement type**")
        st.table({"Type": list(by_type.keys()), "Count": [len(v) for v in by_type.values()]})

    with c2:
        st.markdown("**By lifecycle status**")
        st.table({"Status": list(by_status.keys()), "Count": [len(v) for v in by_status.values()]})

    st.markdown("### Logical map (Type → Requirement IDs)")
    for req_type, reqs in sorted(by_type.items()):
        with st.expander(f"{req_type} ({len(reqs)})", expanded=False):
            for req in reqs:
                st.markdown(f"- **{req.get('id', 'unknown-id')}** → {req.get('status', 'unknown')}")
                st.caption(req.get("text", ""))


def _build_export_zip(items: List[Dict[str, Any]]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as zf:
        manifest = {
            "generated_utc": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "count": len(items),
            "components": [
                {
                    "component": item["component"],
                    "instance_id": item["instance"].get("instance_id", "unknown"),
                }
                for item in items
            ],
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

        for item in items:
            component = item["component"]
            instance = item["instance"]
            instance_id = instance.get("instance_id", f"{component}-requirements")
            safe_name = instance_id.replace("/", "_")
            zf.writestr(f"{component}/{safe_name}.json", json.dumps(instance, indent=2))
    return buffer.getvalue()


def main() -> None:
    st.set_page_config(page_title="Requirements Agent UI", page_icon="🧩", layout="wide")
    st.title("🧩 Requirements Agent Web App")
    st.write("Generate and organize component requirements from baseline templates.")

    if "generated_instances" not in st.session_state:
        st.session_state.generated_instances = []

    component_name = st.selectbox("1) Select a component type", options=sorted(COMPONENTS.keys()))

    with st.form("profile_form"):
        profile = _render_profile_editor(component_name)
        submitted = st.form_submit_button("2) Generate requirements")

    if submitted:
        cfg = get_component(component_name)
        template = load_template(str(ROOT / cfg.template_default))
        instance = filter_and_instantiate(
            template,
            profile,
            profile_key=cfg.profile_key,
            tag_field=cfg.tag_field,
        )
        st.session_state.generated_instances.append({"component": component_name, "instance": instance})
        st.success(f"Generated requirements for {component_name}: {instance['instance_id']}")

    generated_items: List[Dict[str, Any]] = st.session_state.generated_instances
    if generated_items:
        st.markdown("---")
        st.header("3) Generated requirement sets")

        for idx, item in enumerate(generated_items, start=1):
            instance = item["instance"]
            component = item["component"]
            with st.expander(f"{idx}. {component} — {instance.get('instance_id', 'unknown')}", expanded=(idx == len(generated_items))):
                _summarize_instance(instance)

                payload = json.dumps(instance, indent=2)
                st.download_button(
                    label="4) Export this component requirements JSON",
                    data=payload,
                    file_name=f"{instance.get('instance_id', component)}.json",
                    mime="application/json",
                    key=f"download_{idx}",
                )

        st.markdown("### 5) Export all generated components")
        archive = _build_export_zip(generated_items)
        st.download_button(
            label="Download ZIP (all generated requirement instances)",
            data=archive,
            file_name="requirements_instances_bundle.zip",
            mime="application/zip",
            key="download_all_zip",
        )

        if st.button("Reset generated components"):
            st.session_state.generated_instances = []
            st.rerun()


if __name__ == "__main__":
    main()
