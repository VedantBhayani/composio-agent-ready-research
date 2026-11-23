"""Builds input/applications.json from the 100-app table in the assignment brief (name, website/hint)."""
import json
import re
from pathlib import Path

RAW = {
    "CRM and Sales": [
        ("Salesforce", "salesforce.com"), ("HubSpot", "hubspot.com"), ("Pipedrive", "pipedrive.com"),
        ("Attio", "attio.com"), ("Twenty", "twenty.com (open-source CRM)"), ("Podio", "podio.com"),
        ("Zoho CRM", "zoho.com/crm"), ("Close", "close.com"), ("Copper", "copper.com"),
        ("DealCloud", "api.docs.dealcloud.com")],
    "Support and Helpdesk": [
        ("Zendesk", "zendesk.com"), ("Intercom", "intercom.com"), ("Freshdesk", "freshdesk.com"),
        ("Front", "front.com"), ("Pylon", "usepylon.com"), ("LiveAgent", "liveagent.com"),
        ("Plain", "plain.com"), ("Help Scout", "helpscout.com"), ("Gorgias", "gorgias.com"),
        ("Gladly", "gladly.com")],
    "Communications and Messaging": [
        ("Slack", "slack.com"), ("Twilio", "twilio.com"), ("Zoho Cliq", "zoho.com/cliq"),
        ("Lark (Larksuite)", "open.larksuite.com"), ("Pumble", "pumble.com"), ("Discord", "discord.com"),
        ("Telegram", "core.telegram.org"), ("WhatsApp Business", "developers.facebook.com/docs/whatsapp"),
        ("Aircall", "aircall.io"), ("Vonage", "developer.vonage.com")],
    "Marketing, Ads, Email and Social": [
        ("Google Ads", "developers.google.com/google-ads"),
        ("Meta Ads", "developers.facebook.com/docs/marketing-apis"),
        ("LinkedIn Ads", "learn.microsoft.com/linkedin/marketing"), ("GoHighLevel", "highlevel.stoplight.io"),
        ("Mailchimp", "mailchimp.com/developer"), ("Klaviyo", "developers.klaviyo.com"),
        ("systeme.io", "systeme.io (funnel builder)"), ("Pinterest", "developers.pinterest.com"),
        ("Threads (Meta)", "developers.facebook.com/docs/threads"), ("SendGrid", "sendgrid.com")],
    "Ecommerce": [
        ("Shopify", "shopify.dev"), ("WooCommerce", "woocommerce.com/document/woocommerce-rest-api"),
        ("BigCommerce", "developer.bigcommerce.com"),
        ("Salesforce Commerce Cloud", "developer.salesforce.com/docs/commerce"),
        ("Magento (Adobe Commerce)", "developer.adobe.com/commerce"), ("Squarespace", "developers.squarespace.com"),
        ("Ecwid", "api-docs.ecwid.com"), ("Gumroad", "gumroad.com/api"),
        ("Amazon Selling Partner", "developer-docs.amazon.com/sp-api"), ("fanbasis", "fanbasis.com")],
    "Data, SEO and Scraping": [
        ("DataForSEO", "docs.dataforseo.com"), ("SE Ranking", "seranking.com/api"), ("Ahrefs", "ahrefs.com/api"),
        ("MrScraper", "docs.mrscraper.com"), ("Apify", "docs.apify.com"), ("Firecrawl", "firecrawl.dev"),
        ("Bright Data", "brightdata.com"), ("Sherlock", "github.com/sherlock-project/sherlock"),
        ("Waterfall.io", "waterfall.io (contact/company intel)"), ("Clay", "clay.com")],
    "Developer, Infra and Data platforms": [
        ("GitHub", "docs.github.com/rest"), ("Vercel", "vercel.com/docs/rest-api"), ("Netlify", "docs.netlify.com/api"),
        ("Cloudflare", "developers.cloudflare.com/api"), ("Supabase", "supabase.com/docs"),
        ("Neo4j", "neo4j.com/docs/api"), ("Snowflake", "docs.snowflake.com"),
        ("MongoDB Atlas", "mongodb.com/docs/atlas/api"), ("Datadog", "docs.datadoghq.com/api"),
        ("Sentry", "docs.sentry.io/api")],
    "Productivity and Project Management": [
        ("Notion", "developers.notion.com"), ("Airtable", "airtable.com/developers"), ("Linear", "developers.linear.app"),
        ("Jira", "developer.atlassian.com"), ("Asana", "developers.asana.com"), ("Monday.com", "developer.monday.com"),
        ("ClickUp", "clickup.com/api"), ("Coda", "coda.io/developers"), ("Smartsheet", "smartsheet.com/developers"),
        ("Harvest", "harvestapp.com (help.getharvest.com/api-v2)")],
    "Finance and Fintech": [
        ("Stripe", "stripe.com/docs/api"), ("Plaid", "plaid.com/docs"), ("Binance", "binance-docs.github.io"),
        ("Paygent Connect", "paygent (NMI-powered)"), ("iPayX", "ipayx.ai/docs"), ("QuickBooks", "developer.intuit.com"),
        ("Xero", "developer.xero.com"), ("Brex", "developer.brex.com"), ("Ramp", "docs.ramp.com"),
        ("PitchBook", "pitchbook.com (research API)")],
    "AI, Research and Media-native": [
        ("NotebookLM", "cloud.google.com/gemini (Enterprise API)"), ("Otter AI", "help.otter.ai (MCP server)"),
        ("Fathom", "fathom.video"), ("Consensus", "consensus.app (OAuth requested)"),
        ("Reducto", "reducto.ai (document parsing)"), ("Devin", "docs.devin.ai (MCP)"),
        ("higgsfield", "higgsfield.ai/cli (content suite)"), ("Mermaid CLI", "github.com/mermaid-js/mermaid-cli"),
        ("YouTube Transcript", "transcriptapi.com"), ("Grain", "grain.com (meeting notes)")],
}


def parse_hint(hint: str):
    """'zoho.com/crm' -> url; 'x.com (note)' -> url + note; 'paygent (NMI-powered)' -> no url."""
    note = None
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", hint)
    if m:
        hint, note = m.group(1).strip(), m.group(2).strip()
    url = f"https://{hint}" if "." in hint else None
    return url, note


def main():
    apps, i = [], 0
    for category, rows in RAW.items():
        for name, hint in rows:
            i += 1
            url, note = parse_hint(hint)
            extra = [f"https://{note}"] if note and "." in note and " " not in note else []
            apps.append({"id": i, "name": name, "category": category, "hint_raw": hint,
                         "hint_url": url, "hint_note": note, "seed_urls": ([url] if url else []) + extra})
    assert len(apps) == 100, len(apps)
    out = Path(__file__).parent / "applications.json"
    out.write_text(json.dumps(apps, indent=2), encoding="utf-8")
    print(f"wrote {len(apps)} apps -> {out}")


if __name__ == "__main__":
    main()
