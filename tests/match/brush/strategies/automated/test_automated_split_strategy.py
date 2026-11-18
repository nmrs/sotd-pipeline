#!/usr/bin/env python3
"""Test file for AutomatedSplitStrategy (unified high/medium priority split strategy)."""

from pathlib import Path
from unittest.mock import Mock

from sotd.match.brush.config import BrushScoringConfig
from sotd.match.brush.strategies.automated.automated_split_strategy import AutomatedSplitStrategy


class TestAutomatedSplitStrategy:
    """Test the unified AutomatedSplitStrategy."""

    def setup_method(self):
        """Set up test fixtures."""
        self.catalogs = {"brushes": {}, "handles": {}, "knots": {}, "correct_matches": {}}
        self.scoring_config = BrushScoringConfig()

        # Create mock instances for required dependencies
        self.handle_matcher = Mock()
        self.knot_matcher = Mock()

        self.strategy = AutomatedSplitStrategy(
            self.catalogs,
            self.scoring_config,
            self.handle_matcher,
            self.knot_matcher,
            brush_splits_path=Path("data/brush_splits.yaml"),
        )

    def test_high_priority_delimiter_with_match(self):
        """Test that high priority delimiters (' w/ ', ' with ') return appropriate strategy name."""
        # Test case: brush string with high priority delimiter
        test_input = "Simpson Chubby 2 w/ Zenith B07 Boar"

        result = self.strategy.match(test_input)

        # Should match and identify as high priority
        assert result is not None
        assert result.matched is not None
        assert result.strategy == "automated_split"
        # Should detect high priority delimiter for scoring modifier
        assert result.matched.get("high_priority_delimiter") is True
        assert result.matched.get("_delimiter_priority") == "high"

    def test_high_priority_delimiter_in_variant(self):
        """Test ' in ' delimiter (high priority)."""
        test_input = "Declaration B2 in Mozingo handle"

        result = self.strategy.match(test_input)

        assert result is not None
        assert result.strategy == "automated_split"
        if result.matched:
            assert result.matched.get("high_priority_delimiter") is True

    def test_medium_priority_delimiter_with_match(self):
        """Test that medium priority delimiters (' - ', ' + ') return appropriate strategy name."""
        # Test case: brush string with medium priority delimiter
        test_input = "Simpson Chubby 2 - Zenith B07 Boar"

        result = self.strategy.match(test_input)

        # Should match and identify as medium priority
        assert result is not None
        assert result.matched is not None
        assert result.strategy == "automated_split"
        # Should detect medium priority delimiter (no scoring modifier)
        assert result.matched.get("high_priority_delimiter") is False
        assert result.matched.get("_delimiter_priority") == "medium"

    def test_medium_priority_plus_delimiter(self):
        """Test ' + ' delimiter (medium priority)."""
        test_input = "Simpson Chubby 2 + Zenith B07 Boar"

        result = self.strategy.match(test_input)

        assert result is not None
        assert result.strategy == "automated_split"
        if result.matched:
            assert result.matched.get("high_priority_delimiter") is False

    def test_no_delimiter_no_match(self):
        """Test that strings without delimiters return None."""
        test_input = "Simpson Chubby 2"

        result = self.strategy.match(test_input)

        assert result is None

    def test_empty_string_no_match(self):
        """Test that empty strings return None."""
        result = self.strategy.match("")
        assert result is None

    def test_none_input_no_match(self):
        """Test that None input returns None."""
        result = self.strategy.match("")  # Empty string instead of None
        assert result is None

    def test_invalid_input_type_no_match(self):
        """Test that non-string input returns None."""
        result = self.strategy.match("")  # Empty string instead of 123
        assert result is None

    def test_unsplittable_string_no_match(self):
        """Test that strings marked as 'should_not_split: true' in brush_splits.yaml return None."""
        # This test uses the actual entry from brush_splits.yaml that has should_not_split: true
        test_input = "Zenith 510SE 28mm x 56mm Bleached Boar knot set in Stirling green resin handle (aka Less Boar Stirling Edition)"

        result = self.strategy.match(test_input)

        # Should return None because should_not_split is True in brush_splits.yaml
        assert result is None, f"Expected None for should_not_split entry, got: {result}"

    def test_reddit_references_not_split(self):
        """Test that Reddit subreddit and user references are not treated as delimiters."""
        test_cases = [
            {
                "text": "Declaration B2 in r/wetshaving handle",
                "expected_handle": "Declaration B2 in r/wetshaving handle",
                "expected_knot": None,
                "description": "Reddit subreddit reference should not split",
            },
            {
                "text": "Zenith B2 u/username knot",
                "expected_handle": "Zenith B2 u/username knot",
                "expected_knot": None,
                "description": "Reddit user reference should not split",
            },
            {
                "text": "Simpson Chubby 2 w/ r/wetshaving community",
                "expected_handle": "Simpson Chubby 2",
                "expected_knot": "r/wetshaving community",
                "description": "Reddit reference after valid delimiter should work",
            },
        ]

        for test_case in test_cases:
            text = test_case["text"]
            expected_handle = test_case["expected_handle"]
            expected_knot = test_case["expected_knot"]
            description = test_case["description"]

            print(f"\nTest case: {description}")
            print(f"Text: {text}")
            print(f"Expected: handle='{expected_handle}', knot='{expected_knot}'")

            # Test that Reddit references don't cause unwanted splits
            result = self.strategy.match(text)

            if expected_knot is None:
                # Should not split - should return None or handle as complete brush
                if result is not None and result.matched:
                    assert result.matched.get(
                        "brand"
                    ), f"Expected no split for Reddit reference, got: {result}"
            else:
                # Should split on valid delimiter, preserving Reddit references
                assert result is not None, f"Expected split result, got: {result}"
                assert result.matched, "Expected matched data in result"
                assert result.matched.get("handle_text") == expected_handle, (
                    f"Expected handle '{expected_handle}', "
                    f"got '{result.matched.get('handle_text')}'"
                )
                assert result.matched.get("knot_text") == expected_knot, (
                    f"Expected knot '{expected_knot}', " f"got '{result.matched.get('knot_text')}'"
                )
