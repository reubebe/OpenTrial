from opentrial.compute.priors import build_prior
from opentrial.data.demo_evidence import t2d_hba1c_evidence
from opentrial.integrations import gemini
from opentrial.schemas import TrialDesignInput


def test_build_prompt_includes_prior_and_context_records():
    design = TrialDesignInput(
        indication="Type 2 Diabetes",
        endpoint="HbA1c change from baseline",
        target_effect=0.5,
        alpha=0.025,
        desired_power=0.8,
        max_n_per_arm=300,
    )
    evidence = t2d_hba1c_evidence()
    prior = build_prior(evidence)

    prompt = gemini._build_prompt(design, evidence, prior)

    assert "Type 2 Diabetes" in prompt
    assert "HbA1c change from baseline" in prompt
    assert "Prior evidence:" in prompt
    assert "Records used:" in prompt


def test_extract_output_text_supports_interactions_output_text():
    assert gemini._extract_output_text({"output_text": "hello"}) == "hello"


def test_extract_output_text_supports_generate_content_shape():
    data = {
        "candidates": [
            {"content": {"parts": [{"text": "generated"}, {"text": "content"}]}}
        ]
    }

    assert gemini._extract_output_text(data) == "generated\ncontent"


def test_extract_output_text_supports_step_content_shape():
    data = {
        "steps": [
            {"content": [{"type": "text", "text": "first"}, {"type": "image"}]},
            {"content": [{"type": "text", "text": "second"}]},
        ]
    }

    assert gemini._extract_output_text(data) == "first\nsecond"
