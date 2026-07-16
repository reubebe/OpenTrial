from opentrial.compute.priors import build_prior
from opentrial.integrations import dailymed


def test_label_to_record_keeps_dailymed_as_context_only():
    record = dailymed._label_to_record(
        {
            "setid": "abc-123",
            "title": "METFORMIN tablet",
            "published_date": "Jun 15, 2024",
            "spl_version": "12",
        },
        drug_name="metformin",
    )

    assert record.source == "DailyMed"
    assert record.title == "METFORMIN tablet"
    assert record.year == 2024
    assert record.url.endswith("setid=abc-123")
    assert "SPL version 12" in record.notes
    assert build_prior([record]).records_used == 0


def test_dailymed_search_labels_uses_spls_endpoint(monkeypatch):
    requested = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"data": []}'

    def fake_urlopen(url, timeout):
        requested["url"] = url
        requested["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(dailymed, "urlopen", fake_urlopen)

    payload = dailymed._search_labels("metformin", n=4, timeout=3.0)

    assert payload == {"data": []}
    assert requested["timeout"] == 3.0
    assert requested["url"].startswith(
        "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json?"
    )
    assert "drug_name=metformin" in requested["url"]
    assert "pagesize=4" in requested["url"]
