from opentrial.compute.priors import build_prior
from opentrial.integrations import pubmed


def test_build_search_term_includes_condition_intervention_and_literature_filters():
    term = pubmed._build_search_term("Type 2 Diabetes", "HbA1c")

    assert "Type 2 Diabetes" in term
    assert "HbA1c" in term
    assert "clinical trial[Publication Type]" in term
    assert "meta-analysis[Publication Type]" in term


def test_summary_to_record_marks_pubmed_citation_as_not_prior_evidence():
    summary = {
        "uid": "12345678",
        "title": "Example randomized trial of diabetes therapy",
        "fulljournalname": "Example Journal",
        "pubdate": "2021 Mar",
    }

    record = pubmed._summary_to_record(summary, condition="Type 2 Diabetes")

    assert record.source == "PubMed"
    assert record.title == "Example randomized trial of diabetes therapy"
    assert record.year == 2021
    assert record.url == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    assert "Example Journal" in record.notes
    assert record.standard_error == 0.0
    assert build_prior([record]).records_used == 0


def test_summary_to_record_extracts_sample_size_for_citation_without_effect():
    # A citation whose abstract reports an N but no usable HbA1c effect should still
    # capture the sample size (so PMID audit can compare it) while staying out of the
    # prior, because its standard error is zero.
    summary = {"uid": "999", "title": "Trial without a clean effect", "pubdate": "2022"}
    abstract = "A randomized study enrolled 412 patients across two arms over 24 weeks."

    record = pubmed._summary_to_record(
        summary,
        condition="Type 2 Diabetes",
        endpoint="HbA1c change from baseline",
        abstract=abstract,
    )

    assert record.n == 412
    assert record.evidence_kind == "citation"
    assert record.standard_error == 0.0
    assert build_prior([record]).records_used == 0


def test_summary_to_record_extracts_hba1c_effect_when_abstract_has_ci():
    summary = {
        "uid": "12345678",
        "title": "Example randomized trial of diabetes therapy",
        "fulljournalname": "Example Journal",
        "pubdate": "2021 Mar",
    }
    abstract = (
        "In 240 patients, treatment reduced HbA1c by -0.54 percentage points "
        "versus control (95% CI -0.76 to -0.32)."
    )

    record = pubmed._summary_to_record(
        summary,
        condition="Type 2 Diabetes",
        endpoint="HbA1c change from baseline",
        abstract=abstract,
    )

    assert record.effect == 0.54
    assert round(record.standard_error, 3) == 0.112
    assert record.n == 240
    assert build_prior([record]).records_used == 1


def test_fetch_pubmed_abstracts_parses_efetch_xml(monkeypatch):
    xml = """
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>111</PMID>
          <Article>
            <Abstract>
              <AbstractText>First sentence.</AbstractText>
              <AbstractText Label="RESULTS">Second sentence.</AbstractText>
            </Abstract>
          </Article>
        </MedlineCitation>
      </PubmedArticle>
    </PubmedArticleSet>
    """

    def fake_get_xml(endpoint, params, timeout):
        assert endpoint == "efetch.fcgi"
        assert params["id"] == "111"
        return pubmed.ElementTree.fromstring(xml)

    monkeypatch.setattr(pubmed, "_get_xml", fake_get_xml)

    assert pubmed._fetch_pubmed_abstracts(["111"], timeout=4.0) == {
        "111": "First sentence. Second sentence."
    }


def test_get_pubmed_effects_runs_esearch_then_esummary(monkeypatch):
    calls = []

    def fake_get_json(endpoint, params, timeout):
        calls.append((endpoint, params, timeout))
        if endpoint == "esearch.fcgi":
            return {"esearchresult": {"idlist": ["111", "222"]}}
        return {
            "result": {
                "uids": ["111", "222"],
                "111": {"uid": "111", "title": "First paper", "pubdate": "2020"},
                "222": {"uid": "222", "title": "Second paper", "pubdate": "2022"},
            }
        }

    monkeypatch.setattr(pubmed, "_get_json", fake_get_json)
    monkeypatch.setattr(pubmed, "_fetch_pubmed_abstracts", lambda pmids, timeout: {})

    records = pubmed.get_pubmed_effects("Diabetes", "HbA1c", n=2, timeout=4.0)

    assert [record.title for record in records] == ["First paper", "Second paper"]
    assert calls[0][0] == "esearch.fcgi"
    assert calls[0][1]["db"] == "pubmed"
    assert calls[0][1]["retmax"] == "2"
    assert calls[0][2] == 4.0
    assert calls[1][0] == "esummary.fcgi"
    assert calls[1][1]["id"] == "111,222"



def test_extract_continuous_effect_generalizes_to_non_hba1c_endpoint():
    # The extractor should handle any continuous endpoint with a unit + 95% CI,
    # not just HbA1c. Here: systolic blood pressure in mmHg.
    abstract = (
        "Systolic blood pressure was reduced by 5.2 mmHg compared with placebo "
        "(95% CI 3.1 to 7.3) across 300 participants."
    )
    extracted = pubmed._extract_continuous_effect(abstract, "Systolic blood pressure")

    assert extracted is not None
    assert extracted["effect"] == 5.2
    assert round(extracted["standard_error"], 3) == 1.071
    assert extracted["n"] == 300
    assert "mmHg" in extracted["basis"]


def test_extract_continuous_effect_rejects_effect_without_ci():
    # Conservative by design: an effect with no 95% CI yields no usable estimate,
    # because the CI is what produces the standard error.
    abstract = "HbA1c was reduced by 0.5 percentage points versus control."
    assert pubmed._extract_continuous_effect(abstract, "HbA1c change from baseline") is None


def test_extract_continuous_effect_ignores_baseline_value():
    # A baseline level (no between-arm difference word) must not be read as an effect.
    abstract = "Mean HbA1c at baseline was 7.2% in the cohort (95% CI 7.0 to 7.4)."
    assert pubmed._extract_continuous_effect(abstract, "HbA1c") is None
