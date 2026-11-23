import pytest
from pydantic import ValidationError

from agent.checks import excerpt_in_text
from agent.composio_layer import match
from agent.schema import AppRecord, Extraction

PAGE = """# API keys\n\nStripe uses **API keys** to authenticate requests from your integration.
See [the dashboard](https://dashboard.stripe.com) to   manage keys."""


def test_excerpt_exact_and_whitespace_markdown_tolerant():
    assert excerpt_in_text("Stripe uses API keys to authenticate requests from your integration.", PAGE)
    assert excerpt_in_text("See the dashboard to manage keys.", PAGE)


def test_excerpt_rejects_paraphrase_and_fabrication():
    assert not excerpt_in_text("Stripe requires OAuth2 for every request made by integrations.", PAGE)
    assert not excerpt_in_text("short", PAGE)


def test_enums_are_enforced():
    with pytest.raises(ValidationError):
        AppRecord(app_id=1, app_name="X", category="C", dev_access="Free forever")


def test_extraction_schema_rejects_unknown_auth_method():
    with pytest.raises(ValidationError):
        Extraction(description="", official_docs_url=None, auth_methods=["Magic"], auth_notes="", auth_evidence=[],
                   dev_access="Unknown", dev_access_evidence=[], prod_gate="Unknown", prod_gate_evidence=[],
                   public_api="unknown", api_type="Unknown", api_breadth="Unknown", api_evidence=[],
                   mcp="Unknown", mcp_urls=[], mcp_evidence=[], blocker_note="")


def test_composio_match_is_exact_not_fuzzy():
    # shared-domain apps must not match a sibling product (zoho.com hosts many Zoho toolkits)
    m = match({"name": "Salesforce Commerce Cloud", "seed_urls": ["https://developer.salesforce.com/docs/commerce"]})
    assert not m.exists
    assert match({"name": "Stripe", "seed_urls": ["https://stripe.com/docs/api"]}).slug == "stripe"
