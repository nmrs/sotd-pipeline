#!/usr/bin/env python3
"""Tests for AutomatedSplitStrategy multi-split functionality."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from sotd.match.brush.strategies.automated.automated_split_strategy import (
    AutomatedSplitStrategy,
)
from sotd.match.types import MatchResult


class TestAutomatedSplitStrategyMulti:
    """Test AutomatedSplitStrategy multi-split functionality."""

    @pytest.fixture
    def mock_catalogs(self):
        """Mock catalogs for testing."""
        return {}

    @pytest.fixture
    def mock_scoring_config(self):
        """Mock scoring config for testing."""
        return Mock()

    @pytest.fixture
    def mock_handle_matcher(self):
        """Mock handle matcher for testing."""
        matcher = Mock()
        matcher.match.return_value = MatchResult(
            original="test handle",
            normalized="test handle",
            matched={"handle_maker": "TestHandle", "handle_model": "TestModel"},
            match_type="handle",
            pattern="test_pattern",
            strategy="handle_matcher",
        )
        return matcher

    @pytest.fixture
    def mock_knot_matcher(self):
        """Mock knot matcher for testing."""
        matcher = Mock()
        matcher.match.return_value = MatchResult(
            original="test knot",
            normalized="test knot",
            matched={"brand": "TestKnot", "model": "TestKnotModel", "fiber": "badger"},
            match_type="knot",
            pattern="test_pattern",
            strategy="knot_matcher",
        )
        return matcher

    @pytest.fixture
    def strategy(self, mock_catalogs, mock_scoring_config, mock_handle_matcher, mock_knot_matcher):
        """Create AutomatedSplitStrategy instance for testing."""
        return AutomatedSplitStrategy(
            mock_catalogs,
            mock_scoring_config,
            mock_handle_matcher,
            mock_knot_matcher,
            brush_splits_path=Path("data/brush_splits.yaml"),
        )

    def test_match_all_single_delimiter(self, strategy):
        """Test match_all with a single delimiter."""
        # Test case: "string one / string two"
        results = strategy.match_all("string one / string two")

        assert len(results) == 1
        result = results[0]
        assert result.original == "string one / string two"
        assert result.matched["handle_text"] == "string one"
        assert result.matched["knot_text"] == "string two"
        assert result.matched["split_priority"] == "medium"
        assert result.strategy == "automated_split"

    def test_match_all_multiple_delimiters(self, strategy):
        """Test match_all with multiple delimiters."""
        # Test case: "string one / string two / string three"
        results = strategy.match_all("string one / string two / string three")

        # Should return 2 results:
        # 1. "string one" vs "string two / string three"
        # 2. "string one / string two" vs "string three"
        assert len(results) == 2

        # First split: "string one" / "string two / string three"
        result1 = results[0]
        assert result1.matched["handle_text"] == "string one"
        assert result1.matched["knot_text"] == "string two / string three"

        # Second split: "string one / string two" / "string three"
        result2 = results[1]
        assert result2.matched["handle_text"] == "string one / string two"
        assert result2.matched["knot_text"] == "string three"

    def test_match_all_high_priority_delimiter(self, strategy):
        """Test match_all with high priority delimiter."""
        # Test case: "handle with knot"
        results = strategy.match_all("handle with knot")

        assert len(results) == 1
        result = results[0]
        assert result.matched["handle_text"] == "handle"
        assert result.matched["knot_text"] == "knot"
        assert result.matched["split_priority"] == "high"

    def test_match_all_mixed_priority_delimiters(self, strategy):
        """Test match_all with mixed priority delimiters."""
        # "with" = high priority, " + " = medium priority
        results = strategy.match_all("Dogwood with 26mm Tuxedo + Omega")

        # Should return 2 results:
        # 1. High priority: "Dogwood" with "26mm Tuxedo + Omega"
        # 2. Medium priority: "Dogwood with 26mm Tuxedo" + "Omega"
        assert len(results) == 2

        # Find high priority result
        high_priority_result = next(
            (r for r in results if r.matched["split_priority"] == "high"), None
        )
        assert high_priority_result is not None
        assert high_priority_result.matched["handle_text"] == "Dogwood"
        assert high_priority_result.matched["knot_text"] == "26mm Tuxedo + Omega"

        # Find medium priority result — signal scoring assigns sides based on
        # knot signals: "Dogwood with 26mm Tuxedo" has knot signals (26mm, Tuxedo)
        # so it becomes the knot; "Omega" becomes the handle.
        medium_priority_result = next(
            (r for r in results if r.matched["split_priority"] == "medium"), None
        )
        assert medium_priority_result is not None
        assert medium_priority_result.matched["handle_text"] == "Omega"
        assert medium_priority_result.matched["knot_text"] == "Dogwood with 26mm Tuxedo"

    def test_match_all_no_delimiters(self, strategy):
        """Test match_all with no delimiters."""
        results = strategy.match_all("no delimiters here")
        assert len(results) == 0

    def test_match_all_empty_string(self, strategy):
        """Test match_all with empty string."""
        results = strategy.match_all("")
        assert len(results) == 0

    def test_match_all_none_input(self, strategy):
        """Test match_all with None input."""
        results = strategy.match_all(None)
        assert len(results) == 0

    def test_match_all_reddit_references_skipped(self, strategy):
        """Test that Reddit references are not split."""
        # Test case: "r/wetshaving" should not be split
        results = strategy.match_all("r/wetshaving")
        assert len(results) == 0

        # Test case: "u/username" should not be split
        results = strategy.match_all("u/username")
        assert len(results) == 0

    def test_match_all_w_slash_not_split(self, strategy):
        """Test that 'w/' patterns are not split by '/'."""
        # Test case: "brush w/ knot" should only split on 'w/', not '/'
        results = strategy.match_all("brush w/ knot")

        assert len(results) == 1
        result = results[0]
        assert result.matched["handle_text"] == "brush"
        assert result.matched["knot_text"] == "knot"
        assert result.matched["split_priority"] == "high"

    def test_match_all_made_context_skipped(self, strategy):
        """Test that 'made' context is not split."""
        # Test case: "made in USA" should not be split
        results = strategy.match_all("made in USA")
        assert len(results) == 0

    def test_match_all_complex_scenario(self, strategy):
        """Test match_all with complex multi-delimiter scenario."""
        # Test case: "handle with knot / extra - more"
        results = strategy.match_all("handle with knot / extra - more")

        # Should return multiple results based on different delimiter combinations
        assert len(results) >= 2

        # Verify all results have proper structure
        for result in results:
            assert result.original == "handle with knot / extra - more"
            assert result.matched["handle_text"] is not None
            assert result.matched["knot_text"] is not None
            assert result.matched["split_priority"] in ["high", "medium"]
            assert result.strategy == "automated_split"

    def test_match_all_handle_knot_scoring(self, strategy):
        """Test that handle/knot scoring works correctly for '/' delimiter."""
        # Test case where first part scores higher as handle
        results = strategy.match_all("custom handle / badger knot")

        assert len(results) >= 1
        result = results[0]
        # Should score "custom handle" as handle (higher score)
        assert result.matched["handle_text"] == "custom handle"
        assert result.matched["knot_text"] == "badger knot"

    def test_match_all_backward_compatibility(self, strategy):
        """Test that match() method still works for backward compatibility."""
        # Test that the single match method still returns the first result
        single_result = strategy.match("handle with knot")
        all_results = strategy.match_all("handle with knot")

        assert single_result is not None
        assert len(all_results) >= 1
        # The single result should match the first result from match_all
        assert single_result.matched["handle_text"] == all_results[0].matched["handle_text"]
        assert single_result.matched["knot_text"] == all_results[0].matched["knot_text"]

    def test_match_all_priority_ordering(self, strategy):
        """Test that results are ordered by delimiter position."""
        # Test case: "a / b / c" should return splits in left-to-right order
        results = strategy.match_all("a / b / c")

        assert len(results) == 2

        # First split should be "a" / "b / c"
        assert results[0].matched["handle_text"] == "a"
        assert results[0].matched["knot_text"] == "b / c"

        # Second split should be "a / b" / "c"
        assert results[1].matched["handle_text"] == "a / b"
        assert results[1].matched["knot_text"] == "c"

    def test_match_all_error_handling(self, strategy):
        """Test error handling in match_all."""
        # Test with invalid input types
        assert strategy.match_all(None) == []
        assert strategy.match_all(123) == []  # Non-string input
        assert strategy.match_all("") == []

        # Test that normal input doesn't raise errors
        results = strategy.match_all("normal input")
        assert isinstance(results, list)
