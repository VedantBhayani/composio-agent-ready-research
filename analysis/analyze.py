"""Patterns from the final dataset (falls back to pass2, then pass1, and says which).
Writes data/insights.json. Every number here is computed, never typed in."""
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"


def load():
    for name in ("final.jsonl", "pass2.jsonl", "pass1.jsonl"):
        p = D / name
        if p.exists():
            return name, [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    raise SystemExit("no dataset")


def pct(n, d):
    return round(100 * n / d, 1) if d else 0.0


def main():
    src, recs = load()
    n = len(recs)
    auth = Counter(a for r in recs for a in r["auth_methods"])
    auth_unknown = sum(1 for r in recs if not r["auth_methods"])
    oauth_any = sum(1 for r in recs if "OAuth2" in r["auth_methods"])
    key_any = sum(1 for r in recs if "API key" in r["auth_methods"])
    both = sum(1 for r in recs if {"OAuth2", "API key"} <= set(r["auth_methods"]))

    cats = defaultdict(list)
    for r in recs:
        cats[r["category"]].append(r)
    self_serve = {"Free self-serve", "Free trial"}
    by_cat = []
    for c, rs in cats.items():
        ss = sum(r["dev_access"] in self_serve for r in rs)
        gated = sum(r["dev_access"] in ("Paid plan", "Approval required", "Partner or contact sales") for r in rs)
        review = sum(r["prod_gate"] in ("App review", "Partner program") for r in rs)
        unk = sum(r["dev_access"] == "Unknown" for r in rs)
        by_cat.append({"category": c, "n": len(rs), "self_serve": ss, "gated": gated, "unknown": unk,
                       "needs_review_to_ship": review, "self_serve_pct": pct(ss, len(rs)),
                       "composio_coverage": sum(r["composio_toolkit"]["exists"] for r in rs),
                       "official_mcp": sum(r["mcp"] in ("Official", "Both") for r in rs)})
    by_cat.sort(key=lambda x: -x["self_serve_pct"])

    blockers = Counter(r["main_blocker"] for r in recs if r["main_blocker"] != "None")
    arche = Counter(r["archetype"] for r in recs)
    members = defaultdict(list)
    for r in recs:
        members[r["archetype"]].append(r["app_name"])

    def row(r):
        return {"app": r["app_name"], "category": r["category"], "archetype": r["archetype"],
                "buildability": r["buildability"], "blocker": r["main_blocker"],
                "composio": r["composio_toolkit"]["slug"], "tools": r["composio_toolkit"]["tool_count"],
                "mcp": r["mcp"], "note": r["blocker_note"]}

    no_tk = [r for r in recs if not r["composio_toolkit"]["exists"]]
    quick_wins = [row(r) for r in no_tk if r["buildability"] == "Yes"]
    gated_no_tk = [row(r) for r in no_tk if r["buildability"] == "Partial"]
    outreach = [row(r) for r in recs if r["main_blocker"] == "Partner gate"]
    paid = [row(r) for r in recs if r["main_blocker"] in ("Paid plan",)]
    review = [row(r) for r in recs if r["main_blocker"] == "App review"]
    defeated = [row(r) for r in recs if r["archetype"] == "Defeated" or r["buildability"] == "Unknown"]
    mcp_only = [row(r) for r in recs if r["archetype"] in ("MCP-only", "Skill-only")]

    tk = [r for r in recs if r["composio_toolkit"]["exists"]]
    official_mcp = [r for r in recs if r["mcp"] in ("Official", "Both")]
    # long-tail hypothesis: do apps WITHOUT a Composio toolkit skew gated/unknown vs apps with one?
    def gated_or_unknown(rs):
        return pct(sum(r["buildability"] in ("Partial", "No", "Unknown") for r in rs), len(rs))

    ins = {
        "dataset": src, "n_apps": n,
        "auth": {"counts": dict(auth.most_common()), "unknown": auth_unknown, "oauth_any": oauth_any,
                 "api_key_any": key_any, "both_oauth_and_key": both,
                 "oauth_pct": pct(oauth_any, n), "api_key_pct": pct(key_any, n), "both_pct": pct(both, n)},
        "dev_access": dict(Counter(r["dev_access"] for r in recs).most_common()),
        "prod_gate": dict(Counter(r["prod_gate"] for r in recs).most_common()),
        "public_api": dict(Counter(r["public_api"] for r in recs).most_common()),
        "api_type": dict(Counter(r["api_type"] for r in recs).most_common()),
        "mcp": dict(Counter(r["mcp"] for r in recs).most_common()),
        "integration_shape": dict(Counter(r["integration_shape"] for r in recs).most_common()),
        "buildability": dict(Counter(r["buildability"] for r in recs).most_common()),
        "confidence": dict(Counter(r["confidence"] for r in recs).most_common()),
        "archetypes": {k: {"count": v, "apps": sorted(members[k])} for k, v in arche.most_common()},
        "blockers": dict(blockers.most_common()),
        "by_category": by_cat,
        "composio": {"covered": len(tk), "covered_pct": pct(len(tk), n),
                     "tools_total": sum(r["composio_toolkit"]["tool_count"] or 0 for r in tk),
                     "not_covered": sorted(r["app_name"] for r in no_tk)},
        "official_mcp_pct": pct(len(official_mcp), n),
        "long_tail_test": {"gated_or_unknown_pct_with_toolkit": gated_or_unknown(tk),
                           "gated_or_unknown_pct_without_toolkit": gated_or_unknown(no_tk),
                           "n_with": len(tk), "n_without": len(no_tk)},
        "opportunities": {"quick_wins_build_now": quick_wins, "gated_no_toolkit": gated_no_tk,
                          "partner_outreach": outreach, "paid_plan": paid, "app_review": review,
                          "mcp_or_skill_only": mcp_only, "defeated_or_unknown": defeated},
    }
    (D / "insights.json").write_text(json.dumps(ins, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"insights from {src} ({n} apps)")
    print("auth:", ins["auth"]["counts"], "| oauth", ins["auth"]["oauth_pct"], "% key", ins["auth"]["api_key_pct"], "%")
    print("dev_access:", ins["dev_access"]); print("prod_gate:", ins["prod_gate"])
    print("archetypes:", {k: v["count"] for k, v in ins["archetypes"].items()})
    print("blockers:", ins["blockers"]); print("buildability:", ins["buildability"])
    print("composio covered:", ins["composio"]["covered"], "| quick wins:", [x["app"] for x in quick_wins])
    print("long tail:", ins["long_tail_test"])
    for c in by_cat:
        print(f"  {c['category']:<38} self-serve {c['self_serve']}/{c['n']} gated {c['gated']} review {c['needs_review_to_ship']} unk {c['unknown']}")


if __name__ == "__main__":
    main()
