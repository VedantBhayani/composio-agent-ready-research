# Agent-ready? Researching 100 apps for Composio

An agent that researches 100 apps and asks of each one: **could this be an agent toolkit today, and if not, what's blocking it?** It records auth methods, how developers get credentials, the approval needed to go live, the API surface, MCP servers and Composio toolkit coverage. Every answer carries a fetched URL and a verbatim excerpt. The output is checked by four automated loops and then a blind human audit.

- **Live page:** not deployed yet (GitHub Pages pending owner OK); open `output/index.html` locally
- **Data:** `output/data.json`, `output/records.csv`, `output/llms.txt` (for agents)

## Results (all computed from `data/`)
**Coverage:** 100 of 100 apps researched, each with fetched evidence. Pass 1 is frozen at `data/pass1.jsonl`; `data/pass2.jsonl` holds the output of the automated loops; `data/final.jsonl` adds the human corrections.

**Findings** (from `data/insights.json`, computed on `final.jsonl`):
- **Free to start, gated to ship.** 68 of 100 apps let a developer get credentials on their own (63 free self-serve, 5 free trial). App review before going live is the #1 blocker (36 apps), followed by partner gates (6) and paid plans (4).
- **OAuth2 leads:** it appears in 75% of apps and API keys in 55%; 38% support both.
- **There are two roads to "buildable":** 86 apps rate Yes, Partial 9 and Unknown 5. Of those 86, only 45 get there through a self-serve REST API. The rest rely on the vendor's official MCP server while the API itself is gated.
- **Composio** has a toolkit for 80 of 100 apps. Apps without one skew gated or unknown: 30% of them, against 10% of covered apps. Fourteen buildable apps have no toolkit yet, which makes them a build-now list (DealCloud, LiveAgent, Gladly, Vonage, systeme.io, WooCommerce, Squarespace, fanbasis, SE Ranking, Binance, Paygent Connect, iPayX, Reducto, Mermaid CLI).

**Accuracy** (blind human audit: 15 apps, 90 claims, sample seed 42, scoring rules fixed before results; see `data/accuracy.json`):

| | Pass 1 | Pass 2 (after loops) | Final |
|---|---|---|---|
| Precision on answered | 71.9% (64/89), CI95 62-80% | 69.0% (60/87), CI95 59-78% | matches human by construction |
| Abstained (Unknown) | 0 | 2 | 0 |
| Unsupported (excerpt not in page) | 5 | 0 | - |

One human answer was outside the allowed values (Salesforce auth: "yes, Rest") and is excluded as unresolved.

**The honest result: the automated loops did not raise precision.** The confidence intervals overlap, so the 3-point drop is noise rather than a gain, and nothing here shows the "lower first pass rising to higher" pattern from the automated loops alone. The rise comes from the human tier. What the loops did achieve:
- **Grounding.** Unsupported claims fell from 5 to 0. Unverified fields became Unknown instead of staying guesses.
- **More Unknowns, on purpose.** Values the loops could not verify became Unknown, so across all 100 apps dev_access Unknown went from 1 in pass 1 to 14 in pass 2. That costs coverage, and the audit shows it did not buy precision.

Where the errors are:
- **Public API, Composio toolkit and buildability** were 15/15, 15/15 and 14/15 correct in pass 2.
- **MCP:** 10 of the 11 MCP errors are "Official" where the human also found a community GitHub repo ("Both"). On whether an official MCP exists, agent and human agree on 14 of 15. The fix is to search GitHub for community servers even when a vendor server exists.
- **Auth** is scored as an exact set, and the agent tends to add a method the human did not confirm (OAuth2 on Pumble, Plaid and MrScraper).
- **Access got worse, 11 → 8 correct.** A real before→after example of a loop helping: Twenty's dev_access went from Unknown to Free self-serve (browser agent, L4), which the human confirmed. And one of a loop hurting: Salesforce's prod_gate went from Unknown to Partner program (L4), where the human found App review. The loops also left free trials labelled "Free self-serve" (SendGrid, BigCommerce).

## Architecture
```
input/applications.json (100 apps + hint URLs from the brief)
  -> Parallel Search (mode=fast, 1 request = 3 queries)  -> rank official domains first
  -> TinyFish Fetch (<=4 pages, markdown, disk-cached)    -> trim to auth/access/MCP sections
  -> Mistral Small structured extraction (Pydantic schema; fetched text only; verbatim excerpt + URL per field)
  -> Composio catalog match (1,842 toolkits; exact name / reviewed alias / single-product domain)
  -> agent/rules.py: buildability, archetype, main blocker, confidence (deterministic)
  => data/pass1.jsonl (frozen)
  -> L0 deterministic: is the excerpt verbatim in a page we fetched? (normalized, fuzzy >= 90)
  -> L1 LLM judge: does the excerpt actually support the claim?
  -> L2 Composio cross-check: our auth methods vs the auth schemes of Composio's toolkit
  -> L4 TinyFish browser agent (audit sample + unreadable pages); its quotes are re-fetched and must match
  -> L3 agentic re-pass: Mistral tool-calling (search, fetch) only on fields that failed; re-judged by L1
  -> anything still unverified becomes Unknown
  => data/pass2.jsonl + data/changes.jsonl (every change: field, old -> new, loop, reason)
  -> blind human audit (15 apps x 6 claims, seed 42) -> analysis/score.py
  => data/final.jsonl (pass2 + human corrections, tagged) -> analysis/analyze.py -> analysis/build_page.py
```
One plain Python pipeline (asyncio, timeouts, retries with backoff, incremental writes, resumable). No agent framework.

## Why each tool
| Tool | Used for | Why |
|---|---|---|
| Parallel Search (`mode: fast`) | Finding the official docs, auth and access pages | One request carries 3 queries and returns ranked URLs with excerpts, at $0.001 a request. 100 apps cost $0.10 |
| TinyFish Fetch / Search | Page text (markdown), re-pass search | Free tier (1,000 URLs a day). Clean markdown. Renders pages that need JavaScript when required |
| TinyFish Agent | L4 browser-use check | A real browser that navigates the docs like a person. About $0.016 a step |
| Mistral Small | Extraction, judge, re-pass agent | Native Pydantic structured output (`chat.parse`) and tool calling. Cheap ($0.15 / $0.60 per million tokens) |
| Composio REST API v3.1 | Toolkit catalog and auth schemes | The authoritative source for "does a toolkit exist", plus an independent second opinion on auth |

### Composio: where it's used and where it isn't
| # | Use | Status |
|---|---|---|
| C1 | Catalog: toolkit exists, slug, tool count for all 100 | **Used.** REST `GET /api/v3.1/toolkits` with cursor pagination. The SDK's `toolkits.get()` (composio 0.34.0) returned only the first 1,000 of 1,842 toolkits and exposed no cursor, so REST was used |
| C2 | Toolkit `auth_schemes` as an independent auth check (L2) | **Used.** A disagreement sends the auth field to the re-pass |
| C3 | Run the re-pass agent's tools through Composio | **Not used.** Composio has no Mistral provider. The re-pass uses plain Mistral function calling. Next step: a Composio custom provider |
| C4 | Recommendations framed as Composio's backlog (build now / plan for app review / partnership / ship as MCP or skill) | **Used** |
| C5 | Composio MCP as the agent's tool transport | **Not used.** It adds a transport, not accuracy. Next step |
| C6 | Expose this dataset as a Composio tool or MCP | **Not used.** Out of scope for the time box. `data.json` and `llms.txt` cover agent consumption |
| C7 | Composio GitHub toolkit for the repo | **Not used.** The `gh` CLI is simpler |

Composio aliases where the names differ (Zoho CRM → `zoho`, MongoDB Atlas → `mongodb`, …) were confirmed by listing each toolkit's tools (`GET /api/v3.1/tools?toolkit_slug=`). Some apps are not matched on purpose: Salesforce Commerce Cloud (the `salesforce` toolkit is the CRM), Mermaid CLI (`mermaid_chart_mcp` is the Mermaid Chart SaaS) and Amazon SP-API (the `amazon` toolkit has 0 tools).

## Schema (`agent/schema.py`)
Per app:
- **Basics:** `category`, `description`, `official_docs_url`
- **Auth:** `auth_methods` (OAuth2 / API key / Basic / Token / Other) and `auth_notes`
- **`dev_access`:** how a developer starts. Free self-serve / Free trial / Paid plan / Approval required / Partner or contact sales / Unknown
- **`prod_gate`:** approval needed to go live. None / App review / Partner program / Unknown
- **API surface:** `public_api`, `api_type`, `api_breadth`
- **MCP:** `mcp` (Official / Community / Both / None found / Unknown) and `mcp_urls`
- **Derived:** `integration_shape` and `composio_toolkit`
- **Verdicts (from rules):** `buildability`, `main_blocker`, `archetype`, `confidence`
- **Proof:** `evidence[]` (claim, source_url, verbatim excerpt, official or third-party, fetched_via, excerpt_match, judge verdict, loop), `verification_status`, and `trace` (queries, URLs, loops, costs)

**Verdict rules (`agent/rules.py`, unit-tested):**
- **Yes:** a public API with free self-serve or trial credentials and no known go-live gate, **or** an official MCP server.
- **Partial:** an API exists but is gated (paid plan, approval, app review or partner), **or** an open-source CLI that could be wrapped as a skill.
- **No:** nothing public.
- **Unknown:** not enough evidence.

## Verification method
1. **Automated loops (L0–L4)** turn pass 1 into pass 2. Every change is logged.
2. **Blind human audit.** 15 apps, stratified by category (1–2 each), seed 42, sampled from the input list before any results existed. 6 claims each: auth, access, public API, MCP, Composio toolkit and buildability, 90 claims in total. The sheet showed **no agent answers**. The human recorded the truth with a source.
3. **Scoring.** Pass 1 and pass 2 are each scored against the human answers. Unknown counts as an abstention: it's reported as answer rate, never as correct. Human corrections produce `final.jsonl` and are **not** counted as gains from the loops.
4. **Labels.** Automated metrics (excerpt verbatim rate, judge-supported rate) are labelled automated, never presented as accuracy.

## Run
```
python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
copy .env.example .env      # add PARALLEL_API_KEY, TINYFISH_API_KEY, MISTRAL_API_KEY, COMPOSIO_API_KEY
python -m agent.smoke_test
python -m agent.composio_catalog
python -m agent run --app Stripe           # one app, end to end (runnable trigger)
python -m agent run                        # all 100; re-run to resume after interruption
python -m agent verify                     # pass 2; resumable
python analysis/make_checklist.py          # human sheet -> fill YOUR_ANSWER
python analysis/score.py --apply
python analysis/analyze.py
python analysis/build_page.py
python -m pytest -q
```

## Limitations
- **Automated loops did not raise human-audited precision** (see Results). The audit is 90 claims, so each CI is about ±10 points.
- **The final tier is not a measurement.** Human corrections apply only to the 15 audited apps. The other 85 are pass 2 as it stands.
- **The judge (L1) runs on Mistral Small.** Mistral Large timed out at over 60 s per call. This makes self-consistency weaker than having a different model judge.
- **The browser loop (L4) ran on 8 audit apps only** (cost about $1.40, one timeout). Only 4 of 23 browser quotes matched our own fetch verbatim, and one L4 change (Salesforce) was wrong.
- **Known wrong value outside the sample:** Datadog's dev_access came from the OAuth partner-sandbox path. It is left as is, not hand-fixed.
- **Strict evidence costs coverage.** prod_gate is Unknown for 53 apps because no page stated it directly. Missing evidence is not proof of absence.
- **The Composio catalog is a snapshot** (1,842 toolkits via REST), and `toolkits.get()` in SDK 0.34.0 returns at most 1,000. The aliases are hand-verified by listing each toolkit's tools.
- **Public docs only.** Nothing was checked by signing up or logging in.
