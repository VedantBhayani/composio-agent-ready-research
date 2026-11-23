"""Mistral structured extraction (pass 1). Uses ONLY the fetched source text given in the prompt."""
import asyncio
import json

from mistralai.client import Mistral

from . import config as C
from .schema import Extraction

_client = None

SYSTEM = """You research software apps for an AI-agent integration team.
Use ONLY the SOURCES provided. Never use outside knowledge. Never invent URLs.
Rules:
- Every non-Unknown answer must have at least one evidence item: the SOURCE url exactly as given and a VERBATIM excerpt copied from that source's text.
- If the sources do not state something, answer Unknown (or empty list / 'None found' for MCP). Missing evidence is not proof of absence.
- auth_methods: OAuth2, API key, Basic, Token (bearer/personal access tokens that are not API keys), Other.
- dev_access = how a developer gets API credentials to START: Free self-serve (anyone can sign up / free account / free developer sandbox), Free trial, Paid plan (API only on paid, Pro, Business or Enterprise tiers), Approval required (must apply / be vetted / an admin or the vendor must approve before getting access), Partner or contact sales (partner program, contact sales, request access form).
  If the API is limited to Enterprise or paid plans, that is Paid plan, NOT Free self-serve, even if signing in is free.
- prod_gate = extra approval to go LIVE or publish an app for other users: App review (app review, verification, security review, developer token approval, tiered vetting), Partner program, None (sources explicitly say no approval is needed), Unknown (sources say nothing about it — the usual case).
- Evidence must DIRECTLY state the value. A sentence that is merely on the same page does not count. If no sentence directly states it, answer Unknown with no evidence.
- A paid API is still a public API. An API does not imply an MCP server.
- mcp: Official only if the vendor itself provides/documents it; Community if a third-party MCP server is shown in a source.
- Excerpts: copy exact text, one or two sentences, max 300 characters, no paraphrase."""


def client() -> Mistral:
    global _client
    if _client is None:
        _client = Mistral(api_key=C.MISTRAL_KEY, timeout_ms=C.HTTP_TIMEOUT_MS)
    return _client


def build_prompt(app: dict, sources: list[dict]) -> str:
    parts = [f"APP: {app['name']}  | category: {app['category']} | hint from brief: {app.get('hint_raw')}\n"]
    for i, s in enumerate(sources, 1):
        parts.append(f"=== SOURCE {i} ===\nurl: {s['url']}\ntitle: {s.get('title','')}\ntext:\n{s['trimmed']}\n")
    return "\n".join(parts)


def _call(model: str, messages: list, response_format, max_tokens: int):
    kw = dict(model=model, messages=messages, response_format=response_format, max_tokens=max_tokens, temperature=0)
    if model == C.LARGE_MODEL:
        kw["top_p"] = 1  # required by the API with greedy sampling on this model
    return client().chat.parse(**kw)


async def parse(model: str, messages: list, response_format, max_tokens: int = 3000, tries: int = 4):
    """Run the sync SDK call in a thread; back off on rate limits (429) and transient errors."""
    for i in range(tries):
        try:
            resp = await asyncio.to_thread(_call, model, messages, response_format, max_tokens)
            u = resp.usage
            cost = (u.prompt_tokens * C.PRICE_MISTRAL[model][0] + u.completion_tokens * C.PRICE_MISTRAL[model][1]) / 1e6
            msg = resp.choices[0].message
            parsed = msg.parsed
            raw = msg.content if isinstance(msg.content, str) else str(msg.content)
            if parsed is None:  # last resort: try to parse JSON text
                parsed = response_format.model_validate_json(raw)
            return parsed, raw, {"model": model, "in": u.prompt_tokens, "out": u.completion_tokens, "usd": cost}
        except Exception as e:
            if i == tries - 1:
                raise
            wait = 20 if "429" in str(e) else 3 * (2 ** i)
            await asyncio.sleep(wait)


async def extract(app: dict, sources: list[dict]):
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": build_prompt(app, sources)}]
    return await parse(C.EXTRACT_MODEL, messages, Extraction, max_tokens=3000)
