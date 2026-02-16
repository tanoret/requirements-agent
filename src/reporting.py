from __future__ import annotations

import csv
import json
from collections import defaultdict
from typing import Any, Dict


def build_report(instance: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a compact summary report from an instance output that includes `validation`.
    Groups issues by (severity, code) and tracks impacted requirement IDs.
    """
    validation = instance.get("validation", {}) or {}
    issues = validation.get("issues", []) or []

    grouped = defaultdict(lambda: {"count": 0, "requirement_ids": set(), "messages": []})

    for issue in issues:
        severity = issue.get("severity", "unknown")
        code = issue.get("code", "UNKNOWN")
        rid = issue.get("requirement_id")
        msg = issue.get("message", "")
        key = (severity, code)

        grouped[key]["count"] += 1
        if rid:
            grouped[key]["requirement_ids"].add(rid)
        if msg and len(grouped[key]["messages"]) < 3:
            grouped[key]["messages"].append(msg)

    sev_order = {"error": 0, "warning": 1, "info": 2}
    by_code = []
    for (severity, code), v in grouped.items():
        by_code.append({
            "severity": severity,
            "code": code,
            "count": v["count"],
            "requirement_ids": sorted(v["requirement_ids"]),
            "message_examples": v["messages"]
        })
    by_code.sort(key=lambda x: (sev_order.get(x["severity"], 99), x["code"]))

    report = {
        "instance_id": instance.get("instance_id"),
        "template_id": instance.get("template_id"),
        "valve_tag": (instance.get("valve_profile", {}) or {}).get("valve_tag"),
        "generated_utc": instance.get("generated_utc"),
        "overall_status": validation.get("overall_status"),
        "counts": {
            "error_count": int(validation.get("error_count", 0) or 0),
            "warning_count": int(validation.get("warning_count", 0) or 0),
            "info_count": int(validation.get("info_count", 0) or 0),
            "issue_count": int(validation.get("issue_count", 0) or 0)
        },
        "by_code": by_code
    }
    return report


def write_report_json(report: Dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def write_report_csv(report: Dict[str, Any], path: str) -> None:
    """
    Write an aggregated CSV with one row per (severity, code).
    Columns: severity, code, count, requirement_ids, message_examples
    """
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["severity", "code", "count", "requirement_ids", "message_examples"])
        for row in report.get("by_code", []) or []:
            w.writerow([
                row.get("severity"),
                row.get("code"),
                row.get("count"),
                ";".join(row.get("requirement_ids", []) or []),
                " | ".join(row.get("message_examples", []) or [])
            ])
