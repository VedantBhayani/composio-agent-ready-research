"""Blind human-verification checklist. Sample = 15 apps, seed 42, stratified (1 per category + 5 extra).
Chosen from input/applications.json only, so the sample is independent of the agent's results.
The sheet shows NO agent answers: the human records the truth; analysis/score.py compares afterwards."""
import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = 42

CLAIMS = [
    ("auth", "Which auth methods does the API support?", "any of: OAuth2; API key; Basic; Token; Other  (semicolon-separated)"),
    ("access", "How does a developer get credentials to START, and is extra approval needed to go LIVE?",
     "start = Free self-serve | Free trial | Paid plan | Approval required | Partner or contact sales ;  live = None | App review | Partner program | Unknown   e.g. 'Free self-serve ; None'"),
    ("public_api", "Is there a documented public API (or SDK/CLI)? Type?", "yes/no ; REST | GraphQL | SOAP | SDK-only | CLI/library"),
    ("mcp", "Is there an MCP server?", "Official | Community | Both | None found"),
    ("composio_toolkit", "Does Composio have a toolkit for it? (check composio.dev/toolkits)", "yes <slug> | no"),
    ("buildability", "Could it be an agent toolkit TODAY? (Yes = public API with self-serve/free credentials, or vendor MCP; Partial = API exists but paid/approval/partner gated, or CLI wrappable as skill; No = nothing public)",
     "Yes | Partial | No"),
]


def sample(apps):
    rng = random.Random(SEED)
    by_cat = {}
    for a in apps:
        by_cat.setdefault(a["category"], []).append(a)
    picked = [rng.choice(v) for _, v in sorted(by_cat.items())]
    extra_cats = rng.sample(sorted(by_cat), 5)          # 5 categories get a 2nd app -> max 2 per category
    for c in extra_cats:
        picked.append(rng.choice([a for a in by_cat[c] if a not in picked]))
    return sorted(picked, key=lambda a: a["id"])


def main():
    apps = json.loads((ROOT / "input" / "applications.json").read_text(encoding="utf-8"))
    s = sample(apps)
    (ROOT / "data" / "sample.json").write_text(json.dumps([a["id"] for a in s]), encoding="utf-8")
    # optional: add the URLs the agent looked at (no answers) to save the checker time
    srcs = {}
    p1 = ROOT / "data" / "pass1.jsonl"
    if p1.exists():
        for l in p1.read_text(encoding="utf-8").splitlines():
            r = json.loads(l)
            srcs[r["app_id"]] = [x["url"] for x in r["trace"].get("sources_used", [])][:4]
    out = ROOT / "data" / "checklist.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["app_id", "app", "category", "claim", "question", "allowed_values", "YOUR_ANSWER",
                    "your_source_url", "notes", "hint_url", "pages_the_agent_read (no answers)"])
        for a in s:
            for key, q, allowed in CLAIMS:
                w.writerow([a["id"], a["name"], a["category"], key, q, allowed, "", "", "",
                            a.get("hint_url") or a.get("hint_raw"), " | ".join(srcs.get(a["id"], []))])
    print(f"sample ({len(s)}):", ", ".join(a["name"] for a in s))
    print(f"wrote {out} ({len(s) * len(CLAIMS)} claims)")


if __name__ == "__main__":
    main()
