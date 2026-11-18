#!/usr/bin/env python3
"""Regression tests: brush-split strategies must use the run's data dir.

AutomatedSplitStrategy and FullInputComponentMatchingStrategy each built
their own BrushSplitsLoader(Path("data/brush_splits.yaml")) -- CWD-relative
-- so from any working directory but the repo root the loader found no
file and every curated should_not_split: true entry was silently ignored.
BrushMatcher now passes a shared BrushSplitsLoader built from the run's
data-dir path (brushes.yaml's parent directory) into both strategies, and
_precompute_handle_knot_results reuses the orchestrator's wired
FullInputComponentMatchingStrategy instead of constructing a new one per
match. These tests fail on the old code: the strategy-level tests pass a
brush_splits_path the old constructors do not accept (TypeError), and the
matcher-level test sees the CWD-relative default path instead of the
data-dir path.
"""

import shutil
from pathlib import Path
from unittest.mock import Mock

import yaml

from sotd.match.brush.comparison.splits_loader import BrushSplitsLoader
from sotd.match.brush.config import BrushScoringConfig
from sotd.match.brush.strategies.automated.automated_split_strategy import (
    AutomatedSplitStrategy,
)
from sotd.match.brush.strategies.full_input_component_matching_strategy import (
    FullInputComponentMatchingStrategy,
)
from sotd.match.brush_matcher import BrushMatcher
from sotd.match.types import MatchResult


def _write_splits_file(path: Path, entries: dict) -> Path:
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(entries, f, default_flow_style=False)
    return path


def _split_entry(should_not_split: bool) -> dict:
    return {
        "handle": None,
        "knot": None,
        "match_type": None,
        "corrected": False,
        "validated": False,
        "should_not_split": should_not_split,
        "occurrences": [],
    }


class TestAutomatedSplitStrategyBrushSplitsPath:
    """AutomatedSplitStrategy honors should_not_split from a given path."""

    def test_should_not_split_entry_from_given_path_returns_none(self, tmp_path):
        """A should_not_split entry in the given file blocks the split."""
        splits_path = _write_splits_file(
            tmp_path / "brush_splits.yaml",
            {"Synthetic Test Handle w/ Synthetic Test Knot 24mm": _split_entry(True)},
        )
        handle_matcher = Mock()
        knot_matcher = Mock()
        handle_matcher.match.return_value = MatchResult(
            original="Synthetic Test Handle",
            matched={"handle_maker": "Synthetic Test"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        knot_matcher.match.return_value = MatchResult(
            original="Synthetic Test Knot 24mm",
            matched={"brand": "Synthetic Test", "model": "Test Knot"},
            match_type="exact",
            strategy="KnotMatcher",
        )
        strategy = AutomatedSplitStrategy(
            {"brushes": {}, "handles": {}, "knots": {}, "correct_matches": {}},
            BrushScoringConfig(),
            handle_matcher,
            knot_matcher,
            brush_splits_path=splits_path,
        )

        assert strategy.splits_loader.brush_splits_path == splits_path
        assert strategy.match("Synthetic Test Handle w/ Synthetic Test Knot 24mm") is None

    def test_unlisted_string_still_splits(self, tmp_path):
        """A string absent from the given file still splits (control)."""
        splits_path = _write_splits_file(
            tmp_path / "brush_splits.yaml",
            {"Synthetic Test Handle w/ Synthetic Test Knot 24mm": _split_entry(True)},
        )
        handle_matcher = Mock()
        knot_matcher = Mock()
        handle_matcher.match.return_value = MatchResult(
            original="Other Handle",
            matched={"handle_maker": "Other"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        knot_matcher.match.return_value = MatchResult(
            original="Other Knot 24mm",
            matched={"brand": "Other", "model": "Knot"},
            match_type="exact",
            strategy="KnotMatcher",
        )
        strategy = AutomatedSplitStrategy(
            {"brushes": {}, "handles": {}, "knots": {}, "correct_matches": {}},
            BrushScoringConfig(),
            handle_matcher,
            knot_matcher,
            brush_splits_path=splits_path,
        )

        result = strategy.match("Other Handle w/ Other Knot 24mm")
        assert result is not None
        assert result.strategy == "automated_split"


class TestFullInputComponentMatchingStrategyBrushSplitsPath:
    """FullInputComponentMatchingStrategy honors should_not_split from a given path."""

    def test_should_not_split_entry_from_given_path_returns_none(self, tmp_path):
        """A should_not_split entry in the given file blocks the match."""
        splits_path = _write_splits_file(
            tmp_path / "brush_splits.yaml",
            {"Synthetic Boar Test Brush SOC knot 24mm": _split_entry(True)},
        )
        handle_matcher = Mock()
        knot_matcher = Mock()
        handle_matcher.match_handle_maker.return_value = MatchResult(
            original="Synthetic Boar Test Brush SOC knot 24mm",
            matched={"handle_maker": "Synthetic Test", "handle_model": "Unspecified"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        knot_matcher.match.return_value = MatchResult(
            original="Synthetic Boar Test Brush SOC knot 24mm",
            matched={"brand": "Synthetic Test", "model": "SOC", "fiber": "Boar"},
            match_type="exact",
            pattern="synthetic.*soc",
            strategy="KnotMatcher",
        )
        strategy = FullInputComponentMatchingStrategy(
            handle_matcher=handle_matcher,
            knot_matcher=knot_matcher,
            catalogs={"brushes": {}, "handles": {}, "knots": {}, "correct_matches": {}},
            brush_splits_path=splits_path,
        )

        assert strategy.splits_loader.brush_splits_path == splits_path
        assert strategy.match("Synthetic Boar Test Brush SOC knot 24mm") is None

    def test_unlisted_string_still_matches(self, tmp_path):
        """A string absent from the given file still matches (control)."""
        splits_path = _write_splits_file(
            tmp_path / "brush_splits.yaml",
            {"Synthetic Boar Test Brush SOC knot 24mm": _split_entry(True)},
        )
        handle_matcher = Mock()
        knot_matcher = Mock()
        handle_matcher.match_handle_maker.return_value = MatchResult(
            original="Synthetic Other Brush B2",
            matched={"handle_maker": "Synthetic Other", "handle_model": "B2"},
            match_type="handle_match",
            strategy="HandleMatcher",
        )
        knot_matcher.match.return_value = MatchResult(
            original="Synthetic Other Brush B2",
            matched={"brand": "Synthetic Other", "model": "B2", "fiber": "Badger"},
            match_type="exact",
            pattern="synthetic.*b2",
            strategy="KnotMatcher",
        )
        strategy = FullInputComponentMatchingStrategy(
            handle_matcher=handle_matcher,
            knot_matcher=knot_matcher,
            catalogs={"brushes": {}, "handles": {}, "knots": {}, "correct_matches": {}},
            brush_splits_path=splits_path,
        )

        result = strategy.match("Synthetic Other Brush B2")
        assert result is not None
        assert result.strategy == "full_input_component_matching"


class TestBrushMatcherWiresDataDirBrushSplitsPath:
    """BrushMatcher passes its data-dir brush_splits.yaml to both strategies."""

    def test_strategies_use_data_dir_path_from_foreign_cwd(self, tmp_path, monkeypatch):
        """From a foreign CWD, both strategies load the run's data-dir file."""
        project_root = Path(__file__).parent.parent.parent.parent
        real_data = project_root / "data"
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        for name in (
            "brushes.yaml",
            "handles.yaml",
            "knots.yaml",
            "brush_scoring_config.yaml",
        ):
            shutil.copy(real_data / name, data_dir / name)
        shutil.copytree(real_data / "correct_matches", data_dir / "correct_matches")
        # Two-entry splits file so the loaded content is identifiably ours,
        # not the repo-root file the old CWD-relative default would read.
        _write_splits_file(
            data_dir / "brush_splits.yaml",
            {
                "Synthetic Test Handle w/ Synthetic Test Knot 24mm": _split_entry(True),
                "Synthetic Boar Test Brush SOC knot 24mm": _split_entry(True),
            },
        )

        # Run the matcher from a directory with no data/ in it, like the
        # loop running from /app with SOTD_DATA_DIR=/data.
        foreign_cwd = tmp_path / "foreign_cwd"
        foreign_cwd.mkdir()
        monkeypatch.chdir(foreign_cwd)

        matcher = BrushMatcher(
            brushes_path=data_dir / "brushes.yaml",
            handles_path=data_dir / "handles.yaml",
            knots_path=data_dir / "knots.yaml",
            correct_matches_path=data_dir / "correct_matches",
            brush_scoring_config_path=data_dir / "brush_scoring_config.yaml",
        )

        strategies = matcher.strategy_orchestrator.strategies
        automated = next(s for s in strategies if type(s).__name__ == "AutomatedSplitStrategy")
        full_input = next(
            s for s in strategies if type(s).__name__ == "FullInputComponentMatchingStrategy"
        )
        expected = data_dir / "brush_splits.yaml"
        assert automated.splits_loader.brush_splits_path == expected
        assert full_input.splits_loader.brush_splits_path == expected
        # Both wired strategies share the matcher's single loader: the file
        # is parsed once, and the precompute reuses this same instance.
        assert automated.splits_loader is full_input.splits_loader
        # The loaders actually read our file, not the repo-root default.
        assert automated.splits_loader.get_splits_count() == 2
        assert full_input.splits_loader.get_splits_count() == 2
        # And the curated entries are honored through the wired strategies.
        assert automated.match("Synthetic Test Handle w/ Synthetic Test Knot 24mm") is None
        assert full_input.match("Synthetic Boar Test Brush SOC knot 24mm") is None


class TestBrushSplitsLoaderPreloadedData:
    """BrushMatcher seeds its one BrushSplitsLoader with the already-parsed
    catalogs["brush_splits"] dict so brush_splits.yaml is read once per
    matcher and both consumers (the dict and the loader) see the same
    UniqueKeyLoader-validated parse."""

    def test_preloaded_data_built_without_reading_file(self, tmp_path):
        data = {
            "Synthetic Test Brush": {
                "handle": "Synthetic Test Handle",
                "knot": "Synthetic Test Knot",
            }
        }
        missing_path = tmp_path / "does_not_exist.yaml"
        loader = BrushSplitsLoader(missing_path, data=data)
        assert loader.brush_splits_path == missing_path
        assert loader.get_splits_count() == 1
        assert loader.get_handle_and_knot("Synthetic Test Brush") == (
            "Synthetic Test Handle",
            "Synthetic Test Knot",
        )

    def test_preloaded_data_respects_should_not_split(self, tmp_path):
        data = {
            "Synthetic Test Brush": {
                "handle": "Synthetic Test Handle",
                "knot": "Synthetic Test Knot",
                "should_not_split": True,
            }
        }
        loader = BrushSplitsLoader(tmp_path / "nope.yaml", data=data)
        assert loader.should_not_split("Synthetic Test Brush") is True

    def test_preloaded_data_skips_non_dict_entries(self, tmp_path):
        """A non-dict entry has no .copy() — skipped like the file path does."""
        data = {
            "Good Brush": {"handle": "h", "knot": "k"},
            "Bad Brush": "not a dict",
        }
        loader = BrushSplitsLoader(tmp_path / "nope.yaml", data=data)
        assert loader.get_splits_count() == 1

    def test_no_data_argument_still_reads_file(self, tmp_path):
        content = (
            "Synthetic Test Brush:\n"
            "  handle: Synthetic Test Handle\n"
            "  knot: Synthetic Test Knot\n"
        )
        path = tmp_path / "brush_splits.yaml"
        path.write_text(content)
        loader = BrushSplitsLoader(path)
        assert loader.get_splits_count() == 1
        assert loader.get_handle_and_knot("Synthetic Test Brush") == (
            "Synthetic Test Handle",
            "Synthetic Test Knot",
        )
