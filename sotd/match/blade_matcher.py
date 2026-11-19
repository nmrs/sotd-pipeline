from pathlib import Path
from typing import Any, Dict, List, Optional

from sotd.utils.data_dir import get_default_catalog_path
from sotd.utils.extract_normalization import normalize_for_matching

from .base_matcher import BaseMatcher
from .loaders import CatalogLoader
from .types import MatchResult, MatchType, create_match_result
from .utils.regex_error_utils import compile_regex_with_context, create_context_dict


class BladeMatcher(BaseMatcher):
    """
    Blade matcher with unified tiebreaker system and context-aware format prioritization.

    This matcher implements a sophisticated pattern matching system that prioritizes
    blade patterns based on specificity rather than hardcoded format preferences.

    Key Features:
    - **Unified Tiebreaker System**: All patterns are sorted by a comprehensive scoring
      system that considers format priority, pattern length, non-optional parts,
      complexity, and word boundaries.
    - **Context-Aware Matching**: When razor format is known, the system prioritizes
      appropriate blade formats while maintaining pattern specificity.
    - **Global Pattern Specificity**: For generic razor formats (like "Shavette"),
      the system uses global pattern specificity across all formats to find the best match.
    - **Flexible Fallback**: Maintains backward compatibility with existing fallback logic
      while adding new capabilities for generic cases.

    The unified tiebreaker system ensures that more specific patterns (longer, more
    complex, with more non-optional parts) are prioritized over generic patterns,
    leading to more accurate blade format identification.
    """

    def __init__(
        self,
        catalog_path: Optional[Path] = None,
        correct_matches_path: Optional[Path] = None,
        bypass_correct_matches: bool = False,
    ):
        # The default catalog resolves from the run's data dir
        # (get_data_dir: SOTD_DATA_DIR env var > "data", relative values
        # anchored at the repo root), so a bare BladeMatcher() works from
        # any working directory -- previously the bare CWD-relative
        # Path("data/blades.yaml") default made construction raise
        # FileNotFoundError from anywhere but the repo root, even with
        # SOTD_DATA_DIR set.
        if catalog_path is None:
            catalog_path = get_default_catalog_path("blades.yaml")
        super().__init__(
            catalog_path=catalog_path,
            field_type="blade",
            correct_matches_path=correct_matches_path,
            bypass_correct_matches=bypass_correct_matches,
        )
        self.loader = CatalogLoader()
        catalogs = self.loader.load_matcher_catalogs(
            catalog_path, "blade", correct_matches_path=correct_matches_path
        )
        # Override catalog and correct_matches from BaseMatcher with loader results
        self.catalog = catalogs["catalog"]
        self.correct_matches = catalogs["correct_matches"] if not bypass_correct_matches else {}
        self.patterns = self._compile_patterns()
        # Pre-compute normalized correct matches for performance
        self._normalized_correct_matches = self._precompute_normalized_correct_matches()
        # Add cache for expensive operations
        self._match_cache = {}
        # Add normalization cache for performance optimization
        self._normalization_cache: Dict[str, str] = {}
        # Build fallback formats list dynamically from catalog (general fallback)
        self._fallback_formats = self._build_fallback_formats()
        # O(1) case-insensitive lookup dictionary
        self._case_insensitive_lookup: Optional[Dict[str, List[Dict[str, Any]]]] = None

    def clear_cache(self):
        """Clear the match cache. Useful for testing to prevent cache pollution."""
        self._match_cache.clear()
        self._normalization_cache.clear()
        self._case_insensitive_lookup = None

    def _build_case_insensitive_lookup(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Build O(1) case-insensitive lookup dictionary for all correct matches.

        Returns:
            Dictionary mapping lowercase strings to match data
        """
        if self._case_insensitive_lookup is not None:
            return self._case_insensitive_lookup

        lookup = {}

        # Build lookup from normalized correct matches
        for key, matches in self._normalized_correct_matches.items():
            lookup[key.lower()] = matches

        self._case_insensitive_lookup = lookup
        return lookup

    def _normalize_with_cache(self, value: str) -> str:
        """
        Normalize value with caching for performance optimization.

        Args:
            value: Input string to normalize

        Returns:
            Normalized string
        """
        if value in self._normalization_cache:
            return self._normalization_cache[value]

        normalized = normalize_for_matching(value, field="blade")
        self._normalization_cache[value] = normalized
        return normalized

    def _build_fallback_formats(self, target_format: Optional[str] = None) -> List[str]:
        """
        Build fallback formats list dynamically from the catalog.

        Args:
            target_format: The target blade format to prioritize (if known)

        Returns formats in order of preference for fallback matching.
        """
        if not self.catalog:
            return []

        # Get all formats from the catalog
        available_formats = list(self.catalog.keys())

        # If we have a target format, prioritize it first
        if target_format:
            # Find the actual format in the catalog (case-insensitive)
            target_format_actual = None
            for fmt in available_formats:
                if fmt.upper() == target_format.upper():
                    target_format_actual = fmt
                    break

            if target_format_actual:
                fallback_formats = [target_format_actual]
                # Add remaining formats (excluding the target)
                remaining_formats = [
                    fmt for fmt in available_formats if fmt != target_format_actual
                ]
                fallback_formats.extend(remaining_formats)
                return fallback_formats

        # For general fallback (no specific target), use a reasonable default order
        # based on common usage patterns
        default_order = [
            "DE",  # Most common
            "HALF DE",  # Specialized blades
            "AC",  # Artist Club
            "GEM",  # GEM format
            "INJECTOR",  # Injector format
            "FHS",  # Feather FHS
            "HAIR SHAPER",  # Hair shaper
            "A77",  # AC77
            "CARTRIDGE",  # Cartridge razors
        ]

        # Start with default order formats that exist in catalog
        fallback_formats = [fmt for fmt in default_order if fmt in available_formats]

        # Add any remaining formats from catalog that weren't in default order
        remaining_formats = [fmt for fmt in available_formats if fmt not in default_order]
        fallback_formats.extend(remaining_formats)

        return fallback_formats

    def _build_shavette_fallback_formats(self, target_format: str) -> List[str]:
        """
        Build fallback formats list specifically for Shavettes.

        For Shavettes, prioritize format-appropriate blades over DE since DE blades
        are less common in Shavettes than specialized formats.

        Args:
            target_format: The target blade format from the razor

        Returns formats in order of preference for Shavette fallback matching.
        """
        if not self.catalog:
            return []

        # Get all formats from the catalog
        available_formats = list(self.catalog.keys())

        # For Shavettes, prioritize the target format and related formats over DE
        if target_format.upper() in ["AC", "ARTIST CLUB"]:
            # For AC razors, prioritize AC, then other specialized formats
            shavette_order = [
                "AC",  # Target format
                "GEM",  # Related single-edge format
                "Injector",  # Another single-edge format
                "Hair Shaper",  # Specialized format
                "FHS",  # Feather format
                "A77",  # AC77 format
                "Half DE",  # Half DE before full DE
                "DE",  # DE last for Shavettes
            ]
        elif target_format.upper() in ["INJECTOR"]:
            # For Injector razors, prioritize Injector, then other single-edge formats
            shavette_order = [
                "Injector",  # Target format
                "GEM",  # Related single-edge format
                "AC",  # Another single-edge format
                "Hair Shaper",  # Specialized format
                "FHS",  # Feather format
                "A77",  # AC77 format
                "Half DE",  # Half DE before full DE
                "DE",  # DE last for Shavettes
            ]
        elif target_format.upper() in ["HAIR SHAPER"]:
            # For Hair Shaper razors, prioritize Hair Shaper, then other specialized formats
            shavette_order = [
                "Hair Shaper",  # Target format
                "Injector",  # Related single-edge format
                "GEM",  # Another single-edge format
                "AC",  # Another single-edge format
                "FHS",  # Feather format
                "A77",  # AC77 format
                "Half DE",  # Half DE before full DE
                "DE",  # DE last for Shavettes
            ]
        else:
            # For other Shavette formats, use a general Shavette-appropriate order
            shavette_order = [
                target_format,  # Target format first
                "Injector",  # Common Shavette format
                "AC",  # Common Shavette format
                "GEM",  # Single-edge format
                "Hair Shaper",  # Specialized format
                "FHS",  # Feather format
                "A77",  # AC77 format
                "Half DE",  # Half DE before full DE
                "DE",  # DE last for Shavettes
            ]

        # Start with Shavette-appropriate order formats that exist in catalog
        fallback_formats = [fmt for fmt in shavette_order if fmt in available_formats]

        # Add any remaining formats from catalog that weren't in the order
        remaining_formats = [fmt for fmt in available_formats if fmt not in shavette_order]
        fallback_formats.extend(remaining_formats)

        return fallback_formats

    def _compile_patterns(self):
        compiled = []
        for format_name, brands in self.catalog.items():
            for brand, models in brands.items():
                for model, entry in models.items():
                    patterns = entry.get("patterns", [])
                    # Use the format from the catalog structure, not from the entry
                    fmt = format_name
                    for pattern in patterns:
                        context = create_context_dict(
                            file_path=str(self.catalog_path), brand=brand, model=model, format=fmt
                        )
                        compiled_pattern = compile_regex_with_context(pattern, context)
                        compiled.append((brand, model, fmt, pattern, compiled_pattern, entry))

        # Sort by pattern specificity: longer patterns first, then by pattern complexity
        # Also prioritize non-DE formats to prevent generic DE patterns from overriding
        # specific patterns
        return sorted(
            compiled, key=lambda item: self._calculate_pattern_score(item, deprioritize_de=True)
        )

    def _get_context_aware_patterns(self, target_format: str, is_shavette: bool = False):
        """
        Get patterns sorted with context-aware prioritization.

        For Shavettes and Half DE razors, prioritize patterns from the target format and
        related formats over DE patterns to avoid incorrect fallback to DE.
        """
        # Apply context-aware sorting for Shavettes and Half DE razors
        is_half_de = target_format.upper() == "HALF DE"
        if not is_shavette and not is_half_de:
            return self.patterns

        # For Shavettes and Half DE razors, re-sort patterns to prioritize target format and
        # related formats

        # Use the unified tiebreaker system with context-aware format prioritization
        # The _calculate_pattern_score method handles format priority when deprioritize_de=True
        return sorted(
            self.patterns,
            key=lambda item: self._calculate_pattern_score(item, deprioritize_de=True),
        )

    def _count_non_optional_parts(self, pattern: str) -> int:
        """
        Count non-optional parts in a regex pattern.

        Simple approach: split on '.*' and count non-empty parts.
        This handles most cases like 'personna.*hair.*shaper' -> 3 parts.
        """
        parts = pattern.split(".*")
        return len([part for part in parts if part.strip()])

    def _calculate_pattern_score(self, item, deprioritize_de: bool = False) -> tuple:
        """
        Unified tiebreaker function for both normal and context-aware cases.

        This method implements a comprehensive scoring system that prioritizes patterns
        based on multiple factors. The scoring uses negative values so that smaller
        tuples (more specific patterns) sort first.

        Args:
            item: Pattern item tuple (brand, model, fmt, pattern, compiled, entry)
            deprioritize_de: Whether to deprioritize DE formats (for context-aware cases)

        Returns:
            Tuple for sorting: (format_priority, -length_score, -non_optional_score,
            -complexity_score, -boundary_score)

            Lower tuple values = higher priority (more specific patterns)
        """
        brand, model, fmt, pattern, compiled, entry = item

        # Primary: format priority (only when deprioritize_de=True)
        # This allows context-aware matching to prioritize non-DE formats
        if deprioritize_de:
            if fmt.upper() == "DE":
                format_priority = 1  # DE gets lower priority (higher number)
            else:
                format_priority = 0  # Non-DE formats get higher priority (lower number)
        else:
            format_priority = 0  # No format bias when using global approach

        # Secondary: pattern length (longer = more specific)
        # Longer patterns are more specific and should win over shorter ones
        length_score = len(pattern)

        # Tertiary: non-optional vs optional (non-optional wins)
        # Patterns with more required parts are more specific
        non_optional_score = self._count_non_optional_parts(pattern)

        # Quaternary: pattern complexity (more special chars = more specific)
        # Complex regex patterns are more specific than simple text patterns
        complexity_score = sum(1 for c in pattern if c in r"[].*+?{}()|^$\\")

        # Quinary: word boundaries (more word boundaries = more specific)
        # Patterns with word boundaries are more precise
        boundary_score = pattern.count(r"\b") + pattern.count(r"\s")

        # Return tuple for lexicographic sorting
        # Negative values ensure smaller tuples (more specific) sort first
        return (
            format_priority,
            -length_score,
            -non_optional_score,
            -complexity_score,
            -boundary_score,
        )

    def _find_best_global_match(
        self, normalized_text: str, original: str | None = None
    ) -> MatchResult:
        """
        Find the best match across all formats using global pattern specificity.

        This method implements the global pattern specificity approach for generic
        razor formats (like "Shavette") where the blade format is unknown. Instead
        of guessing which format to use, it sorts all patterns by specificity and
        finds the most specific match, then derives the format from that match.

        The method leverages the existing self.patterns list, which is already
        sorted by the unified tiebreaker system. This ensures that the most
        specific patterns are tried first, leading to more accurate matches.

        Args:
            normalized_text: The normalized text to match against
            original: The original text (preserved in the result)

        Returns:
            MatchResult with the best match found, or a "no match" result
            with the same structure as existing code for consistency.

        Example:
            For "personna hair shaper" with generic "Shavette" razor:
            - The pattern 'person+a.*hair.*shaper' (Hair Shaper format) will win
            - Over 'person+a(?:.*inject)?' (Injector format) due to more
            - non-optional parts and better specificity
        """
        # Check correct_matches first so confirmed entries return exact, not regex
        all_correct = self._collect_all_correct_matches(normalized_text)
        if all_correct:
            orig = original or normalized_text
            return create_match_result(
                original=orig,
                matched=all_correct[0],
                match_type="exact",
                pattern=None,
            )
        # Try patterns in order until we find a match
        for brand, model, fmt, pattern, compiled, entry in self.patterns:
            if compiled.search(normalized_text):
                match_data = {
                    "brand": brand,
                    "model": str(model),
                    "format": fmt,
                }

                # Preserve all additional specifications from the catalog entry
                for key, value in entry.items():
                    if key not in ["patterns", "format"]:
                        match_data[key] = value

                return create_match_result(
                    original=original or normalized_text,
                    matched=match_data,
                    match_type=MatchType.REGEX,
                    pattern=pattern,
                )

        # No matches found - return same structure as existing "no match" case
        return create_match_result(
            original=original or normalized_text,
            matched=None,
            match_type=None,
            pattern=None,
        )

    def _precompute_normalized_correct_matches(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Pre-compute normalized correct matches for performance.

        Returns a dictionary mapping normalized strings to their match data.
        """
        if not self.correct_matches:
            return {}

        normalized_matches = {}

        # Iterate through all formats in correct matches (blade section is organized by format)
        for format_name, format_data in self.correct_matches.items():
            if not isinstance(format_data, dict):
                continue

            # Iterate through all brands in this format
            for brand, brand_data in format_data.items():
                if not isinstance(brand_data, dict):
                    continue

                # Iterate through all models in this brand
                for model, strings in brand_data.items():
                    if not isinstance(strings, list):
                        continue

                    # Find the catalog entry for this brand/model in this format
                    catalog_entry = None
                    if format_name in self.catalog:
                        format_brands = self.catalog[format_name]
                        if brand in format_brands and model in format_brands[brand]:
                            catalog_entry = format_brands[brand][model]

                    if catalog_entry is None:
                        # If not found in catalog, use empty dict
                        catalog_entry = {}

                    # Build matched data structure
                    matched = {
                        "brand": brand,
                        "model": model,
                        "format": format_name,  # Use the format from the structure
                    }
                    # Add all other catalog fields except patterns and format
                    for key, val in catalog_entry.items():
                        if key not in ["patterns", "format"]:
                            matched[key] = val

                    # Check if this string matches any of the correct strings
                    for correct_string in strings:
                        normalized_correct = normalize_for_matching(correct_string, field="blade")
                        if normalized_correct:
                            if normalized_correct not in normalized_matches:
                                normalized_matches[normalized_correct] = []
                            normalized_matches[normalized_correct].append(matched)

        return normalized_matches

    def _match_with_regex(self, normalized_text: str, original_text: str) -> MatchResult:
        """Match blade using regex patterns."""
        # Check cache first
        if normalized_text in self._match_cache:
            cached_result = self._match_cache[normalized_text]
            # Convert cached dict to MatchResult for backward compatibility
            if isinstance(cached_result, dict):
                return create_match_result(
                    original=cached_result.get("original", original_text),
                    matched=cached_result.get("matched"),
                    match_type=cached_result.get("match_type"),
                    pattern=cached_result.get("pattern"),
                )
            return cached_result

        original = original_text

        # Use cached normalization for performance
        normalized = self._normalize_with_cache(normalized_text)
        if not normalized:
            result = create_match_result(
                original=original,
                matched=None,
                match_type=None,
                pattern=None,
            )
            self._match_cache[normalized_text] = result
            return result

        blade_text = normalized

        for brand, model, fmt, raw_pattern, compiled, entry in self.patterns:
            if compiled.search(blade_text):
                match_data = {
                    "brand": brand,
                    "model": str(model),
                    "format": fmt,
                }

                # Preserve all additional specifications from the catalog entry
                for key, val in entry.items():
                    if key not in ["patterns", "format"]:
                        match_data[key] = val

                result = create_match_result(
                    original=original,
                    matched=match_data,
                    pattern=raw_pattern,
                    match_type=MatchType.REGEX,
                )
                self._match_cache[normalized_text] = result
                return result

        result = create_match_result(
            original=original,
            matched=None,
            match_type=None,
            pattern=None,
        )
        self._match_cache[normalized_text] = result
        return result

    def _collect_all_correct_matches(self, value: str) -> List[Dict[str, Any]]:
        """
        Collect all correct matches for a given string.

        Returns a list of all matching brand/model combinations from correct_matches.yaml.
        """
        # Check cache first
        cache_key = f"correct_matches:{value}"
        if cache_key in self._match_cache:
            return self._match_cache[cache_key]

        if not value or not self._normalized_correct_matches:
            self._match_cache[cache_key] = []
            return []

        # Use cached normalization for performance
        normalized_value = self._normalize_with_cache(value)
        if not normalized_value:
            self._match_cache[cache_key] = []
            return []

        # Try exact match first
        if normalized_value in self._normalized_correct_matches:
            result = self._normalized_correct_matches[normalized_value]
            self._match_cache[cache_key] = result
            return result

        # If no exact match, try case-insensitive match using O(1) lookup
        lookup = self._build_case_insensitive_lookup()
        matches = lookup.get(normalized_value.lower())
        if matches:
            self._match_cache[cache_key] = matches
            return matches

        self._match_cache[cache_key] = []
        return []

    def _collect_correct_matches_in_format(
        self, value: str, target_format: str
    ) -> List[Dict[str, Any]]:
        """
        Collect correct matches for a given string in a specific format only.

        Args:
            value: The string to match
            target_format: The target format to search in

        Returns:
            List of correct matches in the target format
        """
        if not value or not self._normalized_correct_matches:
            return []

        # Use cached normalization for performance
        normalized_value = self._normalize_with_cache(value)
        if not normalized_value:
            return []

        # Find all correct matches
        all_matches = []

        # Try exact match first
        if normalized_value in self._normalized_correct_matches:
            all_matches = self._normalized_correct_matches[normalized_value]
        else:
            # If no exact match, try case-insensitive match
            normalized_value_lower = normalized_value.lower()
            for key, matches in self._normalized_correct_matches.items():
                if key.lower() == normalized_value_lower:
                    all_matches = matches
                    break

        # Filter to only include matches in the target format
        format_matches = [m for m in all_matches if m["format"].upper() == target_format.upper()]
        return format_matches

    def _match_regex_in_format(
        self, normalized_value: str, target_format: str, is_shavette: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Match using regex patterns in a specific format only.

        Args:
            normalized_value: The normalized string to match
            target_format: The target format to search in
            is_shavette: Whether this is a Shavette razor for context-aware matching

        Returns:
            Match result or None if no match found
        """
        # Use context-aware patterns for Shavettes
        patterns_to_search = self._get_context_aware_patterns(target_format, is_shavette)

        # Search only patterns in the target format
        for brand, model, fmt, raw_pattern, compiled, entry in patterns_to_search:
            if fmt.upper() == target_format.upper() and compiled.search(normalized_value):
                match_data = {
                    "brand": brand,
                    "model": str(model),
                    "format": fmt,
                }

                # Preserve all additional specifications from the catalog entry
                for key, value in entry.items():
                    if key not in ["patterns", "format"]:
                        match_data[key] = value

                return {
                    "original": normalized_value,
                    "matched": match_data,
                    "pattern": raw_pattern,
                    "match_type": MatchType.REGEX,
                }

        return None

    def _filter_by_format(
        self, matches: List[Dict[str, Any]], target_format: str
    ) -> Optional[Dict[str, Any]]:
        """
        Filter matches by format compatibility.

        Args:
            matches: List of all matching brand/model combinations
            target_format: Target blade format (e.g., "DE", "GEM", "AC")

        Returns:
            Best matching format or first match if no format match found
        """
        if not matches:
            return None

        # First, try to find exact format matches
        format_matches = [m for m in matches if m["format"].upper() == target_format.upper()]
        if format_matches:
            return format_matches[0]  # Return first format match

        # Special fallback case: Half DE razors can use DE blades
        # Only use fallback if no Half DE matches exist at all
        if target_format.upper() == "HALF DE":
            half_de_matches = [m for m in matches if m["format"].upper() == "HALF DE"]
            if not half_de_matches:  # Only fallback if no Half DE matches exist
                de_matches = [m for m in matches if m["format"].upper() == "DE"]
                if de_matches:
                    return de_matches[0]  # Return first DE match as fallback

        # If no exact format match and no fallback, return the first match
        return matches[0]

    def _get_normalized_text(self, value: str) -> str:
        """
        Return normalized text directly.

        Args:
            value: Normalized text string

        Returns:
            Normalized text string
        """
        return value

    def _get_original_text(self, value: str) -> str:
        """
        Return original text directly.

        Args:
            value: Original text string

        Returns:
            Original text string
        """
        return value

    def _get_target_blade_format(self, razor_format: str) -> str:
        """
        Map razor formats to blade formats.

        Args:
            razor_format: The razor format string (e.g., "SHAVETTE (HAIR SHAPER)", "STRAIGHT")

        Returns:
            The corresponding blade format string (e.g., "HAIR SHAPER", "STRAIGHT")
        """
        if not razor_format:
            return "DE"  # Default to DE if no format provided

        # Use lowercase keys for case-insensitive mapping
        format_mapping = {
            "shavette (hair shaper)": "HAIR SHAPER",
            "shavette (ac)": "AC",
            "shavette (gem)": "GEM",
            "shavette (injector)": "INJECTOR",
            "shavette (fhs)": "FHS",
            "shavette (a77)": "A77",
            "shavette (cartridge)": "CARTRIDGE",
            "shavette (disposable)": "CARTRIDGE",
            "shavette (straight)": "STRAIGHT",
            "shavette (half de)": "HALF DE",
            "shavette (de)": "DE",
            "shavette (unspecified)": "DE",
            "shavette (predefined)": "DE",
            "straight": "STRAIGHT",
            "half de": "HALF DE",  # Add missing mapping for plain "Half DE"
            "half de (multi-blade)": "HALF DE",
        }
        return format_mapping.get(razor_format.lower(), razor_format)

    def match_with_context(
        self, normalized_text: str, razor_format: str, original_text: str | None = None
    ) -> MatchResult:
        """Match blade with context-aware format prioritization and flexible fallback."""
        # Use provided original text or default to normalized text
        original = original_text if original_text is not None else normalized_text

        # Determine target blade format from razor format
        target_blade_format = self._get_target_blade_format(razor_format)

        # Skip blade matching for straight razors
        if target_blade_format == "STRAIGHT":
            result = create_match_result(
                original=original,
                matched=None,
                match_type=None,
                pattern=None,
            )
            return result

        # Track which formats we've already searched to avoid redundant work
        searched_formats = set()

        # Determine if this is a Shavette razor for context-aware matching
        is_shavette = razor_format.upper().startswith("SHAVETTE")

        # 1. Try correct matches in target format first
        if normalized_text:
            searched_formats.add(target_blade_format.upper())
            correct_target = self._collect_correct_matches_in_format(
                normalized_text, target_blade_format
            )
            if correct_target:
                result = create_match_result(
                    original=original,
                    matched=correct_target[0],
                    match_type="exact",
                    pattern=None,
                )
                return result

        # 2. Try regex matching in target format
        if normalized_text:
            regex_target = self._match_regex_in_format(
                normalized_text, target_blade_format, is_shavette
            )
            if regex_target:
                result = create_match_result(
                    original=original,
                    matched=regex_target["matched"],
                    match_type=MatchType.REGEX,
                    pattern=regex_target.get("pattern"),
                )
                return result

        # 3. Try Half DE format if target is DE (special case)
        if target_blade_format.upper() == "DE" and normalized_text:
            searched_formats.add("HALF DE")
            correct_half_de = self._collect_correct_matches_in_format(normalized_text, "HALF DE")
            if correct_half_de:
                result = create_match_result(
                    original=original,
                    matched=correct_half_de[0],
                    match_type="exact",
                    pattern=None,
                )
                return result
            regex_half_de = self._match_regex_in_format(normalized_text, "HALF DE", is_shavette)
            if regex_half_de:
                result = create_match_result(
                    original=original,
                    matched=regex_half_de["matched"],
                    match_type=MatchType.REGEX,
                    pattern=regex_half_de.get("pattern"),
                )
                return result

        # 3.25. Try DE format if target is Half DE (special case)
        if target_blade_format.upper() == "HALF DE" and normalized_text:
            searched_formats.add("DE")
            correct_de = self._collect_correct_matches_in_format(normalized_text, "DE")
            if correct_de:
                result = create_match_result(
                    original=original,
                    matched=correct_de[0],
                    match_type="exact",
                    pattern=None,
                )
                return result
            regex_de = self._match_regex_in_format(normalized_text, "DE", is_shavette)
            if regex_de:
                result = create_match_result(
                    original=original,
                    matched=regex_de["matched"],
                    match_type=MatchType.REGEX,
                    pattern=regex_de.get("pattern"),
                )
                return result

        # 3.5. Try FHS format if target is Other (special case for Valet AutoStrop razors)
        if target_blade_format.upper() == "OTHER" and normalized_text:
            searched_formats.add("FHS")
            correct_fhs = self._collect_correct_matches_in_format(normalized_text, "FHS")
            if correct_fhs:
                result = create_match_result(
                    original=original,
                    matched=correct_fhs[0],
                    match_type="exact",
                    pattern=None,
                )
                return result
            regex_fhs = self._match_regex_in_format(normalized_text, "FHS", is_shavette)
            if regex_fhs:
                result = create_match_result(
                    original=original,
                    matched=regex_fhs["matched"],
                    match_type=MatchType.REGEX,
                    pattern=regex_fhs.get("pattern"),
                )
                return result

        # 4. General fallback system: try format-appropriate blades first
        if normalized_text:
            # Check if this is generic "Shavette" or "Other" format (case-insensitive)
            if razor_format.lower() in ["shavette", "other"]:
                # Use global pattern specificity approach for generic formats
                return self._find_best_global_match(normalized_text, original)

            # Determine if this is a Shavette razor for special fallback logic
            is_shavette = razor_format.upper().startswith("SHAVETTE")

            # For Shavettes, use Shavette-specific fallback that prioritizes
            # format-appropriate blades
            if is_shavette:
                # Use Shavette-specific fallback order that prioritizes target format and
                # related formats over DE
                fallback_formats = self._build_shavette_fallback_formats(target_blade_format)
            else:
                # For non-Shavettes (dedicated razors), use standard fallback with DE priority
                # Try DE format first (most common) - unless we already searched it
                if "DE" not in searched_formats:
                    correct_de = self._collect_correct_matches_in_format(normalized_text, "DE")
                    if correct_de:
                        result = create_match_result(
                            original=original,
                            matched=correct_de[0],
                            match_type="exact",
                            pattern=None,
                        )
                        return result
                    regex_de = self._match_regex_in_format(normalized_text, "DE", is_shavette)
                    if regex_de:
                        result = create_match_result(
                            original=original,
                            matched=regex_de["matched"],
                            match_type=MatchType.REGEX,
                            pattern=regex_de.get("pattern"),
                        )
                        return result

                # Use context-aware fallback list if we have a target format
                if target_blade_format and target_blade_format != "DE":
                    fallback_formats = self._build_fallback_formats(target_blade_format)
                else:
                    fallback_formats = self._fallback_formats

            # Try fallback formats in order - skip already searched formats
            for fallback_format in fallback_formats:
                if fallback_format not in searched_formats:
                    correct_fallback = self._collect_correct_matches_in_format(
                        normalized_text, fallback_format
                    )
                    if correct_fallback:
                        result = create_match_result(
                            original=original,
                            matched=correct_fallback[0],
                            match_type="exact",
                            pattern=None,
                        )
                        return result
                    regex_fallback = self._match_regex_in_format(
                        normalized_text, fallback_format, is_shavette
                    )
                    if regex_fallback:
                        result = create_match_result(
                            original=original,
                            matched=regex_fallback["matched"],
                            match_type=MatchType.REGEX,
                            pattern=regex_fallback.get("pattern"),
                        )
                        return result

        # 5. Not found
        result = create_match_result(
            original=original,
            matched=None,
            match_type=None,
            pattern=None,
        )
        return result

    def match(
        self, value: str, original: str | None = None, bypass_correct_matches: bool = False
    ) -> MatchResult:
        """
        Match blade with format-aware logic and flexible fallback.

        When no context is provided, prioritizes more specific patterns over default DE format.
        Includes flexible fallback to try DE first, then other formats.
        """
        # Use provided original text or default to normalized text
        original_text = original if original is not None else value
        normalized_text = value

        # First try correct matches without context (will find all matches)
        all_correct_matches = self._collect_all_correct_matches(normalized_text)
        if all_correct_matches:
            # If we have multiple matches, prioritize by format compatibility
            # Prioritize DE over Half DE when no specific context is provided
            de_matches = [m for m in all_correct_matches if m["format"].upper() == "DE"]
            if de_matches:
                return create_match_result(
                    original=original_text,
                    matched=de_matches[0],
                    match_type="exact",
                    pattern=None,
                )

            # If no DE matches, return the first match
            return create_match_result(
                original=original_text,
                matched=all_correct_matches[0],
                match_type="exact",
                pattern=None,
            )

        # If no correct matches, use regex matching with format prioritization
        if not normalized_text:
            return create_match_result(
                original=original_text,
                matched=None,
                match_type=None,
                pattern=None,
            )

        blade_text = normalized_text

        # Collect all regex matches with their patterns
        # Since self.patterns is already sorted by pattern specificity (with deprioritize_de=True),
        # the first match we find will be the most specific pattern
        for brand, model, fmt, raw_pattern, compiled, entry in self.patterns:
            if compiled.search(blade_text):
                match_data = {
                    "brand": brand,
                    "model": str(model),
                    "format": fmt,
                }

                # Preserve all additional specifications from the catalog entry
                for key, value in entry.items():
                    if key not in ["patterns", "format"]:
                        match_data[key] = value

                # Return the first (most specific) match
                return create_match_result(
                    original=original_text,
                    matched=match_data,
                    match_type=MatchType.REGEX,
                    pattern=raw_pattern,
                )

        # No matches found
        return create_match_result(
            original=original_text,
            matched=None,
            match_type=None,
            pattern=None,
        )

    def match_cartridge_auto(self, original_text: str) -> MatchResult:
        """
        Automatically match blade to Cartridge/Disposable format.

        This method is called when the razor format is Cartridge/Disposable,
        and the blade should automatically be matched to the Cartridge/Disposable
        blade entry regardless of the blade text.

        Args:
            original_text: The original blade text (preserved for reference)

        Returns:
            MatchResult with Cartridge/Disposable blade match
        """
        cartridge_match = {
            "brand": "Cartridge/Disposable",
            "model": "",
            "format": "Cartridge/Disposable",
        }

        return create_match_result(
            original=original_text,
            matched=cartridge_match,
            match_type="auto_cartridge",
            pattern="cartridge_razor_format",
        )
