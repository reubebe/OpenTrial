from opentrial.compute.priors import build_prior
from opentrial.integrations import clinicaltrials


def test_study_to_record_marks_registry_precedent_as_not_prior_evidence():
    study = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT12345678",
                "briefTitle": "A trial of example therapy in type 2 diabetes",
            },
            "statusModule": {"startDateStruct": {"date": "2022-03"}},
            "designModule": {"enrollmentInfo": {"count": 120}},
            "outcomesModule": {
                "primaryOutcomes": [{"measure": "HbA1c change from baseline"}]
            },
        }
    }

    record = clinicaltrials._study_to_record(study, indication="Type 2 Diabetes")

    assert record.source == "ClinicalTrials.gov"
    assert record.title == "A trial of example therapy in type 2 diabetes"
    assert record.n == 120
    assert record.year == 2022
    assert record.endpoint == "HbA1c change from baseline"
    assert record.url == "https://clinicaltrials.gov/study/NCT12345678"
    assert record.standard_error == 0.0
    assert build_prior([record]).records_used == 0


def test_fetch_url_uses_v2_studies_endpoint(monkeypatch):
    requested = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"studies": []}'

    def fake_urlopen(url, timeout):
        requested["url"] = url
        requested["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(clinicaltrials, "urlopen", fake_urlopen)

    payload = clinicaltrials._fetch_studies("Type 2 Diabetes", n=5, timeout=3.0)

    assert payload == {"studies": []}
    assert requested["timeout"] == 3.0
    assert requested["url"].startswith("https://clinicaltrials.gov/api/v2/studies?")
    assert "query.term=Type+2+Diabetes" in requested["url"]
    assert "pageSize=5" in requested["url"]


def test_study_to_record_clamps_malformed_start_date():
    from datetime import date

    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT1", "briefTitle": "T"},
            "statusModule": {"startDateStruct": {"date": "0019-01"}},
        }
    }

    record = clinicaltrials._study_to_record(study, indication="x")

    assert record.year == date.today().year
