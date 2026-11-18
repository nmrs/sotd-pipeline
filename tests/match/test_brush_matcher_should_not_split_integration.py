#!/usr/bin/env python3
"""Integration tests for should_not_split behavior in FullInputComponentMatchingStrategy."""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import yaml

from sotd.match.brush.strategies.full_input_component_matching_strategy import (
    FullInputComponentMatchingStrategy,
)
from sotd.match.types import MatchResult


class TestFullInputComponentMatchingStrategyShouldNotSplitIntegration:
    """Integration tests to verify should_not_split behavior in FullInputComponentMatchingStrategy."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        self.test_brush_splits_path = Path(self.test_dir) / "brush_splits.yaml"

        # Create test brush_splits.yaml with should_not_split entries
        test_brush_splits = {
            "Boar Rudy Vey SOC knot 24mm": {
                "handle": None,
                "knot": None,
                "match_type": None,
                "corrected": False,
                "validated": False,
                "should_not_split": True,
                "occurrences": [],
            },
            "Test Brush That Can Split": {
                "handle": "Test Handle",
                "knot": "Test Knot",
                "match_type": "regex",
                "corrected": False,
                "validated": False,
                "should_not_split": False,
                "occurrences": [],
            },
        }

        with open(self.test_brush_splits_path, "w", encoding="utf-8") as f:
            yaml.dump(test_brush_splits, f, default_flow_style=False)

        # Create mock handle and knot matchers
        self.handle_matcher = Mock()
        self.knot_matcher = Mock()
        self.catalogs = {"brushes": {}, "handles": {}, "knots": {}, "correct_matches": {}}

        # Create strategy with the test brush_splits file via a shared loader.
        from sotd.match.brush.comparison.splits_loader import BrushSplitsLoader

        self.strategy = FullInputComponentMatchingStrategy(
            handle_matcher=self.handle_matcher,
            knot_matcher=self.knot_matcher,
            catalogs=self.catalogs,
            splits_loader=BrushSplitsLoader(self.test_brush_splits_path),
        )

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir)

    def test_should_not_split_prevents_dual_component_matching(self):
        """Test that brushes with should_not_split: true are not matched as dual components."""
        # Mock handle and knot matches (would normally create dual component)
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

        # Test with brush marked should_not_split: true
        test_input = "Boar Rudy Vey SOC knot 24mm"

        # Match the brush - should return None because should_not_split is True
        result = self.strategy.match(test_input)

        # Should return None even though both components match
        assert result is None, (
            f"Brush '{test_input}' with should_not_split: true should not be matched "
            f"by FullInputComponentMatchingStrategy, but got: {result}"
        )

    def test_should_not_split_prevents_single_component_matching(self):
        """Test that brushes with should_not_split: true are not matched as single components."""
        # Mock handle match only (would normally create single component)
        handle_result = MatchResult(
            original="Boar Rudy Vey SOC knot 24mm",
            matched={"handle_maker": "Rudy Vey", "handle_model": "Unspecified"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result
        self.knot_matcher.match.return_value = None

        # Test with brush marked should_not_split: true
        test_input = "Boar Rudy Vey SOC knot 24mm"

        # Match the brush - should return None because should_not_split is True
        result = self.strategy.match(test_input)

        # Should return None even though handle matches
        assert result is None, (
            f"Brush '{test_input}' with should_not_split: true should not be matched "
            f"by FullInputComponentMatchingStrategy, but got: {result}"
        )

    def test_normal_behavior_when_should_not_split_false(self):
        """Test that normal behavior works when should_not_split is False."""
        # Test with brush that can be split (should_not_split: False)
        test_input = "Test Brush That Can Split"

        # Mock handle and knot matches
        handle_result = MatchResult(
            original=test_input,
            matched={"handle_maker": "Test Handle", "handle_model": "Test Model"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        self.handle_matcher.match_handle_maker.return_value = handle_result

        knot_result = MatchResult(
            original=test_input,
            matched={"brand": "Test Knot", "model": "Test Model", "fiber": "Badger"},
            match_type="exact",
            pattern="test.*knot",
            strategy="KnotMatcher",
        )
        self.knot_matcher.match.return_value = knot_result

        # Match the brush - should work normally
        result = self.strategy.match(test_input)

        # Should return a result since should_not_split is False
        assert result is not None, (
            f"Brush '{test_input}' with should_not_split: false should be matched "
            f"by FullInputComponentMatchingStrategy, but got None"
        )
        assert result.strategy == "full_input_component_matching"
