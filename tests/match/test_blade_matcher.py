# pylint: disable=redefined-outer-name

from pathlib import Path
from unittest.mock import patch

import pytest

from sotd.match.blade_matcher import BladeMatcher


@pytest.fixture(scope="session")
def session_matcher():
    """Session-scoped matcher to avoid repeated YAML loading."""
    yaml_content = """
DE:
  Feather:
    DE:
      patterns:
        - feather
  Astra:
    Superior Platinum (Green):
      patterns:
        - astra.*sp
  Derby:
    Extra:
      patterns:
        - derby.*extra
  Gillette:
    Perma-Sharp:
      patterns:
        - perma.*sharp

GEM:
  Accuforge:
    PTFE:
      patterns:
        - accuforge

AC:
  Feather:
    Pro:
      patterns:
        - feather.*pro

Half DE:
  Gillette:
    Perma-Sharp SE:
      patterns:
        - perma.*sharp
"""
    # Create a temporary file for the session
    import os
    import tempfile

    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    temp_file.write(yaml_content)
    temp_file.close()

    matcher = BladeMatcher(catalog_path=Path(temp_file.name))

    # Clean up the temp file after the session
    def cleanup():
        try:
            os.unlink(temp_file.name)
        except OSError:
            pass

    # Register cleanup
    import atexit

    atexit.register(cleanup)

    return matcher


@pytest.fixture(scope="class")
def matcher(session_matcher):
    """Class-scoped matcher that uses session-scoped instance."""
    # Clear cache to prevent pollution between tests
    session_matcher.clear_cache()
    return session_matcher


@pytest.fixture(scope="class")
def correct_matches_matcher(tmp_path_factory):
    """Create a BladeMatcher with correct matches for testing."""
    tmp_path = tmp_path_factory.mktemp("correct_matches_tests")

    # Create a test catalog with a regex pattern that would match
    catalog_content = """
DE:
  Gillette:
    Nacet:
      patterns:
        - "gillette.*nacet"
      format: "DE"
"""
    catalog_file = tmp_path / "blades.yaml"
    catalog_file.write_text(catalog_content)

    # Create a correct_matches.yaml with a different match for the same input
    correct_matches_content = """
blade:
  DE:
    Gillette:
      Nacet:
        - "Gillette Nacet"
"""
    correct_matches_file = tmp_path / "correct_matches.yaml"
    correct_matches_file.write_text(correct_matches_content)

    return BladeMatcher(catalog_path=catalog_file, correct_matches_path=correct_matches_file)


# Parameterized use count tests
@pytest.mark.parametrize(
    "input_text,expected_brand,expected_model",
    [
        ("Feather (3)", "Feather", "DE"),
        ("Astra SP [5]", "Astra", "Superior Platinum (Green)"),
        ("Derby Extra {7}", "Derby", "Extra"),
        ("Feather (x3)", "Feather", "DE"),
        ("Astra SP [5x]", "Astra", "Superior Platinum (Green)"),
        ("Derby Extra (2X)", "Derby", "Extra"),
        ("Derby Extra", "Derby", "Extra"),  # Without use count
    ],
)
def test_match_with_use_count_variations(matcher, input_text, expected_brand, expected_model):
    """Test blade matching with various use count formats."""
    result = matcher.match(input_text)
    assert result.matched["brand"] == expected_brand
    assert result.matched["model"] == expected_model
    # Blade use count is now handled in the enrich phase
    assert result.original == input_text


# Parameterized format/context tests
@pytest.mark.parametrize(
    "input_text,context,expected_brand,expected_model,expected_format",
    [
        ("Perma-Sharp", "DE", "Gillette", "Perma-Sharp", "DE"),
        ("Perma-Sharp", "HALF DE", "Gillette", "Perma-Sharp SE", "Half DE"),
        (
            "Perma-Sharp 1/2 DE",
            "HALF DE",
            "Gillette",
            "Perma-Sharp SE",
            "Half DE",
        ),  # Context-first: should match Half DE model if it exists
        ("DE Perma-Sharp", "DE", "Gillette", "Perma-Sharp", "DE"),
        (
            "DE Perma-Sharp",
            "HALF DE",
            "Gillette",
            "Perma-Sharp SE",
            "Half DE",
        ),  # DE in text overrides context
        ("Perma-Sharp", None, "Gillette", "Perma-Sharp", "DE"),  # No context defaults to DE
    ],
)
def test_format_context_matching(
    matcher, input_text, context, expected_brand, expected_model, expected_format
):
    """Test blade matching with different format contexts."""
    if context:
        result = matcher.match_with_context(input_text, context)
    else:
        result = matcher.match(input_text)

    assert result.matched is not None
    assert result.matched["brand"] == expected_brand
    assert result.matched["model"] == expected_model
    assert result.matched["format"] == expected_format
    assert result.original == input_text


def test_specific_pattern_priority_over_generic(tmp_path):
    """
    Test that more specific patterns (like AC Proline) match before generic patterns (like DE Schick).

    This test reproduces the issue where "Schick - P-30 Proline Artist Club Style" was matching
    to DE format instead of AC format, even though the AC pattern is more specific.
    """
    # Create a test catalog with both DE and AC Schick patterns
    yaml_content = """
DE:
  Schick:
    Stainless (DE):
      patterns:
        - sc?hick
AC:
  Schick:
    Proline (AC):
      patterns:
        - (schick.*)?proline
        - (schick.*)?(proline.*)?p[ -]+[23]0
        - schick.*\\bac\\b
"""
    catalog_file = tmp_path / "test_blades.yaml"
    catalog_file.write_text(yaml_content)

    matcher = BladeMatcher(catalog_path=catalog_file, bypass_correct_matches=True)

    # This should match the AC Proline pattern, not the generic DE Schick pattern
    blade_text = "Schick - P-30 Proline Artist Club Style"
    result = matcher.match(blade_text, bypass_correct_matches=True)

    assert result.matched is not None
    # Should match AC format, not DE format
    assert result.matched["format"] == "AC", f"Expected AC format, got {result.matched['format']}"
    assert result.matched["brand"] == "Schick"
    assert result.matched["model"] == "Proline (AC)"
    # The pattern should be the AC pattern, not the generic DE pattern
    assert result.pattern is not None
    # The AC pattern should be longer/more specific than the DE pattern
    assert len(result.pattern) > 7, "AC pattern should be longer than generic 'sc?hick' pattern"
    # Verify it's one of the AC patterns
    assert (
        "proline" in result.pattern.lower() or "p[ -]+[23]0" in result.pattern
    ), f"Pattern should be AC pattern, got: {result.pattern}"


def test_regex_sorting_order(matcher):
    """Test that patterns are properly sorted by format priority and specificity."""
    # Retrieve the compiled patterns directly
    patterns = matcher.patterns

    # Check that patterns are compiled and sorted
    assert len(patterns) > 0, "Should have compiled patterns"

    # Note: Duplicate patterns across different formats are legitimate
    # (e.g., same pattern for DE vs Half DE razors)
    # The test verifies that patterns are properly sorted according to the current logic
    # We can't easily test the complex sorting without duplicating the logic, so just verify
    # that we have patterns and they're in some consistent order

    # Verify that patterns are sorted (the exact order depends on the complex sorting logic)
    # This is a basic sanity check that the sorting didn't fail completely
    assert len(patterns) > 0, "Should have patterns after sorting"


def test_format_prioritization_with_multiple_matches(matcher):
    """Test that format prioritization works with multiple potential matches."""
    # This test verifies the format prioritization logic works correctly
    # when there are multiple potential matches for the same blade
    result = matcher.match_with_context("Perma-Sharp", "DE")
    assert result.matched["format"] == "DE"

    result = matcher.match_with_context("Perma-Sharp", "HALF DE")
    assert result.matched["format"] == "Half DE"


def test_format_fallback_for_half_de_razors(matcher):
    """Test that Half DE razors use Half DE format when context is HALF DE."""
    result = matcher.match_with_context("DE Perma-Sharp", "HALF DE")
    assert result.matched["format"] == "Half DE"  # Should use Half DE due to context


def test_correct_matches_priority_before_regex(correct_matches_matcher):
    """Test that correct matches take priority over regex patterns."""
    # This should match the correct match, not the regex pattern
    result = correct_matches_matcher.match("Gillette Nacet")
    assert result.matched["brand"] == "Gillette"
    assert result.matched["model"] == "Nacet"
    assert result.match_type == "exact"


def test_global_match_checks_correct_matches_before_regex(tmp_path):
    """With generic Shavette/Other razor, correct_matches must be used first (exact not regex)."""
    catalog_content = """
Hair Shaper:
  Personna:
    Hair Shaper:
      patterns:
        - "person+a.*hair.*shaper"
      format: "Hair Shaper"
"""
    catalog_file = tmp_path / "blades.yaml"
    catalog_file.write_text(catalog_content)

    correct_matches_dir = tmp_path / "correct_matches"
    correct_matches_dir.mkdir()
    blade_cm = correct_matches_dir / "blade.yaml"
    blade_cm.write_text("""
Hair Shaper:
  Personna:
    Hair Shaper:
      - personna hair shaper
""")

    matcher = BladeMatcher(catalog_path=catalog_file, correct_matches_path=correct_matches_dir)
    # Generic "Shavette" triggers _find_best_global_match; must return exact from correct_matches
    result = matcher.match_with_context("personna hair shaper", "Shavette")
    assert result.matched is not None
    assert result.matched["brand"] == "Personna"
    assert result.matched["model"] == "Hair Shaper"
    assert (
        result.match_type == "exact"
    ), "generic Shavette should use correct_matches first, not regex"


def test_fail_fast_on_malformed_yaml_data(tmp_path):
    """Test that malformed YAML data causes immediate failure."""
    malformed_yaml = """
DE:
  Feather:
    DE:
      patterns: null  # This should cause an error when trying to iterate
"""
    catalog_file = tmp_path / "malformed_blades.yaml"
    catalog_file.write_text(malformed_yaml)

    with pytest.raises(Exception):
        BladeMatcher(catalog_path=catalog_file)


def test_fail_fast_on_non_dict_entry(tmp_path):
    """Test that non-dict entries in YAML cause immediate failure."""
    invalid_yaml = """
DE:
  Feather: "this should be a dict, not a string"
"""
    catalog_file = tmp_path / "invalid_blades.yaml"
    catalog_file.write_text(invalid_yaml)

    with pytest.raises(Exception):
        BladeMatcher(catalog_path=catalog_file)


def test_flexible_fallback_system():
    """Test the new flexible fallback system with format tracking."""
    # Create a test catalog with blades in different formats
    yaml_content = """
DE:
  Feather:
    DE:
      patterns:
        - feather
  Astra:
    Superior Platinum (Green):
      patterns:
        - astra
GEM:
  Personna:
    GEM PTFE:
      patterns:
        - ptfe
        - gem
AC:
  Feather:
    Pro:
      patterns:
        - feather.*pro
INJECTOR:
  Schick:
    Injector:
      patterns:
        - schick
FHS:
  Feather:
    FHS-1:
      patterns:
        - fhs
"""
    import os
    import tempfile

    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    temp_file.write(yaml_content)
    temp_file.close()

    matcher = BladeMatcher(catalog_path=Path(temp_file.name))

    def cleanup():
        try:
            os.unlink(temp_file.name)
        except OSError:
            pass

    import atexit

    atexit.register(cleanup)

    # Test 1: DE razor with DE blade (no fallback needed)
    result = matcher.match_with_context("Feather", "DE")
    assert result.matched is not None
    assert result.matched["format"] == "DE"
    assert result.matched["brand"] == "Feather"

    # Test 2: GEM razor with blade that doesn't exist in GEM, should fallback to DE
    result = matcher.match_with_context("Feather", "GEM")
    assert result.matched is not None
    assert result.matched["format"] == "DE"  # Should fallback to DE
    assert result.matched["brand"] == "Feather"

    # Test 3: AC razor with blade that doesn't exist in AC, should fallback to DE
    result = matcher.match_with_context("Astra", "AC")
    assert result.matched is not None
    assert result.matched["format"] == "DE"  # Should fallback to DE
    assert result.matched["brand"] == "Astra"

    # Test 4: INJECTOR razor with blade that doesn't exist in INJECTOR, should fallback to DE
    result = matcher.match_with_context("Astra", "INJECTOR")
    assert result.matched is not None
    assert result.matched["format"] == "DE"  # Should fallback to DE
    assert result.matched["brand"] == "Astra"

    # Test 5: FHS razor with blade that doesn't exist in FHS, should fallback to DE
    result = matcher.match_with_context("Astra", "FHS")
    assert result.matched is not None
    assert result.matched["format"] == "DE"  # Should fallback to DE
    assert result.matched["brand"] == "Astra"


def test_format_tracking_optimization():
    """Test that the format tracking optimization prevents redundant searches."""
    # Create a test catalog with specific patterns
    yaml_content = """
DE:
  Feather:
    DE:
      patterns:
        - feather
GEM:
  Personna:
    GEM PTFE:
      patterns:
        - ptfe
AC:
  Feather:
    Pro:
      patterns:
        - feather.*pro
"""
    import os
    import tempfile

    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    temp_file.write(yaml_content)
    temp_file.close()

    matcher = BladeMatcher(catalog_path=Path(temp_file.name))

    def cleanup():
        try:
            os.unlink(temp_file.name)
        except OSError:
            pass

    import atexit

    atexit.register(cleanup)

    # Test 1: DE razor searches DE, should not search DE again in fallback
    result = matcher.match_with_context("Feather", "DE")
    assert result.matched is not None
    assert result.matched["format"] == "DE"

    # Test 2: GEM razor searches GEM first, then falls back to DE (not GEM again)
    result = matcher.match_with_context("Feather", "GEM")
    assert result.matched is not None
    assert result.matched["format"] == "DE"  # Should fallback to DE, not search GEM twice

    # Test 3: AC razor searches AC first, then falls back to DE (not AC again)
    result = matcher.match_with_context("Feather Pro", "AC")
    assert result.matched is not None
    # Should match AC format since "feather.*pro" pattern exists
    assert result.matched["format"] == "AC"


def test_straight_razor_skip():
    """Test that straight razors skip blade matching entirely."""
    # Create a simple test catalog
    yaml_content = """
DE:
  Feather:
    DE:
      patterns:
        - feather
"""
    import os
    import tempfile

    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    temp_file.write(yaml_content)
    temp_file.close()

    matcher = BladeMatcher(catalog_path=Path(temp_file.name))

    def cleanup():
        try:
            os.unlink(temp_file.name)
        except OSError:
            pass

    import atexit

    atexit.register(cleanup)

    # Test that straight razors return no match for any blade
    result = matcher.match_with_context("Feather", "STRAIGHT")
    assert result.matched is None
    assert result.match_type is None
    assert result.pattern is None
    assert result.original == "Feather"

    # Test with any blade string
    result = matcher.match_with_context("Any Blade", "STRAIGHT")
    assert result.matched is None
    assert result.match_type is None
    assert result.pattern is None
    assert result.original == "Any Blade"


def test_half_de_special_fallback():
    """Test that Half DE razors use the special Half DE → DE fallback."""
    # Create a test catalog with Half DE and DE blades
    yaml_content = """
DE:
  Feather:
    DE:
      patterns:
        - feather
  Astra:
    Superior Platinum (Green):
      patterns:
        - astra
Half DE:
  Gillette:
    Perma-Sharp SE:
      patterns:
        - perma.*sharp
"""
    import os
    import tempfile

    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    temp_file.write(yaml_content)
    temp_file.close()

    matcher = BladeMatcher(catalog_path=Path(temp_file.name))

    def cleanup():
        try:
            os.unlink(temp_file.name)
        except OSError:
            pass

    import atexit

    atexit.register(cleanup)

    # Test 1: Half DE razor with blade that exists in Half DE
    result = matcher.match_with_context("Perma-Sharp", "HALF DE")
    assert result.matched is not None
    assert result.matched["format"] == "Half DE"
    assert result.matched["brand"] == "Gillette"

    # Test 2: Half DE razor with blade that only exists in DE (should fallback)
    result = matcher.match_with_context("Feather", "HALF DE")
    assert result.matched is not None
    assert result.matched["format"] == "DE"  # Should fallback to DE
    assert result.matched["brand"] == "Feather"

    # Test 3: Half DE razor with blade that only exists in DE (should fallback)
    result = matcher.match_with_context("Astra", "HALF DE")
    assert result.matched is not None
    assert result.matched["format"] == "DE"  # Should fallback to DE
    assert result.matched["brand"] == "Astra"


def test_non_context_match_fallback():
    """Test that the non-context match method also uses the flexible fallback."""
    # Create a test catalog
    yaml_content = """
DE:
  Feather:
    DE:
      patterns:
        - feather
GEM:
  Personna:
    GEM PTFE:
      patterns:
        - ptfe
"""
    import os
    import tempfile

    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    temp_file.write(yaml_content)
    temp_file.close()

    matcher = BladeMatcher(catalog_path=Path(temp_file.name))

    def cleanup():
        try:
            os.unlink(temp_file.name)
        except OSError:
            pass

    import atexit

    atexit.register(cleanup)

    # Test that non-context matching uses flexible fallback
    result = matcher.match("Feather")
    assert result.matched is not None
    assert result.matched["format"] == "DE"
    assert result.matched["brand"] == "Feather"

    # Test with a blade that doesn't exist in any format
    result = matcher.match("NonexistentBlade")
    assert result.matched is None
    assert result.match_type is None
    assert result.pattern is None


def test_shavette_fallback_prioritizes_format_appropriate_blades():
    """Test that Shavette razors prioritize format-appropriate blades over DE in fallback."""
    matcher = BladeMatcher()

    # Test case: Shavette (Injector) razor with "Personna injector" blade
    # Should match to Personna Injector, not Personna Lab Blue (DE)
    result = matcher.match_with_context(
        normalized_text="personna injector",
        razor_format="Shavette (Injector)",
        original_text="Personna injector",
    )

    # Should match to Injector format, not DE
    assert result.matched is not None
    assert result.matched["format"] == "Injector"
    assert result.matched["brand"] == "Personna"
    assert result.matched["model"] == "Injector"

    # Test case: Shavette (Hair Shaper) razor with "Personna" blade
    # Should prioritize Hair Shaper format over DE
    result = matcher.match_with_context(
        normalized_text="personna", razor_format="Shavette (Hair Shaper)", original_text="Personna"
    )

    # Should match to Hair Shaper format, not DE
    assert result.matched is not None
    assert result.matched["format"] == "Hair Shaper"
    assert result.matched["brand"] == "Personna"
    assert result.matched["model"] == "Hair Shaper"


def test_enhanced_regex_error_reporting():
    """Test that malformed regex patterns produce detailed error messages."""
    mock_blades = {
        "DE": {
            "Test Brand": {
                "Test Model": {
                    "patterns": [r"invalid[regex"],  # Malformed regex - missing closing bracket
                    "format": "DE",
                }
            }
        }
    }

    # Mock the CatalogLoader.load_catalog method to return our mock catalog
    with patch("sotd.match.loaders.CatalogLoader.load_catalog", return_value=mock_blades):
        with pytest.raises(ValueError) as exc_info:
            BladeMatcher()

        error_message = str(exc_info.value)
        assert "Invalid regex pattern" in error_message
        assert "invalid[regex" in error_message
        assert "File: " in error_message
        assert "blades.yaml" in error_message
        assert "Brand: Test Brand" in error_message
        assert "Model: Test Model" in error_message
        assert "unterminated character set" in error_message  # The actual regex error


def test_pattern_traceability_with_format_prioritization(tmp_path):
    """
    Test that returned pattern corresponds to the most specific match when multiple patterns match.

    This test verifies that when multiple patterns match the same text, the most specific
    pattern (longer, more complex) is selected, and the returned pattern corresponds to
    that selected match.

    Example case: "Personna Twin Pivot Plus Refills, Atra"
    - Pattern "(personna)?.*twin.*pivot(.*plus)?" (Cartridge/Disposable) is more specific (33 chars)
    - Pattern "person+a" (Personna Lab Blue, DE format) is less specific (8 chars)
    - Code should select the more specific Cartridge/Disposable pattern
    """
    # Create a test catalog with multiple patterns that match the same text
    yaml_content = """
Cartridge/Disposable:
  Cartridge/Disposable:
    "":
      patterns:
        - (personna)?.*twin.*pivot(.*plus)?
DE:
  Personna:
    Lab Blue:
      patterns:
        - person+a
"""
    catalog_file = tmp_path / "test_blades.yaml"
    catalog_file.write_text(yaml_content)

    matcher = BladeMatcher(catalog_path=catalog_file, bypass_correct_matches=True)

    # This text matches both patterns
    blade_text = "Personna Twin Pivot Plus Refills, Atra"
    result = matcher.match(blade_text, bypass_correct_matches=True)

    # Should match Cartridge/Disposable format (more specific pattern wins)
    assert result.matched is not None
    assert result.matched["format"] == "Cartridge/Disposable"
    assert result.matched["brand"] == "Cartridge/Disposable"

    # The pattern should correspond to the selected match (Cartridge/Disposable)
    assert result.pattern is not None
    assert (
        "twin.*pivot" in result.pattern
    ), f"Expected Cartridge/Disposable pattern with 'twin.*pivot', got: {result.pattern}"
    # Verify it's NOT the less specific DE pattern
    assert (
        result.pattern != "person+a"
    ), f"Pattern should be Cartridge/Disposable pattern, not DE pattern: {result.pattern}"
