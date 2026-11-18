#!/usr/bin/env python3
"""AutomatedSplitStrategy for unified high/medium priority split handling.

This strategy merges the functionality of HighPriorityAutomatedSplitStrategy
and MediumPriorityAutomatedSplitStrategy into a single strategy that uses
scoring modifiers to differentiate between high and medium priority delimiters.

All splitting logic is delegated to the shared text_splitter module.
"""

from pathlib import Path
from typing import Optional

from sotd.match.types import MatchResult

from ...comparison.splits_loader import BrushSplitsLoader
from ...text_splitter import normalize_text, split_on_delimiters
from ..base_brush_matching_strategy import (
    BaseMultiResultBrushMatchingStrategy,
)
from ..utils.subdict_builders import build_handle_subdict, build_knot_subdict


class AutomatedSplitStrategy(BaseMultiResultBrushMatchingStrategy):
    """Unified strategy for automated split handling with priority-based scoring."""

    def __init__(
        self,
        catalogs,
        scoring_config,
        handle_matcher,
        knot_matcher,
        brush_splits_path: Optional[Path] = None,
        splits_loader: Optional[BrushSplitsLoader] = None,
    ):
        """
        Initialize automated split strategy.

        Args:
            catalogs: Dictionary containing all catalog data
            scoring_config: BrushScoringConfig instance
            handle_matcher: HandleMatcher instance for matching handle components
            knot_matcher: KnotMatcher instance for matching knot components
            brush_splits_path: Path to brush_splits.yaml. BrushMatcher passes
                a shared splits_loader instead; a path is for direct use.
            splits_loader: Shared BrushSplitsLoader (preferred). BrushMatcher
                builds one per matcher so brush_splits.yaml is parsed once.
                One of splits_loader or brush_splits_path is required: there
                is no CWD-relative default, which silently dropped every
                curated should_not_split entry from any working directory
                but the repo root.
        """
        super().__init__()
        self.catalogs = catalogs
        self.scoring_config = scoring_config
        self.handle_matcher = handle_matcher
        self.knot_matcher = knot_matcher
        self.strategy_name = "automated_split"

        # The brush-split source must be explicit: a shared loader, or a path.
        if splits_loader is not None:
            self.splits_loader = splits_loader
        elif brush_splits_path is not None:
            self.splits_loader = BrushSplitsLoader(brush_splits_path)
        else:
            raise ValueError(
                "AutomatedSplitStrategy requires splits_loader or "
                "brush_splits_path; pass the run's data-dir "
                "brush_splits.yaml explicitly"
            )

    def match(self, value: str, full_string: Optional[str] = None) -> Optional[MatchResult]:
        """
        Try to match using unified automated split logic.

        Args:
            value: The brush string to match

        Returns:
            MatchResult if successful split and component matching, None otherwise
        """
        if not value or not isinstance(value, str):
            return None

        # Check if this brush should not be split (from brush_splits.yaml)
        if self.splits_loader.should_not_split(value):
            return None

        value = normalize_text(value)

        try:
            candidates = split_on_delimiters(value)
            if not candidates:
                return None

            # Try high priority first, then medium
            for priority in ("high", "medium"):
                for candidate in candidates:
                    if candidate.priority == priority:
                        result = self._create_split_result(
                            candidate.handle_text,
                            candidate.knot_text,
                            value,
                            candidate.priority,
                        )
                        result.strategy = "automated_split"
                        return result

            return None

        except Exception as e:
            raise ValueError(f"Automated split matching failed for '{value}': {e}") from e

    def match_all(self, value: str) -> list[MatchResult]:
        """
        Try to match using all possible automated split combinations.

        Args:
            value: The brush string to match

        Returns:
            List of MatchResult objects for all possible splits, empty list if no splits found
        """
        if not value or not isinstance(value, str):
            return []

        # Check if this brush should not be split (from brush_splits.yaml)
        if self.splits_loader.should_not_split(value):
            return []

        value = normalize_text(value)

        try:
            all_results = []
            candidates = split_on_delimiters(value)

            for candidate in candidates:
                result = self._create_split_result(
                    candidate.handle_text,
                    candidate.knot_text,
                    value,
                    candidate.priority,
                )
                result.strategy = "automated_split"
                all_results.append(result)

            return all_results

        except Exception as e:
            raise ValueError(f"Automated split matching failed for '{value}': {e}") from e

    def _create_split_result(
        self, handle: str, knot: str, original_value: str, priority: str
    ) -> MatchResult:
        """Create a MatchResult for a split brush."""
        # Use the handle and knot matchers to match the split parts
        handle_result = self.handle_matcher.match(handle)
        knot_result = self.knot_matcher.match(knot, full_string=original_value)

        # Create a basic match result structure
        result = MatchResult(
            original=original_value,
            normalized=original_value.lower().strip(),
            matched={
                "handle_text": handle,
                "knot_text": knot,
                "split_priority": priority,
                "_delimiter_priority": priority,
                "high_priority_delimiter": priority == "high",
                "handle": build_handle_subdict(
                    (
                        handle_result.matched.get("handle_maker")
                        if handle_result and handle_result.matched
                        else None
                    ),
                    (
                        handle_result.matched.get("handle_model")
                        if handle_result and handle_result.matched
                        else None
                    ),
                    source_text=handle,
                    matched_by="automated_split",
                    pattern=(handle_result.pattern if handle_result else "unknown"),
                    priority=getattr(handle_result, "priority", None),
                ),
                "knot": build_knot_subdict(
                    (
                        knot_result.matched.get("brand")
                        if knot_result and knot_result.matched
                        else None
                    ),
                    (
                        knot_result.matched.get("model")
                        if knot_result and knot_result.matched
                        else None
                    ),
                    (
                        knot_result.matched.get("fiber")
                        if knot_result and knot_result.matched
                        else None
                    ),
                    (
                        knot_result.matched.get("knot_size_mm")
                        if knot_result and knot_result.matched
                        else None
                    ),
                    source_text=knot,
                    matched_by="automated_split",
                    pattern=(knot_result.pattern if knot_result else "unknown"),
                    priority=getattr(knot_result, "priority", None),
                ),
            },
            match_type="split_brush",
            pattern=f"split_on_{priority}_priority_delimiter",
            strategy="automated_split",
        )

        return result
