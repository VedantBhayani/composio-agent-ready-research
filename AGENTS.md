# AGENTS.md

Guide for an AI agent working in this repo.

## What this is
A research pipeline that answers, for 100 apps, "could this be an agent toolkit today?". It collects
auth methods, how developers get credentials, the approval needed to go live, the API surface, MCP servers
and Composio coverage. Every answer carries a fetched URL and a verbatim excerpt.

## Commands (Windows paths; use `python` from `.venv`)
```
python -m agent.smoke_test          # one real call per tool (needs .env)
python -m agent.composio_catalog    # refresh data/composio_catalog.json
python -m agent run [--app NAME]... [--limit N]   # pass 1 -> data/pass1.jsonl (resumes; skips done ids)
python -m agent verify              # loops L0-L4 -> data/pass2.jsonl + data/changes.jsonl (resumes)
python analysis/make_checklist.py   # blind human sheet (seed 42) -> data/checklist.csv
python analysis/score.py --apply    # accuracy from human answers -> data/accuracy.json, data/final.jsonl
python analysis/analyze.py          # patterns -> data/insights.json
python analysis/build_page.py       # output/index.html + data.json + records.csv + llms.txt
python -m pytest -q
```

## Rules you must keep
- `data/pass1.jsonl` is frozen after the run. Never edit it. Corrections go to pass2 or final.
- No evidence means Unknown. Never fill a field from model knowledge.
- Verdicts (buildability, archetype, blocker, confidence) come only from `agent/rules.py`. Change the rules and the tests together.
- Secrets live only in `.env` (gitignored). Never print or commit keys.
- Every number shown on the page must be computed from files in `data/`.

## Layout
- `agent/` holds the pipeline: sources, extract, composio_layer, rules, checks, verifier, browser.
- `analysis/` holds scoring, patterns and the page builder.
- `data/` holds the outputs, with `raw/` keeping the untouched provider responses.
- `cache/pages/` holds cached fetches, so re-runs make no network calls.
