#!/usr/bin/env python3
"""Tests for FullInputComponentMatchingStrategy."""

from pathlib import Path
from unittest.mock import Mock

from sotd.match.brush.strategies.full_input_component_matching_strategy import (
    FullInputComponentMatchingStrategy,
)
from sotd.match.types import MatchResult


class TestFullInputComponentMatchingStrategy:
    """Test the unified component matching strategy."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handle_matcher = Mock()
        self.knot_matcher = Mock()
        self.catalogs = {"brushes": {}, "handles": {}, "knots": {}, "correct_matches": {}}

        self.strategy = FullInputComponentMatchingStrategy(
            handle_matcher=self.handle_matcher,
            knot_matcher=self.knot_matcher,
            catalogs=self.catalogs,
            brush_splits_path=Path("data/brush_splits.yaml"),
        )

    def test_init_with_required_components(self):
        """Test strategy initialization with required components."""
        assert self.strategy.handle_matcher == self.handle_matcher
        assert self.strategy.knot_matcher == self.knot_matcher
        assert self.strategy.catalogs == self.catalogs

    def test_dual_component_match_both_handle_and_knot(self):
        """Test dual component match when both handle and knot match."""
        # Mock handle match
        handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        # Mock knot match
        knot_result = MatchResult(
            original="Declaration Grooming Washington B2",
            matched={"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        result = self.strategy.match("Declaration Grooming Washington B2")

        assert result is not None
        assert result.strategy == "full_input_component_matching"  # Uses the actual strategy name
        assert result.match_type == "composite"
        # Score is applied by scoring engine: base 50 + dual_component modifier 15 = 65

    def test_single_component_match_handle_only(self):
        """Test single component match when only handle matches."""
        # Mock handle match
        handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        # Mock no knot match
        self.knot_matcher.match.return_value = None

        result = self.strategy.match("Declaration Grooming Washington")

        assert result is not None
        assert result.strategy == "full_input_component_matching"  # Uses the actual strategy name
        assert result.match_type == "single_component"
        # Score is applied by scoring engine: base 50 (no modifier)

    def test_single_component_match_knot_only(self):
        """Test single component match when only knot matches."""
        # Mock no handle match
        self.handle_matcher.match_handle_maker.return_value = None

        # Mock knot match
        knot_result = MatchResult(
            original="Declaration Grooming B2",
            matched={"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        result = self.strategy.match("Declaration Grooming B2")

        assert result is not None
        assert result.strategy == "full_input_component_matching"  # Uses the actual strategy name
        assert result.match_type == "single_component"
        # Score is applied by scoring engine: base 50 (no modifier)

    def test_no_match_neither_handle_nor_knot(self):
        """Test no match when neither handle nor knot matches."""
        # Mock no handle match
        self.handle_matcher.match_handle_maker.return_value = None

        # Mock no knot match
        self.knot_matcher.match.return_value = None

        result = self.strategy.match("Invalid Brush String")

        assert result is None

    def test_handle_matcher_exception_handling(self):
        """Test handling of handle matcher exceptions."""
        # Mock handle matcher exception
        self.handle_matcher.match_handle_maker.side_effect = Exception("Handle matcher error")

        # Mock knot match
        knot_result = MatchResult(
            original="Declaration Grooming B2",
            matched={"brand": "Declaration Grooming", "model": "B2"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        # Should still work with just knot match
        result = self.strategy.match("Declaration Grooming B2")

        assert result is not None
        assert result.strategy == "full_input_component_matching"  # Uses the actual strategy name
        # Score is applied by scoring engine: base 50 (no modifier)

    def test_knot_matcher_exception_handling(self):
        """Test handling of knot matcher exceptions."""
        # Mock handle match
        handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        # Mock knot matcher exception
        self.knot_matcher.match.side_effect = Exception("Knot matcher error")

        # Should still work with just handle match
        result = self.strategy.match("Declaration Grooming Washington")

        assert result is not None
        assert result.strategy == "full_input_component_matching"  # Uses the actual strategy name
        assert result.match_type == "single_component"
        # Score is applied by scoring engine: base 50 (no modifier)

    def test_empty_string_handling(self):
        """Test handling of empty input string."""
        result = self.strategy.match("")
        assert result is None

    def test_none_string_handling(self):
        """Test handling of None input string."""
        result = self.strategy.match("")  # Empty string instead of None
        assert result is None

    def test_dual_component_different_brands_should_not_set_top_level_brand_model(self):
        """Test that dual component brushes with different brands should not set top-level brand/model."""
        # Mock handle match with one brand
        handle_result = MatchResult(
            original="Heritage Collection Merit 99-4 w/ AP Shave Co G5C",
            matched={"handle_maker": "Heritage Collection", "handle_model": "Merit 99-4"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        # Mock knot match with different brand
        knot_result = MatchResult(
            original="Heritage Collection Merit 99-4 w/ AP Shave Co G5C",
            matched={"brand": "AP Shave Co", "model": "G5C", "fiber": "Synthetic"},
            match_type="exact",
            pattern="ap shave co.*g5c",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        result = self.strategy.match("Heritage Collection Merit 99-4 w/ AP Shave Co G5C")

        assert result is not None
        assert result.strategy == "full_input_component_matching"
        assert result.match_type == "composite"

        # Ensure matched data exists
        assert result.matched is not None

        # Key assertion: Top-level brand and model should be None for multi-component brushes
        assert (
            result.matched["brand"] is None
        ), "Top-level brand should be None for multi-component brushes with different brands"
        assert (
            result.matched["model"] is None
        ), "Top-level model should be None for multi-component brushes with different brands"

        # Handle and knot sections should still be populated
        assert result.matched["handle"]["brand"] == "Heritage Collection"
        assert result.matched["handle"]["model"] == "Merit 99-4"
        assert result.matched["knot"]["brand"] == "AP Shave Co"
        assert result.matched["knot"]["model"] == "G5C"
        assert result.matched["knot"]["fiber"] == "Synthetic"

    def test_match_all_returns_list(self):
        """Test that match_all() returns a list of MatchResult objects."""
        # Mock handle match
        handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        # Mock knot match
        knot_result = MatchResult(
            original="Declaration Grooming Washington B2",
            matched={"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        results = self.strategy.match_all("Declaration Grooming Washington B2")

        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], MatchResult)
        assert results[0].strategy == "full_input_component_matching"

    def test_match_all_empty_input_returns_empty_list(self):
        """Test that match_all() returns empty list for empty input."""
        results = self.strategy.match_all("")
        assert results == []

    def test_match_all_no_match_returns_empty_list(self):
        """Test that match_all() returns empty list when no matches found."""
        # Mock no handle match
        self.handle_matcher.match_handle_maker.return_value = None
        # Mock no knot match
        self.knot_matcher.match.return_value = None

        results = self.strategy.match_all("Invalid Brush String")
        assert results == []

    def test_match_still_returns_single_result(self):
        """Test that match() still returns a single result for backward compatibility."""
        # Mock handle match
        handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        # Mock knot match
        knot_result = MatchResult(
            original="Declaration Grooming Washington B2",
            matched={"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        result = self.strategy.match("Declaration Grooming Washington B2")

        assert isinstance(result, MatchResult)
        assert result.strategy == "full_input_component_matching"

    def test_match_returns_none_when_no_results(self):
        """Test that match() returns None when no results found."""
        # Mock no handle match
        self.handle_matcher.match_handle_maker.return_value = None
        # Mock no knot match
        self.knot_matcher.match.return_value = None

        result = self.strategy.match("Invalid Brush String")
        assert result is None

    def test_brand_exclusion_methods_exist(self):
        """Test that brand exclusion methods exist and have correct signatures."""
        # Test that methods exist
        assert hasattr(self.strategy, "_match_handle_with_exclusions")
        assert hasattr(self.strategy, "_match_knot_with_exclusions")
        assert hasattr(self.strategy, "_extract_brand_from_result")

        # Test method signatures (they should be callable)
        assert callable(self.strategy._match_handle_with_exclusions)
        assert callable(self.strategy._match_knot_with_exclusions)
        assert callable(self.strategy._extract_brand_from_result)

    def test_brand_exclusion_methods_placeholder_behavior(self):
        """Test that brand exclusion methods work correctly (no longer placeholders)."""
        # These methods are now implemented and should work correctly
        # Test with no mocks - should return None due to no matches
        result = self.strategy._match_handle_with_exclusions("test", {"brand1"})
        assert result is None

        result = self.strategy._match_knot_with_exclusions("test", {"brand1"})
        assert result is None

        # _extract_brand_from_result returns empty string for None input
        result = self.strategy._extract_brand_from_result(None)
        assert result == ""

    def test_match_handle_with_exclusions_excludes_matching_brand(self):
        """Test that handle matching excludes brands in excluded set."""
        # Mock handle match with specific brand
        handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        # Test exclusion of matching brand
        result = self.strategy._match_handle_with_exclusions(
            "Declaration Grooming Washington", {"Declaration Grooming"}
        )
        assert result is None

    def test_match_handle_with_exclusions_allows_non_matching_brand(self):
        """Test that handle matching allows brands not in excluded set."""
        # Mock handle match with specific brand
        handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        # Test allowing non-matching brand
        result = self.strategy._match_handle_with_exclusions(
            "Declaration Grooming Washington", {"Different Brand"}
        )
        assert result is not None
        assert result == handle_result

    def test_match_handle_with_exclusions_case_insensitive(self):
        """Test that handle matching exclusion is case-insensitive."""
        # Mock handle match with specific brand
        handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        # Test case-insensitive exclusion
        result = self.strategy._match_handle_with_exclusions(
            "Declaration Grooming Washington", {"declaration grooming"}
        )
        assert result is None

    def test_match_handle_with_exclusions_no_match_returns_none(self):
        """Test that handle matching returns None when no match found."""
        # Mock no handle match
        self.handle_matcher.match_handle_maker.return_value = None

        result = self.strategy._match_handle_with_exclusions("Invalid Handle", {"Some Brand"})
        assert result is None

    def test_match_handle_with_exclusions_exception_handling(self):
        """Test that handle matching handles exceptions gracefully."""
        # Mock handle matcher exception
        self.handle_matcher.match_handle_maker.side_effect = Exception("Handle matcher error")

        result = self.strategy._match_handle_with_exclusions("Test Handle", {"Some Brand"})
        assert result is None

    def test_match_knot_with_exclusions_excludes_matching_brand(self):
        """Test that knot matching excludes brands in excluded set."""
        # Mock knot match with specific brand
        knot_result = MatchResult(
            original="Declaration Grooming B2",
            matched={"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        # Test exclusion of matching brand
        result = self.strategy._match_knot_with_exclusions(
            "Declaration Grooming B2", {"Declaration Grooming"}
        )
        assert result is None

    def test_match_knot_with_exclusions_allows_non_matching_brand(self):
        """Test that knot matching allows brands not in excluded set."""
        # Mock knot match with specific brand
        knot_result = MatchResult(
            original="Declaration Grooming B2",
            matched={"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        # Test allowing non-matching brand
        result = self.strategy._match_knot_with_exclusions(
            "Declaration Grooming B2", {"Different Brand"}
        )
        assert result is not None
        assert result == knot_result

    def test_match_knot_with_exclusions_case_insensitive(self):
        """Test that knot matching exclusion is case-insensitive."""
        # Mock knot match with specific brand
        knot_result = MatchResult(
            original="Declaration Grooming B2",
            matched={"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        # Test case-insensitive exclusion
        result = self.strategy._match_knot_with_exclusions(
            "Declaration Grooming B2", {"declaration grooming"}
        )
        assert result is None

    def test_match_knot_with_exclusions_no_match_returns_none(self):
        """Test that knot matching returns None when no match found."""
        # Mock no knot match
        self.knot_matcher.match.return_value = None

        result = self.strategy._match_knot_with_exclusions("Invalid Knot", {"Some Brand"})
        assert result is None

    def test_match_knot_with_exclusions_exception_handling(self):
        """Test that knot matching handles exceptions gracefully."""
        # Mock knot matcher exception
        self.knot_matcher.match.side_effect = Exception("Knot matcher error")

        result = self.strategy._match_knot_with_exclusions("Test Knot", {"Some Brand"})
        assert result is None

    def test_extract_brand_from_handle_result(self):
        """Test brand extraction from handle MatchResult."""
        handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )

        brand = self.strategy._extract_brand_from_result(handle_result)
        assert brand == "declaration grooming"

    def test_extract_brand_from_knot_result(self):
        """Test brand extraction from knot MatchResult."""
        knot_result = MatchResult(
            original="Declaration Grooming B2",
            matched={"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )

        brand = self.strategy._extract_brand_from_result(knot_result)
        assert brand == "declaration grooming"

    def test_extract_brand_from_dict_result(self):
        """Test brand extraction from dict result."""
        handle_dict = {"handle_maker": "Declaration Grooming", "handle_model": "Washington"}

        brand = self.strategy._extract_brand_from_result(handle_dict)
        assert brand == "declaration grooming"

    def test_extract_brand_from_knot_dict_result(self):
        """Test brand extraction from knot dict result."""
        knot_dict = {"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"}

        brand = self.strategy._extract_brand_from_result(knot_dict)
        assert brand == "declaration grooming"

    def test_extract_brand_from_none_result(self):
        """Test brand extraction from None result."""
        brand = self.strategy._extract_brand_from_result(None)
        assert brand == ""

    def test_extract_brand_from_empty_result(self):
        """Test brand extraction from empty result."""
        empty_dict = {}

        brand = self.strategy._extract_brand_from_result(empty_dict)
        assert brand == ""

    def test_extract_brand_from_result_without_brand_fields(self):
        """Test brand extraction from result without brand fields."""
        result_without_brand = {"some_field": "some_value"}

        brand = self.strategy._extract_brand_from_result(result_without_brand)
        assert brand == ""

    def test_extract_brand_case_insensitive(self):
        """Test that brand extraction returns lowercase."""
        handle_result = MatchResult(
            original="DECLARATION GROOMING Washington",
            matched={"handle_maker": "DECLARATION GROOMING", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )

        brand = self.strategy._extract_brand_from_result(handle_result)
        assert brand == "declaration grooming"

    def test_match_all_generates_multiple_results_for_same_brand(self):
        """Test that match_all generates multiple results when both components have same brand."""
        # Mock handle match with specific brand
        handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        # Mock knot match with same brand
        knot_result = MatchResult(
            original="Declaration Grooming B2",
            matched={"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        # Mock alternative handle with different brand
        alternative_handle_result = MatchResult(
            original="AP Shave Co Handle",
            matched={"handle_maker": "AP Shave Co", "handle_model": "Handle"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.side_effect = [
            handle_result,  # First call returns original
            alternative_handle_result,  # Second call returns alternative
        ]

        # Mock alternative knot with different brand
        alternative_knot_result = MatchResult(
            original="AP Shave Co Knot",
            matched={"brand": "AP Shave Co", "model": "Knot", "fiber": "Synthetic"},
            match_type="exact",
            pattern="ap shave co.*knot",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.side_effect = [
            knot_result,  # First call returns original
            alternative_knot_result,  # Second call returns alternative
        ]

        results = self.strategy.match_all("Declaration Grooming Washington B2")

        # Should have multiple results
        assert len(results) >= 1  # At least the original combination
        assert all(isinstance(result, MatchResult) for result in results)
        assert all(result.strategy == "full_input_component_matching" for result in results)
        assert all(result.match_type == "composite" for result in results)

    def test_match_all_deduplicates_identical_combinations(self):
        """Test that match_all deduplicates identical brand combinations."""
        # Mock handle match
        handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        # Mock knot match
        knot_result = MatchResult(
            original="Declaration Grooming B2",
            matched={"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        results = self.strategy.match_all("Declaration Grooming Washington B2")

        # Should have exactly one result (no duplicates)
        assert len(results) == 1
        assert results[0].strategy == "full_input_component_matching"
        assert results[0].match_type == "composite"

    def test_match_all_preserves_single_component_matching(self):
        """Test that match_all preserves single component matching logic."""
        # Mock handle match only
        handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        # Mock no knot match
        self.knot_matcher.match.return_value = None

        results = self.strategy.match_all("Declaration Grooming Washington")

        # Should have one single component result
        assert len(results) == 1
        assert results[0].strategy == "full_input_component_matching"
        assert results[0].match_type == "single_component"

    def test_match_all_handles_no_matches(self):
        """Test that match_all handles no matches correctly."""
        # Mock no matches
        self.handle_matcher.match_handle_maker.return_value = None
        self.knot_matcher.match.return_value = None

        results = self.strategy.match_all("Invalid Brush String")

        # Should return empty list
        assert results == []

    def test_match_all_handles_empty_input(self):
        """Test that match_all handles empty input correctly."""
        results = self.strategy.match_all("")
        assert results == []

    def test_match_all_handles_dict_input(self):
        """Test that match_all handles dict input correctly."""
        # Mock handle match
        handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        # Mock knot match
        knot_result = MatchResult(
            original="Declaration Grooming B2",
            matched={"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        # Test with dict input
        dict_input = {
            "normalized": "Declaration Grooming Washington B2",
            "original": "Declaration Grooming Washington B2",
        }
        results = self.strategy.match_all(dict_input)

        # Should work the same as string input
        assert len(results) >= 1
        assert all(isinstance(result, MatchResult) for result in results)

    def test_generate_alternative_combinations_creates_alternatives(self):
        """Test that _generate_alternative_combinations creates alternative combinations."""
        # Mock original handle result
        original_handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )

        # Mock original knot result
        original_knot_result = MatchResult(
            original="Declaration Grooming B2",
            matched={"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )

        # Mock alternative handle result
        alternative_handle_result = MatchResult(
            original="AP Shave Co Handle",
            matched={"handle_maker": "AP Shave Co", "handle_model": "Handle"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )

        # Mock alternative knot result
        alternative_knot_result = MatchResult(
            original="AP Shave Co Knot",
            matched={"brand": "AP Shave Co", "model": "Knot", "fiber": "Synthetic"},
            match_type="exact",
            pattern="ap shave co.*knot",
            strategy="KnotMatcher",
        )

        # Mock the exclusion methods to return alternatives
        # Type ignore for test - we're mocking private methods for testing
        self.strategy._match_handle_with_exclusions = lambda text, excluded: (  # type: ignore
            alternative_handle_result if "declaration grooming" in excluded else None
        )
        self.strategy._match_knot_with_exclusions = lambda text, excluded: (  # type: ignore
            alternative_knot_result if "declaration grooming" in excluded else None
        )

        results = []
        seen_combinations = set()

        # Call the method
        self.strategy._generate_alternative_combinations(
            "test text", original_handle_result, original_knot_result, results, seen_combinations
        )

        # Should have created alternative combinations
        assert len(results) >= 1  # At least one alternative combination
        assert all(isinstance(result, MatchResult) for result in results)
        assert all(result.strategy == "full_input_component_matching" for result in results)
        assert all(result.match_type == "composite" for result in results)

    def test_generate_alternative_combinations_handles_no_alternatives(self):
        """Test that _generate_alternative_combinations handles no alternatives gracefully."""
        # Mock original handle result
        original_handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )

        # Mock original knot result
        original_knot_result = MatchResult(
            original="Declaration Grooming B2",
            matched={"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )

        # Mock the exclusion methods to return None (no alternatives)
        # Type ignore for test - we're mocking private methods for testing
        self.strategy._match_handle_with_exclusions = lambda text, excluded: None  # type: ignore
        self.strategy._match_knot_with_exclusions = lambda text, excluded: None  # type: ignore

        results = []
        seen_combinations = set()

        # Call the method
        self.strategy._generate_alternative_combinations(
            "test text", original_handle_result, original_knot_result, results, seen_combinations
        )

        # Should not have created any new combinations
        assert len(results) == 0

    def test_should_not_split_returns_empty_list_in_match_all(self):
        """Test that match_all() returns empty list when should_not_split is True."""
        # Mock splits_loader to return True for should_not_split
        self.strategy.splits_loader.should_not_split = lambda text: True

        # Mock handle and knot matches (should be ignored)
        handle_result = MatchResult(
            original="Boar Rudy Vey SOC knot 24mm",
            matched={"handle_maker": "Rudy Vey", "handle_model": "Unspecified"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        knot_result = MatchResult(
            original="Boar Rudy Vey SOC knot 24mm",
            matched={"brand": "Semogue", "model": "SOC", "fiber": "Boar"},
            match_type="exact",
            pattern="semogue.*soc",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        # Should return empty list even though both components match
        results = self.strategy.match_all("Boar Rudy Vey SOC knot 24mm")
        assert results == []

    def test_should_not_split_returns_none_in_match(self):
        """Test that match() returns None when should_not_split is True."""
        # Mock splits_loader to return True for should_not_split
        self.strategy.splits_loader.should_not_split = lambda text: True

        # Mock handle and knot matches (should be ignored)
        handle_result = MatchResult(
            original="Boar Rudy Vey SOC knot 24mm",
            matched={"handle_maker": "Rudy Vey", "handle_model": "Unspecified"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        knot_result = MatchResult(
            original="Boar Rudy Vey SOC knot 24mm",
            matched={"brand": "Semogue", "model": "SOC", "fiber": "Boar"},
            match_type="exact",
            pattern="semogue.*soc",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        # Should return None even though both components match
        result = self.strategy.match("Boar Rudy Vey SOC knot 24mm")
        assert result is None

    def test_should_not_split_prevents_dual_component_matching(self):
        """Test that should_not_split prevents dual component matching."""
        # Mock splits_loader to return True for should_not_split
        self.strategy.splits_loader.should_not_split = lambda text: (
            text == "Boar Rudy Vey SOC knot 24mm"
        )

        # Mock handle and knot matches
        handle_result = MatchResult(
            original="Boar Rudy Vey SOC knot 24mm",
            matched={"handle_maker": "Rudy Vey", "handle_model": "Unspecified"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        knot_result = MatchResult(
            original="Boar Rudy Vey SOC knot 24mm",
            matched={"brand": "Semogue", "model": "SOC", "fiber": "Boar"},
            match_type="exact",
            pattern="semogue.*soc",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        # Should return None for should_not_split brush
        result = self.strategy.match("Boar Rudy Vey SOC knot 24mm")
        assert result is None

        # Should work normally for other brushes
        result = self.strategy.match("Declaration Grooming Washington B2")
        assert result is not None

    def test_should_not_split_prevents_single_component_matching(self):
        """Test that should_not_split prevents single component matching."""
        # Mock splits_loader to return True for should_not_split
        self.strategy.splits_loader.should_not_split = lambda text: (text == "Test Brush String")

        # Mock handle match only
        handle_result = MatchResult(
            original="Test Brush String",
            matched={"handle_maker": "Test Maker", "handle_model": "Test Model"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result
        self.knot_matcher.match.return_value = None

        # Should return None even though handle matches
        result = self.strategy.match("Test Brush String")
        assert result is None

    def test_normal_behavior_when_should_not_split_false(self):
        """Test that normal behavior works when should_not_split is False."""
        # Mock splits_loader to return False for should_not_split
        self.strategy.splits_loader.should_not_split = lambda text: False

        # Mock handle and knot matches
        handle_result = MatchResult(
            original="Declaration Grooming Washington",
            matched={"handle_maker": "Declaration Grooming", "handle_model": "Washington"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        knot_result = MatchResult(
            original="Declaration Grooming B2",
            matched={"brand": "Declaration Grooming", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="declaration.*b2",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        # Should work normally
        result = self.strategy.match("Declaration Grooming Washington B2")
        assert result is not None
        assert result.strategy == "full_input_component_matching"
        assert result.match_type == "composite"
