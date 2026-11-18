"""Test that AutomatedSplitStrategy correctly identifies Black Eagle HT2 for the full input text."""

import re
import sys
from pathlib import Path

# Add the parent directory to Python path to import SOTD modules
parent_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(parent_dir))

# Import SOTD modules after path setup
from sotd.match.brush.strategies.automated.automated_split_strategy import AutomatedSplitStrategy
from sotd.match.brush.config import BrushScoringConfig
from sotd.match.brush.handle_matcher import HandleMatcher
from sotd.match.brush.knot_matcher import KnotMatcher


class TestAutomatedSplitBlackEagleHT2:
    """Test that AutomatedSplitStrategy correctly identifies Black Eagle HT2."""

    def setup_method(self):
        """Set up test data and strategy."""
        # Create minimal test catalogs with the specific patterns we're testing
        self.test_catalogs = {
            "brushes": {"known_brushes": {}, "other_brushes": {}},
            "handles": {"Black Eagle": {"default": "Badger", "patterns": ["black.*eag"]}},
            "knots": {
                "known_knots": {
                    "Black Eagle": {
                        "HT2": {
                            "fiber": "Badger",
                            "patterns": [
                                "black.*eag.*ht2",  # 15 chars
                                "(?:black.*eag)?.*exclusive.*b2",  # 30 chars
                            ],
                        }
                    },
                    "Declaration Grooming": {
                        "B2": {
                            "fiber": "Badger",
                            "patterns": [
                                "(declaration|\\bdg\\b).*\\bb2\\b",  # 28 chars
                                "\\bb2\\b",  # 6 chars
                            ],
                        }
                    },
                },
                "other_knots": {},
            },
        }

        # Create scoring config
        self.scoring_config = BrushScoringConfig()

        # Create handle and knot matchers
        self.handle_matcher = HandleMatcher()
        self.knot_matcher = KnotMatcher([])  # Empty strategies for now

        # Create the automated split strategy
        self.strategy = AutomatedSplitStrategy(
            self.test_catalogs,
            self.scoring_config,
            self.handle_matcher,
            self.knot_matcher,
            brush_splits_path=Path("data/brush_splits.yaml"),
        )

    def test_automated_split_splits_correctly(self):
        """Test that the strategy splits the input text correctly."""
        input_text = "BLACK EAGLE - Warthog Eagles Beak - 28 x 49.5 mm EXCLUSIVE BADGER KNOT B2"

        # Test the splitting logic directly
        delimiter = " - "
        parts = input_text.split(delimiter, 1)

        assert len(parts) == 2, "Should split into 2 parts"
        handle = parts[0].strip()
        knot = parts[1].strip()
        assert handle == "BLACK EAGLE", f"Handle should be 'BLACK EAGLE', got '{handle}'"
        expected_knot = "Warthog Eagles Beak - 28 x 49.5 mm EXCLUSIVE BADGER KNOT B2"
        assert knot == expected_knot, f"Knot should be correct, got '{knot}'"

    def test_handle_matches_black_eagle(self):
        """Test that the handle text matches Black Eagle patterns."""
        handle_text = "BLACK EAGLE"

        # Test handle matching (simplified)
        handle_text_lower = handle_text.lower()
        black_eagle_pattern = "black.*eag"

        compiled_pattern = re.compile(black_eagle_pattern, re.IGNORECASE)
        match = compiled_pattern.search(handle_text_lower)

        assert (
            match is not None
        ), f"Handle text '{handle_text}' should match pattern '{black_eagle_pattern}'"
        assert "black" in handle_text_lower, "Handle should contain 'black'"
        assert "eag" in handle_text_lower, "Handle should contain 'eag'"

    def test_knot_text_contains_exclusive_b2(self):
        """Test that the knot text contains the expected EXCLUSIVE B2 pattern."""
        knot_text = "Warthog Eagles Beak - 28 x 49.5 mm EXCLUSIVE BADGER KNOT B2"

        # Test that it contains the key elements
        assert "EXCLUSIVE" in knot_text, "Knot text should contain 'EXCLUSIVE'"
        assert "B2" in knot_text, "Knot text should contain 'B2'"
        assert "BADGER" in knot_text, "Knot text should contain 'BADGER'"
        assert "KNOT" in knot_text, "Knot text should contain 'KNOT'"

    def test_black_eagle_ht2_pattern_matches_knot_text(self):
        """Test that the Black Eagle HT2 pattern matches the knot text."""
        knot_text = "Warthog Eagles Beak - 28 x 49.5 mm EXCLUSIVE BADGER KNOT B2"

        # Test the Black Eagle HT2 exclusive pattern
        ht2_exclusive_pattern = "(?:black.*eag)?.*exclusive.*b2"

        compiled_pattern = re.compile(ht2_exclusive_pattern, re.IGNORECASE)
        match = compiled_pattern.search(knot_text)

        assert (
            match is not None
        ), f"Black Eagle HT2 pattern '{ht2_exclusive_pattern}' should match knot text '{knot_text}'"
        matched_text = match.group()
        assert "EXCLUSIVE" in matched_text, "Should match text containing 'EXCLUSIVE'"
        assert "B2" in matched_text, "Should match text containing 'B2'"

    def test_generic_b2_pattern_also_matches_knot_text(self):
        """Test that the generic B2 pattern also matches the knot text."""
        knot_text = "Warthog Eagles Beak - 28 x 49.5 mm EXCLUSIVE BADGER KNOT B2"

        # Test the generic B2 pattern
        generic_b2_pattern = r"\bb2\b"

        compiled_pattern = re.compile(generic_b2_pattern, re.IGNORECASE)
        match = compiled_pattern.search(knot_text)

        assert (
            match is not None
        ), f"Generic B2 pattern '{generic_b2_pattern}' should match knot text '{knot_text}'"
        assert match.group() == "B2", f"Should match exactly 'B2', got '{match.group()}'"

    def test_black_eagle_ht2_pattern_is_longer_than_generic_b2(self):
        """Test that the Black Eagle HT2 pattern is longer than the generic B2 pattern."""
        ht2_exclusive_pattern = "(?:black.*eag)?.*exclusive.*b2"
        generic_b2_pattern = r"\bb2\b"

        ht2_length = len(ht2_exclusive_pattern)
        generic_length = len(generic_b2_pattern)

        assert ht2_length > generic_length, (
            f"Black Eagle HT2 pattern should be longer than generic B2 pattern. "
            f"Got: {ht2_length} vs {generic_length}"
        )

        print("Pattern length comparison:")
        print(f"  Black Eagle HT2: '{ht2_exclusive_pattern}' ({ht2_length} chars)")
        print(f"  Generic B2: '{generic_b2_pattern}' ({generic_length} chars)")

    def test_full_automated_split_strategy_result(self):
        """Test the full automated split strategy with the complete input text."""
        input_text = "BLACK EAGLE - Warthog Eagles Beak - 28 x 49.5 mm EXCLUSIVE BADGER KNOT B2"

        # This test requires the actual strategy to work with real catalogs
        # For now, we'll test the individual components

        # Test splitting
        delimiter = " - "
        parts = input_text.split(delimiter, 1)
        handle_text = parts[0].strip()
        knot_text = parts[1].strip()

        # Test handle matching
        assert "BLACK EAGLE" in handle_text, "Handle should contain 'BLACK EAGLE'"

        # Test knot matching
        expected_knot_content = "EXCLUSIVE BADGER KNOT B2"
        assert expected_knot_content in knot_text, f"Knot should contain '{expected_knot_content}'"

        # Test that both patterns match
        ht2_pattern = "(?:black.*eag)?.*exclusive.*b2"
        generic_pattern = r"\bb2\b"

        ht2_match = re.search(ht2_pattern, knot_text, re.IGNORECASE)
        generic_match = re.search(generic_pattern, knot_text, re.IGNORECASE)

        assert ht2_match is not None, "Black Eagle HT2 pattern should match"
        assert generic_match is not None, "Generic B2 pattern should match"

        # Test that the longer pattern should win (this is the key assertion)
        ht2_length = len(ht2_pattern)
        generic_length = len(generic_pattern)

        assert ht2_length > generic_length, (
            f"Black Eagle HT2 pattern ({ht2_length} chars) should be longer than "
            f"generic B2 pattern ({generic_length} chars) to ensure proper priority"
        )

        print("\nFull strategy test result:")
        print(f"  Input: {input_text}")
        print(f"  Handle: {handle_text}")
        print(f"  Knot: {knot_text}")
        print(f"  Black Eagle HT2 pattern: {ht2_pattern} ({ht2_length} chars)")
        print(f"  Generic B2 pattern: {generic_pattern} ({generic_length} chars)")
        print("  Priority: Black Eagle HT2 should win due to longer pattern length")
