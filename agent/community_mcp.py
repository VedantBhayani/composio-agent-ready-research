"""L5 / pass 3: community MCP sweep. Designed AFTER the blind audit showed the agent misses community
MCP repos once it finds the vendor's own server (10 of 11 audit MCP errors). Therefore pass 3's audit
score is NOT blind; it is labelled as such everywhere.

Runs on all 100 apps (not just the audited 15). One Parallel search per app. A community server counts
only if a github.com/<owner>/<repo> result whose owner is not the vendor names the app AND "mcp" in
its URL/title/excerpt. Evidence = that result's URL + verbatim search excerpt. pass1/pass2 untouched.
Output: data/pass3.jsonl, changes appended to data/changes.jsonl with loop='L5'."""
import asyncio
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from . import config as C, rules
from .schema import AppRecord, Evidence
from .sources import parallel_search

PASS3 = C.PASS2.parent / "pass3.jsonl"


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def app_key(name):
    return norm(name.split("(")[0])


def vendor_owners(rec):
    """GitHub owners already cited as the vendor's own (official evidence) + owners named like the app."""
    own = set()
    for e in rec["evidence"]:
        u = urlparse(e["source_url"])
        if u.hostname == "github.com" and e.get("source_type") == "official":
            p = u.path.strip("/").split("/")
            if p and p[0]:
                own.add(p[0].lower())
    return own


def community_hits(rec, results):
    key = app_key(rec["app_name"])
    own = vendor_owners(rec)
    hits = []
    for r in results:
        u = urlparse(r.get("url", ""))
        parts = u.path.strip("/").split("/")
        if u.hostname != "github.com" or len(parts) < 2:
            continue
        owner, repo = parts[0].lower(), parts[1].lower()
        if owner in own or norm(owner) == key or norm(owner).startswith(key) or owner in ("modelcontextprotocol",):
            continue  # vendor org or the reference-servers org: not community
        text = " ".join([r.get("url", ""), r.get("title") or ""] + (r.get("excerpts") or []))
        if "mcp" not in text.lower() or key not in norm(text):
            continue
        if "mcp" not in repo or key not in norm(repo):
            continue  # the repo name itself must name the app AND be an MCP server (kills generic matches)
        ex = next((x for x in (r.get("excerpts") or []) if "mcp" in x.lower()), (r.get("excerpts") or [r.get("title") or ""])[0])
        hits.append({"url": r["url"], "title": r.get("title") or "", "excerpt": ex[:400]})
    return hits


async def one(client, rec, sem):
    name = rec["app_name"].split("(")[0].strip()
    async with sem:
        try:
            res = await parallel_search(client, {"name": name}, [f"{name} MCP server github", f"{name} model context protocol server"],
                                        f"Open-source community MCP (Model Context Protocol) server repositories on GitHub for {name}")
        except Exception as e:  # noqa: BLE001
            return rec, [], f"search error: {e}"
    return rec, community_hits(rec, res.get("results", [])), None


async def main():
    recs = [json.loads(l) for l in C.PASS2.read_text(encoding="utf-8").splitlines() if l.strip()]
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient() as client:
        out = await asyncio.gather(*(one(client, r, sem) for r in recs))
    now = datetime.now(timezone.utc).isoformat()
    changes, errors = [], 0
    final = []
    for rec, hits, err in out:
        errors += bool(err)
        old = rec["mcp"]
        new = {"Official": "Both", "None found": "Community", "Unknown": "Community"}.get(old, old) if hits else old
        if new != old:
            h = hits[0]
            rec["evidence"].append(Evidence(claim_field="mcp", claim=f"community MCP server: {h['url']}", source_url=h["url"],
                                            source_title=h["title"], supporting_excerpt=h["excerpt"], source_type="third-party",
                                            retrieved_at=now, fetched_via="parallel_index", excerpt_match=True,
                                            verifier="supported", loop="L5").model_dump())
            rec["mcp"] = new
            changes.append({"app_id": rec["app_id"], "app": rec["app_name"], "field": "mcp", "old": old, "new": new,
                            "loop": "L5", "reason": f"community repo {h['url']} (designed after audit; not blind)"})
        final.append(rules.apply(AppRecord(**rec)).model_dump())
    with open(PASS3, "w", encoding="utf-8") as f:
        for r in sorted(final, key=lambda x: x["app_id"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    prior = [l for l in C.CHANGES.read_text(encoding="utf-8").splitlines()
             if l.strip() and json.loads(l).get("loop") != "L5"]  # idempotent re-runs
    with open(C.CHANGES, "w", encoding="utf-8") as f:
        for l in prior:
            f.write(l + "\n")
        for c in changes:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"pass3: {len(changes)} mcp changes, {errors} search errors -> {PASS3}")
    for c in changes:
        print(f"  {c['app']}: {c['old']} -> {c['new']} | {c['reason'][:90]}")


if __name__ == "__main__":
    asyncio.run(main())
