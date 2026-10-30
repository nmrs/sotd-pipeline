import re

import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from sotd.utils.catalog_validator import validate_patterns_format
from sotd.utils.yaml_loader import UniqueKeyLoader, load_yaml_with_nfc

from .types import MatchResult, create_match_result

# Global catalog cache for YAML files
_catalog_cache = {}


def clear_catalog_cache() -> None:
    """Clear the global catalog cache. Useful when catalog files are modified."""
    global _catalog_cache
    _catalog_cache.clear()


class BaseMatcher:
    def __init__(
        self,
        catalog_path: Path,
        field_type: str,
        correct_matches_path: Optional[Path] = None,
        bypass_correct_matches: bool = False,
    ):
        self.catalog_path = catalog_path
        self.field_type = field_type  # "razor", "blade", "brush", "soap"
        self.correct_matches_path = correct_matches_path or Path("data/correct_matches")
        self.bypass_correct_matches = bypass_correct_matches
        self.catalog = self._load_catalog()
        self.correct_matches = self._load_correct_matches()

        # Lazy-loaded caches for performance optimization
        self._correct_matches_lookup: Optional[Dict[str, Dict[str, Any]]] = None
        self._catalog_patterns: Optional[List[Dict[str, Any]]] = None
        self._compiled_patterns: Dict[str, Any] = {}  # Pattern -> compiled regex

    def _load_catalog(self) -> dict:
        # Use global cache to avoid repeated YAML loads
        global _catalog_cache
        cache_key = str(self.catalog_path.resolve())
        if cache_key not in _catalog_cache:
            catalog_data = load_yaml_with_nfc(self.catalog_path, loader_cls=UniqueKeyLoader)
            # Validate patterns format before caching
            validate_patterns_format(catalog_data, self.catalog_path)
            _catalog_cache[cache_key] = catalog_data
        return _catalog_cache[cache_key]

    def _load_correct_matches(self) -> Dict[str, Dict[str, Any]]:
        """Load correct matches for this field type from correct_matches directory with caching."""
        if self.bypass_correct_matches:
            return {}

        # Directory structure mode with caching
        field_file = self.correct_matches_path / f"{self.field_type}.yaml"
        if not field_file.exists():
            return {}

        try:
            # Use global cache to avoid repeated YAML loads
            global _catalog_cache
            cache_key = str(field_file.resolve())
            if cache_key not in _catalog_cache:
                _catalog_cache[cache_key] = load_yaml_with_nfc(
                    field_file, loader_cls=UniqueKeyLoader
                )
            return _catalog_cache[cache_key]
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as e:
            # A missing correct_matches file is fine (returns {} above). Any
            # OTHER load failure must surface loudly: silently falling back
            # to regex-only matching would corrupt the whole run.
            raise ValueError(
                f"Failed to load correct matches file {field_file}: {e}"
            ) from e

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

    def _build_correct_matches_lookup(self) -> Dict[str, Dict[str, Any]]:
        """
        Build a fast lookup dictionary from correct matches.

        Converts the nested structure to a flat dictionary for O(1) lookups.
        Uses pre-normalized text from extraction.
        """
        lookup = {}

        for brand, brand_data in self.correct_matches.items():
            if not isinstance(brand_data, dict):
                continue

            for model, strings in brand_data.items():
                if not isinstance(strings, list):
                    continue

                # Get catalog entry for this brand/model
                catalog_entry = self.catalog.get(brand, {}).get(model, {})

                # Build matched data structure
                matched = {
                    "brand": brand,
                    "model": model,
                    "format": catalog_entry.get("format", "DE"),
                }
                # Add all other catalog fields except patterns and format
                for key, val in catalog_entry.items():
                    if key not in ["patterns", "format"]:
                        matched[key] = val

                # Create lookup entries for each correct string
                for correct_string in strings:
                    # Use the correct string as-is since it should already be normalized
                    if correct_string:
                        lookup[correct_string] = matched

        return lookup

    def _get_correct_matches_lookup(self) -> Dict[str, Dict[str, Any]]:
        """Lazy load field-specific correct matches lookup."""
        if self._correct_matches_lookup is None:
            self._correct_matches_lookup = self._build_correct_matches_lookup()
        return self._correct_matches_lookup

    def _extract_patterns_from_catalog(self) -> List[Dict[str, Any]]:
        """
        Extract all patterns from catalog data for this field type.

        Returns a list of pattern dictionaries with metadata.
        """
        patterns = []

        if not isinstance(self.catalog, dict):
            return patterns

        # Extract patterns based on field type
        if self.field_type == "soap":
            # Soap catalog has maker -> scent -> patterns structure
            for maker, maker_data in self.catalog.items():
                if isinstance(maker_data, dict) and "scents" in maker_data:
                    for scent, scent_data in maker_data["scents"].items():
                        if isinstance(scent_data, dict) and "patterns" in scent_data:
                            for pattern in scent_data["patterns"]:
                                patterns.append(
                                    {
                                        "pattern": pattern,
                                        "maker": maker,
                                        "scent": scent,
                                    }
                                )
        else:
            # Other catalogs have brand -> model -> patterns structure
            for brand, brand_data in self.catalog.items():
                if isinstance(brand_data, dict):
                    for model, model_data in brand_data.items():
                        if isinstance(model_data, dict) and "patterns" in model_data:
                            for pattern in model_data["patterns"]:
                                patterns.append(
                                    {
                                        "pattern": pattern,
                                        "brand": brand,
                                        "model": model,
                                    }
                                )

        return patterns

    def _get_catalog_patterns(self) -> List[Dict[str, Any]]:
        """Lazy load field-specific catalog patterns."""
        if self._catalog_patterns is None:
            self._catalog_patterns = self._extract_patterns_from_catalog()
        return self._catalog_patterns

    def _get_compiled_pattern(self, pattern_text: str) -> Optional[Any]:
        """Get or create a compiled regex pattern."""
        if pattern_text not in self._compiled_patterns:
            try:
                self._compiled_patterns[pattern_text] = re.compile(pattern_text, re.IGNORECASE)
            except re.error:
                # Skip invalid patterns
                return None
        return self._compiled_patterns[pattern_text]

    def _check_correct_matches(self, value: str) -> Optional[Dict[str, Any]]:
        # Use pre-normalized text from extraction
        if not value or not self.correct_matches:
            return None

        # Use pre-built lookup dictionary for O(1) access
        lookup = self._get_correct_matches_lookup()

        # Try exact match first
        result = lookup.get(value)
        if result:
            return result

        # Fall back to case-insensitive lookup for backward compatibility
        normalized_lower = value.lower()
        for key, match_data in lookup.items():
            if key.lower() == normalized_lower:
                return match_data

        return None

    def _get_format_from_catalog(self, brand: str, model: str) -> str:
        """Get format from catalog for a brand/model combination."""
        try:
            brand_data = self.catalog.get(brand, {})
            model_data = brand_data.get(model, {})
            return model_data.get("format", "DE")  # Default to DE for razors/blades
        except Exception:
            return "DE"

    def normalize(self, value: Optional[str]) -> Optional[str]:
        """
        Normalize a string for comparison.

        DEPRECATED: Normalization now happens in extraction phase.
        This method is kept for backward compatibility but should not be used.
        """
        if not isinstance(value, str):
            return None
        # Return the value as-is since normalization happens in extraction
        return value

    def clear_caches(self) -> None:
        """Clear all caches (useful for testing or when files are updated)."""
        self._correct_matches_lookup = None
        self._catalog_patterns = None
        self._compiled_patterns.clear()

    def match(
        self, value: str, original: str | None = None, bypass_correct_matches: bool = False
    ) -> MatchResult:
        """
        Enhanced match method with correct matches priority.

        Priority order:
        1. Correct matches file (highest priority, fastest) - unless bypassed
        2. Regex patterns (fallback, slower)
        3. Brand/alias fallbacks (lowest priority)

        Args:
            value: Normalized text string for matching
            original: Original text string for debugging (defaults to value if not provided)
            bypass_correct_matches: If True, skip correct matches check and go directly to regex
        """
        # Use provided original text or default to normalized text
        original_text = original if original is not None else value
        normalized_text = value

        # Step 1: Check correct matches first (highest priority) - unless bypassed
        if not bypass_correct_matches:
            correct_match = self._check_correct_matches(normalized_text)
            if correct_match:
                return create_match_result(
                    original=original_text,
                    matched=correct_match,
                    match_type="exact",
                    pattern=None,
                )

        # Step 2: Fall back to regex patterns (implemented by subclasses)
        # This should be implemented by each specific matcher
        return self._match_with_regex(normalized_text, original_text)

    def _match_with_regex(self, normalized_text: str, original_text: str) -> MatchResult:
        """
        Match using regex patterns. To be implemented by subclasses.

        This method should return a MatchResult with match_type set to MatchType.REGEX
        for regex-based matches.

        Args:
            normalized_text: Normalized text string for matching
            original_text: Original text string for debugging
        """
        raise NotImplementedError("Subclasses must implement _match_with_regex")
