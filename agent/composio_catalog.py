"""C1: pull Composio's full toolkit catalog -> data/composio_catalog.json.
Run: python -m agent.composio_catalog

Why REST and not the SDK: with composio==0.34.0, `Composio().toolkits.get()` returned only the first
1,000 toolkits and exposed no cursor (tested 2026-11-23); the v3.1 REST endpoint paginates with
`next_cursor` and returned all 1,842. Same auth (project API key, header x-api-key)."""
import json

import httpx

from . import config as C

URL = "https://backend.composio.dev/api/v3.1/toolkits"


def fetch_all() -> list[dict]:
    items, cursor = [], None
    for _ in range(20):
        params = {"limit": 1000, **({"cursor": cursor} if cursor else {})}
        r = httpx.get(URL, headers={"x-api-key": C.COMPOSIO_KEY}, params=params, timeout=60)
        r.raise_for_status()
        d = r.json()
        items += d.get("items", [])
        cursor = d.get("next_cursor")
        if not cursor:
            break
    return items


def main():
    catalog = [{"slug": t.get("slug"), "name": t.get("name"), "toolkit_type": t.get("toolkit_type"),
                "auth_schemes": t.get("auth_schemes"), "composio_managed_auth_schemes": t.get("composio_managed_auth_schemes"),
                "no_auth": t.get("no_auth"), "tools_count": (t.get("meta") or {}).get("tools_count"),
                "app_url": (t.get("meta") or {}).get("app_url"),
                "categories": [c.get("name") if isinstance(c, dict) else c for c in (t.get("meta") or {}).get("categories") or []]}
               for t in fetch_all()]
    C.CATALOG_FILE.write_text(json.dumps(catalog, indent=1), encoding="utf-8")
    print(f"{len(catalog)} toolkits -> {C.CATALOG_FILE}")


if __name__ == "__main__":
    main()
