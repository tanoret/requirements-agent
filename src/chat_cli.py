from __future__ import annotations

import argparse
from pathlib import Path

from .agent import AgentPaths, RequirementsChatAgent
from .component_registry import COMPONENTS, get_component
from .dotenv_loader import load_env_file
from .llm_client import from_env


def _repo_root_from_here() -> Path:
    # Assumes this file is at repo_root/src/chat_cli.py
    return Path(__file__).resolve().parents[1]


def _resolve_under_repo(repo_root: Path, maybe_rel: str) -> Path:
    p = Path(maybe_rel)
    return (repo_root / p).resolve() if not p.is_absolute() else p.resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interactive chat CLI for requirements (valves, pumps, SGs, turbines, condensers, pressurizers).")
    parser.add_argument("--repo-root", default=None, help="Path to repo root (defaults to auto-detected).")
    parser.add_argument("--component", default="valve", choices=sorted(COMPONENTS.keys()), help="Which component library/schema to use.")
    parser.add_argument("--template", default=None, help="Override template JSON path (repo-root-relative or absolute).")
    parser.add_argument("--schema", default=None, help="Override profile schema JSON path (repo-root-relative or absolute).")
    parser.add_argument("--profile-key", default=None, help="Override profile key used in requirements_instance.json (advanced).")
    parser.add_argument("--tag-field", default=None, help="Override tag field used for naming outputs (advanced).")
    parser.add_argument("--out-dir", default="demo/out", help="Directory to write output packages (repo-root-relative or absolute).")
    parser.add_argument("--env-file", default=".env", help="Dotenv file to load (repo-root-relative or absolute). Use 'none' to disable.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else _repo_root_from_here()

    # Load .env early so users don't have to export env vars manually
    env_loaded = {}
    env_warnings = []
    env_path = None
    if args.env_file and str(args.env_file).strip().lower() not in {"none", "false", "0"}:
        env_path = _resolve_under_repo(repo_root, args.env_file)
        loaded, warnings = load_env_file(env_path, override=False)
        env_loaded, env_warnings = loaded, warnings

    cfg = get_component(args.component)

    template_rel = args.template if args.template else cfg.template_default
    schema_rel = args.schema if args.schema else cfg.schema_default

    template_path = _resolve_under_repo(repo_root, template_rel)
    schema_path = _resolve_under_repo(repo_root, schema_rel)
    out_dir = _resolve_under_repo(repo_root, args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    profile_key = args.profile_key or cfg.profile_key
    tag_field = args.tag_field or cfg.tag_field

    llm = from_env(repo_root=repo_root, load_env=False)  # already loaded above
    agent = RequirementsChatAgent(
        paths=AgentPaths(
            repo_root=repo_root,
            template_path=template_path,
            schema_path=schema_path,
            out_dir=out_dir,
            component=cfg.name,
            profile_key=profile_key,
            tag_field=tag_field,
        ),
        llm=llm,
    )

    print("\nRequirements Chat CLI")
    print("Component:", cfg.name)
    print("Repo root:", repo_root)
    print("Template :", template_path)
    print("Schema   :", schema_path)
    print("Out dir  :", out_dir)

    if env_path and env_path.exists():
        print("Env file :", env_path)
        if env_loaded:
            print("Loaded   :", ", ".join(sorted(env_loaded.keys())))
        if env_warnings:
            print("Env warnings:")
            for w in env_warnings[:10]:
                print("  -", w)

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
