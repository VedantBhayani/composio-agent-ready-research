"""Finding and fetching sources: Parallel search -> rank -> TinyFish fetch (disk-cached) -> trim."""
import asyncio
import hashlib
import json
import re
import time
from urllib.parse import urlparse

import httpx

from . import config as C

KEYWORDS = ["oauth", "api key", "api-key", "apikey", "authenticat", "authoriz", "access token", "bearer",
            "personal access token", "client id", "client secret", "basic auth", "pricing", "plan",
            "free", "trial", "partner", "app review", "review process", "approval", "apply", "developer token",
            "sandbox", "rate limit", "mcp", "model context protocol", "rest api", "graphql", "endpoint", "sdk"]
URL_HINTS = ["auth", "oauth", "api-key", "keys", "token", "developer", "docs", "api", "mcp", "pricing", "getting-started"]


async def retry(fn, *args, tries=3, base=2.0, **kw):
    for i in range(tries):
        try:
            return await fn(*args, **kw)
        except Exception:
            if i == tries - 1:
                raise
            await asyncio.sleep(base * (2 ** i))


def reg_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com") and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def official_domains(app: dict) -> set[str]:
    doms = {reg_domain(u) for u in app.get("seed_urls", [])}
    doms.discard("github.com")  # github repos are official only via exact repo path (handled in is_official)
    return doms


def is_official(url: str, app: dict) -> bool:
    for s in app.get("seed_urls", []):
        if "github.com" in s and url.lower().startswith(s.lower()):
            return True
    if reg_domain(url) in official_domains(app):
        return True
    token = re.sub(r"[^a-z0-9]", "", app["name"].lower().split("(")[0])[:8]
    host = (urlparse(url).hostname or "").replace("-", "").replace(".", "")
    return len(token) >= 4 and token in host and "github" not in host and "medium" not in host


# ---------------- Parallel search ----------------
async def parallel_search(client: httpx.AsyncClient, app: dict, queries: list[str], objective: str) -> dict:
    body = {"objective": objective, "search_queries": queries, "mode": "fast",
            "advanced_settings": {"max_results": 10}}

    async def call():
        r = await client.post("https://api.parallel.ai/v1/search", headers={"x-api-key": C.PARALLEL_KEY},
                              json=body, timeout=60)
        r.raise_for_status()
        return r.json()
    return await retry(call)


def search_plan(app: dict) -> tuple[list[str], str]:
    n = app["name"].split("(")[0].strip()
    hint = f" (website: {app['hint_raw']})" if app.get("hint_raw") else ""
    objective = (f"Official developer documentation for {n}{hint}: how API requests are authenticated "
                 f"(OAuth2, API key, token), how a developer gets API credentials (free, trial, paid plan, "
                 f"partner program, app review), the API reference, and any official or community MCP server.")
    queries = [f"{n} API authentication", f"{n} API key OAuth developer access", f"{n} MCP server"]
    return queries, objective


def rank_urls(app: dict, results: list[dict]) -> list[str]:
    """Seeds first, then official results by keyword score, then best MCP page (may be third-party)."""
    chosen: list[str] = []
    for s in app.get("seed_urls", [])[:2]:
        chosen.append(s)

    def score(r):
        u = r["url"].lower()
        txt = (" ".join(r.get("excerpts") or []) + " " + (r.get("title") or "")).lower()
        return sum(h in u for h in URL_HINTS) * 2 + sum(k in txt for k in KEYWORDS)

    official = sorted([r for r in results if is_official(r["url"], app)], key=score, reverse=True)
    for r in official:
        if len(chosen) >= C.MAX_FETCH_PER_APP - 1:
            break
        if r["url"] not in chosen:
            chosen.append(r["url"])
    mcp = [r for r in results if "mcp" in (r["url"] + (r.get("title") or "")).lower() and r["url"] not in chosen]
    mcp.sort(key=lambda r: (not is_official(r["url"], app), -score(r)))
    if mcp:
        chosen.append(mcp[0]["url"])
    return chosen[:C.MAX_FETCH_PER_APP]


# ---------------- TinyFish fetch (cached) ----------------
def _cache_path(url: str):
    return C.CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".json")


def cached(url: str):
    p = _cache_path(url)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


async def tinyfish_fetch(client: httpx.AsyncClient, urls: list[str]) -> tuple[dict, int]:
    """Returns ({url: page}, n_network_fetches). Page = {url, final_url, title, text, error, retrieved_at}."""
    out, todo = {}, []
    for u in urls:
        c = cached(u)
        if c is not None:
            out[u] = c
        else:
            todo.append(u)
    if not todo:
        return out, 0

    async def call():
        r = await client.post("https://api.fetch.tinyfish.ai", headers={"X-API-Key": C.TINYFISH_KEY},
                              json={"urls": todo, "format": "markdown", "per_url_timeout_ms": 60000}, timeout=150)
        r.raise_for_status()
        return r.json()
    d = await retry(call)
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    for res in d.get("results", []):
        page = {"url": res.get("url"), "final_url": res.get("final_url"), "title": res.get("title") or "",
                "text": res.get("text") or "", "error": None, "retrieved_at": now, "fetched_via": "tinyfish"}
        out[res.get("url")] = page
    for err in d.get("errors", []):
        out[err.get("url")] = {"url": err.get("url"), "final_url": None, "title": "", "text": "",
                               "error": err.get("error"), "retrieved_at": now, "fetched_via": "tinyfish"}
    for u in todo:
        if u in out:
            _cache_path(u).write_text(json.dumps(out[u]), encoding="utf-8")
    return out, len(todo)


def is_dead(page: dict) -> bool:
    t = (page.get("text") or "").lower()
    return bool(page.get("error")) or len(t) < 300 or "workspace does not exist" in t or "page not found" in t[:400]


# ---------------- trim ----------------
def trim(text: str, per_page: int = C.TRIM_CHARS_PER_PAGE) -> str:
    """Keep the intro + windows around auth/access/MCP keywords, merged, capped."""
    if len(text) <= per_page:
        return text
    low = text.lower()
    spans = [(0, 600)]
    for k in KEYWORDS:
        for m in re.finditer(re.escape(k), low):
            spans.append((max(0, m.start() - 350), min(len(text), m.end() + 450)))
    spans.sort()
    merged = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    # prefer windows with more keyword hits
    def hits(se):
        seg = low[se[0]:se[1]]
        return sum(seg.count(k) for k in KEYWORDS)
    keep = [merged[0]] + sorted(merged[1:], key=hits, reverse=True)
    out, total = [], 0
    for s, e in keep:
        if total >= per_page:
            break
        seg = text[s:e]
        out.append((s, seg[: per_page - total]))
        total += len(seg)
    out.sort()
    return "\n...\n".join(seg for _, seg in out)
