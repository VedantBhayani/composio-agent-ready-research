"""CLI.
  python -m agent run                     # all 100, resumes from data/pass1.jsonl
  python -m agent run --app Stripe --app "LinkedIn Ads"
  python -m agent run --limit 10
"""
import argparse
import asyncio

from . import pipeline


def main():
    p = argparse.ArgumentParser(prog="agent")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="pass 1 research")
    r.add_argument("--app", action="append", help="app name or id (repeatable)")
    r.add_argument("--limit", type=int)
    sub.add_parser("verify", help="pass 2: verification loops L0-L3")
    sub.add_parser("browser", help="L4: TinyFish browser agent on the audit sample (updates pass2)")
    a = p.parse_args()
    if a.cmd == "run":
        asyncio.run(pipeline.run(a.app, a.limit))
    elif a.cmd == "verify":
        from . import verifier
        asyncio.run(verifier.run())
    elif a.cmd == "browser":
        from . import verifier
        asyncio.run(verifier.run_browser())


if __name__ == "__main__":
    main()
