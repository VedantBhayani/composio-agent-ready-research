"""Accuracy from the human's blind judgments only (data/checklist.csv -> YOUR_ANSWER).
Scores pass1 (raw first pass) and pass2 (after automated loops) on the same 15 apps x 6 claims.
--apply: writes data/final.jsonl = pass2 + human corrections on audited apps (tagged), logged in changes.jsonl.

Scoring rules (fixed before seeing results):
- auth: correct iff agent's set of methods == human's set. Agent empty = abstained.
- access: correct iff dev_access matches AND prod_gate does not contradict (agent 'Unknown' never contradicts;
          human blank/Unknown never contradicts). Agent dev_access Unknown = abstained.
- public_api: yes/no must match (type not scored). Agent 'unknown' = abstained.
- mcp: exact match (Official / Community / Both / None found). Agent 'Unknown' = abstained.
- composio_toolkit: exists yes/no must match.
- buildability: exact match. Agent 'Unknown' = abstained.
- human answer blank or '?' = unresolved (excluded from accuracy).
- unsupported (pass1 only meaningful): agent gave a value but none of its excerpts was found verbatim in a fetched page.
"""
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
AUTH = ["OAuth2", "API key", "Basic", "Token", "Other"]
ACCESS = ["Free self-serve", "Free trial", "Paid plan", "Approval required", "Partner or contact sales"]
GATE = ["None", "App review", "Partner program", "Unknown"]
MCP = ["Official", "Community", "Both", "None found"]


def load(p):
    return {r["app_id"]: r for r in (json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip())}


def pick(s, vocab):
    s = (s or "").strip().lower()
    for v in sorted(vocab, key=len, reverse=True):
        if v.lower() in s:
            return v
    return None


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def has_support(rec, field):
    return any(e["claim_field"] == field and e.get("excerpt_match") and e.get("verifier") != "unsupported"
               for e in rec["evidence"])


def judge(claim, truth_raw, rec):
    """returns (outcome, agent_value_str, truth_str, unsupported_flag)"""
    t = (truth_raw or "").strip()
    if not t or t in ("?", "-"):
        return "unresolved", None, t, False
    if claim == "auth":
        truth = {a for a in AUTH if a.lower() in t.lower()}
        if "api_key" in t.lower() or "apikey" in t.lower():
            truth.add("API key")
        if not truth:  # answer outside the allowed values (e.g. a public_api answer in the auth row)
            return "unresolved", None, t, False
        agent = set(rec["auth_methods"])
        if not agent:
            return "abstained", "Unknown", ";".join(sorted(truth)), False
        return ("correct" if agent == truth else "incorrect"), ";".join(sorted(agent)), ";".join(sorted(truth)), not has_support(rec, "auth_methods")
    if claim == "access":
        parts = [p.strip() for p in t.replace("|", ";").split(";")]
        t_dev = pick(parts[0], ACCESS)
        t_gate = pick(parts[1], GATE) if len(parts) > 1 else None
        a_dev, a_gate = rec["dev_access"], rec["prod_gate"]
        av = f"{a_dev} ; {a_gate}"
        if a_dev == "Unknown":
            return "abstained", av, t, False
        ok = a_dev == t_dev and (a_gate == "Unknown" or not t_gate or t_gate == "Unknown" or a_gate == t_gate)
        return ("correct" if ok else "incorrect"), av, f"{t_dev} ; {t_gate}", not has_support(rec, "dev_access")
    if claim == "public_api":
        tv = "yes" if t.lower().startswith("y") else "no" if t.lower().startswith("n") else None
        av = rec["public_api"]
        if av == "unknown":
            return "abstained", av, t, False
        return ("correct" if av == tv else "incorrect"), f"{av} ({rec['api_type']})", t, not has_support(rec, "public_api")
    if claim == "mcp":
        tv = pick(t, MCP) or ("None found" if t.lower().startswith(("no", "none")) else None)
        av = rec["mcp"]
        if av == "Unknown":
            return "abstained", av, t, False
        return ("correct" if av == tv else "incorrect"), av, tv, (av != "None found" and not has_support(rec, "mcp"))
    if claim == "composio_toolkit":
        tv = t.lower().startswith("y")
        av = rec["composio_toolkit"]["exists"]
        return ("correct" if av == tv else "incorrect"), f"{'yes ' + str(rec['composio_toolkit']['slug']) if av else 'no'}", t, False
    if claim == "buildability":
        tv = pick(t, ["Yes", "Partial", "No"])
        av = rec["buildability"]
        if av == "Unknown":
            return "abstained", av, t, False
        return ("correct" if av == tv else "incorrect"), av, tv, False
    raise ValueError(claim)


def score(recs, rows):
    out = Counter()
    by_claim = defaultdict(Counter)
    errors = []
    for row in rows:
        rec = recs.get(int(row["app_id"]))
        if rec is None:
            out["missing"] += 1
            continue
        oc, av, tv, unsup = judge(row["claim"], row["YOUR_ANSWER"], rec)
        out[oc] += 1
        by_claim[row["claim"]][oc] += 1
        if unsup and oc in ("correct", "incorrect"):
            out["unsupported"] += 1
        if oc == "incorrect":
            errors.append({"app": row["app"], "claim": row["claim"], "agent": av, "human": tv,
                           "human_source": row.get("your_source_url", ""), "notes": row.get("notes", "")})
    answered = out["correct"] + out["incorrect"]
    checked = answered + out["abstained"]
    res = {"checked": checked, "correct": out["correct"], "incorrect": out["incorrect"],
           "abstained_unknown": out["abstained"], "unresolved": out["unresolved"], "unsupported": out["unsupported"],
           "precision_on_answered": round(out["correct"] / answered, 3) if answered else None,
           "precision_ci95": wilson(out["correct"], answered),
           "answer_rate": round(answered / checked, 3) if checked else None,
           "strict_accuracy": round(out["correct"] / checked, 3) if checked else None,
           "by_claim": {k: dict(v) for k, v in by_claim.items()}, "errors": errors}
    # diagnostic only (not the headline): does the agent agree on whether an OFFICIAL MCP exists?
    # Separates "missed a community repo" (Official vs Both) from a wrong official claim.
    agree = n = 0
    for row in rows:
        rec = recs.get(int(row["app_id"]))
        if row["claim"] != "mcp" or rec is None or rec["mcp"] == "Unknown":
            continue
        tv = pick(row["YOUR_ANSWER"], MCP)
        if tv is None:
            continue
        n += 1
        agree += (rec["mcp"] in ("Official", "Both")) == (tv in ("Official", "Both"))
    res["diag_official_mcp_agreement"] = {"agree": agree, "n": n}
    return res


def main():
    ck = Path(sys.argv[sys.argv.index("--checklist") + 1]) if "--checklist" in sys.argv else D / "checklist.csv"
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else D / "accuracy.json"
    rows = list(csv.DictReader(open(ck, encoding="utf-8-sig")))
    filled = [r for r in rows if (r.get("YOUR_ANSWER") or "").strip()]
    print(f"checklist rows: {len(rows)}, filled: {len(filled)}")
    p1, p2 = load(D / "pass1.jsonl"), load(D / "pass2.jsonl")
    res = {"sample_apps": sorted({r["app"] for r in rows}), "claims_total": len(rows),
           "pass1": score(p1, rows), "pass2": score(p2, rows)}
    # automated metrics over all 100 (labelled automated, not accuracy)
    def auto(recs):
        ev = [e for r in recs.values() for e in r["evidence"]]
        return {"apps": len(recs), "evidence_items": len(ev),
                "excerpt_verbatim_rate": round(sum(bool(e.get("excerpt_match")) for e in ev) / len(ev), 3) if ev else None,
                "judge_supported_rate": round(sum(e.get("verifier") == "supported" for e in ev) / len(ev), 3) if ev else None,
                "unknown_core_fields": sum(r[f] in ("Unknown", "unknown") or r[f] == [] for r in recs.values()
                                           for f in ("auth_methods", "dev_access", "public_api"))}
    res["automated"] = {"pass1": auto(p1), "pass2": auto(p2)}
    if "--apply" in sys.argv:
        final = apply_corrections(p2, rows)
        res["final"] = score(final, rows)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    for k in ("pass1", "pass2", "final"):
        if k in res:
            s = res[k]
            print(f"{k}: correct {s['correct']}/{s['correct']+s['incorrect']} answered "
                  f"(precision {s['precision_on_answered']}, CI {s['precision_ci95']}), abstained {s['abstained_unknown']}, "
                  f"unresolved {s['unresolved']}, unsupported {s['unsupported']}")


def apply_corrections(p2, rows):
    """Human corrections -> final. Only for audited apps; every change logged with loop='human'."""
    import copy
    final = copy.deepcopy(p2)
    changes = []
    for row in rows:
        rec = final.get(int(row["app_id"]))
        oc, av, tv, _ = judge(row["claim"], row["YOUR_ANSWER"], rec)
        if oc not in ("incorrect", "abstained"):
            continue
        t = row["YOUR_ANSWER"].strip()
        c, before = row["claim"], None
        if c == "auth":
            before, rec["auth_methods"] = rec["auth_methods"], [a for a in AUTH if a.lower() in t.lower()]
        elif c == "access":
            parts = [p.strip() for p in t.replace("|", ";").split(";")]
            before = f"{rec['dev_access']} ; {rec['prod_gate']}"
            rec["dev_access"] = pick(parts[0], ACCESS) or rec["dev_access"]
            if len(parts) > 1 and pick(parts[1], GATE):
                rec["prod_gate"] = pick(parts[1], GATE)
        elif c == "public_api":
            before, rec["public_api"] = rec["public_api"], ("yes" if t.lower().startswith("y") else "no")
        elif c == "mcp":
            before, rec["mcp"] = rec["mcp"], (pick(t, MCP) or "None found")
        else:
            continue  # composio (catalog is authoritative -> investigate, don't overwrite) / buildability (derived)
        rec["verification_status"] = "human_corrected"
        rec["evidence"].append({"claim_field": {"auth": "auth_methods", "access": "dev_access"}.get(c, c),
                                "claim": f"{c} = {t} (human)", "source_url": row.get("your_source_url") or "",
                                "source_title": "human check", "supporting_excerpt": row.get("notes") or "",
                                "source_type": "official", "retrieved_at": "", "fetched_via": "none",
                                "excerpt_match": None, "verifier": "supported", "loop": "human"})
        changes.append({"app_id": rec["app_id"], "app": rec["app_name"], "field": c, "old": before,
                        "new": t, "loop": "human", "reason": row.get("notes") or "human blind check"})
    # recompute derived verdicts
    sys.path.insert(0, str(ROOT))
    from agent import rules
    from agent.schema import AppRecord
    for k, rec in final.items():
        final[k] = rules.apply(AppRecord(**rec)).model_dump()
    with open(D / "final.jsonl", "w", encoding="utf-8") as f:
        for k in sorted(final):
            f.write(json.dumps(final[k], ensure_ascii=False) + "\n")
    prior = [l for l in (D / "changes.jsonl").read_text(encoding="utf-8").splitlines()
             if l.strip() and json.loads(l).get("loop") != "human"]  # idempotent re-runs
    with open(D / "changes.jsonl", "w", encoding="utf-8") as f:
        for l in prior:
            f.write(l + "\n")
        for c in changes:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"human corrections applied: {len(changes)} -> data/final.jsonl")
    return final


if __name__ == "__main__":
    main()

