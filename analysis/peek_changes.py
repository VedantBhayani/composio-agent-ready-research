"""Dev helper: summarize data/changes.jsonl and L4 browser runs."""
import json
import collections as K
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "data"
ch = [json.loads(l) for l in (D / "changes.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
print(len(ch), K.Counter(c["loop"] for c in ch), K.Counter(c["field"] for c in ch))
for c in ch[-45:]:
    print(f"{c['app'][:16]:<16} {c['field']:<12} {str(c['old'])[:26]:<26} -> {str(c['new'])[:26]:<26} {c['loop']:<19} {c['reason'][:80]}")
p2 = [json.loads(l) for l in (D / "pass2.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
for r in p2:
    b = r["trace"].get("l4_browser")
    if b:
        print("L4", r["app_name"], {k: b.get(k) for k in ("status", "steps", "usd", "quotes", "quotes_verified", "fields", "error")})
