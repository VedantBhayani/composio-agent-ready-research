"""L4 browser-use loop: TinyFish browser agent navigates the official docs like a person and returns quotes
+ the URL each came from. Every quote is then checked deterministically (we fetch that URL ourselves and
require the quote to appear in it) before it can count. Runs on the 15 audit-sample apps. ~$0.016/step.
Uses run-async + polling (the synchronous /run endpoint hit client read timeouts on long runs)."""
import asyncio
import time

import httpx

from . import config as C

BASE = "https://agent.tinyfish.ai/v1"
GOAL = ("You are checking the developer documentation of {app}. Find: (1) how API requests are authenticated "
        "(OAuth2, API key, Basic, token); (2) how a developer gets API credentials (free sign-up, free trial, "
        "paid plan only, must apply/be approved, partner program / contact sales); (3) whether publishing an "
        "app for other users needs app review or partner approval; (4) whether the vendor offers an official "
        "MCP server. For every answer give a short verbatim quote and the exact page URL it appears on. "
        "Be quick: visit at most 4 pages.")

SCHEMA = {"type": "object", "properties": {
    "auth_methods": {"type": "array", "items": {"type": "string"}},
    "dev_access": {"type": "string"}, "prod_gate": {"type": "string"}, "mcp": {"type": "string"},
    "quotes": {"type": "array", "items": {"type": "object", "properties": {
        "field": {"type": "string", "enum": ["auth_methods", "dev_access", "prod_gate", "mcp"]},
        "url": {"type": "string"}, "quote": {"type": "string"}}}}}}


async def run_agent(http: httpx.AsyncClient, app_name: str, start_url: str, max_wait: int = 600) -> dict:
    t = time.time()
    h = {"X-API-Key": C.TINYFISH_KEY}
    body = {"url": start_url, "goal": GOAL.format(app=app_name), "output_schema": SCHEMA,
            "agent_config": {"max_duration_seconds": 120}}
    r = await http.post(f"{BASE}/automation/run-async", headers=h, json=body, timeout=30)
    run_id = r.json().get("run_id")
    if not run_id:
        return {"status": "FAILED", "steps": 0, "usd": 0, "seconds": 0, "result": None, "error": r.text[:200]}
    d = {}
    while time.time() - t < max_wait:
        await asyncio.sleep(6)
        d = (await http.get(f"{BASE}/runs/{run_id}", headers=h, timeout=30)).json()
        if d.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
            break
    else:
        await http.post(f"{BASE}/runs/{run_id}/cancel", headers=h, timeout=30)
        d["status"] = "TIMEOUT_CANCELLED"
    steps = d.get("num_of_steps") or 0
    return {"status": d.get("status"), "steps": steps, "usd": round(steps * 0.016, 3),
            "seconds": round(time.time() - t, 1), "result": d.get("result"), "error": d.get("error")}
