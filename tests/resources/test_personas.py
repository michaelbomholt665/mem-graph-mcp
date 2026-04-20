"""Tests for the persona natural-language OCEAN rendering (Task 031)."""

from __future__ import annotations

import re

from mem_graph.resources.personas import (
    BigFiveTraits,
    Persona,
    PERSONA_REGISTRY,
    LLMParams,
    render_ocean_trait,
)

# Regex that should NOT appear in any rendered persona preamble
_FLOAT_PATTERN = re.compile(
    r"\b(Openness|Conscientiousness|Extraversion|Agreeableness|Neuroticism)\s*=\s*\d+\.\d+",
    re.IGNORECASE,
)


class TestRenderOceanTrait:
    """Unit tests for the render_ocean_trait() helper."""

    def test_low_openness(self) -> None:
        desc = render_ocean_trait(0.1, "openness")
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_high_conscientiousness(self) -> None:
        desc = render_ocean_trait(0.95, "conscientiousness")
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_mid_extraversion(self) -> None:
        desc = render_ocean_trait(0.5, "extraversion")
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_all_traits_return_strings(self) -> None:
        for trait in ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]:
            for value in [0.0, 0.25, 0.5, 0.75, 1.0]:
                result = render_ocean_trait(value, trait)
                assert isinstance(result, str), f"Expected str for {trait}={value}"
                assert result.strip(), f"Expected non-empty string for {trait}={value}"

    def test_unknown_trait_does_not_crash(self) -> None:
        # Falls back to openness ranges
        result = render_ocean_trait(0.5, "unknown_trait")
        assert isinstance(result, str)


class TestBigFiveToNaturalLanguage:
    """Tests for BigFiveTraits.to_natural_language()."""

    def test_returns_string(self) -> None:
        traits = BigFiveTraits(openness=0.7, conscientiousness=0.9, extraversion=0.3,
                               agreeableness=0.4, neuroticism=0.2)
        result = traits.to_natural_language()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_no_floats(self) -> None:
        traits = BigFiveTraits(openness=0.7, conscientiousness=0.9, extraversion=0.3,
                               agreeableness=0.4, neuroticism=0.2)
        result = traits.to_natural_language()
        # Should not contain raw float numbers in OCEAN= format
        assert not _FLOAT_PATTERN.search(result)

    def test_reproducible(self) -> None:
        traits = BigFiveTraits(openness=0.8, conscientiousness=0.8, extraversion=0.5,
                               agreeableness=0.7, neuroticism=0.1)
        first = traits.to_natural_language()
        second = traits.to_natural_language()
        assert first == second, "Natural language rendering must be deterministic"


class TestPersonaGetSystemInstructions:
    """Tests for Persona.get_system_instructions() natural-language rendering."""

    def test_no_raw_ocean_floats_in_any_registered_persona(self) -> None:
        for key, persona in PERSONA_REGISTRY.items():
            rendered = persona.get_system_instructions()
            match = _FLOAT_PATTERN.search(rendered)
            assert match is None, (
                f"Persona '{key}' still contains raw OCEAN float: '{match.group() if match else ''}'. "
                "Update get_system_instructions() to use natural-language descriptors."
            )

    def test_includes_persona_name(self) -> None:
        persona = Persona(
            name="TestBot",
            role="Test Role",
            description="A test persona.",
            traits=BigFiveTraits(openness=0.7, conscientiousness=0.8,
                                 extraversion=0.5, agreeableness=0.6, neuroticism=0.2),
            params=LLMParams(temperature=0.5),
            base_instructions="Do the test.",
        )
        result = persona.get_system_instructions()
        assert "TestBot" in result

    def test_includes_role(self) -> None:
        persona = Persona(
            name="Bot",
            role="Unique Role XYZ",
            description="Description.",
            traits=BigFiveTraits(),
            params=LLMParams(),
            base_instructions="",
        )
        result = persona.get_system_instructions()
        assert "Unique Role XYZ" in result

    def test_persona_preamble_is_stable(self) -> None:
        """Same persona must produce identical output on every call (cache-safe)."""
        from mem_graph.resources.personas import AUDITOR_PERSONA
        first = AUDITOR_PERSONA.get_system_instructions()
        second = AUDITOR_PERSONA.get_system_instructions()
        assert first == second
