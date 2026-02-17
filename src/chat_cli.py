from __future__ import annotations

import argparse
from pathlib import Path

from .agent import AgentPaths, RequirementsChatAgent
from .llm_client import from_env


DEFAULT_COMPONENT_CONFIG = {
    "valve": {
        "template": "data/valve_baseline.json",
        "schema": "schemas/valve_profile.schema.json",
        "profile_key": "valve_profile",
        "tag_field": "valve_tag",
    },
    "pump": {
        "template": "data/pump_baseline.json",
        "schema": "schemas/pump_profile.schema.json",
        "profile_key": "pump_profile",
        "tag_field": "pump_tag",
    },
    "steam_generator": {
        "template": "data/steam_generator_baseline.json",
        "schema": "schemas/steam_generator_profile.schema.json",
        "profile_key": "steam_generator_profile",
        "tag_field": "steam_generator_tag",
    },
    "turbine": {
        "template": "data/turbine_baseline.json",
        "schema": "schemas/turbine_profile.schema.json",
        "profile_key": "turbine_profile",
        "tag_field": "turbine_tag",
    },
    "condenser": {
        "template": "data/condenser_baseline.json",
        "schema": "schemas/condenser_profile.schema.json",
        "profile_key": "condenser_profile",
        "tag_field": "condenser_tag",
    },
    "pressurizer": {
        "template": "data/pressurizer_baseline.json",
        "schema": "schemas/pressurizer_profile.schema.json",
        "profile_key": "pressurizer_profile",
        "tag_field": "pressurizer_tag",
    },
}


def _repo_root_from_here() -> Path:
    # Assumes this file is at repo_root/src/chat_cli.py
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interactive chat CLI for the component requirements agent MVP.")
    parser.add_argument(
        "--component",
        default="valve",
        choices=sorted(DEFAULT_COMPONENT_CONFIG.keys()),
        help="Which component library to use.",
    )
    parser.add_argument("--repo-root", default=None, help="Path to repo root (defaults to auto-detected).")

    # Optional overrides (if omitted, defaults come from the component config above)
    parser.add_argument("--template", default=None, help="Path to requirements library JSON (override).")

    parser.add_argument("--schema", default=None, help="Path to component profile schema JSON (override).")
    parser.add_argument("--profile-key", default=None, help="Instance key for the profile (override).")

    parser.add_argument("--tag-field", default=None, help="Primary tag field inside the profile (override).")

    parser.add_argument("--out-dir", default="demo/out", help="Directory to write output packages.")
    args = parser.parse_args(argv)

    component = args.component
    cfg = DEFAULT_COMPONENT_CONFIG[component]

    repo_root = Path(args.repo_root).resolve() if args.repo_root else _repo_root_from_here()

    template_rel = args.template if args.template is not None else cfg["template"]
    schema_rel = args.schema if args.schema is not None else cfg["schema"]

    template_path = (repo_root / template_rel).resolve()
    schema_path = (repo_root / schema_rel).resolve()

    out_dir = (repo_root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    llm = from_env()
    agent = RequirementsChatAgent(
        paths=AgentPaths(
            repo_root=repo_root,
            component=component,
            template_path=template_path,
            schema_path=schema_path,
            out_dir=out_dir,
            profile_key=args.profile_key or cfg.get("profile_key"),
            tag_field=args.tag_field or cfg.get("tag_field"),
        ),
        llm=llm,
    )

    print("\nComponent Requirements Agent (MVP)")
    print("Component:", component)
    print("Repo root :", repo_root)
    print("Template  :", template_path)
    print("Schema    :", schema_path)
    print("Out dir   :", out_dir)
    print("LLM mode  :", ("configured" if llm else "NONE (manual mode)"))
    print("\n" + agent.help_text())

    while True:
        try:
            user = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            return 0

        if not user:
            continue

        if user in {"/exit", "exit", "quit"}:
            return 0

        if user in {"/help", "help"}:
            print(agent.help_text())
            continue

        if user == "/reset":
            agent.reset()
            print("Profile cleared.")
            continue

        if user == "/show":
            print(agent.render_profile())
            continue

        if user == "/missing":
            m = agent.missing_required()
            print("Missing required fields:", (", ".join(m) if m else "None"))
            continue

        if user.startswith("/set "):
            # /set field=value
            expr = user[len("/set "):].strip()
            if "=" not in expr:
                print("Usage: /set field=value")
                continue
            field, value = expr.split("=", 1)
            print(agent.set_field(field.strip(), value.strip()))
            continue

        if user.startswith("/ask "):
            q = user[len("/ask "):].strip()
            print(agent.answer_dev_question(q))
            continue

        if user == "/run":
            try:
                pkg = agent.run_and_package()
            except Exception as e:
                print("Could not run:", e)
                continue
            print(f"✅ Wrote package folder: {pkg}")
            zip_path = pkg.with_suffix(".zip")
            if zip_path.exists():
                print(f"✅ Wrote zip: {zip_path}")
            continue

        # Default: treat as spec text (LLM-assisted or manual flow)
        changed, msg = agent.apply_user_text(user)
        print(msg)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
