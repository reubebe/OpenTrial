from opentrial.compute.priors import build_prior
from opentrial.integrations import pharmgkb


def test_annotation_to_record_keeps_pharmgkb_as_context_only():
    annotation = {
        "accessionId": "PA166104944",
        "name": "rs5219 and metformin response",
        "levelOfEvidence": {"term": "3"},
        "location": {"genes": [{"symbol": "KCNJ11"}]},
        "relatedChemicals": [{"name": "metformin"}],
        "relatedDiseases": [{"name": "Type 2 Diabetes Mellitus"}],
    }

    record = pharmgkb._annotation_to_record(annotation)

    assert record.evidence_kind == "pharmacogenomics"
    assert record.source == "PharmGKB"
    assert record.title == "rs5219 and metformin response"
    assert record.standard_error == 0.0
    assert "Level of evidence: 3" in record.notes
    assert "genes: KCNJ11" in record.notes
    assert "chemicals: metformin" in record.notes
    assert build_prior([record]).records_used == 0


def test_get_json_calls_pharmgkb_rest_endpoint(monkeypatch):
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

    monkeypatch.setattr(pharmgkb, "urlopen", fake_urlopen)

    payload = pharmgkb._get_json(
        "/data/clinicalAnnotation",
        {"relatedChemicals.name": "metformin", "view": "base"},
        timeout=3.0,
    )

    assert payload == {"data": []}
    assert requested["timeout"] == 3.0
    assert requested["url"].startswith(
        "https://api.pharmgkb.org/v1/data/clinicalAnnotation?"
    )
    assert "relatedChemicals.name=metformin" in requested["url"]
    assert "view=base" in requested["url"]
