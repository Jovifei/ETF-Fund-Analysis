"""Versioned related-sector lookup. Not an index-constituent or holdings map."""
from functools import lru_cache
import json
from pathlib import Path
from app.core.config import PROJECT_ROOT

@lru_cache(maxsize=1)
def rules():
    path = PROJECT_ROOT / "config" / "sector_search_aliases.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["version"], data["aliases"]

def search_terms(query):
    query = query.strip()
    version, aliases = rules()
    cleaned = query
    for suffix in ("行业板块", "概念板块", "板块"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
            break
    values = aliases.get(cleaned, [cleaned])
    terms = list(dict.fromkeys([query, *values]))[:16]
    return terms, {"query": query, "terms": terms, "version": version,
        "method": "sector_alias" if cleaned in aliases else "literal",
        "expanded": cleaned in aliases and terms != [query],
        "note": "按名称、主题和跟踪指数关联，不代表成分股重叠或同一指数；请核对基金跟踪标的。"}

def matching_reason(inst, terms):
    metadata = inst.metadata_json or {}
    for label, value in (("基金名称", inst.name), ("跟踪指数", inst.benchmark or metadata.get("index_name")),
                         ("主题", inst.theme_l2), ("分类", inst.theme_l1)):
        if value and any(term.lower() in str(value).lower() for term in terms if term):
            return label + "匹配"
    return "代码匹配"
