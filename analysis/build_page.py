"""Build the deliverable page + data exports.  Run: python analysis/build_page.py
Writes output/index.html, output/data.json, output/records.csv, output/llms.txt.
All numbers come from data files; prose strings live in the constants below."""
import csv
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "output"

# ------------------------- editable copy -------------------------
REPO_URL = "https://github.com/VedantBhayani/composio-agent-ready-research"
PAGE_TITLE = "100 Apps, Agent-Ready?"
TAGLINE = ("An AI agent researched 100 apps for Composio: how you authenticate, whether access is "
           "self-serve or gated, what API and MCP exist, and what it would take to ship an agent toolkit. "
           "Every claim is backed by a source excerpt, and a human audited a sample.")
LIMITATIONS = [
    "Unknown means no verified evidence was found. It is not a claim that the answer is 'no'. 'None found' for MCP means none was found, not that none exists.",
    "The judge (L1) runs on Mistral Small, the same model family as the extractor. Mistral Large was the plan, but it timed out (>60 s per call) on this key, so the judge is less independent than intended.",
    "Evidence-strict by design: when the docs pages we fetched don't state something (often the go-live approval), the field becomes Unknown even when the answer is 'well known'.",
    "The browser loop (L4) ran on only 8 audit apps. TinyFish browser runs averaged ~17 steps (~$0.30) and run one at a time, so it was capped on cost and time.",
    "The human audit covers 15 apps Ã— 6 claims (90 claims), one person, in about an hour. The confidence intervals are wide, and the human can be wrong too.",
    "Composio coverage is a snapshot of the catalog (1,842 toolkits) taken on 2026-11-23. Matching is exact name, a reviewed alias, or a single-product domain. Renamed toolkits can be missed, and that's preferred over false matches.",
    "Only public docs were read. Pages behind a login and partner portals were not.",
]
VERIFY_LINES = [
    "A human blindly audited 15 apps x 6 claims (a seeded, stratified sample) without seeing the agent's answers.",
    "Pass 1 (frozen) and pass 2 (after verification loops) are both scored against the human answers.",
    "Human corrections are a separate tier (final) and are not counted as loop gains.",
    "Unknown is reported separately as answer rate, so abstaining is not disguised as being right or wrong.",
]
PIPELINE_MAIN = [
    ("Parallel search", "fast web search for candidate sources"),
    ("TinyFish fetch", "page text, cached"),
    ("Mistral Small extraction", "structured fields + verbatim excerpts"),
    ("Composio catalog match", "toolkit slug, tool count"),
    ("Deterministic rules", "buildability, archetype, blocker"),
    ("Pass 1 (frozen)", "baseline snapshot"),
]
PIPELINE_LOOPS = [
    ("L0", "Deterministic excerpt check", "is the excerpt verbatim in the fetched page?"),
    ("L1", "LLM judge", "does the excerpt actually support the claim?"),
    ("L2", "Composio auth cross-check", "toolkit auth schemes vs. our auth claim"),
    ("L3", "Agentic re-pass", "tool-calling search/fetch on disputed claims"),
    ("L4", "TinyFish browser agent", "a real browser navigates the docs; its quotes are re-fetched and must match (audit apps)"),
]
PIPELINE_END = [("Pass 2", "after loops"), ("Human blind audit", "scored against the human"), ("Final", "human corrections tier")]
COMPOSIO_LEDGER = [
    ("C1", "Catalog: toolkit exists, slug and tool count for all 100 apps", "Used",
     "REST v3.1 /toolkits with cursor pagination (1,842 toolkits). The Python SDK's toolkits.get() returned only the first 1,000, with no cursor."),
    ("C2", "Toolkit auth schemes as an independent auth cross-check (L2)", "Used",
     "A disagreement sends the auth field to the agentic re-pass."),
    ("C3", "Agentic re-pass on Composio tools", "Not used",
     "Composio has no Mistral provider, re-pass uses plain Mistral function calling (next step: custom provider)."),
    ("C4", "Recommendations framed as Composio backlog", "Used", ""),
    ("C5", "Composio MCP as tool transport", "Not used", "Adds transport, not accuracy (next step)."),
    ("C6", "Expose dataset as Composio tool/MCP", "Not used", "Out of scope for the time box (next step)."),
    ("C7", "Composio GitHub toolkit for repo", "Not used", "gh CLI simpler."),
]
BACKLOG = [  # (opportunities key, heading, framing)
    ("quick_wins_build_now", "Build now", "Buildable and no Composio toolkit yet: the easy wins."),
    ("app_review", "Build, plan for app review", "Self-serve to build, but going live needs the vendor's app review."),
    ("partner_outreach", "Needs partnership", "Access sits behind a partner program or sales contact: outreach, not engineering."),
    ("mcp_or_skill_only", "Ship as MCP / skill", "No public API, but an MCP server or CLI/library exists."),
    ("paid_plan", "Paid plan", "API access requires a paid tier."),
]

# ------------------------- loading -------------------------
def jl(p):
    p = Path(p)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8-sig").splitlines() if l.strip()]


def jf(p):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else None


def parse_human_log(p):
    rows = []
    if not Path(p).exists():
        return rows
    for line in Path(p).read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("|") and not line.startswith("|---") and "Time (IST)" not in line:
            cells = [c.strip().replace("`", "") for c in line.strip().strip("|").split("|")]
            if len(cells) >= 4:
                rows.append(cells[:4])
    return rows


def main():
    ds = next((n for n in ("final.jsonl", "pass2.jsonl", "pass1.jsonl") if (DATA / n).exists()), None)
    records = jl(DATA / ds)
    pass1 = jl(DATA / "pass1.jsonl")
    if ds == "pass2.jsonl" and len(records) < len(pass1):  # partial pass 2: fill the rest from pass 1
        have = {r["app_id"] for r in records}
        records += [r for r in pass1 if r["app_id"] not in have]
        ds += f" (partial: {len(have)} re-verified, rest from pass1.jsonl)"
    # verdicts are derived: re-apply the current rules so matrix and insights always agree
    import sys
    sys.path.insert(0, str(ROOT))
    from agent import rules
    from agent.schema import AppRecord
    records = [rules.apply(AppRecord(**r)).model_dump() for r in records]
    records.sort(key=lambda r: r["app_id"])
    insights = jf(DATA / "insights.json") or {}
    accuracy = jf(DATA / "accuracy.json")
    changes = jl(DATA / "changes.jsonl")
    runlog = jl(DATA / "run_log.jsonl")
    human = parse_human_log(ROOT / "human_log.md")

    def runcost(r):
        return sum(v for k, v in r.items() if k.endswith("_usd") and isinstance(v, (int, float)))
    run = {"apps": len(runlog), "ok": sum(1 for r in runlog if r.get("ok")),
           "cost": round(sum(runcost(r) for r in runlog), 4),
           "avg_seconds": round(sum(r.get("seconds", 0) for r in runlog) / len(runlog), 1) if runlog else None,
           "tinyfish_fetches": sum(r.get("tinyfish_fetches", 0) or 0 for r in runlog)}
    loop_counts = {}
    for c in changes:
        loop_counts[c["loop"]] = loop_counts.get(c["loop"], 0) + 1
    # before/after examples
    ex = [c for c in changes if c["loop"] in ("L1", "L3", "L4") and c["old"] != c["new"] and c["new"] != "Unknown"]
    seen, examples = set(), []
    for c in ex:  # diversify by loop first
        if c["loop"] not in seen and len(examples) < 3:
            seen.add(c["loop"]); examples.append(c)
    for c in ex:
        if len(examples) < 3 and c not in examples:
            examples.append(c)
    unk = next((c for c in changes if c["loop"] == "unverified->Unknown"), None)
    if unk:
        examples.append(unk)

    bundle = {
        "records": records, "insights": insights, "accuracy": accuracy, "changes": changes,
        "run": run, "loop_counts": loop_counts, "human": human, "examples": examples,
        "dataset": ds, "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "n_pass1": len(pass1),
        "copy": {"limitations": LIMITATIONS, "verify": VERIFY_LINES, "tagline": TAGLINE,
                 "pipeline_main": PIPELINE_MAIN, "pipeline_loops": PIPELINE_LOOPS, "pipeline_end": PIPELINE_END,
                 "ledger": COMPOSIO_LEDGER, "backlog": BACKLOG, "repo": REPO_URL},
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "data.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(records)
    (OUT / "llms.txt").write_text(make_llms(records, insights, accuracy, ds, run, bundle["generated"]), encoding="utf-8")
    blob = json.dumps(bundle, ensure_ascii=False).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = HTML.replace("__TITLE__", PAGE_TITLE).replace("__DATA__", blob)
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print(f"wrote output/ from {ds}: {len(records)} records, {len(changes)} changes, accuracy={'yes' if accuracy else 'pending'}")


def write_csv(records):
    cols = ["app", "category", "archetype", "buildability", "main_blocker", "auth_methods", "dev_access", "prod_gate",
            "public_api", "api_type", "mcp", "composio_slug", "composio_tools", "confidence", "official_docs_url",
            "evidence_count"]
    with open(OUT / "records.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in records:
            ct = r.get("composio_toolkit") or {}
            w.writerow([r["app_name"], r["category"], r["archetype"], r["buildability"], r["main_blocker"],
                        "; ".join(r.get("auth_methods") or []) or "Unknown", r["dev_access"], r["prod_gate"],
                        r["public_api"], r["api_type"], r["mcp"], ct.get("slug") or "", ct.get("tool_count") if ct.get("tool_count") is not None else "",
                        r["confidence"], r.get("official_docs_url") or "", len(r.get("evidence") or [])])


def pc(x):
    return "n/a" if x is None else f"{x * 100:.1f}%"


def make_llms(records, ins, acc, ds, run, gen):
    n = len(records)
    L = [f"# {PAGE_TITLE}", "",
         f"What this is: a researched dataset of {n} apps (auth, access gating, API, MCP, Composio toolkit coverage) "
         "built by an AI agent for Composio, with source evidence per claim.", f"Generated: {gen}. Dataset: {ds}.", "",
         "## Headline numbers"]
    a = ins.get("auth", {})
    L += [f"- OAuth2 in {a.get('oauth_pct')}% of apps; API key in {a.get('api_key_pct')}%.",
          f"- Composio toolkit coverage: {ins.get('composio', {}).get('covered_pct')}% ({ins.get('composio', {}).get('covered')} of {n}).",
          f"- Official MCP server: {ins.get('official_mcp_pct')}% of apps.",
          f"- Main blockers: {json.dumps(ins.get('blockers', {}))}",
          f"- Archetypes: {json.dumps({k: v['count'] for k, v in ins.get('archetypes', {}).items()})}"]
    if acc:
        for k in ("pass1", "pass2", "final"):
            if acc.get(k):
                x = acc[k]
                L.append(f"- Human-audited {k}{' (human-corrected, matches by construction)' if k == 'final' else ''}: precision on answered {pc(x.get('precision_on_answered'))} "
                         f"(95% CI {x.get('precision_ci95')}), answer rate {pc(x.get('answer_rate'))}, checked {x.get('checked')}.")
    else:
        L.append("- Human audit: pending (no accuracy numbers published yet).")
    L += ["", "## Files", "- index.html: the report", "- data.json: full records with evidence and trace",
          "- records.csv: flat table, one row per app", "- llms.txt: this file", "",
          "## Schema (data.json)",
          "- app_name, category, description, official_docs_url",
          "- auth_methods: OAuth2 | API key | Basic | Token | Other (empty = Unknown)",
          "- dev_access: how a developer gets credentials (Free self-serve, Free trial, Paid plan, Approval required, Partner or contact sales, Unknown)",
          "- prod_gate: approval needed to go live (None, App review, Partner program, Unknown)",
          "- public_api, api_type, api_breadth; mcp (Official, Community, Both, None found, Unknown)",
          "- composio_toolkit: exists, slug, tool_count, auth_schemes",
          "- buildability (Yes/Partial/No/Unknown), main_blocker, archetype, confidence",
          "- evidence[]: claim_field, supporting_excerpt, source_url, source_type, fetched_via, excerpt_match, verifier, loop",
          "- trace: queries, urls fetched, loops run, open issues", "",
          "## How verified", *[f"- {s}" for s in VERIFY_LINES],
          f"- Run: {run['apps']} apps, ${run['cost']} total, {run['avg_seconds']}s average per app.", ""]
    return "\n".join(L)


# ------------------------- page -------------------------
HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fbfaf7;--fg:#1d1d1b;--mut:#6b6a64;--line:#e4e1d8;--card:#fff;--acc:#1f5eff;--good:#1a7f4b;--bad:#b3261e;--warn:#a86a00;
--c1:#1f5eff;--c2:#1a7f4b;--c3:#a86a00;--c4:#b3261e;--c5:#7a3fbf;--c6:#0e8a8a;--c7:#8a6d3b;--c8:#8b8b84;--chip:#f0eee6}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe5;--mut:#9e9d95;--line:#2d2c29;--card:#1c1c1a;--acc:#7ca2ff;--good:#53c58a;--bad:#ff8a80;--warn:#e5ad4a;
--c1:#7ca2ff;--c2:#53c58a;--c3:#e5ad4a;--c4:#ff8a80;--c5:#b88ae8;--c6:#4cc9c9;--c7:#c9a96b;--c8:#8b8b84;--chip:#262623}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:1100px;margin:0 auto;padding:0 16px 80px}
h1{font:700 clamp(2rem,6vw,3.4rem)/1.05 Georgia,"Times New Roman",serif;letter-spacing:-.02em;margin:48px 0 12px}
h2{font:700 1.7rem/1.2 Georgia,serif;margin:0 0 8px;letter-spacing:-.01em}h3{margin:24px 0 8px;font-size:1.05rem}
section{padding:48px 0 8px;border-top:1px solid var(--line);margin-top:48px}
.lede{font-size:1.15rem;color:var(--mut);max-width:760px}.headline{font:600 1.35rem/1.35 Georgia,serif;max-width:820px;margin:20px 0 28px}
.sub{color:var(--mut);max-width:760px;margin:0 0 20px}
.grid{display:grid;gap:14px}.g4{grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}.g2{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}
.card .q{font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin-bottom:6px}
.card .a{font:700 1.5rem/1.2 Georgia,serif}.card .d{color:var(--mut);font-size:.9rem;margin-top:6px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:0;margin:24px 0;border:1px solid var(--line);border-radius:10px;background:var(--card)}
.stat{padding:14px 16px;border-right:1px solid var(--line)}.stat b{display:block;font:700 1.6rem Georgia,serif}.stat span{font-size:.82rem;color:var(--mut)}
.mut,.unk{color:var(--mut)}.unk{font-style:italic}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.chip{background:var(--chip);border-radius:999px;padding:2px 10px;font-size:.82rem}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.85rem;margin-top:8px}.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}
.stack{width:100%;height:34px;display:block}
.bars{display:grid;gap:6px}.brow{display:grid;grid-template-columns:minmax(90px,38%) 1fr 44px;gap:8px;align-items:center;font-size:.88rem}
.brow svg{width:100%;height:16px;display:block}.brow .v{text-align:right;font-variant-numeric:tabular-nums}.brow .l{overflow-wrap:anywhere}
.two{display:grid;gap:24px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
.find li,.rec li{margin:6px 0}.block{border-left:4px solid var(--acc);padding:4px 0 4px 18px;margin:20px 0}.block.rec{border-color:var(--c2)}
.tag{font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;color:var(--mut)}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card);max-width:100%}
table{border-collapse:collapse;width:100%;font-size:.88rem}th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);white-space:nowrap;position:sticky;top:0;background:var(--card)}
#matrix tbody tr.r{cursor:pointer}#matrix tbody tr.r:hover{background:var(--chip)}
#mwrap{max-height:640px}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
input,select{font:inherit;font-size:.9rem;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);max-width:100%}
input[type=search]{flex:1 1 220px}
.detail td{background:var(--bg);padding:16px}.detail .ev{border:1px solid var(--line);border-radius:8px;padding:10px;margin:8px 0;background:var(--card);overflow-wrap:anywhere}
.detail blockquote{margin:6px 0;padding-left:10px;border-left:3px solid var(--line);color:var(--mut)}
.badge{display:inline-block;font-size:.72rem;padding:1px 7px;border-radius:5px;border:1px solid var(--line);margin-right:4px;white-space:nowrap}
.ok{color:var(--good)}.no{color:var(--bad)}.warn{color:var(--warn)}
.pipe{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch}.pb{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px;font-size:.88rem;flex:1 1 150px}
.pb small{display:block;color:var(--mut)}.arrow{align-self:center;color:var(--mut)}.pb.loop{border-color:var(--acc)}.pb.hum{border-color:var(--c3)}
.pending{border:2px dashed var(--warn);border-radius:10px;padding:16px;background:var(--card)}
.nowrap{white-space:nowrap}code{background:var(--chip);padding:1px 5px;border-radius:4px;font-size:.85em}
a{color:var(--acc)}footer{border-top:1px solid var(--line);margin-top:64px;padding-top:20px;color:var(--mut);font-size:.9rem}
footer a{margin-right:14px}
@media(max-width:600px){.stat{border-right:0;border-bottom:1px solid var(--line)}.brow{grid-template-columns:minmax(80px,40%) 1fr 36px}}
</style></head><body><main>
<header>
<h1>__TITLE__</h1><p class="lede" id="tagline"></p><p class="headline" id="headline"></p>
<h3 class="tag">The four answers</h3><div class="grid g4" id="answers"></div>
<div class="stats" id="stats"></div>
<h3 class="tag">Archetypes</h3><div id="arch"></div>
</header>

<section id="findings"><h2>Findings and recommendations</h2>
<div class="block"><div class="tag">Findings: what the data says</div><ul class="find" id="findlist"></ul></div>
<div class="block rec"><div class="tag">Recommendations: Composio's backlog</div><div id="reclist"></div></div></section>

<section id="matrix-sec"><h2>The matrix</h2><p class="sub">All apps. Search or filter, then click a row for the evidence, trace and any changes. Unknown values are shown, never hidden.</p>
<div class="filters" id="filters"><input type="search" id="q" placeholder="Search apps, categories, notes" aria-label="Search"></div>
<div class="mut" id="mcount" style="font-size:.85rem"></div>
<div class="tw" id="mwrap"><table id="matrix"><thead><tr></tr></thead><tbody></tbody></table></div></section>

<section id="patterns"><h2>Patterns</h2><div class="two" id="charts"></div></section>

<section id="agent"><h2>The agent</h2><p class="sub">Pipeline from search to a human-audited final dataset.</p>
<div class="pipe" id="pipe"></div><div class="stats" id="runstats"></div>
<h3>Composio: where used and why</h3><div class="tw"><table id="ledger"><thead><tr><th>#</th><th>Use</th><th>Status</th><th>Why / next step</th></tr></thead><tbody></tbody></table></div>
<h3>Where a human was needed</h3><div class="tw"><table id="human"><thead><tr><th>Time (IST)</th><th>Step</th><th>What the human did</th><th>Why the agent couldn't</th></tr></thead><tbody></tbody></table></div></section>

<section id="verification"><h2>Verification</h2><ul id="vlines"></ul><div id="vbody"></div></section>

<section id="method"><h2>Methodology and limitations</h2><ul id="limits"></ul></section>

<footer id="foot"></footer>
</main>
<script type="application/json" id="bundle">__DATA__</script>
<script>
"use strict";
const B=JSON.parse(document.getElementById("bundle").textContent);
const R=B.records,I=B.insights,A=B.accuracy,N=R.length,NS="http://www.w3.org/2000/svg";
const COL=["var(--c1)","var(--c2)","var(--c3)","var(--c4)","var(--c5)","var(--c6)","var(--c7)","var(--c8)"];
function h(tag,attrs,...kids){const e=document.createElement(tag);for(const k in(attrs||{})){if(k==="class")e.className=attrs[k];else if(k==="href"){e.href=attrs[k];e.target="_blank";e.rel="noopener"}else e.setAttribute(k,attrs[k])}
 for(const c of kids.flat()){if(c==null||c===false)continue;e.append(c.nodeType?c:document.createTextNode(String(c)))}return e}
function sv(tag,attrs){const e=document.createElementNS(NS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);return e}
const $=id=>document.getElementById(id);
const pct=(a,b)=>b?Math.round(a/b*1000)/10:0;
const fp=x=>x==null?"n/a":(x*100).toFixed(1)+"%";
const isUnk=v=>v==null||v===""||v==="Unknown"||v==="unknown"||(Array.isArray(v)&&!v.length);
function val(v){const s=Array.isArray(v)?(v.join(", ")||"Unknown"):(v==null||v===""?"Unknown":String(v));return isUnk(v)?h("span",{class:"unk"},"Unknown"):s}
const sorted=o=>Object.entries(o||{}).sort((a,b)=>b[1]-a[1]);
const selfServe=r=>r.dev_access==="Free self-serve"||r.dev_access==="Free trial";
function table(el,rows){const tb=el.querySelector("tbody");for(const r of rows)tb.append(h("tr",{},r.map(c=>h("td",{},c))))}

// ---- A. top
const arch=I.archetypes||{},archE=Object.entries(arch).sort((a,b)=>b[1].count-a[1].count);
const blk=sorted(I.blockers).filter(x=>x[0]!=="None");
const cats=(I.by_category||[]);
$("tagline").textContent=B.copy.tagline;
const NI=I.n_apps||N;
if(NI!==N)document.getElementById("tagline").after(h("p",{class:"pending"},`Note: pattern figures come from insights.json computed on ${NI} apps (${I.dataset}); the matrix below has ${N} records. Re-run analysis/analyze.py then build_page.py to sync.`));
const topArch=archE[0],topBl=blk[0];
{const da=I.dev_access||{},ss=(da["Free self-serve"]||0)+(da["Free trial"]||0),qw=((I.opportunities||{}).quick_wins_build_now||[]).length;
 $("headline").textContent=`Free to start, gated to ship: ${ss} of ${NI} apps let a developer get credentials on their own, `+
 (topBl?`but ${topBl[0].toLowerCase()} before going live is the #1 blocker (${topBl[1]} apps). `:"")+
 `${qw} buildable apps have no Composio toolkit yet: the build-now list.`;}
const au=I.auth||{},opp=I.opportunities||{};
const bigCats=cats.filter(c=>c.n>=3);const pool=bigCats.length?bigCats:cats;
const topSS=[...pool].sort((a,b)=>b.self_serve_pct-a.self_serve_pct||b.n-a.n)[0];
const topG=[...pool].sort((a,b)=>b.gated-a.gated||b.n-a.n)[0];
const cards=[
 ["Which auth dominates?",`OAuth2 ${au.oauth_pct}% vs API key ${au.api_key_pct}%`,`${au.both_pct}% support both. Unknown auth: ${au.unknown||0}.`],
 ["Which categories are self-serve vs gated?",topSS?`Most self-serve: ${topSS.category} (${topSS.self_serve_pct}%)`:"n/a",
   topG?`Most gated: ${topG.category} (${topG.gated} of ${topG.n} gated)`:""],
 ["Most common blocker?",topBl?`${topBl[0]}: ${topBl[1]} apps`:"None",`${(blk.slice(1,3)).map(x=>x[0]+" "+x[1]).join(", ")}`],
 ["Easy wins vs outreach?",`${(opp.quick_wins_build_now||[]).length} build-now vs ${(opp.partner_outreach||[]).length} partner outreach`,
   "Build-now = buildable and no Composio toolkit yet."]];
for(const c of cards)$("answers").append(h("div",{class:"card"},h("div",{class:"q"},c[0]),h("div",{class:"a"},c[1]),h("div",{class:"d"},c[2])));
const stat=(v,l)=>h("div",{class:"stat"},h("b",{},v),h("span",{},l));
const accTxt=()=>{if(!A)return["audit pending","Human audit pending"];const a=A.pass3||A.pass2,b=A.pass1;
 return[`${fp(b&&b.precision_on_answered)} \u2192 ${fp(A.pass2.precision_on_answered)} \u2192 ${fp(a&&a.precision_on_answered)}`,`human-audited precision: pass 1 \u2192 pass 2 (blind) \u2192 pass 3 (fix designed from audit errors, not blind). ${a&&a.checked} claims, 15 apps.`]};
$("stats").append(stat(`${N}/100`,"apps researched"),stat((I.composio||{}).covered_pct+"%","Composio toolkit coverage"),
 stat(I.official_mcp_pct+"%","official MCP server"),stat(...accTxt()));
function stacked(parts,total,label){const s=sv("svg",{class:"stack",viewBox:"0 0 1000 34",preserveAspectRatio:"none",role:"img","aria-label":label});let x=0;
 parts.forEach((p,i)=>{const w=p[1]/total*1000;const r=sv("rect",{x:x,y:0,width:Math.max(w-1.5,0),height:34,fill:COL[i%8],rx:2});const t=sv("title",{});t.textContent=p[0]+": "+p[1];r.append(t);s.append(r);x+=w});return s}
function legend(parts){return h("div",{class:"legend"},parts.map((p,i)=>h("span",{},h("i",{style:"background:"+COL[i%8]}),`${p[0]} (${p[1]})`)))}
const ap=archE.map(([k,v])=>[k,v.count]);$("arch").append(stacked(ap,NI,"Archetype counts"),legend(ap));

// ---- B. findings + recs
const F=[],cmp=I.composio||{},lt=I.long_tail_test||{},pg=I.prod_gate||{};
F.push(`Auth: OAuth2 appears in ${au.oauth_pct}% of apps and API key in ${au.api_key_pct}%; ${au.both_pct}% offer both.`);
const ssN=R.filter(selfServe).length;F.push(`Access: ${ssN} of ${N} apps (${pct(ssN,N)}%) let a developer start with free self-serve or a free trial.`);
if(topSS&&topG)F.push(`By category, ${topSS.category} is the most self-serve (${topSS.self_serve_pct}%) and ${topG.category} has the most gated apps (${topG.gated}).`);
const rev=pg["App review"]||0,unkG=pg["Unknown"]||0;
F.push(`Review-to-ship: ${rev} apps (${pct(rev,NI)}%) need an app review before going live; prod gate is unknown for ${unkG} (${pct(unkG,NI)}%).`);
const mc=I.mcp||{};F.push(`MCP: ${I.official_mcp_pct}% have an official MCP server; ${sorted(mc).map(x=>x[0]+" "+x[1]).join(", ")}.`);
F.push(`Composio coverage: ${cmp.covered} of ${NI} apps (${cmp.covered_pct}%) already have a toolkit, ${cmp.tools_total} tools in total.`);
{const bp=I.buildable_paths||{};if(bp.self_serve_api!=null)F.push(`Two roads to "buildable": ${bp.self_serve_api} apps via a self-serve API with no known go-live gate; ${bp.official_mcp_only} more only via the vendor's own MCP server (their REST API is gated by review, approval, a plan or unverified access). MCP is now the faster path for gated apps.`);}
if(lt.n_with!=null)F.push(`Long-tail test: ${lt.gated_or_unknown_pct_with_toolkit}% of apps with a toolkit are gated or unknown (n=${lt.n_with}), vs ${lt.gated_or_unknown_pct_without_toolkit}% of those without (n=${lt.n_without}).`);
for(const f of F)$("findlist").append(h("li",{},f));
for(const [key,head,frame] of B.copy.backlog){const L=opp[key]||[];
 $("reclist").append(h("h3",{},`${head} (${L.length})`),h("div",{class:"mut"},frame),
  h("div",{class:"chips"},L.length?L.map(o=>h("span",{class:"chip",title:o.note||""},o.app+(o.composio?" \u00b7 "+o.composio:""))):h("span",{class:"mut"},"None in this dataset")))}

// ---- C. matrix
const cols=["App","Category","Archetype","Buildable","Auth","Dev access","Prod gate","MCP","Composio","Confidence"];
for(const c of cols)document.querySelector("#matrix thead tr").append(h("th",{},c));
const uniq=f=>[...new Set(R.map(f))].sort();
const sels={cat:["Category",uniq(r=>r.category),r=>r.category],arch:["Archetype",uniq(r=>r.archetype),r=>r.archetype],
 build:["Buildable",uniq(r=>r.buildability),r=>r.buildability],mcp:["MCP",uniq(r=>r.mcp),r=>r.mcp],
 comp:["Composio toolkit",["yes","no"],r=>(r.composio_toolkit&&r.composio_toolkit.exists)?"yes":"no"],conf:["Confidence",uniq(r=>r.confidence),r=>r.confidence]};
for(const k in sels){const s=h("select",{id:"f_"+k,"aria-label":sels[k][0]},h("option",{value:""},sels[k][0]+": all"),sels[k][1].map(o=>h("option",{value:o},o)));s.onchange=drawM;$("filters").append(s)}
$("q").oninput=drawM;
const chg={};for(const c of B.changes)(chg[c.app_id]=chg[c.app_id]||[]).push(c);
function evEl(e){return h("div",{class:"ev"},h("div",{},h("b",{},e.claim_field)," ",e.claim),
 h("blockquote",{},"\u201c"+(e.supporting_excerpt||"")+"\u201d"),
 h("div",{},h("span",{class:"badge"},e.source_type),h("span",{class:"badge"},"via "+e.fetched_via),
  h("span",{class:"badge "+(e.excerpt_match?"ok":"no")},e.excerpt_match===true?"\u2713 verbatim":e.excerpt_match===false?"\u2717 not verbatim":"match n/a"),
  h("span",{class:"badge "+(e.verifier==="supported"?"ok":e.verifier==="unsupported"?"no":"")},"judge: "+e.verifier),h("span",{class:"badge"},"loop "+e.loop)," ",
  e.source_url?h("a",{href:e.source_url},e.source_title||e.source_url):null))}
function detail(r){const t=r.trace||{},kv=(k,v)=>h("p",{},h("b",{},k+": "),v);
 const L=(a)=>a&&a.length?h("ul",{},a.map(x=>h("li",{},typeof x==="string"?x:JSON.stringify(x)))):h("span",{class:"unk"},"none");
 const cs=chg[r.app_id]||[];
 return h("div",{},kv("Description",r.description||"Unknown"),kv("Docs",r.official_docs_url?h("a",{href:r.official_docs_url},r.official_docs_url):h("span",{class:"unk"},"Unknown")),
  kv("Blocker note",r.blocker_note||h("span",{class:"unk"},"none")),
  kv("Auth notes",r.auth_notes||h("span",{class:"unk"},"none")),
  h("h3",{},`Evidence (${(r.evidence||[]).length})`),(r.evidence||[]).map(evEl),
  h("h3",{},"Changes from verification"),cs.length?h("ul",{},cs.map(c=>h("li",{},h("b",{},c.field+": "),val(c.old)," \u2192 ",val(c.new)," ",h("span",{class:"badge"},c.loop)," ",h("span",{class:"mut"},c.reason)))):h("span",{class:"unk"},"no changes"),
  h("h3",{},"Trace"),kv("Queries",L(t.queries)),kv("URLs fetched",L(t.urls_fetched)),kv("Loops run",(t.loops_run||[]).join(" \u2192 ")||"n/a"),
  kv("L2 Composio note",t.l2_composio?JSON.stringify(t.l2_composio):h("span",{class:"unk"},"none")),
  kv("L4 browser",t.l4_browser?JSON.stringify(t.l4_browser):h("span",{class:"unk"},"not run")),
  kv("Open issues",t.open_issues&&Object.keys(t.open_issues).length?JSON.stringify(t.open_issues):h("span",{class:"unk"},"none")),
  kv("Status",r.verification_status))}
function drawM(){const q=$("q").value.trim().toLowerCase(),tb=document.querySelector("#matrix tbody");tb.textContent="";let n=0;
 for(const r of R){let ok=true;for(const k in sels){const v=$("f_"+k).value;if(v&&sels[k][2](r)!==v)ok=false}
  if(ok&&q&&!(r.app_name+" "+r.category+" "+r.description+" "+r.blocker_note+" "+r.archetype).toLowerCase().includes(q))ok=false;if(!ok)continue;n++;
  const ct=r.composio_toolkit||{};const tr=h("tr",{class:"r",tabindex:"0"},
   h("td",{},h("b",{},r.app_name)),h("td",{},r.category),h("td",{},r.archetype),h("td",{},val(r.buildability)),h("td",{},val(r.auth_methods)),
   h("td",{},val(r.dev_access)),h("td",{},val(r.prod_gate)),h("td",{},val(r.mcp)),
   h("td",{},ct.exists?`${ct.slug} (${ct.tool_count??"?"})`:h("span",{class:"mut"},"none")),h("td",{},r.confidence));
  let d=null;const tog=()=>{if(d){d.remove();d=null}else{d=h("tr",{class:"detail"},h("td",{colspan:cols.length},detail(r)));tr.after(d)}};
  tr.onclick=tog;tr.onkeydown=e=>{if(e.key==="Enter")tog()};tb.append(tr)}
 $("mcount").textContent=`${n} of ${N} apps`}
drawM();

// ---- D. charts
function bars(title,entries,total,colorIdx){const w=h("div",{class:"card"},h("h3",{style:"margin-top:0"},title));const g=h("div",{class:"bars"});const mx=Math.max(1,...entries.map(e=>e[1]));
 for(const [k,v] of entries){const s=sv("svg",{viewBox:"0 0 100 16",preserveAspectRatio:"none","aria-hidden":"true"});
  s.append(sv("rect",{x:0,y:0,width:100,height:16,fill:"var(--chip)",rx:2}),sv("rect",{x:0,y:0,width:Math.max(v/mx*100,v?1:0),height:16,fill:k==="Unknown"?"var(--c8)":COL[colorIdx||0],rx:2}));
  g.append(h("div",{class:"brow"},h("span",{class:"l"},k),s,h("span",{class:"v"},v)))}
 w.append(g);return w}
function stackedCats(){const w=h("div",{class:"card",style:"grid-column:1/-1"},h("h3",{style:"margin-top:0"},"Self-serve vs gated by category"));
 w.append(legend([["Self-serve",""],["Gated",""],["Unknown",""]].map(x=>[x[0],cats.reduce((a,c)=>a+c[x[0]==="Self-serve"?"self_serve":x[0].toLowerCase()],0)])));
 const g=h("div",{class:"bars",style:"margin-top:10px"});
 for(const c of [...cats].sort((a,b)=>b.n-a.n)){const s=sv("svg",{viewBox:"0 0 100 16",preserveAspectRatio:"none"});let x=0;
  [[c.self_serve,0],[c.gated,3],[c.unknown,7]].forEach(([v,ci])=>{const ww=v/c.n*100;s.append(sv("rect",{x:x,y:0,width:Math.max(ww-.4,0),height:16,fill:COL[ci]}));x+=ww});
  g.append(h("div",{class:"brow"},h("span",{class:"l"},c.category),s,h("span",{class:"v"},c.n)))}
 w.append(g);return w}
const C=$("charts");
C.append(bars("Auth methods (apps)",sorted((I.auth||{}).counts).concat((I.auth||{}).unknown?[["Unknown",I.auth.unknown]]:[]),N,0),
 bars("Developer access",sorted(I.dev_access),N,1),stackedCats(),bars("Main blockers",sorted(I.blockers),N,3),
 bars("Composio coverage by category (apps with toolkit)",cats.map(c=>[`${c.category} (of ${c.n})`,c.composio_coverage]).sort((a,b)=>b[1]-a[1]),N,4),
 bars("MCP availability",sorted(I.mcp),N,5));

// ---- E. agent
const P=$("pipe"),cp=B.copy;
const pb=(a,b,cls)=>h("div",{class:"pb "+(cls||"")},h("b",{},a),h("small",{},b));const ar=()=>h("span",{class:"arrow"},"\u2192");
cp.pipeline_main.forEach(x=>{P.append(pb(x[0],x[1]),ar())});
cp.pipeline_loops.forEach(x=>{const n=B.loop_counts[x[0]];P.append(pb(`${x[0]} ${x[1]}`,x[2]+(n!=null?` (${n} changes)`:""),"loop"),ar())});
cp.pipeline_end.forEach((x,i)=>{P.append(pb(x[0],x[1],i?"hum":""));if(i<cp.pipeline_end.length-1)P.append(ar())});
const run=B.run,lc=B.loop_counts;
$("runstats").append(stat(run.apps,"apps in run log"),stat("$"+run.cost,"total cost (search + LLM)"),stat(run.avg_seconds+"s","avg seconds per app"),
 stat(run.tinyfish_fetches,"TinyFish fetches"),
 ...Object.entries(lc).map(([k,v])=>stat(v,"changes: "+k)));
table($("ledger"),cp.ledger.map(r=>[r[0],r[1],h("b",{class:r[2]==="Used"?"ok":"mut"},r[2]),r[3]||"-"]));
table($("human"),B.human);

// ---- F. verification
$("vlines").append(...cp.verify.map(s=>h("li",{},s)));
function pend(){return h("div",{class:"pending"},h("b",{},"Human audit pending."),h("p",{},"No accuracy numbers are published until the blind audit is scored. Automated checks below do not replace it."))}
const V=$("vbody");
if(!A)V.append(pend());
else{const tiers=[["pass1","Pass 1"],["pass2","Pass 2"],["pass3","Pass 3 (L5, not blind)"],["final","Final (human-corrected: matches the human by construction, not a measurement)"]].filter(t=>A[t[0]]);
 const p1=A.pass1,p2=A.pass2,bc1=p1.by_claim,bc2=p2.by_claim,d2=p2.diag_official_mcp_agreement||{};
 const mcpErr=p2.errors.filter(e=>e.claim==="mcp"),mcpBoth=mcpErr.filter(e=>e.human==="Both").length;
 V.append(h("div",{class:"card"},h("b",{},"What the audit says"),h("ul",{},
  h("li",{},`The blind-measured loops (L0–L4) did not improve precision: pass 1 ${fp(p1.precision_on_answered)} (CI ${p1.precision_ci95.map(v=>(v*100).toFixed(0)+"%").join("–")}) vs pass 2 ${fp(p2.precision_on_answered)} (CI ${p2.precision_ci95.map(v=>(v*100).toFixed(0)+"%").join("–")}). The intervals overlap; the difference is noise, not a gain. What the loops did remove was ${p1.unsupported} unsupported claim(s) (pass 1) → ${p2.unsupported} (pass 2).`),
  ...(A.pass3?[h("li",{},`Pass 3 (L5 community-MCP sweep, all 100 apps) raised precision to ${fp(A.pass3.precision_on_answered)} (CI ${A.pass3.precision_ci95.map(v=>(v*100).toFixed(0)+"%").join("–")}); MCP went from ${bc2.mcp.correct} to ${A.pass3.by_claim.mcp.correct} of 15 correct. Caveat: L5 was designed after seeing these audit errors, so this score is not blind and likely flatters it. It also added one new error (Salesforce marked "Both"; the human found official only).`)]:[]),
  h("li",{},`Public API, Composio toolkit and buildability were ${bc2.public_api.correct}/15, ${bc2.composio_toolkit.correct}/15 and ${bc2.buildability.correct||0}/15 correct in pass 2. Errors sit in three fields: auth, access and MCP.`),
  h("li",{},`MCP: ${mcpBoth} of ${mcpErr.length} pass 2 MCP errors are "Official" where the human also found a community repo ("Both"). On whether an official MCP exists, agent and human agree on ${d2.agree}/${d2.n}. The agent did not search GitHub for community servers once it found the vendor's own one.`),
  h("li",{},`Auth is scored as an exact set, so one extra or missing method counts as wrong (${bc2.auth.incorrect} wrong in pass 2). The usual mistake is adding a method the human did not confirm (OAuth2 on Pumble, Plaid and MrScraper; Token on BigCommerce).`),
  h("li",{},`Access got worse in pass 2 (${bc1.access.correct} → ${bc2.access.correct} correct). The browser agent moved Salesforce to "Partner program", and the human found "App review" there. The loops also left free trials labelled "Free self-serve".`))));
 const rows=[["Checked","checked"],["Correct","correct"],["Incorrect","incorrect"],["Abstained (Unknown)","abstained_unknown"],["Unresolved","unresolved"],["Unsupported","unsupported"],
  ["Precision on answered","precision_on_answered",1],["95% CI","precision_ci95",2],["Answer rate","answer_rate",1]];
 const fmt=(x,k,t)=>t===1?fp(x[k]):t===2?(x[k]?x[k].map(v=>(v*100).toFixed(1)+"%").join(" to "):"n/a"):(x[k]??"n/a");
 V.append(h("p",{class:"sub"},`Sample: ${A.sample_apps??"?"} apps, ${A.claims_total??"?"} claims. Scored against the human answers.`));
 const t=h("table",{},h("thead",{},h("tr",{},h("th",{},"Metric"),tiers.map(x=>h("th",{},x[1])))),h("tbody",{},rows.map(r=>h("tr",{},h("td",{},r[0]),tiers.map(x=>h("td",{},fmt(A[x[0]],r[1],r[2])))))));
 V.append(h("div",{class:"tw"},t));
 const bc=new Set();tiers.forEach(x=>Object.keys(A[x[0]].by_claim||{}).forEach(k=>bc.add(k)));
 if(bc.size){V.append(h("h3",{},"By claim (correct / incorrect / abstained)"));
  V.append(h("div",{class:"tw"},h("table",{},h("thead",{},h("tr",{},h("th",{},"Claim"),tiers.map(x=>h("th",{},x[1])))),
   h("tbody",{},[...bc].map(k=>h("tr",{},h("td",{},k),tiers.map(x=>{const b=(A[x[0]].by_claim||{})[k]||{};return h("td",{},`${b.correct||0} / ${b.incorrect||0} / ${b.abstained||0}`)})))))))}
 const errs=(A.pass2||A.pass1||{}).errors||[];V.append(h("h3",{},`Errors (${A.pass2?"pass 2":"pass 1"}: ${errs.length})`));
 V.append(errs.length?h("div",{class:"tw"},h("table",{},h("thead",{},h("tr",{},["App","Claim","Agent said","Human found","Notes"].map(x=>h("th",{},x)))),
  h("tbody",{},errs.map(e=>h("tr",{},h("td",{},e.app),h("td",{},e.claim),h("td",{},val(e.agent)),h("td",{},val(e.human)),h("td",{},e.notes||"")))))):h("p",{class:"mut"},"No errors recorded."))}
V.append(h("h3",{},"AUTOMATED (not human-verified)"));
const au2=A&&A.automated;
if(au2){const ks=["apps","evidence_items","excerpt_verbatim_rate","judge_supported_rate","unknown_core_fields"];
 V.append(h("div",{class:"tw"},h("table",{},h("thead",{},h("tr",{},h("th",{},"Metric"),h("th",{},"Pass 1"),h("th",{},"Pass 2"))),
  h("tbody",{},ks.map(k=>h("tr",{},h("td",{},k.replace(/_/g," ")),["pass1","pass2"].map(p=>{const v=(au2[p]||{})[k];return h("td",{},typeof v==="number"&&k.endsWith("rate")?fp(v):(v??"n/a"))})))))))}
else V.append(h("p",{class:"mut"},"Automated metrics are not yet computed (accuracy.json missing). Live counts: "+
 `${R.reduce((a,r)=>a+(r.evidence||[]).length,0)} evidence items; excerpt verbatim rate ${fp(R.reduce((a,r)=>a+(r.evidence||[]).filter(e=>e.excerpt_match).length,0)/Math.max(1,R.reduce((a,r)=>a+(r.evidence||[]).length,0)))} (automated, not human-verified).`));
V.append(h("h3",{},"Before \u2192 after examples"),h("div",{class:"grid g2"},B.examples.map(c=>h("div",{class:"card"},
 h("b",{},c.app+" \u00b7 "+c.field)," ",h("span",{class:"badge"},c.loop),h("div",{style:"margin:6px 0"},val(c.old)," \u2192 ",val(c.new)),h("div",{class:"d"},c.reason)))));
if(!B.examples.length)V.append(h("p",{class:"mut"},"No changes recorded yet."));

// ---- G/H
const unkF=R.reduce((a,r)=>a+["auth_methods","dev_access","prod_gate","public_api","api_type","mcp"].filter(f=>isUnk(r[f])).length,0);
const defeated=R.filter(r=>r.archetype==="Defeated").map(r=>r.app_name);
const ml=[`Dataset in use: ${B.dataset}. ${N} apps; ${B.n_pass1} in the frozen pass 1.`,
 `${unkF} core fields across all apps are Unknown (kept as Unknown rather than guessed).`,
 `Defeated apps (no usable evidence found): ${defeated.length?defeated.join(", "):"none"}.`];
if(A){const x=A.pass2||{};ml.push(`Human audit sample: ${A.sample_apps} apps, ${A.claims_total} claims; precision CI95 ${x.precision_ci95?x.precision_ci95.map(v=>(v*100).toFixed(0)+"%").join(" to "):"n/a"}.`)}
else ml.push("Human audit not yet scored: no accuracy figures are claimed.");
for(const s of [...ml,...cp.limitations])$("limits").append(h("li",{},s));
$("foot").append(h("a",{href:cp.repo},"Repo"),h("a",{href:cp.repo+"/blob/main/README.md"},"README"),h("a",{href:"data.json"},"data.json"),
 h("a",{href:"records.csv"},"records.csv"),h("a",{href:"llms.txt"},"llms.txt"),h("p",{},`Generated ${B.generated}. Dataset: ${B.dataset}.`));
</script></body></html>
"""

if __name__ == "__main__":
    main()

