"""Composio catalog (C1) and auth-scheme cross-check source (C2).
Catalog pulled once from GET https://backend.composio.dev/api/v3.1/toolkits (see agent/smoke_test.py)."""
import json
import re
from functools import lru_cache

from . import config as C
from .schema import ComposioToolkit
from .sources import reg_domain


def norm(s: str) -> str:
    s = s.lower().split("(")[0]
    return re.sub(r"[^a-z0-9]", "", s)


@lru_cache
def catalog() -> list[dict]:
    return json.loads(C.CATALOG_FILE.read_text(encoding="utf-8"))


# Reviewed aliases where names differ. Each was confirmed by listing the toolkit's tools
# (GET /api/v3.1/tools?toolkit_slug=...), e.g. 'zoho' exposes ZOHO_CONVERT_ZOHO_LEAD (CRM),
# 'mongodb' exposes Atlas admin tools (MONGODB_ADD_GROUP_API_KEY). Logged in human_log.md.
ALIASES = {"Zoho CRM": "zoho", "WhatsApp Business": "whatsapp", "GoHighLevel": "highlevel_location",
           "MongoDB Atlas": "mongodb", "Netlify": "netlify_mcp", "Otter AI": "otter_ai_mcp"}
# Not matched on purpose: 'Salesforce Commerce Cloud' (salesforce toolkit = CRM), 'Mermaid CLI'
# (mermaid_chart_mcp is the Mermaid Chart SaaS), 'Amazon Selling Partner' ('amazon' has 0 tools).
SHARED_DOMAINS = {"zoho.com", "facebook.com", "salesforce.com", "google.com", "microsoft.com", "adobe.com",
                  "amazon.com", "github.com"}


def match(app: dict) -> ComposioToolkit:
    """Exact normalized name/slug match, then reviewed alias, then domain match (only for single-product
    domains). No fuzzy guessing: a wrong 'exists' would corrupt the quick-wins list."""
    names = {norm(app["name"])}
    raw = app["name"]
    if "(" in raw:  # 'Lark (Larksuite)' -> also 'larksuite'
        names.add(norm(raw.split("(")[1]))
    hits = [t for t in catalog() if norm(t.get("name") or "") in names or norm(t.get("slug") or "") in names]
    method = "name"
    if not hits and raw in ALIASES:
        hits = [t for t in catalog() if t["slug"] == ALIASES[raw]]
        method = "alias"
    if not hits:
        doms = {reg_domain(u) for u in app.get("seed_urls", [])} - SHARED_DOMAINS
        hits = [t for t in catalog() if t.get("app_url") and reg_domain(t["app_url"]) in doms]
        method = "domain"
    hits = [t for t in hits if (t.get("tools_count") or 0) > 0]
    if not hits:
        return ComposioToolkit(exists=False)
    best = max(hits, key=lambda t: t.get("tools_count") or 0)
    return ComposioToolkit(exists=True, slug=best["slug"], name=best["name"], tool_count=best.get("tools_count"),
                           auth_schemes=best.get("auth_schemes") or [], match_method=method)


# Composio scheme -> our AuthMethod vocabulary
SCHEME_MAP = {"OAUTH2": "OAuth2", "OAUTH1": "OAuth2", "API_KEY": "API key", "BASIC": "Basic",
              "BASIC_WITH_JWT": "Basic", "BEARER_TOKEN": "Token", "BILLCOM_AUTH": "Other",
              "GOOGLE_SERVICE_ACCOUNT": "Other", "NO_AUTH": "Other", "CALCOM_AUTH": "Other"}


def composio_auth(tk: ComposioToolkit) -> set[str]:
    return {SCHEME_MAP.get(s, "Other") for s in tk.auth_schemes}
