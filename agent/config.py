"""Paths, model names, limits and prices. Prices are from the providers' pricing pages (read 2026-11-23)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
RAW = DATA / "raw"
CACHE = ROOT / "cache" / "pages"
OUTPUT = ROOT / "output"
for p in (DATA, RAW, CACHE, OUTPUT):
    p.mkdir(parents=True, exist_ok=True)

APPS_FILE = ROOT / "input" / "applications.json"
CATALOG_FILE = DATA / "composio_catalog.json"
PASS1 = DATA / "pass1.jsonl"
PASS2 = DATA / "pass2.jsonl"
FINAL = DATA / "final.jsonl"
CHANGES = DATA / "changes.jsonl"
RUN_LOG = DATA / "run_log.jsonl"

PARALLEL_KEY = os.getenv("PARALLEL_API_KEY", "")
TINYFISH_KEY = os.getenv("TINYFISH_API_KEY", "")
MISTRAL_KEY = os.getenv("MISTRAL_API_KEY", "")
COMPOSIO_KEY = os.getenv("COMPOSIO_API_KEY", "")

EXTRACT_MODEL = "mistral-small-latest"   # fast, cheap, good at schema-following
# Judge: we tried mistral-large-latest (a reasoning model) first; on this key it timed out (>60 s per call,
# 2026-11-23 ~19:55 IST), so the judge runs on mistral-small with a separate strict entailment prompt.
# Limitation (stated on the page): same model family as the extractor -> less independent than intended.
JUDGE_MODEL = "mistral-small-latest"
LARGE_MODEL = "mistral-large-latest"
HTTP_TIMEOUT_MS = 60000

CONCURRENCY = 5            # apps in flight; Mistral limit is 100 req/min, 100k tokens/min on this key
MAX_FETCH_PER_APP = 4      # TinyFish free allowance is 1,000 URLs/day
TRIM_CHARS_PER_PAGE = 4000
TRIM_CHARS_TOTAL = 14000

# USD
PRICE_PARALLEL_FAST = 0.001                      # per request (10 results)
PRICE_MISTRAL = {EXTRACT_MODEL: (0.15, 0.60),    # per 1M tokens (input, output)
                 LARGE_MODEL: (0.70, 2.10)}
