from opentrial.compute.priors import build_prior
from opentrial.integrations import you_search


def test_extract_results_supports_common_you_payload_shapes():
    assert you_search._extract_results({"hits": [{"title": "hit"}]}) == [{"title": "hit"}]
    assert you_search._extract_results({"results": [{"title": "result"}]}) == [
        {"title": "result"}
    ]
    assert you_search._extract_results(
        {"results": {"web": [{"title": "web"}], "news": [{"title": "news"}]}}
    ) == [{"title": "web"}, {"title": "news"}]
    assert you_search._extract_results({"data": [{"title": "data"}]}) == [
        {"title": "data"}
    ]


def test_result_to_record_keeps_you_search_as_context_only():
    result = {
        "title": "FDA guidance on adaptive designs",
        "url": "https://example.test/guidance",
        "snippet": "Useful regulatory context.",
    }

    record = you_search._result_to_record(
        result,
        indication="Type 2 Diabetes",
        endpoint="HbA1c",
    )

    assert record.source == "You.com"
    assert record.title == "FDA guidance on adaptive designs"
    assert record.url == "https://example.test/guidance"
    assert "Useful regulatory context" in record.notes
    assert build_prior([record]).records_used == 0


def test_result_to_record_supports_snippets_list():
    record = you_search._result_to_record(
        {
            "title": "Adaptive design source",
            "url": "https://example.test/source",
            "snippets": ["First useful sentence.", "Second useful sentence."],
        },
        indication="Type 2 Diabetes",
        endpoint="HbA1c",
    )

    assert "First useful sentence" in record.notes
    assert "Second useful sentence" in record.notes


def test_you_search_uses_index_endpoint(monkeypatch):
    requested = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"results": {"web": []}}'

    def fake_urlopen(request, timeout):
        requested["url"] = request.full_url
        requested["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(you_search, "urlopen", fake_urlopen)

    payload = you_search._search_you("adaptive trial", n=3, timeout=4.0)

    assert payload == {"results": {"web": []}}
    assert requested["timeout"] == 4.0
    assert requested["url"].startswith("https://ydc-index.io/v1/search?")
    assert "query=adaptive+trial" in requested["url"]
    assert "count=3" in requested["url"]


def test_get_you_search_context_skips_non_dict_results(monkeypatch):
    monkeypatch.setattr(
        you_search,
        "_search_you",
        lambda query, n, timeout: {"results": ["a bare string", {"title": "ok", "url": "https://x"}]},
    )

    records = you_search.get_you_search_context("query", n=5)

    # The bare string must be skipped, not crash the adapter.
    assert len(records) == 1
    assert records[0].title == "ok"
