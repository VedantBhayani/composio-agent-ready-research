"""L0 deterministic checks: was the URL actually fetched, does the excerpt really appear in it, enums valid."""
import re
import unicodedata

from rapidfuzz import fuzz

MATCH_THRESHOLD = 90


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)     # markdown links -> text
    s = re.sub(r"[*_`#>|\\]", " ", s)
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


def excerpt_in_text(excerpt: str, text: str) -> bool:
    e, t = normalize(excerpt), normalize(text)
    if not e or len(e) < 12:
        return False
    if e in t:
        return True
    return fuzz.partial_ratio(e, t) >= MATCH_THRESHOLD
