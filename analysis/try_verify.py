"""Dev helper: dry-run the verification loops on named apps without writing pass2.
Usage: python analysis/try_verify.py "Otter AI" Stripe"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx  # noqa: E402

from agent import config as C, verifier as V  # noqa: E402


async def main(names):
    recs = [json.loads(l) for l in C.PASS1.read_text(encoding="utf-8").splitlines() if l.strip()]
    async with httpx.AsyncClient() as h:
        for rec in [r for r in recs if r["app_name"] in names]:
            ch = []
            out = await V.verify_app(rec, h, {"fetches": 15, "browser_runs": 1}, ch)
            print("\n==", rec["app_name"], rec["buildability"], "->", out["buildability"], out["archetype"])
            b = out["trace"].get("l4_browser") or {}
            print("L4", {k: b.get(k) for k in ("status", "steps", "usd", "quotes", "quotes_verified", "fields", "error")})
            for q in b.get("raw_quotes", []):
                print("  Q", q)
            for c in ch:
                print("  CHANGE", c["field"], c["old"], "->", c["new"], c["loop"], "|", c["reason"][:100])


asyncio.run(main(sys.argv[1:]))
