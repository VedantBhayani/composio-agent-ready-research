"""Deterministic verdicts. The LLM only supplies facts; these pure functions decide.
Kept tiny so every verdict is explainable in one sentence (and unit-tested in tests/test_rules.py)."""
from .schema import AppRecord

SELF_SERVE = {"Free self-serve", "Free trial"}


def is_cli(r: AppRecord) -> bool:
    return r.api_type == "CLI/library"


def has_official_mcp(r: AppRecord) -> bool:
    return r.mcp in ("Official", "Both")


def integration_shape(r: AppRecord) -> str:
    shapes = []
    if r.public_api == "yes" and not is_cli(r):
        shapes.append("Hosted API")
    if r.mcp in ("Official", "Both", "Community"):
        shapes.append("MCP server")
    if is_cli(r):
        shapes.append("Skill (CLI/library)")
    if not shapes:
        return "None found"
    return shapes[0] if len(shapes) == 1 else "Multiple"


def buildability(r: AppRecord) -> str:
    if r.public_api == "yes" and not is_cli(r) and r.dev_access in SELF_SERVE and r.prod_gate in ("None", "Unknown"):
        return "Yes"
    if has_official_mcp(r):
        return "Yes"  # a buildable path exists today via the vendor's own MCP server (even if the REST API is gated)
    if is_cli(r):
        return "Partial"  # no hosted API, but an open CLI/library can be wrapped as a local skill
    if r.public_api == "yes" and r.dev_access == "Unknown":
        return "Unknown"  # API exists but we could not establish how credentials are obtained
    if r.public_api == "yes":
        return "Partial"  # API exists but gated: paid plan / admin approval / app review / partner
    if r.public_api == "no" and not has_official_mcp(r):
        return "No"
    return "Unknown"


def main_blocker(r: AppRecord) -> str:
    if r.public_api == "no" and not has_official_mcp(r):
        return "No public interface"
    if r.dev_access == "Partner or contact sales" or r.prod_gate == "Partner program":
        return "Partner gate"
    if r.prod_gate == "App review" or r.dev_access == "Approval required":
        return "App review"
    if r.dev_access == "Paid plan":
        return "Paid plan"
    if r.public_api == "unknown" or r.dev_access == "Unknown":
        return "Insufficient evidence"
    return "None"


def archetype(r: AppRecord) -> str:
    if r.public_api == "unknown" and r.dev_access == "Unknown" and not has_official_mcp(r):
        return "Defeated"
    if has_official_mcp(r) and r.public_api != "yes":
        return "MCP-only"
    if is_cli(r):
        return "Skill-only"
    if r.dev_access == "Partner or contact sales" or r.prod_gate == "Partner program":
        return "Partner gate"
    if r.dev_access == "Approval required":
        return "Approval gate"
    if r.dev_access == "Paid plan":
        return "Paid gate"
    if r.dev_access in SELF_SERVE and r.prod_gate == "App review":
        return "Open + app review"
    if r.dev_access in SELF_SERVE:
        return "Open API"
    if r.public_api == "yes":
        return "Access unverified"  # API documented, but how credentials are obtained could not be verified
    return "Defeated"


def confidence(r: AppRecord) -> str:
    core = ["auth_methods", "dev_access", "public_api"]

    def good(e, official_only):
        return (e.excerpt_match is not False and e.verifier != "unsupported"
                and (e.source_type == "official" or not official_only))
    by = {f: [e for e in r.evidence if e.claim_field == f] for f in core}
    if all(any(good(e, True) and e.excerpt_match and e.verifier == "supported" for e in by[f]) for f in core):
        return "High"
    if all(any(good(e, False) for e in by[f]) for f in core):
        return "Medium"
    return "Low"


def apply(r: AppRecord) -> AppRecord:
    r.integration_shape = integration_shape(r)
    r.buildability = buildability(r)
    r.main_blocker = main_blocker(r)
    r.archetype = archetype(r)
    r.confidence = confidence(r)
    return r
