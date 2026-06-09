import re

from scripts.generate_typical_sentences import DEFAULT_FULL_PAGE_COUNT, iter_full_page_rows


def test_full_page_samples_are_natural_page_text():
    rows = list(iter_full_page_rows(DEFAULT_FULL_PAGE_COUNT))

    assert len(rows) == DEFAULT_FULL_PAGE_COUNT
    for row in rows:
        query = row["query"]
        lower = query.lower()
        assert len(query) >= 1200
        assert row["expected_focus"].lower() in lower
        assert re.search(r"\bpages?\b", lower) is None
        assert re.search(r"\bsections?\b", lower) is None
        for phrase in (
            "full-page sample query",
            "intended central concepts",
            "search expectation",
            "ranking challenge",
            "evidence-routing challenge",
            "final query intent",
            "search engine",
            "top-ranked concepts",
            "first page of search results",
            "current page",
            "current chart excerpt asks",
            "page also contains",
            "chart excerpt also contains",
            "those sections",
            "reason-for-visit section",
            "exam section",
            "participant flow section",
            "completed-results section",
            "different parts of the page",
            "different parts of the note",
            "the page is long",
            "the note is long",
            "licensed-only umls",
            "generic corpus boilerplate",
        ):
            assert phrase not in lower
        if row["style"] == "full_page_lay_language":
            for phrase in (
                "the after-visit summary repeats",
                "reason-for-visit text",
                "exam wording",
                "copied medication lists",
                "routine chart language",
                "active assessment",
                "the team is not making a new care decision",
                "no active issue related",
            ):
                assert phrase not in lower
