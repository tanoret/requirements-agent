from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional

from .validation import validate_instance
from .reporting import build_report, write_report_json, write_report_csv


_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


@dataclass(frozen=True)
class ConditionResult:
    matched: bool
    reasons: List[str]


def _get(profile: Dict[str, Any], key: str) -> Any:
    """Get a profile value. Currently expects flat keys (e.g., 'actuation_type')."""
    return profile.get(key)


def parse_simple_condition(cond: str) -> Tuple[str, str, str]:
    """
    Parse a simple condition string of the forms:
      - key=value1|value2
      - key>number, key>=number, key<number, key<=number
    Returns (key, op, rhs_string).
    """
    cond = cond.strip()
    # Order matters: >= and <= before > and <
    for op in (">=", "<=", ">", "<", "="):
        if op in cond:
            parts = cond.split(op, 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid condition: {cond!r}")
            key = parts[0].strip()
            rhs = parts[1].strip()
            if not key:
                raise ValueError(f"Invalid condition (missing key): {cond!r}")
            if rhs == "":
                raise ValueError(f"Invalid condition (missing rhs): {cond!r}")
            return key, op, rhs
    raise ValueError(f"Invalid condition (no operator found): {cond!r}")


def eval_condition(profile: Dict[str, Any], cond: str) -> ConditionResult:
    """
    Evaluate a single condition. Supports:
      - 'always'
      - key=value1|value2 (string equality)
      - key>number etc (numeric compare)
    """
    cond = cond.strip()
    if cond == "always":
        return ConditionResult(True, [])

    try:
        key, op, rhs = parse_simple_condition(cond)
    except ValueError as e:
        return ConditionResult(False, [str(e)])

    value = _get(profile, key)
    if value is None:
        return ConditionResult(False, [f"Missing profile value for '{key}'"])

    # Equality (string-ish)
    if op == "=":
        accepted = [v.strip() for v in rhs.split("|")]
        matched = str(value) in accepted
        if matched:
            return ConditionResult(True, [])
        return ConditionResult(False, [f"{key}='{value}' not in {accepted}"])

    # Numeric comparisons
    try:
        lhs = float(value)
        rhs_num = float(rhs)
    except Exception:
        return ConditionResult(False, [f"Non-numeric compare for {key} {op} {rhs} (value={value!r})"])

    if op == ">":
        ok = lhs > rhs_num
    elif op == ">=":
        ok = lhs >= rhs_num
    elif op == "<":
        ok = lhs < rhs_num
    elif op == "<=":
        ok = lhs <= rhs_num
    else:
        ok = False

    if ok:
        return ConditionResult(True, [])
    return ConditionResult(False, [f"{key}={lhs} not {op} {rhs_num}"])


def eval_when(profile: Dict[str, Any], when_list: List[str]) -> ConditionResult:
    """
    Evaluate a list of conditions (AND semantics).
    - If 'always' appears alone, it's trivially true.
    - Otherwise all conditions must match.
    """
    reasons: List[str] = []
    for cond in when_list:
        r = eval_condition(profile, cond)
        if not r.matched:
            reasons.extend(r.reasons or [f"Failed condition: {cond}"])
    return ConditionResult(matched=(len(reasons) == 0), reasons=reasons)


def instantiate_text(text: str, profile: Dict[str, Any]) -> Tuple[str, Dict[str, Any], List[str]]:
    """
    Replace {{param}} placeholders with values from profile (if present).
    Returns (instantiated_text, parameter_values_used, tbd_params).
    """
    used: Dict[str, Any] = {}
    tbd: List[str] = []

    def repl(m: re.Match) -> str:
        key = m.group(1)
        val = profile.get(key, None)
        if val is None:
            if key not in tbd:
                tbd.append(key)
            return f"{{{{{key}}}}}"  # keep placeholder
        used[key] = val
        return str(val)

    instantiated = _PLACEHOLDER_RE.sub(repl, text)
    return instantiated, used, tbd


def load_template(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def iter_requirements(template: Dict[str, Any]):
    for req_set in template.get("requirement_sets", []):
        for r in req_set.get("requirements", []):
            yield r


def _infer_tag_field(profile: Dict[str, Any]) -> Optional[str]:
    # Prefer *_tag keys if present
    tag_keys = [k for k in profile.keys() if isinstance(k, str) and k.endswith("_tag") and profile.get(k)]
    if tag_keys:
        return sorted(tag_keys)[0]
    return None


def filter_and_instantiate(
    template: Dict[str, Any],
    profile: Dict[str, Any],
    *,
    component: str = "valve",
    profile_key: Optional[str] = None,
    tag_field: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Produce an instance object with applicable + non-applicable requirements.

    Notes:
      - 'component' is used only to choose sensible defaults for profile_key/tag_field.
      - The instance embeds the profile under 'profile_key' (e.g., 'valve_profile', 'pump_profile', ...).
      - No additional top-level keys are added beyond the instance schema fields.
    """
    profile_key = profile_key or f"{component}_profile"
    tag_field = tag_field or f"{component}_tag"

    # If the chosen tag_field isn't present, infer from provided profile contents.
    if profile.get(tag_field) in {None, ""}:
        inferred = _infer_tag_field(profile)
        if inferred:
            tag_field = inferred

    tag_value = profile.get(tag_field) if tag_field else None
    tag_value = (str(tag_value).strip() if tag_value is not None else "") or component.upper()

    applicable = []
    non_applicable = []
    tbd_params_total = set()

    for r in iter_requirements(template):
        when_list = r.get("applicability", {}).get("when", ["always"])
        res = eval_when(profile, when_list)

        if res.matched:
            text = r.get("text", "")
            instantiated_text, used, tbd = instantiate_text(text, profile)
            for p in tbd:
                tbd_params_total.add(p)

            status = "review_required" if tbd else "draft"
            applicable.append({
                "id": r.get("id"),
                "text": instantiated_text,
                "type": r.get("type", "unknown"),
                "verification": r.get("verification", {"method": [], "acceptance": ""}),
                "provenance_refs": r.get("provenance_refs", []),
                "status": status,
                "parameter_values": used,
                "tbd_parameters": tbd,
                "applicability": {"conditions": when_list, "matched": True}
            })
        else:
            non_applicable.append({
                "id": r.get("id"),
                "conditions": when_list,
                "reasons": res.reasons or ["Not applicable"]
            })

    instance: Dict[str, Any] = {
        "instance_id": f"{tag_value}-requirements",
        "template_id": template.get("template_id", "unknown_template"),
        "generated_utc": __import__("datetime").datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        profile_key: profile,
        "summary": {
            "applicable_count": len(applicable),
            "non_applicable_count": len(non_applicable),
            "tbd_parameter_count": len(tbd_params_total)
        },
        "applicable_requirements": applicable,
        "non_applicable_requirements": non_applicable
    }

    # Quality gate validation (custom checks; independent from JSON Schema)
    instance["validation"] = validate_instance(instance)

    return instance


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Filter and instantiate component requirements from a template.")
    parser.add_argument("--component", default="valve", help="Component name (affects defaults). Example: valve, pump, turbine, condenser, pressurizer, steam_generator")
    parser.add_argument("--profile-key", default=None, help="Top-level instance key for the profile (e.g., valve_profile, pump_profile). Defaults to '<component>_profile'.")
    parser.add_argument("--tag-field", default=None, help="Primary tag field inside the profile (e.g., valve_tag). Defaults to '<component>_tag'.")
    parser.add_argument("--template", required=True, help="Path to requirements library JSON.")
    parser.add_argument("--profile", required=True, help="Path to ComponentProfile JSON (must match the profile schema).")
    parser.add_argument("--out", required=True, help="Output path for instance JSON.")
    parser.add_argument("--strict", action="store_true", help="Exit with non-zero status if validation fails (errors present).")
    parser.add_argument("--fail-on-warnings", action="store_true", help="Exit with non-zero status if any warnings are present.")
    parser.add_argument("--max-warnings", type=int, default=None, help="Exit non-zero if warning_count exceeds this value.")
    parser.add_argument("--report-json", default=None, help="Optional path to write a validation summary report (JSON).")
    parser.add_argument("--report-csv", default=None, help="Optional path to write a validation summary report (CSV).")
    args = parser.parse_args(argv)

    template = load_template(args.template)
    with open(args.profile, "r", encoding="utf-8") as f:
        profile = json.load(f)

    instance = filter_and_instantiate(
        template,
        profile,
        component=args.component,
        profile_key=args.profile_key,
        tag_field=args.tag_field,
    )
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(instance, f, indent=2, ensure_ascii=False)
    print(f"Wrote: {args.out} (applicable={instance['summary']['applicable_count']})")

    # Optional report outputs
    if args.report_json or args.report_csv:
        report = build_report(instance)
        if args.report_json:
            write_report_json(report, args.report_json)
            print(f"Wrote report (JSON): {args.report_json}")
        if args.report_csv:
            write_report_csv(report, args.report_csv)
            print(f"Wrote report (CSV): {args.report_csv}")

    # Quality gate strict exit
    v = instance.get("validation", {}) or {}
    overall = v.get("overall_status", "pass")
    warnings = int(v.get("warning_count", 0) or 0)
    if args.strict and overall != "pass":
        return 2
    if args.fail_on_warnings and warnings > 0:
        return 3
    if args.max_warnings is not None and warnings > args.max_warnings:
        return 4

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
