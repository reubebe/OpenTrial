from opentrial.compute.priors import build_prior
from opentrial.integrations import semantic_scholar


def test_paper_to_record_keeps_semantic_scholar_as_context_only():
    paper = {
        "paperId": "abc123",
        "title": "Bayesian adaptive trial design",
        "year": 2024,
        "venue": "Clinical Trials",
        "url": "https://example.test/paper",
        "externalIds": {"DOI": "10.1000/example"},
        "citationCount": 42,
        "authors": [{"name": "A. Author"}, {"name": "B. Author"}],
    }

    record = semantic_scholar._paper_to_record(
        paper,
        condition="Type 2 Diabetes",
        endpoint="HbA1c change from baseline",
    )

    assert record.source == "Semantic Scholar"
    assert record.title == "Bayesian adaptive trial design"
    assert record.year == 2024
    assert record.url == "https://example.test/paper"
    assert "citations: 42" in record.notes
    assert "DOI: 10.1000/example" in record.notes
    assert record.standard_error == 0.0
    assert build_prior([record]).records_used == 0


def test_semantic_scholar_search_uses_graph_endpoint(monkeypatch):
    requested = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"data": []}'

    def fake_urlopen(request, timeout):
        requested["url"] = request.full_url
        requested["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(semantic_scholar, "urlopen", fake_urlopen)

    payload = semantic_scholar._search_papers("diabetes HbA1c", n=3, timeout=4.0)

    assert payload == {"data": []}
    assert requested["timeout"] == 4.0
    assert requested["url"].startswith(
        "https://api.semanticscholar.org/graph/v1/paper/search?"
    )
    assert "query=diabetes+HbA1c" in requested["url"]
    assert "limit=3" in requested["url"]


def test_paper_to_record_clamps_out_of_range_year():
    from datetime import date

    record = semantic_scholar._paper_to_record(
        {"paperId": "x", "title": "An old reference", "year": 1887, "externalIds": {}},
        "diabetes",
        "",
    )

    # A pre-1900 year would fail EvidenceRecord validation; it must be clamped,
    # not crash the whole Semantic Scholar source.
    assert record.year == date.today().year
