from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .agent import AgentPaths, RequirementsChatAgent
from .llm_client import from_env


def _repo_root_from_here() -> Path:
    # Assumes this file is at repo_root/src/chat_cli.py
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interactive chat CLI for the valve requirements agent MVP.")
    parser.add_argument("--repo-root", default=None, help="Path to repo root (defaults to auto-detected).")
    parser.add_argument("--template", default="data/primary_loop_valve_baseline_v0.2_150reqs.json")
    parser.add_argument("--schema", default="schemas/valve_profile.schema.json")
    parser.add_argument("--out-dir", default="demo/out", help="Directory to write output packages.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else _repo_root_from_here()
    template_path = (repo_root / args.template).resolve()
    schema_path = (repo_root / args.schema).resolve()
    out_dir = (repo_root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    llm = from_env()
    agent = RequirementsChatAgent(
        paths=AgentPaths(repo_root=repo_root, template_path=template_path, schema_path=schema_path, out_dir=out_dir),
        llm=llm,
    )

    print("\nValve Requirements Agent (MVP)")
    print("Repo root:", repo_root)
    print("Template :", template_path)
    print("Schema   :", schema_path)
    print("Out dir  :", out_dir)
    print("LLM mode :", ("configured" if llm else "NONE (manual mode)"))
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
