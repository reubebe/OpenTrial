from opentrial.compute.priors import build_prior
from opentrial.integrations import openfda


def test_reaction_to_record_keeps_faers_as_context_only():
    record = openfda._reaction_to_record(
        {"term": "NAUSEA", "count": 123},
        drug_or_class="metformin",
    )

    assert record.source == "openFDA FAERS"
    assert record.title == "NAUSEA reports for metformin"
    assert record.n == 123
    assert "cannot establish incidence" in record.notes
    assert build_prior([record]).records_used == 0


def test_openfda_count_reactions_uses_drug_event_endpoint(monkeypatch):
    requested = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"results": []}'

    def fake_urlopen(url, timeout):
        requested["url"] = url
        requested["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(openfda, "urlopen", fake_urlopen)

    payload = openfda._count_reactions("metformin", n=7, timeout=4.0)

    assert payload == {"results": []}
    assert requested["timeout"] == 4.0
    assert requested["url"].startswith("https://api.fda.gov/drug/event.json?")
    assert "count=patient.reaction.reactionmeddrapt.exact" in requested["url"]
    assert "limit=7" in requested["url"]
