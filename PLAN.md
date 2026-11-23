# PLAN — Composio take-home: 100-app API research agent (v2)

Hard stop **22:00 IST** (real cutoff 23:00 = received 15:00 + 8 h; 22:00–23:00 is untouched buffer).
Role: **AI Product Ops** → accuracy, judgment, honest verification and presentation are graded above engineering.
Standard: every number traceable to a file, every claim to a fetched URL + excerpt, every gap stated.

---

## 0. What they grade (exact brief lines → our answer)

| # | Brief (verbatim intent) | Our deliverable | Done when |
|---|---|---|---|
| G1 | "**Accuracy is what matters most.**" "Verify… sample… cross-check by hand… report right and wrong… real verification loops (agent, **browser-use**, other means) plus human checks… accuracy moved from lower first pass to higher one **because of those loops**" | Blind human truth on 15 apps × 6 claims; pass1 vs pass2 scored; 4 automated loops incl. browser-use and a Composio cross-check; human fixes as a separate tier | Real counts + CI on page; ≥1 real before→after; loops credited only for automated gains |
| G2 | "The actual point: **Find the patterns. Cluster the results**… which auth dominates, which categories self-serve vs gated, most common blocker, easy wins vs outreach. Insight over raw table." | Archetype clusters + the **4 named questions answered verbatim** at the top | Each answer is one sentence + one number from `final.jsonl` |
| G3 | "Do it with an agent… **Composio's own SDK and MCP** in the spirit of the role. Tell us what it does and **where it needed a human**." | Python pipeline; Composio used where it earns it (§6) + ledger of what we didn't use and why; `human_log.md` | README + page show architecture, Composio ledger, human touchpoints |
| G4 | "Single self-explanatory HTML page / Case Study… ~2 minutes, no narration… findings, patterns (up top), agent, proof, verification… **process/workflow**… easy for **agent and human** to consume. Clarity and presentation are the point." | `output/index.html` + `data.json`, `records.csv`, `llms.txt` | First screen alone answers G2 + shows accuracy |
| G5 | "**Proof** (the app you built, live link or runnable trigger)" | Live Pages URL; per-app run trace on page; recorded real run log; `python -m agent run --app X`; workflow_dispatch if ahead | CLI works from clean clone; trace visible per row |
| G6 | "If the agent got things wrong or an app defeated you, say so… gated with evidence is the correct finding" | "Defeated / Unknown" list + limitations | Unknown counts visible, never hidden |
| G7 | "Context: whether it can be an **MCP server or agent-callable skills**" + hints "Otter (MCP server)", "Devin (MCP)", CLIs in list | `integration_shape` field; MCP-only and CLI apps treated as buildable via MCP/skill | Rule tests cover MCP-only and CLI cases |
| G8 | "Primary filter… submit as early as possible (<8 h)" | Ship by 22:00 | — |
| G9 | Submit: live link + repo with short README on how to run the agent | Public repo, README | URLs in final summary |

"A real mix: apps customers have actually requested… every common auth pattern **on purpose**" → test hypothesis *long-tail requested apps are where gaps/outreach concentrate*; state only if data supports it.

Per-app fields required by brief: category · one-line · auth · self-serve vs gated · API surface (REST/GraphQL, breadth, **any** existing MCP) · buildability + main blocker · evidence URLs · "and more.." (ours: `prod_gate`, `integration_shape`, `archetype`, `composio_toolkit`, `confidence`, `verification_status`, `trace`).

---

## 1. Settled decisions

| Decision | Choice |
|---|---|
| Buildability | Deterministic rule in code (§4). LLM extracts facts only. |
| Access | `dev_access` (how a dev starts) + `prod_gate` (approval to go live) |
| MCP | Official · Community (only with a fetched page proving it) · Both · None found · Unknown. Never "None". |
| Integration shape | Hosted API · MCP server · Skill (CLI/library) · Multiple · None found |
| Clusters | Rule-assigned archetypes (§4) — the page's spine |
| Truth | You label **blind** (claim + links, no agent answer); pass1 and pass2 scored; your fixes → `final`, not counted as loop gain |
| Claims checked | 6 per app: auth · access (dev_access+prod_gate) · public API · MCP · Composio toolkit · buildability verdict → 90 claims |
| Unknown | Reported separately: precision on answered + answer rate + Wilson 95% CI |
| Sample | 15 apps, seed 42, stratified 1–2 per category |
| Composio | §6 — catalog + auth cross-check + agentic re-pass on Composio tools; ledger explains every non-use |
| Browser-use | **Not cuttable** — runs on the 15 sampled apps + every page plain fetch couldn't read |
| Proof | Trace per app on page + real run log + CLI; workflow_dispatch only if ahead at 21:15 |
| Deploy | GitHub Pages, same repo (gh logged in, `repo`+`workflow` scopes) |
| Never | OpenRouter, multi-agent frameworks, backend, guessing SDK methods, pushing/deploying without your OK |

---

## 2. Repo layout

```
.
├── README.md  AGENTS.md  PLAN.md  requirements.txt  .env.example  .gitignore
├── human_log.md                      every human intervention, timestamped
├── input/applications.json           100 apps: id, name, category, hint_url, hint_note
├── agent/
│   ├── __main__.py      CLI: run [--app X] [--limit N] [--resume] · verify · score · analyze · build-page
│   ├── config.py        env, models, limits
│   ├── schema.py        Pydantic models + enums
│   ├── search.py        Parallel search (TinyFish search fallback)
│   ├── fetch.py         TinyFish fetch + disk cache (cache/pages/<sha1>.json)
│   ├── browser.py       browser-use verification (TinyFish agent/render or Playwright — chosen in S1)
│   ├── trim.py          keyword windows (auth/oauth/api key/token/pricing/plan/review/partner/MCP)
│   ├── extract.py       Mistral structured extraction → raw + validated
│   ├── composio_layer.py  catalog load/match · toolkit auth schemes · custom tools for agentic re-pass
│   ├── rules.py         buildability · integration_shape · archetype · blocker · confidence
│   ├── checks.py        deterministic checks
│   ├── verifier.py      LLM entailment judge + agentic re-pass loop
│   └── pipeline.py      async orchestration, retries/backoff, checkpoint, incremental writes, trace
├── data/
│   ├── raw/<app_id>.json   raw provider outputs, never edited
│   ├── composio_catalog.json
│   ├── pass1.jsonl (frozen) · pass2.jsonl · final.jsonl
│   ├── changes.jsonl       every automated + human change: field, old→new, loop, reason
│   ├── checklist.csv · truth.csv
│   └── run_log.jsonl       per-app cost, latency, errors
├── analysis/score.py · analyze.py → accuracy.json · insights.json
├── output/index.html · data.json · records.csv · llms.txt · run_log.txt
├── tests/test_schema.py · test_rules.py · test_checks.py
└── .github/workflows/research-one.yml   (only if ahead)
```

---

## 3. Schema (`agent/schema.py`)

- `AuthMethod`: OAuth2 · API key · Basic · Token · Other  (brief's list; Bearer/PAT recorded in `auth_notes`)
- `DevAccess`: Free self-serve · Free trial · Paid plan · Admin approval · Partner or contact sales · Unknown
- `ProdGate`: None · App review · Partner program · Unknown
- `YesNoUnknown`: yes · no · unknown
- `ApiType`: REST · GraphQL · SOAP · SDK-only · CLI/library · None found · Unknown
- `ApiBreadth`: Broad · Moderate · Narrow · Unknown
- `Mcp`: Official · Community · Both · None found · Unknown
- `IntegrationShape`: Hosted API · MCP server · Skill (CLI/library) · Multiple · None found
- `Buildability`: Yes · Partial · No · Unknown
- `Blocker`: None · Paid plan · Partner gate · App review · No public interface · Insufficient evidence
- `Archetype`: Open API · Open + app review · Paid gate · Partner gate · MCP-only · Skill-only · Defeated
- `Confidence`: High · Medium · Low

`Evidence`: claim_field, claim, source_url, source_title, supporting_excerpt, source_type (official|third-party), retrieved_at, excerpt_match, verifier (supported|unsupported|not_run), loop (pass1|verifier|composio|repass|browser|human).

`AppRecord`: app_id, app_name, category, description, official_docs_url, auth_methods[], auth_notes, dev_access, prod_gate, public_api, api_type, api_breadth, mcp + mcp_urls[], integration_shape, composio_toolkit {exists, slug, tool_count, auth_schemes[]}, buildability, main_blocker, blocker_note, archetype, confidence, evidence[], verification_status (pass1|reverified|human_corrected), trace {queries[], urls_fetched[], checks{}, loops_run[]}, last_verified.

Rule: a field with no evidence item ⇒ `Unknown` (code-enforced).

---

## 4. Rules (`agent/rules.py`, pure, unit-tested)

```
integration_shape: from public_api, mcp, api_type (CLI/library) → one or Multiple

buildability:
  public_api=yes & dev_access∈{Free self-serve, Free trial} & prod_gate∈{None, Unknown} → Yes
  mcp∈{Official, Both} & public_api≠yes                                                  → Yes (via MCP)
  public_api=yes (any other access/gate)                                                  → Partial
  api_type=CLI/library (open source, no hosted API)                                       → Partial (wrap as skill)
  public_api=no & mcp∉{Official, Both} & not CLI                                          → No
  else                                                                                     → Unknown

archetype (first match):
  Unknown on public_api AND dev_access            → Defeated
  MCP-only (no public API, official MCP)          → MCP-only
  CLI/library only                                → Skill-only
  dev_access=Partner or contact sales             → Partner gate
  dev_access∈{Paid plan, Admin approval}          → Paid gate
  self-serve/trial & prod_gate∈{App review, Partner program} → Open + app review
  self-serve/trial & prod_gate∈{None, Unknown}    → Open API

main_blocker: No public interface > Partner gate > App review > Paid plan > None; Unknown → Insufficient evidence

confidence:
  High   = auth, dev_access, public_api each backed by ≥1 official excerpt, excerpt_match ✓, verifier supported
  Medium = all three backed, some third-party or one check failed
  Low    = otherwise
```

---

## 5. Verification loops (G1 — the core)

| Loop | Type | What it does | Runs on |
|---|---|---|---|
| L0 | Deterministic | URL ∈ fetched set · excerpt fuzzy-match ≥90 after normalize · enums valid; fail → claim → Unknown + queued | all 100 |
| L1 | Agent (LLM judge) | separate Mistral call: does excerpt support claim? unsupported → Unknown + queued | all evidence |
| L2 | Composio cross-check | our auth vs Composio toolkit auth schemes; mismatch → queued (condition: SDK exposes schemes — verified S1) | apps Composio covers |
| L3 | Agentic re-pass | Mistral tool-calling agent with search/fetch as Composio custom tools (fallback: plain function calling) re-researches only queued fields | queued claims, Low confidence, Unknown core fields |
| L4 | Browser-use | real browser render/agent on official docs; re-extract fields from rendered text | 15 sampled apps + all empty/JS-shell fetches |
| H | Human blind | you set truth on 90 claims; scores pass1, pass2; your fixes → final | 15 apps |

Reported: per-loop change counts (`changes.jsonl`), automated metrics (excerpt-match %, verifier-supported %, Composio agreement %) labelled **automated**; accuracy from `truth.csv` labelled **human-checked**.

---

## 6. Composio — where it's used and why (ledger goes into README + page)

| # | Use | Status | Why |
|---|---|---|---|
| C1 | Catalog via SDK: toolkit exists, slug, tool count for all 100 | **Must** | Only authoritative source for coverage; drives the quick-wins list (buildable, no toolkit) |
| C2 | Toolkit auth schemes as independent auth check (L2) | **Must if SDK exposes it** (verify S1, ≤10 min) | Second source we don't control → accuracy |
| C3 | Agentic re-pass on Composio tools (L3): register `search`/`fetch` as Composio custom tools, Mistral calls them through Composio | **Must try**, timebox 20 min in S3 (built while full run executes) | Puts Composio in the agent itself, where the loop actually needs tool calls |
| C4 | Output in Composio terms: toolkit, auth config, managed OAuth vs API key; recommendations as build-now / build+app-review / partnership / ship-as-MCP-or-skill | **Must** | Shows product understanding; turns findings into Composio's backlog |
| C5 | Composio MCP server as the agent's tool transport | **Not used** — state why | Adds a transport, not accuracy; C3 already exercises Composio tools. Next step on page |
| C6 | Expose our dataset as a Composio custom tool / MCP for other agents | **Not used** — state why | Overscope for 7 h; `data.json`/`llms.txt` cover agent consumption. Next step |
| C7 | Composio GitHub toolkit for repo/deploy | **Not used** — state why | gh CLI is simpler and needs no OAuth hop; no benefit to findings |

If C2 or C3 fails its check: the ledger says exactly what was tried, what failed, and the fallback used. Never claim it worked.

---

## 7. Step-by-step attack (exit gate per step)

### S1 · 18:55–19:20 · Setup + tool smoke tests
1. venv; install `httpx pydantic mistralai composio rapidfuzz python-dotenv pytest` (+ `playwright` only if chosen for L4). Verify package names on PyPI.
2. `.gitignore`, `.env.example`; you add keys to `.env` (never printed).
3. `input/applications.json` from Notion: 100 rows + hint URL + hint note.
4. Read current docs → one minimal call each; record exact methods/params in README "Tool notes":
   - Parallel: pricing → cost/search; speed/mode param exists?; 1 test search.
   - TinyFish: fetch static page + JS page (highlevel.stoplight.io); does it render? does it offer a browser-agent endpoint (→ L4)?
   - Mistral: models, JSON-schema output, tool calling, RPM/TPM limits.
   - Composio: inspect SDK; list toolkits → `composio_catalog.json`; do toolkits expose auth schemes (C2)?; do custom tools + execution exist (C3)?
5. `git init` (no remote). Start `human_log.md`.
**Exit:** all tools return real data; 100-app cost estimate shown; C2/C3/L4 feasibility recorded.

### S2 · 19:20–19:40 · Pipeline + 3-app test
Per app: hint URL seed → Parallel 1 query (auth/access/pricing; 2nd query "MCP server" if budget) → rank official domain → TinyFish fetch ≤4 pages (cached) → trim (~12k chars) → Mistral extract (fetched text only, verbatim excerpt + URL per field, else Unknown) → Pydantic → L0 → C1 match → rules → append `pass1.jsonl` + trace + `run_log.jsonl`.
Test: **Stripe** (open), **LinkedIn Ads** (app review/partner), **Otter AI** (MCP-shaped) — Sherlock covered in full run.
**Exit:** 3 real records + cost/app + time/app shown → your **GO**.

### S3 · 19:40–20:30 · Full run ∥ blind truth ∥ build loops
- `python -m agent run --resume` (semaphore tuned to Mistral limits; backoff on 429/5xx; timeouts; checkpoint = ids in pass1).
- `checklist.csv` generated at start (seeded sample, no agent answers): app, claim, official links, your_truth, your_source_url, notes. You fill 90 claims (~50 min).
- Me meanwhile: L1 verifier, L2, L3 (C3 timeboxed 20 min), L4 browser, page skeleton.
- Freeze pass1 (copy; never edited).
**Exit:** real N/100 in pass1; checklist filled.

### S4 · 20:30–20:50 · Loops → pass2
L1 → L2 → L3 → L4 in order; every change to `changes.jsonl`; write `pass2.jsonl`.
**Exit:** pass2 + per-loop change counts.

### S5 · 20:50–21:05 · Score + human corrections
- `score.py`: 90 claims vs truth for pass1 and pass2 → correct · incorrect · abstained (Unknown) · unsupported · unresolved; precision on answered, answer rate, Wilson CI; per-loop attribution of fixes.
- Error taxonomy; ≥1 real before→after from `changes.jsonl`.
- Your corrections → `final.jsonl` (tagged human). Systemic error → fix rule/prompt, note it.
**Exit:** `accuracy.json`; automated vs human labelled.

### S6 · 21:05–21:35 · Analysis + page
`analyze.py` on `final.jsonl`: archetype clusters (counts + members); the 4 named questions; auth mix; dev_access × category; prod_gate share; public API share; MCP coverage; integration shapes; Composio coverage; buildability; blocker ranking; quick wins (buildable ∧ no toolkit); paid/gated; outreach (partner gate); defeated; long-tail hypothesis test.

`index.html` (single file, data inlined, pinned chart lib from cdnjs or hand SVG, 375px-safe):
1. **First screen:** headline · 4 named answers with numbers · archetype strip · accuracy pass1→pass2 (n=90 claims, CI) · coverage N/100 · links
2. Matrix: search + filters (category, archetype, buildability, MCP, toolkit); row expands → evidence excerpts + trace
3. Patterns charts
4. Opportunities for Composio: build now · build + app review · partnership · ship as MCP/skill
5. The agent: pipeline diagram · loops · Composio ledger · where a human was needed
6. Verification: method, numbers, per-loop gains, error types, before/after; automated vs human labels
7. Proof: real run log excerpt + CLI command + repo
8. Methodology + limitations (sample size, CI, Unknowns, defeated apps, tool limits)
9. For agents: `data.json` · `records.csv` · `llms.txt`
Findings and recommendations in separate blocks.
**Exit:** opens from disk; 375px OK; every number traceable.

### S7 · 21:35–21:50 · Docs, tests, exports
README (architecture, why each tool, Composio ledger, schema, loops, accuracy, run + resume commands tested from clean, limitations, next steps), AGENTS.md, pinned requirements, 3 test files green. workflow_dispatch only if ahead at 21:15.
**Exit:** `pytest` green; commands verified.

### S8 · 21:50–22:00 · Ship (your explicit OK only)
`gh repo create` public → push → Pages → open live URL. Blocked >10 min → local files + instructions.
Final summary: repo URL, live URL, real N researched, audit n (15 apps / 90 claims), pass1→pass2 accuracy, main findings, known limits.

---

## 8. Your touchpoints (= "where it needed a human")
1. Keys into `.env` (S1) · 2. GO after 3-app test (S2) · 3. Blind truth, 90 claims (S3) · 4. Approve corrections (S5) · 5. OK to push/deploy (S8). All logged in `human_log.md`.

## 9. Risks → mitigation
| Risk | Mitigation |
|---|---|
| Mistral rate limits | trim ~12k/app, tuned semaphore, backoff, resume |
| TinyFish no JS render | L4 browser on empty shells; else Unknown + Defeated list |
| Composio SDK lacks auth schemes / custom tools | ledger states it; L2 dropped / L3 uses plain function calling |
| Parallel budget | measured in S1; ≤2 searches/app; hint URLs reduce searches |
| Paraphrased excerpts | fuzzy ≥90; fail → Unknown, never silent pass |
| Gaming via Unknown | answer rate next to precision |
| pass2 not better than pass1 | report it honestly with why |
| Run unfinished by 20:30 | page shows real N/100; finish in background, regenerate before ship |

## 10. Cut order if behind
**Never cut:** coverage · evidence checks · L1 · L4 browser (on sample) · blind human check · C1 · Composio ledger.
Cut in order: 1. workflow_dispatch → 2. L4 beyond the sample → 3. charts → tables → 4. 2nd Parallel query → 5. C3 (fallback plain function calling, ledger says so) → 6. design polish.

## 11. Pre-ship checklist
- [ ] no secrets in git history; `.env` ignored
- [ ] every non-Unknown field has fetched URL + matching excerpt
- [ ] pass1 untouched since freeze
- [ ] all page numbers regenerate from `final.jsonl` / `accuracy.json`
- [ ] Composio ledger accurate (nothing claimed that didn't run)
- [ ] "100 researched" only if 100 in final
- [ ] README commands run from fresh clone
- [ ] live link works on mobile
