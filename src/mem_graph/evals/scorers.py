"""Scoring helpers for mem-graph eval suites."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from ..models.evals import EvalCase, EvalSuite, ScorerName

logger = logging.getLogger(__name__)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return " ".join(without_marks.strip().lower().split())


def exact_match_score(output: str, expected: str) -> float:
    """Return 1.0 for exact semantic equality, otherwise 0.0."""
    if not expected:
        return 1.0 if not output.strip() else 0.0

    try:
        parsed_output = json.loads(output)
        parsed_expected = json.loads(expected)
    except json.JSONDecodeError:
        return 1.0 if _normalize_text(output) == _normalize_text(expected) else 0.0

    return 1.0 if parsed_output == parsed_expected else 0.0


def keyword_score(output: str, expected_keywords: list[str]) -> float:
    """Score based on how many expected keywords appear in the output."""
    if not expected_keywords:
        return 0.0

    output_normalized = _normalize_text(output)
    matches = sum(
        1
        for keyword in expected_keywords
        if _normalize_text(keyword) in output_normalized
    )
    return matches / len(expected_keywords)


@lru_cache(maxsize=256)
def _compile_pattern(pattern: str) -> re.Pattern[str]:
    """Compile a regex pattern once, failing fast on invalid patterns."""
    return re.compile(pattern, re.IGNORECASE | re.MULTILINE)


def regex_score(output: str, pattern: str) -> float:
    """Return 1.0 if the output matches the expected regex pattern."""
    if not pattern:
        return 0.0
    try:
        compiled = _compile_pattern(pattern)
    except re.error as exc:
        logger.warning("Invalid regex pattern %r: %s", pattern, exc)
        return 0.0
    return 1.0 if compiled.search(output) else 0.0


def validate_suite_configuration(suite: EvalSuite) -> None:
    """Fail fast when a suite contains invalid regex configuration."""

    for case in suite.cases:
        scorer = case.scorer or suite.default_scorer
        if scorer != "regex":
            continue
        pattern = case.expected_pattern or ""
        if not pattern:
            raise ValueError(
                f"Eval suite '{suite.suite_name}' case '{case.case_id}' uses regex scoring without expected_pattern."
            )
        try:
            _compile_pattern(pattern)
        except re.error as exc:
            raise ValueError(
                f"Invalid regex in eval suite '{suite.suite_name}' case '{case.case_id}': {pattern!r}"
            ) from exc


def _semantic_token_overlap(output: str, expected: str) -> float:
    output_tokens = {
        token for token in re.findall(r"[a-z0-9_]+", _normalize_text(output)) if token
    }
    expected_tokens = {
        token for token in re.findall(r"[a-z0-9_]+", _normalize_text(expected)) if token
    }
    if not output_tokens or not expected_tokens:
        return exact_match_score(output, expected)

    overlap = len(output_tokens & expected_tokens)
    return overlap / len(output_tokens | expected_tokens)


@lru_cache(maxsize=1)
def _load_sentence_model():
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:  # noqa: BLE001
        logger.debug("Falling back to token-overlap semantic scorer due to error")
        return None


def semantic_similarity_score(output: str, expected: str) -> float:
    """Score semantic similarity using embeddings when available, otherwise token overlap."""
    if not expected:
        return 0.0

    model = _load_sentence_model()
    if model is None:
        return _semantic_token_overlap(output, expected)

    try:
        from sentence_transformers import util

        embeddings = model.encode([output, expected], convert_to_tensor=True)
        similarity = float(util.pytorch_cos_sim(embeddings[0], embeddings[1])[0][0])
        return max(0.0, min(1.0, similarity))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Embedding-based semantic scorer failed, using fallback: %s", exc)
        return _semantic_token_overlap(output, expected)


def score_case_output(
    case: EvalCase,
    output: str,
    *,
    default_scorer: ScorerName,
) -> tuple[ScorerName, float]:
    """Score one case output using either its override or the suite default scorer."""
    scorer = case.scorer or default_scorer
    if scorer == "exact":
        return scorer, exact_match_score(output, case.expected_output)
    if scorer == "keywords":
        return scorer, keyword_score(output, case.expected_keywords)
    if scorer == "regex":
        return scorer, regex_score(output, case.expected_pattern or "")
    return scorer, semantic_similarity_score(output, case.expected_output)


def _field(value: object, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


@dataclass
class HostedTextScorer(Evaluator[Any, Any, Any]):
    """pydantic-evals scorer for hosted dataset cases with text outputs."""

    def evaluate(self, ctx: EvaluatorContext[Any, Any, Any]) -> float:
        output = str(_field(ctx.output, "text", ctx.output))
        expected_output = _field(ctx.expected_output, "text", "")
        scorer = _field(ctx.metadata, "scorer", "semantic")

        if scorer == "exact":
            return exact_match_score(output, str(expected_output))
        if scorer == "keywords":
            return keyword_score(
                output,
                list(_field(ctx.metadata, "expected_keywords", []) or []),
            )
        if scorer == "regex":
            return regex_score(
                output, str(_field(ctx.metadata, "expected_pattern", "") or "")
            )
        return semantic_similarity_score(output, str(expected_output))
