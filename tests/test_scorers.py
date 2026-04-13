from __future__ import annotations

import pytest

import mem_graph.evals.scorers as scorers
from mem_graph.models.evals import EvalCase


@pytest.mark.evals
def test_exact_match_score_handles_json() -> None:
    assert scorers.exact_match_score(
        '{"status": "approved"}',
        '{"status":"approved"}',
    ) == pytest.approx(1.0)
    assert scorers.exact_match_score(
        '{"status":"rejected"}',
        '{"status":"approved"}',
    ) == pytest.approx(0.0)


@pytest.mark.evals
def test_keyword_score_counts_matches() -> None:
    score = scorers.keyword_score(
        "Use os.getenv for the api key and raise if it is missing.",
        ["os.getenv", "api key", "missing"],
    )
    assert score == pytest.approx(1.0)


@pytest.mark.evals
def test_regex_score_matches_pattern() -> None:
    assert scorers.regex_score(
        "except Exception as exc:\n    raise RuntimeError(str(exc))",
        r"except\s+Exception",
    ) == pytest.approx(1.0)


@pytest.mark.evals
def test_semantic_similarity_uses_token_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scorers, "_load_sentence_model", lambda: None)
    near_score = scorers.semantic_similarity_score(
        "bare except hides database errors",
        "bare except hides failures",
    )
    far_score = scorers.semantic_similarity_score(
        "use environment variables for the token",
        "bare except hides failures",
    )
    assert near_score > 0.3
    assert far_score < 0.4


@pytest.mark.evals
def test_score_case_output_uses_case_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scorers, "_load_sentence_model", lambda: None)
    case = EvalCase(
        case_id="audit-clean",
        description="Sanity case",
        prompt="Audit the clean fixture.",
        expected_output="no issues found in the clean addition helper",
        scorer="semantic",
    )
    scorer_name, score = scorers.score_case_output(
        case,
        "No issues found in the clean addition helper.",
        default_scorer="keywords",
    )
    assert scorer_name == "semantic"
    assert score > 0.7
