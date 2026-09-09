from app.workspace.catalog_search import search_terms


def test_sector_search_expansion_is_explicit_for_the_ui():
    terms, context = search_terms("元器件")
    assert context["expanded"] is True
    assert context["method"] == "sector_alias"
    assert "半导体" in terms
    assert search_terms("510300.SH")[1]["expanded"] is False
