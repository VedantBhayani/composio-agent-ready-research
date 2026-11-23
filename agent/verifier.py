"""Pass 2: automated verification loops over pass1 (pass1 itself is never modified).
L0 deterministic  : evidence URL was fetched + excerpt really appears in it; otherwise evidence dropped.
L1 agent judge    : a different, stronger model (Mistral Large) checks each claim against its excerpts.
L2 Composio check : our auth methods vs the auth schemes of Composio's toolkit (independent source).
L3 agentic re-pass: a tool-calling agent (search/fetch) re-researches only fields that failed L0/L1/L2.
L4 browser        : TinyFish browser agent on official docs for sampled / unreadable apps (see browser.py).
After the loops, any field with no surviving evidence becomes Unknown, and verdicts are recomputed.
Every change is written to data/changes.jsonl (field, old -> new, loop, reason)."""
import asyncio
import json
import time
from typing import Literal

import httpx
from pydantic import BaseModel

from . import composio_layer, config as C, rules
from .checks import excerpt_in_text
from .extract import parse
from .pipeline import append_jsonl, done_ids, load_apps
from .schema import AppRecord, Ev, Evidence
from .sources import cached, is_dead, is_official, tinyfish_fetch

FIELDS = ["auth_methods", "dev_access", "prod_gate", "public_api", "mcp"]
UNKNOWN = {"auth_methods": [], "dev_access": "Unknown", "prod_gate": "Unknown", "public_api": "unknown",
           "mcp": "Unknown"}


# ---------------- helpers ----------------
def value_of(r: AppRecord, f: str):
    return r.auth_methods if f == "auth_methods" else getattr(r, f)


def set_value(r: AppRecord, f: str, v, loop: str, reason: str, changes: list):
    old = value_of(r, f)
    if old == v:
        return
    if f == "auth_methods":
        r.auth_methods = list(v)
    else:
        setattr(r, f, v)
    if f == "public_api" and v == "unknown":
        r.api_type, r.api_breadth = "Unknown", "Unknown"
    changes.append({"app_id": r.app_id, "app": r.app_name, "field": f, "old": old, "new": v,
                    "loop": loop, "reason": reason[:300]})


def is_unknown(r, f):
    return value_of(r, f) in ([], "Unknown", "unknown")


def page_text(url: str) -> str | None:
    p = cached(url)
    if p and not is_dead(p):
        return p["text"]
    return None


# ---------------- L0 ----------------
def l0(r: AppRecord, raw_sources: dict) -> list[str]:
    """Return fields whose evidence did not survive. Parallel-index excerpts are checked against the
    excerpt text Parallel returned (stored in raw)."""
    failed = []
    for e in r.evidence:
        txt = page_text(e.source_url) or raw_sources.get(e.source_url)
        e.excerpt_match = bool(txt) and excerpt_in_text(e.supporting_excerpt, txt)
        if not e.excerpt_match:
            e.verifier = "unsupported"
    for f in FIELDS:
        if f == "mcp" and r.mcp == "None found":
            continue  # absence claim: nothing to quote (reported as 'none found', never 'none')
        if not is_unknown(r, f) and not any(e.claim_field == f and e.excerpt_match for e in r.evidence):
            failed.append(f)
    return failed


# ---------------- L1 ----------------
class Verdict(BaseModel):
    field: str
    verdict: Literal["supported", "unsupported", "partially"]
    corrected_value: str
    reason: str


class Judgement(BaseModel):
    verdicts: list[Verdict]


JUDGE_SYS = """You are a strict fact-checker for an API research dataset.
For each CLAIM you get the excerpts quoted as evidence. Decide ONLY from those excerpts:
- supported: the excerpts directly state the claimed value.
- partially: the excerpts support part of it (e.g. one of two auth methods) â€” put the value the excerpts DO support in corrected_value.
- unsupported: the excerpts do not state it (or contradict it) â€” put the value the excerpts imply in corrected_value, or 'Unknown'.
Allowed values: auth_methods = list from OAuth2, API key, Basic, Token, Other (comma-separated);
dev_access = Free self-serve | Free trial | Paid plan | Approval required | Partner or contact sales | Unknown;
prod_gate = None | App review | Partner program | Unknown; public_api = yes | no | unknown;
mcp = Official | Community | Both | None found | Unknown.
Rules: paid API is still a public API; prod_gate 'None' needs an excerpt saying no approval is needed; an API on Enterprise/paid tiers only is 'Paid plan'.
dev_access 'Free self-serve' is supported when the excerpts show a developer can create the credentials themselves (e.g. generate an API key / personal access token / register an app in their account or developer portal) AND either a free plan/free account/free developer sandbox exists or nothing says a paid plan is required. Explicit 'free' wording is not mandatory if self-service creation is shown and no paywall is mentioned."""


async def l1(r: AppRecord, only: set | None = None, include_unknown=False) -> tuple[list[Verdict], dict]:
    blocks = []
    for f in FIELDS:
        if only is not None and f not in only:
            continue
        if (is_unknown(r, f) and not include_unknown) or (f == "mcp" and r.mcp == "None found" and not include_unknown):
            continue
        evs = [e for e in r.evidence if e.claim_field == f and e.excerpt_match and e.verifier != "unsupported"]
        if not evs:
            continue
        ex = "\n".join(f'  - [{e.source_type}] {e.source_url}: "{e.supporting_excerpt}"' for e in evs[:4])
        blocks.append(f"CLAIM field={f} value={value_of(r, f)}\n{ex}")
    if not blocks:
        return [], {"usd": 0}
    msg = [{"role": "system", "content": JUDGE_SYS},
           {"role": "user", "content": f"APP: {r.app_name}\n\n" + "\n\n".join(blocks)}]
    j, _, usage = await parse(C.JUDGE_MODEL, msg, Judgement, max_tokens=6000)
    return j.verdicts, usage


def parse_value(f, s: str):
    s = (s or "").strip()
    if f == "auth_methods":
        allowed = ["OAuth2", "API key", "Basic", "Token", "Other"]
        return [a for a in allowed if a.lower() in s.lower()]
    allowed = {"dev_access": ["Free self-serve", "Free trial", "Paid plan", "Approval required",
                              "Partner or contact sales", "Unknown"],
               "prod_gate": ["None", "App review", "Partner program", "Unknown"],
               "public_api": ["yes", "no", "unknown"],
               "mcp": ["Official", "Community", "Both", "None found", "Unknown"]}[f]
    for a in allowed:
        if s.lower() == a.lower():
            return a
    return UNKNOWN[f]


# ---------------- L2 ----------------
def l2(r: AppRecord) -> str | None:
    tk = r.composio_toolkit
    if not tk.exists or not tk.auth_schemes:
        return None
    theirs = {composio_layer.SCHEME_MAP.get(s, "OAuth2" if "OAUTH" in s else "Other") for s in tk.auth_schemes}
    ours = set(r.auth_methods)
    if not ours:
        return f"we have no auth; Composio toolkit '{tk.slug}' uses {sorted(theirs)}"
    missing = theirs - ours - {"Other"}
    if missing:
        return f"Composio toolkit '{tk.slug}' uses {sorted(theirs)} but we found {sorted(ours)}"
    return None


# ---------------- L3: agentic re-pass ----------------
class FieldAnswer(BaseModel):
    field: str
    value: str
    evidence: list[Ev]


class Repass(BaseModel):
    answers: list[FieldAnswer]


TOOLS = [
    {"type": "function", "function": {"name": "search", "description": "Web search. Returns titles, urls, snippets.",
                                      "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                                                     "required": ["query"]}}},
    {"type": "function", "function": {"name": "fetch", "description": "Fetch a page as markdown text (trimmed).",
                                      "parameters": {"type": "object", "properties": {"url": {"type": "string"}},
                                                     "required": ["url"]}}},
]

REPASS_SYS = """You re-research specific fields for one app using the tools. Prefer the vendor's official docs.
Call search then fetch the most relevant official pages (max 3 fetches). Then answer every requested field
with a value and VERBATIM excerpts (exact sentences) from pages you fetched, with their exact url.
If you cannot find a direct statement, answer Unknown with no evidence. Never invent urls or quotes.
Where to look: for dev_access, find the page that says how to create an account / API key / personal access token
/ developer app, and the pricing page that says whether the API is on the free plan; for prod_gate, find the
app review / marketplace publishing / partner program page; for mcp, find the vendor's MCP server page.
Value vocab: auth_methods = comma list of OAuth2, API key, Basic, Token, Other; dev_access = Free self-serve |
Free trial | Paid plan | Approval required | Partner or contact sales | Unknown; prod_gate = None | App review |
Partner program | Unknown; public_api = yes | no | unknown; mcp = Official | Community | Both | None found | Unknown."""


async def tool_search(http, q):
    r = await http.get("https://api.search.tinyfish.ai", headers={"X-API-Key": C.TINYFISH_KEY},
                       params={"query": q}, timeout=60)
    r.raise_for_status()
    return [{"title": x.get("title"), "url": x.get("url"), "snippet": x.get("snippet")}
            for x in r.json().get("results", [])[:8]]


async def tool_fetch(http, url, budget):
    from .sources import trim
    if budget["fetches"] <= 0 and not cached(url):
        return "fetch budget exhausted"
    pages, n = await tinyfish_fetch(http, [url])
    budget["fetches"] -= n
    p = pages.get(url)
    if not p or is_dead(p):
        return f"could not read page ({(p or {}).get('error')})"
    return trim(p["text"], 6000)


async def l3(r: AppRecord, fields: list[str], reasons: dict, http, budget) -> tuple[list[FieldAnswer], dict, list]:
    """Mistral tool-calling loop (plain function calling: Composio has no Mistral provider; see README ledger)."""
    from .extract import client
    want = "\n".join(f"- {f}: currently {value_of(r, f)!r}; problem: {reasons.get(f, 'no verified evidence')}" for f in fields)
    messages = [{"role": "system", "content": REPASS_SYS},
                {"role": "user", "content": f"APP: {r.app_name} ({r.category}). Official docs: {r.official_docs_url}\nFields to re-research:\n{want}"}]
    usd, calls = 0.0, []
    async def complete():
        for i in range(5):  # rate limits (429) are expected at this concurrency: back off, never give up silently
            try:
                return await asyncio.to_thread(client().chat.complete, model=C.EXTRACT_MODEL, messages=messages,
                                               tools=TOOLS, tool_choice="auto", temperature=0, max_tokens=1500)
            except Exception as e:
                if i == 4:
                    raise
                await asyncio.sleep(15 if "429" in str(e) else 3 * (2 ** i))

    for _ in range(5):
        resp = await complete()
        u = resp.usage
        usd += (u.prompt_tokens * C.PRICE_MISTRAL[C.EXTRACT_MODEL][0] + u.completion_tokens * C.PRICE_MISTRAL[C.EXTRACT_MODEL][1]) / 1e6
        m = resp.choices[0].message
        if not m.tool_calls:
            break
        messages.append(m)
        for tc in m.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            calls.append({tc.function.name: args})
            try:
                out = await (tool_search(http, args.get("query", "")) if tc.function.name == "search"
                             else tool_fetch(http, args.get("url", ""), budget))
            except Exception as e:
                out = f"error: {e}"
            messages.append({"role": "tool", "name": tc.function.name, "content": json.dumps(out)[:9000],
                             "tool_call_id": tc.id})
    messages.append({"role": "user", "content": "Now give the final answers for the requested fields."})
    ans, _, usage = await parse(C.EXTRACT_MODEL, messages, Repass, max_tokens=2500)
    return ans.answers, {"usd": usd + usage["usd"]}, calls


# ---------------- L4: browser-use ----------------
SAMPLE = set(json.loads((C.DATA / "sample.json").read_text())) if (C.DATA / "sample.json").exists() else set()
FIELD_ALIASES = {"auth": "auth_methods", "auth_methods": "auth_methods", "dev_access": "dev_access",
                 "access": "dev_access", "credentials": "dev_access", "prod_gate": "prod_gate",
                 "app_review": "prod_gate", "publishing": "prod_gate", "mcp": "mcp"}


def map_field(s: str) -> str | None:
    s = s.lower()
    if s in FIELD_ALIASES:
        return FIELD_ALIASES[s]
    if "mcp" in s or "model context" in s:
        return "mcp"
    if any(k in s for k in ("review", "publish", "approv", "partner", "go live", "production", "marketplace")):
        return "prod_gate"
    if any(k in s for k in ("auth", "oauth", "token", "key")):
        return "auth_methods"
    if any(k in s for k in ("access", "credential", "sign", "plan", "pricing", "free", "trial", "dev")):
        return "dev_access"
    return None


async def l4(r: AppRecord, app: dict, http, budget, changes, reasons) -> dict:
    from .browser import run_agent
    start = r.official_docs_url or (app.get("seed_urls") or [None])[0]
    if not start:
        return {"skipped": "no start url"}
    try:
        res = await run_agent(http, r.app_name, start)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:200]}
    info = {k: res[k] for k in ("status", "steps", "usd", "seconds", "error")}
    quotes = ((res.get("result") or {}).get("quotes") or [])[:10]
    verified, touched = 0, set()
    info["raw_quotes"] = [{k: str(q.get(k, ""))[:300] for k in ("field", "url", "quote")} for q in quotes]
    for q in quotes:
        f = map_field(str(q.get("field", "")))
        url, quote = q.get("url") or "", q.get("quote") or ""
        if not f or not url.startswith("http") or len(quote) < 12:
            continue
        if budget["fetches"] <= 0 and not cached(url):
            continue
        pages, n = await tinyfish_fetch(http, [url])
        budget["fetches"] -= n
        txt = page_text(url)
        ok = bool(txt) and excerpt_in_text(quote, txt)
        if ok:
            verified += 1
            touched.add(f)
            r.evidence.append(Evidence(claim_field=f, claim=f"{f} (browser)", source_url=url, supporting_excerpt=quote,
                                       source_type="official" if is_official(url, app) else "third-party",
                                       retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"), fetched_via="browser",
                                       excerpt_match=True, verifier="not_run", loop="L4"))
    info.update({"quotes": len(quotes), "quotes_verified": verified, "fields": sorted(touched),
                 "browser_answer": {k: (res.get("result") or {}).get(k) for k in ("auth_methods", "dev_access", "prod_gate", "mcp")}})
    if touched:
        verdicts, u = await l1(r, only=touched, include_unknown=True)
        info["judge_usd"] = u.get("usd", 0)
        for v in verdicts:
            if v.field not in touched:
                continue
            newv = parse_value(v.field, v.corrected_value)
            if v.verdict == "supported":
                for e in r.evidence:
                    if e.claim_field == v.field and e.excerpt_match:
                        e.verifier = "supported"
                reasons.pop(v.field, None)
            elif newv not in ([], "Unknown", "unknown"):
                set_value(r, v.field, newv, "L4", f"browser evidence: {v.reason}", changes)
                for e in r.evidence:
                    if e.claim_field == v.field and e.loop == "L4":
                        e.verifier = "supported"
                reasons.pop(v.field, None)
    return info


# ---------------- orchestration ----------------
async def verify_app(rec: dict, http, budget, changes_all: list) -> dict:
    r = AppRecord(**rec)
    app = next(a for a in load_apps() if a["id"] == r.app_id)
    raw = json.loads((C.RAW / f"{r.app_id:03d}.json").read_text(encoding="utf-8"))
    raw_src = {x["url"]: "\n".join(x.get("excerpts") or []) for x in raw["search"].get("results", [])}
    changes, usd = [], 0.0
    reasons: dict[str, str] = {}
    partial_auth: dict[str, list] = {}

    # L0
    for f in l0(r, raw_src):
        reasons[f] = "L0: no excerpt found verbatim in a fetched page"
    # L1
    verdicts, u = await l1(r)
    usd += u.get("usd", 0)
    for v in verdicts:
        if v.field not in FIELDS:
            continue
        if v.verdict == "supported":
            for e in r.evidence:
                if e.claim_field == v.field and e.excerpt_match:
                    e.verifier = "supported"
        else:
            for e in r.evidence:
                if e.claim_field == v.field and e.excerpt_match and v.verdict == "unsupported":
                    e.verifier = "unsupported"
            reasons[v.field] = f"L1 judge: {v.verdict} â€” {v.reason}"
            if v.verdict == "partially":
                for e in r.evidence:
                    if e.claim_field == v.field and e.excerpt_match:
                        e.verifier = "supported"
                if v.field == "auth_methods":
                    # don't narrow yet: excerpts are a sample of the docs. Look for evidence of the unsupported
                    # method(s) in L3; if none is found, narrow to the supported subset afterwards.
                    partial_auth[v.field] = parse_value(v.field, v.corrected_value)
                else:
                    set_value(r, v.field, parse_value(v.field, v.corrected_value), "L1", v.reason, changes)
                    reasons.pop(v.field, None)
    # L2
    l2_reason = l2(r)
    if l2_reason:
        reasons.setdefault("auth_methods", "L2 Composio: " + l2_reason)
    # L4 browser-use (audit sample + apps whose pages were unreadable)
    l4_info = None
    if r.app_id in SAMPLE:
        if budget["browser_runs"] > 0:
            budget["browser_runs"] -= 1
            l4_info = await l4(r, app, http, budget, changes, reasons)
            usd += l4_info.get("judge_usd", 0)
    # also re-research core unknowns
    for f in ("auth_methods", "dev_access", "public_api"):
        if is_unknown(r, f):
            reasons.setdefault(f, "pass1 Unknown")
    # L3
    calls = []
    if reasons:
        try:
            answers, u, calls = await l3(r, list(reasons), reasons, http, budget)
            usd += u["usd"]
            for a in answers:
                if a.field not in FIELDS:
                    continue
                good = []
                for ev in a.evidence:
                    txt = page_text(ev.url)
                    if txt and excerpt_in_text(ev.excerpt, txt):
                        good.append(Evidence(claim_field=a.field, claim=f"{a.field} = {a.value}", source_url=ev.url,
                                             supporting_excerpt=ev.excerpt,
                                             source_type="official" if is_official(ev.url, app) else "third-party",
                                             retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"), fetched_via="tinyfish",
                                             excerpt_match=True, verifier="not_run", loop="L3"))
                newv = parse_value(a.field, a.value)
                if good and newv not in ([], "Unknown", "unknown"):
                    r.evidence = [e for e in r.evidence if not (e.claim_field == a.field and e.verifier == "unsupported")]
                    r.evidence += good
                    set_value(r, a.field, newv, "L3", reasons.get(a.field, ""), changes)
                    reasons.pop(a.field, None)
        except Exception as e:
            calls.append({"error": f"{type(e).__name__}: {e}"[:200]})
    # L1 on new L3 evidence (judge the re-pass too)
    new_fields = {e.claim_field for e in r.evidence if e.loop == "L3"}
    if new_fields:
        verdicts, u = await l1(r)
        usd += u.get("usd", 0)
        for v in verdicts:
            if v.field in new_fields:
                for e in r.evidence:
                    if e.claim_field == v.field and e.loop == "L3":
                        e.verifier = "supported" if v.verdict != "unsupported" else "unsupported"
                if v.verdict == "unsupported":
                    reasons[v.field] = "L1 judge rejected re-pass evidence: " + v.reason
    # partially-supported auth that L3 could not complete -> narrow to what the excerpts support
    if "auth_methods" in partial_auth and "auth_methods" in reasons and partial_auth["auth_methods"]:
        set_value(r, "auth_methods", partial_auth["auth_methods"], "L1",
                  "narrowed to the methods the excerpts support (re-pass found no evidence for the rest)", changes)
        reasons.pop("auth_methods")
    # anything still failing -> Unknown (never keep an unverified guess)
    for f, why in reasons.items():
        if not any(e.claim_field == f and e.excerpt_match and e.verifier != "unsupported" for e in r.evidence):
            set_value(r, f, UNKNOWN[f], "unverified->Unknown", why, changes)
    rules.apply(r)
    r.verification_status = "reverified"
    r.trace = {**r.trace, "loops_run": ["pass1", "L0", "L1", "L2"] + (["L4"] if l4_info else []) + (["L3"] if calls else []),
               "l2_composio": l2_reason, "l3_tool_calls": calls, "l4_browser": l4_info, "verify_usd": round(usd, 5),
               "open_issues": reasons}
    for c in changes:
        changes_all.append(c)
    return r.model_dump()


async def run_browser():
    """L4 as its own step (TinyFish agent runs queue for minutes): audit-sample apps in pass2 get a browser
    run; verified quotes become evidence, the judge arbitrates, rules re-run; pass2 rewritten in place."""
    recs = [json.loads(l) for l in C.PASS2.read_text(encoding="utf-8").splitlines() if l.strip()]
    apps = {a["id"]: a for a in load_apps()}
    # cost cap: TinyFish agent averaged ~17 steps (~$0.30) per run and runs one at a time -> 8 runs.
    # Priority: audit apps with open issues / Unknown core fields first.
    budget = {"fetches": 120, "browser_runs": 8}
    def prio(rec):
        unk = sum(rec[f] in ("Unknown", "unknown") or rec[f] == [] for f in ("auth_methods", "dev_access", "prod_gate", "public_api", "mcp"))
        return -(unk + len(rec["trace"].get("open_issues") or {}))
    order = sorted([i for i, r in enumerate(recs) if r["app_id"] in SAMPLE], key=lambda i: prio(recs[i]))
    allowed = {recs[i]["app_id"] for i in order[:8]}
    sem = asyncio.Semaphore(3)
    async with httpx.AsyncClient() as http:
        async def one(i, rec):
            if rec["app_id"] not in allowed or (rec["trace"].get("l4_browser") or {}).get("status") == "COMPLETED":
                return
            async with sem:
                r, changes, reasons = AppRecord(**rec), [], {}
                info = await l4(r, apps[r.app_id], http, budget, changes, reasons)
                rules.apply(r)
                r.trace = {**r.trace, "l4_browser": info,
                           "loops_run": list(dict.fromkeys(r.trace.get("loops_run", []) + ["L4"]))}
                recs[i] = r.model_dump()
                for c in changes:
                    append_jsonl(C.CHANGES, c)
                print(f"  L4 {r.app_name:<22} {info.get('status')} steps={info.get('steps')} "
                      f"verified={info.get('quotes_verified')}/{info.get('quotes')} changes={len(changes)}", flush=True)
        await asyncio.gather(*(one(i, r) for i, r in enumerate(recs)))
    with open(C.PASS2, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


async def run(browser_inline: bool = False):
    p1 = [json.loads(l) for l in C.PASS1.read_text(encoding="utf-8").splitlines() if l.strip()]
    skip = done_ids(C.PASS2)
    todo = [r for r in p1 if r["app_id"] not in skip]
    print(f"verify: {len(todo)} (already done: {len(skip)})")
    budget = {"fetches": 400, "browser_runs": 15 if browser_inline else 0}
    sem = asyncio.Semaphore(4)
    lock = asyncio.Lock()
    async with httpx.AsyncClient() as http:
        async def one(rec):
            async with sem:
                changes = []
                try:
                    out = await verify_app(rec, http, budget, changes)
                    async with lock:
                        append_jsonl(C.PASS2, out)
                        for c in changes:
                            append_jsonl(C.CHANGES, c)
                    print(f"  ok  {rec['app_id']:3d} {rec['app_name']:<26} changes={len(changes)} "
                          f"{rec['buildability']}->{out['buildability']}  open={list(out['trace']['open_issues'])}")
                except Exception as e:
                    print(f"  ERR {rec['app_id']} {rec['app_name']}: {type(e).__name__}: {str(e)[:200]}")
        await asyncio.gather(*(one(r) for r in todo))


