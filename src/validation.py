from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


@dataclass(frozen=True)
class ValidationIssue:
    severity: str  # "error" | "warning" | "info"
    code: str
    message: str
    requirement_id: Optional[str] = None


def _has_shall(text: str) -> bool:
    # nuclear requirements are typically "shall". Keep it heuristic.
    return " shall " in f" {text.lower()} "


def _atomicity_warnings(text: str) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    tl = text.lower()

    if "and/or" in tl:
        issues.append(ValidationIssue(
            severity="warning",
            code="REQ_ATOMICITY_ANDOR",
            message="Requirement contains 'and/or' which is often ambiguous; consider splitting."
        ))

    # Simple heuristic: multiple 'shall' often indicates compound requirement
    shall_count = tl.count(" shall ")
    if shall_count > 1:
        issues.append(ValidationIssue(
            severity="warning",
            code="REQ_ATOMICITY_MULTI_SHALL",
            message=f"Requirement contains {shall_count} occurrences of 'shall'; may be compound."
        ))

    # Heuristic for compound clauses: ' shall ... and shall ...' or ' shall ... and ...'
    if re.search(r"\bshall\b.*\band\b.*\bshall\b", tl):
        issues.append(ValidationIssue(
            severity="warning",
            code="REQ_ATOMICITY_CONJUNCTION",
            message="Requirement may be compound (contains 'shall ... and ... shall ...'); consider splitting."
        ))

    return issues


def validate_requirement_instance(req: Dict[str, Any]) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    rid = req.get("id")

    text = req.get("text", "") or ""
    rtype = req.get("type", "") or ""

    # 1) Verification method & acceptance criteria
    verification = req.get("verification", {}) or {}
    methods = verification.get("method", [])
    acceptance = verification.get("acceptance", "")

    if not isinstance(methods, list) or len(methods) == 0:
        issues.append(ValidationIssue(
            severity="error",
            code="REQ_VERIFICATION_METHOD_MISSING",
            message="Verification.method must be a non-empty list.",
            requirement_id=rid
        ))

    if not isinstance(acceptance, str) or acceptance.strip() == "":
        issues.append(ValidationIssue(
            severity="error",
            code="REQ_VERIFICATION_ACCEPTANCE_MISSING",
            message="Verification.acceptance must be a non-empty string.",
            requirement_id=rid
        ))

    # 2) 'shall' heuristic (allow exceptions for some types)
    if rtype not in {"programmatic"}:
        if not _has_shall(text):
            issues.append(ValidationIssue(
                severity="warning",
                code="REQ_SHALL_NOT_FOUND",
                message="Requirement text does not contain 'shall'; confirm requirement wording.",
                requirement_id=rid
            ))

    # 3) Unresolved placeholders must be listed as TBD
    unresolved = sorted(set(m.group(1) for m in _PLACEHOLDER_RE.finditer(text)))
    tbd = req.get("tbd_parameters", []) or []
    if unresolved:
        missing_from_tbd = [p for p in unresolved if p not in tbd]
        if missing_from_tbd:
            issues.append(ValidationIssue(
                severity="error",
                code="REQ_PLACEHOLDER_UNTRACKED",
                message=f"Unresolved placeholders not tracked in tbd_parameters: {missing_from_tbd}",
                requirement_id=rid
            ))
        else:
            issues.append(ValidationIssue(
                severity="warning",
                code="REQ_PLACEHOLDER_TBD",
                message=f"Requirement has unresolved placeholders that require inputs: {unresolved}",
                requirement_id=rid
            ))

    # 4) Atomicity heuristics
    for i in _atomicity_warnings(text):
        issues.append(ValidationIssue(
            severity=i.severity,
            code=i.code,
            message=i.message,
            requirement_id=rid
        ))

    return issues


def validate_instance(instance: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate an instance output. Returns a 'validation' object:
      - overall_status: "pass" | "fail"
      - error_count, warning_count, info_count, issue_count
      - issues: list of issue dicts
    """
    issues: List[ValidationIssue] = []

    applicable = instance.get("applicable_requirements", []) or []
    if not isinstance(applicable, list):
        issues.append(ValidationIssue(
            severity="error",
            code="INSTANCE_APPLICABLE_NOT_LIST",
            message="applicable_requirements must be a list."
        ))
        applicable = []

    for req in applicable:
        if not isinstance(req, dict):
            issues.append(ValidationIssue(
                severity="error",
                code="INSTANCE_REQ_NOT_OBJECT",
                message="Each applicable requirement must be an object."
            ))
            continue
        issues.extend(validate_requirement_instance(req))

    # Summaries
    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    info_count = sum(1 for i in issues if i.severity == "info")
    issue_count = len(issues)

    overall = "fail" if error_count > 0 else "pass"

    return {
        "overall_status": overall,
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "issue_count": issue_count,
        "issues": [
            {
                "severity": i.severity,
                "code": i.code,
                "message": i.message,
                **({"requirement_id": i.requirement_id} if i.requirement_id else {})
            }
            for i in issues
        ]
    }
