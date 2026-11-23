"""The verdict rules are the part an interviewer will probe: they must behave exactly as documented."""
from agent import rules
from agent.schema import AppRecord


def rec(**kw):
    base = dict(app_id=1, app_name="X", category="C", public_api="yes", api_type="REST",
                dev_access="Free self-serve", prod_gate="None", mcp="None found")
    base.update(kw)
    return rules.apply(AppRecord(**base))


def test_open_api_is_buildable():
    r = rec()
    assert (r.buildability, r.archetype, r.main_blocker) == ("Yes", "Open API", "None")


def test_app_review_is_still_buildable_but_flagged():
    r = rec(prod_gate="App review")
    assert r.buildability == "Partial" and r.archetype == "Open + app review" and r.main_blocker == "App review"


def test_partner_gate():
    r = rec(dev_access="Partner or contact sales")
    assert r.buildability == "Partial" and r.archetype == "Partner gate" and r.main_blocker == "Partner gate"


def test_paid_plan_is_public_api_but_partial():
    r = rec(dev_access="Paid plan")
    assert r.buildability == "Partial" and r.archetype == "Paid gate" and r.main_blocker == "Paid plan"


def test_official_mcp_makes_it_buildable_even_without_rest():
    r = rec(public_api="no", api_type="None found", mcp="Official", dev_access="Unknown")
    assert r.buildability == "Yes" and r.archetype == "MCP-only" and r.integration_shape == "MCP server"


def test_cli_is_a_skill():
    r = rec(api_type="CLI/library", dev_access="Free self-serve")
    assert r.buildability == "Partial" and r.archetype == "Skill-only" and r.integration_shape == "Skill (CLI/library)"


def test_no_public_interface():
    r = rec(public_api="no", api_type="None found", dev_access="Unknown")
    assert r.buildability == "No" and r.main_blocker == "No public interface"


def test_unknown_access_is_not_guessed():
    r = rec(dev_access="Unknown")
    assert r.buildability == "Unknown" and r.main_blocker == "Insufficient evidence"


def test_defeated_when_nothing_known():
    r = rec(public_api="unknown", api_type="Unknown", dev_access="Unknown")
    assert r.archetype == "Defeated" and r.buildability == "Unknown"
