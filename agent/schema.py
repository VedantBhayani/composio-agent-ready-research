"""Data model. Two layers:
- Extraction*: what the LLM is asked to return (facts + verbatim excerpts), from fetched text only.
- AppRecord: the normalized record we publish, with evidence, derived verdicts and a trace.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

AuthMethod = Literal["OAuth2", "API key", "Basic", "Token", "Other"]
DevAccess = Literal["Free self-serve", "Free trial", "Paid plan", "Approval required",
                    "Partner or contact sales", "Unknown"]
ProdGate = Literal["None", "App review", "Partner program", "Unknown"]
YesNoUnknown = Literal["yes", "no", "unknown"]
ApiType = Literal["REST", "GraphQL", "SOAP", "SDK-only", "CLI/library", "None found", "Unknown"]
ApiBreadth = Literal["Broad", "Moderate", "Narrow", "Unknown"]
Mcp = Literal["Official", "Community", "Both", "None found", "Unknown"]
IntegrationShape = Literal["Hosted API", "MCP server", "Skill (CLI/library)", "Multiple", "None found"]
Buildability = Literal["Yes", "Partial", "No", "Unknown"]
Blocker = Literal["None", "Paid plan", "Partner gate", "App review", "No public interface",
                  "Insufficient evidence"]
Archetype = Literal["Open API", "Open + app review", "Approval gate", "Paid gate", "Partner gate", "MCP-only",
                    "Skill-only", "Access unverified", "Defeated"]
Confidence = Literal["High", "Medium", "Low"]

CORE_FIELDS = ["auth_methods", "dev_access", "prod_gate", "public_api", "api_type", "mcp"]


# ---------- LLM-facing extraction schema ----------
class Ev(BaseModel):
    url: str = Field(description="One of the SOURCE urls given in the input, exactly as written")
    excerpt: str = Field(description="Verbatim sentence copied from that source's text (max ~300 chars)")


class Extraction(BaseModel):
    description: str = Field(description="What the app does, one line, max 20 words")
    official_docs_url: Optional[str] = Field(description="Official developer/API docs URL among the sources, else null")
    auth_methods: list[AuthMethod] = Field(description="Auth methods for the app's API. Empty list if not stated")
    auth_notes: str = Field(description="Short note, e.g. 'Bearer token = API key', 'PAT', or ''")
    auth_evidence: list[Ev]
    dev_access: DevAccess = Field(description="How a developer gets credentials to start")
    dev_access_evidence: list[Ev]
    prod_gate: ProdGate = Field(description="Approval needed before going live / for public apps (app review, partner program)")
    prod_gate_evidence: list[Ev]
    public_api: YesNoUnknown = Field(description="Is there a documented public API (or SDK/CLI) developers can use")
    api_type: ApiType
    api_breadth: ApiBreadth = Field(description="Broad = many resources/endpoints; Narrow = a handful")
    api_evidence: list[Ev]
    mcp: Mcp = Field(description="Official = by the vendor; Community = third-party, shown in a source; None found if nothing in sources")
    mcp_urls: list[str]
    mcp_evidence: list[Ev]
    blocker_note: str = Field(description="Main obstacle to building an agent toolkit, one short sentence, or ''")


# ---------- published record ----------
class Evidence(BaseModel):
    claim_field: str
    claim: str
    source_url: str
    source_title: str = ""
    supporting_excerpt: str
    source_type: Literal["official", "third-party"]
    retrieved_at: str
    fetched_via: Literal["tinyfish", "parallel_index", "browser", "none"] = "none"
    excerpt_match: Optional[bool] = None
    verifier: Literal["supported", "unsupported", "not_run"] = "not_run"
    loop: str = "pass1"


class ComposioToolkit(BaseModel):
    exists: bool
    slug: Optional[str] = None
    name: Optional[str] = None
    tool_count: Optional[int] = None
    auth_schemes: list[str] = []
    match_method: Optional[str] = None


class AppRecord(BaseModel):
    app_id: int
    app_name: str
    category: str
    description: str = ""
    official_docs_url: Optional[str] = None
    auth_methods: list[str] = []          # empty = Unknown
    auth_notes: str = ""
    dev_access: DevAccess = "Unknown"
    prod_gate: ProdGate = "Unknown"
    public_api: YesNoUnknown = "unknown"
    api_type: ApiType = "Unknown"
    api_breadth: ApiBreadth = "Unknown"
    mcp: Mcp = "Unknown"
    mcp_urls: list[str] = []
    integration_shape: IntegrationShape = "None found"
    composio_toolkit: ComposioToolkit = ComposioToolkit(exists=False)
    buildability: Buildability = "Unknown"
    main_blocker: Blocker = "Insufficient evidence"
    blocker_note: str = ""
    archetype: Archetype = "Defeated"
    confidence: Confidence = "Low"
    evidence: list[Evidence] = []
    verification_status: Literal["pass1", "reverified", "human_corrected"] = "pass1"
    trace: dict = {}
    last_verified: str = ""


