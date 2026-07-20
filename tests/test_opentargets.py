from opentrial.compute.priors import build_prior
from opentrial.integrations import opentargets


def test_target_to_record_keeps_open_targets_as_context_only():
    row = {
        "score": 0.87,
        "target": {
            "id": "ENSG00000118513",
            "approvedSymbol": "KCNJ11",
            "approvedName": "potassium inwardly rectifying channel subfamily J member 11",
        },
    }
    disease = {"id": "MONDO_0005148", "name": "type 2 diabetes mellitus"}

    record = opentargets._target_to_record(row, disease)

    assert record.evidence_kind == "target_biology"
    assert record.source == "Open Targets"
    assert record.title == "KCNJ11 association with type 2 diabetes mellitus"
    # The association score is context, not a treatment effect: effect stays 0.0
    # and the score is preserved in notes.
    assert record.effect == 0.0
    assert record.standard_error == 0.0
    assert "Association score 0.870" in record.notes
    assert build_prior([record]).records_used == 0


def test_graphql_posts_to_open_targets_endpoint(monkeypatch):
    requested = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"data": {"search": {"hits": []}}}'

    def fake_urlopen(request, timeout):
        requested["url"] = request.full_url
        requested["method"] = request.get_method()
        requested["timeout"] = timeout
        requested["content_type"] = request.headers["Content-type"]
        requested["body"] = request.data.decode("utf-8")
        return FakeResponse()

    monkeypatch.setattr(opentargets, "urlopen", fake_urlopen)

    payload = opentargets._graphql(
        "query Example($term: String!) { search(queryString: $term) { hits { id } } }",
        {"term": "type 2 diabetes"},
        timeout=4.0,
    )

    assert payload == {"data": {"search": {"hits": []}}}
    assert requested["url"] == opentargets.OPEN_TARGETS_GRAPHQL_URL
    assert requested["method"] == "POST"
    assert requested["timeout"] == 4.0
    assert requested["content_type"] == "application/json"
    assert '"type 2 diabetes"' in requested["body"]
