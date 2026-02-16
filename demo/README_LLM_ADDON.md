# LLM Add-on Demo

This add-on provides an interactive chat CLI that can:
- collect ValveProfile fields (manual or LLM-assisted)
- show the current profile (/show)
- run deterministic requirements generation (/run)
- build a portable output package (manifest + instance + reports)
- answer developer questions grounded on the repo code (/ask ...)

## How to use

Copy these NEW files into your repository (repo_root/src). Do NOT overwrite your existing src/__init__.py:
- code_rag.py
- profile_builder.py
- llm_client.py
- agent.py
- chat_cli.py

Then run from repo root:

```bash
python -m src.chat_cli
```

## LLM configuration (optional)

### Ollama
```bash
export LLM_MODE=ollama
export OLLAMA_MODEL=llama3.1
# optional: export OLLAMA_BASE_URL=http://localhost:11434
python -m src.chat_cli
```

### OpenAI-compatible endpoint
```bash
export LLM_MODE=openai_compat
export LLM_BASE_URL=http://localhost:8000
export LLM_API_KEY=...
export LLM_MODEL=...
python -m src.chat_cli
```

Without LLM configuration, the CLI runs in manual mode and prompts for missing required fields.
