"""Pass 1: search -> fetch -> extract -> Composio match -> rules. One app at a time per worker,
incremental writes after each app, resumable (apps already in pass1.jsonl are skipped)."""
import asyncio
import json
import time
import traceback

import httpx

from . import composio_layer, config as C, extract as X, rules
from .checks import excerpt_in_text
from .schema import AppRecord, Evidence
from .sources import is_dead, is_official, parallel_search, rank_urls, search_plan, tinyfish_fetch, trim

FIELD_EVIDENCE = {"auth_methods": "auth_evidence", "dev_access": "dev_access_evidence",
                  "prod_gate": "prod_gate_evidence", "public_api": "api_evidence", "mcp": "mcp_evidence"}


def load_apps():
    return json.loads(C.APPS_FILE.read_text(encoding="utf-8"))


def done_ids(path=C.PASS1) -> set[int]:
    if not path.exists():
        return set()
    return {json.loads(l)["app_id"] for l in path.read_text(encoding="utf-8").splitlines() if l.strip()}


def append_jsonl(path, obj):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def claim_text(field: str, value) -> str:
    if isinstance(value, list):
        value = ", ".join(value) if value else "Unknown"
    return f"{field} = {value}"


def build_sources(app, search, pages):
    """Fetched pages (TinyFish) + Parallel excerpts for official results we did not fetch."""
    srcs, fetched_urls = [], set()
    for u, p in pages.items():
        if p and not is_dead(p):
            srcs.append({"url": u, "title": p.get("title", ""), "text": p["text"], "trimmed": trim(p["text"]),
                         "via": "tinyfish", "retrieved_at": p["retrieved_at"]})
            fetched_urls.add(u)
    extra = 0
    for r in search.get("results", []):
        if r["url"] in fetched_urls or extra >= 3:
            continue
        if is_official(r["url"], app) or "mcp" in (r["url"] + (r.get("title") or "")).lower():
            txt = "\n".join(r.get("excerpts") or [])[:1800]
            if len(txt) > 200:
                srcs.append({"url": r["url"], "title": r.get("title") or "", "text": txt, "trimmed": txt,
                             "via": "parallel_index", "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
                extra += 1
    # global cap on prompt size
    total, kept = 0, []
    for s in srcs:
        if total + len(s["trimmed"]) > C.TRIM_CHARS_TOTAL:
            s["trimmed"] = s["trimmed"][: max(0, C.TRIM_CHARS_TOTAL - total)]
        if s["trimmed"]:
            kept.append(s)
            total += len(s["trimmed"])
    return kept


def to_record(app, ext, sources) -> AppRecord:
    by_url = {s["url"]: s for s in sources}
    r = AppRecord(app_id=app["id"], app_name=app["name"], category=app["category"])
    r.description = ext.description
    r.official_docs_url = ext.official_docs_url if ext.official_docs_url in by_url else (
        ext.official_docs_url if ext.official_docs_url and is_official(ext.official_docs_url, app) else None)
    r.auth_methods, r.auth_notes = list(dict.fromkeys(ext.auth_methods)), ext.auth_notes
    r.dev_access, r.prod_gate, r.public_api = ext.dev_access, ext.prod_gate, ext.public_api
    r.api_type, r.api_breadth, r.mcp, r.mcp_urls = ext.api_type, ext.api_breadth, ext.mcp, ext.mcp_urls
    r.blocker_note = ext.blocker_note
    values = {"auth_methods": r.auth_methods, "dev_access": r.dev_access, "prod_gate": r.prod_gate,
              "public_api": f"{r.public_api} ({r.api_type}, {r.api_breadth})", "mcp": r.mcp}
    for field, evfield in FIELD_EVIDENCE.items():
        for ev in getattr(ext, evfield):
            src = by_url.get(ev.url)
            r.evidence.append(Evidence(
                claim_field=field, claim=claim_text(field, values[field]), source_url=ev.url,
                source_title=src["title"] if src else "", supporting_excerpt=ev.excerpt,
                source_type="official" if is_official(ev.url, app) else "third-party",
                retrieved_at=src["retrieved_at"] if src else "", fetched_via=src["via"] if src else "none",
                excerpt_match=bool(src) and excerpt_in_text(ev.excerpt, src["text"])))
    return r


async def research_app(app, http: httpx.AsyncClient) -> dict:
    t0 = time.time()
    cost = {"parallel_usd": 0.0, "mistral_usd": 0.0, "tinyfish_fetches": 0}
    queries, objective = search_plan(app)
    search = await parallel_search(http, app, queries, objective)
    cost["parallel_usd"] += C.PRICE_PARALLEL_FAST
    urls = rank_urls(app, search.get("results", []))
    pages, n_fetch = await tinyfish_fetch(http, urls)
    cost["tinyfish_fetches"] += n_fetch
    sources = build_sources(app, search, pages)
    ext, raw_ext, usage = await X.extract(app, sources)
    cost["mistral_usd"] += usage["usd"]
    rec = to_record(app, ext, sources)
    rec.composio_toolkit = composio_layer.match(app)
    rules.apply(rec)
    rec.last_verified = time.strftime("%Y-%m-%d")
    rec.trace = {"queries": queries, "search_results": [r["url"] for r in search.get("results", [])],
                 "urls_fetched": urls,
                 "dead_or_failed": [u for u, p in pages.items() if not p or is_dead(p)],
                 "sources_used": [{"url": s["url"], "via": s["via"]} for s in sources],
                 "excerpt_match_rate": (round(sum(bool(e.excerpt_match) for e in rec.evidence) / len(rec.evidence), 2)
                                        if rec.evidence else None),
                 "loops_run": ["pass1"], "seconds": round(time.time() - t0, 1), "cost": cost, "usage": [usage]}
    raw = {"app": app, "search": search, "extraction_raw": raw_ext, "extraction": ext.model_dump(),
           "sources": [{k: v for k, v in s.items() if k != "text"} for s in sources]}
    (C.RAW / f"{app['id']:03d}.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec.model_dump()


async def run(app_filter=None, limit=None, out=C.PASS1):
    apps = load_apps()
    if app_filter:
        wanted = {a.lower() for a in app_filter}
        apps = [a for a in apps if a["name"].lower() in wanted or str(a["id"]) in wanted]
    skip = done_ids(out)
    apps = [a for a in apps if a["id"] not in skip][: limit or None]
    print(f"to research: {len(apps)} (already done: {len(skip)})")
    sem = asyncio.Semaphore(C.CONCURRENCY)
    lock = asyncio.Lock()

    async with httpx.AsyncClient() as http:
        async def one(app):
            async with sem:
                try:
                    rec = await research_app(app, http)
                    async with lock:
                        append_jsonl(out, rec)
                        append_jsonl(C.RUN_LOG, {"app_id": app["id"], "app": app["name"], "ok": True,
                                                 **rec["trace"]["cost"], "seconds": rec["trace"]["seconds"]})
                    print(f"  ok  {app['id']:3d} {app['name']:<28} {rec['buildability']:<8} {rec['archetype']:<18} "
                          f"{rec['trace']['seconds']}s ${rec['trace']['cost']['mistral_usd']+rec['trace']['cost']['parallel_usd']:.4f}")
                except Exception as e:
                    async with lock:
                        append_jsonl(C.RUN_LOG, {"app_id": app["id"], "app": app["name"], "ok": False,
                                                 "error": f"{type(e).__name__}: {e}"[:500],
                                                 "tb": traceback.format_exc()[-1500:]})
                    print(f"  ERR {app['id']:3d} {app['name']}: {type(e).__name__}: {str(e)[:200]}")
        await asyncio.gather(*(one(a) for a in apps))
