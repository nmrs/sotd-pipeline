"""
Catalog loader for enrichment phase.

Loads handle and knot patterns from YAML catalogs for use in enrichment.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from sotd.match.utils.regex_error_utils import compile_regex_with_context, create_context_dict


class CatalogLoader:
    """
    Loads handle and knot patterns from YAML catalogs.

    Provides caching for performance and handles different catalog structures.
    """

    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path or Path("data")
        self._pattern_cache: Dict[str, List[str]] = {}
        self._compiled_pattern_cache: Dict[str, List[re.Pattern]] = {}
        self._handle_defaults_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def set_data_path(self, data_path: Path) -> None:
        """Point the loader at a different data directory.

        Cached patterns and handle defaults are dropped so the next load
        reads from the new directory. A no-op when the path is unchanged.
        """
        data_path = Path(data_path)
        if data_path == self.data_path:
            return
        self.data_path = data_path
        self._pattern_cache.clear()
        self._compiled_pattern_cache.clear()
        self._handle_defaults_cache.clear()

    def load_handle_patterns(self, brand: str, model: str) -> List[str]:
        """
        Load handle patterns for a specific brand and model.

        Args:
            brand: Brand name
            model: Model name

        Returns:
            List of pattern strings
        """
        return self._get_cached_patterns("handles", brand, model)

    def load_compiled_handle_patterns(self, brand: str, model: str) -> List[re.Pattern]:
        """
        Load compiled handle patterns for a specific brand and model.

        Args:
            brand: Brand name
            model: Model name

        Returns:
            List of compiled regex patterns
        """
        return self._get_cached_compiled_patterns("handles", brand, model)

    def load_knot_patterns(self, brand: str, model: str) -> List[str]:
        """
        Load knot patterns for a specific brand and model.

        Args:
            brand: Brand name
            model: Model name

        Returns:
            List of pattern strings
        """
        return self._get_cached_patterns("knots", brand, model)

    def load_compiled_knot_patterns(self, brand: str, model: str) -> List[re.Pattern]:
        """
        Load compiled knot patterns for a specific brand and model.

        Args:
            brand: Brand name
            model: Model name

        Returns:
            List of compiled regex patterns
        """
        return self._get_cached_compiled_patterns("knots", brand, model)

    def load_handle_maker_defaults(self, brand: str, model: Optional[str] = None) -> Dict[str, Any]:
        """
        Load handle maker defaults (like knot_size_mm) for a specific brand and model.

        Args:
            brand: Brand name
            model: Model name (optional, defaults to brand-level defaults)

        Returns:
            Dictionary containing handle maker defaults (e.g., {'knot_size_mm': 26})
        """
        cache_key = f"handle_defaults:{brand}:{model or 'brand'}"
        if cache_key in self._handle_defaults_cache:
            self._cache_hits += 1
            return self._handle_defaults_cache[cache_key]

        self._cache_misses += 1
        defaults = self._load_handle_maker_defaults_from_catalog(brand, model)
        self._handle_defaults_cache[cache_key] = defaults
        return defaults

    def _load_handle_maker_defaults_from_catalog(
        self, brand: str, model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Load handle maker defaults from the handles.yaml catalog.

        Args:
            brand: Brand name
            model: Model name (optional)

        Returns:
            Dictionary containing handle maker defaults
        """
        catalog_path = self.data_path / "handles.yaml"
        if not catalog_path.exists():
            return {}

        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                catalog_data = yaml.safe_load(f)
            # Validate patterns format if catalog data exists
            if catalog_data:
                from sotd.utils.catalog_validator import validate_patterns_format

                validate_patterns_format(catalog_data, catalog_path)
        except (yaml.YAMLError, OSError):
            return {}

        if not catalog_data:
            return {}

        # Search all handle sections: artisan_handles, manufacturer_handles, other_handles
        catalog_sections = [
            catalog_data.get("artisan_handles", {}),
            catalog_data.get("manufacturer_handles", {}),
            catalog_data.get("other_handles", {}),
        ]

        # Search through all catalog sections
        for catalog_section in catalog_sections:
            # Find brand in this catalog section
            brand_data = catalog_section.get(brand, {})
            if not brand_data:
                continue

            # If model is specified, check model level first
            if model and model in brand_data:
                model_data = brand_data[model]
                if isinstance(model_data, dict):
                    # Extract defaults (fields that are not 'patterns')
                    defaults = {k: v for k, v in model_data.items() if k != "patterns"}
                    if defaults:
                        return defaults

            # Check brand level defaults (fields that are not 'patterns' and not model names)
            brand_defaults = {}
            for key, value in brand_data.items():
                if key != "patterns" and not isinstance(value, dict):
                    brand_defaults[key] = value

            if brand_defaults:
                return brand_defaults

        return {}

    def _get_cached_patterns(self, catalog_type: str, brand: str, model: str) -> List[str]:
        """
        Get patterns from cache or load from catalog.

        Args:
            catalog_type: Type of catalog ("handles" or "knots")
            brand: Brand name
            model: Model name

        Returns:
            List of pattern strings
        """
        cache_key = f"{catalog_type}:{brand}:{model}"
        if cache_key in self._pattern_cache:
            self._cache_hits += 1
            return self._pattern_cache[cache_key]

        self._cache_misses += 1
        patterns = self._load_patterns_from_catalog(catalog_type, brand, model)
        self._pattern_cache[cache_key] = patterns
        return patterns

    def _get_cached_compiled_patterns(
        self, catalog_type: str, brand: str, model: str
    ) -> List[re.Pattern]:
        """
        Get compiled patterns from cache or compile from catalog.

        Args:
            catalog_type: Type of catalog ("handles" or "knots")
            brand: Brand name
            model: Model name

        Returns:
            List of compiled regex patterns
        """
        cache_key = f"{catalog_type}:{brand}:{model}"
        if cache_key in self._compiled_pattern_cache:
            self._cache_hits += 1
            return self._compiled_pattern_cache[cache_key]

        self._cache_misses += 1
        patterns = self._get_cached_patterns(catalog_type, brand, model)
        compiled_patterns = self.compile_patterns(patterns, catalog_type, brand, model)
        self._compiled_pattern_cache[cache_key] = compiled_patterns
        return compiled_patterns

    def _load_patterns_from_catalog(self, catalog_type: str, brand: str, model: str) -> List[str]:
        """
        Load patterns from YAML catalog file.

        Args:
            catalog_type: Type of catalog ("handles" or "knots")
            brand: Brand name
            model: Model name

        Returns:
            List of pattern strings
        """
        # Determine catalog file path
        if catalog_type == "handles":
            catalog_path = self.data_path / "handles.yaml"
        elif catalog_type == "knots":
            catalog_path = self.data_path / "knots.yaml"
        else:
            return []

        # Load catalog data
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                catalog_data = yaml.safe_load(f)
            # Validate patterns format if catalog data exists
            if catalog_data:
                from sotd.utils.catalog_validator import validate_patterns_format

                validate_patterns_format(catalog_data, catalog_path)
        except (yaml.YAMLError, OSError):
            return []

        if not catalog_data:
            return []

        # Navigate to the appropriate section based on catalog type
        if catalog_type == "handles":
            # Search all handle sections: artisan_handles, manufacturer_handles, other_handles
            catalog_sections = [
                catalog_data.get("artisan_handles", {}),
                catalog_data.get("manufacturer_handles", {}),
                catalog_data.get("other_handles", {}),
            ]
        elif catalog_type == "knots":
            catalog_sections = [catalog_data.get("known_knots", {})]
        else:
            return []

        patterns = []

        # Search through all catalog sections
        for catalog_section in catalog_sections:
            # Find brand in this catalog section
            brand_data = catalog_section.get(brand, {})
            if not brand_data:
                continue

            # Handle different catalog structures
            if catalog_type == "handles":
                # Handles catalog: brand -> model -> patterns
                if model and model in brand_data:
                    model_data = brand_data[model]
                    if isinstance(model_data, dict) and "patterns" in model_data:
                        patterns.extend(model_data["patterns"])
                else:
                    # Check for "Unspecified" model
                    unspecified_data = brand_data.get("Unspecified", {})
                    if isinstance(unspecified_data, dict) and "patterns" in unspecified_data:
                        patterns.extend(unspecified_data["patterns"])

            elif catalog_type == "knots":
                # Knots catalog: brand -> model -> patterns (or brand -> patterns for some entries)
                if model and model in brand_data:
                    model_data = brand_data[model]
                    if isinstance(model_data, dict) and "patterns" in model_data:
                        patterns.extend(model_data["patterns"])
                else:
                    # Check if brand has direct patterns (some knots have this structure)
                    if isinstance(brand_data, dict) and "patterns" in brand_data:
                        patterns.extend(brand_data["patterns"])

        return patterns

    def compile_patterns(
        self, patterns: List[str], catalog_type: str, brand: str, model: str
    ) -> List[re.Pattern]:
        """
        Compile regex patterns for efficient matching with enhanced error reporting.

        Args:
            patterns: List of pattern strings
            catalog_type: Type of catalog ("handles" or "knots")
            brand: Brand name
            model: Model name

        Returns:
            List[re.Pattern]: List of compiled patterns
        """
        compiled_patterns = []
        for pattern in patterns:
            # Create context for enhanced error reporting
            context = create_context_dict(
                file_path=f"data/{catalog_type}.yaml", brand=brand, model=model
            )
            compiled_pattern = compile_regex_with_context(pattern, context)
            compiled_patterns.append(compiled_pattern)
        return compiled_patterns

    def clear_pattern_cache(self):
        """Clear pattern cache."""
        self._pattern_cache.clear()
        self._compiled_pattern_cache.clear()
        self._handle_defaults_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache performance statistics.

        Returns:
            dict: Cache statistics
        """
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "total_requests": total_requests,
            "hit_rate_percent": hit_rate,
            "cached_patterns": len(self._pattern_cache),
            "cached_compiled_patterns": len(self._compiled_pattern_cache),
        }
