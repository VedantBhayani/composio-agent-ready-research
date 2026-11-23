"""S1 smoke test: one minimal real call per tool. Never prints secrets.
Run: .venv\\Scripts\\python -m agent.smoke_test
"""
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
OUT = {}


def key(name):
    v = os.getenv(name, "").strip()
    return v or None


def parallel():
    k = key("PARALLEL_API_KEY")
    if not k:
        return "MISSING KEY"
    body = {"objective": "Find Stripe's official docs on API authentication and API keys",
            "search_queries": ["Stripe API authentication", "Stripe API keys docs"],
            "mode": "fast", "advanced_settings": {"max_results": 5}}
    t = time.time()
    r = httpx.post("https://api.parallel.ai/v1/search", headers={"x-api-key": k}, json=body, timeout=60)
    d = r.json()
    return {"status": r.status_code, "secs": round(time.time() - t, 2),
            "n_results": len(d.get("results", [])), "urls": [x["url"] for x in d.get("results", [])],
            "usage": d.get("usage"), "warnings": d.get("warnings"), "error": d.get("error")}


def tinyfish_fetch():
    k = key("TINYFISH_API_KEY")
    if not k:
        return "MISSING KEY"
    urls = ["https://docs.stripe.com/keys", "https://highlevel.stoplight.io/"]
    t = time.time()
    r = httpx.post("https://api.fetch.tinyfish.ai", headers={"X-API-Key": k},
                   json={"urls": urls, "format": "markdown"}, timeout=150)
    d = r.json()
    return {"status": r.status_code, "secs": round(time.time() - t, 2),
            "results": [{"url": x.get("url"), "final_url": x.get("final_url"), "title": x.get("title"),
                         "chars": len(x.get("text") or ""), "head": (x.get("text") or "")[:160]}
                        for x in d.get("results", [])],
            "errors": d.get("errors"), "rate_headers": {h: v for h, v in r.headers.items() if "limit" in h.lower()}}


def tinyfish_search():
    k = key("TINYFISH_API_KEY")
    if not k:
        return "MISSING KEY"
    r = httpx.get("https://api.search.tinyfish.ai", headers={"X-API-Key": k},
                  params={"query": "Otter.ai MCP server"}, timeout=60)
    d = r.json()
    return {"status": r.status_code, "n": len(d.get("results", [])),
            "top": [(x.get("title"), x.get("url")) for x in d.get("results", [])[:5]]}


def mistral():
    k = key("MISTRAL_API_KEY")
    if not k:
        return "MISSING KEY"
    from pydantic import BaseModel
    try:
        from mistralai.client import Mistral  # path shown in current docs
        imp = "mistralai.client"
    except ImportError:
        from mistralai import Mistral
        imp = "mistralai"

    class Probe(BaseModel):
        auth_methods: list[str]
        excerpt: str

    client = Mistral(api_key=k)
    out = {"import": imp}
    for model in ["mistral-small-latest", "mistral-large-latest"]:
        t = time.time()
        try:
            resp = client.chat.parse(
                model=model, temperature=0, max_tokens=200, response_format=Probe,
                messages=[{"role": "system", "content": "Extract from the text only."},
                          {"role": "user", "content": "Stripe authenticates API requests using your account's API keys. Use OAuth for Connect platforms."}])
            msg = resp.choices[0].message
            out[model] = {"secs": round(time.time() - t, 2), "content": msg.content,
                          "parsed_attr": type(getattr(msg, "parsed", None)).__name__,
                          "usage": resp.usage.model_dump() if resp.usage else None}
        except Exception as e:  # report, don't hide
            out[model] = {"error": f"{type(e).__name__}: {e}"[:400]}
    # raw call to read rate-limit headers
    r = httpx.post("https://api.mistral.ai/v1/chat/completions", headers={"Authorization": f"Bearer {k}"},
                   json={"model": "mistral-small-latest", "max_tokens": 5,
                         "messages": [{"role": "user", "content": "hi"}]}, timeout=60)
    out["rate_headers"] = {h: v for h, v in r.headers.items() if "ratelimit" in h.lower() or "limit" in h.lower()}
    return out


def composio():
    k = key("COMPOSIO_API_KEY")
    if not k:
        return "MISSING KEY"
    items, cursor, pages = [], None, 0
    while True:
        params = {"limit": 1000}
        if cursor:
            params["cursor"] = cursor
        r = httpx.get("https://backend.composio.dev/api/v3.1/toolkits", headers={"x-api-key": k},
                      params=params, timeout=60)
        if r.status_code != 200:
            return {"status": r.status_code, "body": r.text[:400]}
        d = r.json()
        items += d.get("items", [])
        pages += 1
        cursor = d.get("next_cursor")
        if not cursor or pages > 20:
            break
    catalog = [{"slug": t.get("slug"), "name": t.get("name"), "toolkit_type": t.get("toolkit_type"),
                "auth_schemes": t.get("auth_schemes"),
                "composio_managed_auth_schemes": t.get("composio_managed_auth_schemes"),
                "no_auth": t.get("no_auth"), "deprecated": t.get("deprecated"),
                "tools_count": (t.get("meta") or {}).get("tools_count"),
                "app_url": (t.get("meta") or {}).get("app_url"),
                "categories": [c.get("name") if isinstance(c, dict) else c for c in (t.get("meta") or {}).get("categories") or []]}
               for t in items]
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "composio_catalog.json").write_text(json.dumps(catalog, indent=1), encoding="utf-8")
    with_auth = sum(1 for c in catalog if c["auth_schemes"])
    sample = [c for c in catalog if c["slug"] in ("stripe", "hubspot", "linear", "otter", "devin")]
    return {"pages": pages, "toolkits": len(catalog), "with_auth_schemes": with_auth, "sample": sample}


if __name__ == "__main__":
    for name, fn in [("parallel", parallel), ("tinyfish_fetch", tinyfish_fetch),
                     ("tinyfish_search", tinyfish_search), ("mistral", mistral), ("composio", composio)]:
        try:
            OUT[name] = fn()
        except Exception as e:
            OUT[name] = {"error": f"{type(e).__name__}: {e}"[:400]}
        print(f"\n=== {name} ===\n{json.dumps(OUT[name], indent=1, default=str)[:2500]}")
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "smoke_test.json").write_text(json.dumps(OUT, indent=1, default=str), encoding="utf-8")
