# Requirements Agent MVP (Valve)

This starter kit turns the **150-item primary-loop valve requirements library** into a deterministic pipeline:

1. **ValveProfile** (input): a flat JSON with fields like `actuation_type`, `seismic_category`, etc.
2. **Filter**: evaluates `applicability.when` conditions (AND semantics; `|` means OR).
3. **Instantiate**: substitutes `{{param}}` placeholders from the ValveProfile.
4. **Output**: a `ValveRequirementsInstance` JSON with applicable + non-applicable requirements and TBD tracking.

## Files
- `schemas/valve_profile.schema.json`
- `schemas/valve_requirements_instance.schema.json`
- `src/engine.py` (filter + instantiate + CLI)
- `examples/` (sample profile and generated output)

## Quick start (CLI)
```bash
python -m src.engine --template "data/primary_loop_valve_baseline_v0.2_150reqs.json" --profile examples/valve_profile_example.json --out examples/valve_requirements_instance.json
```

## Condition language (MVP)
Supported condition forms in `applicability.when`:
- `always`
- `key=value1|value2`
- `key>number`, `key>=number`, `key<number`, `key<=number`

Semantics:
- The list under `when` is **AND**.
- The `|` within `=` is **OR**.

## Next step
Once this deterministic stage is stable, add:
- standards clause database ingestion (clause-tree + embeddings)
- requirement-to-clause trace mapping
- LLM enrichment for parameters / acceptance criteria / gap detection


## Quality gate (validation)
- The engine adds a `validation` section to the instance output.
- If `validation.error_count > 0`, `overall_status` is `fail`.
- Validation checks (MVP): verification presence, acceptance presence, placeholder tracking, and basic atomicity heuristics.


## Run tests
```bash
python -m unittest discover -s tests -v
```


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
