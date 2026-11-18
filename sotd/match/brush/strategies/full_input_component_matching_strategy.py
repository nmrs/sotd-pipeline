#!/usr/bin/env python3
"""Unified component matching strategy that handles both dual and single component matches."""

from pathlib import Path
from typing import List, Optional

# ComponentScoreCalculator no longer needed - scoring is handled externally
from sotd.match.types import MatchResult

from ..comparison.splits_loader import BrushSplitsLoader
from .base_brush_matching_strategy import (
    BaseMultiResultBrushMatchingStrategy,
)
from .utils.knot_signal_utils import knot_signal_spans
from .utils.subdict_builders import build_handle_subdict, build_knot_subdict


class FullInputComponentMatchingStrategy(BaseMultiResultBrushMatchingStrategy):
    """
    Unified strategy for component matching that handles both dual and single component scenarios.

    This strategy runs HandleMatcher and KnotMatcher once and combines their results:
    - If both match: Creates dual component result (score 65)
    - If only one matches: Creates single component result (score 50)
    - If neither matches: Returns None
    """

    def __init__(
        self,
        handle_matcher,
        knot_matcher,
        catalogs: dict,
        brush_splits_path: Optional[Path] = None,
        splits_loader: Optional[BrushSplitsLoader] = None,
    ):
        """
        Initialize the unified component matching strategy.

        Args:
            handle_matcher: HandleMatcher instance for handle matching
            knot_matcher: KnotMatcher instance for knot matching
            catalogs: Dictionary containing all catalog data
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
        self.handle_matcher = handle_matcher
        self.knot_matcher = knot_matcher
        self.catalogs = catalogs

        # The brush-split source must be explicit: a shared loader, or a path.
        if splits_loader is not None:
            self.splits_loader = splits_loader
        elif brush_splits_path is not None:
            self.splits_loader = BrushSplitsLoader(brush_splits_path)
        else:
            raise ValueError(
                "FullInputComponentMatchingStrategy requires splits_loader or "
                "brush_splits_path; pass the run's data-dir "
                "brush_splits.yaml explicitly"
            )

    def match(self, value: str | dict, full_string: Optional[str] = None) -> Optional[MatchResult]:
        """
        Match a brush string using unified component matching logic.
        Returns the best single result for backward compatibility.

        Args:
            value: The brush string or field data object to match

        Returns:
            MatchResult or None
        """
        all_results = self.match_all(value)
        return all_results[0] if all_results else None

    def match_all(self, value: str | dict) -> List[MatchResult]:
        """
        Match a brush string and return all possible brand combination results.

        Args:
            value: The brush string or field data object to match

        Returns:
            List of MatchResult objects for all possible matches
        """
        # Handle both string and field data object inputs
        if isinstance(value, dict):
            # Extract normalized text from field data object
            text = value.get("normalized", value.get("original", ""))
        else:
            # Direct string input
            text = value

        if not text or not isinstance(text, str):
            return []

        # Check if this brush should not be split (from brush_splits.yaml)
        if self.splits_loader.should_not_split(text):
            # Skip all split strategies if should_not_split is True
            return []

        results = []
        seen_combinations = set()

        # Run both matchers once
        handle_result = None
        knot_result = None

        try:
            handle_result = self.handle_matcher.match_handle_maker(text)
        except Exception:
            # Handle matcher failed, continue with None
            pass

        try:
            knot_result = self.knot_matcher.match(text)
        except Exception:
            # Knot matcher failed, continue with None
            pass

        # Determine match type and create results
        if handle_result and knot_result:
            # Both matched - dual component
            # Extract brands for comparison
            handle_brand = self._extract_brand_from_result(handle_result)
            knot_brand = self._extract_brand_from_result(knot_result)

            # Validate assignment: when both matchers fire on the full text,
            # the handle brand should appear BEFORE the knot brand (convention:
            # "Handle Knot").  If positions are reversed, re-match the substrings.
            if handle_brand and knot_brand and handle_brand != knot_brand:
                corrected = self._correct_brand_positions(text, handle_result, knot_result)
                if corrected:
                    handle_result, knot_result = corrected
                    handle_brand = self._extract_brand_from_result(handle_result)
                    knot_brand = self._extract_brand_from_result(knot_result)

            # Always include the original combination
            combination_key = (handle_brand, knot_brand)
            if combination_key not in seen_combinations:
                result = self._create_dual_component_result(handle_result, knot_result, text)
                if result:
                    result.strategy = "full_input_component_matching"
                    result.match_type = "composite"
                    results.append(result)
                    seen_combinations.add(combination_key)

            # Check if both components have the same brand
            if handle_brand and knot_brand and handle_brand == knot_brand:
                # Same brand - generate alternative combinations
                self._generate_alternative_combinations(
                    text, handle_result, knot_result, results, seen_combinations
                )
        elif handle_result or knot_result:
            # Only one matched - single component
            if handle_result:
                result = self._convert_handle_result_to_brush_result(handle_result)
            elif knot_result:
                result = self._convert_knot_result_to_brush_result(knot_result)
            else:
                return []

            if result:
                result.strategy = "full_input_component_matching"
                result.match_type = "single_component"
                results.append(result)

        return results

    def _generate_alternative_combinations(
        self,
        text: str,
        original_handle_result,
        original_knot_result,
        results: List[MatchResult],
        seen_combinations: set,
    ) -> None:
        """
        Generate alternative brand combinations when both components have the same brand.

        Args:
            text: Original text to match against
            original_handle_result: Original handle match result
            original_knot_result: Original knot match result
            results: List to add new results to
            seen_combinations: Set to track seen combinations for deduplication
        """
        original_handle_brand = self._extract_brand_from_result(original_handle_result)
        original_knot_brand = self._extract_brand_from_result(original_knot_result)

        # Try to find alternative handle with different brand
        alternative_handle_result = self._match_handle_with_exclusions(
            text, {original_handle_brand}
        )

        # Try to find alternative knot with different brand
        alternative_knot_result = self._match_knot_with_exclusions(text, {original_knot_brand})

        # Generate all possible combinations
        combinations_to_try = []

        # Original + alternative knot
        if alternative_knot_result:
            combinations_to_try.append((original_handle_result, alternative_knot_result))

        # Alternative handle + original knot
        if alternative_handle_result:
            combinations_to_try.append((alternative_handle_result, original_knot_result))

        # Alternative handle + alternative knot
        if alternative_handle_result and alternative_knot_result:
            combinations_to_try.append((alternative_handle_result, alternative_knot_result))

        # Create results for valid combinations
        for handle_res, knot_res in combinations_to_try:
            handle_brand = self._extract_brand_from_result(handle_res)
            knot_brand = self._extract_brand_from_result(knot_res)
            combination_key = (handle_brand, knot_brand)

            if combination_key not in seen_combinations:
                result = self._create_dual_component_result(handle_res, knot_res, text)
                if result:
                    result.strategy = "full_input_component_matching"
                    result.match_type = "composite"
                    results.append(result)
                    seen_combinations.add(combination_key)

    def _match_handle_with_exclusions(
        self, text: str, excluded_brands: set[str]
    ) -> Optional[MatchResult]:
        """
        Match handle while excluding specific brands.

        Args:
            text: Text to match against
            excluded_brands: Set of brand names to exclude (case-insensitive)

        Returns:
            MatchResult if match found and brand not excluded, None otherwise
        """
        try:
            result = self.handle_matcher.match_handle_maker(text)
            if result is None:
                return None

            # Extract brand from result
            brand = self._extract_brand_from_result(result)
            if not brand:
                return result  # No brand to exclude

            # Check if brand is in excluded set (case-insensitive)
            if brand.lower() in {b.lower() for b in excluded_brands}:
                return None

            return result
        except Exception:
            # Handle matcher failed, return None
            return None

    def _match_knot_with_exclusions(
        self, text: str, excluded_brands: set[str]
    ) -> Optional[MatchResult]:
        """
        Match knot while excluding specific brands.

        Args:
            text: Text to match against
            excluded_brands: Set of brand names to exclude (case-insensitive)

        Returns:
            MatchResult if match found and brand not excluded, None otherwise
        """
        try:
            result = self.knot_matcher.match(text)
            if result is None:
                return None

            # Extract brand from result
            brand = self._extract_brand_from_result(result)
            if not brand:
                return result  # No brand to exclude

            # Check if brand is in excluded set (case-insensitive)
            if brand.lower() in {b.lower() for b in excluded_brands}:
                return None

            return result
        except Exception:
            # Knot matcher failed, return None
            return None

    # ------------------------------------------------------------------
    # Brand-position validation for dual-component matches
    # ------------------------------------------------------------------

    @staticmethod
    def _find_brand_span(text: str, brand_name: str) -> tuple[int, int]:
        """Return (start, end) of a brand name in *text* (case-insensitive).

        Handles the common variation where the canonical name has a
        trailing 's' but the user's text does not
        (e.g. "DS Cosmetics" vs "DS Cosmetic").

        Returns (-1, -1) when the brand cannot be located.
        """
        text_lower = text.lower()
        brand_lower = brand_name.lower()

        pos = text_lower.find(brand_lower)
        if pos != -1:
            return pos, pos + len(brand_lower)

        if brand_lower.endswith("s"):
            shorter = brand_lower[:-1]
            pos = text_lower.find(shorter)
            if pos != -1:
                return pos, pos + len(shorter)

        return -1, -1

    def _correct_brand_positions(self, text, handle_result, knot_result):
        """Validate handle/knot assignment using proximity to knot signals.

        When both matchers fire on the full text they each grab the first
        brand their patterns match, which may assign the roles backwards.

        This method locates every knot-indicative token (mm sizes, fiber
        words, "knot", batch codes …) and both brand names, then checks
        which brand is *closer* to those knot signals.  The closer brand
        is the knot maker; the other is the handle maker.

        If the current assignment is already correct (or there are no knot
        signals to disambiguate), returns None.  Otherwise re-matches the
        two substrings with the correct matchers and returns the corrected
        (handle_result, knot_result) tuple.
        """
        # Get original-case brand names
        if hasattr(handle_result, "matched"):
            handle_brand = (handle_result.matched or {}).get("handle_maker", "")
        else:
            handle_brand = (handle_result or {}).get("handle_maker", "")

        if hasattr(knot_result, "matched"):
            knot_brand = (knot_result.matched or {}).get("brand", "")
        else:
            knot_brand = (knot_result or {}).get("brand", "")

        if not handle_brand or not knot_brand:
            return None

        # If the knot result has a specific model (known_knots match like B13,
        # G5C, v27), the KnotMatcher's assignment is authoritative — don't
        # override it with a proximity heuristic.
        if hasattr(knot_result, "matched"):
            knot_model = (knot_result.matched or {}).get("model")
        else:
            knot_model = (knot_result or {}).get("model")
        if knot_model and knot_model.lower() not in ("unspecified", ""):
            return None

        # Locate each brand in the text
        handle_start, handle_end = self._find_brand_span(text, handle_brand)
        knot_start, knot_end = self._find_brand_span(text, knot_brand)

        if handle_start == -1 or knot_start == -1:
            return None

        # Locate knot-signal tokens (as spans)
        signal_spans = knot_signal_spans(text)
        if not signal_spans:
            return None  # no knot signals → nothing to disambiguate

        # Proximity = minimum gap between brand span and any signal span.
        # A gap of 0 means they overlap or are adjacent.
        # The brand whose span is closest to a knot signal is the knot maker.
        def _span_gap(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
            """Compute the gap between two spans (0 if overlapping/adjacent)."""
            return max(0, max(a_start - b_end, b_start - a_end))

        handle_proximity = min(
            _span_gap(handle_start, handle_end, s_start, s_end) for s_start, s_end in signal_spans
        )
        knot_proximity = min(
            _span_gap(knot_start, knot_end, s_start, s_end) for s_start, s_end in signal_spans
        )

        if handle_proximity >= knot_proximity:
            # Current assignment looks correct (or tied) — no swap needed
            return None

        # The "handle" brand is actually the knot maker.  Split the text so
        # each matcher gets the substring containing its brand.
        # actual_knot_pos  = where the true knot brand (currently labelled handle) sits
        # actual_handle_pos = where the true handle brand (currently labelled knot) sits
        actual_knot_pos = handle_start
        actual_handle_pos = knot_start

        if actual_knot_pos > actual_handle_pos:
            # True handle appears first, true knot appears second
            handle_text = text[:actual_knot_pos].strip()
            knot_text = text[actual_knot_pos:].strip()
        else:
            # True knot appears first, true handle appears second
            knot_text = text[:actual_handle_pos].strip()
            handle_text = text[actual_handle_pos:].strip()

        if not handle_text or not knot_text:
            return None

        try:
            new_handle = self.handle_matcher.match_handle_maker(handle_text)
            new_knot = self.knot_matcher.match(knot_text, full_string=text)
        except Exception:
            return None

        if new_handle and new_knot:
            return new_handle, new_knot

        return None

    def _extract_brand_from_result(self, result) -> str:
        """
        Extract brand name from a match result for consistent comparison.

        Args:
            result: MatchResult or dict containing match data

        Returns:
            Lowercase brand name for consistent comparison
        """
        if result is None:
            return ""

        # Handle MatchResult objects
        if hasattr(result, "matched"):
            matched_data = result.matched or {}
        else:
            # Handle dict results
            matched_data = result or {}

        # Extract brand based on result type
        # Handle results have "handle_maker" field
        if "handle_maker" in matched_data:
            brand = matched_data.get("handle_maker", "")
        # Knot results have "brand" field
        elif "brand" in matched_data:
            brand = matched_data.get("brand", "")
        else:
            brand = ""

        # Return lowercase for consistent comparison
        return brand.lower() if brand else ""

    def _create_dual_component_result(self, handle_result, knot_result, value: str) -> MatchResult:
        """Create a dual component result combining handle and knot."""
        # Extract handle data - handle_result might be a dict or MatchResult
        if hasattr(handle_result, "matched"):
            handle_data = handle_result.matched or {}
        else:
            handle_data = handle_result or {}

        # Extract knot data - knot_result should be a MatchResult
        if hasattr(knot_result, "matched"):
            knot_data = knot_result.matched or {}
        else:
            knot_data = knot_result or {}

        # Create combined brush data with nested handle/knot structure
        brush_data = {
            "brand": None,  # Multi-component brushes should not have top-level brand
            "model": None,  # Multi-component brushes should not have top-level model
            "fiber": knot_data.get("fiber"),
            "knot_size_mm": knot_data.get("knot_size_mm"),
            "handle_maker": handle_data.get("handle_maker"),
            "source_text": value,
            "_matched_by": "FullInputComponentMatchingStrategy",
            "_pattern": "dual_component",
            "_original_handle_text": handle_data.get("source_text"),
            "_original_knot_text": knot_data.get("source_text"),
            # Add nested handle and knot sections for modifier functions
            "handle": build_handle_subdict(
                handle_data.get("handle_maker"),
                handle_data.get("handle_model"),
                source_text=handle_data.get("source_text", value),
                matched_by="HandleMatcher",
                pattern=handle_data.get("_pattern_used"),
            ),
            "knot": build_knot_subdict(
                knot_data.get("brand"),
                knot_data.get("model"),
                knot_data.get("fiber"),
                knot_data.get("knot_size_mm"),
                source_text=knot_data.get("source_text", value),
                matched_by="KnotMatcher",
                pattern=(
                    knot_result.pattern
                    if hasattr(knot_result, "pattern")
                    else knot_data.get("_pattern_used")
                ),
            ),
        }

        # Component scores are now calculated externally by the scoring engine
        # No need to pre-calculate scores here

        return MatchResult(
            original=value, matched=brush_data, match_type="composite", pattern="dual_component"
        )

    def _create_single_component_result(
        self, component_result: MatchResult, value: str, component_type: str
    ) -> MatchResult:
        """Create a single component result."""
        if component_type == "handle":
            return self._convert_handle_result_to_brush_result(component_result)
        elif component_type == "knot":
            return self._convert_knot_result_to_brush_result(component_result)
        else:
            return component_result

    def _convert_handle_result_to_brush_result(self, handle_result) -> MatchResult:
        """Convert HandleMatcher result to brush format."""
        # Handle both dict and MatchResult types
        if hasattr(handle_result, "matched"):
            handle_data = handle_result.matched or {}
        else:
            handle_data = handle_result or {}

        brush_data = {
            "brand": handle_data.get("handle_maker"),
            "model": handle_data.get("handle_model"),
            "source_text": handle_data.get("source_text", ""),
            "_matched_by": "HandleMatcher",
            "_pattern": handle_data.get("_pattern_used"),
            # Add nested handle and knot sections for modifier functions
            "handle": build_handle_subdict(
                handle_data.get("handle_maker"),
                handle_data.get("handle_model"),
                source_text=handle_data.get("source_text", ""),
                matched_by="HandleMatcher",
                pattern=handle_data.get("_pattern_used"),
            ),
            "knot": build_knot_subdict(
                None,
                None,
                source_text="",
                matched_by="HandleMatcher",
                pattern=handle_data.get("_pattern_used"),
            ),
        }

        return MatchResult(
            original="",  # Handle matcher doesn't provide original text
            matched=brush_data,
            match_type="handle",
            pattern=handle_data.get("_pattern_used"),
        )

    def _convert_knot_result_to_brush_result(self, knot_result: MatchResult) -> MatchResult:
        """Convert KnotMatcher result to brush format."""
        knot_data = knot_result.matched or {}
        # Get pattern from MatchResult.pattern, not from matched data
        knot_pattern = (
            knot_result.pattern or knot_data.get("_pattern_used") or knot_data.get("_pattern")
        )

        brush_data = {
            "brand": knot_data.get("brand"),
            "model": knot_data.get("model"),
            "source_text": knot_data.get("source_text", ""),
            "_matched_by": "KnotMatcher",
            "_pattern": knot_pattern,
            # Add nested handle and knot sections for modifier functions
            "handle": build_handle_subdict(
                None,
                None,
                source_text="",
                matched_by="KnotMatcher",
                pattern=knot_pattern,
            ),
            "knot": build_knot_subdict(
                knot_data.get("brand"),
                knot_data.get("model"),
                knot_data.get("fiber"),
                knot_data.get("knot_size_mm"),
                source_text=knot_data.get("source_text", ""),
                matched_by="KnotMatcher",
                pattern=knot_pattern,
            ),
        }

        return MatchResult(
            original="",  # Knot matcher doesn't provide original text
            matched=brush_data,
            match_type="knot",
            pattern=knot_pattern,
            strategy="full_input_component_matching",
        )
