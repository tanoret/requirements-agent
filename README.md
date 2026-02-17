# Requirements Agent MVP (Valve)

This starter kit turns the deterministic requirements generation flow into both:
- a **CLI pipeline**, and
- a **Streamlit web app** for interactive multi-component generation.

The core flow is:
1. **ComponentProfile** (input): a flat JSON with schema-defined tags/fields.
2. **Filter**: evaluates `applicability.when` conditions (AND semantics; `|` means OR).
3. **Instantiate**: substitutes `{{param}}` placeholders from the profile.
4. **Output**: a component-specific `*RequirementsInstance` JSON with applicable + non-applicable requirements and TBD tracking.

## Files
- Component schemas in `schemas/*_profile.schema.json`
- Instance schemas in `schemas/*_requirements_instance.schema.json`
- Baselines/templates in `data/*_baseline.json`
- `src/engine.py` (filter + instantiate + CLI)
- `src/streamlit_app.py` (interactive web app)
- `examples/` (sample profile and generated output)

## Quick start (CLI)
```bash
python -m src.engine \
  --template "data/valve_baseline.json" \
  --profile examples/valve_profile_example.json \
  --out examples/valve_requirements_instance.json
```

## Streamlit web app

### Install runtime dependency
```bash
pip install -r requirements.txt
```

### Launch the app
```bash
streamlit run src/streamlit_app.py
```

### What the app supports
1. Select a component type (valve, pump, turbine, condenser, steam generator, pressurizer).
2. Fill schema tags/fields (required + optional) directly in a form.
3. Generate requirements for that component.
4. Review semantic organization:
   - summary metrics,
   - grouping by requirement type,
   - grouping by lifecycle status,
   - logical map: Type → Requirement IDs.
5. Export JSON for each generated component.
6. Repeat the workflow for additional components in the same session.
7. Export a single ZIP containing all generated component requirement instances.


## Deploy on Streamlit Community Cloud

This repository is now set up with the files Streamlit Cloud expects:
- `requirements.txt` (runtime + notebook/demo Python dependencies),
- `.streamlit/config.toml` (runtime/server settings).

Deployment steps:
1. Push this repository to GitHub.
2. In Streamlit Community Cloud, click **New app**.
3. Select your repo + branch.
4. Set the app entrypoint to: `src/streamlit_app.py`.
5. Deploy.

If you use LLM-related features later, add required API keys in Streamlit Cloud **Secrets** (do not commit `.env`).

Dependency notes:
- The app itself only needs Streamlit + standard-library modules from this repo.
- Additional packages in `requirements.txt` are included so hosted environments and demo/notebook workflows have the common data/validation stack available out of the box.

## Condition language (MVP)
Supported condition forms in `applicability.when`:
- `always`
- `key=value1|value2`
- `key>number`, `key>=number`, `key<number`, `key<=number`

Semantics:
- The list under `when` is **AND**.
- The `|` within `=` is **OR**.

## Quality gate (validation)
- The engine adds a `validation` section to the instance output.
- If `validation.error_count > 0`, `overall_status` is `fail`.
- Validation checks (MVP): verification presence, acceptance presence, placeholder tracking, and basic atomicity heuristics.

## Strict mode and reports
The CLI supports strict quality-gate behavior and optional validation reports.

### Generate instance + reports
```bash
python -m src.engine \
  --template "/path/to/primary_loop_valve_baseline_v0.2_150reqs.json" \
  --profile examples/valve_profile_example.json \
  --out examples/valve_requirements_instance.json \
  --report-json examples/validation_report.json \
  --report-csv examples/validation_report.csv
```

### Fail build if errors exist
```bash
python -m src.engine --template ... --profile ... --out ... --strict
```

### Fail build if warnings exist (or exceed a threshold)
```bash
python -m src.engine --template ... --profile ... --out ... --fail-on-warnings
python -m src.engine --template ... --profile ... --out ... --max-warnings 5
```

## Run tests
```bash
python -m unittest discover -s tests -v
```
