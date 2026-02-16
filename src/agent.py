from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .code_rag import CodebaseRAG
from .profile_builder import ValveProfileBuilder
from .llm_client import LLMClient

from .engine import filter_and_instantiate
from .reporting import build_report, write_report_csv, write_report_json


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_first_json_object(text: str) -> Dict[str, Any]:
    """
    Best-effort extraction of a JSON object from an LLM response.
    Accepts:
      - pure JSON
      - JSON embedded in markdown/code fences
    """
    text = text.strip()

    # remove common fences
    if text.startswith("```"):
        text = text.strip("`")
        lines = text.splitlines()
        if lines and lines[0].strip().lower() in {"json", "javascript"}:
            text = "\n".join(lines[1:])

    m = _JSON_RE.search(text)
    if not m:
        raise ValueError("No JSON object found in model output.")
    candidate = m.group(0)
    return json.loads(candidate)


@dataclass
class AgentPaths:
    repo_root: Path
    template_path: Path
    schema_path: Path
    out_dir: Path


class RequirementsChatAgent:
    """
    Thin orchestration layer:
      - Maintains a ValveProfile draft
      - Collects user specs until profile is schema-complete
      - Runs deterministic engine to generate requirement instances
      - Produces a package (instance + reports) in out_dir

    Supported interaction modes:
      1) LLM-assisted extraction (preferred): user can type free text specs
      2) Manual fallback: agent will ask for required fields one by one

    CLI entrypoint:
      python -m src.chat_cli
    """

    def __init__(
        self,
        paths: AgentPaths,
        llm: Optional[LLMClient] = None,
        rag: Optional[CodebaseRAG] = None,
    ) -> None:
        self.paths = paths
        self.llm = llm
        self.builder = ValveProfileBuilder(paths.schema_path)
        self.profile: Dict[str, Any] = self.builder.new_profile()

        # Manual-mode state: which field we are currently asking the user to fill
        self._pending_field: Optional[str] = None

        self.rag = rag or CodebaseRAG(paths.repo_root)

        # Load template once
        self.template = json.loads(paths.template_path.read_text(encoding="utf-8"))

    def help_text(self) -> str:
        return (
            "Commands:\n"
            "  /help                 show commands\n"
            "  /show                 show current ValveProfile\n"
            "  /missing              show missing required fields\n"
            "  /set <field>=<value>  set a field explicitly (works in manual mode)\n"
            "  /run                  generate requirements + reports into demo/out (also zips)\n"
            "  /reset                clear the current profile\n"
            "  /ask <q>              ask a dev question grounded on the repo code (uses RAG)\n"
            "  /exit                 quit\n"
        )

    def reset(self) -> None:
        self.profile = self.builder.new_profile()
        self._pending_field = None

    def render_profile(self) -> str:
        return self.builder.render_markdown(self.profile)

    def missing_required(self) -> List[str]:
        return self.builder.missing_required(self.profile)

    def _llm_patch_from_text(self, user_text: str) -> Dict[str, Any]:
        """
        Ask the model to extract a JSON patch that updates the ValveProfile.
        """
        allowed_keys = sorted(self.builder.props.keys())
        required = self.builder.required
        enums = {k: self.builder.enums.get(k, []) for k in sorted(self.builder.enums.keys())}

        # Retrieve small amount of grounding context from the repo
        ctx = self.rag.retrieve("valve_profile schema required properties enum", k=4)
        ctx_text = "\n\n".join([f"[{c.path}:{c.start_line}-{c.end_line}]\n{c.text}" for c in ctx])

        system = (
            "You extract valve specification updates for a ValveProfile JSON.\n"
            "Return ONLY a JSON object (no prose). The JSON object is a PATCH that updates fields.\n"
            "- Use only allowed keys.\n"
            "- If a value is unknown, omit the key.\n"
            "- For numeric fields, output a number.\n"
            "- For enumerated fields, output exactly one of the allowed enum strings.\n"
        )

        user = (
            f"User message:\n{user_text}\n\n"
            f"Current ValveProfile (partial):\n{json.dumps(self.profile, indent=2)}\n\n"
            f"Required fields:\n{required}\n\n"
            f"Allowed keys:\n{allowed_keys}\n\n"
            f"Enums (only for keys that have them):\n{json.dumps(enums, indent=2)}\n\n"
            f"Repo context (for grounding):\n{ctx_text}\n\n"
            "Return a JSON patch now."
        )

        if self.llm is None:
            raise RuntimeError("No LLM client configured. Set LLM_MODE env vars or use manual entry.")
        out = self.llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
        return _extract_first_json_object(out)

    def _manual_apply(self, user_text: str) -> Tuple[bool, str]:
        """
        Manual fallback mode:
          - If a field is pending, treat user_text as the answer for that field.
          - Otherwise, ask for the next missing required field.
        """
        # If we're waiting on a specific field, apply the answer
        if self._pending_field:
            field = self._pending_field
            self._pending_field = None
            errs = self.builder.apply_patch(self.profile, {field: user_text})
            if errs:
                # Ask again for the same field
                self._pending_field = field
                return True, f"Could not set '{field}': {errs[0]}\nPlease try again."

            st = self.builder.status(self.profile)
            if st.ok:
                return True, "✅ ValveProfile looks complete. Use /show to review or /run to generate requirements."
            missing = self.builder.missing_required(self.profile)
            if missing:
                nxt = missing[0]
                self._pending_field = nxt
                if nxt in self.builder.enums:
                    return True, f"Set '{field}'. Next required field: '{nxt}'. Choose one: {self.builder.enums[nxt]}"
                return True, f"Set '{field}'. Next required field: '{nxt}'. Please provide a value."
            return True, "Updated profile. Use /show to review or /run to generate requirements."

        # No pending field -> ask the next missing required
        missing = self.builder.missing_required(self.profile)
        if missing:
            k = missing[0]
            self._pending_field = k
            if k in self.builder.enums:
                opts = self.builder.enums[k]
                return False, f"Missing required field '{k}'. Choose one: {opts}"
            return False, f"Missing required field '{k}'. Please provide a value."
        return False, "Profile appears complete. Use /run to generate requirements, or /show to review."

    def apply_user_text(self, user_text: str) -> Tuple[bool, str]:
        """
        Apply user message to profile. Returns (changed, message).
        If LLM is configured, attempts free-text extraction into a patch.
        Otherwise uses a manual "one-field-at-a-time" flow.
        """
        if self.llm is None:
            return self._manual_apply(user_text)

        # LLM-assisted patch
        try:
            patch = self._llm_patch_from_text(user_text)
        except Exception as e:
            return False, f"Could not extract a JSON patch from your message. Error: {e}"

        errs = self.builder.apply_patch(self.profile, patch)
        if errs:
            return True, "Applied partial update, but found issues:\n- " + "\n- ".join(errs)

        st = self.builder.status(self.profile)
        if st.ok:
            return True, "✅ ValveProfile looks complete. Use /show to review or /run to generate requirements."
        else:
            msg = []
            if st.missing_required:
                msg.append("Missing required: " + ", ".join(st.missing_required))
            if st.errors:
                msg.append("Schema issues: " + "; ".join(st.errors))
            return True, "Updated profile.\n" + "\n".join(msg)

    def set_field(self, field: str, value: str) -> str:
        """
        Explicitly set a field (useful in manual mode or for corrections).
        """
        errs = self.builder.apply_patch(self.profile, {field: value})
        if errs:
            return "Could not set field:\n- " + "\n- ".join(errs)
        self._pending_field = None
        st = self.builder.status(self.profile)
        if st.ok:
            return "✅ Updated. ValveProfile looks complete."
        missing = self.builder.missing_required(self.profile)
        return "Updated. Missing required: " + (", ".join(missing) if missing else "None")

    def run_and_package(self, package_name: Optional[str] = None, make_zip: bool = True) -> Path:
        """
        Generate requirements + validation reports and write a package folder into out_dir.
        Also creates a .zip (by default) for easy hand-off to downstream agents.
        Returns the created package directory path.
        """
        st = self.builder.status(self.profile)
        if not st.ok:
            raise ValueError(f"ValveProfile is incomplete/invalid. Missing={st.missing_required} Errors={st.errors}")

        instance = filter_and_instantiate(self.template, self.profile)
        report = build_report(instance)

        ts = __import__("datetime").datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        tag = str(self.profile.get("valve_tag", "VALVE")).replace("/", "_").replace(" ", "_")
        package_dir = self.paths.out_dir / (package_name or f"{tag}_{ts}")
        package_dir.mkdir(parents=True, exist_ok=True)

        # Write core artifacts
        (package_dir / "valve_profile.json").write_text(json.dumps(self.profile, indent=2), encoding="utf-8")
        (package_dir / "requirements_instance.json").write_text(json.dumps(instance, indent=2), encoding="utf-8")

        write_report_json(report, str(package_dir / "validation_report.json"))
        write_report_csv(report, str(package_dir / "validation_report.csv"))

        # Manifest for downstream agents
        manifest = {
            "package_version": "0.1",
            "created_utc": instance.get("generated_utc"),
            "valve_tag": self.profile.get("valve_tag"),
            "template_id": instance.get("template_id"),
            "summary": instance.get("summary"),
            "validation": instance.get("validation"),
            "files": {
                "valve_profile": "valve_profile.json",
                "requirements_instance": "requirements_instance.json",
                "validation_report_json": "validation_report.json",
                "validation_report_csv": "validation_report.csv",
            },
        }
        (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        if make_zip:
            zip_path = package_dir.with_suffix(".zip")
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
                for p in package_dir.rglob("*"):
                    if p.is_file():
                        z.write(p, arcname=str(p.relative_to(package_dir)))
            # Add zip name to manifest for convenience (non-breaking)
            manifest["zip"] = zip_path.name
            (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        return package_dir

    def answer_dev_question(self, question: str) -> str:
        """
        Use RAG over the repo code to answer a question.
        If no LLM configured, returns the top retrieved chunks as a fallback.
        """
        hits = self.rag.retrieve(question, k=6)
        if not hits:
            return "No relevant code snippets found."

        ctx = "\n\n".join([f"[{h.path}:{h.start_line}-{h.end_line} score={h.score:.2f}]\n{h.text}" for h in hits])

        if self.llm is None:
            return "Top relevant snippets (no LLM configured):\n\n" + ctx

        system = (
            "You answer developer questions about this repository.\n"
            "Use ONLY the provided context. If unsure, say what is missing.\n"
        )
        user = f"Question:\n{question}\n\nContext:\n{ctx}\n\nAnswer:"
        return self.llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}], temperature=0.1)
